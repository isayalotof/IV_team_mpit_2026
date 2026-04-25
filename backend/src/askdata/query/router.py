"""Route query: template match OR full LLM generation."""
import re
import difflib
import logging
from dataclasses import dataclass
from askdata.query.templates.catalog import ALL_TEMPLATES, Template
from askdata.config import get_settings

# Keyword shortcuts: unambiguous phrases that bypass embedding match.
# Each entry: (list of trigger substrings, template_id). First match wins.
# Substrings are matched on lowercased input; order matters — more specific first.
_KEYWORD_SHORTCUTS: list[tuple[list[str], str]] = [
    (["воронка заказов", "этапы заказа", "конверсия заказов"], "funnel_dropoff"),
    (["накопительн", "нарастающ"], "running_total"),
    (["коэффициент отмен", "cancel rate"], "cancellation_rate"),
    (["разбивка по статусам", "статусы заказов", "выполненные и отменённые"], "status_split"),
    (["время подачи", "pickup time", "время прибытия водителя"], "pickup_time"),
    (["по часам", "пиковые часы", "часам дня", "час дня"], "hourly_distribution"),
]

settings = get_settings()
logger = logging.getLogger(__name__)

# Cached (template, embedding) pairs — built once on first routing call
_template_emb_cache: list[tuple[Template, "np.ndarray"]] | None = None


@dataclass
class RouteResult:
    path: str  # "template" | "llm"
    template: Template | None = None
    slots: dict | None = None
    score: float = 0.0


def _build_template_emb_cache() -> None:
    global _template_emb_cache
    if _template_emb_cache is not None:
        return
    try:
        from askdata.rag.store import _embed
        cache = []
        for tmpl in ALL_TEMPLATES:
            for example in tmpl.examples:
                cache.append((tmpl, _embed(example)))
        _template_emb_cache = cache
        logger.info("Router: built embedding cache for %d template examples", len(cache))
    except Exception as e:
        logger.warning("Router: could not build embedding cache: %s — using SequenceMatcher", e)
        _template_emb_cache = []  # mark as attempted so we don't retry every call


def _best_template_match(text: str) -> tuple[Template | None, float]:
    """Match template using embeddings (primary) or SequenceMatcher (fallback)."""
    # Try embedding-based match first
    if _template_emb_cache is None:
        _build_template_emb_cache()

    if _template_emb_cache:
        try:
            import numpy as np
            from askdata.rag.store import _embed
            q_emb = _embed(text)
            best_score = 0.0
            best_template = None
            for tmpl, ex_emb in _template_emb_cache:
                score = float(np.dot(q_emb, ex_emb))
                if score > best_score:
                    best_score = score
                    best_template = tmpl
            return best_template, best_score
        except Exception as e:
            logger.warning("Router: embedding match failed, falling back to SequenceMatcher: %s", e)

    # Fallback: SequenceMatcher
    best_score = 0.0
    best_template = None
    for tmpl in ALL_TEMPLATES:
        for example in tmpl.examples:
            score = difflib.SequenceMatcher(None, text.lower(), example.lower()).ratio()
            if score > best_score:
                best_score = score
                best_template = tmpl
    return best_template, best_score


_RUSSIAN_CITIES: dict[str, int] = {
    "москв": 1, "санкт-петербург": 2, "питер": 2,
    "екатеринбург": 3, "новосибирск": 4, "казан": 5,
    "краснодар": 6, "нижн": 7, "перм": 8,
    "уф": 9, "хабаровск": 10, "самар": 11, "ростов": 12,
}

# Queries with numeric thresholds (более 5, больше 10, >N) cannot be handled by templates
_THRESHOLD_RE = re.compile(
    r'\b(более|больше|свыше|менее|меньше|не более|не менее)\s+\d+\b'
    r'|\b\d+\s*(и более|и меньше|и выше|и ниже)\b'
    r'|[><!]=?\s*\d+',
    re.IGNORECASE,
)

_DYNAMIC_PERIOD_RE = re.compile(
    r"последн(?:ие|их|ий)\s+(\d+)\s+(дн(?:ей|я|ь)|недел(?:ь|и|ю)|месяц(?:а|ев)?|час(?:а|ов)?)",
    re.IGNORECASE,
)
_UNIT_MAP = {"дн": "days", "недел": "weeks", "месяц": "months", "час": "hours"}


