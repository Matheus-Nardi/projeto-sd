"""Executa os cenários sequencial e MPI, confere a corretude e grava CSV e resumo.

Uso (na raiz do projeto):
    python3 -m scripts.experimentos.executar ENTRADA --saida-dir DIR [opções]
"""

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import time


POLITICAS = ('estatica', 'dinamica')
AMBIENTES = ('local', 'vm')
VERSOES = Path('/opt/projeto-sd/versions.json')
OBSERVACAO = ('tempo_total_s é medido dentro do programa (exclui o lançamento do mpirun); '
              'tempo_externo_s inclui o lançamento. O mestre é dedicado: W workers usam W+1 processos.')
COLUNAS = ['cenario', 'modo', 'politica', 'workers', 'repeticao', 'aquecimento', 'tempo_total_s',
           'tempo_externo_s', 'blocos', 'bytes_enviados', 'tarefas_por_worker',
           'tempo_ocupado_por_worker_s']


def comando_sequencial(entrada, bloco_linhas, saida):
    return [sys.executable, '-m', 'src.sequencial', str(entrada),
            '--bloco-linhas', str(bloco_linhas), '--saida', str(saida)]


def comando_mpi(entrada, bloco_linhas, saida, politica, workers, atrasos=(), hostfile=None,
                rede=None, timeout=600):
    comando = ['timeout', '--kill-after=5s', f'{timeout}s', 'mpirun']
    if hostfile:
        comando += ['--hostfile', str(hostfile), '--map-by', 'ppr:1:node']
    else:
        comando += ['--oversubscribe']
    if rede:
        comando += ['--mca', 'btl_tcp_if_include', rede, '--mca', 'oob_tcp_if_include', rede]
    comando += ['-np', str(workers + 1), sys.executable, '-m', 'src.distribuido', str(entrada),
                '--politica', politica, '--bloco-linhas', str(bloco_linhas), '--saida', str(saida)]
    for atraso in atrasos:
        comando += ['--atraso', atraso]
    return comando


def extrair_metricas(stderr):
    """Procura de trás para frente a última linha JSON com tempo_total_s."""
    for linha in reversed(stderr.splitlines()):
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dados, dict) and 'tempo_total_s' in dados:
            return dados
    raise ValueError('Métricas (JSON com tempo_total_s) não encontradas no stderr')


def _e_aquecimento(valor):
    return valor in (True, 1, '1')


def _por_workers(speedup, resumo):
    return None if speedup is None else speedup / resumo['workers']


def resumir(execucoes):
    """Um dict por cenário (ordem de primeira aparição), ignorando as de aquecimento."""
    grupos = {}
    for execucao in execucoes:
        if _e_aquecimento(execucao['aquecimento']):
            continue
        grupos.setdefault(execucao['cenario'], []).append(execucao)

    resumos = []
    for cenario, medidas in grupos.items():
        tempos = [float(m['tempo_total_s']) for m in medidas]
        primeira = medidas[0]
        resumos.append({
            'cenario': cenario,
            'modo': primeira['modo'],
            'politica': primeira['politica'] or None,
            'workers': int(primeira['workers']),
            'repeticoes': len(tempos),
            'mediana_s': statistics.median(tempos),
            'min_s': min(tempos),
            'max_s': max(tempos),
            'desvio_padrao_s': statistics.stdev(tempos) if len(tempos) > 1 else 0.0,
        })

    sequencial = next((r for r in resumos if r['modo'] == 'sequencial'), None)
    for resumo in resumos:
        ehmpi = resumo['modo'] == 'mpi'
        mpi_1 = None
        if ehmpi:
            mpi_1 = next((r for r in resumos if r['modo'] == 'mpi'
                          and r['politica'] == resumo['politica'] and r['workers'] == 1), None)
        vs_sequencial = sequencial['mediana_s'] / resumo['mediana_s'] if sequencial else None
        vs_mpi_1 = mpi_1['mediana_s'] / resumo['mediana_s'] if mpi_1 else None
        resumo['speedup_vs_sequencial'] = vs_sequencial
        resumo['speedup_vs_mpi_1'] = vs_mpi_1
        resumo['eficiencia_vs_sequencial'] = _por_workers(vs_sequencial, resumo) if ehmpi else None
        resumo['eficiencia_vs_mpi_1'] = _por_workers(vs_mpi_1, resumo) if ehmpi else None
    return resumos


