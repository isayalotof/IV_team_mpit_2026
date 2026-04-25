"""Admin routes for managing RAG few-shot examples."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from askdata.auth.deps import require_role
from askdata.rag.store import list_examples, add_example, delete_example, count_by_source

router = APIRouter(prefix="/admin/rag", tags=["admin"])


class RagExampleIn(BaseModel):
    question: str
    sql: str


@router.get("")
async def get_rag_examples(_=Depends(require_role("admin"))):
    examples = await asyncio.to_thread(list_examples)
    stats = await asyncio.to_thread(count_by_source)
    return {"examples": examples, "stats": stats}


@router.post("")
async def create_rag_example(body: RagExampleIn, _=Depends(require_role("admin"))):
    try:
        row_id = await asyncio.to_thread(add_example, body.question, body.sql, "manual", 1.0)
        return {"id": row_id, "ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{example_id}")
async def remove_rag_example(example_id: int, _=Depends(require_role("admin"))):
    deleted = await asyncio.to_thread(delete_example, example_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Example not found")
    return {"ok": True}
