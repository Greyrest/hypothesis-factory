# Техническое задание: разделение «Фабрики гипотез» на модули

**Версия:** 1.0 (проект) · **Дата:** 2026-07-04 · **Статус:** на согласование

---

## 1. Общие сведения

### 1.1 Система

«Фабрика гипотез» — инструмент автоматической генерации и приоритизации
технологических гипотез снижения потерь цветных металлов (Ni, Cu) с хвостами
флотации. Текущее состояние — прототип-монолит (хакатон Норникеля, «Задача 1.
Фабрика гипотез»): CLI-конвейер на Python, результат — статические HTML-страницы.

### 1.2 Назначение документа

Определить целевую модульную архитектуру и объём работ по рефакторингу
прототипа в клиент-серверное приложение из четырёх модулей:

1. **Backend** — сервер приложения на FastAPI (REST API, оркестрация конвейера,
   хранение результатов и обратной связи).
2. **Frontend** — SPA-дашборд (React + TypeScript).
3. **Модуль LLM** (`hf_llm`) — изолированная работа с языковыми моделями:
   провайдеры, промпты, схемы структурированного вывода, деградация.
4. **Модуль графа знаний** (`hf_kg`) — база знаний (справка, каталог практик,
   правила) + полноценный граф знаний с онтологией, запросами и трассировкой
   «гипотеза → ячейки отчёта».

Дополнительно вводится служебный пакет **`hf_contracts`** (общие Pydantic-модели
и доменные константы), устраняющий дублирование и циклические зависимости.

### 1.3 Уровни требований

- **ОБЯЗАТЕЛЬНО (MUST)** — без выполнения работа не принимается;
- **СЛЕДУЕТ (SHOULD)** — выполняется, если нет веской причины отказаться
  (причина фиксируется письменно);
- **ДОПУСКАЕТСЯ (MAY)** — опционально, на усмотрение исполнителя.

### 1.4 Термины

| Термин | Значение |
|---|---|
| Хвосты | Отвальный продукт флотации; вход системы — отчёт института `Хвосты *.xlsx` |
| Поток | Поток хвостов («Хвосты породные», «Хвосты пирротиновые», сводный блок) |
| Класс крупности | Гранулометрический класс: `+125`, `-125+71`, `+71`, `-71+45`, `-45+20`, `-20+10`, `-10` (мкм) |
| Минеральная форма | Форма нахождения металла: Раскрытый Pnt/Cp, Закрытый Pnt/Cp, Миллерит, Примесь в пирротине, Силикатная форма/Валлериит, Пирит/Другие |
| Извлекаемые формы | Ni: раскрытый/закрытый Pnt + миллерит; Cu: раскрытый/закрытый Pnt/Cp (по справке института) |
| Элемент 28 / 29 | Ni / Cu (по атомным номерам, кодировка отчёта) |
| Сигнал | Диагностический паттерн потерь: `coarse_locked`, `fine_liberated`, `mid_liberated`, `mid_locked`, `coarse_share`, `pyrrhotite` (+ справочный `pyrrhotite_info`, + `tails_recycle` в генераторе) |
| Находка (finding) | Экземпляр сигнала с тоннами, долей потерь, привязкой к классам/формам |
| Ячейка потерь (LossCell) | Кортеж «поток × класс × форма × элемент → тонны»; атом интерпретируемости |
| Карточка гипотезы | Структура JSON гипотезы (§9.2), формат зафиксирован |
| Каталог практик | 26–27 проверенных мероприятий из мозговых штурмов 4 фабрик (docx `Гипотезы*.docx`) с курируемыми метаданными |
| Правила R1–R7 | Доменные правила физики обогащения с привязкой к литературе |
| КБ (KB) | База знаний: чанки справки + каталог + правила + метазаписи литературы |
| ГЗ (KG) | Граф знаний: типизированные узлы и рёбра над данными КБ и результатами конвейера |
| Фабрика (plant) | Обогатительная фабрика из примера: КГМК, НОФ Вкр, НОФ мед, ТОФ |

---

## 2. Текущее состояние (as-is)

### 2.1 Состав репозитория

Все модули лежат в корне, взаимодействие — прямые импорты, запуск — CLI.

| Файл | Ответственность |
|---|---|
| `parse_tailings.py` | Парсер xlsx-отчёта в структуру `{plant, feed, tailings_fact, streams[...], warnings}`; устойчив к `#REF!`, пропускам, 1–2 потокам; восстанавливает извлекаемый металл из форм; помечает сводные блоки (`aggregate`) |
| `diagnose.py` | 6 сигналов диагностики + справочная запись; порог шума `max(10 т, 1% потерь)`; плоская таблица ячеек `_cells()` для расчёта адресуемого металла |
| `knowledge_base.py` | Ингест docx (справка → чанки, гипотезы экспертов → каталог с дедупликацией между фабриками), курируемые метаданные `CATALOG_META` (22 паттерна), правила `DOMAIN_RULES` (R1–R7), метазаписи PDF, лексический `retrieve()` |
| `generate.py` | Rule-based генерация (каталог × сигналы, порог 30 т адресуемого), «пробельные» гипотезы, ранжирование (0.40·эффект + 0.30·реализуемость + 0.20·(1−риск) + 0.10·новизна, поправка фидбэка ±3/голос с потолком ±10, штраф однотипности −5), LLM-усиление (Anthropic SDK, `claude-opus-4-8`, structured output, fallback на rule-based) |
| `export_results.py` | Экспорт JSON / CSV (`;`, utf-8-sig) / Markdown на фабрику |
| `build_web.py` | Генерация статического дашборда: сводка, heatmap-матрица потерь, граф vis-network (CDN), карточки, 👍/👎 в localStorage → скачивание `feedback.json` |
| `pipeline.py` | Оркестрация всего конвейера + leave-one-out оценка покрытия тем эталона (`evaluation.json`) |
| `run.sh` | Бутстрап venv (`openpyxl`, `python-docx`, `anthropic`), запуск, открытие дашборда |

### 2.2 Поток данных

```
Хвосты *.xlsx ─▶ parse_workbook ─▶ diagnose ─▶ generate(kb, llm?) ─▶ export_all ─▶ build_plant_page
Как читать отчет*.docx ┐                            ▲                                    │
Гипотезы*.docx         ├─▶ build_kb ────────────────┘                        index.html ◀┘
Дополнительные PDF     ┘                                       feedback.json (ручной перенос)
                                                                     └─▶ pipeline.py --feedback
```

### 2.3 Проблемы, мотивирующие рефакторинг

| # | Проблема | Где |
|---|---|---|
| P1 | Обратная связь эксперта живёт в localStorage браузера; перенос в конвейер — ручное скачивание `feedback.json` и перезапуск CLI. Нет серверного состояния | `build_web.py:160-186` |
| P2 | Граф знаний существует только как JS-визуализация, строится на лету на странице; невозможны запросы («какие ячейки отчёта обосновывают гипотезу»), нет глобального графа по всем фабрикам, нет графа над каталогом/правилами/источниками | `build_web.py:117-159` |
| P3 | Вызов LLM зашит в `generate.py`: провайдер, модель, промпт, схема неконфигурируемы; нет мока для тестов, нет учёта токенов/стоимости, нет ретраев/таймаутов | `generate.py:316-414` |
| P4 | Дублирование доменных констант: `COARSE/MID/FINE` заданы дважды | `diagnose.py:9-11`, `generate.py:84-86` |
| P5 | Дашборд тянет `vis-network` с CDN unpkg — противоречит требованию локального/оффлайн развёртывания | `build_web.py:20` |
| P6 | Идентификатор фабрики — отображаемое имя с пробелами/кириллицей; артефакты именуются от него. Хрупко для URL и интеграций | `parse_tailings.py:114`, `export_results.py:97` |
| P7 | Пути по умолчанию (`Задача 1. Фабрика гипотез/Задача 1`, `solution/output`) указывают на структуру хакатона вне репозитория | `pipeline.py:76-77`, `run.sh` |
| P8 | Тексты гипотез вставляются в HTML без экранирования | `build_web.py:277-314` |

