from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.core.config import settings


async def _register_webhook():
    if settings.telegram_bot_token and settings.telegram_webhook_url:
        import httpx
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"url": settings.telegram_webhook_url})
            print(f"Webhook registration: {resp.json()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    await init_db()
    from app.services.bake_orchestrator import fail_orphaned_bakes
    recovered = await fail_orphaned_bakes()
    if recovered:
        print(f"Recovered {recovered} orphaned bake job(s) on startup")

    from app.services.worker import requeue_stranded_jobs, worker_loop
    requeued = await requeue_stranded_jobs()
    if requeued:
        print(f"Re-queued {requeued} stranded inbound job(s) on startup")
    worker_task = asyncio.create_task(worker_loop())

    def _log_worker_crash(task: "asyncio.Task") -> None:
        if not task.cancelled() and task.exception() is not None:
            import logging
            logging.getLogger("app.worker").error(
                "Worker loop crashed", exc_info=task.exception()
            )
    worker_task.add_done_callback(_log_worker_crash)

    await _register_webhook()
    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="AI Diary API",
    description="Інтелектуальний застосунок для ведення особистого щоденника",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Vue.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.auth import router as auth_router
from app.api.buffer import router as buffer_router
from app.api.entries import router as entries_router
from app.api.highlights import router as highlights_router
from app.api.webhook import router as webhook_router
from app.api.sse import router as sse_router
from app.api.settings import router as settings_router
from app.api.media import router as media_router

app.include_router(auth_router)
app.include_router(buffer_router)
app.include_router(entries_router)
app.include_router(highlights_router)
app.include_router(webhook_router)
app.include_router(sse_router)
app.include_router(settings_router)
app.include_router(media_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
