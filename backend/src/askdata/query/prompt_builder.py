import asyncio
import time
from datetime import date
from askdata.semantic.loader import get_semantic_layer
from askdata.db.target import get_schema

_schema_cache: list | None = None
_schema_cache_ts: float = 0.0
_SCHEMA_TTL = 300  # 5 minutes


async def _get_cached_schema() -> list:
    global _schema_cache, _schema_cache_ts
    if _schema_cache is None or time.time() - _schema_cache_ts > _SCHEMA_TTL:
        _schema_cache = await get_schema()
        _schema_cache_ts = time.time()
    return _schema_cache


SYSTEM_PROMPT = """Ты — эксперт по PostgreSQL и аналитике данных такси-сервиса Drivee.
Твоя задача — преобразовать вопрос пользователя на русском языке в корректный SQL-запрос.

ПРАВИЛА (строго соблюдать):
1. Только SELECT. Никаких INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE.
2. Используй только таблицы и колонки из предоставленной схемы.
3. Добавляй LIMIT 1000 если LIMIT не указан явно.
4. Сегодняшняя дата: {today}.
5. Даты вычисляй относительно CURRENT_DATE/NOW().
6. Отвечай ТОЛЬКО SQL-запросом без объяснений, без markdown блоков (```sql), без лишних слов.
7. SQL должен быть синтаксически корректным для PostgreSQL.
8. Группируй результаты там, где это логично.
9. Сортируй по основной метрике DESC если не указано иное.

МОДЕЛЬ ДАННЫХ (три таблицы):

1. anonymized_incity_orders — детальные события заказов и тендеров
   - Одна строка = один тендер (предложение конкретному водителю)
   - Один заказ (order_id) → несколько строк (разные водители-кандидаты)
   - ВСЕГДА используй COUNT(DISTINCT order_id) для подсчёта заказов
   - Завершённая поездка: status_tender = 'done' (ровно одна такая строка на заказ)
   - Отменённый заказ: status_order = 'cancel'
   - tender_id может быть NULL (заказ без конкретного тендера)
   - Несколько городов (city_id), города: LEFT JOIN cities c ON c.city_id = o.city_id

2. passenger_daily_stats — дневные метрики пассажиров (одна строка = пассажир × город × день)
   - Поля: city_id, user_id, order_date_part (DATE), user_reg_date (DATE)
   - Счётчики: orders_count, orders_cnt_with_tenders, orders_cnt_accepted, rides_count
   - Времена: rides_time_sum_seconds, online_time_sum_seconds
   - client_cancel_after_accept — отмены после принятия
   - Для анализа активности пассажиров, новых регистраций, retention

3. driver_daily_stats — дневные метрики водителей (одна строка = водитель × город × день)
   - Поля: city_id, driver_id, tender_date_part (DATE), driver_reg_date (DATE)
   - Счётчики: orders, orders_cnt_with_tenders, orders_cnt_accepted, rides_count
   - Времена: rides_time_sum_seconds, online_time_sum_seconds
   - client_cancel_after_accept — отмены пассажиром после принятия водителем
   - Для анализа эффективности водителей, онлайн-времени, acceptance rate

СВЯЗИ: passenger_daily_stats.user_id = anonymized_incity_orders.user_id
        driver_daily_stats.driver_id = anonymized_incity_orders.driver_id

КОГДА ИСПОЛЬЗОВАТЬ КАКУЮ ТАБЛИЦУ:
- Детальный анализ по событиям, временным меткам, ценам → anonymized_incity_orders
- Анализ активности пассажиров по дням, когорты пассажиров → passenger_daily_stats
- Анализ активности водителей, онлайн-время, acceptance rate → driver_daily_stats
- Новые регистрации водителей → driver_daily_stats GROUP BY driver_reg_date (первая дата)

СЛОЖНЫЕ ЗАПРОСЫ — используй соответствующие конструкции:
- Пороговые условия (более N, больше X, свыше Y) → HAVING
- "Самый популярный / пиковый / топ-1" → ORDER BY ... DESC LIMIT 1 (или LIMIT N)
- "В какое время / во сколько / когда чаще всего" → EXTRACT(HOUR FROM timestamp) + GROUP BY + ORDER BY count DESC
- Процент/доля среди группы → оконная функция OVER()
- Водители/клиенты с условием по количеству → подзапрос или HAVING
- Сравнение периодов → UNION ALL с явными метками
- Удержание/повторные заказы → CTE с first_order + activity join
- Нарастающий итог → оконная функция SUM(...) OVER (ORDER BY day)
- Acceptance rate → SUM(orders_cnt_accepted) / NULLIF(SUM(orders_cnt_with_tenders), 0)
- Новые регистрации → GROUP BY driver_reg_date или user_reg_date с COUNT(DISTINCT id)
"""

