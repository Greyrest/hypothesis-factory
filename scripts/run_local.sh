#!/usr/bin/env bash
# Локальный запуск всех сервисов без Docker: venv -> deps -> 5 uvicorn + статика.
# Использование: bash scripts/run_local.sh [--no-llm]
set -euo pipefail
cd "$(dirname "$0")/.."

DATA_DIR_DEFAULT="../Задача 1. Фабрика гипотез/Задача 1"
export DATA_DIR="${DATA_DIR:-$DATA_DIR_DEFAULT}"
export OUTPUT_DIR="${OUTPUT_DIR:-output}"
export LLM_PROVIDER="${LLM_PROVIDER:-anthropic}"
[[ "${1:-}" == "--no-llm" ]] && export LLM_PROVIDER=none

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -r services/ingestion/requirements.txt \
               -r services/knowledge/requirements.txt \
               -r services/generation/requirements.txt \
               -r services/llm/requirements.txt \
               -r services/gateway/requirements.txt
pip -q install -e libs/contracts

export INGESTION_URL=http://localhost:8001 KNOWLEDGE_URL=http://localhost:8002
export GENERATION_URL=http://localhost:8003 LLM_URL=http://localhost:8004

pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT

(cd services/ingestion  && uvicorn app.main:app --port 8001) & pids+=($!)
(cd services/knowledge  && DATA_DIR="$(cd "$DATA_DIR" && pwd)" uvicorn app.main:app --port 8002) & pids+=($!)
(cd services/generation && uvicorn app.main:app --port 8003) & pids+=($!)
(cd services/llm        && uvicorn app.main:app --port 8004) & pids+=($!)
(cd services/gateway    && DATA_DIR="$(cd "$DATA_DIR" && pwd)" OUTPUT_DIR="$(pwd)/../../$OUTPUT_DIR" \
                           uvicorn app.main:app --port 8000) & pids+=($!)
(cd frontend && python3 -m http.server 8088) & pids+=($!)

sleep 2
echo ""
echo "Gateway API:  http://localhost:8000/docs"
echo "Дашборд:      http://localhost:8088"
echo "LLM-провайдер: $LLM_PROVIDER (сменить: LLM_PROVIDER=mock LLM_MODEL=... bash scripts/run_local.sh)"
echo "Ctrl+C — остановить всё."
wait
