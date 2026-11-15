"""Referência: python -m src.sequencial entrada.csv [--saida resultado.json]."""

import argparse
import csv
import json
from pathlib import Path
import sys
import time

from scripts.obter_dados import calcular_sha256
from src.agregacao import agregar, combinar, finalizar, ler_blocos


def executar(caminho, bloco_linhas=10000):
    grupos = {}
    quantidade = 0
    for bloco_id, linhas in ler_blocos(caminho, bloco_linhas):
        try:
            combinar(grupos, agregar(linhas))
        except ValueError as erro:
            raise ValueError(f'Bloco {bloco_id}: {erro}') from erro
        quantidade += len(linhas)
    return montar_resultado(caminho, quantidade, grupos)


def montar_resultado(caminho, quantidade, grupos):
    """JSON de corretude, idêntico para as versões sequencial e distribuídas."""
    return {
        'contrato': 'enem-uf-escola-v1',
        'entrada': {'sha256': calcular_sha256(caminho), 'linhas': quantidade,
                    'bytes': Path(caminho).stat().st_size},
        'grupos': finalizar(grupos),
    }


def main():
    parser = argparse.ArgumentParser(description='Médias ENEM por UF da prova e tipo de escola')
    parser.add_argument('entrada', type=Path)
    parser.add_argument('--bloco-linhas', type=int, default=10000)
    parser.add_argument('--saida', type=Path)
    args = parser.parse_args()
    if args.saida and args.saida.resolve() == args.entrada.resolve():
        parser.error('A saída deve ser diferente da entrada')
    inicio = time.perf_counter()
    try:
        resultado = executar(args.entrada, args.bloco_linhas)
        texto = json.dumps(resultado, ensure_ascii=False, indent=2) + '\n'
        if args.saida:
            args.saida.write_text(texto, encoding='utf-8')
        else:
            sys.stdout.write(texto)
    except (OSError, ValueError, csv.Error) as erro:
        parser.exit(1, f'Erro: {erro}\n')
    print(json.dumps({'modo': 'sequencial', 'bloco_linhas': args.bloco_linhas,
                      'tempo_total_s': time.perf_counter() - inicio}), file=sys.stderr)


if __name__ == '__main__':
    main()
