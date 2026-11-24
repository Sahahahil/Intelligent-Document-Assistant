"""Shared fixtures: the HTTP client, the service doubles and the live stack.

The unit suite uses only the doubles — no PostgreSQL, no Redis, no Qdrant and
no network. The live fixtures are used by the `integration`-marked tests, which
are deselected by default.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from tests.fakes import FakeEmbeddingService, FakeLLM, FakeVectorStore


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client that talks to the app in-process — no socket, no server."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def fake_embedding_service() -> FakeEmbeddingService:
    return FakeEmbeddingService()


@pytest.fixture
def fake_vector_store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM("the answer")


@pytest.fixture
def session_id() -> str:
    """A conversation id of this test's own — no key is ever shared."""
    return f"test-{uuid4().hex}"


@pytest.fixture
def collection() -> str:
    """A Qdrant collection name of this test's own."""
    return f"documents-{uuid4().hex[:8]}"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session on an empty database.

    The repositories commit their own transactions, so the rows are deleted
    instead of rolled back.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM bookings"))
        await session.execute(text("DELETE FROM documents"))
        await session.commit()
        yield session
        # And again afterwards, so a test run leaves no rows in the database
        # the app reads from.
        await session.execute(text("DELETE FROM bookings"))
        await session.execute(text("DELETE FROM documents"))
        await session.commit()
    # Each test runs in its own event loop, so pooled connections from the
    # previous loop must not be reused.
    await engine.dispose()


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def qdrant_client(tmp_path: Path) -> AsyncIterator[AsyncQdrantClient]:
    """An embedded Qdrant in a temporary folder — gone when the test ends."""
    client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    yield client
    await client.close()
