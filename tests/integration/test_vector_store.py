"""Vector store tests against a live embedded Qdrant."""

import math
import random
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from qdrant_client import AsyncQdrantClient, models

from app.chunking.base import DocumentChunk
from app.core.exceptions import UpstreamError
from app.integrations.qdrant import VectorStore

pytestmark = pytest.mark.integration

VECTOR_SIZE = 384


def make_vector(seed: int) -> list[float]:
    rng = random.Random(seed)
    values = [rng.uniform(-1.0, 1.0) for _ in range(VECTOR_SIZE)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def make_chunks(document_id: UUID, count: int) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            content=f"chunk {index} of the document",
            chunk_index=index,
            document_id=document_id,
            token_count=6,
            metadata={"strategy": "recursive", "start_char": 0, "end_char": 10},
        )
        for index in range(count)
    ]


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[VectorStore]:
    client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    vector_store = VectorStore(client, "documents", VECTOR_SIZE)
    await vector_store.ensure_collection()
    yield vector_store
    await client.close()


async def test_ensure_collection_is_idempotent(store: VectorStore) -> None:
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 2),
        vectors=[make_vector(1), make_vector(2)],
    )

    await store.ensure_collection()

    assert await store.count_document(document_id) == 2


async def test_a_different_vector_size_is_reported(tmp_path: Path) -> None:
    client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    await client.create_collection(
        "documents",
        vectors_config=models.VectorParams(size=128, distance=models.Distance.COSINE),
    )
    store = VectorStore(client, "documents", VECTOR_SIZE)
    try:
        with pytest.raises(UpstreamError) as excinfo:
            await store.ensure_collection()
        message = str(excinfo.value)
        assert "128" in message
        assert "384" in message
    finally:
        await client.close()


async def test_upsert_writes_the_points(store: VectorStore) -> None:
    document_id = uuid4()
    written = await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 3),
        vectors=[make_vector(1), make_vector(2), make_vector(3)],
    )
    assert written == 3
    assert await store.count_document(document_id) == 3


async def test_upserting_twice_does_not_duplicate(store: VectorStore) -> None:
    document_id = uuid4()
    chunks = make_chunks(document_id, 3)
    vectors = [make_vector(1), make_vector(2), make_vector(3)]
    await store.upsert_chunks(
        document_id=document_id, filename="a.pdf", chunks=chunks, vectors=vectors
    )
    await store.upsert_chunks(
        document_id=document_id, filename="a.pdf", chunks=chunks, vectors=vectors
    )
    assert await store.count_document(document_id) == 3


async def test_search_returns_the_closest_chunks(store: VectorStore) -> None:
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 3),
        vectors=[make_vector(1), make_vector(2), make_vector(3)],
    )

    results = await store.search(make_vector(1), top_k=2)

    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert results[0].document_id == document_id
    assert results[0].filename == "a.pdf"
    assert results[0].chunk_index == 0
    assert results[0].content == "chunk 0 of the document"


async def test_search_can_be_restricted_to_documents(store: VectorStore) -> None:
    document_id = uuid4()
    other_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 2),
        vectors=[make_vector(1), make_vector(2)],
    )
    await store.upsert_chunks(
        document_id=other_id,
        filename="b.pdf",
        chunks=make_chunks(other_id, 2),
        vectors=[make_vector(3), make_vector(4)],
    )

    results = await store.search(make_vector(1), top_k=10, document_ids=[other_id])

    assert results
    assert all(result.document_id == other_id for result in results)


async def test_score_threshold_filters_weak_matches(store: VectorStore) -> None:
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 2),
        vectors=[make_vector(1), make_vector(2)],
    )

    results = await store.search(make_vector(99), top_k=10, score_threshold=0.99)

    assert results == []


async def test_delete_document_removes_only_that_document(store: VectorStore) -> None:
    document_id = uuid4()
    other_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 2),
        vectors=[make_vector(1), make_vector(2)],
    )
    await store.upsert_chunks(
        document_id=other_id,
        filename="b.pdf",
        chunks=make_chunks(other_id, 2),
        vectors=[make_vector(3), make_vector(4)],
    )

    await store.delete_document(document_id)

    assert await store.count_document(document_id) == 0
    assert await store.count_document(other_id) == 2


async def test_deleting_an_unknown_document_is_a_no_op(store: VectorStore) -> None:
    await store.delete_document(uuid4())
    assert await store.count_document(uuid4()) == 0


async def test_a_broken_client_raises_upstream_error(tmp_path: Path) -> None:
    client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client, "documents", VECTOR_SIZE)
    await client.close()

    with pytest.raises(UpstreamError):
        await store.ensure_collection()


async def test_mismatched_lengths_raise_value_error(store: VectorStore) -> None:
    document_id = uuid4()
    with pytest.raises(ValueError):
        await store.upsert_chunks(
            document_id=document_id,
            filename="a.pdf",
            chunks=make_chunks(document_id, 3),
            vectors=[make_vector(1)],
        )


async def test_no_chunks_means_no_api_call(store: VectorStore) -> None:
    assert (
        await store.upsert_chunks(document_id=uuid4(), filename="a.pdf", chunks=[], vectors=[]) == 0
    )


async def test_an_empty_document_filter_means_no_filter(store: VectorStore) -> None:
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=make_chunks(document_id, 2),
        vectors=[make_vector(1), make_vector(2)],
    )

    results = await store.search(make_vector(1), top_k=10, document_ids=[])

    assert len(results) == 2


async def test_unicode_filenames_survive(store: VectorStore) -> None:
    document_id = uuid4()
    filename = "rapport-été-日本語.pdf"
    await store.upsert_chunks(
        document_id=document_id,
        filename=filename,
        chunks=make_chunks(document_id, 1),
        vectors=[make_vector(1)],
    )

    results = await store.search(make_vector(1), top_k=1)

    assert results[0].filename == filename
