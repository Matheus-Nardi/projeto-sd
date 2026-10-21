# Projeto de Sistemas Distribuídos — Contexto

> Arquivo de contexto para o Claude Code e para os integrantes do grupo.
> Atualize este arquivo sempre que uma decisão importante for tomada (no mesmo commit da mudança).

## Sobre o projeto

- **Disciplina:** Sistemas Distribuídos — Sistemas de Informação, UNITINS — 7º período, semestre 2026/2
- **Professor:** Mailson Oliveira
- **Peso:** substitui a prova da 2ª avaliação (projeto em vez de prova)
- **Formato:** projeto em grupo com **entregas semanais** (relatório + eventualmente apresentação)
- **Cenário escolhido:** _[A DEFINIR — preencher com o cenário proposto pelo professor que o grupo escolheu]_
- **Integrantes:** Alêkson Castro (`aleksoncastro`), Italo Beckman (`italobeckman`), Matheus Nardi (`Matheus-Nardi`)
- **Repositório:** https://github.com/Matheus-Nardi/projeto-sd (público)

### Resumo do cenário

Sistema com arquitetura **mestre/workers** para processamento de **alto volume de dados**:

1. O **mestre** divide os dados em pedaços (*chunks*) e distribui tarefas.
2. Os **workers** processam seus pedaços em paralelo e devolvem resultados parciais (pequenos).
3. O mestre **agrega** os resultados parciais e produz a resposta final.

Padrão base: **MapReduce** (dividir → processar em paralelo → combinar).

- **Pergunta que o sistema responde:** _[A DEFINIR — ex.: "média de nota de matemática por estado no ENEM"]_
- **Tipo de processamento:** _[A DEFINIR — agregação, filtragem, contagem, ordenação, análise de logs...]_

## Ideias em avaliação (nada decidido ainda)

### Ambiente de execução
- **VMs** (VirtualBox ou KVM) simulando máquinas separadas: 1 mestre + 2 a 3 workers, em rede interna com IPs fixos e acesso via SSH.
- **Distro voltada a cluster:** o professor mencionou que existem distros próprias para isso. A candidata principal é a **PelicanHPC** (Debian, live, traz Open MPI e monitoramento Ganglia; os workers dão boot pela rede a partir do frontend). Rocks Cluster está descontinuada (última versão em 2017) e deve ser evitada.
  - Importante: a distro **não particiona os dados sozinha**. Ela entrega o ambiente pronto (rede, SSH, MPI). A divisão e a distribuição são feitas pelo nosso programa.
- **Alternativas:** Docker Compose para o desenvolvimento do dia a dia; os notebooks do grupo na mesma rede para a demonstração final.
- **Vagrant** para versionar a criação das VMs (`Vagrantfile` no repositório).

### Comunicação / implementação
- **MPI** (`mpi4py` em Python ou C com Open MPI): `scatter` dos pedaços e `gather` dos resultados.
- Alternativas: sockets, gRPC, fila de mensagens (RabbitMQ). Para comparação: Dask, Ray ou Spark.

### Dados de teste
- **Sintéticos** (para experimentos controlados de escala): script Python com seed fixa, TPC-H (dbgen, *scale factor*) ou TeraGen.
- **Reais** (para credibilidade): microdados do ENEM (INEP), NYC Taxi Trip Records, Portal da Transparência, dumps da Wikipedia, Kaggle.
- Escala sugerida: ~100 MB para validar → 1 a 5 GB para os experimentos.
- **Dados NÃO vão para o Git.** Versionar apenas o script de download/geração, com seed e checksum anotados no README.

### Desafios de Sistemas Distribuídos a explorar
- **Balanceamento de carga com máquinas heterogêneas:** usar **fila dinâmica de tarefas** (*self-scheduling*): muitos pedaços pequenos, e cada worker pede o próximo ao terminar. Comparar com a divisão estática igual.
- **Tolerância a falhas:** detectar worker caído e reatribuir o pedaço dele.
- **Desempenho:** *speedup* com 1, 2 e 4 workers; impacto do tamanho do pedaço; quando a comunicação passa a dominar.
- Simular heterogeneidade: VMs com núcleos diferentes, *execution cap* de CPU no VirtualBox ou atraso artificial no worker.

### Experimentos planejados (rascunho)
1. Tempo total × número de workers (*speedup*).
2. Divisão estática × fila dinâmica em cluster heterogêneo (tempo total, pedaços por worker, ociosidade).
3. Derrubar um worker no meio da execução e verificar a recuperação.

## Organização do grupo

