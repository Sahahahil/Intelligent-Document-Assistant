"""Ingestion service tests.

The repository, the vector store and the embedder are fakes here — the real
ones are exercised in `tests/integration/test_ingestion_service.py`.

The pipeline runs in the background: `start` writes the row and returns it,
and the tests wait for the row to reach its final state.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    PayloadTooLargeError,
    UnsupportedFileTypeError,
    ValidationError,
)
from app.integrations.qdrant import VectorStore
from app.models.document import Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from tests.fakes import FakeEmbeddingService, FakeVectorStore

TEXT = ("Machine learning is a field of study. " * 60).encode()
DIMENSION = 384


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[UUID, Document] = {}
        self.create_error: Exception | None = None
        # Set when the pipeline reaches the end of a row, one way or the other.
        self.finished = asyncio.Event()

    async def get_by_hash(self, file_hash: str) -> Document | None:
        return next((d for d in self.documents.values() if d.file_hash == file_hash), None)

    async def create(self, document: Document) -> Document:
        if self.create_error is not None:
            raise self.create_error
        self.documents[document.id] = document
        return document

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        total_chunks: int | None = None,
        error_message: str | None = None,
    ) -> bool:
        document = self.documents.get(document_id)
        if document is None:
            return False
        document.status = status
        if total_chunks is not None:
            document.total_chunks = total_chunks
        if error_message is not None:
            document.error_message = error_message
        if status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            self.finished.set()
        return True

    async def delete(self, document_id: UUID) -> bool:
        return self.documents.pop(document_id, None) is not None


class FakeRedis:
    """Just enough Redis for the progress."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.data[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.data.pop(key, None) is not None else 0


class FakeSession:
    """The session the background pipeline opens for itself."""

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class Boom(RuntimeError):
    pass


@pytest.fixture
def repo() -> FakeDocumentRepository:
    return FakeDocumentRepository()


@pytest.fixture
def store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
def embedder() -> FakeEmbeddingService:
    return FakeEmbeddingService(dimension=DIMENSION)


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def service(
    repo: FakeDocumentRepository,
    store: FakeVectorStore,
    embedder: FakeEmbeddingService,
    redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> IngestionService:
    # The pipeline runs in the background and opens its own session and
    # repository, so both are pointed at the fakes here.
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        "app.repositories.document_repository.DocumentRepository", lambda session: repo
    )
    return IngestionService(
        document_repo=cast(DocumentRepository, repo),
        vector_store=cast(VectorStore, store),
        embedding_service=cast(EmbeddingService, embedder),
        redis=cast(Redis, redis),
    )


