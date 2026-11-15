# Projeto de Sistemas Distribuídos — Contexto

> Arquivo de contexto para o Claude Code e para os integrantes do grupo.
> Atualize este arquivo sempre que uma decisão importante for tomada (no mesmo commit da mudança).

## Sobre o projeto

- **Disciplina:** Sistemas Distribuídos — Sistemas de Informação, UNITINS — 7º período, semestre 2026/2
- **Professor:** Mailson Oliveira
- **Peso:** substitui a prova da 2ª avaliação (projeto em vez de prova)
- **Formato:** projeto em grupo com **entregas semanais às quintas-feiras** (relatório + eventualmente apresentação)
- **Entrega final (A2):** 03/12/2026 (quinta), última aula do semestre
- **Cenário escolhido:** Processamento distribuído de grande volume de dados com arquitetura mestre/workers (um dos 4 cenários propostos pelo professor; os outros envolviam load balancing entre aplicações e banco de dados distribuído, entre outros)
- **Integrantes:** Alêkson Castro (`aleksoncastro`), Italo Beckman (`italobeckman`), Matheus Nardi (`Matheus-Nardi`)
- **Repositório:** https://github.com/Matheus-Nardi/projeto-sd (público)

### Resumo do cenário

Sistema com arquitetura **mestre/workers** para processamento de **alto volume de dados**:

1. O **mestre** divide os dados em pedaços (*chunks*) e distribui tarefas.
2. Os **workers** processam seus pedaços em paralelo e devolvem resultados parciais (pequenos).
3. O mestre **agrega** os resultados parciais e produz a resposta final.

Padrão base: **MapReduce** (dividir → processar em paralelo → combinar).

- **Prioridade: técnica primeiro, negócio depois.** O núcleo (mestre/workers, distribuição, agregação, medições) não depende do tema dos dados; o desenvolvimento pode começar com dados sintéticos enquanto os datasets reais são analisados.
- **Pergunta que o sistema responde (Decidido em 29/10/2026):** Média das notas de Matemática e Redação por Unidade Federativa (UF) e tipo de dependência administrativa da escola (pública vs. privada).
- **Tipo de processamento (Decidido em 29/10/2026):** Filtragem de faltosos/eliminados e agregação aditiva por chave composta `(UF, TP_ESCOLA)` em modelo MapReduce (tuplas `[soma, contagem]`).

### Visão atual (para o pré-projeto)

Termos que descrevem o cenário, cada um sob um aspecto:

| Aspecto | Termo |
|---|---|
| Arquitetura | mestre/trabalhador (*master-worker*) |
| Tipo de paralelismo | paralelismo de dados (*data parallelism*): a mesma operação em pedaços diferentes |
| Modelo de programação | MapReduce / *scatter-gather* (dividir → processar → combinar) |
| Natureza do problema | "embaraçosamente paralelo": pedaços independentes entre si |
| Forma de execução | processamento em lote (*batch*): roda sobre um conjunto de dados e termina |
| Fila dinâmica | *bag of tasks* / *task farm* |

**Diferença para o cenário de load balancing:** load balancing distribui *requisições* que chegam continuamente (processamento online; foco em disponibilidade e tempo de resposta). O nosso cenário distribui *pedaços de dados* de um trabalho com começo e fim (batch; foco em terminar mais rápido, ou seja, *speedup*). Balanceamento de carga aparece aqui só como desafio interno (não deixar worker ocioso).

**Conceitos a medir e discutir:** *speedup* (tempo com 1 worker ÷ tempo com N), Lei de Amdahl (a parte não paralelizável limita o ganho), custo de comunicação (pedaços pequenos demais fazem a rede dominar), balanceamento estático × dinâmico e tolerância a falhas.

**Nota de ambiente:** a PelicanHPC segue mantida (versão 6.1, set/2025, baseada no Debian 13), mas o grupo optou por Ubuntu Server (ver "Ambiente de execução").

## Ideias e decisões técnicas (itens decididos vêm marcados com "Decidido" e a data)