### Versionamento
- **Git + GitHub**, repositório público. Todos fazem commit e push direto na `main` (sem branches nem Pull Requests obrigatórios). Antes de começar a trabalhar, sempre `git pull`.
- Commits: curtos, no imperativo (ex.: `adiciona seção de resultados da semana 3`).
- Tarefas como **issues** no GitHub Projects (A fazer → Fazendo → Feito), cada uma com responsável e prazo.

### Papéis rotativos (trocam a cada semana)
- **Redator:** consolida o relatório.
- **Revisor:** revisa o relatório final e o código da semana.
- **Responsável técnico:** código e experimentos da semana.
- **Apresentador:** apresenta quando houver apresentação.

### Estrutura do repositório
Mantida enxuta de propósito: novas pastas só entram quando houver conteúdo para elas (ex.: código, experimentos).
```
projeto-sd/
├── CLAUDE.md
├── README.md
├── ideia.md                # este arquivo: contexto e decisões
├── Makefile                # build dos relatórios (make ajuda)
├── .gitignore              # ignora auxiliares do LaTeX e a pasta de dados
└── relatorios/
    ├── template/           # preâmbulo, capa, dados.tex (dados compartilhados), img/logo, main.tex modelo e secoes/
    └── semana-XX/          # criado com make novo-relatorio S=XX
```

### Padrão de relatórios (LaTeX)
- Build: `make relatorio S=XX` na raiz (ver README). Preâmbulo comum em `relatorios/template/`; uma seção por arquivo (`\input{secoes/...}`); referências em um `.bib` compartilhado. Usar abnTeX2 se o professor exigir ABNT.
- **Capa obrigatória em todo relatório**, com:
  - logo da universidade (UNITINS)
  - instituição, curso e disciplina
  - título do projeto e título/número da entrega (ex.: "Relatório Semanal 03")
  - cenário escolhido
  - integrantes
  - professor
  - local e data da entrega (`AAAA-MM-DD`)
- **Dados fundamentais compartilhados:** as informações fixas da capa (instituição, curso, disciplina, professor, título do projeto, cenário, integrantes, logo) ficam definidas **uma única vez** em `relatorios/template/dados.tex` (como macros, ex.: `\professor`, `\integrantes`) e o logo em `relatorios/template/img/logo-unitins.png`. Todos os relatórios e slides importam esse arquivo, e cada relatório define só o que muda: número da semana, título da entrega e data. Mudou um integrante ou o cenário? Altera-se só esse arquivo.
  - Título do projeto: _[A DEFINIR]_
- **Estrutura fixa de todo relatório semanal (depois da capa):**
  1. Objetivo da semana
  2. O que foi feito
  3. Decisões tomadas e por quê
  4. Resultados e métricas
  5. Problemas encontrados
  6. Próximos passos
  7. Contribuição de cada integrante
- Nomenclatura: minúsculas, sem acento, datas no formato `AAAA-MM-DD`.

### Padrão de slides
- Beamer (mesmo preâmbulo e cores dos relatórios) ou template HTML versionado. _[A DEFINIR]_
- Fixar: capa (reaproveitando `relatorios/template/dados.tex` e o logo), sequência de seções, paleta, fonte, estilo de diagrama e pouco texto por slide.

## Próximos passos

- [ ] Reunião do grupo: definir cenário, pergunta do sistema, ambiente e papéis da semana 1
- [x] Criar o repositório no GitHub e convidar os integrantes
- [x] Template LaTeX dos relatórios e Makefile de build
- [ ] **Apresentação do pré-projeto (22/10/2026)**, roteiro sugerido:
  1. Problema e cenário escolhido
  2. Por que é um problema distribuído (volume de dados, limite de uma máquina só)
  3. Arquitetura proposta (diagrama mestre → workers)
  4. Ambiente e tecnologias candidatas
  5. Métricas de sucesso
  6. Cronograma das entregas semanais
  7. Divisão de papéis
  8. Riscos e desafios (heterogeneidade, falhas, custo de comunicação)

## Instruções para o Claude

- O grupo **ainda está aprendendo** Sistemas Distribuídos: explique os conceitos de forma didática e justifique as escolhas técnicas.
- Responda em **português**.
- Siga os padrões descritos neste arquivo ao gerar relatórios, slides ou código.
- Prefira soluções simples e reprodutíveis (seed fixa, scripts versionados, ambiente via Vagrant/Docker).
- Ao tomar ou sugerir uma decisão importante, proponha registrá-la neste arquivo e na seção "Decisões tomadas" do relatório da semana.
- Itens marcados como _[A DEFINIR]_ ainda não foram decididos pelo grupo: não assuma valores para eles; pergunte.