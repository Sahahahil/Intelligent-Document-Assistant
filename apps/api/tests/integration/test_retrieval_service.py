"""Retrieval service against a live embedded Qdrant.

Run with:  uv run pytest -m integration

The embedder is a fake that maps a query to a fixed vector, so the ranking is
deterministic — the point here is the vector store plumbing, not the model.
"""

from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID, uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app.chunking.base import DocumentChunk
from app.integrations.qdrant import VectorStore
from app.models.document import ChunkingStrategy
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from tests.fakes import FakeEmbeddingService

pytestmark = pytest.mark.integration

DIMENSION = 4

# Vectors chosen so the cosine similarity tells the story:
#   supervised chunk  -> 1.0 for the ML query, -0.7 for the banana query
#   clustering chunk   -> 0.99 for the ML query
#   banana chunk       -> 1.0 for the banana query
ML_QUERY = [1.0, 0.0, 0.0, 0.0]
BANANA_QUERY = [-0.7, 0.7, 0.0, 0.0]
ALIEN_QUERY = [0.0, 0.0, 1.0, 0.0]


def query_vector(text: str) -> list[float]:
    """The vector a query gets - by keyword, so the ranking is fixed."""
    lowered = text.lower()
    if "banana" in lowered:
        return list(BANANA_QUERY)
    if "supervised" in lowered or "machine learning" in lowered:
        return list(ML_QUERY)
    return list(ALIEN_QUERY)


@pytest.fixture
async def store(qdrant_client: AsyncQdrantClient, collection: str) -> AsyncIterator[VectorStore]:
    vector_store = VectorStore(qdrant_client, collection, DIMENSION)
    await vector_store.ensure_collection()
    yield vector_store


def make_chunk(document_id: UUID, index: int, content: str) -> DocumentChunk:
    return DocumentChunk(
        content=content,
        chunk_index=index,
        document_id=document_id,
        token_count=len(content.split()),
        strategy=ChunkingStrategy.FIXED_SIZE,
        start_char=0,
        end_char=10,
    )


@pytest.fixture
async def seeded(store: VectorStore) -> AsyncIterator[tuple[UUID, UUID]]:
    """Two documents: one about ML, one about banana bread."""
    ml_document = uuid4()
    banana_document = uuid4()

    await store.upsert_chunks(
        document_id=ml_document,
        filename="ml.pdf",
        chunks=[
            make_chunk(ml_document, 0, "Supervised learning trains on labelled examples."),
            make_chunk(ml_document, 1, "Unsupervised learning finds clusters in data."),
        ],
        vectors=[[1.0, 0.0, 0.0, 0.0], [0.9, 0.1, 0.0, 0.0]],
    )
    await store.upsert_chunks(
        document_id=banana_document,
        filename="banana.pdf",
        chunks=[make_chunk(banana_document, 0, "Banana bread needs ripe bananas and butter.")],
        vectors=[[-0.7, 0.7, 0.0, 0.0]],
    )
    yield ml_document, banana_document


@pytest.fixture
def service(store: VectorStore) -> RetrievalService:
    return RetrievalService(
        vector_store=store,
        embedding_service=cast(
            EmbeddingService,
            FakeEmbeddingService(dimension=DIMENSION, mapper=query_vector),
        ),
    )


async def test_the_matching_chunk_ranks_first(
    service: RetrievalService, seeded: tuple[UUID, UUID]
) -> None:
    ml_document, _ = seeded

    results = await service.retrieve("what is supervised learning?")

    assert results
    assert results[0].document_id == ml_document
    assert results[0].chunk_index == 0
    assert "Supervised learning" in results[0].content


async def test_an_unrelated_query_scores_low(
    service: RetrievalService, seeded: tuple[UUID, UUID]
) -> None:
    results = await service.retrieve("quantum chromodynamics")

    assert all(chunk.score < 0.5 for chunk in results)
    assert await service.retrieve("quantum chromodynamics", score_threshold=0.5) == []


async def test_filtering_by_an_unrelated_document_returns_nothing(
    service: RetrievalService, seeded: tuple[UUID, UUID]
) -> None:
    _, banana_document = seeded

    results = await service.retrieve("what is supervised learning?", document_ids=[banana_document])

    assert results == []


async def test_an_empty_store_returns_nothing(service: RetrievalService) -> None:
    assert await service.retrieve("machine learning") == []
