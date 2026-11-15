"""Cluster em containers Docker (Linux/WSL): rápido para desenvolver e ensaiar.

    python3 -m scripts.cluster.docker subir --workers 4 [--cpus 1]
    python3 -m scripts.cluster.docker dados dados/enem_2023_real.csv
    python3 -m scripts.cluster.docker executar -- python3 -m unittest discover -s tests
    python3 -m scripts.cluster.docker atualizar      # recopia o código para os nós
    python3 -m scripts.cluster.docker derrubar

Usa a mesma role Ansible das VMs. Containers dividem o kernel e a CPU do
computador: servem para funcionamento e ensaio, não substituem máquinas reais.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.cluster.conectar import extrair_chave, validar_confianca


ROOT = Path(__file__).resolve().parents[2]
IMAGEM = 'projeto-sd-no'
REDE = 'projeto-sd-rede'
ROTULO = 'projeto-sd-cluster'
RAIZ = '/opt/projeto-sd'


def sh(*args, timeout=900):
    return subprocess.run(args, check=True, text=True, capture_output=True,
                          timeout=timeout).stdout


def container(no):
    return f'{ROTULO}-{no}'


def nos_ativos():
    """Nomes dos nós em execução, com o mestre primeiro."""
    nomes = sh('docker', 'ps', '--filter', f'label={ROTULO}',
               '--format', '{{.Names}}').split()
    nos = sorted(nome.removeprefix(ROTULO + '-') for nome in nomes)
    return sorted(nos, key=lambda no: (no != 'master', len(no), no))


def em_paralelo(funcao, itens):
    with ThreadPoolExecutor(max_workers=len(itens)) as executor:
        return list(executor.map(funcao, itens))


def playbook(no, nome, *extras):
    return sh('docker', 'exec', container(no), 'ansible-playbook',
              f'/vagrant/infra/ansible/{nome}', '-i', '/tmp/inventory.ini', '-c', 'local',
              '-e', '@/tmp/config.json', '-e', 'ansible_python_interpreter=/usr/bin/python3',
              *extras)


def derrubar():
    ids = sh('docker', 'ps', '-aq', '--filter', f'label={ROTULO}').split()
    if ids:
        sh('docker', 'rm', '-f', *ids)
    subprocess.run(['docker', 'network', 'rm', REDE], capture_output=True)


def subir(workers, cpus=None):
    sh('docker', 'build', '-t', IMAGEM, str(ROOT / 'infra/docker'))
    derrubar()
    sh('docker', 'network', 'create', REDE)
    nos = [{'name': 'master' if i == 0 else f'worker{i}', 'slots': 1}
           for i in range(workers + 1)]
    # Só o necessário é montado, somente leitura; nada de .vagrant/ ou .cluster/.
    montagens = []
    for pasta in ('infra', 'src', 'scripts', 'tests'):
        montagens += ['--mount', f'type=bind,src={ROOT / pasta},dst=/vagrant/{pasta},readonly']
    for no in nos:
        limite = ['--cpus', str(cpus)] if cpus else []
        sh('docker', 'run', '-d', '--name', container(no['name']), '--label', ROTULO,
           '--hostname', no['name'], '--network', REDE, '--network-alias', no['name'],
           *limite, *montagens, IMAGEM)
        dados = json.loads(sh('docker', 'inspect', container(no['name'])))[0]
        no['ip'] = dados['NetworkSettings']['Networks'][REDE]['IPAddress']
    config = {'cluster_nodes': nos, 'cluster_source_dir': '/vagrant',
              'cluster_source_remote': True, 'cluster_manage_services': False}
    nomes = [no['name'] for no in nos]
    with tempfile.TemporaryDirectory() as pasta:
        arquivos = {'config.json': json.dumps(config)}

        def copiar(no):
            for nome, texto in dict(arquivos, **{'inventory.ini': f'[cluster]\n{no}\n'}).items():
                (Path(pasta) / f'{no}-{nome}').write_text(texto, encoding='utf-8')
                sh('docker', 'cp', str(Path(pasta) / f'{no}-{nome}'),
                   f'{container(no)}:/tmp/{nome}')

        def provisionar(no):
            copiar(no)
            playbook(no, 'node.yml')
            sh('docker', 'kill', '--signal=HUP', container(no))  # sshd relê a chave de host
            return (extrair_chave(sh('docker', 'exec', container(no), 'cat',
                                     '/etc/ssh/ssh_host_projeto_sd_ed25519_key.pub')),
                    extrair_chave(sh('docker', 'exec', container(no), 'cat',
                                     '/home/mpi/.ssh/id_ed25519.pub')))

        chaves = em_paralelo(provisionar, nomes)
        confianca = {'cluster_host_keys': {n: c[0] for n, c in zip(nomes, chaves)},
                     'cluster_user_keys': {n: c[1] for n, c in zip(nomes, chaves)}}
        validar_confianca(config, confianca)
        arquivos = {'trust.json': json.dumps(confianca)}

        def conectar(no):
            copiar(no)
            playbook(no, 'conectar.yml', '-e', '@/tmp/trust.json')

        em_paralelo(conectar, nomes)
    return nomes


def atualizar():
    em_paralelo(lambda no: playbook(no, 'node.yml'), nos_ativos())


def enviar_dados(arquivo):
    destino = f'{RAIZ}/dados/{Path(arquivo).name}'
    sh('docker', 'cp', str(arquivo), f'{container("master")}:{destino}')
    sh('docker', 'exec', container('master'), 'chown', 'mpi:mpi', destino)
    return destino


def executar(comando):
    """Roda no mestre, como mpi, na pasta do código; devolve o código de saída."""
    return subprocess.run(['docker', 'exec', '-u', 'mpi', '-w', f'{RAIZ}/code',
                           container('master'), *comando]).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    acoes = parser.add_subparsers(dest='acao', required=True)
    acao = acoes.add_parser('subir', help='recria o cluster do zero')
    acao.add_argument('--workers', type=int, default=2)
    acao.add_argument('--cpus', type=float, help='limite de CPU por container')
    acoes.add_parser('atualizar', help='recopia o código para os nós')
    acoes.add_parser('derrubar', help='remove containers e rede deste cluster')
    acao = acoes.add_parser('dados', help='copia um CSV para o disco do mestre')
    acao.add_argument('arquivo', type=Path)
    acao = acoes.add_parser('executar', help='roda um comando no mestre como mpi')
    acao.add_argument('comando', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.acao == 'subir':
            if args.workers < 1:
                parser.error('Use ao menos 1 worker')
            print('Nós prontos:', ' '.join(subir(args.workers, args.cpus)))
        elif args.acao == 'atualizar':
            atualizar()
        elif args.acao == 'derrubar':
            derrubar()
        elif args.acao == 'dados':
            print(enviar_dados(args.arquivo))
        else:
            comando = args.comando[1:] if args.comando[:1] == ['--'] else args.comando
            if not comando:
                parser.error('Informe o comando a executar')
            sys.exit(executar(comando))
    except (OSError, ValueError, subprocess.SubprocessError) as erro:
        detalhes = '\n'.join(str(v)[-3000:] for v in (getattr(erro, 'stdout', None),
                                                     getattr(erro, 'stderr', None)) if v)
        parser.exit(1, f'Erro: {detalhes or erro}\n')


if __name__ == '__main__':
    main()