def _ler_hostfile(caminho):
    if caminho is None:
        return None
    linhas = Path(caminho).read_text(encoding='utf-8').splitlines()
    return [linha.strip() for linha in linhas if linha.strip()]


def _ler_versoes():
    try:
        return json.loads(VERSOES.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _json_compacto(valor):
    return None if valor is None else json.dumps(valor, sort_keys=True, separators=(',', ':'))


def _linha_csv(execucao):
    return {
        'cenario': execucao['cenario'],
        'modo': execucao['modo'],
        'politica': execucao['politica'],
        'workers': execucao['workers'],
        'repeticao': execucao['repeticao'],
        'aquecimento': 1 if execucao['aquecimento'] else 0,
        'tempo_total_s': execucao['tempo_total_s'],
        'tempo_externo_s': execucao['tempo_externo_s'],
        'blocos': execucao['blocos'],
        'bytes_enviados': execucao['bytes_enviados'],
        'tarefas_por_worker': _json_compacto(execucao['tarefas_por_worker']),
        'tempo_ocupado_por_worker_s': _json_compacto(execucao['tempo_ocupado_por_worker_s']),
    }


def _gravar_csv(caminho, execucoes):
    with caminho.open('w', encoding='utf-8', newline='') as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, delimiter=';', lineterminator='\n')
        escritor.writeheader()
        for execucao in execucoes:
            escritor.writerow(_linha_csv(execucao))


def executar_experimento(args, rodar=subprocess.run, relogio=time.perf_counter):
    saida_dir = Path(args.saida_dir)
    saida_dir.mkdir(parents=True, exist_ok=True)
    temporario = saida_dir / '_saida.json'
    hostfile = _ler_hostfile(args.hostfile)
    atrasos = list(args.atraso or [])

    cenarios = [('sequencial', None, None)]
    cenarios += [(f'mpi-{p}-{w}w', p, w) for p in args.politicas for w in args.workers]

    execucoes = []
    referencia = None
    try:
        for nome, politica, workers in cenarios:
            for indice in range(args.aquecimento + args.repeticoes):
                aquecimento = indice < args.aquecimento
                repeticao = indice + 1 if aquecimento else indice - args.aquecimento + 1
                if politica is None:
                    comando = comando_sequencial(args.entrada, args.bloco_linhas, temporario)
                else:
                    comando = comando_mpi(args.entrada, args.bloco_linhas, temporario, politica,
                                          workers, atrasos=atrasos, hostfile=args.hostfile,
                                          rede=args.rede, timeout=args.timeout)
                if temporario.exists():
                    temporario.unlink()
                inicio = relogio()
                proc = rodar(comando, capture_output=True, text=True)
                tempo_externo = relogio() - inicio
                if proc.returncode != 0:
                    raise RuntimeError(f'Falha em {nome} (código {proc.returncode}): '
                                       f'{proc.stderr[-2000:]}')
                metricas = extrair_metricas(proc.stderr)
                resultado = json.loads(temporario.read_text(encoding='utf-8'))
                if referencia is None:
                    referencia = resultado
                elif resultado != referencia:
                    raise RuntimeError(f'Resultado divergente em {nome}')

                tipo = 'aquecimento' if aquecimento else 'medida'
                print(f'{nome} rep {repeticao} ({tipo}): {metricas["tempo_total_s"]:.3f} s',
                      flush=True)
                execucoes.append({
                    'cenario': nome,
                    'modo': 'sequencial' if politica is None else 'mpi',
                    'politica': politica,
                    'workers': 0 if workers is None else workers,
                    'repeticao': repeticao,
                    'aquecimento': aquecimento,
                    'tempo_total_s': float(metricas['tempo_total_s']),
                    'tempo_externo_s': tempo_externo,
                    'blocos': metricas.get('blocos'),
                    'bytes_enviados': metricas.get('bytes_enviados'),
                    'tarefas_por_worker': metricas.get('tarefas_por_worker'),
                    'tempo_ocupado_por_worker_s': metricas.get('tempo_ocupado_por_worker_s'),
                })

        cenarios_resumidos = resumir(execucoes)
        resumo = {
            'data': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'rotulo': args.rotulo,
            'ambiente': args.ambiente,
            'commit': args.commit,
            'entrada': dict(referencia['entrada'], arquivo=str(args.entrada)),
            'bloco_linhas': args.bloco_linhas,
            'atrasos': atrasos,
            'repeticoes': args.repeticoes,
            'aquecimento': args.aquecimento,
            'timeout_s': args.timeout,
            'hostfile': hostfile,
            'rede': args.rede,
            'maquina': {
                'hostname': socket.gethostname(),
                'cpus': os.cpu_count(),
                'plataforma': platform.platform(),
                'python': platform.python_version(),
            },
            'versoes': _ler_versoes(),
            'observacao': OBSERVACAO,
            'cenarios': cenarios_resumidos,
        }
        _gravar_csv(saida_dir / 'execucoes.csv', execucoes)
        (saida_dir / 'resumo.json').write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return resumo
    finally:
        if temporario.exists():
            temporario.unlink()


