# Hypothesis Factory 2.0

Микросервисная платформа для генерации и приоритизации проверяемых R&D-гипотез на основе данных, источников, ограничений и экспертного feedback.

## Быстрый запуск

Требования: Docker Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

- UI: <http://localhost:3000>
- Swagger: <http://localhost:3000/docs>
- OpenAPI: <http://localhost:3000/openapi.json>
- ReDoc: <http://localhost:3000/redoc>

По умолчанию система полностью работает в локальном rule-based режиме. Внешние LLM-вызовы являются явным opt-in:

```dotenv
HF_ALLOW_EXTERNAL_MODELS=true
ANTHROPIC_API_KEY=...
# или OPENAI_API_KEY=...
```

Ollama выбирается в UI как отдельный provider и не требует разрешения внешних моделей.

## Сервисы

| Сервис | Ответственность |
|---|---|
| `gateway` | публичный API, проекты, upload, jobs, SQLite, feedback, export |
| `ingestion` | PDF/DOCX/TXT/CSV/XLSX/JSON → факты и доменная диагностика |
| `knowledge` | retrieval-контекст, технологический каталог, граф и trace |
| `hypothesis` | rule-based генерация, LLM merge, scoring/ranking |
| `model-runtime` | Anthropic, OpenAI, Ollama и mock; изоляция API-ключей |
| `frontend` | React/TypeScript SPA для полного пользовательского сценария |

Подробная схема: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). OpenAPI каждого сервиса хранится в [docs/openapi](docs/openapi).

## Публичный API

```text
GET  /api/v1/health
GET  /api/v1/domains
GET  /api/v1/models
POST /api/v1/projects
GET  /api/v1/projects/{id}
POST /api/v1/projects/{id}/files
PUT  /api/v1/projects/{id}/model
POST /api/v1/projects/{id}/runs
GET  /api/v1/runs/{id}
GET  /api/v1/projects/{id}/hypotheses
GET  /api/v1/hypotheses/{id}
PUT  /api/v1/hypotheses/{id}/feedback
POST /api/v1/projects/{id}/rerank
GET  /api/v1/projects/{id}/graph
GET  /api/v1/hypotheses/{id}/trace
GET  /api/v1/projects/{id}/export?format=json|csv|md
```

## Разработка и проверки

Целевой runtime — Python 3.12 и Node 24.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v

cd frontend
npm ci
npm run build

# обновить зафиксированные спецификации
PYTHONPATH=.:packages/contracts/src:packages/llm/src:packages/kg/src:packages/domains/src \
  ../.venv/bin/python ../scripts/export_openapi.py
```

## Сохраненная доменная логика

Проверенные алгоритмы MVP не удалены: `parse_tailings.py`, `diagnose.py`, `knowledge_base.py` и `generate.py` используются профильными сервисами для домена `mining_flotation`. Пакеты `hf_contracts`, `hf_kg`, `hf_llm`, `hf_domains` остаются общими библиотеками без HTTP- и UI-зависимостей.

Статический прежний dashboard в `output/web` сохранен как reference-результат; новый frontend работает с живым API.
