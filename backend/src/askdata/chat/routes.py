from fastapi import APIRouter, Depends, HTTPException
from askdata.auth.deps import require_role
from askdata.auth.models import User
from askdata.db.meta import get_session
from askdata.chat.service import get_user_sessions, get_history, delete_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    current_user: User = Depends(require_role("analyst")),
    db: AsyncSession = Depends(get_session),
):
    sessions = await get_user_sessions(db, current_user.id)
    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title or "Новый чат",
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: str,
    current_user: User = Depends(require_role("analyst")),
    db: AsyncSession = Depends(get_session),
):
    from askdata.chat.models import ChatSession
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    messages = await get_history(db, session_id, limit=100)
    return {
        "session_id": session_id,
        "title": session.title or "Новый чат",
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "query_response": m.query_response,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.delete("/{session_id}")
async def remove_session(
    session_id: str,
    current_user: User = Depends(require_role("analyst")),
    db: AsyncSession = Depends(get_session),
):
    ok = await delete_session(db, session_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    await db.commit()
    return {"ok": True}
