"""HTTP tests for the documents API.

The repository, the ingestion service and the vector store are replaced with
fakes through FastAPI's dependency overrides — this exercises the HTTP layer
only.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_document_repository, get_ingestion_service
from app.core.exceptions import ConflictError, ValidationError
from app.integrations.qdrant import StoredChunk, get_vector_store
from app.main import app
from app.models.document import ChunkingStrategy, Document, DocumentStatus
from app.services.ingestion_service import IngestionResult


def make_document(**overrides: object) -> Document:
    values: dict[str, object] = {
        "id": uuid4(),
        "filename": "notes.txt",
        "content_type": "text/plain",
        "file_size": 1234,
        "file_hash": uuid4().hex,
        "file_extension": "txt",
        "chunking_strategy": ChunkingStrategy.RECURSIVE,
        "chunk_size": 200,
        "chunk_overlap": 40,
        "total_chunks": 3,
        "embedding_model": "fake-model",
        "embedding_dim": 384,
        "status": DocumentStatus.COMPLETED,
        "error_message": None,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Document(**values)


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents: list[Document] = []
        self.deleted: list[UUID] = []

    async def get(self, document_id: UUID) -> Document | None:
        return next((d for d in self.documents if d.id == document_id), None)

    async def list(
        self, *, limit: int = 20, offset: int = 0, status: DocumentStatus | None = None
    ) -> tuple[list[Document], int]:
        rows = [d for d in self.documents if status is None or d.status == status]
        return rows[offset : offset + limit], len(rows)

    async def delete(self, document_id: UUID) -> bool:
        self.deleted.append(document_id)
        return any(d.id == document_id for d in self.documents)


class FakeIngestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def ingest(self, **kwargs: object) -> IngestionResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return IngestionResult(
            document_id=uuid4(),
            filename=str(kwargs["filename"]),
            status=DocumentStatus.COMPLETED,
            chunking_strategy=ChunkingStrategy(str(kwargs["chunking_strategy"])),
            total_chunks=3,
            embedding_model="fake-model",
            embedding_dim=384,
            duration_ms=12,
        )


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []
        self.chunks: list[StoredChunk] = [
            StoredChunk(chunk_index=0, content="first chunk", strategy="recursive"),
            StoredChunk(chunk_index=1, content="second chunk", strategy="recursive"),
        ]

    async def list_chunks(self, document_id: UUID, *, limit: int = 20) -> list[StoredChunk]:
        return self.chunks[:limit]

    async def delete_document(self, document_id: UUID) -> None:
        self.deleted.append(document_id)


@pytest.fixture
def repo() -> FakeDocumentRepository:
    return FakeDocumentRepository()


@pytest.fixture
def service() -> FakeIngestionService:
    return FakeIngestionService()


@pytest.fixture
def store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
async def client(
    repo: FakeDocumentRepository,
    service: FakeIngestionService,
    store: FakeVectorStore,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_ingestion_service] = lambda: service
    app.dependency_overrides[get_vector_store] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_ingest_returns_201_and_the_document(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    response = await client.post(
        "/api/v1/documents/ingest",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"chunking_strategy": "recursive"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["status"] == "completed"
    assert body["chunking_strategy"] == "recursive"
    assert body["total_chunks"] == 3
    assert body["embedding_model"] == "fake-model"
    assert body["embedding_dim"] == 384
    assert body["duration_ms"] == 12
    assert UUID(body["document_id"])
    assert len(service.calls) == 1


async def test_ingest_without_a_file_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.post("/api/v1/documents/ingest", data={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "validation_error"


async def test_ingest_with_an_unknown_strategy_never_reaches_the_service(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    response = await client.post(
        "/api/v1/documents/ingest",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"chunking_strategy": "bogus"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert service.calls == []


async def test_ingest_passes_the_fixed_size_strategy_through(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    response = await client.post(
        "/api/v1/documents/ingest",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"chunking_strategy": "fixed_size"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["chunking_strategy"] == "fixed_size"


async def test_ingest_passes_the_chunk_overrides_through(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    await client.post(
        "/api/v1/documents/ingest",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"chunk_size": "50", "chunk_overlap": "10"},
    )

    assert service.calls[0]["chunk_size"] == 50
    assert service.calls[0]["chunk_overlap"] == 10


async def test_ingest_defaults_the_strategy_to_recursive(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    await client.post(
        "/api/v1/documents/ingest", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert service.calls[0]["chunking_strategy"] == ChunkingStrategy.RECURSIVE


async def test_a_conflict_from_the_service_is_a_409(
    client: AsyncClient, service: FakeIngestionService
) -> None:
    service.error = ConflictError("Document already ingested")

    response = await client.post(
        "/api/v1/documents/ingest", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "conflict"


async def test_an_empty_file_is_a_422(client: AsyncClient, service: FakeIngestionService) -> None:
    service.error = ValidationError("Uploaded file is empty")

    response = await client.post(
        "/api/v1/documents/ingest", files={"file": ("notes.txt", b"", "text/plain")}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_unicode_filename_round_trips(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents/ingest",
        files={"file": ("rapport-été-日本語.txt", b"hello", "text/plain")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["filename"] == "rapport-été-日本語.txt"


async def test_the_list_is_paginated(client: AsyncClient, repo: FakeDocumentRepository) -> None:
    repo.documents = [make_document() for _ in range(5)]

    response = await client.get("/api/v1/documents", params={"limit": 2, "offset": 1})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert len(body["items"]) == 2


async def test_the_limit_is_bounded(client: AsyncClient) -> None:
    response = await client.get("/api/v1/documents", params={"limit": 1000})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_list_can_be_filtered_by_status(
    client: AsyncClient, repo: FakeDocumentRepository
) -> None:
    repo.documents = [
        make_document(status=DocumentStatus.COMPLETED),
        make_document(status=DocumentStatus.FAILED),
    ]

    response = await client.get("/api/v1/documents", params={"status": "failed"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "failed"


async def test_an_unknown_document_is_a_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/documents/{uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "not_found"


async def test_the_detail_is_returned(client: AsyncClient, repo: FakeDocumentRepository) -> None:
    document = make_document()
    repo.documents = [document]

    response = await client.get(f"/api/v1/documents/{document.id}")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == str(document.id)
    assert body["file_hash"] == document.file_hash
    assert body["embedding_dim"] == 384


async def test_the_chunks_are_previewed(client: AsyncClient, repo: FakeDocumentRepository) -> None:
    document = make_document()
    repo.documents = [document]

    response = await client.get(f"/api/v1/documents/{document.id}/chunks")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total_chunks"] == 3
    assert body["items"][0]["content"] == "first chunk"


async def test_chunks_of_an_unknown_document_is_a_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/documents/{uuid4()}/chunks")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_delete_removes_the_row_and_the_vectors(
    client: AsyncClient, repo: FakeDocumentRepository, store: FakeVectorStore
) -> None:
    document = make_document()
    repo.documents = [document]

    response = await client.delete(f"/api/v1/documents/{document.id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    assert repo.deleted == [document.id]
    assert store.deleted == [document.id]


async def test_deleting_an_unknown_document_is_a_404(client: AsyncClient) -> None:
    response = await client.delete(f"/api/v1/documents/{uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_responses_leak_no_orm_fields(
    client: AsyncClient, repo: FakeDocumentRepository
) -> None:
    repo.documents = [make_document()]

    response = await client.get("/api/v1/documents")

    body = response.json()
    assert set(body["items"][0]) == {
        "id",
        "filename",
        "file_extension",
        "file_size",
        "chunking_strategy",
        "total_chunks",
        "embedding_model",
        "status",
        "created_at",
    }


async def test_the_openapi_schema_documents_the_upload() -> None:
    schema = app.openapi()

    operation = schema["paths"]["/api/v1/documents/ingest"]["post"]
    body = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    properties = schema["components"]["schemas"][body["$ref"].split("/")[-1]]["properties"]
    assert "file" in properties
    assert "chunking_strategy" in properties
