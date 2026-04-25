from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from askdata.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.meta_db_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    from askdata.auth.models import User
    from askdata.reports.models import SavedReport
    from askdata.schedules.models import Schedule, RunHistory
    from askdata.audit.models import QueryAudit
    from askdata.chat.models import ChatSession, ChatMessage  # noqa: F401
    from askdata.dashboards.models import Dashboard, DashboardWidget  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed demo users only when DEMO_MODE is enabled
    if settings.demo_mode:
        from askdata.auth.service import create_user_if_not_exists
        async with async_session() as session:
            await create_user_if_not_exists(session, "viewer", "viewer123", "viewer")
            await create_user_if_not_exists(session, "manager", "manager123", "analyst")
            await create_user_if_not_exists(session, "admin", "admin123", "admin")
            await session.commit()
