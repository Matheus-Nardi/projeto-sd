# Projeto de Sistemas Distribuídos — UNITINS

Sistema mestre/workers (padrão MapReduce) para processamento de alto volume de dados.

**Disciplina:** Sistemas Distribuídos — 7º período, 2026/2 — Prof. Mailson Oliveira

**Integrantes:** Alêkson Castro, Italo Beckman, Matheus Nardi

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `relatorios/` | `template/` com preâmbulo, capa, `dados.tex` e `referencias.bib` compartilhados; `pre-projeto/`; uma pasta por semana (`semana-XX/`) |
| `apresentacoes/` | Slides em HTML/CSS: `template/` (estilo, navegação e `dados.js` da capa) e uma pasta por apresentação; abra o `index.html` no navegador |
| `src/` | Núcleo de agregação, versão sequencial e versão MPI |
| `tests/` | Testes (`python -m unittest discover -s tests`) e `fixtures/` |
| `scripts/` | `obter_dados.py` (download/extração do ENEM e gerador sintético); `cluster/` (preparar, conectar e validar as VMs; testes de infraestrutura); `experimentos/` (execução e registro das medições) |
| `infra/` | `cluster.json` (topologia), `bootstrap.sh` e `ansible/` (playbooks e role) |
| `docs/` | Contrato de dados, protocolo MPI e guia do cluster |
| `resultados/` | Medições pequenas e versionáveis dos experimentos |

## Relatórios em LaTeX

### O que instalar (uma vez)

É preciso ter `make`, `latexmk` e uma distribuição TeX Live com suporte a português.

| Sistema | Comando |
|---|---|
| Ubuntu / Debian / WSL | `sudo apt install make latexmk texlive-latex-extra texlive-lang-portuguese texlive-fonts-recommended` |
| Arch / Manjaro | `sudo pacman -S make texlive-basic texlive-latex texlive-latexextra texlive-langportuguese texlive-binextra texlive-fontsrecommended` |
| Windows | use o **WSL** (Ubuntu) e siga a linha do Ubuntu |

### Comandos (sempre na raiz do repositório)

```bash
make                        # mostra a ajuda e os relatórios existentes
make novo-relatorio S=01    # cria relatorios/semana-01/ a partir do template
make relatorio S=01         # gera relatorios/semana-01/relatorio-semana-01.pdf
make pre-projeto            # gera relatorios/pre-projeto/pre-projeto.pdf
make assistir S=01          # recompila sozinho sempre que um .tex for salvo (Ctrl+C para sair)
make todos                  # gera todos os relatórios
make template               # gera o PDF do template, para conferir a capa
make limpar                 # apaga arquivos auxiliares (.aux, .log...)
make slides A=pre-projeto   # exporta apresentacoes/pre-projeto/ para PDF (precisa do Chrome ou Chromium)
```

### Passo a passo de um relatório semanal

1. `git pull`
2. `make novo-relatorio S=01` (só uma pessoa faz isso, uma vez por semana)
3. Abra `relatorios/semana-01/main.tex` e ajuste **só** o bloco marcado: título da entrega e data.
4. Escreva o conteúdo em `relatorios/semana-01/secoes/` (um arquivo por seção; dividir as seções entre os integrantes evita conflitos no Git).
5. `make relatorio S=01` e confira o PDF.
6. `git add`, `git commit` e `git push` (o PDF também é versionado).

### Onde fica cada coisa

- `relatorios/template/dados.tex`: dados da capa que valem para **todos** os relatórios (integrantes, professor, cenário...). Mudou algo? Altere só aqui.
- `relatorios/template/preambulo.tex`: pacotes e configuração comuns.
- `relatorios/template/capa.tex`: layout da capa.
- `relatorios/template/img/`: logo e imagens compartilhadas. Imagens de uma semana específica vão em `relatorios/semana-XX/img/`.

Se a compilação falhar, o `make` mostra o arquivo e a linha do erro, e o log completo fica em `relatorios/semana-XX/relatorio-semana-XX.log`.

