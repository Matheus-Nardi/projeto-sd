#!/usr/bin/env python3
"""
scripts/obter_dados.py
Gerenciamento, geração sintética e verificação de integridade dos dados para o
projeto de Sistemas Distribuídos (UNITINS 2026/2).

Permite:
- Gerar dados sintéticos reproduzíveis (com seed fixa) no esquema dos Microdados do ENEM.
- Calcular checksum SHA-256 de arquivos de dados.
- Inspecionar a estrutura, número de linhas e colunas de arquivos de dados.
"""

import argparse
import csv
import hashlib
import os
import random
import sys
from typing import Dict, Tuple

# Constantes e esquema de dados
UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
]

# Distribuição aproximada de participantes por porte de estado (pesos)
UF_PESOS = [
    0.01, 0.02, 0.01, 0.03, 0.08, 0.06, 0.03, 0.02, 0.04, 0.05,
    0.02, 0.01, 0.10, 0.05, 0.03, 0.05, 0.05, 0.03, 0.08, 0.02,
    0.05, 0.01, 0.01, 0.03, 0.18, 0.01, 0.01
]

# Tipos de escola no ENEM: 1 = Não informado / Outro, 2 = Pública, 3 = Privada
TP_ESCOLA_OPCOES = [1, 2, 3]
TP_ESCOLA_PESOS = [0.45, 0.40, 0.15]

COLUNAS_SELECIONADAS = [
    "NU_INSCRICAO",
    "SG_UF_PROVA",
    "TP_ESCOLA",
    "TP_PRESENCA_MT",
    "TP_PRESENCA_LC",
    "NU_NOTA_MT",
    "NU_NOTA_REDACAO"
]


def calcular_sha256(caminho_arquivo: str, bloco: int = 65536) -> str:
    """Calcula o hash SHA-256 de um arquivo."""
    sha = hashlib.sha256()
    with open(caminho_arquivo, "rb") as f:
        while chunk := f.read(bloco):
            sha.update(chunk)
    return sha.hexdigest()


