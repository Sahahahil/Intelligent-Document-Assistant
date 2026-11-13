"""RAG service tests - the LLM, the retrieval and the rewriter are fakes."""

import logging
from collections.abc import Sequence
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.qdrant import RetrievedChunk
from app.services.query_rewriter import QueryRewriter
from app.services.rag_service import (
    MAX_CONTEXT_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    NO_CONTEXT,
    RAGService,
)
from app.services.retrieval_service import RetrievalService


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


class FakeLLM:
    """Records the messages it was given and returns a canned answer."""

    def __init__(self, answer: str = "the answer") -> None:
        self.answer = answer
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append({"messages": list(messages), "temperature": temperature})
        if self.error is not None:
            raise self.error
        return self.answer

    @property
    def prompt(self) -> str:
        messages = cast(list[ChatMessage], self.calls[0]["messages"])
        return messages[-1].content


class FakeRetrieval:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[dict[str, object]] = []

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        self.calls.append({"query": query, "document_ids": document_ids})
        return self.chunks


class FakeRewriter:
    def __init__(self, rewritten: str = "a standalone question") -> None:
        self.rewritten = rewritten
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def rewrite(self, message: str, history: Sequence[ChatMessage]) -> str:
        self.calls.append((message, list(history)))
        return self.rewritten


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def retrieval() -> FakeRetrieval:
    return FakeRetrieval([make_chunk()])


@pytest.fixture
def service(retrieval: FakeRetrieval, llm: FakeLLM) -> RAGService:
    return RAGService(
        retrieval=cast(RetrievalService, retrieval),
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

    prompt = llm.prompt
    assert chunk.content in prompt
    assert "user: tell me about ML" in prompt
    assert "Question: what is machine learning?" in prompt


async def test_the_context_is_numbered_with_the_file_and_chunk(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = [make_chunk(index=2, filename="machine_learning.pdf")]

    await service.answer("what is machine learning?")

    assert "[1] (machine_learning.pdf, chunk 2)" in llm.prompt


async def test_without_context_the_model_is_told_there_is_none(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval
) -> None:
    retrieval.chunks = []

    result = await service.answer("what is machine learning?")

    assert NO_CONTEXT in llm.prompt
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
    retrieval: FakeRetrieval, llm: FakeLLM
) -> None:
    rewriter = FakeRewriter()
    service = RAGService(
        retrieval=cast(RetrievalService, retrieval),
        llm=cast(LLMClient, llm),
        rewriter=cast(QueryRewriter, rewriter),
    )

    result = await service.answer("what about the second one?", history=[])

    assert result.rewritten_query == "a standalone question"
    assert retrieval.calls[0]["query"] == "a standalone question"
    assert len(rewriter.calls) == 1


async def test_without_a_rewriter_the_original_message_is_the_query(
    service: RAGService, retrieval: FakeRetrieval
) -> None:
    result = await service.answer("what about the second one?")

    assert result.rewritten_query == "what about the second one?"
    assert retrieval.calls[0]["query"] == "what about the second one?"


async def test_only_the_last_six_history_messages_reach_the_prompt(
    service: RAGService, llm: FakeLLM
) -> None:
    history = [ChatMessage(role="user", content=f"message {index}") for index in range(50)]

    await service.answer("and now?", history=history)

    assert f"message {50 - MAX_HISTORY_MESSAGES}" in llm.prompt
    assert f"message {49 - MAX_HISTORY_MESSAGES}" not in llm.prompt


async def test_a_long_history_message_is_truncated(service: RAGService, llm: FakeLLM) -> None:
    history = [ChatMessage(role="user", content="x" * 10_000)]

    await service.answer("and now?", history=history)

    assert "x" * (MAX_MESSAGE_CHARS + 1) not in llm.prompt
    assert "x" * MAX_MESSAGE_CHARS in llm.prompt


async def test_the_context_is_capped_and_the_dropped_chunks_are_logged(
    service: RAGService, llm: FakeLLM, retrieval: FakeRetrieval, caplog: pytest.LogCaptureFixture
) -> None:
    retrieval.chunks = [make_chunk(content="y" * 2000, index=index) for index in range(20)]

    with caplog.at_level(logging.WARNING):
        result = await service.answer("what is machine learning?")

    assert len(llm.prompt) < MAX_CONTEXT_CHARS + 2000
    assert len(result.sources) < 20
    assert "truncated" in caplog.text


async def test_a_failing_llm_propagates(service: RAGService, llm: FakeLLM) -> None:
    llm.error = UpstreamError("LLM error: 500")

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
    assert "[1] (" in llm.prompt