### Ambiente de execução
- **Decidido (21/10/2026): um ambiente por etapa.**
  - **Desenvolvimento:** máquina local ou Docker (`mpirun -n 4` numa máquina só já roda 4 processos).
  - **Validação:** VMs com **Ubuntu Server** sem interface gráfica, criadas com **Vagrant** (`Vagrantfile` no repositório): 1 mestre + 2 a 3 workers, rede interna com IPs fixos e SSH. Servem para testar rede real e falhas (desligar uma VM).
  - **Medição (atualizado em 15/11/2026):** cluster em containers Docker no WSL, num host de 16 núcleos/32 threads, com um processo por container. A medição em notebooks físicos, prevista no pré-projeto, foi descartada. Limite assumido: os nós dividem a CPU do mesmo computador e a rede é uma ponte virtual, então o custo de rede real não aparece nas medições.
  - Motivo de usar distro comum: uma distro de cluster só automatiza a configuração que o MPI precisa (MPI igual em todos os nós, rede, SSH sem senha, hostfile, programa/dados acessíveis). Numa distro comum o grupo faz isso com scripts, tem mais controle e documenta a montagem como aprendizado. Clusters reais também costumam usar distros de uso geral.
- **Decidido (21/10/2026): automação com Vagrant + Ansible.** Vagrant *cria* as VMs; Ansible *configura* os nós (instala Open MPI e `mpi4py`, distribui chaves SSH, gera o hostfile, copia o programa). Motivo: a mesma role configura as VMs e os containers, então validação e medição usam configuração idêntica. O grupo já usou Ansible em outras disciplinas. Quem usa Windows precisa de WSL para rodar o Ansible.
- **Alternativa avaliada:** PelicanHPC (Debian, live, Open MPI e Ganglia prontos; workers dão boot pela rede; v6.1 de set/2025). Rocks Cluster descontinuada (2017).

### Comunicação / implementação
- **Decidido (21/10/2026, atualizado em 29/10/2026): MPI via Python (mpi4py).** `scatter` dos pedaços e `gather` dos resultados, e mensagens ponto a ponto para a fila dinâmica. Motivo: padrão da computação em cluster e alta produtividade para manipulação e validação das tabelas de dados.
- Alternativas consideradas: sockets, gRPC, fila de mensagens (RabbitMQ). Para comparação: Dask, Ray ou Spark.

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

## Cronograma

Aulas e entregas às quintas-feiras. Cronograma pouco folgado: as semanas 1 e 2 correm em paralelo (datasets × cluster) para ganhar margem; a última semana é só para consolidar; se apertar, a tolerância a falhas é o que se simplifica.

| Etapa | Data | Entrega |
|---|---|---|
| Pré-projeto | 22/10/2026 | Apresentação da proposta |
| Semana 1 | 29/10/2026 | Análise dos datasets; escolha do dataset e da pergunta |
| Semana 2 | 05/11/2026 | Cluster de validação (VMs Ubuntu Server + Vagrant + Ansible) |
| Semana 3 | 12/11/2026 | Versão sequencial de referência + primeira versão distribuída (estática) |
| Semana 4 | 19/11/2026 | Fila dinâmica + experimento de escalabilidade |
| Semana 5 | 26/11/2026 | Tolerância a falhas + experimento estático × dinâmico |
| Final | 03/12/2026 | Consolidação e apresentação final |

## Organização do grupo

### Versionamento
- **Git + GitHub**, repositório público. Todos fazem commit e push direto na `main` (sem branches nem Pull Requests obrigatórios). Antes de começar a trabalhar, sempre `git pull`.
- Commits: curtos, no imperativo (ex.: `adiciona seção de resultados da semana 3`).
- Tarefas como **issues** no GitHub Projects (A fazer → Fazendo → Feito), cada uma com responsável e prazo.

### Papéis fixos (decidido em 21/10/2026)
Com 3 integrantes e 6 semanas, papéis fixos por frente rendem mais que rodízio (sem tempo de adaptação a cada semana). Não há revisor dedicado. Mesmo com papéis fixos, a tendência é todos participarem um pouco de tudo: o papel indica quem responde pela frente, não um limite.
- **Dados e documentação:** análise e preparo dos datasets (scripts, seed, checksum); consolida os relatórios semanais; slides; mantém este arquivo atualizado. Responsável: Matheus Nardi
- **Desenvolvimento:** código MPI (mestre, workers, fila dinâmica, tolerância a falhas) e versão sequencial de referência. Responsável: Alêkson Castro
- **Infraestrutura e experimentos:** Vagrant + Ansible, cluster de VMs e de containers; roda os experimentos, coleta métricas e gera gráficos. Responsável: Italo Beckman
- **Contratos entre as frentes:** desenvolvimento entrega um programa que roda com `mpirun`; infraestrutura entrega um cluster onde esse comando funciona; dados entrega o arquivo no formato combinado.
- **Relatórios:** cada um escreve a parte da sua frente; quem cuida da documentação consolida; todos leem o PDF antes da entrega (substitui o revisor).
- **Apresentações:** cada um apresenta a parte que conduziu.

