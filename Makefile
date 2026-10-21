# =============================================================
# Build dos documentos LaTeX do projeto.
# Rode `make` (ou `make ajuda`) na raiz do repositório para ver os comandos.
# =============================================================

LATEXMK   := latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error -silent
RELDIR    := relatorios
APRDIR    := apresentacoes
TEMPLATE  := $(RELDIR)/template

# Todas as pastas que têm um main.tex (exceto os templates)
RELATORIOS    := $(filter-out $(TEMPLATE),$(patsubst %/main.tex,%,$(wildcard $(RELDIR)/*/main.tex)))
APRESENTACOES := $(filter-out $(APRDIR)/template,$(patsubst %/main.tex,%,$(wildcard $(APRDIR)/*/main.tex)))

# compila(pasta, nome-do-pdf): gera <pasta>/<nome>.pdf e apaga os auxiliares
define compila
	@echo ">> Compilando $(1)/main.tex -> $(1)/$(2).pdf"
	@cd $(1) && $(LATEXMK) -jobname=$(2) main.tex >/dev/null 2>&1 \
		|| { echo "!! Erro de compilação:"; grep -A2 -E '^(!|.*:[0-9]+:)' $(2).log | head -15; \
		     echo "!! Log completo: $(1)/$(2).log"; exit 1; }
	@cd $(1) && latexmk -c -jobname=$(2) main.tex >/dev/null 2>&1
	@echo "OK: $(1)/$(2).pdf"
endef

.PHONY: ajuda relatorio novo-relatorio apresentacao todos template assistir limpar checa-s

ajuda:
	@echo "Uso (sempre na raiz do repositório):"
	@echo ""
	@echo "  make novo-relatorio S=01      cria relatorios/semana-01/ a partir do template"
	@echo "  make relatorio S=01           gera relatorios/semana-01/relatorio-semana-01.pdf"
	@echo "  make assistir S=01            recompila sozinho a cada vez que um .tex é salvo"
	@echo "  make apresentacao N=pasta     gera apresentacoes/<pasta>/<pasta>.pdf"
	@echo "  make todos                    gera todos os relatórios e apresentações"
	@echo "  make template                 gera o PDF do template (para conferir a capa)"
	@echo "  make limpar                   apaga arquivos auxiliares do LaTeX"
	@echo ""
	@echo "Relatórios encontrados:     $(or $(RELATORIOS),nenhum)"
	@echo "Apresentações encontradas:  $(or $(APRESENTACOES),nenhuma)"

checa-s:
	@test -n "$(S)" || { echo "!! Informe a semana, ex.: make $(MAKECMDGOALS) S=01"; exit 1; }

novo-relatorio: checa-s
	@test ! -e $(RELDIR)/semana-$(S) || { echo "!! $(RELDIR)/semana-$(S) já existe"; exit 1; }
	@mkdir -p $(RELDIR)/semana-$(S)
	@cp -r $(TEMPLATE)/main.tex $(TEMPLATE)/secoes $(RELDIR)/semana-$(S)/
	@sed -i 's/\\newcommand{\\numerosemana}{XX}/\\newcommand{\\numerosemana}{$(S)}/' $(RELDIR)/semana-$(S)/main.tex
	@echo "OK: criado $(RELDIR)/semana-$(S)/ (edite main.tex e os arquivos em secoes/)"

relatorio: checa-s
	@test -f $(RELDIR)/semana-$(S)/main.tex || { echo "!! Não existe $(RELDIR)/semana-$(S)/main.tex. Crie com: make novo-relatorio S=$(S)"; exit 1; }
	$(call compila,$(RELDIR)/semana-$(S),relatorio-semana-$(S))

assistir: checa-s
	cd $(RELDIR)/semana-$(S) && latexmk -pdf -pvc -interaction=nonstopmode -jobname=relatorio-semana-$(S) main.tex

apresentacao:
	@test -n "$(N)" || { echo "!! Informe a pasta, ex.: make apresentacao N=2026-10-22-pre-projeto"; exit 1; }
	@test -f $(APRDIR)/$(N)/main.tex || { echo "!! Não existe $(APRDIR)/$(N)/main.tex"; exit 1; }
	$(call compila,$(APRDIR)/$(N),$(N))

template:
	$(call compila,$(TEMPLATE),template)

todos:
	@$(foreach d,$(RELATORIOS),$(MAKE) --no-print-directory relatorio S=$(patsubst $(RELDIR)/semana-%,%,$(d)) || exit 1;)
	@$(foreach d,$(APRESENTACOES),$(MAKE) --no-print-directory apresentacao N=$(notdir $(d)) || exit 1;)

limpar:
	@for d in $(TEMPLATE) $(RELATORIOS) $(APRESENTACOES); do (cd $$d && latexmk -c >/dev/null 2>&1; rm -f *.aux *.log *.fls *.fdb_latexmk *.out *.toc *.synctex.gz); done
	@echo "OK: auxiliares removidos"
