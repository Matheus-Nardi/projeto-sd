# Projeto de Sistemas Distribuídos — UNITINS

Sistema mestre/workers (padrão MapReduce) para processamento de alto volume de dados.

**Disciplina:** Sistemas Distribuídos — 7º período, 2026/2 — Prof. Mailson Oliveira

**Integrantes:** Alêkson Castro, Italo Beckman, Matheus Nardi

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `docs/` | `padrao.md` (regras de relatório, slides e commits) e `decisoes/` (uma decisão por arquivo) |
| `relatorios/` | `template/` com preâmbulo, capa e `dados.tex` compartilhados; uma pasta por semana (`semana-XX/`) |
| `apresentacoes/` | `template/` e uma pasta por apresentação (`AAAA-MM-DD-nome/`) |
| `src/` | código do mestre (`master/`) e dos workers (`worker/`) |
| `experimentos/` | scripts, resultados (CSV) e gráficos |
| `infra/` | Vagrantfile, docker-compose e configuração das VMs |

## Dados

Os dados **não** são versionados. Para obtê-los, use os scripts em `experimentos/` (seed e checksum documentados aqui quando definidos).

## Fluxo de trabalho

- Trabalho direto na `main`: `git pull` antes de começar, depois `git add`, `git commit` e `git push`.
- Cada entrega semanal vira uma tag + Release (`semana-01`, `semana-02`...) com o PDF anexado.