### 2.4 Инварианты (сохранить ОБЯЗАТЕЛЬНО)

- **I1.** Полная работоспособность без сети и без `ANTHROPIC_API_KEY`
  (rule-based режим) — требование безопасности локального контура.
- **I2.** JSON-схема карточки гипотезы (§9.2) и схемы файлов экспорта
  (JSON/CSV/MD) обратно совместимы с текущими.
- **I3.** Физический контроль: адресуемый металл гипотезы считается как
  объединение ячеек отчёта (без задвоений) и не превышает фактические потери.
- **I4.** Формула приоритета, семантика фидбэка (±3 за голос по категории,
  потолок ±10) и штраф однотипности (−5 за повтор категории) не меняются.
- **I5.** Rule-based прогон 4 фабрик — не более 10 секунд.
- **I6.** Язык данных и интерфейса — русский.
- **I7.** Метрика leave-one-out покрытия тем эталона не деградирует
  (текущий уровень: КГМК 67 %, НОФ Вкр 100 %, НОФ мед 83 %, ТОФ 100 %).

---

## 3. Цели и границы работ

### 3.1 Цели

- **G1.** Выделить четыре модуля с явными контрактами и однонаправленными
  зависимостями; устранить P1–P8.
- **G2.** Backend на FastAPI: загрузка отчётов, запуск конвейера (в т.ч.
  асинхронно при включённом LLM), выдача результатов, серверная обратная связь
  и переранжирование, экспорт файлов.
- **G3.** Frontend-SPA с функциональным паритетом текущего дашборда
  (сводка, находки, матрица потерь, граф, карточки, фидбэк, экспорт).
- **G4.** Модуль LLM: провайдерная абстракция, версионируемые промпты,
  структурированный вывод, мок для тестов, наблюдаемость (токены, латентность),
  гарантированная деградация до rule-based.
- **G5.** Модуль графа знаний: онтология, построение графа из данных конвейера
  и КБ, запросы (подграф, соседи, трассировка), сериализация для фронтенда,
  лексический retrieval; хранение с заделом под Neo4j.
- **G6.** Сохранить CLI-режим «один скрипт» для локального прогона без сервера.

### 3.2 Вне объёма работ (out of scope)

- Аутентификация/авторизация и многопользовательский режим (система работает
  в доверенном локальном контуре; заложить `X-Expert-Id` — см. §5.5.3).
- Развёртывание Neo4j в продуктиве (закладывается только интерфейс хранилища).
- Векторный RAG по PDF-учебникам (бэклог, §15).
- Мультиязычный UI (EN/CN) — бэклог.
- Распознавание png-схем цепей аппаратов — бэклог.
- Очереди типа Celery/Redis — избыточны для локального контура (см. §5.6).

---

## 4. Целевая архитектура (to-be)

### 4.1 Схема модулей

```
┌────────────────────┐         HTTP/JSON (REST, /api/v1)
│  frontend (React)  │ ◀──────────────────────────────────┐
└────────────────────┘                                    │
                                                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  backend (FastAPI)                                               │
│  ┌───────────┐  ┌──────────────────────────────┐  ┌───────────┐  │
│  │ api/      │─▶│ services/ (pipeline, jobs,   │─▶│ domain/   │  │
│  │ routers   │  │ storage, feedback)           │  │ parsing,  │  │
│  └───────────┘  └──────────────────────────────┘  │ diagnosis,│  │
│                                                   │ generation│  │
│                                                   │ ranking,  │  │
│                                                   │ export,   │  │
│                                                   │ evaluation│  │
│                                                   └─────┬─────┘  │
└─────────────────────────────────────────────────────────┼────────┘
                              ┌────────────────┬──────────┤
                              ▼                ▼          ▼
                        ┌──────────┐    ┌──────────┐ ┌──────────────┐
                        │  hf_kg   │    │  hf_llm  │ │ hf_contracts │
                        │ КБ + граф│    │ LLM-слой │ │ модели/конст.│
                        └────┬─────┘    └────┬─────┘ └──────────────┘
                             └───────┬───────┘  (оба зависят только
                                     ▼           от hf_contracts)
                              hf_contracts
```

### 4.2 Матрица зависимостей

| Модуль | Может импортировать | Запрещено импортировать |
|---|---|---|
| `hf_contracts` | стандартная библиотека, pydantic | всё остальное |
| `hf_llm` | `hf_contracts`, anthropic SDK | `hf_kg`, backend, frontend |
| `hf_kg` | `hf_contracts`, networkx, python-docx | `hf_llm`, backend, frontend |
| `backend` | `hf_contracts`, `hf_llm`, `hf_kg`, fastapi, openpyxl, sqlalchemy | frontend |
| `frontend` | — (только HTTP к backend) | — |

Нарушение матрицы — блокер код-ревью. СЛЕДУЕТ закрепить проверкой
(import-linter или ruff-правило) в CI.

### 4.3 Структура репозитория (монорепо, uv workspace)

```
hypothesis-factory/
├── pyproject.toml              # uv workspace: members = backend, packages/*
├── uv.lock
├── Makefile                    # dev, test, lint, demo, build
├── docker-compose.yml
├── .env.example
├── docs/
│   └── TZ_modularization.md    # этот документ
├── data/                       # входные данные (gitignore; примеры кладутся сюда)
├── output/                     # артефакты: результаты, экспорт, граф, БД (gitignore)
├── packages/
│   ├── contracts/              # дистрибутив hf-contracts, пакет hf_contracts
│   │   ├── pyproject.toml
│   │   └── src/hf_contracts/
│   │       ├── models.py       # Pydantic-модели домена (§9)
│   │       ├── constants.py    # COARSE/MID/FINE, FORM_*, RECOVERABLE_FORMS,
│   │       │                   # CATEGORY_RU, UPLIFT, EL_RU (единственный источник)
│   │       └── enums.py        # Element, Signal, Category, HypothesisStatus
│   ├── llm/                    # дистрибутив hf-llm, пакет hf_llm (§7)
│   │   ├── pyproject.toml
│   │   ├── src/hf_llm/
│   │   └── tests/
│   └── kg/                     # дистрибутив hf-kg, пакет hf_kg (§8)
│       ├── pyproject.toml
│       ├── src/hf_kg/
│       └── tests/
├── backend/
│   ├── pyproject.toml          # deps: hf-contracts, hf-llm, hf-kg (workspace)
│   ├── src/app/                # (§5)
│   └── tests/
└── frontend/                   # (§6)
    ├── package.json
    ├── vite.config.ts
    └── src/
```

### 4.4 Технологический стек

