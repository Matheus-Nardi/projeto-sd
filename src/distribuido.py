"""Versão MPI: mpirun ... python -m src.distribuido entrada.csv --politica dinamica.

Rank 0 é o mestre dedicado (lê, distribui e agrega); os demais são workers.
O protocolo está descrito em docs/protocolo-mpi.md.
"""

import argparse
import csv
import io
import json
import os
from pathlib import Path
import pickle
import sys
import time

from src.agregacao import agregar, combinar, interpretar, ler_blocos_texto
from src.sequencial import montar_resultado


TAG_TASK, TAG_RESULT, TAG_STOP = 1, 2, 3
POLITICAS = ('estatica', 'dinamica')


class ErroProtocolo(RuntimeError):
    """Mensagem inesperada: o estado da execução deixou de ser confiável."""


def destino_estatico(bloco_id, workers):
    """Divisão fixa em rodízio: o destino não depende de quem está livre."""
    return 1 + bloco_id % workers


def carregar_checkpoint(caminho, identidade):
    """Lê os blocos já concluídos: bloco_id -> (linhas, parcial).

    A primeira linha identifica entrada e tamanho de bloco; as demais trazem um
    bloco cada. A última linha sem quebra (escrita interrompida) é descartada.
    """
    feitos = {}
    if not Path(caminho).exists():
        return feitos
    completas = Path(caminho).read_text(encoding='utf-8').split('\n')[:-1]
    if completas and json.loads(completas[0]) != identidade:
        raise ValueError('Checkpoint de outra entrada ou de outro tamanho de bloco')
    for texto in completas[1:]:
        registro = json.loads(texto)
        if registro['bloco'] in feitos:
            raise ValueError(f"Checkpoint com bloco repetido: {registro['bloco']}")
        feitos[registro['bloco']] = (registro['linhas'], {
            (uf, escola): valores for uf, escola, *valores in registro['parcial']})
    return feitos


def _linha_checkpoint(bloco_id, linhas, parcial):
    return json.dumps({'bloco': bloco_id, 'linhas': linhas,
                       'parcial': [[*chave, *valores] for chave, valores in parcial.items()]}) + '\n'


def mestre(comm, criar_status, caminho, bloco_linhas=10000, politica='dinamica',
           checkpoint=None):
    """Distribui os blocos e retorna (grupos, métricas).

    Erros de dados encerram os workers normalmente e viram ValueError.
    ErroProtocolo não tem encerramento limpo: quem chama deve abortar.
    """
    workers = comm.Get_size() - 1
    if workers < 1:
        raise ValueError('Use ao menos 2 processos: mestre dedicado e 1 worker')
    if politica not in POLITICAS:
        raise ValueError(f'Política desconhecida: {politica!r}')
    ranks = range(1, workers + 1)
    pendentes = {}  # rank -> (bloco_id, linhas enviadas); no máximo uma tarefa por worker
    grupos = {}
    metricas = {'blocos': 0, 'blocos_retomados': 0, 'linhas': 0, 'bytes_enviados': 0,
                'tarefas_por_worker': {r: 0 for r in ranks},
                'tempo_ocupado_por_worker_s': {r: 0.0 for r in ranks}}
    erro = None
    feitos = {}
    registro = None  # arquivo de checkpoint aberto para acréscimo
    status = criar_status()

    def receber():
        nonlocal erro
        resposta = comm.recv(tag=TAG_RESULT, status=status)
        rank = status.Get_source()
        esperado = pendentes.pop(rank, None)
        if (esperado is None or not isinstance(resposta, dict)
                or resposta.get('rank') != rank or resposta.get('bloco_id') != esperado[0]):
            raise ErroProtocolo(f'Resultado inesperado do rank {rank}: esperado {esperado}')
        if 'erro' in resposta:
            erro = erro or f"Bloco {esperado[0]}: {resposta['erro']}"
            return
        if resposta['linhas'] != esperado[1]:
            raise ErroProtocolo(f'Bloco {esperado[0]}: {resposta["linhas"]} linhas '
                                f'processadas, {esperado[1]} enviadas')
        if registro:
            # Grava antes de contar o bloco como feito: após uma queda, o que
            # está no disco é exatamente o que não precisa ser refeito.
            registro.write(_linha_checkpoint(esperado[0], esperado[1], resposta['parcial']))
            registro.flush()
            os.fsync(registro.fileno())
        combinar(grupos, resposta['parcial'])
        metricas['linhas'] += esperado[1]
        metricas['tempo_ocupado_por_worker_s'][rank] += resposta['tempo_s']

    try:
        if checkpoint:
            identidade = {'contrato': 'checkpoint-v1', 'bloco_linhas': bloco_linhas,
                          'bytes': Path(caminho).stat().st_size}
            feitos = carregar_checkpoint(checkpoint, identidade)
            # Regrava só o que é válido (sem linha cortada) e passa a acrescentar.
            temporario = Path(str(checkpoint) + '.tmp')
            with open(temporario, 'w', encoding='utf-8') as limpo:
                limpo.write(json.dumps(identidade) + '\n')
                for bloco_id, (quantidade, parcial) in sorted(feitos.items()):
                    limpo.write(_linha_checkpoint(bloco_id, quantidade, parcial))
                    combinar(grupos, parcial)
                    metricas['linhas'] += quantidade
            os.replace(temporario, checkpoint)
            registro = open(checkpoint, 'a', encoding='utf-8')
        for bloco_id, campos, linhas in ler_blocos_texto(caminho, bloco_linhas):
            if bloco_id in feitos:
                if feitos[bloco_id][0] != len(linhas):
                    raise ValueError(f'Checkpoint incompatível com a entrada no bloco {bloco_id}')
                metricas['blocos_retomados'] += 1
                continue
            if politica == 'estatica':
                destino = destino_estatico(bloco_id, workers)
                while destino in pendentes and erro is None:
                    receber()
            else:
                while len(pendentes) == workers and erro is None:
                    receber()
                destino = next((r for r in ranks if r not in pendentes), None)
            if erro:
                break
            # Serialização explícita para contabilizar o que trafega na rede.
            dados = pickle.dumps((bloco_id, campos, ''.join(linhas)), pickle.HIGHEST_PROTOCOL)
            comm.send(dados, dest=destino, tag=TAG_TASK)
            pendentes[destino] = (bloco_id, len(linhas))
            metricas['blocos'] += 1
            metricas['bytes_enviados'] += len(dados)
            metricas['tarefas_por_worker'][destino] += 1
        if erro is None and metricas['blocos_retomados'] != len(feitos):
            raise ValueError('Checkpoint com blocos que não existem na entrada')
    except (OSError, ValueError, csv.Error) as falha:
        erro = erro or str(falha)
    try:
        while pendentes:
            receber()
    finally:
        if registro:
            registro.close()
    for rank in ranks:
        comm.send(None, dest=rank, tag=TAG_STOP)
    comm.bcast({'ok': erro is None, 'erro': erro}, root=0)
    if erro:
        raise ValueError(erro)
    return grupos, metricas