FEW_SHOT_EXAMPLES = """
ПРИМЕРЫ (вопрос → SQL):

=== anonymized_incity_orders (алиас o) ===
Одна строка = один тендер. Один order_id → несколько строк.
COUNT(DISTINCT order_id) для заказов. status_tender='done' для поездок. status_order='cancel' для отмен.
Города: LEFT JOIN cities c ON c.city_id = o.city_id

Покажи отмены по городам за прошлую неделю
SELECT COALESCE(c.name, o.city_id::text) AS city, COUNT(DISTINCT CASE WHEN o.clientcancel_timestamp IS NOT NULL THEN o.order_id END) AS client_cancels, COUNT(DISTINCT CASE WHEN o.drivercancel_timestamp IS NOT NULL THEN o.order_id END) AS driver_cancels, COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) AS total_cancels FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' AND o.order_timestamp < DATE_TRUNC('week', NOW()) GROUP BY o.city_id, c.name ORDER BY total_cancels DESC LIMIT 1000

Сколько поездок было за последние 7 дней
SELECT COUNT(DISTINCT order_id) AS trips_count FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= NOW() - INTERVAL '7 days'

Выручка за вчера
SELECT SUM(price_order_local) AS revenue FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('day', NOW()) - INTERVAL '1 day' AND o.order_timestamp < DATE_TRUNC('day', NOW())

Топ 5 водителей по числу поездок за месяц
SELECT o.driver_id, COUNT(DISTINCT order_id) AS trips_count FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('month', NOW()) GROUP BY o.driver_id ORDER BY trips_count DESC LIMIT 5

Средний чек по городам
SELECT COALESCE(c.name, o.city_id::text) AS city, ROUND(AVG(price_order_local)::numeric, 2) AS avg_check FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id WHERE o.status_tender = 'done' GROUP BY o.city_id, c.name ORDER BY avg_check DESC LIMIT 1000

Процент отмен за 30 дней
SELECT ROUND(100.0 * COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS cancel_rate_pct FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '30 days'

Динамика выручки за последние 30 дней
SELECT DATE_TRUNC('day', o.order_timestamp)::date AS period_date, SUM(price_order_local) AS revenue FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= NOW() - INTERVAL '30 days' GROUP BY 1 ORDER BY 1 LIMIT 1000

Сравни заказы этой и прошлой недели
SELECT 'эта неделя' AS period, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) UNION ALL SELECT 'прошлая неделя' AS period, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' AND o.order_timestamp < DATE_TRUNC('week', NOW())

Заказы по часам за сегодня
SELECT EXTRACT(HOUR FROM o.order_timestamp)::int AS hour, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('day', NOW()) GROUP BY 1 ORDER BY 1 LIMIT 24

Во сколько чаще всего начинают заказы за последнюю неделю
SELECT EXTRACT(HOUR FROM o.order_timestamp)::int AS hour, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' AND o.order_timestamp < DATE_TRUNC('week', NOW()) GROUP BY 1 ORDER BY orders_count DESC LIMIT 5

Распределение заказов по статусам
SELECT status_order, COUNT(DISTINCT order_id) AS cnt, ROUND(COUNT(DISTINCT order_id) * 100.0 / SUM(COUNT(DISTINCT order_id)) OVER(), 1) AS pct FROM anonymized_incity_orders o GROUP BY status_order ORDER BY cnt DESC LIMIT 1000

Средняя длительность поездки
SELECT ROUND((AVG(duration_in_seconds) / 60.0)::numeric, 1) AS avg_duration_min FROM anonymized_incity_orders o WHERE o.status_tender = 'done'

Среднее время подачи водителя по городам
SELECT COALESCE(c.name, o.city_id::text) AS city, ROUND((AVG(EXTRACT(EPOCH FROM (driverarrived_timestamp - driveraccept_timestamp))) / 60.0)::numeric, 1) AS avg_pickup_min FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id WHERE o.driverarrived_timestamp IS NOT NULL AND o.driveraccept_timestamp IS NOT NULL GROUP BY o.city_id, c.name ORDER BY avg_pickup_min ASC LIMIT 1000

Топ 10 водителей по выручке за неделю
SELECT o.driver_id, SUM(price_order_local) AS revenue FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('week', NOW()) GROUP BY o.driver_id ORDER BY revenue DESC LIMIT 10

Воронка заказов за 7 дней
SELECT COUNT(DISTINCT order_id) AS created, COUNT(DISTINCT CASE WHEN driveraccept_timestamp IS NOT NULL THEN order_id END) AS accepted, COUNT(DISTINCT CASE WHEN driverarrived_timestamp IS NOT NULL THEN order_id END) AS arrived, COUNT(DISTINCT CASE WHEN driverstarttheride_timestamp IS NOT NULL THEN order_id END) AS started, COUNT(DISTINCT CASE WHEN driverdone_timestamp IS NOT NULL THEN order_id END) AS completed FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '7 days'

Сколько уникальных клиентов было в этом месяце
SELECT COUNT(DISTINCT user_id) AS unique_clients FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('month', NOW())

Сколько активных водителей на прошлой неделе
SELECT COUNT(DISTINCT driver_id) AS active_drivers FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' AND o.order_timestamp < DATE_TRUNC('week', NOW())

Средняя дистанция поездки по дням недели
SELECT EXTRACT(DOW FROM o.order_timestamp)::int AS day_of_week, ROUND((AVG(distance_in_meters) / 1000.0)::numeric, 2) AS avg_distance_km FROM anonymized_incity_orders o WHERE o.status_tender = 'done' GROUP BY 1 ORDER BY 1 LIMIT 7

Отмены клиентом за 30 дней
SELECT COUNT(DISTINCT order_id) AS client_cancels FROM anonymized_incity_orders o WHERE o.clientcancel_timestamp IS NOT NULL AND o.order_timestamp >= NOW() - INTERVAL '30 days'

Сколько водителей отменило более 5 заказов за последний месяц
SELECT driver_id, COUNT(DISTINCT order_id) AS cancel_count FROM anonymized_incity_orders o WHERE o.drivercancel_timestamp IS NOT NULL AND o.order_timestamp >= DATE_TRUNC('month', NOW()) GROUP BY driver_id HAVING COUNT(DISTINCT order_id) > 5 ORDER BY cancel_count DESC LIMIT 1000

Водители с конверсией ниже 50% за последние 30 дней
SELECT driver_id, COUNT(DISTINCT CASE WHEN status_tender = 'done' THEN order_id END) AS completed, COUNT(DISTINCT order_id) AS total, ROUND(100.0 * COUNT(DISTINCT CASE WHEN status_tender = 'done' THEN order_id END) / NULLIF(COUNT(DISTINCT order_id), 0), 1) AS conversion_pct FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '30 days' GROUP BY driver_id HAVING COUNT(DISTINCT order_id) >= 5 AND ROUND(100.0 * COUNT(DISTINCT CASE WHEN status_tender = 'done' THEN order_id END) / NULLIF(COUNT(DISTINCT order_id), 0), 1) < 50 ORDER BY conversion_pct ASC LIMIT 100

Клиенты которые сделали более 3 заказов за этот месяц
SELECT user_id, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= DATE_TRUNC('month', NOW()) GROUP BY user_id HAVING COUNT(DISTINCT order_id) > 3 ORDER BY orders_count DESC LIMIT 1000

Самый загруженный день недели по заказам за последние 90 дней
SELECT TO_CHAR(o.order_timestamp, 'Day') AS day_name, EXTRACT(DOW FROM o.order_timestamp)::int AS dow, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '90 days' GROUP BY dow, day_name ORDER BY orders_count DESC LIMIT 7

Город с наибольшей выручкой за прошлый месяц
SELECT COALESCE(c.name, o.city_id::text) AS city, SUM(price_order_local) AS revenue FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('month', NOW()) - INTERVAL '1 month' AND o.order_timestamp < DATE_TRUNC('month', NOW()) GROUP BY o.city_id, c.name ORDER BY revenue DESC LIMIT 1

Сколько заказов в день в среднем за последние 30 дней
SELECT ROUND(COUNT(DISTINCT order_id)::numeric / 30, 1) AS avg_orders_per_day FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '30 days'

Выручка по дням недели за последние 4 недели
SELECT EXTRACT(DOW FROM o.order_timestamp)::int AS dow, TO_CHAR(o.order_timestamp, 'Day') AS day_name, SUM(price_order_local) AS revenue, COUNT(DISTINCT order_id) AS orders FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= NOW() - INTERVAL '4 weeks' GROUP BY dow, day_name ORDER BY dow LIMIT 7

Водители с более чем 100 поездками за месяц
SELECT driver_id, COUNT(DISTINCT order_id) AS trips FROM anonymized_incity_orders o WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('month', NOW()) GROUP BY driver_id HAVING COUNT(DISTINCT order_id) > 100 ORDER BY trips DESC LIMIT 1000

Среднее число заказов на водителя по городам за последнюю неделю
SELECT COALESCE(c.name, o.city_id::text) AS city, ROUND(COUNT(DISTINCT o.order_id)::numeric / NULLIF(COUNT(DISTINCT o.driver_id), 0), 1) AS avg_orders_per_driver FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' AND o.order_timestamp < DATE_TRUNC('week', NOW()) GROUP BY o.city_id, c.name ORDER BY avg_orders_per_driver DESC LIMIT 1000

Процент повторных клиентов за последние 30 дней
WITH orders AS (SELECT user_id, COUNT(DISTINCT order_id) AS cnt FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '30 days' GROUP BY user_id) SELECT ROUND(100.0 * COUNT(CASE WHEN cnt > 1 THEN 1 END) / NULLIF(COUNT(*), 0), 1) AS repeat_client_pct, COUNT(*) AS total_clients, COUNT(CASE WHEN cnt > 1 THEN 1 END) AS repeat_clients FROM orders

Динамика новых клиентов по неделям за последние 3 месяца
WITH first_orders AS (SELECT user_id, DATE_TRUNC('week', MIN(order_timestamp))::date AS first_week FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '3 months' GROUP BY user_id) SELECT first_week, COUNT(*) AS new_clients FROM first_orders GROUP BY first_week ORDER BY first_week LIMIT 1000

=== driver_daily_stats (алиас d) ===
Одна строка = водитель × город × день. Используй для онлайн-времени, acceptance rate, новых регистраций водителей.

Среднее время онлайн водителей по городам за последний месяц
SELECT d.city_id, ROUND(AVG(d.online_time_sum_seconds) / 3600.0, 1) AS avg_online_hours FROM driver_daily_stats d WHERE d.tender_date_part >= CURRENT_DATE - INTERVAL '30 days' GROUP BY d.city_id ORDER BY avg_online_hours DESC LIMIT 1000

Acceptance rate водителей по дням за последние 2 недели
SELECT d.tender_date_part AS day, ROUND(100.0 * SUM(d.orders_cnt_accepted) / NULLIF(SUM(d.orders_cnt_with_tenders), 0), 1) AS acceptance_rate_pct FROM driver_daily_stats d WHERE d.tender_date_part >= CURRENT_DATE - INTERVAL '14 days' GROUP BY 1 ORDER BY 1 LIMIT 1000

Топ 10 водителей по суммарному времени онлайн за месяц
SELECT d.driver_id, ROUND(SUM(d.online_time_sum_seconds) / 3600.0, 1) AS total_online_hours, SUM(d.rides_count) AS total_rides FROM driver_daily_stats d WHERE d.tender_date_part >= DATE_TRUNC('month', CURRENT_DATE) GROUP BY d.driver_id ORDER BY total_online_hours DESC LIMIT 10

Сколько новых водителей зарегистрировалось по месяцам за последний год
SELECT DATE_TRUNC('month', d.driver_reg_date)::date AS reg_month, COUNT(DISTINCT d.driver_id) AS new_drivers FROM driver_daily_stats d WHERE d.driver_reg_date >= CURRENT_DATE - INTERVAL '1 year' GROUP BY reg_month ORDER BY reg_month LIMIT 12

Водители с acceptance rate ниже 30% за последние 30 дней
SELECT d.driver_id, ROUND(100.0 * SUM(d.orders_cnt_accepted) / NULLIF(SUM(d.orders_cnt_with_tenders), 0), 1) AS acceptance_rate_pct, SUM(d.rides_count) AS rides FROM driver_daily_stats d WHERE d.tender_date_part >= CURRENT_DATE - INTERVAL '30 days' GROUP BY d.driver_id HAVING SUM(d.orders_cnt_with_tenders) >= 10 AND ROUND(100.0 * SUM(d.orders_cnt_accepted) / NULLIF(SUM(d.orders_cnt_with_tenders), 0), 1) < 30 ORDER BY acceptance_rate_pct ASC LIMIT 100

Среднее число поездок на водителя по дням недели
SELECT EXTRACT(DOW FROM d.tender_date_part)::int AS dow, TO_CHAR(d.tender_date_part, 'Day') AS day_name, ROUND(AVG(d.rides_count), 2) AS avg_rides FROM driver_daily_stats d WHERE d.tender_date_part >= CURRENT_DATE - INTERVAL '90 days' GROUP BY dow, day_name ORDER BY dow LIMIT 7

=== passenger_daily_stats (алиас p) ===
Одна строка = пассажир × город × день. Используй для активности пассажиров, новых регистраций, retention.

Сколько новых пассажиров зарегистрировалось по неделям за последние 3 месяца
SELECT DATE_TRUNC('week', p.user_reg_date)::date AS reg_week, COUNT(DISTINCT p.user_id) AS new_passengers FROM passenger_daily_stats p WHERE p.user_reg_date >= CURRENT_DATE - INTERVAL '3 months' GROUP BY reg_week ORDER BY reg_week LIMIT 1000

Активные пассажиры по дням за последние 30 дней (хотя бы 1 заказ)
SELECT p.order_date_part AS day, COUNT(DISTINCT p.user_id) AS active_passengers FROM passenger_daily_stats p WHERE p.order_date_part >= CURRENT_DATE - INTERVAL '30 days' AND p.orders_count > 0 GROUP BY 1 ORDER BY 1 LIMIT 1000

Среднее число поездок на пассажира по городам за последний месяц
SELECT p.city_id, ROUND(AVG(p.rides_count), 2) AS avg_rides_per_passenger FROM passenger_daily_stats p WHERE p.order_date_part >= DATE_TRUNC('month', CURRENT_DATE) AND p.rides_count > 0 GROUP BY p.city_id ORDER BY avg_rides_per_passenger DESC LIMIT 1000

Пассажиры с более чем 5 отменами после принятия за последние 30 дней
SELECT p.user_id, SUM(p.client_cancel_after_accept) AS total_cancels_after_accept FROM passenger_daily_stats p WHERE p.order_date_part >= CURRENT_DATE - INTERVAL '30 days' GROUP BY p.user_id HAVING SUM(p.client_cancel_after_accept) > 5 ORDER BY total_cancels_after_accept DESC LIMIT 100

Когортный retention пассажиров по неделям регистрации
WITH cohorts AS (SELECT DATE_TRUNC('week', p.user_reg_date)::date AS cohort_week, p.user_id FROM passenger_daily_stats p GROUP BY 1, 2), activity AS (SELECT DISTINCT DATE_TRUNC('week', p.order_date_part)::date AS activity_week, p.user_id FROM passenger_daily_stats p WHERE p.orders_count > 0) SELECT c.cohort_week, COUNT(DISTINCT c.user_id) AS cohort_size, COUNT(DISTINCT CASE WHEN a.activity_week = c.cohort_week + INTERVAL '1 week' THEN a.user_id END) AS week_1, COUNT(DISTINCT CASE WHEN a.activity_week = c.cohort_week + INTERVAL '2 weeks' THEN a.user_id END) AS week_2, COUNT(DISTINCT CASE WHEN a.activity_week = c.cohort_week + INTERVAL '3 weeks' THEN a.user_id END) AS week_3 FROM cohorts c LEFT JOIN activity a ON c.user_id = a.user_id GROUP BY c.cohort_week ORDER BY c.cohort_week DESC LIMIT 12
"""


