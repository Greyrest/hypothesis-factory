#!/usr/bin/env bash
# Фабрика гипотез — запуск одним скриптом.
# Использование: bash solution/run.sh [--no-llm]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "Создаю виртуальное окружение…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet openpyxl python-docx anthropic
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ℹ ANTHROPIC_API_KEY не задан — генерация в rule-based режиме (LLM-усиление отключено)."
fi

.venv/bin/python solution/pipeline.py "$@"

INDEX="solution/output/web/index.html"
if [ -f "$INDEX" ] && command -v open >/dev/null; then
  open "$INDEX"
fi