def gerar_dados_sinteticos(
    caminho_saida: str,
    tamanho_mb: float,
    seed: int = 42
) -> Dict[str, any]:
    """
    Gera um arquivo CSV sintético compatível com o esquema dos Microdados do ENEM.
    Garante reprodutibilidade total através de seed fixa.
    """
    random.seed(seed)
    bytes_alvo = int(tamanho_mb * 1024 * 1024)
    
    diretorio = os.path.dirname(caminho_saida)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)

    total_linhas = 0
    inscricao_base = 230000000001

    with open(caminho_saida, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(COLUNAS_SELECIONADAS)

        # Escreve em blocos para controle de tamanho e boa performance
        while f.tell() < bytes_alvo:
            linhas_bloco = []
            for _ in range(5000):
                total_linhas += 1
                inscricao = inscricao_base + total_linhas
                uf = random.choices(UFS, weights=UF_PESOS, k=1)[0]
                tp_escola = random.choices(TP_ESCOLA_OPCOES, weights=TP_ESCOLA_PESOS, k=1)[0]
                
                # Presença: ~75% de presentes, ~24% de faltosos, ~1% eliminados
                presenca = random.choices([1, 0, 2], weights=[0.75, 0.24, 0.01], k=1)[0]
                
                if presenca == 1:
                    # Média de notas variando ligeiramente por tipo de escola
                    offset = 40.0 if tp_escola == 3 else (0.0 if tp_escola == 2 else 10.0)
                    nota_mt = round(min(1000.0, max(0.0, random.gauss(520.0 + offset, 110.0))), 1)
                    nota_red = round(min(1000.0, max(0.0, random.gauss(620.0 + offset, 140.0))), 1)
                    # Arredondar redação para múltiplos de 20 (regra do ENEM)
                    nota_red = round(nota_red / 20.0) * 20.0
                    nota_mt_str = f"{nota_mt:.1f}"
                    nota_red_str = f"{nota_red:.1f}"
                else:
                    nota_mt_str = ""
                    nota_red_str = ""

                linhas_bloco.append([
                    inscricao,
                    uf,
                    tp_escola,
                    presenca,
                    presenca,
                    nota_mt_str,
                    nota_red_str
                ])

            writer.writerows(linhas_bloco)
            if f.tell() >= bytes_alvo:
                break

    tamanho_final_bytes = os.path.getsize(caminho_saida)
    checksum = calcular_sha256(caminho_saida)

    return {
        "arquivo": caminho_saida,
        "linhas": total_linhas,
        "bytes": tamanho_final_bytes,
        "mb": round(tamanho_final_bytes / (1024 * 1024), 2),
        "seed": seed,
        "sha256": checksum
    }


def inspecionar_arquivo(caminho_arquivo: str, limite_linhas: int = 5) -> Dict[str, any]:
    """Inspeciona um arquivo CSV e extrai contagens e amostras."""
    if not os.path.exists(caminho_arquivo):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")

    tamanho_bytes = os.path.getsize(caminho_arquivo)
    total_linhas = 0
    presentes = 0
    faltosos = 0
    amostras = []

    with open(caminho_arquivo, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        colunas = reader.fieldnames or []
        for row in reader:
            total_linhas += 1
            if total_linhas <= limite_linhas:
                amostras.append(row)
            if row.get("TP_PRESENCA_MT") == "1":
                presentes += 1
            else:
                faltosos += 1

    checksum = calcular_sha256(caminho_arquivo)

    return {
        "arquivo": caminho_arquivo,
        "tamanho_mb": round(tamanho_bytes / (1024 * 1024), 2),
        "colunas": colunas,
        "total_linhas": total_linhas,
        "presentes": presentes,
        "faltosos": faltosos,
        "sha256": checksum,
        "amostras": amostras
    }


def main():
    parser = argparse.ArgumentParser(
        description="Utilitário de dados para o Projeto de Sistemas Distribuídos — UNITINS"
    )
    parser.add_argument(
        "--gerar-sintetico",
        action="store_true",
        help="Gera dataset sintético baseado no esquema do ENEM"
    )
    parser.add_argument(
        "--mb",
        type=float,
        default=50.0,
        help="Tamanho do arquivo em MB a gerar (padrão: 50 MB)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed para reprodução determinística (padrão: 42)"
    )
    parser.add_argument(
        "--saida",
        type=str,
        default="dados/enem_sintetico.csv",
        help="Caminho de saída do CSV"
    )
    parser.add_argument(
        "--checksum",
        type=str,
        help="Calcula o SHA-256 do arquivo informado"
    )
    parser.add_argument(
        "--inspecionar",
        type=str,
        help="Inspeciona e sumariza o arquivo CSV informado"
    )

    args = parser.parse_args()

    if args.checksum:
        sha = calcular_sha256(args.checksum)
        print(f"Arquivo: {args.checksum}")
        print(f"SHA-256: {sha}")
        return

    if args.inspecionar:
        info = inspecionar_arquivo(args.inspecionar)
        print(f"=== Inspeção de Dados: {info['arquivo']} ===")
        print(f"Tamanho: {info['tamanho_mb']} MB")
        print(f"Total de Registros: {info['total_linhas']:,}")
        print(f"Presentes em MT: {info['presentes']:,}")
        print(f"Faltosos/Outros: {info['faltosos']:,}")
        print(f"Colunas: {', '.join(info['colunas'])}")
        print(f"SHA-256: {info['sha256']}")
        print("\nPrimeiras linhas da amostra:")
        for i, row in enumerate(info['amostras'], 1):
            print(f"  {i}: {row}")
        return

    if args.gerar_sintetico:
        print(f">> Gerando {args.mb} MB de dados sintéticos com seed={args.seed}...")
        res = gerar_dados_sinteticos(args.saida, args.mb, args.seed)
        print(f"OK! Arquivo gerado em: {res['arquivo']}")
        print(f"Tamanho real: {res['mb']} MB ({res['bytes']:,} bytes)")
        print(f"Linhas geradas: {res['linhas']:,}")
        print(f"SHA-256: {res['sha256']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
