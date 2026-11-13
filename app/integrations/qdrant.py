"""Qdrant client factory (vector store).

Embedded by default: `AsyncQdrantClient(path=...)` runs Qdrant on disk with no
server process. Set `QDRANT_URL` to point at a Qdrant server instead.
"""

from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    """One client for the process — embedded mode takes a lock on its path."""
    settings = get_settings()
    if settings.qdrant_url:
        return AsyncQdrantClient(url=settings.qdrant_url)
    return AsyncQdrantClient(path=settings.qdrant_path)


async def close_qdrant_client() -> None:
    await get_qdrant_client().close()
