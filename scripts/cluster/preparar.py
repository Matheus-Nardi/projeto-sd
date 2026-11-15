"""Gera a topologia das VMs após verificar rotas e orçamento do host."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def configurar(**opcoes):
    config = json.loads((ROOT / 'infra/cluster.json').read_text(encoding='utf-8'))
    config.update({k: v for k, v in opcoes.items() if v is not None})
    if config['workers'] not in (1, 2, 4):
        raise ValueError('Use 1, 2 ou 4 workers')
    for campo in ('cpus', 'memory_mb'):
        if type(config[campo]) is not int or config[campo] <= 0:
            raise ValueError(f'{campo} deve ser um inteiro positivo')
    rede = ipaddress.IPv4Network(config['subnet'], strict=True)
    privadas = [ipaddress.IPv4Network(r) for r in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    if rede.prefixlen != 24 or not any(rede.subnet_of(r) for r in privadas):
        raise ValueError('Use uma sub-rede IPv4 privada /24')
    config['cluster_nodes'] = [
        {'name': 'master' if i == 0 else f'worker{i}',
         'ip': str(rede.network_address + 10 + i), 'slots': config['cpus']}
        for i in range(config['workers'] + 1)
    ]
    config.update(cluster_source_dir='/vagrant', cluster_source_remote=True)
    return config


def verificar_subrede(subnet, rotas):
    rede = ipaddress.IPv4Network(subnet)
    for rota in rotas:
        existente = ipaddress.IPv4Network(rota, strict=False)
        if existente.prefixlen != 0 and rede.overlaps(existente):
            raise ValueError(f'A sub-rede {subnet} conflita com a rota {rota}')


def verificar_recursos(config, cpus, memoria_mb, disco_mb):
    nos = len(config['cluster_nodes'])
    if nos * config['cpus'] > cpus:
        raise ValueError('As VMs excedem o número de CPUs lógicas do host')
    if nos * config['memory_mb'] + 2048 > memoria_mb:
        raise ValueError('RAM insuficiente para as VMs e reserva de 2 GiB para o host')
    if nos * 10240 > disco_mb:
        raise ValueError('Reserve ao menos 10 GiB livres por VM')


def recursos_e_rotas():
    if os.name == 'nt':
        comando = (
            '$mem = Get-CimInstance Win32_OperatingSystem; '
            '@{memoria_mb=[int]($mem.FreePhysicalMemory/1024); '
            'rotas=@(Get-NetRoute -AddressFamily IPv4 | '
            'Select-Object -ExpandProperty DestinationPrefix)} | ConvertTo-Json -Compress'
        )
        resultado = subprocess.run(['powershell', '-NoProfile', '-Command', comando],
                                   check=True, capture_output=True, text=True)
        info = json.loads(resultado.stdout)
    else:
        memoria = dict(linha.split(':', 1) for linha in Path('/proc/meminfo').read_text().splitlines())
        resultado = subprocess.run(['ip', '-j', '-4', 'route', 'show', 'table', 'all'],
                                   check=True, capture_output=True, text=True)
        info = {'memoria_mb': int(memoria['MemAvailable'].split()[0]) // 1024,
                'rotas': [r['dst'] for r in json.loads(resultado.stdout) if r['dst'] != 'default']}
    # Boxes e discos virtuais podem estar em volumes diferentes do repositório.
    pasta_vms = Path.home() / 'VirtualBox VMs'
    vbox = shutil.which('VBoxManage')
    if vbox:
        resultado = subprocess.run([vbox, 'list', 'systemproperties'],
                                   check=True, capture_output=True, text=True)
        for linha in resultado.stdout.splitlines():
            if linha.startswith('Default machine folder:'):
                pasta_vms = Path(linha.split(':', 1)[1].strip())
                break
    pasta_boxes = Path(os.environ.get('VAGRANT_HOME', str(Path.home() / '.vagrant.d')))
    livres = []
    for pasta in (ROOT, pasta_vms, pasta_boxes):
        while not pasta.exists() and pasta != pasta.parent:
            pasta = pasta.parent
        livres.append(shutil.disk_usage(pasta).free // (1024 * 1024))
    info.update(cpus=os.cpu_count() or 1, disco_mb=min(livres))
    return info


def salvar(config):
    destino = ROOT / '.cluster'
    destino.mkdir(exist_ok=True)
    (destino / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    inventarios = destino / 'inventory-local'
    inventarios.mkdir(exist_ok=True)
    for no in config['cluster_nodes']:
        (inventarios / f"{no['name']}.ini").write_text(
            f"[cluster]\n{no['name']} ansible_connection=local ansible_python_interpreter=/usr/bin/python3\n",
            encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=(1, 2, 4))
    parser.add_argument('--cpus', type=int)
    parser.add_argument('--memory-mb', type=int)
    parser.add_argument('--subnet')
    parser.add_argument('--rede-existente', action='store_true',
                        help='a sub-rede já é deste cluster (ampliar VMs existentes)')
    args = parser.parse_args()
    try:
        opcoes = vars(args)
        rede_existente = opcoes.pop('rede_existente')
        config = configurar(**opcoes)
        info = recursos_e_rotas()
        rotas = info.pop('rotas')
        if not rede_existente:
            verificar_subrede(config['subnet'], rotas)
        verificar_recursos(config, **info)
        salvar(config)
    except (OSError, ValueError, subprocess.CalledProcessError) as erro:
        parser.exit(1, f'Erro: {erro}\n')
    nos = len(config['cluster_nodes'])
    print(f"Topologia gerada em .cluster/: {nos} nós, {nos * config['cpus']} vCPUs, "
          f"{nos * config['memory_mb']} MiB RAM. Sub-rede verificada.")


if __name__ == '__main__':
    main()
