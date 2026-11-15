# Protocolo MPI proposto

Estado: implementado em `src/distribuido.py` (15/11/2026), com testes em
`tests/test_distribuido.py`. As duas políticas reproduziram o JSON da referência
sequencial com a entrada real nas VMs (mestre + 1 e 2 workers).

```bash
mpirun --hostfile /opt/projeto-sd/hostfile --map-by ppr:1:node -np 3 \
  /usr/bin/python3 -m src.distribuido entrada.csv --politica dinamica \
  [--bloco-linhas 10000] [--saida resultado.json] [--atraso 1=0.05] \
  [--checkpoint blocos.jsonl]
```

Rank zero é mestre dedicado. Os ranks `1..N` são workers. O mesmo núcleo de
agregação e o mesmo JSON de corretude da referência sequencial serão utilizados.
A entrada permanece imutável durante a execução.

## Mensagens e contabilidade

- `TASK`: ID inteiro contíguo a partir de zero, nomes das colunas e o texto das
  linhas do bloco, ainda sem interpretar. O mestre só corta o arquivo em linhas;
  interpretar o CSV e validar os campos é trabalho do worker. Assim a parte
  sequencial (Lei de Amdahl) fica restrita a leitura, serialização e agregação
  final. Como o corte ignora o CSV, entradas com aspas são rejeitadas.
- `RESULT`: ID, rank, quantidade de linhas, tempo gasto na tarefa e parcial de
  somas/contagens, ou erro da tarefa. O parcial tem o formato retornado por `agregar`.
- `STOP`: encerra a recepção de tarefas naquele worker, inclusive sem trabalho.

Cada tipo terá uma tag MPI fixa. O mestre mantém no máximo uma tarefa pendente
por worker e só aceita o ID que atribuiu àquele rank. Resultados duplicados,
inesperados ou com quantidade de linhas divergente invalidam a execução.
Antes de combinar um parcial, valida a identidade da tarefa. Ao final, não pode
haver tarefas pendentes e as contagens de blocos e linhas devem coincidir com o envio.

Não haverá scatter de toda a entrada. O mestre lê em fluxo e mantém os agregados,
metadados das tarefas em voo e um bloco de leitura. Cada worker mantém um bloco.
Os resultados são compactos, com até 81 grupos observados.

## Políticas

No estático, o destino é `1 + bloco_id % N`. Se esse worker ainda estiver ocupado,
o mestre recebe resultados até ele ficar disponível. Pode receber resultados
fora de ordem, mas não muda o destino do próximo bloco.

No dinâmico, qualquer worker disponível recebe o próximo bloco. Após receber um
resultado, o mestre pode imediatamente enviar outra tarefa àquele worker.

Em ambas as políticas, o mestre envia tarefas apenas a workers ociosos e STOP
apenas quando não há tarefa pendente naquele rank. Um worker envia exatamente
um resultado antes de voltar a receber. Essa ordem evita depender do buffer
eager do MPI para que envios bloqueantes progridam; os testes devem incluir
mensagens maiores que esse buffer.

Após EOF, todos os workers recebem STOP quando ficam ociosos. O resultado final
só é escrito após sucesso completo. Uma comunicação coletiva final informa o
estado da execução; todos os workers precisam alcançá-la para o término normal.
O smoke de infraestrutura já verifica ranks e hostnames, dispensando outro
protocolo HELLO no algoritmo.

## Erros e atraso controlado

Erros de dados em uma tarefa retornam como RESULT com erro. O mestre interrompe
novos envios, drena tarefas em andamento e envia STOP conforme os workers ficam
ociosos. Erro de leitura no mestre segue a mesma regra. Não publica resultado
parcial; a execução termina com código diferente de zero.

Violação de protocolo ou perda de processo pode exigir `MPI.Abort`. O lançamento
terá timeout externo. Isso detecta travamento e encerra a execução; não é
recuperação automática nem garantia de reutilização do comunicador.

Um atraso fixo configurável por rank será aplicado por tarefa, nas duas políticas.
Os parâmetros e a distribuição de tarefas serão registrados junto das métricas,
separadamente do JSON usado para comparar corretude. Não se exigirá ganho de
desempenho para aprovar a fila dinâmica.

## Falhas: checkpoint e reinício supervisionado

Prova feita nas VMs em 15/11/2026 com Open MPI 4.1.6: ao matar o processo de um
worker, o `mpirun` encerra o job inteiro em poucos segundos (código 137) e nenhum
resultado é escrito. Com `--enable-recovery` o job não se recupera: fica parado
até o timeout externo. Portanto **não há continuidade automática** dentro de uma
execução MPI; o que o projeto oferece é reinício sem perder o trabalho já feito.

- `--checkpoint ARQ`: o mestre acrescenta ao arquivo, com `fsync`, uma linha JSON
  por bloco concluído (ID, quantidade de linhas e parcial). A primeira linha
  identifica o tamanho da entrada e o tamanho do bloco.
- Se o arquivo já existe, o mestre soma os parciais gravados e **não reenvia**
  esses blocos. Uma última linha cortada pela queda é descartada. Checkpoint de
  outra entrada, de outro tamanho de bloco ou com bloco repetido é erro.
- Cada bloco continua contribuindo exatamente uma vez: ou vem do checkpoint, ou
  é processado nesta execução.
- `python3 -m scripts.experimentos.com_retomada ENTRADA --saida R.json
  --checkpoint C.jsonl --hostfile H [--rede SUBREDE] [--tentativas 3]`, executado
  no mestre, relança o job quando ele falha, usando só os nós que respondem por
  SSH. O mestre não é protegido: se ele cair, o supervisor cai junto e a
  retomada é manual, com o mesmo comando.

## Métricas

O mestre escreve no stderr uma linha JSON, separada do resultado: política,
workers, tamanho do bloco, atrasos, blocos retomados do checkpoint, `tempo_total_s` (do início do programa até
o resultado escrito; exclui o lançamento pelo `mpirun`), blocos, bytes
serializados enviados, tarefas por worker e tempo ocupado por worker.

## Testes

Os casos abaixo rodam em qualquer máquina com um comunicador simulado por
threads; com `mpirun` e `mpi4py` presentes (nós do cluster), a mesma suíte
também lança processos MPI reais.

1. Contabilidade: resultados fora de ordem, duplicados, inesperados, incompletos,
   rank/ID divergentes e contagem de linhas errada.
2. Atribuição estática para 1, 2 e 4 workers, com zero, poucos e muitos blocos.
3. Fixture manual: saída das duas políticas idêntica à sequencial, com blocos de
   1, 2, 3 linhas e maiores que a entrada; último bloco parcial.
4. Cabeçalho sem registros e menos blocos que workers; todos encerram.
5. Cabeçalho inválido e erro de dados após algumas tarefas já enviadas; saída
   vazia e término dentro do prazo, sem workers aguardando trabalho.
6. Blocos acima do limite eager; atraso em um worker nas duas políticas.
7. Comparação com entrada real pelo mesmo checksum, após preparar dados em disco
   Linux. Resultados exatos; medições em VMs identificadas como exploratórias.

Quatro workers só serão testados quando houver recursos disponíveis. ACK, run ID
e bitmap global foram considerados e descartados; a versão atual usa o estado
das tarefas pendentes e a conclusão coletiva. O reinício é feito pelo checkpoint
descrito acima, sem ACK nem bitmap.