def _resolve_dynamic_period(text: str) -> str | None:
    """Extract 'последние N дней/недель/...' and return a pseudo-period key like 'dyn.14.days'."""
    m = _DYNAMIC_PERIOD_RE.search(text)
    if not m:
        return None
    n = m.group(1)
    unit_raw = m.group(2).lower()
    for prefix, unit_sql in _UNIT_MAP.items():
        if unit_raw.startswith(prefix):
            return f"dyn.{n}.{unit_sql}"
    return None


def _register_dynamic_period(key: str) -> None:
    """Inject a dynamic period into semantic layer periods cache so resolve_period works."""
    from askdata.semantic.loader import get_semantic_layer
    sl = get_semantic_layer()
    if key not in sl.periods:
        _, n, unit = key.split(".")  # "dyn.14.days" → ["dyn", "14", "days"]

        class _DynPeriod:
            start = f"NOW() - INTERVAL '{n} {unit}'"
            end = "NOW()"

        sl.periods[key] = _DynPeriod()


def _extract_slots_simple(text: str, template: Template) -> dict:
    """Basic slot extraction using keyword rules."""
    from askdata.semantic.loader import get_semantic_layer
    sl = get_semantic_layer()
    slots = {}

    # Extract number N — prefer larger numbers for "топ N", avoid confusing with periods
    n_match = re.search(r"\bтоп[\-\s]+(\d+)\b|\bлучш[а-яё]*\s+(\d+)\b|^(\d+)\b", text)
    if n_match:
        n_val = next(v for v in n_match.groups() if v is not None)
        slots["n"] = int(n_val)
    else:
        plain = re.search(r"\b(\d+)\b", text)
        if plain:
            slots["n"] = int(plain.group(1))

    # Extract metric
    for metric_name in sl.metrics:
        synonyms_for_metric = sl.synonyms.get(metric_name, [])
        if metric_name in text or any(s in text for s in synonyms_for_metric):
            slots["metric"] = metric_name
            break

    # Named periods take priority, dynamic period only as fallback
    for period_name in sl.periods:
        if period_name in text:
            slots["period"] = period_name
            break
    if "period" not in slots:
        dyn_key = _resolve_dynamic_period(text)
        if dyn_key:
            _register_dynamic_period(dyn_key)
            slots["period"] = dyn_key

    # Extract city_id for city filter
    lower = text.lower()
    for stem, city_id in _RUSSIAN_CITIES.items():
        if stem in lower:
            slots["city_id"] = city_id
            break

    # Extract group dimension
    for dim_name, dim in sl.dimensions.items():
        stem = dim_name[:5] if len(dim_name) >= 5 else dim_name
        if stem in text or dim_name in text:
            slots["group_by"] = dim.column
            break
    if "group_by" not in slots:
        slots["group_by"] = "city_id"

    # Period comparison
    if template.id == "period_comparison":
        period_keys = list(sl.periods.keys())
        found_periods = [p for p in period_keys if p in text]
        if len(found_periods) >= 2:
            slots["period_a"] = found_periods[0]
            slots["period_b"] = found_periods[1]
        else:
            slots["period_a"] = "эта неделя"
            slots["period_b"] = "прошлая неделя"

    return slots


def _keyword_shortcut(text: str) -> tuple[Template | None, float]:
    """Return a template if an unambiguous keyword phrase is found in text."""
    tmpl_map = {t.id: t for t in ALL_TEMPLATES}
    text_lower = text.lower()
    for phrases, tmpl_id in _KEYWORD_SHORTCUTS:
        for phrase in phrases:
            if phrase in text_lower:
                t = tmpl_map.get(tmpl_id)
                if t:
                    logger.debug("Router: keyword shortcut '%s' → %s", phrase, tmpl_id)
                    return t, 1.0
    return None, 0.0


async def route_query(text: str, force_llm: bool = False) -> RouteResult:
    if force_llm:
        return RouteResult(path="llm")

    # Queries with numeric thresholds must go to LLM — templates can't handle HAVING/WHERE N
    if _THRESHOLD_RE.search(text):
        logger.debug("Router: threshold detected → LLM")
        return RouteResult(path="llm")

    # Keyword shortcuts take priority over embeddings for unambiguous phrases
    template, score = _keyword_shortcut(text)
    if template:
        slots = _extract_slots_simple(text, template)
        return RouteResult(path="template", template=template, slots=slots, score=score)

    template, score = _best_template_match(text)
    threshold = settings.template_match_threshold

    if template and score >= threshold:
        slots = _extract_slots_simple(text, template)
        return RouteResult(path="template", template=template, slots=slots, score=score)

    return RouteResult(path="llm", score=score)
