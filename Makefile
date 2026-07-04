.PHONY: help venv test up down logs restart-llm openapi local docs clean

VENV := .venv/bin

help:            ## список целей
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

venv:            ## создать venv и поставить зависимости всех сервисов
	python3 -m venv .venv
	$(VENV)/pip -q install -r services/ingestion/requirements.txt \
		-r services/knowledge/requirements.txt \
		-r services/generation/requirements.txt \
		-r services/llm/requirements.txt \
		-r services/gateway/requirements.txt pytest
	$(VENV)/pip -q install -e libs/contracts

test: 	         ## запустить тесты (36 шт.)
	$(VENV)/python -m pytest tests -q

up:              ## собрать и поднять весь стек в Docker
	docker compose up -d --build

down:            ## остановить стек
	docker compose down

logs:            ## логи всех сервисов
	docker compose logs -f

restart-llm:     ## сменить нейронку: make restart-llm LLM_MODEL=...
	docker compose up -d --build llm

openapi:         ## перегенерировать openapi/*.json
	$(VENV)/python scripts/export_openapi.py

local:           ## запуск без Docker (5 uvicorn + статика)
	bash scripts/run_local.sh

clean:           ## убрать кэши и артефакты
	find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null; \
	rm -rf libs/contracts/src/*.egg-info output_test; true
