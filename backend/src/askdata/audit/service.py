from sqlalchemy.ext.asyncio import AsyncSession
from askdata.audit.models import QueryAudit


async def log_query(
    session: AsyncSession,
    user_id: int,
    question: str,
    sql: str = "",
    sql_source: str = "",
    confidence: float | None = None,
    rows_returned: int | None = None,
    error: str | None = None,
    violations: list | None = None,
):
    audit = QueryAudit(
        user_id=user_id,
        question=question,
        sql_generated=sql,
        sql_source=sql_source,
        confidence=confidence,
        rows_returned=rows_returned,
        error=error,
        violations=violations,
    )
    session.add(audit)