## Dados

A referência sequencial já pode ser executada com Python, sem dependências externas:

```bash
python -m unittest discover -s tests -v
python -m src.sequencial tests/fixtures/enem_manual.csv --bloco-linhas 2
python -m src.sequencial dados/enem_2023_real.csv --saida dados/resultado_sequencial.json
```

O resultado JSON contém somas, contagens e médias por UF da prova e tipo de escola.
O tempo é escrito separadamente no stderr. Consulte o [contrato de dados](docs/contrato-dados.md)
para filtros, tratamento de zeros, precisão e formato.

A versão distribuída (`src/distribuido.py`) roda com MPI, com divisão estática ou
fila dinâmica, e produz o mesmo JSON da referência:

```bash
mpirun -n 3 python3 -m src.distribuido dados/enem_2023_real.csv --politica dinamica
```

O cluster de VMs (Vagrant + Ansible) está validado com mestre e dois workers.
O [guia do cluster](docs/cluster.md) contém comandos, configuração de recursos e
evidências; o [protocolo MPI](docs/protocolo-mpi.md) descreve mensagens, políticas,
métricas e o tratamento de falhas.

Experimentos e falhas (executar no mestre do cluster, em `/opt/projeto-sd/code`):

```bash
# sequencial + MPI, com aquecimento e 5 repetições; grava execucoes.csv e resumo.json
python3 -m scripts.experimentos.executar /opt/projeto-sd/dados/enem_2023_real.csv \
  --saida-dir /opt/projeto-sd/resultados/teste --workers 1 2 \
  --hostfile /opt/projeto-sd/hostfile --rede 192.168.56.0/24 --ambiente vm

# job com checkpoint, relançado automaticamente se um worker cair
python3 -m scripts.experimentos.com_retomada /opt/projeto-sd/dados/enem_2023_real.csv \
  --saida /opt/projeto-sd/resultados/r.json --checkpoint /opt/projeto-sd/resultados/r.jsonl \
  --hostfile /opt/projeto-sd/hostfile --rede 192.168.56.0/24
```

Neste computador, o caminho mais rápido é o cluster em containers no WSL
(`python3 -m scripts.cluster.docker subir --workers 8`, ver o guia do cluster).

As medições guardadas em `resultados/` foram feitas em VMs e em containers no mesmo computador;
os nós dividem a CPU do host e a rede é virtual.

Os dados **não** são versionados no Git. O script `scripts/obter_dados.py` gerencia tanto o download dos microdados oficiais do INEP quanto a geração sintética para testes:

```bash
# 1. DADOS REAIS: Baixar o pacote oficial do ENEM (INEP) e extrair CSV filtrado
python scripts/obter_dados.py --baixar-enem --ano 2023

# Extrair uma amostra de 200.000 linhas reais a partir do ZIP oficial:
python scripts/obter_dados.py --extrair-real --ano 2023 --amostra-linhas 200000

# 2. DADOS SINTÉTICOS: Gerar amostra determinística de 10 MB (seed=42)
python scripts/obter_dados.py --gerar-sintetico --mb 10 --saida dados/enem_sintetico_amostra.csv --seed 42

# 3. INSPEÇÃO E CHECKSUM
python scripts/obter_dados.py --inspecionar dados/enem_sintetico_amostra.csv
python scripts/obter_dados.py --checksum dados/enem_sintetico_amostra.csv
```

**Checksums de referência:**
- `dados/enem_2023_real.csv` (113.91 MB, 3.933.955 participantes reais do ENEM 2023): `e3d4e5c7e2d07db0ea501690dd2f6b49de3566e7eb45835deac47490d4f65169`
- `dados/enem_sintetico_amostra.csv` (10 MB, seed 42): `72ad34931db8e1adf99a53b0f99549d26a3c6075d98eafc7425ae76e0b5796b7`

## Fluxo de trabalho

- Trabalho direto na `main`: `git pull` antes de começar, depois `git add`, `git commit` e `git push`.
