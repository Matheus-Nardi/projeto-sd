"""Agregação inteira por UF da prova e tipo de escola, independente de MPI."""

import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from itertools import islice
import re

from scripts.obter_dados import COLUNAS_SELECIONADAS, UFS


def ler_blocos(caminho, tamanho=10000):
    """Produz (ID contíguo, linhas), mantendo no máximo um bloco em memória."""
    if tamanho <= 0:
        raise ValueError('O tamanho do bloco deve ser positivo')
    with open(caminho, encoding='utf-8-sig', newline='') as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=';', strict=True)
        _validar_cabecalho(leitor.fieldnames or [])
        bloco_id = 0
        while linhas := list(islice(leitor, tamanho)):
            yield bloco_id, linhas
            bloco_id += 1


def _validar_cabecalho(campos):
    if len(campos) != len(set(campos)) or not set(COLUNAS_SELECIONADAS) <= set(campos):
        raise ValueError('Cabeçalho ausente, duplicado ou incompatível com o esquema ENEM')


def _linhas_cruas(arquivo):
    for linha in arquivo:
        if '"' in linha:
            # Um campo entre aspas pode conter quebra de linha; cortar o texto
            # em linhas sem interpretar o CSV deixaria de ser seguro.
            raise ValueError('Campos entre aspas não são aceitos na leitura distribuída')
        if linha.strip('\r\n'):
            yield linha


def ler_blocos_texto(caminho, tamanho=10000):
    """Produz (ID contíguo, campos, linhas de texto) sem interpretar os registros.

    Usada pelo mestre MPI: o custo de interpretar o CSV fica com os workers.
    Linhas vazias são descartadas, como faz o leitor da referência sequencial.
    """
    if tamanho <= 0:
        raise ValueError('O tamanho do bloco deve ser positivo')
    with open(caminho, encoding='utf-8-sig', newline='') as arquivo:
        campos = next(csv.reader([arquivo.readline()], delimiter=';', strict=True), [])
        _validar_cabecalho(campos)
        linhas = _linhas_cruas(arquivo)
        bloco_id = 0
        while bloco := list(islice(linhas, tamanho)):
            yield bloco_id, campos, bloco
            bloco_id += 1


def interpretar(campos, linhas):
    """Converte linhas de texto de um bloco nos registros esperados por agregar."""
    return list(csv.DictReader(linhas, fieldnames=campos, delimiter=';', strict=True))


def _nota(valor):
    if valor == '':
        return None
    if not re.fullmatch(r'[0-9]+(?:\.[0-9])?', valor):
        raise ValueError(f'Nota inválida (esperado até uma casa decimal): {valor!r}')
    nota = Decimal(valor)
    if not 0 <= nota <= 1000:
        raise ValueError(f'Nota fora do intervalo [0, 1000]: {valor!r}')
    return int(nota * 10)


def agregar(linhas):
    """Retorna chave -> [soma MT, contagem MT, soma redação, contagem redação]."""
    grupos = {}
    for indice, linha in enumerate(linhas, 1):
        try:
            if None in linha or any(linha.get(c) is None for c in COLUNAS_SELECIONADAS):
                raise ValueError('Quantidade de campos incompatível')
            uf, escola = linha['SG_UF_PROVA'], linha['TP_ESCOLA']
            if uf not in UFS or escola not in ('1', '2', '3'):
                raise ValueError('UF ou tipo de escola desconhecido')
            if any(linha[c] not in ('0', '1', '2')
                   for c in ('TP_PRESENCA_MT', 'TP_PRESENCA_LC')):
                raise ValueError('Código de presença desconhecido')
            mt, red = _nota(linha['NU_NOTA_MT']), _nota(linha['NU_NOTA_REDACAO'])
            valores = grupos.setdefault((uf, escola), [0, 0, 0, 0])
            for inicio, presenca, nota in ((0, linha['TP_PRESENCA_MT'], mt),
                                          (2, linha['TP_PRESENCA_LC'], red)):
                if presenca == '1' and nota is not None:
                    valores[inicio] += nota
                    valores[inicio + 1] += 1
        except (ValueError, InvalidOperation) as erro:
            raise ValueError(f'Linha {indice} do bloco: {erro}') from erro
    return grupos


def combinar(destino, parcial):
    """Combina somas e contagens; cada bloco deve ser fornecido uma única vez."""
    for chave, valores in parcial.items():
        atual = destino.setdefault(chave, [0, 0, 0, 0])
        for i, valor in enumerate(valores):
            atual[i] += valor


def _resultado(soma, contagem):
    media = None
    if contagem:
        with localcontext() as contexto:
            contexto.prec = max(28, len(str(soma)) + len(str(contagem)) + 6)
            media = format((Decimal(soma) / (10 * contagem)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
    return {'soma_decimos': soma, 'contagem': contagem, 'media': media}


def finalizar(grupos):
    return [
        {'uf': uf, 'tp_escola': escola,
         'mt': _resultado(valores[0], valores[1]),
         'redacao': _resultado(valores[2], valores[3])}
        for (uf, escola), valores in sorted(grupos.items())
    ]
