"""Troca somente chaves públicas entre VMs já provisionadas pelo Vagrant."""

import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def executar_no(nome, comando, timeout=120):
    if not re.fullmatch(r'master|worker[1-4]', nome):
        raise ValueError(f'Nome de VM inválido: {nome!r}')
    resultado = subprocess.run(['vagrant', 'ssh', nome, '-c', comando], cwd=ROOT,
                               check=True, capture_output=True, text=True,
                               encoding='utf-8', timeout=timeout)
    return resultado.stdout


def extrair_chave(texto):
    chaves = [linha.strip() for linha in texto.splitlines()
              if re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [^\r\n]+)?', linha.strip())]
    if len(chaves) != 1:
        raise ValueError('Esperada exatamente uma chave pública ed25519')
    return ' '.join(chaves[0].split()[:2])


def validar_confianca(config, confianca):
    nomes = {no['name'] for no in config['cluster_nodes']}
    for campo in ('cluster_host_keys', 'cluster_user_keys'):
        chaves = confianca[campo]
        if set(chaves) != nomes or len(set(chaves.values())) != len(nomes):
            raise ValueError(f'{campo}: cada nó deve ter uma chave pública própria')


def conectar(config, executar=executar_no):
    confianca = {'cluster_host_keys': {}, 'cluster_user_keys': {}}
    # Primeiro coleta tudo. Uma VM indisponível impede alterar a confiança dos demais.
    for no in config['cluster_nodes']:
        nome = no['name']
        confianca['cluster_host_keys'][nome] = extrair_chave(executar(
            nome, 'sudo cat /etc/ssh/ssh_host_projeto_sd_ed25519_key.pub'))
        confianca['cluster_user_keys'][nome] = extrair_chave(executar(
            nome, 'sudo cat /home/mpi/.ssh/id_ed25519.pub'))
    validar_confianca(config, confianca)
    (ROOT / '.cluster/trust.json').write_text(json.dumps(confianca, indent=2) + '\n', encoding='utf-8')
    for no in config['cluster_nodes']:
        nome = no['name']
        saida = executar(nome, 'sudo ansible-playbook /vagrant/infra/ansible/conectar.yml '
                        f'-i /vagrant/.cluster/inventory-local/{nome}.ini '
                        '-e @/vagrant/.cluster/config.json -e @/vagrant/.cluster/trust.json')
        print(saida)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        config = json.loads((ROOT / '.cluster/config.json').read_text(encoding='utf-8'))
        conectar(config)
    except (OSError, ValueError, subprocess.SubprocessError) as erro:
        detalhes = getattr(erro, 'stderr', None) or str(erro)
        parser.exit(1, f'Falha na configuração SSH: {detalhes}\n')


if __name__ == '__main__':
    main()
