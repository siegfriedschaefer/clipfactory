from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from apps.api.config import settings
from apps.api.database import async_session_factory

app = FastAPI(
    title="ClipFabric API",
    description="Local MVP for long-form video analysis and viral clip generation.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Liveness probe — returns 200 when the API process is running."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/ready", tags=["system"])
async def ready() -> dict:
    """Readiness probe — verifies DB connectivity."""
    async with async_session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
