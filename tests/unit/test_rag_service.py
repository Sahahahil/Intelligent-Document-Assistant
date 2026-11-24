"""RAG service tests - the LLM, the retrieval and the rewriter are fakes."""

import logging
from collections.abc import Sequence
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.qdrant import RetrievedChunk
from app.services.rag_service import (
    MAX_CONTEXT_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    NO_CONTEXT,
    RAGService,
)
from app.integrations.qdrant import VectorStore
from app.services.embedding_service import EmbeddingService
from tests.fakes import FakeLLM


def make_chunk(
    content: str = "chunk body", index: int = 0, filename: str = "file.pdf"
) -> RetrievedChunk:
    return RetrievedChunk(
        content=content,
        document_id=uuid4(),
        filename=filename,
        chunk_index=index,
        score=0.9,
    )


class FakeRetrieval:
    """Stands in for the vector store: it returns the chunks it was given."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        self.calls.append({"top_k": top_k, "document_ids": document_ids})
        return self.chunks


class FakeEmbeddings:
    """Every text embeds to the same placeholder vector."""

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


class FakeRewriter:
    def __init__(self, rewritten: str = "a standalone question") -> None:
        self.rewritten = rewritten
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def rewrite(self, message: str, history: Sequence[ChatMessage]) -> str:
        self.calls.append((message, list(history)))
        return self.rewritten


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM("the answer")


@pytest.fixture
def retrieval() -> FakeRetrieval:
    return FakeRetrieval([make_chunk()])


@pytest.fixture
def service(
    retrieval: FakeRetrieval, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> RAGService:
    # The rewrite is a module function: the default here leaves the message
    # alone, so the model is only asked for the answer.
    async def no_rewrite(llm_client: LLMClient, message: str, history: list[ChatMessage]) -> str:
        return message

    monkeypatch.setattr("app.services.rag_service.rewrite_query", no_rewrite)
    return RAGService(
        vector_store=cast(VectorStore, retrieval),
        embedding_service=cast(EmbeddingService, FakeEmbeddings()),
        llm=cast(LLMClient, llm),
    )


async def test_the_llm_is_called_once_and_the_answer_returned(
    service: RAGService, llm: FakeLLM
) -> None:
    result = await service.answer("what is machine learning?")

    assert result.answer == "the answer"
    assert len(llm.calls) == 1
    assert result.context_used is True


async def test_the_prompt_carries_the_context_history_and_question(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    chunk = retrieval.chunks[0]

    await service.answer(
        "what is machine learning?",
        history=[ChatMessage(role="user", content="tell me about ML")],
    )

    prompt = llm.sent[-1].content
    assert chunk.content in prompt
    assert "user: tell me about ML" in prompt
    assert "Question: what is machine learning?" in prompt


async def test_the_context_is_numbered_with_the_file_and_chunk(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = [make_chunk(index=2, filename="machine_learning.pdf")]

    await service.answer("what is machine learning?")

    assert "[1] (machine_learning.pdf, chunk 2)" in llm.sent[-1].content


async def test_without_context_the_model_is_told_there_is_none(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = []

    result = await service.answer("what is machine learning?")

    assert NO_CONTEXT in llm.sent[-1].content
    assert result.context_used is False
    assert result.sources == []


async def test_the_sources_match_the_chunks_that_were_used(
    service: RAGService, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = [make_chunk(index=0), make_chunk(index=1)]

    result = await service.answer("what is machine learning?")

    assert len(result.sources) == 2
    assert result.context_used is True


async def test_the_rewriter_produces_the_retrieval_query(
    retrieval: FakeRetrieval, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    rewriter = FakeRewriter()

    async def rewrite(llm_client: LLMClient, message: str, history: list[ChatMessage]) -> str:
        return await rewriter.rewrite(message, history)

    monkeypatch.setattr("app.services.rag_service.rewrite_query", rewrite)
    service = RAGService(
        vector_store=cast(VectorStore, retrieval),
        embedding_service=cast(EmbeddingService, FakeEmbeddings()),
        llm=cast(LLMClient, llm),
    )

    result = await service.answer("what about the second one?", history=[])

    assert result.rewritten_query == "a standalone question"
    assert rewriter.calls[0][0] == "what about the second one?"
    assert len(rewriter.calls) == 1


async def test_without_a_rewriter_the_original_message_is_the_query(
    service: RAGService, retrieval: FakeRetrieval
) -> None:
    result = await service.answer("what about the second one?")

    assert result.rewritten_query == "what about the second one?"


async def test_only_the_last_six_history_messages_reach_the_prompt(
    service: RAGService, llm: FakeLLM
) -> None:
    history = [ChatMessage(role="user", content=f"message {index}") for index in range(50)]

    await service.answer("and now?", history=history)

    assert f"message {50 - MAX_HISTORY_MESSAGES}" in llm.sent[-1].content
    assert f"message {49 - MAX_HISTORY_MESSAGES}" not in llm.sent[-1].content


async def test_a_long_history_message_is_truncated(service: RAGService, llm: FakeLLM) -> None:
    history = [ChatMessage(role="user", content="x" * 10_000)]

    await service.answer("and now?", history=history)

    assert "x" * (MAX_MESSAGE_CHARS + 1) not in llm.sent[-1].content
    assert "x" * MAX_MESSAGE_CHARS in llm.sent[-1].content


async def test_the_context_is_capped_and_the_dropped_chunks_are_logged(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval, caplog: pytest.LogCaptureFixture
) -> None:
    retrieval.chunks = [make_chunk(content="y" * 2000, index=index) for index in range(20)]

    with caplog.at_level(logging.WARNING):
        result = await service.answer("what is machine learning?")

    assert len(llm.sent[-1].content) < MAX_CONTEXT_CHARS + 2000
    assert len(result.sources) < 20
    assert "truncated" in caplog.text


async def test_a_failing_llm_propagates(retrieval: FakeRetrieval) -> None:
    llm = FakeLLM(UpstreamError("LLM error: 500"))
    service = RAGService(
        vector_store=cast(VectorStore, retrieval),
        embedding_service=cast(EmbeddingService, FakeEmbeddings()),
        llm=cast(LLMClient, llm),
    )

    with pytest.raises(UpstreamError):
        await service.answer("what is machine learning?")


async def test_the_answer_temperature_is_low(service: RAGService, llm: FakeLLM) -> None:
    await service.answer("what is machine learning?")

    assert llm.calls[0]["temperature"] == 0.2


async def test_the_document_filter_reaches_the_retrieval(
    service: RAGService, retrieval: FakeRetrieval
) -> None:
    document_id = uuid4()

    await service.answer("what is machine learning?", document_ids=[document_id])

    assert retrieval.calls[0]["document_ids"] == [document_id]


async def test_the_system_prompt_forbids_inventing_facts(service: RAGService, llm: FakeLLM) -> None:
    await service.answer("what is machine learning?")

    system = cast(list[ChatMessage], llm.calls[0]["messages"])[0]
    assert system.role == "system"
    assert "ONLY the" in system.content
    assert "Do not invent facts" in system.content


async def test_an_empty_chunk_is_skipped(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = [make_chunk(content="   ", index=0), make_chunk(index=1)]

    result = await service.answer("what is machine learning?")

    assert len(result.sources) == 1
    assert "[1] (" in llm.sent[-1].content