### Estrutura do repositório
Mantida enxuta de propósito: novas pastas só entram quando houver conteúdo para elas (ex.: código, experimentos).
```
projeto-sd/
├── CLAUDE.md
├── README.md
├── ideia.md                # este arquivo: contexto e decisões
├── Makefile                # build dos relatórios (make ajuda)
├── Vagrantfile             # VMs do cluster de validação
├── .gitignore              # ignora auxiliares do LaTeX, dados e arquivos gerados do cluster
├── src/                    # núcleo de agregação, versão sequencial e versão MPI
├── tests/                  # testes (python -m unittest discover -s tests) e fixtures/
├── scripts/
│   ├── obter_dados.py      # download/extração do ENEM e gerador sintético
│   ├── cluster/            # preparar, conectar e validar as VMs; testes de infraestrutura
│   └── experimentos/       # execução e registro das medições
├── infra/                  # cluster.json (topologia), bootstrap.sh e ansible/ (playbooks e role)
├── docs/                   # contrato de dados, protocolo MPI e guia do cluster
├── resultados/             # medições pequenas e versionáveis dos experimentos
├── relatorios/
│   ├── template/           # preâmbulo, capa, dados.tex (dados compartilhados), referencias.bib, img/logo, main.tex modelo e secoes/
│   ├── pre-projeto/        # relatório do pré-projeto (make pre-projeto); segue o roteiro abaixo, não as 7 seções semanais
│   └── semana-XX/          # criado com make novo-relatorio S=XX
└── apresentacoes/
    ├── template/           # estilo.css, slides.js, dados.js (dados da capa)
    └── pre-projeto/        # index.html (abrir no navegador)
```

### Padrão de relatórios (LaTeX)
- Build: `make relatorio S=XX` na raiz (ver README). Preâmbulo comum em `relatorios/template/`; uma seção por arquivo (`\input{secoes/...}`); referências em um `.bib` compartilhado. Usar abnTeX2 se o professor exigir ABNT.
- **Capa obrigatória em todo relatório**, com:
  - logo da universidade (UNITINS)
  - instituição, curso e disciplina
  - título do projeto (que é o próprio cenário escolhido, por isso não há linha "Cenário" separada) e título/número da entrega (ex.: "Relatório Semanal 03")
  - integrantes
  - professor
  - local e data da entrega (`dd/mm/aaaa`)
- **Dados fundamentais compartilhados:** as informações fixas da capa (instituição, curso, disciplina, professor, título do projeto, cenário, integrantes, logo) ficam definidas **uma única vez** em `relatorios/template/dados.tex` (como macros, ex.: `\professor`, `\integrantes`) e o logo em `relatorios/template/img/logo-unitins.png`. Todos os relatórios e slides importam esse arquivo, e cada relatório define só o que muda: número da semana, título da entrega e data. Mudou um integrante ou o cenário? Altera-se só esse arquivo.
  - Título do projeto: igual ao cenário, "Processamento distribuído de grande volume de dados com arquitetura mestre/workers".
  - Local: Palmas – TO.
- **Estrutura fixa de todo relatório semanal (depois da capa):**
  1. Objetivo da semana
  2. O que foi feito
  3. Decisões tomadas e por quê
  4. Resultados e métricas
  5. Problemas encontrados
  6. Próximos passos
  7. Contribuição de cada integrante
- Datas: sempre no formato `dd/mm/aaaa` (relatórios, capa, cronograma, referências e neste arquivo).
- Nomenclatura de arquivos: minúsculas, sem acento.

