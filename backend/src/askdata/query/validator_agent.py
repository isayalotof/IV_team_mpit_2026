"""Pre-flight question validator for Easy mode."""
import asyncio
import json
import re
from dataclasses import dataclass, field

# Настоящие метрики — что считать
METRIC_KEYWORDS = {
    "выручка", "заказ", "отмен", "клиент", "водител", "поездк", "оплат",
    "средн", "топ", "рейтинг", "количество", "доход", "сумма", "процент",
    "динамик", "статус", "время", "подач", "дистанц", "рейс", "тариф",
    "скольк",
}

# Слова-команды без метрики — сами по себе не дают понять ЧТО считать
COMMAND_ONLY = {"покажи", "покажь", "выведи", "отобрази", "дай", "напиши"}

PERIOD_KEYWORDS = {
    "сегодня", "вчера", "неделя", "месяц", "год", "квартал", "день", "час",
    "последн", "апрел", "март", "феврал", "январ", "декабр", "ноябр",
    "октябр", "сентябр", "август", "июл", "июн", "май", "числ", "период",
    "дней", "недель", "недели", "сутки",
}


@dataclass
class ValidationResult:
    valid: bool
    missing: list[str] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)


def _keyword_check(text: str) -> ValidationResult | None:
    """Fast local check. Returns None if result is ambiguous (needs LLM)."""
    lower = text.lower()
    words = set(lower.split())

    if len(text) < 5:
        return ValidationResult(
            valid=False,
            missing=["metric", "period"],
            suggestions=[
                {"text": "Что именно посчитать? (выручку, заказы, отмены, водителей)"},
                {"text": "За какой период? (сегодня, за неделю, за месяц)"},
            ],
        )

    # Убираем команды и смотрим остаток
    content_words = words - COMMAND_ONLY
    content_text = " ".join(content_words)

    has_metric = any(k in content_text for k in METRIC_KEYWORDS)
    has_period = any(k in lower for k in PERIOD_KEYWORDS)

    # Только команда без метрики: "покажи данные", "выведи всё"
    if not has_metric and len(content_text.strip()) < 10:
        return ValidationResult(
            valid=False,
            missing=["metric"],
            suggestions=_default_suggestions(["metric"]),
        )

    # Есть метрика, но запрос очень короткий и без периода → спросить период
    # Исключение: топ-N запросы (период необязателен), сравни
    is_topn = any(k in lower for k in ("топ", "лучш", "худш", "рейтинг", "сравни"))
    if has_metric and len(text) < 12 and not has_period and not is_topn:
        return ValidationResult(
            valid=False,
            missing=["period"],
            suggestions=_default_suggestions(["period"]),
        )

    # Есть метрика → valid
    if has_metric:
        return ValidationResult(valid=True)

    # Длинный текст без явных ключевых слов → пусть LLM решит
    if len(text) >= 15:
        return None

    # Короткий без метрики → invalid
    return ValidationResult(
        valid=False,
        missing=["metric"] + ([] if has_period else ["period"]),
        suggestions=_default_suggestions(["metric"]),
    )


async def validate_question(text: str) -> ValidationResult:
    """Validate question completeness for Easy mode.

    Fast keyword check first; if ambiguous, calls LLM with 5s timeout.
    """
    fast = _keyword_check(text)
    if fast is not None:
        if not fast.valid and not fast.suggestions:
            fast.suggestions = _default_suggestions(fast.missing)
        return fast

    # Ambiguous — call LLM classifier with tight timeout
    try:
        result = await asyncio.wait_for(_llm_classify(text), timeout=5.0)
        return result
    except Exception:
        pass

    # Fallback: treat as valid to avoid false negatives
    return ValidationResult(valid=True)


async def _llm_classify(text: str) -> ValidationResult:
    from askdata.query.llm.provider import get_provider
    provider = get_provider()
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — классификатор аналитических запросов на русском. "
                "Отвечай ТОЛЬКО JSON без markdown. "
                "Поля: has_metric (bool), has_period (bool), is_analytics (bool)."
            ),
        },
        {
            "role": "user",
            "content": (
                f'Запрос: "{text}"\n\n'
                "Ответь JSON: есть ли метрика (что считать), период (за какое время), "
                "это аналитический вопрос о данных такси?"
            ),
        },
    ]
    raw = await provider.generate(messages, temperature=0.0)
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not m:
        return ValidationResult(valid=True)

    parsed = json.loads(m.group())
    has_metric = bool(parsed.get("has_metric", True))
    is_analytics = bool(parsed.get("is_analytics", True))

    if not is_analytics:
        return ValidationResult(
            valid=False,
            missing=["not_analytics"],
            suggestions=[{"text": "Я отвечаю только на аналитические вопросы о данных Drivee"}],
        )

    if not has_metric:
        return ValidationResult(
            valid=False,
            missing=["metric"],
            suggestions=_default_suggestions(["metric"]),
        )

    return ValidationResult(valid=True)


def _default_suggestions(missing: list[str]) -> list[dict]:
    suggestions = []
    if "metric" in missing:
        suggestions += [
            {"text": "Уточните: выручку, заказы, отмены, водителей или клиентов"},
            {"text": "Например: «выручка за апрель» или «топ-5 городов по заказам»"},
        ]
    if "period" in missing:
        suggestions += [
            {"text": "Добавьте период: «за сегодня», «за прошлую неделю», «за апрель»"},
        ]
    if "not_analytics" in missing:
        suggestions += [
            {"text": "Попробуйте: «сколько заказов за апрель?» или «динамика выручки за месяц»"},
        ]
    return suggestions[:3]
