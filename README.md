# AskData — NL→SQL аналитическая платформа

Self-service аналитика на естественном языке для Drivee. Конкурс МПИТ25/26.

**Демо:** https://mpit.aguzarty.ru

---

## Быстрый старт (локальная разработка)

### 1. Переменные окружения

```bash
cp .env.example .env
# Вставьте CLAUDE_API_KEY (или GIGACHAT_CREDENTIALS) и SECRET_KEY
```

### 2. Сборка и запуск

```bash
sg docker -c "docker-compose2 -f docker-compose.prod.yml --env-file .env up -d --build"
```

Или через стандартный Docker Compose:

```bash
docker compose --env-file .env up -d --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger: http://localhost:8000/docs

### 3. Локальная разработка без Docker

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn askdata.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### 4. Тесты

```bash
cd backend
uv run pytest tests/ -v
```

---

## Демо-пользователи (DEMO_MODE=1)

| Логин   | Пароль    | Роль    |
|---------|-----------|---------|
| viewer  | viewer123 | Viewer  |
| manager | manager123| Analyst |
| admin   | admin123  | Admin   |

---

## LLM провайдеры

| `LLM_PROVIDER` | Что нужно | Рекомендация |
|----------------|-----------|--------------|
| `claude`       | `CLAUDE_API_KEY` | ✅ Лучшее качество SQL |
| `gigachat`     | `GIGACHAT_CREDENTIALS` | Альтернатива |
| `local`        | `LOCAL_LLM_URL` + модель | Для локального Qwen |

---

## Переменные окружения

| Переменная | Описание | Дефолт |
|-----------|---------|--------|
| `LLM_PROVIDER` | Провайдер LLM: `claude` / `gigachat` / `local` | `claude` |
| `CLAUDE_API_KEY` | Ключ Anthropic API | — |
| `CLAUDE_MODEL` | ID модели Claude | `claude-sonnet-4-6` |
| `GIGACHAT_CREDENTIALS` | Ключ GigaChat (base64) | — |
| `LOCAL_LLM_URL` | URL OpenAI-compatible LLM | — |
| `SECRET_KEY` | JWT secret (сгенерировать!) | — |
| `DEMO_MODE` | `1` = создаются демо-пользователи | `1` |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота | — |

---

## Архитектура

```
Пользователь → Chat UI (React)
  → POST /api/v1/query {text, mode, session_id}
  → [Easy mode] validator_agent → проверка метрики/периода
  → Router: cosine embedding ≥0.65 → шаблон, иначе LLM
  → 15 SQL-шаблонов | Claude / GigaChat / Qwen
  → sqlglot AST validator → asyncpg executor (read-only)
  → Visualizer (bar / line / stacked / kpi) → Confidence SC
  → Response {sql, data, chart, confidence, interpretation}
```

## SQL-шаблоны (15 штук)

TopNByGroup, BottomNByGroup, AvgByGroup, Timeseries, AggregateByPeriod, PeriodComparison, Distribution, RunningTotal, HourlyDistribution, CancellationRate, StatusSplit, PickupTime, FunnelDropoff, **AnomalyDetection**, **RetentionCohort**

## Ключевые endpoints

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/api/v1/auth/login` | Аутентификация |
| POST | `/api/v1/query` | NL→SQL запрос |
| GET | `/api/v1/query/templates` | Список шаблонов |
| GET | `/api/v1/health` | Статус сервиса |
| GET/POST | `/api/v1/reports` | Отчёты |
| GET/POST | `/api/v1/schedules` | Расписания |
| GET/POST | `/api/v1/admin/rag` | RAG few-shot store |
| GET | `/api/v1/admin/audit` | Журнал аудита |

## Guardrails (7 уровней)

1. Read-only DB user (`askdata_reader`)
2. sqlglot AST allowlist (только SELECT)
3. Readonly transaction
4. 30-секундный таймаут
5. Auto LIMIT 1000
6. Audit log каждого запроса
7. Rate limiting 30 req/min

## Стек

- **Backend:** Python 3.11, FastAPI, asyncpg, sqlglot, sentence-transformers
- **Frontend:** React 18, TypeScript, Vite, Tailwind, Zustand, Recharts
- **LLM:** Claude Sonnet 4.6 (Anthropic) / GigaChat / Qwen2.5-Coder-7b
- **DB:** PostgreSQL 16 (данные Drivee) + SQLite (мета)
- **Infra:** Docker Compose, Nginx, Let's Encrypt
