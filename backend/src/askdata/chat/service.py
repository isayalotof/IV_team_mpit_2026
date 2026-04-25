from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from askdata.chat.models import ChatSession, ChatMessage
from datetime import datetime, timezone


async def get_or_create_session(db: AsyncSession, session_id: str, user_id: int) -> ChatSession:
    row = await db.get(ChatSession, session_id)
    if row is None:
        row = ChatSession(id=session_id, user_id=user_id)
        db.add(row)
        await db.flush()
    return row


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    query_response: dict | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        query_response=query_response,
    )
    db.add(msg)
    # Touch session updated_at
    session = await db.get(ChatSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
        # Auto-title from first user message
        if role == "user" and not session.title:
            session.title = content[:80]
    await db.flush()
    return msg


async def get_history(db: AsyncSession, session_id: str, limit: int = 12) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    msgs = result.scalars().all()
    return list(reversed(msgs))


async def get_user_sessions(db: AsyncSession, user_id: int) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, session_id: str, user_id: int) -> bool:
    row = await db.get(ChatSession, session_id)
    if row is None or row.user_id != user_id:
        return False
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.delete(row)
    return True
