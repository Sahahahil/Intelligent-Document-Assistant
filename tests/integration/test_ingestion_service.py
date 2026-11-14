"""Ingestion service tests against a real PostgreSQL database and Qdrant.

Run with:  uv run pytest -m integration

The embedder is a fake — the real model would download ~90 MB and slow the
suite down for no extra coverage here.
"""

from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import UUID, uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.base import DocumentChunk
from app.core.exceptions import ConflictError, UpstreamError
from app.integrations.qdrant import VectorStore
from app.models.document import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.integration

VECTOR_SIZE = 384


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
async def store(qdrant_client: AsyncQdrantClient, collection: str) -> AsyncIterator[VectorStore]:
    vector_store = VectorStore(qdrant_client, collection, VECTOR_SIZE)
    await vector_store.ensure_collection()
    yield vector_store


@pytest.fixture
def failing_store(qdrant_client: AsyncQdrantClient, collection: str) -> VectorStore:
    return FailingVectorStore(qdrant_client, collection, VECTOR_SIZE)


def make_service(db_session: AsyncSession, store: VectorStore) -> IngestionService:
    return IngestionService(
        document_repo=DocumentRepository(db_session),
        vector_store=store,
        embedding_service=cast(EmbeddingService, FakeEmbeddingService(dimension=VECTOR_SIZE)),
    )


def payload() -> bytes:
    """Content unique to each test, so the unique file_hash never clashes."""
    return f"Machine learning is a field of study. {uuid4().hex}".encode()


async def test_a_document_is_ingested_end_to_end(
    db_session: AsyncSession, store: VectorStore
) -> None:
    service = make_service(db_session, store)

    result = await service.ingest(
        filename="notes.txt",
        content_type="text/plain",
        data=payload(),
        chunking_strategy="recursive",
    )

    assert result.status == "completed"
    assert result.total_chunks > 0

    document = await DocumentRepository(db_session).get(result.document_id)
    assert document is not None
    assert document.status == DocumentStatus.COMPLETED
    assert document.total_chunks == result.total_chunks
    assert document.chunking_strategy == "recursive"

    # The two stores agree.
    assert await store.count_document(result.document_id) == result.total_chunks


async def test_the_same_content_twice_is_a_conflict(
    db_session: AsyncSession, store: VectorStore
) -> None:
    service = make_service(db_session, store)
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

    rows, total = await DocumentRepository(db_session).list()
    assert total == 1
    assert len(rows) == 1


async def test_a_failed_upload_leaves_a_failed_row_and_no_vectors(
    db_session: AsyncSession, store: VectorStore, failing_store: VectorStore
) -> None:
    service = make_service(db_session, failing_store)

    with pytest.raises(UpstreamError):
        await service.ingest(
            filename="notes.txt",
            content_type="text/plain",
            data=payload(),
            chunking_strategy="recursive",
        )

    rows, total = await DocumentRepository(db_session).list()
    assert total == 1
    assert rows[0].status == DocumentStatus.FAILED
    assert rows[0].error_message
    assert await store.count_document(rows[0].id) == 0


async def test_a_failed_upload_can_be_retried(
    db_session: AsyncSession, store: VectorStore, failing_store: VectorStore
) -> None:
    data = payload()
    broken = make_service(db_session, failing_store)
    with pytest.raises(UpstreamError):
        await broken.ingest(
            filename="notes.txt",
            content_type="text/plain",
            data=data,
            chunking_strategy="recursive",
        )

    service = make_service(db_session, store)
    result = await service.ingest(
        filename="notes.txt", content_type="text/plain", data=data, chunking_strategy="recursive"
    )

    assert result.status == "completed"
    rows, total = await DocumentRepository(db_session).list()
    assert total == 1
    assert rows[0].status == DocumentStatus.COMPLETED
    assert await store.count_document(result.document_id) == result.total_chunks