async def _build_few_shots(question: str | None) -> str:
    """Return relevant few-shot examples from RAG store, fallback to static."""
    if question:
        try:
            from askdata.rag.store import get_similar
            hits = await asyncio.to_thread(get_similar, question, top_k=4, min_score=0.55)
            if hits:
                lines = ["\nПРИМЕРЫ (наиболее релевантные для данного вопроса):\n"]
                for h in hits:
                    lines.append(f"{h['question']}\n{h['sql']}\n")
                return "\n".join(lines)
        except Exception:
            pass
    return FEW_SHOT_EXAMPLES


async def _build_system_content(question: str | None = None) -> str:
    """Build system prompt: rules + schema + semantic layer + dynamic few-shots."""
    today = date.today().strftime("%Y-%m-%d")

    try:
        schema = await _get_cached_schema()
        schema_lines = ["СХЕМА БАЗЫ ДАННЫХ:"]
        for table in schema:
            cols = ", ".join(f"{c['name']} ({c['type']})" for c in table["columns"])
            schema_lines.append(f"  {table['name']}: {cols}")
        schema_context = "\n".join(schema_lines)
    except Exception:
        schema_context = "СХЕМА БАЗЫ ДАННЫХ: (недоступна)"

    sl = get_semantic_layer()
    semantic_lines = ["БИЗНЕС-МЕТРИКИ (семантический слой):"]
    for name, m in sl.metrics.items():
        semantic_lines.append(f"  {name}: {m.description}")
        semantic_lines.append(
            f"    SQL: {m.sql_expr} FROM {m.base_table}" + (f" WHERE {m.filters}" if m.filters else "")
        )
    semantic_context = "\n".join(semantic_lines)

    few_shots = await _build_few_shots(question)

    return (
        SYSTEM_PROMPT.format(today=today)
        + f"\n\n{schema_context}\n\n{semantic_context}\n\n{few_shots}"
    )


