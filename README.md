# Projeto de Sistemas Distribuídos — UNITINS

Sistema mestre/workers (padrão MapReduce) para processamento de alto volume de dados.

**Disciplina:** Sistemas Distribuídos — 7º período, 2026/2 — Prof. Mailson Oliveira

**Integrantes:** Alêkson Castro, Italo Beckman, Matheus Nardi

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `relatorios/` | `template/` com preâmbulo, capa, `dados.tex` e `referencias.bib` compartilhados; `pre-projeto/`; uma pasta por semana (`semana-XX/`) |

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

Os dados **não** são versionados. Para obtê-los, use os scripts de download/geração (seed e checksum documentados aqui quando definidos).

## Fluxo de trabalho

- Trabalho direto na `main`: `git pull` antes de começar, depois `git add`, `git commit` e `git push`.