| Слой | Выбор | Версии |
|---|---|---|
| Python | CPython | ≥ 3.12 |
| Пакетный менеджер | uv (workspace) | актуальная |
| Backend | FastAPI + Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2 (SQLite) | FastAPI ≥ 0.115 |
| Парсинг | openpyxl, python-docx (переносятся как есть) | текущие |
| Граф | networkx (in-memory) + node-link JSON | ≥ 3.x |
| LLM | anthropic SDK; модель по умолчанию `claude-opus-4-8` | актуальный SDK |
| Frontend | React 18 + TypeScript 5 + Vite, TanStack Query, react-router, vis-network (из бандла, не CDN) | Node 22 LTS |
| Качество | ruff, mypy (strict для packages/*), pytest, eslint, vitest | — |

Замена React на Vue ДОПУСКАЕТСЯ по согласованию — контракт API от этого не
зависит.

---

## 5. Модуль 1: Backend (FastAPI)

### 5.1 Назначение

Единственная точка входа для фронтенда и интеграций. Владеет доменной логикой
конвейера (парсинг, диагностика, генерация, ранжирование, экспорт, оценка),
оркестрацией, хранением. Использует `hf_kg` для знаний/графа и `hf_llm` для
LLM-усиления.

### 5.2 Структура

```
backend/src/app/
├── main.py             # create_app(): маунт роутеров, CORS, lifespan (прогрев КБ)
├── cli.py              # бывш. pipeline.py: команды run / serve (§5.8)
├── config.py           # Settings (pydantic-settings), env-переменные (§12.2)
├── api/
│   ├── deps.py         # DI: Settings, Storage, KnowledgeService, JobRunner
│   └── routers/        # health, reports, runs, jobs, plants, feedback,
│                       # graph, exports, evaluation
├── domain/             # чистые функции, без FastAPI/БД
│   ├── parsing.py      # бывш. parse_tailings.py
│   ├── diagnosis.py    # бывш. diagnose.py
│   ├── generation.py   # rule-based генерация + слияние результатов hf_llm (§7.5)
│   ├── ranking.py      # rank(): формула, фидбэк, диверсификация (инвариант I4)
│   ├── evaluation.py   # leave-one-out (бывш. pipeline.evaluate)
│   └── exporting.py    # бывш. export_results.py
├── services/
│   ├── pipeline.py     # оркестрация: parse → diagnose → generate → export → граф
│   ├── jobs.py         # in-proc исполнитель фоновых задач (§5.6)
│   ├── storage.py      # результаты/артефакты на ФС + метаданные в SQLite
│   └── feedback.py     # голоса, агрегация по категориям, rerank
└── db/
    ├── models.py       # SQLAlchemy: reports, jobs, feedback_votes
    └── session.py
```

Требования к переносу домена:

- **B-1 (MUST).** `parse_tailings.py`, `diagnose.py`, логика генерации и
  ранжирования из `generate.py`, `export_results.py`, `pipeline.evaluate`
  переносятся в `app/domain/*` без изменения алгоритмов (инварианты §2.4).
- **B-2 (MUST).** Все доменные константы импортируются из `hf_contracts`
  (устранение P4); функции принимают/возвращают модели из `hf_contracts`.
- **B-3 (MUST).** `domain/*` не импортирует FastAPI, SQLAlchemy и `services/*`
  (чистые функции — тестируются без сервера).
- **B-4 (MUST).** Слияние LLM-предложений в карточки (маппинг `base_id`,
  добавление evidence «Обоснование Claude», пересчёт scores, сохранение
  невозвращённых черновиков) — в `domain/generation.py`, не в `hf_llm` (§7.5).

### 5.3 Идентификаторы

- **B-5 (MUST).** Вводится `plant_id` — стабильный URL-безопасный слаг
  (нижний регистр, латиница/цифры/дефис). Фиксированная транслитерация для
  известных фабрик: `КГМК → kgmk`, `НОФ Вкр → nof-vkr`, `НОФ мед → nof-med`,
  `ТОФ → tof`; для новых — автотранслитерация + суффикс при коллизии.
  Отображаемое имя (`plant`) хранится отдельно и не участвует в путях API.
  Имена файлов экспорта сохраняют текущий вид (`hypotheses_КГМК.json` и т.п.)
  для обратной совместимости (I2).
- **B-6 (MUST).** `report_id`, `job_id` — UUIDv4.

### 5.4 REST API (контракт)

Базовый префикс `/api/v1`. Формат ошибок — стандартный FastAPI
`{"detail": ...}` с корректными кодами. OpenAPI-схема публикуется на `/docs`,
снапшот `openapi.json` фиксируется в репозитории и проверяется в CI.

#### 5.4.1 Служебные

| Метод и путь | Назначение | Ответ |
|---|---|---|
| `GET /health` | Живость и конфигурация | `{status, version, llm: {enabled, provider, model, available}, kb: {chunks, catalog, rules}}` |

#### 5.4.2 Отчёты

| Метод и путь | Назначение | Тело / параметры | Ответ, коды |
|---|---|---|---|
| `POST /reports` | Загрузка xlsx-отчёта | multipart `file` (xlsx, ≤ 20 МБ) | `201 {report_id, plant, plant_id, warnings[], streams_found}`; `400` не xlsx / превышен размер; `422` не распознан ни один поток хвостов |
| `GET /reports` | Список загруженных отчётов | — | `200 [{report_id, plant_id, plant, filename, uploaded_at, has_result}]` |
| `GET /reports/{report_id}` | Разобранная структура отчёта | — | `200 ParsedReport (§9.1)`; `404` |

Загрузка выполняет только парсинг (быстро, синхронно) и возвращает
предупреждения парсера (`#REF!` восстановлен и т.п.). Файл сохраняется в
`DATA_DIR/uploads/`, разобранный JSON — в хранилище (§5.5).

- **B-7 (SHOULD).** При старте сервер сканирует `DATA_DIR` по текущим маскам
  (`Пример */Хвосты*.xlsx`) и регистрирует найденные отчёты — паритет с
  текущим CLI-поведением.

#### 5.4.3 Запуск конвейера и задачи

| Метод и путь | Назначение | Тело / параметры | Ответ, коды |
|---|---|---|---|
| `POST /runs` | Запуск конвейера | `{report_id?: uuid, scope?: "all", use_llm?: bool}` — ровно одно из `report_id`/`scope` | `202 {job_id}`; `404` нет отчёта; `409` уже выполняется задача по тому же отчёту |
| `GET /jobs/{job_id}` | Статус задачи | — | `200 {job_id, status: queued\|running\|done\|error, progress: {stage, plant_id?}, error?, started_at?, finished_at?, result: [{plant_id}]?}`; `404` |

- **B-8 (MUST).** `use_llm` по умолчанию = `settings.llm_enabled`. При
  недоступности LLM задача НЕ падает: конвейер завершает работу rule-based,
  поле `engine` результата отражает фактический движок (инвариант I1).
- **B-9 (MUST).** Повторный запуск для того же отчёта перезаписывает результат
  (идемпотентность по `report_id`).
- **B-10 (MUST).** LLM никогда не вызывается в горячем пути HTTP-запроса —
  только внутри фоновой задачи.
- Фронтенд опрашивает `GET /jobs/{id}` с интервалом 1–2 с. WebSocket не
  требуется (MAY — бэклог).

#### 5.4.4 Результаты по фабрикам

| Метод и путь | Назначение | Параметры | Ответ, коды |
|---|---|---|---|
| `GET /plants` | Список фабрик с результатами | — | `200 [{plant_id, plant, engine, summary (§9.1), n_hypotheses, top_title, updated_at}]` |
| `GET /plants/{plant_id}` | Полный результат | — | `200 PlantResult (§9.3)`; `404` (с подсказкой запустить `/runs`) |
| `GET /plants/{plant_id}/matrix` | Данные heatmap-матрицы потерь | `element=ni\|cu` (MAY) | `200 {streams: [{name, pyrrhotite, totals, classes: [{cls, share_pct, forms: {форма: {ni_t, cu_t}}, recoverable}]}]}` — сводные (`aggregate`) потоки исключены |
| `GET /plants/{plant_id}/graph` | Подграф знаний для визуализации | `view=losses\|full` (default `losses`) | `200 VisGraph (§8.6)`; `404` |
| `GET /plants/{plant_id}/hypotheses/{hyp_id}/trace` | Трассировка гипотезы до ячеек отчёта | — | `200 VisGraph`; `404` |
| `GET /evaluation` | Leave-one-out против эталона | — | `200` содержимое `evaluation.json`; `404` если эталонные docx отсутствуют в `DATA_DIR` |

#### 5.4.5 Обратная связь и переранжирование

| Метод и путь | Назначение | Тело | Ответ, коды |
|---|---|---|---|
| `PUT /plants/{plant_id}/feedback/{hyp_id}` | Голос по гипотезе | `{vote: "up" \| "down" \| null}` (null — снять голос) | `204`; `404` |
| `GET /plants/{plant_id}/feedback` | Текущие голоса (для отрисовки) | — | `200 {votes: {hyp_id: "up"\|"down"}, by_category: {CAT: {up, down}}}` |
| `POST /plants/{plant_id}/rerank` | Пересчёт приоритетов с учётом накопленных голосов (без повторного LLM) | — | `200 PlantResult` (обновлённые `scores.priority`, `rank`, `feedback_adj`) |
| `POST /feedback/import` (MAY) | Импорт legacy `feedback.json` (`{CAT: {up, down}}`) | файл/JSON | `204` |

- **B-11 (MUST).** Голоса хранятся на сервере per-hypothesis
  (`plant_id, hyp_id, vote, updated_at`); агрегация в категорные счётчики —
  в `services/feedback.py` по текущей семантике `build_web.exportFeedback`
  (голос гипотезы учитывается в каждой её категории).
- **B-12 (MUST).** `rerank` вызывает `domain/ranking.rank()` с теми же
  формулами (I4) и персистит обновлённый результат.

#### 5.4.6 Экспорт

| Метод и путь | Назначение | Параметры | Ответ |
|---|---|---|---|
| `GET /plants/{plant_id}/export` | Скачивание файла | `format=json\|csv\|md` | `200`, `Content-Disposition: attachment`, имена и схемы файлов — как сейчас (I2); `422` неизвестный формат |

Экспорт `format=html` (самодостаточная статическая страница, бывш.
`build_web.py`) — ДОПУСКАЕТСЯ, бэклог §15.

### 5.5 Хранение

- **B-13 (MUST).** Артефакты — файлы на ФС в `OUTPUT_DIR` (совместимость и
  простота локального контура): `results/{plant_id}.json` (PlantResult),
  `parsed/{report_id}.json`, `web-export/` (файлы §5.4.6 генерируются на лету
  либо кэшируются), `graph/{plant_id}.json` и `graph/global.json` (§8.5).
- **B-14 (MUST).** Метаданные — SQLite (`OUTPUT_DIR/app.db`, SQLAlchemy 2):

  | Таблица | Поля |
  |---|---|
  | `reports` | `id (uuid PK)`, `plant_id`, `plant`, `filename`, `uploaded_at`, `parsed_path` |
  | `jobs` | `id (uuid PK)`, `report_id?`, `scope?`, `status`, `use_llm`, `engine?`, `error?`, `created_at`, `started_at?`, `finished_at?` |
  | `feedback_votes` | `plant_id`, `hyp_id`, `vote`, `expert_id?`, `updated_at`; PK `(plant_id, hyp_id, expert_id)` |

- **B-15 (MAY).** `expert_id` берётся из заголовка `X-Expert-Id` (default
  `"local"`) — задел на многопользовательность без реализации auth.
- Внешние СУБД (Postgres и пр.) НЕ вводятся.

### 5.6 Фоновые задачи

- **B-16 (MUST).** In-proc исполнитель: `ThreadPoolExecutor(max_workers=1)`
  (конвейер синхронный, CPU/IO-bound), статусы и прогресс — в таблице `jobs`.
  Никаких Celery/Redis/брокеров.
- **B-17 (MUST).** Этапы прогресса: `parsing → diagnosing → generating →
  llm_enhancing (опц.) → exporting → building_graph → done`; текущий этап и
  фабрика видны в `GET /jobs/{id}`.
- **B-18 (SHOULD).** Задачи, оставшиеся `running` после рестарта сервера,
  помечаются `error: "interrupted by restart"` при старте.

### 5.7 Конфигурация

Через `pydantic-settings` (env / `.env`), полный список — §12.2. Секреты
(`ANTHROPIC_API_KEY`) не логируются и не попадают в `/health`.

### 5.8 CLI-режим (сохранение G6)

- **B-19 (MUST).** `app/cli.py` предоставляет команды:
  - `hf run [--data DIR] [--out DIR] [--no-llm] [--feedback FILE]` —
    полный прогон, эквивалент текущего `pipeline.py`, использует те же
    `services/pipeline.py` (никакой второй реализации конвейера);
  - `hf serve [--host] [--port]` — запуск uvicorn.
- **B-20 (MUST).** `run.sh` адаптируется: bootstrap через uv, запуск `hf run`,
  открытие фронтенда/статического экспорта. Консольный вывод прогона
  (сводки по фабрикам, топ-3, оценка) сохраняется.

---

## 6. Модуль 2: Frontend (SPA)

### 6.1 Стек и принципы

React 18 + TypeScript + Vite; данные — TanStack Query; маршрутизация —
react-router; граф — **vis-network из npm-бандла** (устранение P5, тот же
внешний вид). Стили — CSS-модули или Tailwind с сохранением текущей палитры
(`--blue #0077C8`, `--dark #0B2D4E`, `--bg #F4F7FA`, статусные цвета) и
светлой темы. Все подписи — русские, тексты секций переносятся из текущего
дашборда.

- **F-1 (MUST).** Типы API генерируются из OpenAPI (`openapi-typescript`);
  ручное дублирование типов запрещено.
- **F-2 (MUST).** Никаких обращений к внешним CDN; сборка работает оффлайн.
- **F-3 (MUST).** Пользовательские тексты рендерятся как текст (React
  экранирует по умолчанию; `dangerouslySetInnerHTML` запрещён) — устранение P8.

### 6.2 Маршруты и страницы

| Маршрут | Страница | Содержимое |
|---|---|---|
| `/` | Главная | Карточки фабрик (`GET /plants`: потери Ni/Cu, % извлекаемого, число гипотез, гипотеза №1), блок «Как это работает», зона загрузки отчёта (drag&drop xlsx → `POST /reports`), кнопка «Запустить конвейер» (`POST /runs`), бейдж состояния LLM из `/health` |
| `/plants/:plantId` | Дашборд фабрики | Секции §6.3 |
| `/plants/:plantId?job=:id` | — | Оверлей прогресса задачи (поллинг `GET /jobs/:id`, отображение этапа §5.6) |
| `*` | 404 | Ссылка на главную |

### 6.3 Дашборд фабрики (функциональный паритет + серверный фидбэк)

1. **Сводка** — 4 карточки: потери Ni, потери Cu (с извлекаемыми т и %),
   число гипотез/находок, потенциал топ-3 (т Ni). Данные: `GET /plants/{id}`.
2. **Диагностика** — список находок с тоннами, долей потерь, деталями;
   справочные — с пометкой «(справочно)».
3. **Матрица потерь** — heatmap «формы × классы» по потокам и элементам,
   зелёная кромка у извлекаемых форм. Данные: `GET /plants/{id}/matrix`.
4. **Граф знаний** — vis-network; переключатель вида `losses | full` (§8.6);
   клик по узлу — панель деталей; клик по гипотезе — действие «Показать
   обоснование» → подсветка трассы (`GET .../trace`). Размер узла ~ тонны,
   группы цветов как сейчас (классы — синие, диагнозы — оранжевые,
   гипотезы — зелёные).
5. **Карточки гипотез** — разворачиваемые, №1 раскрыта; бейдж приоритета,
   теги категории/оборудования/статуса (`практика экспертов`, `генерация по
   правилам`, `доработано Claude`, `новая (Claude)`); секции: гипотеза,
   механизм, обоснование с источниками, KPI с допущением, шкалы
   (эффект/реализуемость/новизна/риск/поправка эксперта), риски, дорожная
   карта.
6. **Обратная связь** — 👍/👎 на карточке → `PUT .../feedback/{hyp_id}`
   (optimistic UI); кнопка «Переранжировать» → `POST .../rerank` → плавное
   обновление порядка. Пояснение механики — как в текущем тулбаре.
7. **Экспорт** — кнопки ⬇ JSON / CSV / MD (`GET .../export?format=`);
   PDF — через печать MD/страницы браузером (как сейчас).

- **F-4 (MUST).** При `engine = rule-based` дашборд полнофункционален и
  явно показывает движок генерации (I1).
- **F-5 (SHOULD).** Состояния загрузки/ошибок для каждой секции; ошибка API
  не роняет страницу целиком.

### 6.4 Структура

```
frontend/src/
├── api/        # client.ts (fetch-обёртка), types.gen.ts (из OpenAPI), hooks/
├── app/        # router, QueryClientProvider, layout (шапка-градиент)
├── pages/      # HomePage, PlantPage, NotFoundPage
├── features/
│   ├── upload/           # загрузка отчёта + предупреждения парсера
│   ├── run/              # запуск, прогресс job
│   ├── summary/          # карточки сводки
│   ├── findings/         # список находок
│   ├── loss-matrix/      # heatmap
│   ├── knowledge-graph/  # обёртка vis-network, панель деталей, trace
│   ├── hypotheses/       # карточки, голосование, rerank
│   └── exports/          # тулбар экспорта
└── shared/     # ui-примитивы, форматирование чисел (пробел-разделитель, «—»)
```

---

## 7. Модуль 3: LLM (`hf_llm`)

### 7.1 Назначение и зона ответственности

Вся работа с языковыми моделями: конфигурация, провайдеры, промпты, схемы
структурированного вывода, вызов с ретраями/таймаутом, валидация ответа,
телеметрия, кэш. Модуль **не знает** про полную структуру карточки гипотезы,
граф, БД и HTTP — принимает и возвращает узкие DTO из `hf_contracts`.

### 7.2 Структура

```
packages/llm/src/hf_llm/
├── __init__.py         # публичный API: enhance_hypotheses, LLMConfig,
│                       # get_provider, LLMUnavailable, LLMBadOutput
├── config.py           # LLMConfig
├── providers/
│   ├── base.py         # class LLMProvider(Protocol)
│   ├── anthropic.py    # AnthropicProvider (перенос из generate.llm_enhance)
│   └── mock.py         # MockProvider: фикстурные ответы для тестов/демо
├── prompts/
│   ├── registry.py     # реестр промптов по (use_case, version)
│   └── enhance_v1.py   # system-промпт «технолог-обогатитель» (перенос as-is)
├── schemas.py          # HYP_SCHEMA (JSON Schema структурированного вывода)
├── usecases/
│   └── enhance.py      # enhance_hypotheses(...) — единственный use case v1
└── cache.py            # опциональный кэш ответов (SHOULD)
```

### 7.3 Публичный интерфейс

```python
# hf_llm/config.py
class LLMConfig(BaseModel):
    provider: Literal["anthropic", "mock"] = "anthropic"
    model: str = "claude-opus-4-8"
    max_tokens: int = 16000
    thinking: Literal["adaptive", "off"] = "adaptive"
    timeout_s: float = 120.0
    retries: int = 1              # повторов при сетевых ошибках
    enabled: bool = True          # False => enhance_hypotheses всегда None
    cache_dir: Path | None = None # None => кэш выключен

# hf_llm/providers/base.py
class LLMProvider(Protocol):
    def available(self) -> bool: ...
    def complete_structured(
        self, *, system: str, user: str, schema: dict, max_tokens: int,
    ) -> StructuredCompletion: ...   # .data: dict, .usage: LLMUsage

# hf_llm/usecases/enhance.py
def enhance_hypotheses(
    ctx: EnhanceContext,          # из hf_contracts: диагностика (сводка,
                                  # находки ≤14), черновики ≤12 (id, title,
                                  # category, addressable_t, evidence-факты ≤2),
                                  # каталог (заголовки+источники), правила
    config: LLMConfig,
) -> EnhanceResult | None:        # None => вызывающий остаётся на rule-based
    ...

class EnhanceResult(BaseModel):
    items: list[LLMHypothesisSuggestion]  # base_id|None, title, hypothesis,
                                          # mechanism, category, risks[],
                                          # roadmap[], novelty, feasibility,
                                          # risk (1..5), rationale
    usage: LLMUsage                       # input/output tokens, latency_ms,
                                          # model, estimated_cost_usd
```

### 7.4 Требования

- **L-1 (MUST).** Перенести текущее поведение `generate.llm_enhance`
  (`generate.py:316-365`) без изменения смысла: тот же system-промпт, та же
  структура контекста и те же лимиты (`findings[:14]`, `drafts[:12]`), та же
  JSON-схема, structured output через `output_config json_schema`,
  `stop_reason == "refusal"` → `None`.
- **L-2 (MUST).** Любая ошибка (нет ключа, сеть, таймаут, квота, невалидный
  JSON, refusal) → `None` + структурированный лог с типом ошибки. Исключения
  наружу не выбрасываются; конвейер не падает (I1).
- **L-3 (MUST).** Ответ провайдера валидируется Pydantic-моделью
  `EnhanceResult` до возврата: оценки приводятся к диапазону 1–5, `category`
  вне enum → предложение отбрасывается с логом (защита от галлюцинаций схемы).
- **L-4 (MUST).** `MockProvider` возвращает детерминированные фикстуры
  (полировка одного черновика + одна новая гипотеза) — для юнит-тестов слияния
  и демо без ключа.
- **L-5 (MUST).** Телеметрия каждого вызова: модель, версия промпта, токены
  in/out, латентность, исход (`ok | fallback:<причина>`); лог локальный.
- **L-6 (SHOULD).** Кэш ответов: ключ `sha256(model + prompt_version +
  canonical_json(ctx))` → файл в `cache_dir`; включается конфигом. Повторный
  прогон того же отчёта не тратит токены.
- **L-7 (SHOULD).** Промпты версионируются (`enhance_v1`, `enhance_v2`, …);
  версия фиксируется в телеметрии и в `engine`-строке результата.
- **L-8 (MAY).** Точка расширения: use case `translate` (мультиязычность из
  бэклога README) добавляется рядом с `enhance` без изменения публичного API.

### 7.5 Граница с backend

`hf_llm` возвращает только валидированные «предложения». Слияние их в карточки
(поиск черновика по `base_id`, dict-merge, evidence «Обоснование Claude (по
данным отчёта)», обнуление `addressable_t` для новых гипотез, сохранение
невозвращённых черновиков, финальный `rank()`) — доменная логика
`backend app/domain/generation.py` (B-4). Это позволяет тестировать слияние
с MockProvider и менять провайдера, не трогая домен.

---

## 8. Модуль 4: Граф знаний (`hf_kg`)

### 8.1 Назначение и зона ответственности

1. **База знаний** (перенос `knowledge_base.py`): ингест docx/pdf → чанки,
   каталог практик с курируемыми метаданными, правила R1–R7, лексический
   retrieval.
2. **Граф знаний** (новое, устранение P2): онтология, построение
   типизированного графа из данных конвейера и КБ, запросы, трассировка,
   сериализация для vis-network.

Модуль не знает про HTTP, БД backend'а и LLM.

### 8.2 Структура

```
packages/kg/src/hf_kg/
├── __init__.py       # KnowledgeBase, KnowledgeGraph, GraphStore, VisGraph
├── kb/
│   ├── ingest.py     # бывш. build_kb: справка → чанки, Гипотезы*.docx →
│   │                 # каталог (дедуп между фабриками), правила → чанки,
│   │                 # PDF → метазаписи; _read_docx_paragraphs
│   ├── catalog_meta.py  # CATALOG_META (22 паттерна) + DEFAULT_META
│   └── rules.py      # DOMAIN_RULES R1–R7
├── retrieval.py      # бывш. retrieve(): лексический скоринг, top_k
├── ontology.py       # NodeType/EdgeType, схемы атрибутов, генерация id узлов
├── builder.py        # build_plant_graph(parsed, diagnosis, hypotheses, kb)
│                     # + build_global_graph(kb, plants)
├── store.py          # GraphStore (Protocol) + NetworkXStore (node-link JSON)
├── query.py          # subgraph, neighbors, trace
└── serializers.py    # to_vis(GraphView) -> VisGraph
```

### 8.3 Онтология

Идентификаторы узлов — детерминированные строки `«тип:ключ»` (стабильны между
прогонами при неизменных входных данных).

**Узлы:**

| Тип | id (шаблон) | Ключевые атрибуты | Источник данных |
|---|---|---|---|
| `Plant` | `plant:{plant_id}` | name | parse |
| `Stream` | `stream:{plant_id}:{n}` | name, smt, ni_t, cu_t, pyrrhotite, aggregate | parse |
| `SizeClass` | `cls:{stream}:{cls}` | cls, share_pct | parse |
| `LossCell` | `cell:{stream}:{cls}:{form}:{el}` | form, el, tons | diagnose.`_cells` |
| `Finding` | `finding:{finding.id}` | signal, element, tons, share_of_losses_pct, detail, informational | diagnose |
| `Rule` | `rule:{R1..R7}` | title, text, signal, categories, source | kb.rules |
| `Practice` | `practice:{cat-XX}` | title, source, plants, categories, signals, equipment, feasibility, risk, novelty, capex | kb.catalog |
| `Hypothesis` | `hyp:{hypothesis.id}` | title, status, priority, impact_t, category_ru | generate |
| `Category` | `cat:{GRIND..AUTO}` | code, name_ru | contracts |
| `Equipment` | `eq:{slug}` | name | catalog meta |
| `Source` | `src:{slug}` | name, kind (guide/literature/brainstorm) | kb |

**Рёбра:**

| Ребро | От → К | Смысл |
|---|---|---|
| `HAS_STREAM` | Plant → Stream | состав фабрики |
| `HAS_CLASS` | Stream → SizeClass | грансостав потока |
| `HAS_LOSS` | SizeClass → LossCell | потери в ячейке |
| `SIGNALS` | LossCell → Finding | ячейка участвует в находке (по предикатам `SIGNAL_CELLS`) |
| `EXPLAINED_BY` | Finding → Rule | правило с тем же `signal` |
| `ADDRESSED_BY` | Finding → Hypothesis | по `hypothesis.finding_ids` |
| `BASED_ON` | Hypothesis → Practice | для `status=catalog` |
| `IN_CATEGORY` | Hypothesis/Practice/Rule → Category | категоризация |
| `USES` | Practice → Equipment | оборудование |
| `PROVEN_AT` | Practice → Plant | где практика подтверждена (`plants`) |
| `CITES` | Hypothesis/Rule → Source | источники/литература |

- **K-1 (MUST).** Онтология реализуется на networkx `MultiDiGraph`; типы и
  обязательные атрибуты валидируются при добавлении (ошибочный узел — исключение
  на этапе построения, не молчаливый пропуск).
- **K-2 (MUST).** Текущий граф дашборда (класс → диагноз → гипотеза,
  `build_web.py:117-159`) воспроизводится как **вид** `losses` над этой
  онтологией: `SizeClass → Finding → Hypothesis` (без informational-находок),
  размер узла — тонны/impact_t (те же правила, что в JS сейчас).

### 8.4 Построение

- **K-3 (MUST).** `build_plant_graph(parsed, diagnosis, result, kb)` строит
  граф фабрики после каждого прогона конвейера; сводные (`aggregate`) потоки
  исключаются (как в `diagnose._cells`).
- **K-4 (MUST).** `build_global_graph(kb, plant_graphs)` — объединённый граф:
  каталог/правила/категории/источники — общие узлы, к ним пристыкованы
  подграфы фабрик. Практика с `plants: [НОФ, ТОФ]` связана `PROVEN_AT` с обеими
  фабриками — это делает явными «аналогии» (перенос практик между фабриками).

### 8.5 Хранение

- **K-5 (MUST).** `GraphStore` — протокол `save(graph_id, G) / load(graph_id) /
  exists`; реализация v1 — `NetworkXStore`: node-link JSON
  (`networkx.node_link_data`) в `OUTPUT_DIR/graph/{plant_id}.json` и
  `graph/global.json`.
- **K-6 (MAY).** Реализация `Neo4jStore` за тем же протоколом — бэклог;
  в v1 не делается, но публичный API модуля не должен ей противоречить.

### 8.6 Запросы и сериализация

```python
class KnowledgeGraph:
    def subgraph(self, *, plant_id: str, view: Literal["losses", "full"]) -> GraphView
    def neighbors(self, node_id: str, depth: int = 1) -> GraphView
    def trace(self, hyp_node_id: str) -> GraphView
    # trace: Hypothesis → Finding(ADDRESSED_BY⁻¹) → LossCell(SIGNALS⁻¹)
    #        → SizeClass → Stream (+ Rule, Practice, Source гипотезы) —
    #        полная цепочка интерпретируемости «гипотеза → цифры отчёта»

def to_vis(view: GraphView) -> VisGraph:
    # {nodes: [{id, label, group, value, payload?}],
    #  edges: [{from, to, arrows?}]} — формат, который сейчас собирает JS
```

- **K-7 (MUST).** `view=losses` даёт визуально тот же граф, что текущий
  дашборд (группы `cls`/`finding`/`hyp`, перенос заголовков, payload для
  панели деталей).
- **K-8 (MUST).** `trace()` возвращает связный подграф; для гипотез
  `status=llm-new` (без `finding_ids`) — узел гипотезы + категория + источники,
  без ячеек (честно показываем отсутствие количественной привязки).
- **K-9 (MUST).** `retrieval.retrieve(kb, terms, kinds, top_k)` переносится
  без изменения скоринга (пересечение термов + бонус правилам) — его использует
  `domain/generation.py` для evidence.
- **K-10 (SHOULD).** `KnowledgeBase.load(data_dir)` кэширует результат ингеста
  (docx неизменны в течение работы сервера); инвалидация — по mtime файлов.

---

## 9. Сквозные контракты данных (`hf_contracts`)

Все модели — Pydantic v2, `model_config = ConfigDict(extra="forbid")`.
Ниже — ключевые; полный список составляется на этапе 0 из фактических структур.

### 9.1 Домены и перечисления

```python
Element = Literal["ni", "cu"]
Signal = Literal["coarse_locked", "fine_liberated", "mid_liberated",
                 "mid_locked", "coarse_share", "pyrrhotite",
                 "pyrrhotite_info", "tails_recycle"]
Category = Literal["GRIND", "CLASSIFY", "REGRIND", "FLOT",
                   "REAGENT", "CRUSH", "TAILS", "AUTO"]
HypothesisStatus = Literal["catalog", "generated", "llm", "llm-new"]

# constants.py — единственный источник (устранение P4):
# COARSE, MID, FINE; FORM_ALIASES; RECOVERABLE_FORMS; CATEGORY_RU; UPLIFT;
# ROADMAP; RISKS; EL_RU; CLS_ORDER; FORM_ORDER; EVAL_TOPICS

class Summary(BaseModel):
    losses_ni_t: float; losses_cu_t: float
    recoverable_ni_t: float; recoverable_cu_t: float
    recoverable_ni_pct: float; recoverable_cu_pct: float

class ParsedReport(BaseModel):     # результат parse_workbook, поля as-is
    source_file: str; plant: str; plant_id: str
    feed: dict; tailings_fact: dict | None
    streams: list[Stream]          # Stream/SizeClassEntry повторяют текущие ключи
    warnings: list[str]
```

### 9.2 Карточка гипотезы (формат зафиксирован, I2)

```python
class Evidence(BaseModel):
    source: str; fact: str

class ExpectedEffect(BaseModel):
    addressable_t: dict[Element, float]
    uplift_pct: tuple[int, int]
    kpi_delta_t: dict[Element, tuple[float, float]]
    kpi: str; assumption: str

class Scores(BaseModel):
    feasibility: int; novelty: int; risk: int          # 1..5
    impact_t: float
    impact_norm: float | None = None
    priority: float | None = None
    feedback_adj: int = 0; diversity_adj: int = 0

class Hypothesis(BaseModel):
    id: str; rank: int | None = None
    title: str; hypothesis: str
    categories: list[Category]; category_ru: str
    equipment: str; streams: list[str]
    mechanism: str; evidence: list[Evidence]
    expected_effect: ExpectedEffect; scores: Scores
    risks: list[str]; roadmap: list[str]
    status: HypothesisStatus
    sources: list[str]; matched_signals: list[str]; finding_ids: list[str]
```

### 9.3 Прочие

```python
class Finding(BaseModel):
    id: str; signal: Signal; element: Element; element_ru: str
    stream: str; title: str
    tons: float; share_of_losses_pct: float
    classes: list[str]; forms: list[str]; detail: str
    informational: bool = False

class PlantResult(BaseModel):
    plant: str; plant_id: str; engine: str
    summary: Summary
    hypotheses: list[Hypothesis]      # топ-12, как сейчас
    findings: list[Finding]

# DTO для hf_llm (§7.3): EnhanceContext, LLMHypothesisSuggestion,
#                        EnhanceResult, LLMUsage
# DTO для hf_kg (§8.6):  GraphView, VisGraph, VisNode, VisEdge
# API-модели (§5.4):     JobStatus, ReportInfo, FeedbackState
```

---

## 10. Нефункциональные требования

| # | Требование |
|---|---|
| N-1 (MUST) | Оффлайн-режим: без `ANTHROPIC_API_KEY` и без сети все функции, кроме LLM-усиления, работают полностью; UI явно показывает движок (I1) |
| N-2 (MUST) | Производительность: rule-based прогон 4 фабрик ≤ 10 с (I5); parse+diagnose+generate одной фабрики ≤ 3 с; чтение готового результата `GET /plants/{id}` p95 ≤ 200 мс; job с LLM ≤ 3 мин (таймаут 120 с + 1 ретрай) |
| N-3 (MUST) | Данные не покидают локальный контур, кроме явно включённого LLM-вызова (только контекст из §7.3, без исходных файлов); флаг `HF_LLM_ENABLED` выключает любые внешние вызовы |
| N-4 (MUST) | Никаких внешних CDN/шрифтов/аналитики во фронтенде (P5, F-2) |
| N-5 (MUST) | Ограничение загрузки: xlsx ≤ 20 МБ, проверка расширения и успешного парсинга; загруженные файлы хранятся только в `DATA_DIR/uploads` |
| N-6 (MUST) | Логирование: структурированные логи (JSON) backend'а; отдельный канал телеметрии LLM (L-5); секреты в логи не попадают |
| N-7 (MUST) | CORS: разрешённые origin'ы — из `HF_CORS_ORIGINS` (dev: `http://localhost:5173`) |
| N-8 (MUST) | Типизация: mypy strict для `packages/*`, базовый для backend; ruff во всём Python-коде; eslint+tsc во фронтенде; всё в CI |
| N-9 (SHOULD) | Кириллица в именах файлов экспорта сохраняется (I2), но во внутренних путях/ключах используются `plant_id`-слаги (B-5) |
| N-10 (SHOULD) | Один процесс backend обслуживает локальную команду экспертов; горизонтальное масштабирование не требуется |

---

## 11. Тестирование и критерии приёмки

### 11.1 Golden-тесты (регресс миграции) — MUST

До начала работ фиксируются эталоны: результаты текущего кода на 4 примерах
в режиме `--no-llm` (`hypotheses_*.json`, `hypotheses_*.csv`, `report_*.md`,
`evaluation.json`). После каждого этапа миграции новый код обязан давать
семантически эквивалентный результат (сравнение JSON по полям; допускается
стабильная пересортировка ключей). Расхождение — блокер этапа.

### 11.2 Модульные тесты — MUST

| Область | Что проверяется |
|---|---|
| `domain/parsing` | 4 фикстурных xlsx; восстановление `#REF!` из форм (кейс КГМК); 1 и 2 потока; детект сводного блока; warnings |
| `domain/diagnosis` | пороги шума `max(10 т, 1 %)`; все сигналы; informational-находки |
| `domain/generation` | `_addressable`: объединение ячеек без задвоений; **свойство: адресуемый металл ≤ фактических потерь потока (I3)**; порог 30 т; gap-гипотезы |
| `domain/ranking` | детерминированность; формула; фидбэк ±3/потолок ±10; штраф −5; пересорт после rerank |
| `hf_llm` | happy-path с MockProvider; невалидный JSON → None; таймаут → None; refusal → None; category вне enum → предложение отброшено; кэш-попадание |
| слияние LLM (domain) | merge по `base_id`; сохранение невозвращённых черновиков; evidence «Обоснование Claude»; новая гипотеза с нулевым addressable |
| `hf_kg` | число узлов/рёбер по типам на фикстурах; `trace()` от гипотезы доходит до LossCell; view `losses` эквивалентен JS-графу (снапшот VisGraph); retrieve() — снапшот выдачи |
| `services/feedback` | агрегация голосов по категориям = семантике `exportFeedback` |

### 11.3 Контрактные и интеграционные — MUST

- API-тесты (httpx + TestClient): все эндпоинты §5.4, коды ошибок,
  сценарий «upload → run → poll → result → feedback → rerank → export».
- Снапшот `openapi.json` в CI (несогласованное изменение контракта — фейл).
- Frontend: vitest + msw для хуков API; e2e smoke (Playwright) — SHOULD:
  открыть главную → фабрика → проголосовать → переранжировать → скачать CSV.

### 11.4 Приёмочные сценарии (демонстрация заказчику)

1. **Оффлайн**: сервер без ключа → загрузка `Хвосты КГМК.xlsx` → в ответе
   предупреждения о восстановлении `#REF!` → run → дашборд полный,
   `engine: rule-based`.
2. **С LLM**: ключ задан → run → `engine: rule-based + claude-opus-4-8`,
   на карточках статусы «доработано Claude» / «новая (Claude)»; при обрыве
   сети результат всё равно готов (rule-based, лог fallback).
3. **Фидбэк**: 👍 гипотезе категории CLASSIFY → «Переранжировать» → приоритеты
   категории выросли на +3, порядок обновился; голос виден после перезагрузки
   страницы (серверное хранение).
4. **Интерпретируемость**: клик «Показать обоснование» на гипотезе №1 →
   подсвечена цепочка до конкретных ячеек «поток × класс × форма» с тоннами.
5. **Экспорт**: JSON/CSV/MD скачиваются, схема и имена файлов прежние;
   `evaluation` показывает покрытие не ниже I7.
6. **CLI**: `hf run --no-llm --data ./data --out ./output` на чистой машине
   отрабатывает ≤ 10 с и печатает сводку, как текущий `pipeline.py`.

### 11.5 Метрики качества кода — SHOULD

Покрытие тестами: `packages/*` ≥ 85 %, `backend/app/domain` ≥ 85 %,
`backend/app` в целом ≥ 70 %.

---

## 12. Развёртывание

### 12.1 Docker Compose — MUST

| Сервис | Образ | Порты | Примечания |
|---|---|---|---|
| `backend` | python:3.12-slim + uv sync | 8000 | volumes: `./data:/data`, `./output:/output`; healthcheck `GET /api/v1/health` |
| `frontend` | multi-stage: node:22 build → nginx:alpine | 80 | статика + proxy `/api` → backend; работает без интернета |

`docker compose up` поднимает систему целиком; образы собираются оффлайн после
первичного скачивания зависимостей.

### 12.2 Переменные окружения

| Переменная | Default | Назначение |
|---|---|---|
| `HF_DATA_DIR` | `./data` | входные данные (xlsx, docx, pdf, uploads) |
| `HF_OUTPUT_DIR` | `./output` | результаты, экспорт, графы, SQLite |
| `ANTHROPIC_API_KEY` | — | ключ LLM (секрет; отсутствие ≠ ошибка) |
| `HF_LLM_ENABLED` | `true`, если задан ключ | глобальный выключатель LLM |
| `HF_LLM_PROVIDER` | `anthropic` | `anthropic \| mock` |
| `HF_LLM_MODEL` | `claude-opus-4-8` | модель |
| `HF_LLM_MAX_TOKENS` | `16000` | лимит ответа |
| `HF_LLM_TIMEOUT_S` | `120` | таймаут вызова |
| `HF_LLM_CACHE` | `false` | кэш ответов LLM (L-6) |
| `HF_CORS_ORIGINS` | `http://localhost:5173` | CORS |
| `HF_HOST` / `HF_PORT` | `0.0.0.0` / `8000` | bind |

### 12.3 Dev-режим и Makefile — MUST

```
make dev      # uvicorn --reload (8000) + vite dev (5173, proxy /api)
make test     # pytest по всем пакетам + vitest
make lint     # ruff + mypy + eslint + tsc --noEmit
make demo     # hf run --data ./data --out ./output (аналог run.sh)
make golden   # регенерация golden-эталонов (только осознанно)
```

---

## 13. План работ (этапы миграции)

Каждый этап заканчивается зелёным CI и выполненными golden-тестами (§11.1).
Порядок выбран так, чтобы конвейер оставался рабочим после каждого этапа.

| Этап | Содержание | Definition of Done | Оценка |
|---|---|---|---|
| **0. Скелет** | Монорепо: uv workspace, `hf_contracts` (модели+константы из §9), перенос текущих файлов в `backend/src/app/domain` с минимальной правкой импортов, фиксация golden-эталонов, CI (ruff/mypy/pytest) | `hf run` (бывш. pipeline.py) даёт результат, эквивалентный эталону; константы — только из contracts | 1–2 дн |
| **1. `hf_kg`** | Перенос `knowledge_base.py` (ингест, каталог, правила, retrieve); онтология, builder, store, query, `to_vis`; конвейер переключён на пакет | Golden ok; юнит-тесты §11.2 (kg); `to_vis(losses)` соответствует снапшоту текущего JS-графа | 3 дн |
| **2. `hf_llm`** | Перенос `llm_enhance` → провайдер/промпт/схема/use case; MockProvider; слияние — в `domain/generation.py`; телеметрия | `--no-llm` эквивалентен эталону; тест слияния на моке детерминирован; fallback-кейсы покрыты | 2 дн |
| **3. Backend API** | FastAPI: роутеры §5.4, сервисы, jobs (§5.6), SQLite (§5.5), фидбэк+rerank, экспорт; CLI `hf run/serve` поверх тех же сервисов; адаптация `run.sh` | Контрактные тесты зелёные; сценарий upload→run→result→feedback→rerank→export проходит; openapi.json зафиксирован | 4–5 дн |
| **4. Frontend** | SPA §6: все секции дашборда, загрузка, прогресс, серверный фидбэк, trace-подсветка; vis-network из бандла; генерация типов из OpenAPI | Чек-лист паритета со статическим дашбордом закрыт; e2e smoke; оффлайн-сборка без CDN | 5–6 дн |
| **5. Поставка** | docker-compose, README (запуск, конфигурация, архитектура), прогон приёмочных сценариев §11.4; решение по `build_web.py` (удалить; html-экспорт — в бэклог) | `docker compose up` работает на чистой машине; все 6 сценариев §11.4 продемонстрированы | 2 дн |

**Итого:** ~17–20 человеко-дней (1 разработчик, 3.5–4 недели с запасом).

---

## 14. Риски

| Риск | Влияние | Митигация |
|---|---|---|
| Изменение формата xlsx-отчётов института | Парсер перестаёт находить потоки | Парсер изолирован в `domain/parsing`; фикстуры 4 форматов; `422` с внятным сообщением; warnings доходят до UI |
| Изменения API Anthropic / модели | Отказ LLM-усиления | Провайдерная абстракция (L-1), гарантированный fallback (L-2), MockProvider для регресса |
| Расхождение поведения при переносе (тихая порча чисел) | Потеря доверия к инструменту | Golden-тесты после каждого этапа (§11.1); свойство I3 закреплено property-тестом |
| Двойная поддержка CLI и API | Дрейф логики | Единственная реализация конвейера в `services/pipeline.py`, CLI — тонкая обёртка (B-19) |
| Кириллица/пробелы в идентификаторах | Битые URL, проблемы интеграций | `plant_id`-слаги (B-5); имена файлов экспорта — legacy-совместимые |
| Просачивание данных наружу при включённом LLM | Безопасность контура | Наружу уходит только контекст §7.3; `HF_LLM_ENABLED=false` отключает всё; факт включения виден в UI и `/health` (N-3) |
| Разрастание графа (много фабрик) | Медленный рендер | Виды `losses`/`full`, подграф по фабрике; глобальный граф — по запросу |

---

## 15. Бэклог развития (вне объёма, задел учтён)

1. Векторный RAG по PDF-учебникам (страницы → эмбеддинги) — расширение
   `hf_kg.retrieval` вторым бэкендом за тем же интерфейсом.
2. `Neo4jStore` для `GraphStore` (K-6) + Cypher-запросы для аналитики.
3. Статический HTML-экспорт дашборда (`format=html`) для передачи «одним
   файлом» — реинкарнация `build_web.py` поверх SPA-сборки.
4. Мультиязычность (EN/CN) — use case `translate` в `hf_llm` (L-8) + i18n UI.
5. Калибровка UPLIFT на исторических парах «мероприятие → эффект».
6. Распознавание png-схем цепей аппаратов → узлы Equipment в графе.
7. Многопользовательский режим: auth поверх `X-Expert-Id` (B-15).
8. WebSocket/SSE для прогресса задач вместо поллинга.

---

## Приложение А. Соответствие «проблема → требование»

| Проблема (§2.3) | Закрывается |
|---|---|
| P1 localStorage-фидбэк | §5.4.5, B-11, B-12 |
| P2 граф только как картинка | §8 целиком, K-1…K-8, эндпоинты graph/trace |
| P3 LLM зашит в generate.py | §7, L-1…L-7, B-4, B-10 |
| P4 дубли констант | B-2, §9.1 constants.py |
| P5 CDN vis-network | F-2, N-4 |
| P6 кириллические id | B-5, N-9 |
| P7 пути хакатона | §12.2 (`HF_DATA_DIR`/`HF_OUTPUT_DIR`), B-7 |
| P8 неэкранированный HTML | F-3 |
