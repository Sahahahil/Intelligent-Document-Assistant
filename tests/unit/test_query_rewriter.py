"""Query rewriter tests - the LLM is a fake."""

import logging
from collections.abc import Sequence
from typing import cast

import pytest

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.services.query_rewriter import MAX_HISTORY_MESSAGES, QueryRewriter


class FakeLLM:
    """Records the messages it was given and returns a canned reply."""

    def __init__(self, reply: str = "What are the advantages of supervised learning?") -> None:
        self.reply = reply
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
        return self.reply

    @property
    def sent(self) -> list[ChatMessage]:
        return cast(list[ChatMessage], self.calls[0]["messages"])


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def rewriter(llm: FakeLLM) -> QueryRewriter:
    return QueryRewriter(cast(LLMClient, llm))


@pytest.fixture
def history() -> list[ChatMessage]:
    return [
        ChatMessage(role="user", content="I like Python"),
        ChatMessage(role="assistant", content="Python is a good choice"),
    ]


async def test_a_first_turn_costs_no_llm_call(rewriter: QueryRewriter, llm: FakeLLM) -> None:
    assert await rewriter.rewrite("hello", []) == "hello"
    assert llm.calls == []


async def test_a_follow_up_is_rewritten(
    rewriter: QueryRewriter, llm: FakeLLM, history: list[ChatMessage]
) -> None:
    result = await rewriter.rewrite("what about the second one?", history)

    assert "supervised learning" in result
    assert len(llm.calls) == 1


async def test_the_quotes_are_stripped(llm: FakeLLM) -> None:
    llm.reply = '"What are the advantages of supervised learning?"'
    rewriter = QueryRewriter(cast(LLMClient, llm))

    result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "What are the advantages of supervised learning?"


async def test_an_empty_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.reply = ""
    rewriter = QueryRewriter(cast(LLMClient, llm))

    result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_a_too_long_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.reply = "x" * 700
    rewriter = QueryRewriter(cast(LLMClient, llm))

    result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_a_failing_llm_falls_back_to_the_message(
    llm: FakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    llm.error = UpstreamError("LLM error: 500")
    rewriter = QueryRewriter(cast(LLMClient, llm))

    with caplog.at_level(logging.WARNING):
        result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"
    assert "rewriting failed" in caplog.text


async def test_a_whitespace_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.reply = "   \n  "
    rewriter = QueryRewriter(cast(LLMClient, llm))

    result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_only_the_last_six_history_messages_are_sent(
    rewriter: QueryRewriter, llm: FakeLLM
) -> None:
    history = [ChatMessage(role="user", content=f"h{index}") for index in range(20)]

    await rewriter.rewrite("and now?", history)

    sent = [message.content for message in llm.sent]
    assert "h14" in sent
    assert "h13" not in sent
    assert len([content for content in sent if content.startswith("h")]) == MAX_HISTORY_MESSAGES


async def test_the_instruction_comes_first(rewriter: QueryRewriter, llm: FakeLLM) -> None:
    await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.sent[0].role == "system"


async def test_the_rewrite_is_deterministic(rewriter: QueryRewriter, llm: FakeLLM) -> None:
    await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.calls[0]["temperature"] == 0.0


async def test_the_current_message_is_the_last_one_sent(
    rewriter: QueryRewriter, llm: FakeLLM
) -> None:
    await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.sent[-1].content == "what about it?"
    assert llm.sent[-1].role == "user"


async def test_an_empty_history_has_no_summary(rewriter: QueryRewriter, llm: FakeLLM) -> None:
    assert await rewriter.summarize_conversation([]) == ""
    assert llm.calls == []


async def test_a_failing_summary_is_empty(llm: FakeLLM) -> None:
    llm.error = UpstreamError("LLM error: 500")
    rewriter = QueryRewriter(cast(LLMClient, llm))

    assert await rewriter.summarize_conversation([ChatMessage(role="user", content="hi")]) == ""


async def test_a_summary_is_produced(rewriter: QueryRewriter, llm: FakeLLM) -> None:
    llm.reply = "The user likes Python."

    summary = await rewriter.summarize_conversation([ChatMessage(role="user", content="hi")])

    assert summary == "The user likes Python."


async def test_a_history_of_only_assistant_messages_still_rewrites(
    rewriter: QueryRewriter, llm: FakeLLM
) -> None:
    result = await rewriter.rewrite(
        "what about it?", [ChatMessage(role="assistant", content="Python is a good choice")]
    )

    assert result
    assert len(llm.calls) == 1


async def test_a_very_long_message_does_not_crash(rewriter: QueryRewriter) -> None:
    result = await rewriter.rewrite("x" * 4000, [ChatMessage(role="user", content="hi")])

    assert result


async def test_only_the_first_line_of_a_multi_line_reply_is_used(llm: FakeLLM) -> None:
    llm.reply = "What is supervised learning?\nLet me know if you need more."
    rewriter = QueryRewriter(cast(LLMClient, llm))

    result = await rewriter.rewrite("what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "What is supervised learning?"
