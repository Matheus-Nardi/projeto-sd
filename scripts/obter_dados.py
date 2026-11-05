#!/usr/bin/env python3
"""
scripts/obter_dados.py
Gerenciamento, download oficial, geração sintética e verificação de dados para o
projeto de Sistemas Distribuídos (UNITINS 2026/2).

Permite:
- Baixar os Microdados REAIS do ENEM direto do portal oficial do INEP.
- Filtrar o CSV real do ENEM mantendo apenas as colunas do projeto.
- Gerar dados sintéticos reproduzíveis (com seed fixa) no esquema do ENEM.
- Calcular checksum SHA-256 de qualquer arquivo de dados.
- Inspecionar a estrutura, número de linhas e colunas de arquivos de dados.
"""

import argparse
import csv
import hashlib
import io
import os
import random
import ssl
import sys
import time
import urllib.request
import zipfile
from typing import Dict, List, Optional

# Constantes e esquema de dados
UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
]

UF_PESOS = [
    0.01, 0.02, 0.01, 0.03, 0.08, 0.06, 0.03, 0.02, 0.04, 0.05,
    0.02, 0.01, 0.10, 0.05, 0.03, 0.05, 0.05, 0.03, 0.08, 0.02,
    0.05, 0.01, 0.01, 0.03, 0.18, 0.01, 0.01
]

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

URL_ENEM_BASE = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"


def _criar_ssl_context():
    """Cria contexto SSL compatível com a configuração de cifras do servidor Apache do INEP."""
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except Exception:
        pass
    return ctx


def calcular_sha256(caminho_arquivo: str, bloco: int = 65536) -> str:
    """Calcula o hash SHA-256 de um arquivo."""
    sha = hashlib.sha256()
    with open(caminho_arquivo, "rb") as f:
        while chunk := f.read(bloco):
            sha.update(chunk)
    return sha.hexdigest()


