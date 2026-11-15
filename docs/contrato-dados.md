# Contrato de dados e resultado v1

Referência: dicionário `Dicionário_Microdados_Enem_2023.xlsx` contido no
ZIP oficial já disponível em `dados/microdados_enem_2023.zip`.
Origem: [Microdados do ENEM, INEP](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem).
O dicionário foi consultado diretamente em 15/11/2026, sem dependências externas.

A pergunta é: quais são as médias de Matemática e Redação por **UF de aplicação
da prova** e **tipo de escola do ensino médio declarado pelo participante**?
`TP_ESCOLA` não é a dependência administrativa detalhada da escola.
Os códigos são `1` (não respondeu), `2` (pública) e `3` (privada).
Não respondeu forma seu próprio grupo.

## Entrada e elegibilidade

CSV UTF-8, delimitador `;`, cabeçalho com as sete colunas de
`scripts/obter_dados.py`. Colunas adicionais são aceitas; cabeçalhos duplicados
ou incompletos são rejeitados. Não há remoção de duplicatas de participantes:
cada registro contribui uma vez. A entrada deve permanecer imutável durante a execução.

- Matemática: `TP_PRESENCA_MT = 1` e `NU_NOTA_MT` preenchida.
- Redação: `TP_PRESENCA_LC = 1` e `NU_NOTA_REDACAO` preenchida.
- Presença `0` (ausente) ou `2` (eliminado) exclui apenas a prova correspondente.
- Nota zero é incluída para presentes. A análise inclui redações com nota zero,
  inclusive anuladas ou em branco; não pretende selecionar apenas redações
  “sem problemas”. Por isso, `TP_STATUS_REDACAO` não é necessário para esta pergunta.
- Notas vazias excluem apenas aquela observação; contagens são independentes.
- Código desconhecido, UF inválida, registro truncado, campos excedentes ou nota
  malformada interrompem a execução com erro, sem resultado parcial na saída.
- Arquivo sem cabeçalho é inválido; cabeçalho sem registros produz grupos vazios (`[]`).
  Grupos observados sem notas elegíveis têm contagens zero e médias `null`.
  Combinações UF/escola não observadas não são materializadas.

O dicionário identifica notas como numéricas, mas não explicita casas decimais.
O contrato de processamento aceita números de 0 a 1000 com até uma casa decimal,
com ponto, compatíveis com a extração e o gerador existentes. Precisão maior é
rejeitada, nunca arredondada silenciosamente. As somas usam décimos inteiros.
A execução completa sobre o CSV real verifica também essa compatibilidade.

## Resultado e blocos

JSON com `contrato = enem-uf-escola-v1`, metadados de entrada (`sha256`, bytes,
linhas) e `grupos`, ordenados por `(uf, tp_escola)`. Cada prova contém
`soma_decimos`, `contagem` e `media`. Média é string decimal com duas casas,
arredondamento `ROUND_HALF_UP`, calculada apenas após combinar as somas.

O leitor produz `(bloco_id, linhas)` em fluxo, IDs contíguos a partir de zero.
O núcleo retorna um dicionário `(uf, escola) -> [soma_mt, n_mt, soma_redacao, n_redacao]`.
Combinar parciais soma os quatro inteiros; quem coordena deve garantir exatamente
uma contribuição por ID; na versão MPI, o mestre faz esse controle. O núcleo
não faz deduplicação de blocos.

A versão distribuída corta o arquivo em linhas sem interpretar o CSV (ver
[protocolo MPI](protocolo-mpi.md)); por isso rejeita qualquer entrada com aspas,
que a referência sequencial aceitaria. Os arquivos de `scripts/obter_dados.py`
não usam aspas.

O JSON de corretude independe do tamanho do bloco e não contém tempos.
O CLI escreve uma medição de tempo em JSON no stderr: inclui leitura, agregação,
segunda leitura para checksum e escrita do resultado; exclui inicialização do
interpretador. Ainda não é o executor de experimentos da etapa 6.
