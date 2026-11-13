"""Redis client factory (conversation memory)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import UpstreamError


@lru_cache
def get_redis_client() -> Redis:
    """One client for the process, so the connection pool is reused."""
    return Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)


async def close_redis_client() -> None:
    await get_redis_client().aclose()


@asynccontextmanager
async def redis_guard() -> AsyncIterator[None]:
    """Turn any Redis failure into an `UpstreamError` (502)."""
    try:
        yield
    except RedisError as exc:
        raise UpstreamError(f"Redis error: {exc}") from exc
