"""RAG service against a live embedded Qdrant.

Run with:  uv run pytest -m integration

The LLM is a fake - there is no provider key configured, and the model is not
what this test is about. The retrieval side is the real one.
"""

from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app.chunking.base import DocumentChunk
from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.qdrant import VectorStore
from app.models.document import ChunkingStrategy
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import NO_CONTEXT, RAGService
from app.services.retrieval_service import RetrievalService
from tests.fakes import FakeEmbeddingService, FakeLLM

pytestmark = pytest.mark.integration

DIMENSION = 4
ML_QUERY = [1.0, 0.0, 0.0, 0.0]
ALIEN_QUERY = [0.0, 0.0, 1.0, 0.0]


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM("the answer")


@pytest.fixture
async def store(qdrant_client: AsyncQdrantClient, collection: str) -> AsyncIterator[VectorStore]:
    vector_store = VectorStore(qdrant_client, collection, DIMENSION)
    await vector_store.ensure_collection()
    yield vector_store


@pytest.fixture
async def service(store: VectorStore, llm: FakeLLM) -> AsyncIterator[RAGService]:
    document_id = uuid4()
    chunk = DocumentChunk(
        content="Supervised learning trains a model on labelled examples.",
        chunk_index=0,
        document_id=document_id,
        token_count=9,
        strategy=ChunkingStrategy.FIXED_SIZE,
        start_char=0,
        end_char=10,
    )
    await store.upsert_chunks(
        document_id=document_id,
        filename="machine_learning.pdf",
        chunks=[chunk],
        vectors=[[1.0, 0.0, 0.0, 0.0]],
    )
    retrieval = RetrievalService(
        vector_store=store,
        embedding_service=cast(
            EmbeddingService,
            FakeEmbeddingService(
                dimension=DIMENSION,
                mapper=lambda text: ML_QUERY if "learning" in text.lower() else ALIEN_QUERY,
            ),
        ),
    )
    yield RAGService(
        retrieval=retrieval,
        llm=cast(LLMClient, llm),
    )


async def test_the_prompt_carries_the_stored_chunk(service: RAGService, llm: FakeLLM) -> None:
    result = await service.answer("what is supervised learning?")

    assert "Supervised learning trains a model on labelled examples." in llm.sent[-1].content
    assert result.context_used is True
    assert result.sources[0].filename == "machine_learning.pdf"


async def test_a_question_outside_the_corpus_gets_no_context(
    service: RAGService, llm: FakeLLM
) -> None:
    result = await service.answer("how do I bake a banana bread?")

    assert NO_CONTEXT in llm.sent[-1].content
    assert result.context_used is False
    assert result.sources == []


async def test_the_history_reaches_the_prompt(service: RAGService, llm: FakeLLM) -> None:
    await service.answer(
        "what is supervised learning?",
        history=[ChatMessage(role="user", content="we discussed machine learning")],
    )

    assert "user: we discussed machine learning" in llm.sent[-1].content
