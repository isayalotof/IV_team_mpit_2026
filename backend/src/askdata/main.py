from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from askdata.config import get_settings
from askdata.db.meta import init_db
from askdata.db.target import close_pool
from askdata.limiter import limiter
from askdata.schedules.scheduler import start_scheduler, stop_scheduler
from askdata.semantic.loader import load_semantic_layer

settings = get_settings()


async def _reload_schedule_jobs():
    from askdata.db.meta import async_session
    from askdata.schedules.models import Schedule
    from askdata.schedules.scheduler import add_schedule_job
    from sqlalchemy import select
    try:
        async with async_session() as db:
            result = await db.execute(select(Schedule).where(Schedule.enabled == True))  # noqa: E712
            schedules = result.scalars().all()
            for s in schedules:
                add_schedule_job(s.id, s.cron, s.timezone)
            print(f"Scheduler: reloaded {len(schedules)} jobs")
    except Exception as e:
        print(f"Warning: could not reload schedule jobs: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.secret_key.startswith("dev-") and not settings.demo_mode:
        raise RuntimeError(
            "Insecure SECRET_KEY detected: set the SECRET_KEY environment variable before running in production. "
            "Set DEMO_MODE=true to suppress this check in demo environments."
        )
    await init_db()
    try:
        load_semantic_layer()
    except Exception as e:
        print(f"Warning: could not load semantic layer: {e}")
    start_scheduler()
    await _reload_schedule_jobs()
    # Warm up RAG, pre-load embedding model, and build template routing cache
    import asyncio as _asyncio
    _asyncio.create_task(_warmup_rag())
    # Start interactive Telegram bot in background
    _asyncio.create_task(_start_telegram_bot())
    yield
    # Shutdown
    stop_scheduler()
    await close_pool()


app = FastAPI(
    title="AskData API",
    description="NL→SQL self-service analytics platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
async def _start_telegram_bot():
    try:
        from askdata.telegram.bot import run_bot
        await run_bot()
    except Exception as e:
        import traceback
        print(f"Warning: Telegram bot failed: {e}")
        traceback.print_exc()


async def _warmup_rag():
    try:
        import asyncio
        from askdata.rag.store import seed_if_empty, _get_model
        await asyncio.to_thread(seed_if_empty)
        await asyncio.to_thread(_get_model)
        print("RAG: ready")
    except Exception as e:
        import traceback
        print(f"Warning: RAG warmup failed: {e}")
        traceback.print_exc()
    # Build template embedding cache after model is loaded
    try:
        import asyncio
        from askdata.query.router import _build_template_emb_cache
        await asyncio.to_thread(_build_template_emb_cache)
        print("Router: embedding cache ready")
    except Exception as e:
        print(f"Warning: Router embedding cache failed: {e}")


from askdata.auth.routes import router as auth_router
from askdata.query.routes import router as query_router
from askdata.reports.routes import router as reports_router
from askdata.schedules.routes import router as schedules_router
from askdata.semantic.routes import router as semantic_router
from askdata.audit.routes import router as audit_router
from askdata.chat.routes import router as chat_router
from askdata.voice.routes import router as voice_router
from askdata.rag.routes import router as rag_router
from askdata.dashboards.routes import router as dashboards_router

PREFIX = "/api/v1"
app.include_router(auth_router, prefix=PREFIX)
app.include_router(query_router, prefix=PREFIX)
app.include_router(reports_router, prefix=PREFIX)
app.include_router(schedules_router, prefix=PREFIX)
app.include_router(semantic_router, prefix=PREFIX)
app.include_router(audit_router, prefix=PREFIX)
app.include_router(chat_router, prefix=PREFIX)
app.include_router(voice_router, prefix=PREFIX)
app.include_router(rag_router, prefix=PREFIX)
app.include_router(dashboards_router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "demo_mode": settings.demo_mode}


@app.get(f"{PREFIX}/health")
async def health_detailed():
    from askdata.query.llm.provider import get_provider
    llm_status = "unknown"
    try:
        provider = get_provider()
        if hasattr(provider, "is_available"):
            available = await provider.is_available()
            llm_status = "ok" if available else "unavailable"
        else:
            llm_status = "ok"
    except Exception as e:
        llm_status = f"error: {e}"
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_status": llm_status,
        "demo_mode": settings.demo_mode,
    }
