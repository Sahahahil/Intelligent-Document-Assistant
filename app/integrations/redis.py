"""Redis client factory (conversation memory)."""

from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    """One client for the process, so the connection pool is reused."""
    return Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)


async def close_redis_client() -> None:
    await get_redis_client().aclose()