def baixar_arquivo_com_progresso(url: str, caminho_destino: str) -> None:
    """Baixa um arquivo via HTTP exibindo taxa e barra de progresso no terminal."""
    os.makedirs(os.path.dirname(os.path.abspath(caminho_destino)), exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "curl/8.4.0 (UNITINS Sistemas Distribuidos)"}
    )
    ctx = _criar_ssl_context()

    print(f">> Conectando a {url}...")
    with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
        total_size = response.headers.get("Content-Length")
        total_bytes = int(total_size) if total_size else 0
        tamanho_mb_total = total_bytes / (1024 * 1024) if total_bytes else 0

        print(f">> Baixando ({tamanho_mb_total:.1f} MB)...")
        bytes_baixados = 0
        bloco = 1024 * 512  # 512 KB
        t0 = time.time()

        with open(caminho_destino, "wb") as f_out:
            while True:
                chunk = response.read(bloco)
                if not chunk:
                    break
                f_out.write(chunk)
                bytes_baixados += len(chunk)
                elapsed = time.time() - t0
                speed = (bytes_baixados / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                mb_baixados = bytes_baixados / (1024 * 1024)

                if total_bytes > 0:
                    pct = (bytes_baixados / total_bytes) * 100
                    sys.stdout.write(
                        f"\r   [{pct:5.1f}%] {mb_baixados:6.1f} / {tamanho_mb_total:6.1f} MB "
                        f"({speed:4.2f} MB/s)"
                    )
                else:
                    sys.stdout.write(f"\r   Baixados: {mb_baixados:6.1f} MB ({speed:4.2f} MB/s)")
                sys.stdout.flush()

        print("\n>> Download concluído!")


def extrair_e_filtrar_enem(
    caminho_zip: str,
    caminho_saida_csv: str,
    ano: int = 2023,
    limite_linhas: Optional[int] = None
) -> Dict[str, any]:
    """
    Extrai o CSV real do ENEM de dentro do arquivo ZIP e filtra apenas as 7 colunas
    necessárias para o projeto de Sistemas Distribuídos.
    """
    nome_csv_esperado = f"DADOS/MICRODADOS_ENEM_{ano}.csv"
    print(f">> Lendo arquivo compactado: {caminho_zip}")

    with zipfile.ZipFile(caminho_zip, "r") as z:
        lista_arquivos = z.namelist()
        arquivo_alvo = None
        for nome in lista_arquivos:
            if nome.endswith(f"MICRODADOS_ENEM_{ano}.csv") or "MICRODADOS_ENEM" in nome:
                arquivo_alvo = nome
                break

        if not arquivo_alvo:
            raise FileNotFoundError(
                f"Não foi possível localizar o arquivo CSV de microdados dentro do ZIP. Encontrados: {lista_arquivos[:5]}"
            )

        print(f">> Extraindo e filtrando colunas de '{arquivo_alvo}'...")
        os.makedirs(os.path.dirname(os.path.abspath(caminho_saida_csv)), exist_ok=True)

        total_processadas = 0
        total_salvas = 0

        with z.open(arquivo_alvo) as f_in_bytes, \
             open(caminho_saida_csv, "w", newline="", encoding="utf-8") as f_out:

            # Decodificar stream em texto (ISO-8859-1 com fallback)
            stream_texto = io.TextIOWrapper(f_in_bytes, encoding="iso-8859-1", errors="replace")
            reader = csv.reader(stream_texto, delimiter=";")
            writer = csv.writer(f_out, delimiter=";")

            cabecalho_original = next(reader)
            # Mapear índices das colunas de interesse
            indices = {}
            for col in COLUNAS_SELECIONADAS:
                if col in cabecalho_original:
                    indices[col] = cabecalho_original.index(col)
                else:
                    raise KeyError(f"Coluna esperada '{col}' não encontrada no cabeçalho do ENEM!")

            # Escreve o cabeçalho padronizado
            writer.writerow(COLUNAS_SELECIONADAS)

            for linha in reader:
                total_processadas += 1
                if not linha:
                    continue

                # Extrai apenas as colunas selecionadas
                linha_filtrada = []
                for col in COLUNAS_SELECIONADAS:
                    idx = indices[col]
                    val = linha[idx].strip() if idx < len(linha) else ""
                    # Padronizar nota com ponto decimal se vier com vírgula
                    if col in ("NU_NOTA_MT", "NU_NOTA_REDACAO") and val:
                        val = val.replace(",", ".")
                    linha_filtrada.append(val)

                writer.writerow(linha_filtrada)
                total_salvas += 1

                if limite_linhas and total_salvas >= limite_linhas:
                    print(f"\n>> Limite de amostragem atingido ({limite_linhas:,} linhas salvas).")
                    break

                if total_processadas % 250000 == 0:
                    sys.stdout.write(f"\r   Processadas {total_processadas:,} linhas...")
                    sys.stdout.flush()

    tamanho_mb = round(os.path.getsize(caminho_saida_csv) / (1024 * 1024), 2)
    checksum = calcular_sha256(caminho_saida_csv)

    print(f"\n>> OK! Arquivo real filtrado gerado em: {caminho_saida_csv}")
    print(f"   Tamanho: {tamanho_mb} MB")
    print(f"   Total de participantes: {total_salvas:,}")
    print(f"   SHA-256: {checksum}")

    return {
        "arquivo": caminho_saida_csv,
        "linhas": total_salvas,
        "tamanho_mb": tamanho_mb,
        "sha256": checksum
    }


def gerar_dados_sinteticos(
    caminho_saida: str,
    tamanho_mb: float,
    seed: int = 42
) -> Dict[str, any]:
    """Gera um arquivo CSV sintético compatível com o esquema dos Microdados do ENEM."""
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

        while f.tell() < bytes_alvo:
            linhas_bloco = []
            for _ in range(5000):
                total_linhas += 1
                inscricao = inscricao_base + total_linhas
                uf = random.choices(UFS, weights=UF_PESOS, k=1)[0]
                tp_escola = random.choices(TP_ESCOLA_OPCOES, weights=TP_ESCOLA_PESOS, k=1)[0]
                presenca = random.choices([1, 0, 2], weights=[0.75, 0.24, 0.01], k=1)[0]

                if presenca == 1:
                    offset = 40.0 if tp_escola == 3 else (0.0 if tp_escola == 2 else 10.0)
                    nota_mt = round(min(1000.0, max(0.0, random.gauss(520.0 + offset, 110.0))), 1)
                    nota_red = round(min(1000.0, max(0.0, random.gauss(620.0 + offset, 140.0))), 1)
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
        description="Utilitário de dados oficiais e sintéticos para o Projeto de Sistemas Distribuídos — UNITINS"
    )
    parser.add_argument(
        "--baixar-enem",
        action="store_true",
        help="Baixa o pacote ZIP oficial dos microdados do ENEM do portal do INEP"
    )
    parser.add_argument(
        "--ano",
        type=int,
        default=2023,
        help="Ano do ENEM a baixar (padrão: 2023)"
    )
    parser.add_argument(
        "--extrair-real",
        action="store_true",
        help="Extrai e filtra o CSV oficial do ENEM a partir do ZIP baixado"
    )
    parser.add_argument(
        "--amostra-linhas",
        type=int,
        default=None,
        help="Quantidade de linhas a extrair do CSV oficial (ex: 200000 para amostra rápida)"
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
        help="Tamanho do arquivo sintético em MB a gerar (padrão: 50 MB)"
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
        default=None,
        help="Caminho personalizado de saída do CSV"
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

    if args.baixar_enem:
        url = URL_ENEM_BASE.format(ano=args.ano)
        zip_destino = f"dados/microdados_enem_{args.ano}.zip"
        baixar_arquivo_com_progresso(url, zip_destino)

        # Se solicitado ou por padrão, extrai o CSV filtrado
        csv_saida = args.saida or (
            f"dados/enem_{args.ano}_amostra_real.csv" if args.amostra_linhas
            else f"dados/enem_{args.ano}_real.csv"
        )
        extrair_e_filtrar_enem(zip_destino, csv_saida, ano=args.ano, limite_linhas=args.amostra_linhas)
        return

    if args.extrair_real:
        zip_origem = f"dados/microdados_enem_{args.ano}.zip"
        csv_saida = args.saida or (
            f"dados/enem_{args.ano}_amostra_real.csv" if args.amostra_linhas
            else f"dados/enem_{args.ano}_real.csv"
        )
        extrair_e_filtrar_enem(zip_origem, csv_saida, ano=args.ano, limite_linhas=args.amostra_linhas)
        return

    if args.gerar_sintetico:
        caminho_saida = args.saida or "dados/enem_sintetico.csv"
        print(f">> Gerando {args.mb} MB de dados sintéticos com seed={args.seed}...")
        res = gerar_dados_sinteticos(caminho_saida, args.mb, args.seed)
        print(f"OK! Arquivo gerado em: {res['arquivo']}")
        print(f"Tamanho real: {res['mb']} MB ({res['bytes']:,} bytes)")
        print(f"Linhas geradas: {res['linhas']:,}")
        print(f"SHA-256: {res['sha256']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
