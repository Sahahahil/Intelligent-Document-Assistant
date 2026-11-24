"""Liveness and readiness probes.

Two different questions, two different endpoints:

- `/health` — is the process up? Deliberately touches nothing: a liveness
  probe that depends on the database restarts a healthy container every time
  the database blips.
- `/ready` — can this process actually serve a request? Every dependency the
  API needs (PostgreSQL, Redis, Qdrant) is probed with a short timeout, and
  the answer is 503 if any of them is unreachable.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db.session import engine
from app.integrations.qdrant import get_qdrant_client, qdrant_guard
from app.integrations.redis import get_redis_client, redis_guard

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

# A readiness probe has to answer fast: it is polled every few seconds and a
# hung probe is worse than a failed one.
PROBE_TIMEOUT_SECONDS = 3.0


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """The process is up and serving."""
    return {"status": "ok"}


async def _check_postgres() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _check_redis() -> None:
    async with redis_guard():
        await get_redis_client().ping()


async def _check_qdrant() -> None:
    async with qdrant_guard():
        # Server-level call on purpose: the collection is created lazily on
        # the first ingest, so asking for it would report a fresh install as
        # "not ready".
        await get_qdrant_client().get_collections()


async def _probe(name: str, check: Callable[[], Awaitable[None]]) -> str:
    """Run one check. Returns `ok`, or the exception type that failed.

    Only the exception *type* is reported: a database error message can
    contain the connection string, and this endpoint is unauthenticated. The
    detail goes to the log instead.
    """
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            await check()
    except Exception as exc:
        logger.warning("readiness probe failed: %s", name, exc_info=True)
        return f"error: {type(exc).__name__}"
    return "ok"


@router.get("/ready", summary="Readiness probe")
async def ready(response: Response) -> dict[str, object]:
    """Every dependency is reachable, so a request can be served."""
    # Concurrently, not one after another: the checks are independent, and
    # running them in sequence would let a dead dependency eat the whole
    # timeout budget before the healthy ones are even tried.
    names = ("postgres", "redis", "qdrant")
    results = await asyncio.gather(
        _probe("postgres", _check_postgres),
        _probe("redis", _check_redis),
        _probe("qdrant", _check_qdrant),
    )
    checks = dict(zip(names, results, strict=True))
    is_ready = all(value == "ok" for value in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if is_ready else "not_ready", "checks": checks}
