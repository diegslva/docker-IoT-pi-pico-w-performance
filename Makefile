.DEFAULT_GOAL := help

## --- App ---

dev: ## Roda servidor FastAPI (verifica porta, mata processo anterior se necessario)
	uv run python -m server

## --- Pico W ---

flash: ## Instala CircuitPython 10.1.4 no Pico 2 W (BOOTSEL mode)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 flash

flash-9: ## Instala CircuitPython 9.2.1 no Pico 2 W (teste de regressao HSTX)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "$$env:CP_VERSION='9.2.1'; & scripts/dev.ps1 flash"

deploy: ## Copia codigo para o Pico W (CIRCUITPY drive)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 deploy

test-dvi: ## Deploya teste minimo do PiCowBell HSTX (listras coloridas, sem rede)
	powershell -NoProfile -Command "Get-Volume | Where-Object { $$_.FileSystemLabel -eq 'CIRCUITPY' } | ForEach-Object { Copy-Item pico\test_dvi.py ($$_.DriveLetter + ':\code.py') -Force; Write-Host ('Test DVI deployed to ' + $$_.DriveLetter + ':') -ForegroundColor Green }"

all: flash deploy dev ## Pipeline completo: flash CircuitPython + deploy code + start server

setup: flash deploy ## Setup inicial sem subir servidor (flash + deploy)

## --- Qualidade ---

lint: ## Roda ruff linter
	uv run ruff check server/ tests/

lint-fix: ## Corrige problemas de lint
	uv run ruff check --fix server/ tests/

format: ## Formata codigo
	uv run ruff format server/ tests/

format-check: ## Verifica formatacao
	uv run ruff format --check server/ tests/

test: ## Roda testes
	uv run pytest

check: format-check lint ## Roda todas as verificacoes

## --- Infra ---

up: ## Sobe Prometheus + Grafana (monitoring stack)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 up

down: ## Para monitoring stack
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 down

restart: ## Reinicia monitoring stack
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 restart

nuke: ## Remove tudo (containers + volumes)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 nuke

ps: ## Mostra status dos containers
	docker compose ps

logs: ## Mostra logs dos containers
	docker compose logs -f --tail=50

firewall: ## Cria regra de firewall para o servidor
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 firewall

## --- Ajuda ---

help: ## Mostra esta ajuda
	@powershell -NoProfile -Command "Get-Content Makefile | Select-String '^\w+:.*##' | ForEach-Object { $$line = $$_.Line; $$parts = $$line -split '##'; $$cmd = ($$parts[0] -replace ':.*','').Trim(); $$desc = $$parts[1].Trim(); Write-Host ('  {0,-16} {1}' -f $$cmd, $$desc) }"

.PHONY: dev flash flash-9 deploy test-dvi all setup lint lint-fix format format-check test check up down restart nuke ps logs firewall help
