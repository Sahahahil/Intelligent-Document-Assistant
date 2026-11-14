"""The test doubles themselves — they are used by every other test."""

import math
from uuid import UUID, uuid4

import pytest

from app.chunking.base import DocumentChunk
from app.models.document import ChunkingStrategy
from app.schemas.booking import BookingExtraction
from tests.fakes import FakeEmbeddingService, FakeLLM, FakeVectorStore


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


def test_the_same_text_gives_the_same_vector() -> None:
    embedder = FakeEmbeddingService()

    assert embedder.embed_query("machine learning") == embedder.embed_query("machine learning")


def test_a_different_text_gives_a_different_vector() -> None:
    embedder = FakeEmbeddingService()

    assert embedder.embed_query("machine learning") != embedder.embed_query("banana bread")


def test_the_vectors_are_unit_norm_and_of_the_configured_length() -> None:
    embedder = FakeEmbeddingService(dimension=8)

    vector = embedder.embed_query("machine learning")

    assert len(vector) == 8
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


def test_the_mapper_replaces_the_hash() -> None:
    embedder = FakeEmbeddingService(dimension=4, mapper=lambda text: [1.0, 0.0, 0.0, 0.0])

    assert embedder.embed_query("anything") == [1.0, 0.0, 0.0, 0.0]


def test_the_embedder_records_what_it_was_asked() -> None:
    embedder = FakeEmbeddingService()

    embedder.embed_texts(["one", "two"])
    embedder.embed_query("three")

    assert embedder.embedded == ["one", "two"]
    assert embedder.queries == ["three"]


def test_the_embedder_can_fail() -> None:
    embedder = FakeEmbeddingService()
    embedder.error = RuntimeError("model exploded")

    with pytest.raises(RuntimeError):
        embedder.embed_texts(["one"])


async def test_the_store_ranks_by_cosine_similarity() -> None:
    store = FakeVectorStore()
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="notes.pdf",
        chunks=[make_chunk(document_id, 0), make_chunk(document_id, 1)],
        vectors=[[1.0, 0.0], [0.0, 1.0]],
    )

    results = await store.search([1.0, 0.0], top_k=2)

    assert [chunk.chunk_index for chunk in results] == [0, 1]
    assert results[0].score == pytest.approx(1.0)


async def test_the_store_filters_and_thresholds() -> None:
    store = FakeVectorStore()
    first, second = uuid4(), uuid4()
    await store.upsert_chunks(
        document_id=first,
        filename="a.pdf",
        chunks=[make_chunk(first, 0)],
        vectors=[[1.0, 0.0]],
    )
    await store.upsert_chunks(
        document_id=second,
        filename="b.pdf",
        chunks=[make_chunk(second, 0)],
        vectors=[[0.0, 1.0]],
    )

    assert await store.search([1.0, 0.0], top_k=10, document_ids=[first]) != []
    # The diagonal query scores 0.7 against both chunks - a 0.9 threshold drops them.
    assert await store.search([0.7071, 0.7071], top_k=10, score_threshold=0.9) == []
    assert await store.count_document(first) == 1


async def test_the_store_deletes_a_document() -> None:
    store = FakeVectorStore()
    document_id = uuid4()
    await store.upsert_chunks(
        document_id=document_id,
        filename="a.pdf",
        chunks=[make_chunk(document_id, 0)],
        vectors=[[1.0, 0.0]],
    )

    await store.delete_document(document_id)

    assert store.deleted == [document_id]
    assert await store.count_document(document_id) == 0


async def test_the_llm_replays_its_queued_replies() -> None:
    llm = FakeLLM("first", "second")

    assert await llm.complete(messages=[]) == "first"
    assert await llm.complete(messages=[]) == "second"


async def test_the_llm_raises_what_it_was_given() -> None:
    llm = FakeLLM(RuntimeError("provider is down"))

    with pytest.raises(RuntimeError):
        await llm.complete(messages=[])


async def test_the_llm_without_a_queued_reply_fails_loudly() -> None:
    llm = FakeLLM()

    with pytest.raises(AssertionError):
        await llm.complete(messages=[])


async def test_the_llm_validates_a_structured_reply() -> None:
    llm = FakeLLM('{"is_booking_request": true, "fields": {"name": "Sahil"}}')

    result = await llm.complete_structured(messages=[], schema=BookingExtraction)

    assert result.is_booking_request is True
    assert result.fields.name == "Sahil"


async def test_the_llm_records_the_call() -> None:
    llm = FakeLLM("the answer")

    await llm.complete(messages=[], temperature=0.2)

    assert llm.calls[0]["temperature"] == 0.2
