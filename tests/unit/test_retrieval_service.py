"""Retrieval service tests — the vector store and the embedder are fakes."""

import math
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.chunking.base import DocumentChunk
from app.core.config import get_settings
from app.core.exceptions import UpstreamError, ValidationError
from app.integrations.qdrant import VectorStore
from app.models.document import ChunkingStrategy
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from tests.fakes import FakeEmbeddingService, FakeVectorStore

DIMENSION = 8
QUERY_VECTOR = [1.0] + [0.0] * (DIMENSION - 1)


def vector_at(cosine: float) -> list[float]:
    """A unit vector whose cosine with the query vector is `cosine`."""
    vector = [0.0] * DIMENSION
    vector[0] = cosine
    vector[1] = math.sqrt(1.0 - cosine * cosine)
    return vector


def make_chunk(document_id: UUID, index: int) -> DocumentChunk:
    return DocumentChunk(
        content=f"chunk {index}",
        chunk_index=index,
        document_id=document_id,
        token_count=2,
        strategy=ChunkingStrategy.FIXED_SIZE,
        start_char=0,
        end_char=10,
    )


@pytest.fixture
def document_id() -> UUID:
    return uuid4()


@pytest.fixture
def embedder() -> FakeEmbeddingService:
    """Every query gives the same vector, so the ranking is predictable."""
    return FakeEmbeddingService(dimension=DIMENSION, mapper=lambda _text: QUERY_VECTOR)


@pytest.fixture
async def store(document_id: UUID) -> FakeVectorStore:
    fake_store = FakeVectorStore()
    await fake_store.upsert_chunks(
        document_id=document_id,
        filename="notes.pdf",
        chunks=[make_chunk(document_id, index) for index in range(5)],
        vectors=[vector_at(0.9 - index * 0.1) for index in range(5)],
    )
    return fake_store


@pytest.fixture
def service(store: FakeVectorStore, embedder: FakeEmbeddingService) -> RetrievalService:
    return RetrievalService(
        vector_store=cast(VectorStore, store),
        embedding_service=cast(EmbeddingService, embedder),
    )


async def test_retrieve_returns_the_top_k_chunks(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    results = await service.retrieve("machine learning", top_k=3)

    assert len(results) == 3
    assert store.calls[0]["top_k"] == 3
    assert [chunk.score for chunk in results] == sorted(
        (chunk.score for chunk in results), reverse=True
    )


async def test_top_k_defaults_to_the_settings(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    await service.retrieve("machine learning")

    assert store.calls[0]["top_k"] == get_settings().top_k


async def test_the_query_is_embedded_by_the_injected_service(
    service: RetrievalService, embedder: FakeEmbeddingService, store: FakeVectorStore
) -> None:
    await service.retrieve("machine learning")

    assert embedder.queries == ["machine learning"]
    assert store.calls[0]["vector"] == embedder.last_vector


async def test_the_results_are_restricted_to_the_given_documents(
    service: RetrievalService, store: FakeVectorStore, document_id: UUID
) -> None:
    other = uuid4()
    await store.upsert_chunks(
        document_id=other,
        filename="other.pdf",
        chunks=[make_chunk(other, 0)],
        vectors=[vector_at(0.95)],
    )

    results = await service.retrieve("machine learning", document_ids=[document_id])

    assert results
    assert all(chunk.document_id == document_id for chunk in results)
    assert store.calls[0]["document_ids"] == [document_id]


async def test_an_empty_document_filter_means_no_filter(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    await service.retrieve("machine learning", document_ids=[])

    assert store.calls[0]["document_ids"] is None


async def test_a_high_threshold_drops_the_weak_matches(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    results = await service.retrieve("machine learning", score_threshold=0.99)

    assert results == []
    assert store.calls[0]["score_threshold"] == 0.99


async def test_the_threshold_defaults_to_the_settings(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    await service.retrieve("machine learning")

    assert store.calls[0]["score_threshold"] == get_settings().score_threshold


async def test_an_empty_query_is_rejected_before_any_embedding(
    service: RetrievalService, embedder: FakeEmbeddingService, store: FakeVectorStore
) -> None:
    with pytest.raises(ValidationError):
        await service.retrieve("")

    assert embedder.queries == []
    assert store.calls == []


async def test_a_blank_query_is_rejected(
    service: RetrievalService, embedder: FakeEmbeddingService
) -> None:
    with pytest.raises(ValidationError):
        await service.retrieve("   ")

    assert embedder.queries == []


async def test_a_top_k_below_one_is_rejected(service: RetrievalService) -> None:
    with pytest.raises(ValidationError):
        await service.retrieve("machine learning", top_k=0)


async def test_a_failing_vector_store_propagates(
    service: RetrievalService, store: FakeVectorStore
) -> None:
    store.search_error = UpstreamError("Qdrant error: connection refused")

    with pytest.raises(UpstreamError):
        await service.retrieve("machine learning")
