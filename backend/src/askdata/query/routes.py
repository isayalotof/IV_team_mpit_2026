from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from askdata.auth.deps import require_role
from askdata.auth.models import User
from askdata.query.pipeline import run_pipeline
from askdata.query.templates.catalog import ALL_TEMPLATES
from askdata.audit.service import log_query
from askdata.db.meta import get_session
from askdata.db.target import get_schema as _get_schema
from askdata.chat.service import get_or_create_session, add_message, get_history
from askdata.limiter import limiter
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    text: str
    session_id: str | None = None
    force_llm: bool = False
    mode: str = "easy"  # "easy" | "expert"


@router.post("")
@limiter.limit("30/minute")
async def query(
    request: Request,
    body: QueryRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    # Load chat history if session_id provided
    history: list[dict] | None = None
    if body.session_id:
        await get_or_create_session(session, body.session_id, current_user.id)
        raw_history = await get_history(session, body.session_id, limit=12)
        if raw_history:
            history = [{"role": m.role, "content": m.content} for m in raw_history]

    result = await run_pipeline(
        body.text,
        force_llm=body.force_llm,
        user_id=current_user.id,
        session_id=body.session_id,
        history=history,
        mode=body.mode,
    )

    # Persist messages to chat history
    if body.session_id:
        await add_message(session, body.session_id, "user", body.text)
        if result.get("status") != "error":
            import json
            assistant_content = result.get("sql") or result.get("detail") or ""
            # Serialize via json to strip non-JSON-safe types (Decimal, date, etc.)
            safe_result = json.loads(json.dumps(result, default=str))
            await add_message(session, body.session_id, "assistant", assistant_content, query_response=safe_result)

    # Audit log
    await log_query(
        session=session,
        user_id=current_user.id,
        question=body.text,
        sql=result.get("sql", ""),
        sql_source=result.get("sql_source", ""),
        confidence=result.get("confidence", {}).get("score"),
        rows_returned=result.get("data", {}).get("row_count"),
        error=result.get("detail") if result.get("status") == "error" else None,
        violations=result.get("violations"),
    )
    await session.commit()

    if result.get("status") == "error":
        error_code = result.get("error_code", "UNKNOWN_ERROR")
        status_map = {
            "INTERPRETATION_FAILED": 400,
            "GUARDRAIL_VIOLATION": 403,
            "SQL_EXECUTION_ERROR": 500,
        }
        raise HTTPException(
            status_code=status_map.get(error_code, 500),
            detail=result,
        )

    return result


@router.get("/templates")
async def get_templates(current_user: User = Depends(require_role("analyst"))):
    return {
        "templates": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "example": t.examples[0] if t.examples else "",
                "slots": t.slots,
            }
            for t in ALL_TEMPLATES
        ]
    }


@router.get("/schema")
async def get_schema(current_user: User = Depends(require_role("analyst"))):
    from askdata.db.target import get_pool
    from askdata.semantic.loader import get_semantic_layer
    try:
        schema = await _get_schema()

        # Enrich with approximate row counts
        pool = await get_pool()
        async with pool.acquire() as conn:
            for table in schema:
                try:
                    row = await conn.fetchrow(
                        "SELECT reltuples::bigint AS cnt FROM pg_class WHERE relname = $1",
                        table["name"],
                    )
                    table["row_count"] = max(0, row["cnt"]) if row else 0
                except Exception:
                    table["row_count"] = None

        # Include semantic metrics
        sl = get_semantic_layer()
        metrics = {}
        if sl:
            for name, m in sl.metrics.items():
                metrics[name] = {
                    "description": m.description,
                    "format": getattr(m, "format", None),
                }

        return {"tables": schema, "metrics": metrics}
    except Exception as e:
        return {"tables": [], "metrics": {}, "error": str(e)}