async def ingest(
    service: IngestionService,
    repo: FakeDocumentRepository,
    data: bytes = TEXT,
    *,
    filename: str = "notes.txt",
    chunking_strategy: str = "recursive",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> Document:
    """Start an ingestion and wait for the pipeline to finish with it."""
    document = await service.start(
        filename=filename,
        content_type="text/plain",
        data=data,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    await asyncio.wait_for(repo.finished.wait(), timeout=30)
    repo.finished.clear()
    return document


async def test_a_valid_text_file_is_ingested(
    service: IngestionService, repo: FakeDocumentRepository, store: FakeVectorStore
) -> None:
    document = await ingest(service, repo)

    assert document.status == DocumentStatus.COMPLETED
    assert document.total_chunks > 0
    assert document.chunking_strategy == "recursive"
    assert len(repo.documents) == 1
    assert len(store.upserts) == 1


async def test_the_same_file_twice_is_a_conflict(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, repo)

    with pytest.raises(ConflictError):
        await ingest(service, repo)

    assert len(repo.documents) == 1


async def test_a_failed_file_can_be_retried(
    service: IngestionService, repo: FakeDocumentRepository, store: FakeVectorStore
) -> None:
    store.upsert_error = Boom("qdrant is down")

    await ingest(service, repo)

    assert len(repo.documents) == 1
    assert next(iter(repo.documents.values())).status == DocumentStatus.FAILED

    store.upsert_error = None
    document = await ingest(service, repo)

    assert document.status == DocumentStatus.COMPLETED
    assert len(repo.documents) == 1


async def test_an_unsupported_extension_is_rejected(service: IngestionService) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        await service.start(
            filename="virus.exe",
            content_type="application/octet-stream",
            data=b"MZ",
            chunking_strategy="recursive",
        )


async def test_an_empty_file_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await service.start(
            filename="notes.txt",
            content_type="text/plain",
            data=b"",
            chunking_strategy="recursive",
        )


async def test_an_oversized_file_is_rejected(service: IngestionService) -> None:
    with pytest.raises(PayloadTooLargeError):
        await service.start(
            filename="notes.txt",
            content_type="text/plain",
            data=b"x" * (21 * 1024 * 1024),
            chunking_strategy="recursive",
        )


async def test_a_file_without_text_fails_and_marks_the_row(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, repo, data=b"   \n\n  ")

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message


async def test_a_failing_upsert_marks_the_row_and_cleans_up(
    service: IngestionService,
    repo: FakeDocumentRepository,
    store: FakeVectorStore,
) -> None:
    store.upsert_error = Boom("qdrant is down")

    await ingest(service, repo)

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "qdrant is down"
    assert store.deleted == [document.id]


async def test_a_failing_embedder_marks_the_row(
    service: IngestionService, repo: FakeDocumentRepository, embedder: FakeEmbeddingService
) -> None:
    embedder.error = Boom("model exploded")

    await ingest(service, repo)

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "model exploded"


async def test_the_embedding_model_is_recorded(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, repo)

    document = next(iter(repo.documents.values()))
    assert document.embedding_model == "fake-model"
    assert document.embedding_dim == DIMENSION


async def test_the_chunk_parameters_are_recorded(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, repo, chunk_size=50, chunk_overlap=10)

    document = next(iter(repo.documents.values()))
    assert document.chunk_size == 50
    assert document.chunk_overlap == 10


async def test_a_zero_chunk_size_means_the_default(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    """An empty number field in the API docs is sent as 0 - that is "not set"."""
    await ingest(service, repo, chunk_size=0, chunk_overlap=0)

    document = next(iter(repo.documents.values()))
    assert document.chunk_size == get_settings().chunk_size
    assert document.chunk_overlap == get_settings().chunk_overlap


async def test_a_smaller_chunk_size_makes_more_chunks(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    big = await ingest(service, repo, chunk_size=500, chunk_overlap=50)
    # Different bytes, so this is a different document and not a duplicate.
    small = await ingest(
        service,
        repo,
        data=b"Machine learning is a field of study. " * 61,
        chunk_size=50,
        chunk_overlap=10,
    )

    assert small.total_chunks > big.total_chunks


async def test_an_unknown_strategy_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await service.start(
            filename="notes.txt",
            content_type="text/plain",
            data=TEXT,
            chunking_strategy="magic",
        )


async def test_an_invalid_overlap_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await service.start(
            filename="notes.txt",
            content_type="text/plain",
            data=TEXT,
            chunking_strategy="recursive",
            chunk_size=10,
            chunk_overlap=10,
        )


async def test_a_hash_race_becomes_a_conflict(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    repo.create_error = IntegrityError("insert", {}, Exception("duplicate key"))

    with pytest.raises(ConflictError):
        await service.start(
            filename="notes.txt",
            content_type="text/plain",
            data=TEXT,
            chunking_strategy="recursive",
        )


async def test_nothing_is_written_to_disk(
    service: IngestionService, repo: FakeDocumentRepository, tmp_path: Path
) -> None:
    before = sorted(path.name for path in tmp_path.iterdir())

    await ingest(service, repo)

    assert sorted(path.name for path in tmp_path.iterdir()) == before


async def test_the_file_hash_is_the_sha256_of_the_bytes(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, repo)

    document = next(iter(repo.documents.values()))
    assert document.file_hash == hashlib.sha256(TEXT).hexdigest()