### Padrão de slides
- **Decidido (21/10/2026): HTML + CSS versionados**, sem dependências externas (abre direto no navegador, funciona sem internet na sala).
  - Template em `apresentacoes/template/`: `estilo.css` (paleta azul-petróleo + coral: petróleo = dados e títulos, coral = mestre e destaques, verde-azulado = workers; cores só em variáveis no `:root`; fontes do sistema), `slides.js` (navegação) e `dados.js` (dados da capa, equivalente ao `dados.tex`; **mudou um, mude o outro**). O logo é o mesmo de `relatorios/template/img/`. Logos das tecnologias em `apresentacoes/template/img/icones/` (SVGs do Simple Icons 11.0.0 com a cor oficial; Open MPI do site oficial), salvos localmente para funcionar sem internet.
  - Cada apresentação é uma pasta `apresentacoes/<nome>/index.html` que define só `data-entrega` e `data-data` no `<body>`.
  - Slides de 1280×720 (16:9), pouco texto por slide. Navegação: setas/espaço/clique; `F` tela cheia; PDF com `make slides A=<nome>` (Chrome/Chromium sem janela; um slide por página, gera `apresentacoes/<nome>/<nome>.pdf`, versionado como os PDFs dos relatórios). Sem `make`, `Ctrl+P` → "Salvar como PDF" no Chrome dá o mesmo resultado.

## Próximos passos

- **Cluster em Docker no WSL (15/11/2026):** `scripts/cluster/docker.py` sobe
  mestre + N workers em containers com a mesma role Ansible; é o ambiente de
  desenvolvimento e de medição (ver "Ambiente de execução"). Motivo: com
  o WSL2 ativo, o VirtualBox roda sobre o Hyper-V e fica lento e instável com
  mais de 1 vCPU por VM. As VMs continuam sendo a validação com máquinas
  separadas (1 vCPU cada). Medição com
  8 workers: speedup de 7,2 na fila dinâmica (`resultados/docker-*`).

- **Experimentos e falhas implementados (15/11/2026):** executor em
  `scripts/experimentos/executar.py` (aquecimento, repetições, mediana, speedup,
  conferência de corretude) com resultados exploratórios das VMs em `resultados/`.
  **Decidido (15/11/2026): tolerância a falhas por checkpoint + reinício
  supervisionado**, não por continuidade automática. Motivo: na prova feita nas
  VMs, o Open MPI 4.1.6 aborta o job inteiro quando um processo morre. O mestre
  grava cada bloco concluído e, ao relançar, só os blocos faltantes são
  distribuídos aos nós que ainda respondem. Limite assumido: a queda do mestre
  exige relançamento manual. Repositório reorganizado (`scripts/cluster/`,
  `scripts/experimentos/`). Pendentes: 4 workers em VMs e gráficos.

- **Versão distribuída implementada (15/11/2026):** `src/distribuido.py` com
  divisão estática (rodízio) e fila dinâmica, validado nas VMs com a entrada
  real: saídas idênticas à sequencial. **Decidido (15/11/2026):** o mestre envia
  o texto cru das linhas e os workers interpretam o CSV, para reduzir a parte
  sequencial (Lei de Amdahl); o mestre mantém no máximo uma tarefa em voo por
  worker. Ver `docs/protocolo-mpi.md`.

- **Infraestrutura implementada (15/11/2026):** Vagrant/Ansible com topologia
  configurável, chaves próprias por nó e troca apenas de material público após
  todos estarem prontos. Código/dados de execução ficam em disco Linux e o
  compartilhamento das VMs é somente leitura. Provisionamento idempotente e
  comunicação MPI comprovados em containers e, depois, nas VMs.
  Ver `docs/cluster.md`.
  Nenhum commit deve ser feito sem aval explícito do usuário.

- **Implementação iniciada (15/11/2026):** referência sequencial em `src/`, com
  leitura em blocos e testes manuais. A pergunta usa UF da aplicação da prova e
  tipo de escola do ensino médio (`TP_ESCOLA`), mantendo não respondentes separados.
  Elegibilidade e contagem são independentes por prova; notas zero são incluídas
  para presentes. Somas em décimos inteiros, médias finais com duas casas e
  `ROUND_HALF_UP`. Ver `docs/contrato-dados.md`.

- [x] Definir o cenário (mestre/workers)
- [x] Analisar datasets candidatos e definir a pergunta que o sistema responde
- [x] Definir o ambiente (local/Docker → VMs Ubuntu com Vagrant) e a comunicação (MPI), com automação via Vagrant + Ansible
- [x] Definir o modelo de papéis (fixos, um por frente)
- [x] Definir quem assume cada papel
- [x] Criar o repositório no GitHub e convidar os integrantes
- [x] Template LaTeX dos relatórios e Makefile de build
- [x] **Apresentação do pré-projeto (22/10/2026)**: relatório em `relatorios/pre-projeto/`, com caráter exploratório (opções de datasets e de ambiente, critérios de escolha e quando cada decisão será tomada). Roteiro:
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