def worker(comm, criar_status, atraso_s=0.0):
    """Processa uma tarefa por vez até receber STOP; retorna o estado final."""
    rank = comm.Get_rank()
    status = criar_status()
    while True:
        dados = comm.recv(source=0, status=status)
        if status.Get_tag() == TAG_STOP:
            break
        inicio = time.perf_counter()
        bloco_id, campos, texto = pickle.loads(dados)
        resposta = {'bloco_id': bloco_id, 'rank': rank}
        try:
            registros = interpretar(campos, io.StringIO(texto, newline=''))
            resposta.update(parcial=agregar(registros), linhas=len(registros))
        except (ValueError, csv.Error) as falha:
            resposta['erro'] = str(falha)
        if atraso_s:
            time.sleep(atraso_s)  # heterogeneidade simulada, por tarefa
        resposta['tempo_s'] = time.perf_counter() - inicio
        comm.send(resposta, dest=0, tag=TAG_RESULT)
    return comm.bcast(None, root=0)


def _atrasos(valores):
    atrasos = {}
    for valor in valores:
        rank, _, segundos = valor.partition('=')
        try:
            atrasos[int(rank)] = float(segundos)
        except ValueError:
            raise argparse.ArgumentTypeError(f'Use RANK=SEGUNDOS: {valor!r}') from None
        if int(rank) < 1 or not 0 <= atrasos[int(rank)] < float('inf'):
            raise argparse.ArgumentTypeError(f'Rank de worker ou atraso inválido: {valor!r}')
    return atrasos


def main():
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    inicio = MPI.Wtime()
    parser = argparse.ArgumentParser(description='Médias ENEM com mestre/workers em MPI')
    parser.add_argument('entrada', type=Path)
    parser.add_argument('--politica', choices=POLITICAS, default='dinamica')
    parser.add_argument('--bloco-linhas', type=int, default=10000)
    parser.add_argument('--saida', type=Path)
    parser.add_argument('--checkpoint', type=Path,
                        help='registra blocos concluídos; se o arquivo existir, retoma dele')
    parser.add_argument('--atraso', action='append', default=[], metavar='RANK=SEGUNDOS',
                        help='atraso artificial por tarefa em um worker (pode repetir)')
    try:
        # Todos os ranks recebem os mesmos argumentos; só o mestre relata erros de uso.
        if rank != 0:
            parser.error = lambda mensagem: sys.exit(2)
        args = parser.parse_args()
        try:
            atrasos = _atrasos(args.atraso)
        except argparse.ArgumentTypeError as falha:
            parser.error(str(falha))
        if args.saida and args.saida.resolve() == args.entrada.resolve():
            parser.error('A saída deve ser diferente da entrada')
        if rank != 0:
            worker(comm, MPI.Status, atrasos.get(rank, 0.0))
            return
        try:
            grupos, metricas = mestre(comm, MPI.Status, args.entrada,
                                      args.bloco_linhas, args.politica, args.checkpoint)
            resultado = montar_resultado(args.entrada, metricas.pop('linhas'), grupos)
            texto = json.dumps(resultado, ensure_ascii=False, indent=2) + '\n'
            if args.saida:
                args.saida.write_text(texto, encoding='utf-8')
            else:
                sys.stdout.write(texto)
                sys.stdout.flush()
        except (OSError, ValueError) as falha:
            # Os workers já foram encerrados pelo mestre; basta sinalizar a falha.
            print(f'Erro: {falha}', file=sys.stderr, flush=True)
            sys.exit(1)
        print(json.dumps({'modo': 'mpi', 'politica': args.politica,
                          'workers': comm.Get_size() - 1, 'bloco_linhas': args.bloco_linhas,
                          'atrasos_s': atrasos, 'tempo_total_s': MPI.Wtime() - inicio,
                          **metricas}), file=sys.stderr, flush=True)
    except SystemExit:
        raise
    except BaseException as falha:  # protocolo violado ou defeito: não há como drenar
        print(f'Rank {rank}: {type(falha).__name__}: {falha}', file=sys.stderr, flush=True)
        comm.Abort(1)


if __name__ == '__main__':
    main()
