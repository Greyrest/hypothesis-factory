# Архитектура Hypothesis Factory 2.0

Система разделена по бизнес-ответственности. Межсервисные контракты — HTTP/JSON по OpenAPI 3.1; frontend не импортирует Python-код и обращается только к gateway.

```text
Browser / external client
          │
          ▼
    frontend :80 ───── /docs, /api ─────▶ gateway :8000
                                              │
                    ┌─────────────────────────┼──────────────────────┐
                    ▼                         ▼                      ▼
             ingestion :8000          knowledge :8000       hypothesis :8000
             files → facts            context + graph       generate + rank
                                                                    │
                                                                    ▼
                                                          model-runtime :8000
                                                          Anthropic/OpenAI/
                                                          Ollama/mock
```

## Владение данными

- `gateway` — проекты, метаданные файлов, запуски, результаты и feedback в SQLite.
- `ingestion` — stateless; читает файлы из общего read-mostly volume и возвращает факты/диагностику.
- `knowledge` — stateless; строит retrieval-контекст, граф и трассировку.
- `hypothesis` — stateless; rule-based генерация, объединение LLM-результата и ранжирование.
- `model-runtime` — stateless; единственный сервис с API-ключами внешних моделей.
- `frontend` — React SPA; никакой бизнес-логики или прямых вызовов внутренних сервисов.

## Основной сценарий

1. `POST /api/v1/projects` создает R&D-задачу.
2. `POST /api/v1/projects/{id}/files` сохраняет исходные данные.
3. `PUT /api/v1/projects/{id}/model` задает provider/model и opt-in для LLM.
4. `POST /api/v1/projects/{id}/runs` создает фоновый запуск.
5. Gateway последовательно вызывает ingestion → knowledge → hypothesis → knowledge graph.
6. Клиент опрашивает `GET /api/v1/runs/{id}` и читает гипотезы/граф после `done`.
7. Feedback немедленно вызывает повторное ранжирование без повторного LLM-запроса.

## Надежность и безопасность

- Rule-based генерация остается рабочей при любой ошибке LLM.
- Внешние модели выключены по умолчанию (`HF_ALLOW_EXTERNAL_MODELS=false`).
- Ключи не проходят через gateway и frontend.
- Pydantic-модели запрещают неизвестные поля на write-endpoints.
- Upload ограничен 100 МБ; ingestion разрешает чтение только из общего data volume.
- У каждого сервиса отдельные `/api/v1/health`, `/openapi.json`, `/docs`, `/redoc`.

## Масштабирование

Все вычислительные сервисы stateless и масштабируются репликами. Для production фоновые задачи gateway следует вынести в очередь (Celery/Arq/Kafka), а SQLite заменить PostgreSQL. Публичный API при этом не меняется.

