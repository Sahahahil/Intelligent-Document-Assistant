"""Ingestion service tests against a real PostgreSQL database and Qdrant.

Run with:  uv run pytest -m integration

The embedder is a fake — the real model would download ~90 MB and slow the
suite down for no extra coverage here.
"""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.base import DocumentChunk
from app.core.exceptions import ConflictError, UpstreamError
from app.db.session import AsyncSessionLocal, engine
from app.integrations.qdrant import VectorStore
from app.models.document import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService

pytestmark = pytest.mark.integration

VECTOR_SIZE = 384


class FakeEmbeddingService:
    """Deterministic unit vectors — no model download needed."""

    model_name = "fake-model"
    dimension = VECTOR_SIZE

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * VECTOR_SIZE for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * VECTOR_SIZE


class FailingVectorStore(VectorStore):
    """A store whose writes always fail."""

    async def upsert_chunks(
        self,
        *,
        document_id: UUID,
        filename: str,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
        extra: dict[str, object] | None = None,
    ) -> int:
        raise UpstreamError("qdrant is down")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db_session:
        await db_session.execute(text("DELETE FROM documents"))
        await db_session.commit()
        yield db_session
    await engine.dispose()


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncQdrantClient]:
    qdrant_client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    yield qdrant_client
    await qdrant_client.close()


@pytest.fixture
async def store(client: AsyncQdrantClient) -> AsyncIterator[VectorStore]:
    vector_store = VectorStore(client, "documents", VECTOR_SIZE)
    await vector_store.ensure_collection()
    yield vector_store


@pytest.fixture
def failing_store(client: AsyncQdrantClient) -> VectorStore:
    return FailingVectorStore(client, "documents", VECTOR_SIZE)


def make_service(session: AsyncSession, store: VectorStore) -> IngestionService:
    return IngestionService(
        document_repo=DocumentRepository(session),
        vector_store=store,
        embedding_service=cast(EmbeddingService, FakeEmbeddingService()),
    )


def payload() -> bytes:
    """Content unique to each test, so the unique file_hash never clashes."""
    return f"Machine learning is a field of study. {uuid4().hex}".encode()


async def test_a_document_is_ingested_end_to_end(session: AsyncSession, store: VectorStore) -> None:
    service = make_service(session, store)

    result = await service.ingest(
        filename="notes.txt",
        content_type="text/plain",
        data=payload(),
        chunking_strategy="recursive",
    )

    assert result.status == "completed"
    assert result.total_chunks > 0

    document = await DocumentRepository(session).get(result.document_id)
    assert document is not None
    assert document.status == DocumentStatus.COMPLETED
    assert document.total_chunks == result.total_chunks
    assert document.chunking_strategy == "recursive"

    # The two stores agree.
    assert await store.count_document(result.document_id) == result.total_chunks


async def test_the_same_content_twice_is_a_conflict(
    session: AsyncSession, store: VectorStore
) -> None:
    service = make_service(session, store)
    data = payload()
    await service.ingest(
        filename="notes.txt", content_type="text/plain", data=data, chunking_strategy="recursive"
    )

    with pytest.raises(ConflictError):
        await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            data=data,
            chunking_strategy="recursive",
        )

    rows, total = await DocumentRepository(session).list()
    assert total == 1
    assert len(rows) == 1


async def test_a_failed_upload_leaves_a_failed_row_and_no_vectors(
    session: AsyncSession, store: VectorStore, failing_store: VectorStore
) -> None:
    service = make_service(session, failing_store)

    with pytest.raises(UpstreamError):
        await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            data=payload(),
            chunking_strategy="recursive",
        )

    rows, total = await DocumentRepository(session).list()
    assert total == 1
    assert rows[0].status == DocumentStatus.FAILED
    assert rows[0].error_message
    assert await store.count_document(rows[0].id) == 0


async def test_a_failed_upload_can_be_retried(
    session: AsyncSession, store: VectorStore, failing_store: VectorStore
) -> None:
    data = payload()
    broken = make_service(session, failing_store)
    with pytest.raises(UpstreamError):
        await broken.ingest(
            filename="notes.txt",
            content_type="text/plain",
            data=data,
            chunking_strategy="recursive",
        )

    service = make_service(session, store)
    result = await service.ingest(
        filename="notes.txt", content_type="text/plain", data=data, chunking_strategy="recursive"
    )

    assert result.status == "completed"
    rows, total = await DocumentRepository(session).list()
    assert total == 1
    assert rows[0].status == DocumentStatus.COMPLETED
    assert await store.count_document(result.document_id) == result.total_chunks