async def build_sql_messages(question: str, history: list[dict] | None = None) -> list[dict]:
    system_content = await _build_system_content(question)
    messages: list[dict] = [{"role": "system", "content": system_content}]

    if history:
        for msg in history[-6:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

    messages.append({"role": "user", "content": f"{question}\nSQL:"})
    return messages


async def build_correction_messages(
    question: str, previous_sql: str, error: str, history: list[dict] | None = None
) -> list[dict]:
    msgs = await build_sql_messages(question, history)
    # Replace last user message with correction context
    msgs[-1]["content"] = (
        f"{question}\n\n"
        f"Предыдущая попытка SQL:\n{previous_sql}\n\n"
        f"Ошибка: {error}\n\n"
        f"Исправь SQL. Отвечай ТОЛЬКО исправленным SQL:"
    )
    return msgs


async def build_interpretation_messages(question: str, sql: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Ты — аналитик данных. Объясняй SQL-запросы на русском языке одним-двумя предложениями, "
                "с точки зрения бизнеса. Не упоминай технические детали SQL."
            ),
        },
        {
            "role": "user",
            "content": f"Вопрос пользователя: {question}\nSQL: {sql}\n\nОбъяснение:",
        },
    ]


async def build_judge_messages(question: str, sql: str, result_sample: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Ты — эксперт по SQL и аналитике данных для такси-сервиса. "
                "Оцени, корректно ли SQL отвечает на вопрос пользователя. "
                "Отвечай ТОЛЬКО числом от 0.0 до 1.0 без пояснений. "
                "1.0 — полностью верен, 0.5 — частично, 0.0 — неверен."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Вопрос: {question}\n"
                f"SQL: {sql}\n"
                f"Результат (первые строки): {result_sample}\n\n"
                f"Оценка (0.0-1.0):"
            ),
        },
    ]


async def build_clarifying_question_messages(question: str) -> list[dict]:
    sl = get_semantic_layer()
    metrics = ", ".join(sl.metrics.keys()) if sl else "выручка, заказы, отмены, поездки"
    return [
        {
            "role": "system",
            "content": (
                "Ты — аналитик данных такси-сервиса. Твоя задача — предлагать конкретные уточняющие вопросы "
                "когда запрос пользователя неоднозначен. Отвечай ТОЛЬКО тремя вариантами, каждый с новой строки, "
                "начиная с цифры и точки. Без вводных слов."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Неоднозначный вопрос: {question}\n\n"
                f"Доступные метрики: {metrics}\n"
                f"Доступные периоды: сегодня, вчера, эта неделя, прошлая неделя, этот месяц, последние 30 дней\n\n"
                f"Сгенерируй 3 конкретных уточняющих варианта:"
            ),
        },
    ]
