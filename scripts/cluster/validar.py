"""Verifica versões, SSH entre todos os nós e comunicação MPI nas VMs."""

import argparse
import json
import re
import shlex
import subprocess
import sys

from scripts.cluster.conectar import ROOT, executar_no


def json_remoto(nome, comando, timeout=120):
    texto = executar_no(nome, comando, timeout=timeout)
    # Open MPI 4 pode encaminhar diagnósticos do launcher ao stdout via SSH.
    # Preserve-os no stderr do validador, separado do documento JSON.
    diagnosticos = []
    conteudo = []
    for linha in texto.splitlines():
        if re.match(r'^\[[^\]]+:\d+\] ', linha):
            diagnosticos.append(linha)
        else:
            conteudo.append(linha)
    try:
        resultado = json.loads('\n'.join(conteudo))
    except json.JSONDecodeError as erro:
        raise ValueError(f'{nome}: resposta JSON inválida para {comando!r}: {texto[:1000]!r}') from erro
    for linha in diagnosticos:
        print(linha, file=sys.stderr)
    return resultado


def validar(config):
    nos = config['cluster_nodes']
    versoes = {}
    for no in nos:
        versoes[no['name']] = json_remoto(no['name'], 'cat /opt/projeto-sd/versions.json')
    if len({json.dumps(v, sort_keys=True) for v in versoes.values()}) != 1:
        raise ValueError(f'Versões divergentes: {versoes}')
    for origem in nos:
        for destino in nos:
            hostname = executar_no(origem['name'],
                f"sudo -u mpi ssh {shlex.quote(destino['name'])} hostname", timeout=30).strip()
            if hostname != destino['name']:
                raise ValueError(f'SSH de {origem["name"]} para {destino["name"]}: {hostname!r}')
    comando = [
        'sudo', '-u', 'mpi', 'timeout', '--kill-after=5s', '45s',
        'mpirun', '--hostfile', '/opt/projeto-sd/hostfile',
        '--mca', 'btl_tcp_if_include', config['subnet'],
        '--mca', 'oob_tcp_if_include', config['subnet'],
        '--map-by', 'ppr:1:node', '-np', str(len(nos)),
        '--wdir', '/opt/projeto-sd/code', '/usr/bin/python3',
        '-m', 'scripts.cluster.testar_mpi', '--hosts', *[no['name'] for no in nos],
    ]
    resultado = json_remoto('master', shlex.join(comando), timeout=90)
    if resultado.get('ok') is not True:
        raise ValueError(f'Smoke MPI falhou: {resultado}')
    return {'versoes': versoes, 'mpi': resultado}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        config = json.loads((ROOT / '.cluster/config.json').read_text(encoding='utf-8'))
        print(json.dumps(validar(config), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as erro:
        detalhes = getattr(erro, 'stderr', None) or str(erro)
        parser.exit(1, f'Falha na validação do cluster: {detalhes}\n')


if __name__ == '__main__':
    main()
