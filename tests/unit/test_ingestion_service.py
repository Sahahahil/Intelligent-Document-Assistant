"""Ingestion service tests.

The repository, the vector store and the embedder are fakes here — the real
ones are exercised in `tests/integration/test_ingestion_service.py`.
"""

import hashlib
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.chunking.base import DocumentChunk
from app.core.exceptions import (
    ConflictError,
    ExtractionError,
    PayloadTooLargeError,
    UnsupportedFileTypeError,
    ValidationError,
)
from app.integrations.qdrant import VectorStore
from app.models.document import Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionResult, IngestionService

TEXT = ("Machine learning is a field of study. " * 60).encode()
DIMENSION = 384


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[UUID, Document] = {}
        self.create_error: Exception | None = None

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
        return True

    async def delete(self, document_id: UUID) -> bool:
        return self.documents.pop(document_id, None) is not None


class FakeVectorStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[UUID, list[DocumentChunk], dict[str, object]]] = []
        self.deleted: list[UUID] = []
        self.upsert_error: Exception | None = None

    async def ensure_collection(self) -> None:
        return None

    async def upsert_chunks(
        self,
        *,
        document_id: UUID,
        filename: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        extra: dict[str, object] | None = None,
    ) -> int:
        if self.upsert_error is not None:
            raise self.upsert_error
        self.upserts.append((document_id, chunks, extra or {}))
        return len(chunks)

    async def delete_document(self, document_id: UUID) -> None:
        self.deleted.append(document_id)


class FakeEmbeddingService:
    model_name = "fake-model"
    dimension = DIMENSION

    def __init__(self) -> None:
        self.error: Exception | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.error is not None:
            raise self.error
        return [[0.1] * DIMENSION for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * DIMENSION


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
    return FakeEmbeddingService()


@pytest.fixture
def service(
    repo: FakeDocumentRepository, store: FakeVectorStore, embedder: FakeEmbeddingService
) -> IngestionService:
    return IngestionService(
        document_repo=cast(DocumentRepository, repo),
        vector_store=cast(VectorStore, store),
        embedding_service=cast(EmbeddingService, embedder),
    )


async def ingest(
    service: IngestionService,
    data: bytes = TEXT,
    *,
    filename: str = "notes.txt",
    chunking_strategy: str = "recursive",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> IngestionResult:
    return await service.ingest(
        filename=filename,
        content_type="text/plain",
        data=data,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


async def test_a_valid_text_file_is_ingested(
    service: IngestionService, repo: FakeDocumentRepository, store: FakeVectorStore
) -> None:
    result = await ingest(service)

    assert result.status == "completed"
    assert result.total_chunks > 0
    assert result.chunking_strategy == "recursive"
    assert len(repo.documents) == 1
    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.COMPLETED
    assert document.total_chunks == result.total_chunks
    assert len(store.upserts) == 1


async def test_the_same_file_twice_is_a_conflict(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service)

    with pytest.raises(ConflictError):
        await ingest(service)

    assert len(repo.documents) == 1


async def test_a_failed_file_can_be_retried(
    service: IngestionService, repo: FakeDocumentRepository, store: FakeVectorStore
) -> None:
    store.upsert_error = Boom("qdrant is down")

    with pytest.raises(Boom):
        await ingest(service)
    assert len(repo.documents) == 1

    store.upsert_error = None
    result = await ingest(service)

    assert result.status == "completed"
    assert len(repo.documents) == 1


async def test_an_unsupported_extension_is_rejected(service: IngestionService) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        await ingest(service, data=b"MZ", filename="virus.exe")


async def test_an_empty_file_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await ingest(service, data=b"")


async def test_an_oversized_file_is_rejected(service: IngestionService) -> None:
    with pytest.raises(PayloadTooLargeError):
        await ingest(service, data=b"x" * (21 * 1024 * 1024))


async def test_a_file_without_text_fails_and_marks_the_row(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    with pytest.raises(ExtractionError):
        await ingest(service, data=b"   \n\n  ")

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message


async def test_a_failing_upsert_marks_the_row_and_cleans_up(
    service: IngestionService,
    repo: FakeDocumentRepository,
    store: FakeVectorStore,
) -> None:
    store.upsert_error = Boom("qdrant is down")

    with pytest.raises(Boom):
        await ingest(service)

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "qdrant is down"
    assert store.deleted == [document.id]


async def test_a_failing_embedder_marks_the_row(
    service: IngestionService, repo: FakeDocumentRepository, embedder: FakeEmbeddingService
) -> None:
    embedder.error = Boom("model exploded")

    with pytest.raises(Boom):
        await ingest(service)

    document = next(iter(repo.documents.values()))
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "model exploded"


async def test_the_duration_is_reported(service: IngestionService) -> None:
    result = await ingest(service)

    assert isinstance(result.duration_ms, int)
    assert result.duration_ms > 0


async def test_the_embedding_model_is_recorded(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    result = await ingest(service)

    document = next(iter(repo.documents.values()))
    assert document.embedding_model == "fake-model"
    assert document.embedding_dim == DIMENSION
    assert result.embedding_model == "fake-model"
    assert result.embedding_dim == DIMENSION


async def test_the_chunk_parameters_are_recorded(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service, chunk_size=50, chunk_overlap=10)

    document = next(iter(repo.documents.values()))
    assert document.chunk_size == 50
    assert document.chunk_overlap == 10


async def test_a_smaller_chunk_size_makes_more_chunks(service: IngestionService) -> None:
    big = await ingest(service, chunk_size=500, chunk_overlap=50)
    # Different bytes, so this is a different document and not a duplicate.
    small = await ingest(
        service,
        data=b"Machine learning is a field of study. " * 61,
        chunk_size=50,
        chunk_overlap=10,
    )

    assert small.total_chunks > big.total_chunks


async def test_an_unknown_strategy_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await ingest(service, chunking_strategy="magic")


async def test_an_invalid_overlap_is_rejected(service: IngestionService) -> None:
    with pytest.raises(ValidationError):
        await ingest(service, chunk_size=10, chunk_overlap=10)


async def test_a_hash_race_becomes_a_conflict(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    repo.create_error = IntegrityError("insert", {}, Exception("duplicate key"))

    with pytest.raises(ConflictError):
        await ingest(service)


async def test_nothing_is_written_to_disk(service: IngestionService, tmp_path: Path) -> None:
    before = sorted(path.name for path in tmp_path.iterdir())

    await ingest(service)

    assert sorted(path.name for path in tmp_path.iterdir()) == before


async def test_the_file_hash_is_the_sha256_of_the_bytes(
    service: IngestionService, repo: FakeDocumentRepository
) -> None:
    await ingest(service)

    document = next(iter(repo.documents.values()))
    assert document.file_hash == hashlib.sha256(TEXT).hexdigest()
