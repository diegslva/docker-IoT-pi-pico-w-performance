.DEFAULT_GOAL := help

## --- App ---

dev: ## Roda servidor FastAPI (verifica porta, mata processo anterior se necessario)
	uv run python -m server

## --- Pico W ---

deploy: ## Copia codigo para o Pico W (CIRCUITPY drive)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 deploy

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

firewall: ## Cria regra de firewall para o servidor
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 firewall

## --- Ajuda ---

help: ## Mostra esta ajuda
	@powershell -NoProfile -Command "Get-Content Makefile | Select-String '^\w+:.*##' | ForEach-Object { $$line = $$_.Line; $$parts = $$line -split '##'; $$cmd = ($$parts[0] -replace ':.*','').Trim(); $$desc = $$parts[1].Trim(); Write-Host ('  {0,-16} {1}' -f $$cmd, $$desc) }"

.PHONY: dev deploy lint lint-fix format format-check test check firewall help