def _formatar(valor):
    return '-' if valor is None else f'{valor:.2f}'


def _imprimir_tabela(cenarios):
    print(f'{"cenário":<18}{"mediana (s)":>13}{"sp/seq":>9}{"sp/mpi-1":>10}')
    for c in cenarios:
        print(f'{c["cenario"]:<18}{c["mediana_s"]:>13.3f}'
              f'{_formatar(c["speedup_vs_sequencial"]):>9}{_formatar(c["speedup_vs_mpi_1"]):>10}')


def construir_parser():
    parser = argparse.ArgumentParser(description='Executa os cenários sequencial e MPI e gera CSV e resumo')
    parser.add_argument('entrada', type=Path)
    parser.add_argument('--saida-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, nargs='+', default=[1, 2])
    parser.add_argument('--politicas', nargs='+', choices=POLITICAS, default=list(POLITICAS))
    parser.add_argument('--repeticoes', type=int, default=5)
    parser.add_argument('--aquecimento', type=int, default=1)
    parser.add_argument('--bloco-linhas', type=int, default=10000)
    parser.add_argument('--atraso', action='append', metavar='RANK=SEGUNDOS',
                        help='atraso artificial em um worker (pode repetir)')
    parser.add_argument('--hostfile', type=Path)
    parser.add_argument('--rede', metavar='SUBREDE')
    parser.add_argument('--ambiente', choices=AMBIENTES, default='local')
    parser.add_argument('--commit', default='desconhecido')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--rotulo')
    return parser


def _validar(args):
    if args.repeticoes < 1:
        raise ValueError('--repeticoes deve ser >= 1')
    if args.aquecimento < 0:
        raise ValueError('--aquecimento não pode ser negativo')
    if any(w < 1 for w in args.workers):
        raise ValueError('--workers deve ter valores >= 1')


def main(argv=None):
    args = construir_parser().parse_args(argv)
    try:
        _validar(args)
        resumo = executar_experimento(args)
    except (OSError, ValueError, RuntimeError) as erro:
        print(f'Erro: {erro}', file=sys.stderr)
        sys.exit(1)
    _imprimir_tabela(resumo['cenarios'])


if __name__ == '__main__':
    main()
