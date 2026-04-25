"""SQL templates for anonymized_incity_orders schema."""
from askdata.query.templates.base import Template, resolve_period
from askdata.semantic.loader import get_semantic_layer

# All templates use FROM anonymized_incity_orders o
# City grouping always adds LEFT JOIN cities c ON c.city_id = o.city_id
# Time column: o.order_timestamp


def _city_join() -> str:
    return "LEFT JOIN cities c ON c.city_id = o.city_id"


def _city_select() -> str:
    return "COALESCE(c.name, o.city_id::text) AS city"


def _city_group() -> str:
    return "o.city_id, c.name"


def _base_from() -> str:
    return "FROM anonymized_incity_orders o"


def _build_where(where_parts: list[str]) -> str:
    parts = [p for p in where_parts if p]
    return f"WHERE {' AND '.join(parts)}" if parts else ""


def _period_clause(period: str | None, col: str = "o.order_timestamp") -> str | None:
    if not period:
        return None
    start, end = resolve_period(period)
    return f"{col} >= {start} AND {col} < {end}"


class TopNByGroup(Template):
    def __init__(self):
        super().__init__(
            id="top_n_by_group",
            title="Топ-N по группе",
            description="Лучшие N записей по метрике, сгруппированных по городу или водителю",
            examples=[
                "топ 5 городов по выручке",
                "топ 5 городов по выручке за месяц",
                "топ 10 городов по выручке за неделю",
                "лучшие 10 водителей по числу поездок",
                "топ города по отменам",
                "топ 10 водителей по выручке",
                "топ 5 городов по заказам за месяц",
                "топ городов по поездкам за прошлую неделю",
                "лучшие города по числу заказов",
                "топ 10 водителей по поездкам за 30 дней",
                "топ 5 городов по числу отмен за месяц",
            ],
            slots=["metric", "group_by", "n", "period", "city_id"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "заказы")
        group = slots.get("group_by", "city_id")
        n = slots.get("n", 10)
        period = slots.get("period")
        city_id = slots.get("city_id")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            where_parts = [m.filters] if m.filters else []
        else:
            metric_sql = "COUNT(*)"
            where_parts = []

        if city_id:
            where_parts.append(f"o.city_id = {city_id}")

        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        if group == "driver_id":
            return (
                f"SELECT o.driver_id, {metric_sql} AS value "
                f"{_base_from()} {where} "
                f"GROUP BY o.driver_id ORDER BY value DESC LIMIT {n}"
            )

        return (
            f"SELECT {_city_select()}, {metric_sql} AS value "
            f"{_base_from()} {_city_join()} {where} "
            f"GROUP BY {_city_group()} ORDER BY value DESC LIMIT {n}"
        )


class BottomNByGroup(Template):
    def __init__(self):
        super().__init__(
            id="bottom_n_by_group",
            title="Анти-топ N по группе",
            description="Худшие N записей по метрике",
            examples=[
                "антитоп 3 городов по отменам",
                "города с наименьшим числом заказов",
                "худшие 5 водителей по поездкам",
                "наименьшая выручка по городам",
            ],
            slots=["metric", "group_by", "n", "period"],
        )

    def render(self, slots: dict) -> str:
        sql = TopNByGroup().render(slots)
        return sql.replace("ORDER BY value DESC", "ORDER BY value ASC")


class AvgByGroup(Template):
    def __init__(self):
        super().__init__(
            id="avg_by_group",
            title="Среднее по группе",
            description="Среднее значение метрики по городам или водителям",
            examples=[
                "средний чек по городам",
                "средний чек по городам за месяц",
                "средняя стоимость поездки по городам",
                "средний чек по водителям за месяц",
                "средняя длительность поездок по городам",
                "средний заказ по городам за неделю",
                "средняя дистанция по городам",
                "средний чек у водителей",
                "какой средний чек у водителей",
                "средний чек водителей",
                "средняя стоимость по водителям",
                "средний чек по водителям",
                "средний заработок водителей",
                "средняя выручка на водителя",
                "средняя стоимость поездки по водителям",
                "средний чек",
            ],
            slots=["metric", "group_by", "period"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "средний_чек")
        group = slots.get("group_by", "city_id")
        period = slots.get("period")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            where_parts = [m.filters] if m.filters else []
        else:
            metric_sql = "ROUND(AVG(price_order_local)::numeric, 2)"
            where_parts = ["driverdone_timestamp IS NOT NULL"]

        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        if group == "driver_id":
            return (
                f"SELECT o.driver_id, {metric_sql} AS avg_value "
                f"{_base_from()} {where} "
                f"GROUP BY o.driver_id ORDER BY avg_value DESC LIMIT 1000"
            )

        return (
            f"SELECT {_city_select()}, {metric_sql} AS avg_value "
            f"{_base_from()} {_city_join()} {where} "
            f"GROUP BY {_city_group()} ORDER BY avg_value DESC LIMIT 1000"
        )


class Timeseries(Template):
    def __init__(self):
        super().__init__(
            id="timeseries",
            title="Динамика по времени",
            description="Изменение метрики по дням/неделям",
            examples=[
                "динамика выручки за 30 дней",
                "динамика выручки за последние 30 дней",
                "отмены по дням за прошлую неделю",
                "заказы по дням за месяц",
                "тренд поездок за последние 7 дней",
                "динамика заказов за неделю",
                "выручка по дням за прошлый месяц",
                "заказы по дням за последние 14 дней",
            ],
            slots=["metric", "period", "granularity"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "заказы")
        period = slots.get("period", "последние 30 дней")
        granularity = slots.get("granularity", "day")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            where_parts = [m.filters] if m.filters else []
        else:
            metric_sql = "COUNT(*)"
            where_parts = []

        start, end = resolve_period(period)
        where_parts.append(f"o.order_timestamp >= {start} AND o.order_timestamp < {end}")
        where = _build_where(where_parts)

        return (
            f"SELECT DATE_TRUNC('{granularity}', o.order_timestamp)::date AS period_date, "
            f"{metric_sql} AS value "
            f"{_base_from()} {where} "
            f"GROUP BY 1 ORDER BY 1 LIMIT 1000"
        )


class AggregateByPeriod(Template):
    def __init__(self):
        super().__init__(
            id="aggregate_by_period",
            title="Агрегат за период",
            description="Одна метрика за указанный период",
            examples=[
                "выручка за прошлый месяц",
                "количество заказов за эту неделю",
                "отмены за сегодня",
                "поездки за последние 30 дней",
                "сколько заказов вчера",
                "выручка за вчера",
                "сколько поездок было за последние 7 дней",
            ],
            slots=["metric", "period"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "заказы")
        period = slots.get("period", "этот месяц")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            where_parts = [m.filters] if m.filters else []
        else:
            metric_sql = "COUNT(*)"
            where_parts = []

        start, end = resolve_period(period)
        where_parts.append(f"o.order_timestamp >= {start} AND o.order_timestamp < {end}")
        where = _build_where(where_parts)

        return f"SELECT {metric_sql} AS value {_base_from()} {where} LIMIT 1"


class PeriodComparison(Template):
    def __init__(self):
        super().__init__(
            id="period_comparison",
            title="Сравнение двух периодов",
            description="Сравнивает метрику между двумя периодами",
            examples=[
                "сравни выручку этой и прошлой недели",
                "сравни заказы этого и прошлого месяца",
                "отмены этот месяц vs прошлый",
                "сравни поездки этой и прошлой недели",
            ],
            slots=["metric", "period_a", "period_b"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "заказы")
        period_a = slots.get("period_a", "эта неделя")
        period_b = slots.get("period_b", "прошлая неделя")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            base_filter = m.filters
        else:
            metric_sql = "COUNT(*)"
            base_filter = ""

        def period_query(label: str, period: str) -> str:
            start, end = resolve_period(period)
            parts = []
            if base_filter:
                parts.append(base_filter)
            parts.append(f"o.order_timestamp >= {start} AND o.order_timestamp < {end}")
            where = _build_where(parts)
            return f"SELECT '{label}' AS period, {metric_sql} AS value {_base_from()} {where}"

        return (
            f"{period_query(period_a, period_a)} "
            f"UNION ALL "
            f"{period_query(period_b, period_b)}"
        )


class Distribution(Template):
    def __init__(self):
        super().__init__(
            id="distribution",
            title="Распределение по группам",
            description="Распределение заказов с процентами по измерению",
            examples=[
                "распределение заказов по статусам",
                "доля заказов по городам",
                "распределение по статусам за месяц",
                "процент завершённых заказов",
            ],
            slots=["group_by", "period"],
        )

    def render(self, slots: dict) -> str:
        group = slots.get("group_by", "status_order")
        period = slots.get("period")

        where_parts: list[str] = []
        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        if group == "city_id":
            return (
                f"SELECT {_city_select()}, COUNT(DISTINCT order_id) AS cnt, "
                f"ROUND(COUNT(DISTINCT order_id) * 100.0 / SUM(COUNT(DISTINCT order_id)) OVER(), 1) AS pct "
                f"{_base_from()} {_city_join()} {where} "
                f"GROUP BY {_city_group()} ORDER BY cnt DESC LIMIT 1000"
            )

        return (
            f"SELECT {group}, COUNT(DISTINCT order_id) AS cnt, "
            f"ROUND(COUNT(DISTINCT order_id) * 100.0 / SUM(COUNT(DISTINCT order_id)) OVER(), 1) AS pct "
            f"{_base_from()} {where} "
            f"GROUP BY {group} ORDER BY cnt DESC LIMIT 1000"
        )


class RunningTotal(Template):
    def __init__(self):
        super().__init__(
            id="running_total",
            title="Накопительная сумма",
            description="Нарастающий итог метрики за период",
            examples=[
                "накопительная выручка за месяц",
                "нарастающие заказы за 30 дней",
                "накопительные поездки за неделю",
            ],
            slots=["metric", "period"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "выручка")
        period = slots.get("period", "этот месяц")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            base_filter = m.filters
        else:
            metric_sql = "COUNT(*)"
            base_filter = ""

        start, end = resolve_period(period)
        parts = []
        if base_filter:
            parts.append(base_filter)
        parts.append(f"o.order_timestamp >= {start} AND o.order_timestamp < {end}")
        where = _build_where(parts)

        # Subquery required: window function ORDER BY can't reference raw column after GROUP BY
        return (
            f"SELECT day, daily_value, SUM(daily_value) OVER (ORDER BY day) AS running_total "
            f"FROM ("
            f"SELECT DATE_TRUNC('day', o.order_timestamp)::date AS day, "
            f"{metric_sql} AS daily_value "
            f"{_base_from()} {where} GROUP BY 1 ORDER BY 1"
            f") sub LIMIT 1000"
        )


class HourlyDistribution(Template):
    def __init__(self):
        super().__init__(
            id="hourly_distribution",
            title="Распределение по часам",
            description="Пиковые часы по метрике",
            examples=[
                "заказы по часам за сегодня",
                "заказы по часам за неделю",
                "пиковые часы за последние 7 дней",
                "выручка по часам за месяц",
                "отмены по часам дня",
                "количество поездок по часам",
            ],
            slots=["metric", "period"],
        )

    def render(self, slots: dict) -> str:
        metric = slots.get("metric", "заказы")
        period = slots.get("period", "последние 7 дней")
        sl = get_semantic_layer()
        m = sl.metrics.get(metric)

        if m:
            metric_sql = m.sql_expr
            where_parts = [m.filters] if m.filters else []
        else:
            metric_sql = "COUNT(*)"
            where_parts = []

        start, end = resolve_period(period)
        where_parts.append(f"o.order_timestamp >= {start} AND o.order_timestamp < {end}")
        where = _build_where(where_parts)

        return (
            f"SELECT EXTRACT(HOUR FROM o.order_timestamp)::int AS hour, "
            f"{metric_sql} AS value "
            f"{_base_from()} {where} "
            f"GROUP BY 1 ORDER BY 1 LIMIT 24"
        )


class CancellationRate(Template):
    def __init__(self):
        super().__init__(
            id="cancellation_rate",
            title="Отмены и коэффициент отмен",
            description="Отмены клиентом и водителем по городам с процентами",
            examples=[
                "покажи отмены по городам за прошлую неделю",
                "отмены по городам за прошлую неделю",
                "процент отмен по городам",
                "коэффициент отмен за месяц",
                "доля отменённых заказов по городам",
                "процент отмен за прошлую неделю",
                "рейтинг городов по отменам",
                "отмены клиентов и водителей по городам",
                "топ 5 городов по отменам клиентов за 30 дней",
                "отмены по городам за последние 30 дней",
            ],
            slots=["group_by", "period"],
        )

    def render(self, slots: dict) -> str:
        group = slots.get("group_by", "city_id")
        period = slots.get("period")

        where_parts: list[str] = []
        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        if group == "driver_id":
            return (
                f"SELECT o.driver_id, "
                f"COUNT(DISTINCT CASE WHEN o.clientcancel_timestamp IS NOT NULL THEN o.order_id END) AS client_cancels, "
                f"COUNT(DISTINCT CASE WHEN o.drivercancel_timestamp IS NOT NULL THEN o.order_id END) AS driver_cancels, "
                f"COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) AS total_cancels, "
                f"ROUND(COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) * 100.0 / NULLIF(COUNT(DISTINCT o.order_id), 0), 1) AS cancel_rate_pct "
                f"{_base_from()} {where} "
                f"GROUP BY o.driver_id ORDER BY cancel_rate_pct DESC LIMIT 1000"
            )

        return (
            f"SELECT {_city_select()}, "
            f"COUNT(DISTINCT CASE WHEN o.clientcancel_timestamp IS NOT NULL THEN o.order_id END) AS client_cancels, "
            f"COUNT(DISTINCT CASE WHEN o.drivercancel_timestamp IS NOT NULL THEN o.order_id END) AS driver_cancels, "
            f"COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) AS total_cancels, "
            f"ROUND(COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) * 100.0 / NULLIF(COUNT(DISTINCT o.order_id), 0), 1) AS cancel_rate_pct "
            f"{_base_from()} {_city_join()} {where} "
            f"GROUP BY {_city_group()} ORDER BY cancel_rate_pct DESC LIMIT 1000"
        )


class StatusSplit(Template):
    def __init__(self):
        super().__init__(
            id="status_split",
            title="Разбивка по статусам заказов",
            description="Количество и доля заказов по каждому статусу",
            examples=[
                "статусы заказов за сегодня",
                "разбивка заказов по статусам за неделю",
                "сколько выполненных и отменённых заказов",
                "статусы за последние 30 дней",
                "выполненные и отменённые за месяц",
                "распределение заказов по статусам за месяц",
            ],
            slots=["period"],
        )

    def render(self, slots: dict) -> str:
        period = slots.get("period")
        where_parts: list[str] = []
        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        # COUNT(DISTINCT order_id) to count unique orders per status
        return (
            f"SELECT status_order, COUNT(DISTINCT order_id) AS cnt, "
            f"ROUND(COUNT(DISTINCT order_id) * 100.0 / SUM(COUNT(DISTINCT order_id)) OVER(), 1) AS pct "
            f"{_base_from()} {where} "
            f"GROUP BY status_order ORDER BY cnt DESC LIMIT 1000"
        )


class PickupTime(Template):
    def __init__(self):
        super().__init__(
            id="pickup_time",
            title="Среднее время подачи",
            description="Среднее время в минутах от принятия заказа до прибытия водителя на точку",
            examples=[
                "время подачи по городам",
                "время прибытия водителя по городам за месяц",
                "pickup time по городам",
                "время ожидания подачи",
                "как долго ждать водителя по городам",
                "сколько минут едет водитель до клиента",
                "время от принятия до прибытия по городам",
                "время подачи по водителям",
            ],
            slots=["group_by", "period"],
        )

    def render(self, slots: dict) -> str:
        group = slots.get("group_by", "city_id")
        period = slots.get("period")

        where_parts = [
            "o.driverarrived_timestamp IS NOT NULL",
            "o.driveraccept_timestamp IS NOT NULL",
        ]
        p = _period_clause(period)
        if p:
            where_parts.append(p)

        where = _build_where(where_parts)

        avg_expr = (
            "ROUND((AVG(EXTRACT(EPOCH FROM "
            "(o.driverarrived_timestamp - o.driveraccept_timestamp))) / 60.0)::numeric, 1) AS avg_pickup_min"
        )

        if group == "driver_id":
            return (
                f"SELECT o.driver_id, {avg_expr} "
                f"{_base_from()} {where} "
                f"GROUP BY o.driver_id ORDER BY avg_pickup_min ASC LIMIT 20"
            )

        return (
            f"SELECT {_city_select()}, {avg_expr} "
            f"{_base_from()} {_city_join()} {where} "
            f"GROUP BY {_city_group()} ORDER BY avg_pickup_min ASC LIMIT 1000"
        )


class FunnelDropoff(Template):
    def __init__(self):
        super().__init__(
            id="funnel_dropoff",
            title="Воронка заказов",
            description="Воронка уникальных заказов: создано → принято → прибыл → поехал → завершено",
            examples=[
                "воронка заказов за 7 дней",
                "воронка за последние 30 дней",
                "покажи воронку заказов за неделю",
                "конверсия заказов за месяц",
                "этапы заказа за этот месяц",
            ],
            slots=["period"],
        )

    def render(self, slots: dict) -> str:
        period = slots.get("period", "последние 7 дней")
        start, end = resolve_period(period)
        where = f"WHERE o.order_timestamp >= {start} AND o.order_timestamp < {end}"

        # Long format (stage, count) → 2 cols → bar chart works correctly
        return (
            f"SELECT stage, order_count FROM ("
            f"SELECT 1 AS ord, 'создано' AS stage, COUNT(DISTINCT order_id) AS order_count {_base_from()} {where} "
            f"UNION ALL "
            f"SELECT 2, 'принято', COUNT(DISTINCT CASE WHEN o.driveraccept_timestamp IS NOT NULL THEN o.order_id END) {_base_from()} {where} "
            f"UNION ALL "
            f"SELECT 3, 'прибыл', COUNT(DISTINCT CASE WHEN o.driverarrived_timestamp IS NOT NULL THEN o.order_id END) {_base_from()} {where} "
            f"UNION ALL "
            f"SELECT 4, 'поехал', COUNT(DISTINCT CASE WHEN o.driverstarttheride_timestamp IS NOT NULL THEN o.order_id END) {_base_from()} {where} "
            f"UNION ALL "
            f"SELECT 5, 'завершено', COUNT(DISTINCT CASE WHEN o.driverdone_timestamp IS NOT NULL THEN o.order_id END) {_base_from()} {where}"
            f") sub ORDER BY ord"
        )


class AnomalyDetection(Template):
    def __init__(self):
        super().__init__(
            id="anomaly_detection",
            title="Аномалии метрики",
            description="Дни с аномально высоким числом отмен или заказов (z-score > 2)",
            examples=[
                "аномалии отмен за последний месяц",
                "аномальные дни по заказам за квартал",
                "пики отмен за 30 дней",
                "найди аномалии в заказах",
                "выброс заказов за 90 дней",
                "дни с аномально высокими отменами",
            ],
            slots=["metric", "period"],
        )

    def render(self, slots: dict) -> str:
        period = slots.get("period", "последние 30 дней")
        metric_hint = slots.get("metric", "заказы").lower()
        start, end = resolve_period(period)
        where = f"WHERE o.order_timestamp >= {start} AND o.order_timestamp < {end}"

        if any(k in metric_hint for k in ("отмен", "cancel")):
            metric_sql = "COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END)"
            metric_name = "cancel_count"
        else:
            metric_sql = "COUNT(DISTINCT o.order_id)"
            metric_name = "order_count"

        return (
            f"WITH daily AS ("
            f"SELECT DATE(o.order_timestamp) AS day, {metric_sql} AS {metric_name} "
            f"{_base_from()} {where} GROUP BY DATE(o.order_timestamp)"
            f"), stats AS ("
            f"SELECT AVG({metric_name}) AS avg_val, STDDEV_POP({metric_name}) AS std_val FROM daily"
            f") "
            f"SELECT d.day, d.{metric_name}, "
            f"ROUND(d.{metric_name} - s.avg_val, 0) AS deviation, "
            f"ROUND((d.{metric_name} - s.avg_val) / NULLIF(s.std_val, 0), 2) AS z_score "
            f"FROM daily d, stats s "
            f"WHERE s.std_val > 0 AND d.{metric_name} > s.avg_val + 2 * s.std_val "
            f"ORDER BY d.{metric_name} DESC LIMIT 20"
        )


class RetentionCohort(Template):
    def __init__(self):
        super().__init__(
            id="retention_cohort",
            title="Когортный анализ retention",
            description="Удержание клиентов по неделям: сколько вернулось через 1-4 недели после первого заказа",
            examples=[
                "retention клиентов по когортам",
                "когортный анализ за последние 8 недель",
                "удержание клиентов по неделям",
                "сколько клиентов возвращаются",
                "retention за квартал",
                "анализ повторных заказов по когортам",
            ],
            slots=["period"],
        )

    def render(self, slots: dict) -> str:
        period = slots.get("period", "последние 8 недель")
        start, end = resolve_period(period)
        cohort_where = f"WHERE o.order_timestamp >= {start} AND o.order_timestamp < {end}"

        return (
            f"WITH first_orders AS ("
            f"SELECT o.user_id, DATE_TRUNC('week', MIN(o.order_timestamp)) AS cohort_week "
            f"{_base_from()} {cohort_where} AND o.status_tender = 'done' "
            f"GROUP BY o.user_id"
            f"), weekly_activity AS ("
            f"SELECT DISTINCT o.user_id, DATE_TRUNC('week', o.order_timestamp) AS activity_week "
            f"{_base_from()} WHERE o.status_tender = 'done'"
            f") "
            f"SELECT TO_CHAR(f.cohort_week, 'YYYY-MM-DD') AS cohort_week, "
            f"COUNT(DISTINCT f.user_id) AS cohort_size, "
            f"COUNT(DISTINCT CASE WHEN w.activity_week = f.cohort_week + INTERVAL '1 week' THEN w.user_id END) AS week_1, "
            f"COUNT(DISTINCT CASE WHEN w.activity_week = f.cohort_week + INTERVAL '2 weeks' THEN w.user_id END) AS week_2, "
            f"COUNT(DISTINCT CASE WHEN w.activity_week = f.cohort_week + INTERVAL '3 weeks' THEN w.user_id END) AS week_3, "
            f"COUNT(DISTINCT CASE WHEN w.activity_week = f.cohort_week + INTERVAL '4 weeks' THEN w.user_id END) AS week_4 "
            f"FROM first_orders f LEFT JOIN weekly_activity w ON f.user_id = w.user_id "
            f"GROUP BY f.cohort_week ORDER BY f.cohort_week DESC LIMIT 10"
        )


class DriverOnlineTime(Template):
    def __init__(self):
        super().__init__(
            id="driver_online_time",
            title="Онлайн-время водителей",
            description="Среднее или суммарное время онлайн водителей по городам/дням из driver_daily_stats",
            examples=[
                "среднее время онлайн водителей по городам",
                "онлайн-время водителей за месяц",
                "сколько часов онлайн водители за последние 30 дней",
                "динамика онлайн-времени водителей за месяц",
                "топ водителей по времени онлайн",
                "среднее время онлайн по городам за последнюю неделю",
            ],
            slots=["period", "group_by"],
        )

    def render(self, slots: dict) -> str:
        group = slots.get("group_by", "city_id")
        period = slots.get("period")

        where_parts: list[str] = []
        if period:
            start, end = resolve_period(period)
            where_parts.append(f"d.tender_date_part >= {start}::date AND d.tender_date_part < {end}::date")
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if group == "driver_id":
            return (
                f"SELECT d.driver_id, "
                f"ROUND(SUM(d.online_time_sum_seconds) / 3600.0, 1) AS total_online_hours, "
                f"SUM(d.rides_count) AS rides "
                f"FROM driver_daily_stats d {where} "
                f"GROUP BY d.driver_id ORDER BY total_online_hours DESC LIMIT 20"
            )

        return (
            f"SELECT d.city_id, "
            f"ROUND(AVG(d.online_time_sum_seconds) / 3600.0, 1) AS avg_online_hours, "
            f"ROUND(AVG(d.rides_count), 2) AS avg_rides "
            f"FROM driver_daily_stats d {where} "
            f"GROUP BY d.city_id ORDER BY avg_online_hours DESC LIMIT 1000"
        )


class DriverAcceptanceRate(Template):
    def __init__(self):
        super().__init__(
            id="driver_acceptance_rate",
            title="Acceptance rate водителей",
            description="Доля принятых заказов от тендеров (из driver_daily_stats) по дням или городам",
            examples=[
                "acceptance rate водителей за 2 недели",
                "acceptance rate по дням за последний месяц",
                "коэффициент принятия заказов водителями",
                "какой процент тендеров принимают водители",
                "acceptance rate по городам за последние 30 дней",
                "динамика acceptance rate за последний месяц",
            ],
            slots=["period", "group_by"],
        )

    def render(self, slots: dict) -> str:
        group = slots.get("group_by", "day")
        period = slots.get("period", "последние 30 дней")

        start, end = resolve_period(period)
        where = f"WHERE d.tender_date_part >= {start}::date AND d.tender_date_part < {end}::date"

        if group == "city_id":
            return (
                f"SELECT d.city_id, "
                f"ROUND(100.0 * SUM(d.orders_cnt_accepted) / NULLIF(SUM(d.orders_cnt_with_tenders), 0), 1) AS acceptance_rate_pct, "
                f"SUM(d.orders_cnt_with_tenders) AS total_tenders, "
                f"SUM(d.rides_count) AS rides "
                f"FROM driver_daily_stats d {where} "
                f"GROUP BY d.city_id ORDER BY acceptance_rate_pct DESC LIMIT 1000"
            )

        return (
            f"SELECT d.tender_date_part AS day, "
            f"ROUND(100.0 * SUM(d.orders_cnt_accepted) / NULLIF(SUM(d.orders_cnt_with_tenders), 0), 1) AS acceptance_rate_pct "
            f"FROM driver_daily_stats d {where} "
            f"GROUP BY d.tender_date_part ORDER BY d.tender_date_part LIMIT 1000"
        )


class PassengerNewRegistrations(Template):
    def __init__(self):
        super().__init__(
            id="passenger_new_registrations",
            title="Новые регистрации пассажиров",
            description="Количество новых пассажиров по дням/неделям регистрации (из passenger_daily_stats)",
            examples=[
                "новые пассажиры по неделям за последние 3 месяца",
                "сколько новых клиентов зарегистрировалось за месяц",
                "новые регистрации пассажиров за последний квартал",
                "прирост пассажиров по неделям",
                "динамика новых пассажиров за 6 месяцев",
                "новые водители по месяцам за год",
            ],
            slots=["period", "granularity", "group"],
        )

    def render(self, slots: dict) -> str:
        period = slots.get("period", "последние 3 месяца")
        granularity = slots.get("granularity", "week")
        group = slots.get("group", "passenger")

        start, end = resolve_period(period)

        if group == "driver":
            return (
                f"SELECT DATE_TRUNC('{granularity}', d.driver_reg_date)::date AS reg_{granularity}, "
                f"COUNT(DISTINCT d.driver_id) AS new_drivers "
                f"FROM driver_daily_stats d "
                f"WHERE d.driver_reg_date >= {start}::date AND d.driver_reg_date < {end}::date "
                f"GROUP BY 1 ORDER BY 1 LIMIT 1000"
            )

        return (
            f"SELECT DATE_TRUNC('{granularity}', p.user_reg_date)::date AS reg_{granularity}, "
            f"COUNT(DISTINCT p.user_id) AS new_passengers "
            f"FROM passenger_daily_stats p "
            f"WHERE p.user_reg_date >= {start}::date AND p.user_reg_date < {end}::date "
            f"GROUP BY 1 ORDER BY 1 LIMIT 1000"
        )


ALL_TEMPLATES = [
    TopNByGroup(),
    BottomNByGroup(),
    AvgByGroup(),
    Timeseries(),
    AggregateByPeriod(),
    PeriodComparison(),
    Distribution(),
    RunningTotal(),
    HourlyDistribution(),
    CancellationRate(),
    StatusSplit(),
    PickupTime(),
    FunnelDropoff(),
    AnomalyDetection(),
    RetentionCohort(),
    DriverOnlineTime(),
    DriverAcceptanceRate(),
    PassengerNewRegistrations(),
]
