"""FastAPI application: lifespan, error envelope, request ids, health check."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import engine
from app.integrations.qdrant import close_qdrant_client, get_qdrant_client
from app.integrations.redis import close_redis_client, get_redis_client

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_qdrant_client()
    await close_redis_client()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Give every request an id, echoed in the response and in error bodies."""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"down: {exc}"


async def _check_redis() -> str:
    try:
        await get_redis_client().ping()
        return "ok"
    except Exception as exc:
        return f"down: {exc}"


async def _check_qdrant() -> str:
    try:
        await get_qdrant_client().get_collections()
        return "ok"
    except Exception as exc:
        return f"down: {exc}"


@app.get("/health", tags=["health"])
async def health() -> JSONResponse:
    """Report the state of every backing service. 503 when any one is down."""
    checks = {
        "postgres": await _check_postgres(),
        "redis": await _check_redis(),
        "qdrant": await _check_qdrant(),
    }
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "checks": checks,
        },
    )
