"""Main NL→SQL pipeline orchestrator."""
import asyncio
import hashlib
import json
import re
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any

from askdata.config import get_settings
from askdata.query.preprocessor import preprocess
from askdata.query.router import route_query
from askdata.query.validator import validate_sql
from askdata.query.visualizer import build_chart_config
from askdata.query.prompt_builder import (
    build_sql_messages,
    build_correction_messages,
    build_interpretation_messages,
    build_clarifying_question_messages,
    build_judge_messages,
)
from askdata.query.llm.provider import get_provider
from askdata.db.target import execute_read_only
from askdata.semantic.loader import get_semantic_layer

settings = get_settings()


def _hash_data(rows: list) -> str:
    # Normalize by values only — ignore column aliases to avoid alias-mismatch across SC runs
    normalized = [[str(v) for v in r.values()] for r in rows]
    return hashlib.md5(json.dumps(normalized).encode()).hexdigest()


def _clean_sql(raw: str) -> str:
    """Strip markdown fences and leading/trailing whitespace from LLM output."""
    sql = raw.strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```\s*$", "", sql)
    return sql.strip().rstrip(";")


def _extract_columns_from_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    first = rows[0]
    cols = []
    for k, v in first.items():
        if isinstance(v, bool):
            t = "text"
        elif isinstance(v, int):
            t = "integer"
        elif isinstance(v, (float, Decimal)):
            t = "double precision"
        elif hasattr(v, "year"):
            t = "date"
        else:
            t = "text"
        cols.append({"name": str(k), "type": t})
    return cols


def _rows_to_list(rows: list[dict]) -> list[list]:
    return [list(r.values()) for r in rows]


async def _generate_sql_once(messages: list[dict], temperature: float, seed: int) -> str:
    provider = get_provider()
    raw = await provider.generate(messages, temperature=temperature, seed=seed)
    return _clean_sql(raw)


def _is_vague_question(text: str) -> bool:
    """Returns True if the question is too short/generic to answer without clarification."""
    if len(text) < 12:
        return True
    period_keywords = {"сегодня", "вчера", "неделя", "месяц", "год", "квартал", "день", "час", "последн"}
    metric_keywords = {
        "выручка", "заказ", "отмен", "клиент", "водител", "поездк", "оплат", "средн", "топ", "рейтинг",
        "пассажир", "регистр", "онлайн", "acceptance", "принят", "новых", "новые", "актив", "время",
        "дистанц", "длительн", "подач", "воронк", "retention", "когорт", "конверс", "аномал",
    }
    lower = text.lower()
    has_period = any(k in lower for k in period_keywords)
    has_metric = any(k in lower for k in metric_keywords)
    # Vague: no metric at all, or very short + no period
    if not has_metric:
        return True
    if len(text) < 20 and not has_period and not has_metric:
        return True
    return False


async def _llm_judge(question: str, sql: str, rows: list) -> float:
    """LLM judge: returns 0.0-1.0 score for how well sql answers question."""
    try:
        sample = json.dumps(rows[:3], default=str)
        messages = await build_judge_messages(question, sql, sample)
        provider = get_provider()
        raw = await provider.generate(messages, temperature=0.0, seed=0)
        m = re.search(r"[0-9]+(?:\.[0-9]+)?", raw)
        if m:
            return min(max(float(m.group()), 0.0), 1.0)
    except Exception:
        pass
    return 0.5


async def _self_consistency(question: str, history: list[dict] | None = None) -> tuple[str, float, str]:
    messages = await build_sql_messages(question, history=history)
    n_runs = settings.self_consistency_runs

    # First run at low temp for best guess; remaining at higher temp for diversity
    temps = [0.1] + [0.7] * (n_runs - 1)
    tasks = [_generate_sql_once(messages, temperature=temps[i], seed=i) for i in range(n_runs)]
    sqls = await asyncio.gather(*tasks, return_exceptions=True)
    sqls = [s for s in sqls if isinstance(s, str)]

    if not sqls:
        raise RuntimeError("LLM returned no results")

    # Validate all, collect hashes of results
    validated = []
    rows_cache: dict[str, list] = {}
    for sql in sqls:
        result = validate_sql(sql)
        if result.ok:
            try:
                rows = await execute_read_only(result.sql, max_rows=100)
                h = _hash_data(rows)
                rows_cache[result.sql] = rows
                validated.append((result.sql, h))
            except Exception:
                validated.append((result.sql, None))
        else:
            validated.append((None, None))

    ok_validated = [(sql, h, rows_cache.get(sql)) for sql, h in validated if sql is not None]
    if not ok_validated:
        return sqls[0], 0.33, "1 из 3 прогонов дал корректный SQL"

    counter = Counter(h for _, h, _ in ok_validated)
    winner_hash, winner_count = counter.most_common(1)[0]
    winning_entries = [(sql, rows) for sql, h, rows in ok_validated if h == winner_hash]
    best_sql, best_rows = winning_entries[0]
    sc_score = winner_count / n_runs

    if sc_score < 0.67 and best_rows is not None:
        judge_score = await _llm_judge(question, best_sql, best_rows)
        blended = round(0.35 * sc_score + 0.65 * judge_score, 2)
        explanation = f"SC {winner_count}/{n_runs} + джадж {judge_score:.0%} → {blended:.0%}"
        return best_sql, blended, explanation

    explanation = f"{winner_count} из {n_runs} прогонов дали идентичный результат"
    return best_sql, sc_score, explanation


async def _correct_sql(question: str, sql: str, error: str, max_retries: int = 2, history: list[dict] | None = None) -> str:
    for _ in range(max_retries):
        messages = await build_correction_messages(question, sql, error, history=history)
        provider = get_provider()
        raw = await provider.generate(messages, temperature=0.1)
        sql = _clean_sql(raw)
        result = validate_sql(sql)
        if result.ok:
            try:
                await execute_read_only(result.sql, dry_run=True)
                return result.sql
            except Exception as e:
                error = str(e)
        else:
            error = result.error
    return sql


def _build_interpretation(text: str, sql: str) -> dict:
    """Build interpretation chips from SQL AST — not from user text, to reflect what was actually queried."""
    import sqlglot
    from sqlglot import exp as sg_exp

    sl = get_semantic_layer()
    interpretation: dict = {}
    sql_norm = sql.lower().replace(" ", "")

    # 1. Detect metric by matching metric SQL expressions against the generated SQL
    for name, m in sl.metrics.items():
        expr_norm = m.sql_expr.lower().replace(" ", "")
        if expr_norm in sql_norm:
            interpretation["metric"] = m.description
            break

    # 2. Parse GROUP BY to detect grouping dimension
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres", error_level=sqlglot.ErrorLevel.IGNORE)
        group = parsed.find(sg_exp.Group)
        if group:
            for col in group.find_all(sg_exp.Column):
                col_name = col.name.lower()
                for dim_name, dim in sl.dimensions.items():
                    dim_col = dim.column.lower().split("(")[-1].rstrip(")")
                    if col_name == dim_col or col_name == dim_col.split(".")[-1]:
                        interpretation["grouping"] = dim_name
                        break
                if "grouping" in interpretation:
                    break
    except Exception:
        pass

    # 3. Detect period from WHERE clause by matching period expressions
    for period_name, period in sl.periods.items():
        check = getattr(period, "clause", "") or getattr(period, "start", "")
        if check:
            if check.lower().replace(" ", "") in sql_norm:
                interpretation["period"] = {"label": period_name}
                break

    # Fallback metric detection from SQL keywords when no metric matched
    if "metric" not in interpretation:
        sql_norm = sql.lower().replace(" ", "")
        if "sum(price_order_local)" in sql_norm:
            interpretation["metric"] = "Выручка"
        elif "clientcancel_timestamp" in sql_norm and "drivercancel_timestamp" in sql_norm:
            interpretation["metric"] = "Отмены (клиент + водитель)"
        elif "clientcancel_timestamp" in sql_norm:
            interpretation["metric"] = "Отмены клиентом"
        elif "drivercancel_timestamp" in sql_norm:
            interpretation["metric"] = "Отмены водителем"
        elif "driverdone_timestamp" in sql_norm and "count(" in sql_norm:
            interpretation["metric"] = "Завершённые поездки"
        elif "count(distinctuser_id)" in sql_norm:
            interpretation["metric"] = "Уникальные клиенты"
        elif "count(distinctdriver_id)" in sql_norm:
            interpretation["metric"] = "Активные водители"
        elif "avg(price_order_local)" in sql_norm:
            interpretation["metric"] = "Средний чек"
        elif "avg(distance_in_meters)" in sql_norm:
            interpretation["metric"] = "Средняя дистанция"
        elif "avg(duration_in_seconds)" in sql_norm:
            interpretation["metric"] = "Средняя длительность"
        elif "driverarrived_timestamp-driveraccept_timestamp" in sql_norm.replace(" ", ""):
            interpretation["metric"] = "Время подачи"
        elif "online_time_sum_seconds" in sql_norm:
            interpretation["metric"] = "Онлайн-время"
        elif "orders_cnt_accepted" in sql_norm and "orders_cnt_with_tenders" in sql_norm:
            interpretation["metric"] = "Acceptance rate"
        elif "driver_reg_date" in sql_norm:
            interpretation["metric"] = "Новые водители"
        elif "user_reg_date" in sql_norm:
            interpretation["metric"] = "Новые пассажиры"
        elif "rides_count" in sql_norm and "driver_daily_stats" in sql_norm:
            interpretation["metric"] = "Поездки водителей"
        elif "rides_count" in sql_norm and "passenger_daily_stats" in sql_norm:
            interpretation["metric"] = "Поездки пассажиров"
        elif "count(" in sql_norm:
            interpretation["metric"] = "Количество"
        else:
            interpretation["metric"] = "данные"

    interpretation["filters"] = []
    return interpretation


async def _generate_clarifying_suggestions(question: str) -> list[dict]:
    """Generate specific clarifying question variants via LLM."""
    try:
        messages = await build_clarifying_question_messages(question)
        provider = get_provider()
        raw = await provider.generate(messages, temperature=0.3)
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        suggestions = []
        for line in lines:
            # Strip leading "1. ", "2. ", "1.. ", "1. . " etc.
            text = re.sub(r"^[\d\.\)\s]+", "", line).strip()
            if text and len(text) > 5:
                suggestions.append({"text": text})
        if suggestions:
            return suggestions[:3]
    except Exception:
        pass
    # Fallback
    return [
        {"text": "Уточните метрику (выручка, заказы, отмены, клиенты)"},
        {"text": "Укажите период (за неделю, за месяц, за сегодня)"},
        {"text": "Добавьте группировку (по городам, по водителям)"},
    ]


async def _save_to_rag(question: str, sql: str, confidence: float) -> None:
    try:
        from askdata.rag.store import add_example
        await asyncio.to_thread(add_example, question, sql, "auto", confidence)
    except Exception:
        pass


async def _generate_explanation(question: str, sql: str) -> str:
    try:
        messages = await build_interpretation_messages(question, sql)
        provider = get_provider()
        return await provider.generate(messages, temperature=0.1)
    except Exception:
        return "Запрос выполнен успешно."


async def run_pipeline(
    text: str,
    force_llm: bool = False,
    user_id: int | None = None,
    session_id: str | None = None,
    history: list[dict] | None = None,
    mode: str = "easy",
) -> dict:
    t_start = time.time()
    timings: dict[str, int] = {}

    # 1. Preprocess
    processed = preprocess(text)
    timings["preprocess_ms"] = int((time.time() - t_start) * 1000)

    # 1.5 Ambiguity check — Easy mode: full validator; Expert mode: skip entirely
    if not force_llm and not history:
        if mode == "easy":
            from askdata.query.validator_agent import validate_question
            validation = await validate_question(processed)
            if not validation.valid:
                suggestions = validation.suggestions or await _generate_clarifying_suggestions(text)
                return {
                    "status": "ambiguous",
                    "confidence": {"score": 0.0, "level": "low", "explanation": "вопрос требует уточнения"},
                    "suggestions": suggestions,
                }
        elif _is_vague_question(processed):
            # Expert mode still blocks completely nonsensical input
            suggestions = await _generate_clarifying_suggestions(text)
            return {
                "status": "ambiguous",
                "confidence": {"score": 0.0, "level": "low", "explanation": "вопрос слишком общий"},
                "suggestions": suggestions,
            }

    # 2. Route
    t_route = time.time()
    route = await route_query(processed, force_llm=force_llm)
    timings["route_ms"] = int((time.time() - t_route) * 1000)

    sql_source = route.path
    sql = ""
    confidence_score = 1.0
    confidence_explanation = "шаблон"

    if route.path == "template":
        sql = route.template.render(route.slots)
        confidence_score = 0.95
        confidence_explanation = "точное совпадение с шаблоном"
        sql_source = "template"
        template_id = route.template.id

        val = validate_sql(sql)
        if not val.ok:
            route = type(route)(path="llm")
        else:
            sql = val.sql
    else:
        template_id = None

    if route.path == "llm" or not sql:
        t_llm = time.time()
        try:
            sql, confidence_score, confidence_explanation = await _self_consistency(processed, history=history)
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERPRETATION_FAILED",
                "detail": f"Не удалось сгенерировать SQL: {e}",
            }
        timings["llm_ms"] = int((time.time() - t_llm) * 1000)

        val = validate_sql(sql)
        if not val.ok:
            sql = await _correct_sql(processed, sql, val.error, history=history)
            val = validate_sql(sql)
            if val.ok:
                sql = val.sql
                sql_source = "llm_corrected"
            else:
                return {
                    "status": "error",
                    "error_code": "GUARDRAIL_VIOLATION",
                    "detail": "Сгенерированный запрос нарушает политики безопасности",
                    "violations": val.violations,
                }
        else:
            sql = val.sql

        template_id = None

    # 3. Execute
    t_exec = time.time()
    try:
        rows_raw = await execute_read_only(sql)
    except Exception as e:
        return {
            "status": "error",
            "error_code": "SQL_EXECUTION_ERROR",
            "detail": "Ошибка при выполнении запроса к БД",
            "sql_error": str(e),
            "sql": sql,
        }
    timings["db_ms"] = int((time.time() - t_exec) * 1000)

    # 4. No results → clarifying questions
    if not rows_raw and confidence_score < 0.9:
        suggestions = await _generate_clarifying_suggestions(text)
        return {
            "status": "ambiguous",
            "confidence": {
                "score": round(confidence_score, 2),
                "level": "low",
                "explanation": confidence_explanation,
            },
            "suggestions": suggestions,
        }

    low_confidence_suggestions = None
    if confidence_score < 0.5 and rows_raw:
        low_confidence_suggestions = await _generate_clarifying_suggestions(text)

    # 5. Build response
    columns = _extract_columns_from_rows(rows_raw)
    rows_list = _rows_to_list(rows_raw)
    chart_config = build_chart_config(columns, rows_list)

    if confidence_score >= 0.9:
        level = "high"
    elif confidence_score >= 0.5:
        level = "medium"
    else:
        level = "low"

    interpretation = _build_interpretation(processed, sql)

    t_exp = time.time()
    explanation = await _generate_explanation(text, sql)
    timings["explanation_ms"] = int((time.time() - t_exp) * 1000)

    timings["total_ms"] = int((time.time() - t_start) * 1000)
    execution_ms = timings["total_ms"]

    # Only auto-save high-confidence LLM results to keep RAG clean
    if confidence_score >= 0.9 and sql_source in ("llm", "llm_corrected"):
        asyncio.create_task(_save_to_rag(processed, sql, confidence_score))

    import uuid
    query_id = f"q_{uuid.uuid4().hex[:8]}"

    response = {
        "status": "ok",
        "query_id": query_id,
        "sql": sql,
        "sql_source": sql_source,
        "template_id": template_id,
        "interpretation": interpretation,
        "explanation": explanation,
        "data": {
            "columns": columns,
            "rows": rows_list,
            "row_count": len(rows_list),
        },
        "chart": chart_config,
        "confidence": {
            "score": round(confidence_score, 2),
            "level": level,
            "explanation": confidence_explanation,
        },
        "execution_ms": execution_ms,
        "timings": timings,
        "warnings": [],
        "suggestions": low_confidence_suggestions,
    }

    return response
