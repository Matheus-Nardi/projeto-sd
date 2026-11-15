"""Valida playbooks, idempotência e SSH/MPI em containers Ubuntu descartáveis.

Execute no Linux/WSL com Docker. Não substitui vagrant up nem mede desempenho.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from scripts.cluster.conectar import extrair_chave
from scripts.cluster.preparar import ROOT, configurar


def comando(args, timeout=600):
    resultado = subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)
    return resultado.stdout


def testar(workers, source_dir):
    prefixo = 'sd-infra-' + uuid.uuid4().hex[:10]
    containers = []
    rede_criada = False
    config = configurar(workers=workers)
    config.update(cluster_source_dir='/vagrant', cluster_source_remote=True,
                  cluster_manage_services=False)
    try:
        comando(['docker', 'network', 'create', prefixo])
        rede_criada = True
        for no in config['cluster_nodes']:
            container = prefixo + '-' + no['name']
            comando(['docker', 'run', '-d', '--name', container,
                     '--hostname', no['name'], '--network', prefixo,
                     '--network-alias', no['name'],
                     '--mount', f'type=bind,src={source_dir},dst=/vagrant,readonly',
                     'projeto-sd-infra-test'])
            containers.append(container)
            inspecao = json.loads(comando(['docker', 'inspect', container]))[0]
            if not inspecao['State']['Running']:
                raise ValueError(f'Container não iniciou: {inspecao["State"]}')
            no['ip'] = inspecao['NetworkSettings']['Networks'][prefixo]['IPAddress']
            prazo = time.monotonic() + 15
            while True:
                pronto = subprocess.run([
                    'docker', 'exec', container, '/usr/bin/python3', '-c',
                    'import socket; socket.create_connection(("127.0.0.1", 22), timeout=1).close()'
                ], capture_output=True, timeout=5)
                if pronto.returncode == 0:
                    break
                if time.monotonic() >= prazo:
                    raise ValueError(f'SSH não ficou pronto em {container}')
                time.sleep(0.2)
        confianca = {'cluster_host_keys': {}, 'cluster_user_keys': {}}
        with tempfile.TemporaryDirectory(prefix='sd-infra-') as temporario:
            config_path = Path(temporario) / 'config.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            for no, container in zip(config['cluster_nodes'], containers):
                comando(['docker', 'cp', str(config_path), container + ':/tmp/config.json'])
                inventory_path = Path(temporario) / 'inventory.ini'
                inventory_path.write_text(f"[cluster]\n{no['name']}\n", encoding='utf-8')
                comando(['docker', 'cp', str(inventory_path), container + ':/tmp/inventory.ini'])
                base = ['docker', 'exec', container, 'ansible-playbook',
                        '/vagrant/infra/ansible/node.yml', '-i', '/tmp/inventory.ini',
                        '-c', 'local', '-e', '@/tmp/config.json',
                        '-e', 'ansible_python_interpreter=/usr/bin/python3']
                comando(base + ['--syntax-check'])
                print(f"Provisionando {no['name']}...", flush=True)
                print(comando(base), flush=True)
                comando(['docker', 'exec', container, '/usr/sbin/sshd', '-t'])
                comando(['docker', 'kill', '--signal=HUP', container])
                confianca['cluster_host_keys'][no['name']] = extrair_chave(comando([
                    'docker', 'exec', container, 'cat', '/etc/ssh/ssh_host_projeto_sd_ed25519_key.pub']))
                confianca['cluster_user_keys'][no['name']] = extrair_chave(comando([
                    'docker', 'exec', container, 'cat', '/home/mpi/.ssh/id_ed25519.pub']))
                repeticao = comando(base)
                if not re.search(r'changed=0\s+unreachable=0\s+failed=0', repeticao):
                    raise ValueError('Provisionamento não idempotente:\n' + repeticao)
                print(f"{no['name']}: segunda aplicação sem mudanças.", flush=True)
            if len(set(confianca['cluster_user_keys'].values())) != len(containers):
                raise ValueError('Os nós não têm chaves próprias distintas')
            if len(set(confianca['cluster_host_keys'].values())) != len(containers):
                raise ValueError('Os nós não têm chaves de host distintas')
            trust_path = Path(temporario) / 'trust.json'
            trust_path.write_text(json.dumps(confianca), encoding='utf-8')
            for no, container in zip(config['cluster_nodes'], containers):
                comando(['docker', 'cp', str(trust_path), container + ':/tmp/trust.json'])
                base = ['docker', 'exec', container, 'ansible-playbook',
                        '/vagrant/infra/ansible/conectar.yml', '-i', '/tmp/inventory.ini',
                        '-c', 'local', '-e', '@/tmp/config.json', '-e', '@/tmp/trust.json',
                        '-e', 'ansible_python_interpreter=/usr/bin/python3']
                comando(base + ['--syntax-check'])
                comando(base)
                repeticao = comando(base)
                if not re.search(r'changed=0\s+unreachable=0\s+failed=0', repeticao):
                    raise ValueError('Confiança SSH não idempotente:\n' + repeticao)
            versoes = [json.loads(comando(['docker', 'exec', c, 'cat',
                                         '/opt/projeto-sd/versions.json'])) for c in containers]
            if any(v != versoes[0] for v in versoes):
                raise ValueError('Versões diferentes entre os nós')
            for container in containers:
                for no in config['cluster_nodes']:
                    for destino in (no['name'], no['ip']):
                        hostname = comando(['docker', 'exec', '-u', 'mpi', container,
                                            'ssh', destino, 'hostname'], timeout=15).strip()
                        if hostname != no['name']:
                            raise ValueError('SSH retornou hostname inesperado')
            dados = ['docker', 'exec', containers[0], 'ansible-playbook',
                     '/vagrant/infra/ansible/dados.yml', '-i', '/tmp/inventory.ini',
                     '-c', 'local', '-e', 'ansible_python_interpreter=/usr/bin/python3',
                     '-e', 'cluster_data_source=/vagrant/tests/fixtures/enem_manual.csv']
            comando(dados + ['--syntax-check'])
            comando(dados)
            if not re.search(r'changed=0\s+unreachable=0\s+failed=0', comando(dados)):
                raise ValueError('Preparação dos dados não idempotente')
            mpi = ['docker', 'exec', '-u', 'mpi', containers[0],
                   'timeout', '--kill-after=5s', '45s', 'mpirun',
                   '--hostfile', '/opt/projeto-sd/hostfile', '--map-by', 'ppr:1:node',
                   '-np', str(workers + 1), '--wdir', '/opt/projeto-sd/code',
                   '/usr/bin/python3', '-m', 'scripts.cluster.testar_mpi', '--hosts',
                   *[no['name'] for no in config['cluster_nodes']]]
            smoke = json.loads(comando(mpi, timeout=90))
            if smoke.get('ok') is not True:
                raise ValueError(f'Smoke MPI falhou: {smoke}')
            # Uma distribuição esperada incorreta deve retornar erro sem travar.
            invalido = mpi[:-1] + ['inexistente']
            falha = subprocess.run(invalido, capture_output=True, text=True, timeout=90)
            if falha.returncode in (0, 124, 125, 126, 127, 137) or 'Distribuição de processos incorreta' not in falha.stderr:
                raise ValueError('Smoke negativo não detectou distribuição incorreta: ' + falha.stderr)
            print(json.dumps({'ok': True, 'workers': workers,
                              'versoes': versoes[0], 'mpi': smoke}, indent=2), flush=True)
    finally:
        for container in reversed(containers):
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        if rede_criada:
            subprocess.run(['docker', 'network', 'rm', prefixo], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=(1, 2, 4), default=2)
    args = parser.parse_args()
    try:
        # Congela as fontes: edições no checkout durante o teste não devem
        # parecer mudanças indevidas de uma segunda aplicação do Ansible.
        staging = ROOT / '.cluster'
        staging.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='infra-snapshot-', dir=staging) as pasta:
            snapshot = Path(pasta)
            for nome in ('infra', 'src', 'scripts', 'tests'):
                shutil.copytree(ROOT / nome, snapshot / nome,
                                ignore=shutil.ignore_patterns('__pycache__', 'inventory.local.yml'))
            testar(args.workers, snapshot)
    except (OSError, ValueError, subprocess.SubprocessError) as erro:
        detalhes = '\n'.join(str(v) for v in (getattr(erro, 'stderr', None),
                                               getattr(erro, 'stdout', None)) if v) or str(erro)
        parser.exit(1, f'Falha na validação isolada: {detalhes}\n')


if __name__ == '__main__':
    main()
