"""Query rewriter tests - the LLM is a fake."""

import logging
from typing import cast

import pytest

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.services.query_rewriter import MAX_HISTORY_MESSAGES, rewrite_query
from tests.fakes import FakeLLM


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM("What are the advantages of supervised learning?")


@pytest.fixture
def history() -> list[ChatMessage]:
    return [
        ChatMessage(role="user", content="I like Python"),
        ChatMessage(role="assistant", content="Python is a good choice"),
    ]


async def test_a_first_turn_costs_no_llm_call(llm: FakeLLM) -> None:
    assert await rewrite_query(cast(LLMClient, llm), "hello", []) == "hello"
    assert llm.calls == []


async def test_a_follow_up_is_rewritten(
    llm: FakeLLM, history: list[ChatMessage]
) -> None:
    result = await rewrite_query(cast(LLMClient, llm), "what about the second one?", history)

    assert "supervised learning" in result
    assert len(llm.calls) == 1


async def test_the_quotes_are_stripped(llm: FakeLLM) -> None:
    llm.queue('"What are the advantages of supervised learning?"')

    result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "What are the advantages of supervised learning?"


async def test_an_empty_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.queue("")

    result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_a_too_long_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.queue("x" * 700)

    result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_a_failing_llm_falls_back_to_the_message(
    llm: FakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    llm.queue(UpstreamError("LLM error: 500"))

    with caplog.at_level(logging.WARNING):
        result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"
    assert "rewriting failed" in caplog.text


async def test_a_whitespace_reply_falls_back_to_the_message(llm: FakeLLM) -> None:
    llm.queue("   \n  ")

    result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "what about it?"


async def test_only_the_last_six_history_messages_are_sent(
    llm: FakeLLM
) -> None:
    history = [ChatMessage(role="user", content=f"h{index}") for index in range(20)]

    await rewrite_query(cast(LLMClient, llm), "and now?", history)

    sent = [message.content for message in llm.sent]
    assert "h14" in sent
    assert "h13" not in sent
    assert len([content for content in sent if content.startswith("h")]) == MAX_HISTORY_MESSAGES


async def test_the_instruction_comes_first(llm: FakeLLM) -> None:
    await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.sent[0].role == "system"


async def test_the_rewrite_is_deterministic(llm: FakeLLM) -> None:
    await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.calls[0]["temperature"] == 0.0


async def test_the_current_message_is_the_last_one_sent(
    llm: FakeLLM
) -> None:
    await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert llm.sent[-1].content == "what about it?"
    assert llm.sent[-1].role == "user"


async def test_a_history_of_only_assistant_messages_still_rewrites(
    llm: FakeLLM
) -> None:
    result = await rewrite_query(cast(LLMClient, llm), 
        "what about it?", [ChatMessage(role="assistant", content="Python is a good choice")]
    )

    assert result
    assert len(llm.calls) == 1


async def test_a_very_long_message_does_not_crash(llm: FakeLLM) -> None:
    result = await rewrite_query(cast(LLMClient, llm), "x" * 4000, [ChatMessage(role="user", content="hi")])

    assert result


async def test_only_the_first_line_of_a_multi_line_reply_is_used(llm: FakeLLM) -> None:
    llm.queue("What is supervised learning?\nLet me know if you need more.")

    result = await rewrite_query(cast(LLMClient, llm), "what about it?", [ChatMessage(role="user", content="hi")])

    assert result == "What is supervised learning?"
