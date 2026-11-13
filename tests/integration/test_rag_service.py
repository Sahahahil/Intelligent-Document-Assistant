"""RAG service against a live embedded Qdrant.

Run with:  uv run pytest -m integration

The LLM is a fake - there is no provider key configured, and the model is not
what this test is about. The retrieval side is the real one.
"""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app.chunking.base import DocumentChunk
from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.qdrant import VectorStore
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import NO_CONTEXT, RAGService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.integration

DIMENSION = 4
ML_QUERY = [1.0, 0.0, 0.0, 0.0]
ALIEN_QUERY = [0.0, 0.0, 1.0, 0.0]


class FakeEmbeddingService:
    model_name = "fake-model"
    dimension = DIMENSION

    def embed_query(self, text: str) -> list[float]:
        return list(ML_QUERY) if "learning" in text.lower() else list(ALIEN_QUERY)


class FakeLLM:
    """Returns the context it was given, so the test can assert on it."""

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        return messages[-1].content


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncQdrantClient]:
    qdrant_client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    yield qdrant_client
    await qdrant_client.close()


@pytest.fixture
async def store(client: AsyncQdrantClient) -> AsyncIterator[VectorStore]:
    vector_store = VectorStore(client, "documents", DIMENSION)
    await vector_store.ensure_collection()
    yield vector_store


@pytest.fixture
async def service(store: VectorStore) -> AsyncIterator[RAGService]:
    document_id = uuid4()
    chunk = DocumentChunk(
        content="Supervised learning trains a model on labelled examples.",
        chunk_index=0,
        document_id=document_id,
        token_count=9,
        metadata={"strategy": "fixed_size"},
    )
    await store.upsert_chunks(
        document_id=document_id,
        filename="machine_learning.pdf",
        chunks=[chunk],
        vectors=[[1.0, 0.0, 0.0, 0.0]],
    )
    retrieval = RetrievalService(
        vector_store=store,
        embedding_service=cast(EmbeddingService, FakeEmbeddingService()),
    )
    yield RAGService(
        retrieval=retrieval,
        llm=cast(LLMClient, FakeLLM()),
    )


async def test_the_answer_is_grounded_in_the_stored_chunk(service: RAGService) -> None:
    result = await service.answer("what is supervised learning?")

    assert "Supervised learning trains a model on labelled examples." in result.answer
    assert result.context_used is True
    assert result.sources[0].filename == "machine_learning.pdf"


async def test_a_question_outside_the_corpus_gets_no_context(service: RAGService) -> None:
    result = await service.answer("how do I bake a banana bread?")

    assert NO_CONTEXT in result.answer
    assert result.context_used is False
    assert result.sources == []


async def test_the_history_reaches_the_prompt(service: RAGService) -> None:
    result = await service.answer(
        "what is supervised learning?",
        history=[ChatMessage(role="user", content="we discussed machine learning")],
    )

    assert "user: we discussed machine learning" in result.answer
