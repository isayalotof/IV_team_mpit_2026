from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from askdata.auth.deps import require_role
from askdata.auth.models import User
from askdata.audit.models import QueryAudit
from askdata.db.meta import get_session

router = APIRouter(prefix="/admin/audit", tags=["admin"])


@router.get("")
async def get_audit_log(
    limit: int = 50,
    current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(QueryAudit).order_by(desc(QueryAudit.created_at)).limit(limit)
    )
    records = result.scalars().all()
    return {
        "logs": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "question": r.question,
                "sql_source": r.sql_source,
                "confidence": r.confidence,
                "rows_returned": r.rows_returned,
                "violations": r.violations,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }
