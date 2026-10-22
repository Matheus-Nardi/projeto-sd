# =============================================================
# Build dos relatórios LaTeX do projeto.
# Rode `make` (ou `make ajuda`) na raiz do repositório para ver os comandos.
# =============================================================

LATEXMK   := latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error -silent
RELDIR    := relatorios
TEMPLATE  := $(RELDIR)/template

# Todas as pastas de relatório que têm um main.tex (exceto o template)
RELATORIOS := $(filter-out $(TEMPLATE),$(patsubst %/main.tex,%,$(wildcard $(RELDIR)/*/main.tex)))
SEMANAS    := $(filter $(RELDIR)/semana-%,$(RELATORIOS))
PREPROJETO := $(RELDIR)/pre-projeto

# Apresentações em HTML: exportadas para PDF com o Chrome/Chromium sem janela
APRDIR     := apresentacoes
CHROME     := $(shell command -v google-chrome-stable || command -v google-chrome || command -v chromium || command -v chromium-browser)

# compila(pasta, nome-do-pdf): gera <pasta>/<nome>.pdf e apaga os auxiliares
define compila
	@echo ">> Compilando $(1)/main.tex -> $(1)/$(2).pdf"
	@cd $(1) && $(LATEXMK) -jobname=$(2) main.tex >/dev/null 2>&1 \
		|| { echo "!! Erro de compilação:"; grep -A2 -E '^(!|.*:[0-9]+:)' $(2).log | head -15; \
		     echo "!! Log completo: $(1)/$(2).log"; exit 1; }
	@cd $(1) && latexmk -c -jobname=$(2) main.tex >/dev/null 2>&1
	@echo "OK: $(1)/$(2).pdf"
endef

.PHONY: ajuda relatorio novo-relatorio pre-projeto todos template assistir limpar checa-s slides

ajuda:
	@echo "Uso (sempre na raiz do repositório):"
	@echo ""
	@echo "  make novo-relatorio S=01      cria relatorios/semana-01/ a partir do template"
	@echo "  make relatorio S=01           gera relatorios/semana-01/relatorio-semana-01.pdf"
	@echo "  make pre-projeto              gera relatorios/pre-projeto/pre-projeto.pdf"
	@echo "  make assistir S=01            recompila sozinho a cada vez que um .tex é salvo"
	@echo "  make todos                    gera todos os relatórios"
	@echo "  make template                 gera o PDF do template (para conferir a capa)"
	@echo "  make limpar                   apaga arquivos auxiliares do LaTeX"
	@echo "  make slides A=pre-projeto     gera apresentacoes/pre-projeto/pre-projeto.pdf (precisa do Chrome ou Chromium)"
	@echo ""
	@echo "Relatórios encontrados: $(or $(RELATORIOS),nenhum)"

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

slides:
	@test -n "$(A)" || { echo "!! Informe a apresentação, ex.: make slides A=pre-projeto"; exit 1; }
	@test -f $(APRDIR)/$(A)/index.html || { echo "!! Não existe $(APRDIR)/$(A)/index.html"; exit 1; }
	@test -n "$(CHROME)" || { echo "!! Instale o Google Chrome ou o Chromium para exportar o PDF"; exit 1; }
	@echo ">> Exportando $(APRDIR)/$(A)/index.html -> $(APRDIR)/$(A)/$(A).pdf"
	@"$(CHROME)" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=3000 \
		--print-to-pdf="$(CURDIR)/$(APRDIR)/$(A)/$(A).pdf" "file://$(CURDIR)/$(APRDIR)/$(A)/index.html" >/dev/null 2>&1
	@echo "OK: $(APRDIR)/$(A)/$(A).pdf"

pre-projeto:
	$(call compila,$(PREPROJETO),pre-projeto)

template:
	$(call compila,$(TEMPLATE),template)

todos:
	@$(if $(wildcard $(PREPROJETO)/main.tex),$(MAKE) --no-print-directory pre-projeto || exit 1;)
	@$(foreach d,$(SEMANAS),$(MAKE) --no-print-directory relatorio S=$(patsubst $(RELDIR)/semana-%,%,$(d)) || exit 1;)

limpar:
	@for d in $(TEMPLATE) $(RELATORIOS); do (cd $$d && latexmk -c >/dev/null 2>&1; rm -f *.aux *.log *.fls *.fdb_latexmk *.out *.toc *.synctex.gz); done
	@echo "OK: auxiliares removidos"
