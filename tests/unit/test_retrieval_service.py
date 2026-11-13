"""Retrieval service tests — the vector store and the embedder are fakes."""

from typing import cast
from uuid import UUID, uuid4

import pytest

from app.core.config import get_settings
from app.core.exceptions import UpstreamError, ValidationError
from app.integrations.qdrant import RetrievedChunk, VectorStore
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService, SourceReference

DIMENSION = 8


def make_chunk(document_id: UUID, index: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        content=f"chunk {index}",
        document_id=document_id,
        filename="notes.pdf",
        chunk_index=index,
        score=score,
    )


class FakeVectorStore:
    """Mimics the real store: descending score, filters, thresholds."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        document_ids: list[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "vector": vector,
                "top_k": top_k,
                "document_ids": document_ids,
                "score_threshold": score_threshold,
            }
        )
        if self.error is not None:
            raise self.error
        results = self.chunks
        if document_ids:
            results = [chunk for chunk in results if chunk.document_id in document_ids]
        if score_threshold is not None:
            results = [chunk for chunk in results if chunk.score >= score_threshold]
        return results[:top_k]


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.model_name = "fake-model"
        self.dimension = DIMENSION
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1] * DIMENSION


@pytest.fixture
def document_id() -> UUID:
    return uuid4()


@pytest.fixture
def store(document_id: UUID) -> FakeVectorStore:
    return FakeVectorStore(
        [make_chunk(document_id, index, 0.9 - index * 0.1) for index in range(5)]
    )


@pytest.fixture
def embedder() -> FakeEmbeddingService:
    return FakeEmbeddingService()


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
    assert store.calls[0]["vector"] == [0.1] * DIMENSION


async def test_the_results_are_restricted_to_the_given_documents(
    service: RetrievalService, store: FakeVectorStore, document_id: UUID
) -> None:
    other = uuid4()
    store.chunks = [
        make_chunk(document_id, 0, 0.9),
        make_chunk(other, 1, 0.8),
    ]

    results = await service.retrieve("machine learning", document_ids=[document_id])

    assert [chunk.document_id for chunk in results] == [document_id]
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
    store.error = UpstreamError("Qdrant error: connection refused")

    with pytest.raises(UpstreamError):
        await service.retrieve("machine learning")


async def test_the_sources_carry_no_content(service: RetrievalService, document_id: UUID) -> None:
    sources = await service.retrieve_sources("machine learning")

    assert sources
    assert all(isinstance(source, SourceReference) for source in sources)
    assert sources[0].document_id == document_id
    assert sources[0].filename == "notes.pdf"
    assert sources[0].chunk_index == 0
    assert not hasattr(sources[0], "content")


async def test_the_scores_are_rounded_to_four_decimals(service: RetrievalService) -> None:
    service_store = cast(FakeVectorStore, service._vector_store)
    document_id = uuid4()
    service_store.chunks = [make_chunk(document_id, 0, 0.123456789)]

    sources = await service.retrieve_sources("machine learning")

    assert sources[0].score == 0.1235
