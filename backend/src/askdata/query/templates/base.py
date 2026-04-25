from dataclasses import dataclass, field
from datetime import date, timedelta
from askdata.semantic.loader import get_semantic_layer


@dataclass
class Template:
    id: str
    title: str
    description: str
    examples: list[str]
    slots: list[str]

    def render(self, slots: dict) -> str:
        raise NotImplementedError


def resolve_period(period_name: str) -> tuple[str, str]:
    """Returns (start_expr, end_expr) for PostgreSQL WHERE clause."""
    sl = get_semantic_layer()
    period_def = sl.periods.get(period_name)
    if period_def:
        if hasattr(period_def, "start") and period_def.start:
            return period_def.start, period_def.end
        # clause-based periods fall through to hardcoded defaults below
    defaults = {
        "сегодня": ("CURRENT_DATE", "CURRENT_DATE + INTERVAL '1 day'"),
        "вчера": ("CURRENT_DATE - 1", "CURRENT_DATE"),
        "эта неделя": ("DATE_TRUNC('week', NOW())", "NOW()"),
        "прошлая неделя": ("DATE_TRUNC('week', NOW() - INTERVAL '1 week')", "DATE_TRUNC('week', NOW())"),
        "этот месяц": ("DATE_TRUNC('month', NOW())", "NOW()"),
        "прошлый месяц": ("DATE_TRUNC('month', NOW() - INTERVAL '1 month')", "DATE_TRUNC('month', NOW())"),
        "последние 30 дней": ("NOW() - INTERVAL '30 days'", "NOW()"),
        "последние 7 дней": ("NOW() - INTERVAL '7 days'", "NOW()"),
        "этот год": ("DATE_TRUNC('year', NOW())", "NOW()"),
    }
    return defaults.get(period_name, ("NOW() - INTERVAL '30 days'", "NOW()"))
