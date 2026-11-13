"""LLM client tests.

The provider is an `httpx2.MockTransport`, so the real SDK stack runs — request
building, response parsing and the SDK's retry policy — without a network.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.exceptions import UpstreamError
from app.integrations import llm as llm_module
from app.integrations.llm import ChatMessage, LLMClient, get_llm_client


class Booking(BaseModel):
    name: str
    email: str


def completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class FakeProvider:
    """A canned OpenAI-compatible endpoint."""

    def __init__(
        self, responder: Callable[[httpx2.Request], httpx2.Response] | None = None
    ) -> None:
        self.requests: list[httpx2.Request] = []
        self._responder = responder or (lambda request: httpx2.Response(200, json=completion("ok")))

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = httpx2.MockTransport(self._handle)
        http_client = httpx2.AsyncClient(transport=transport)
        real_client = AsyncOpenAI

        def factory(*, api_key: str, base_url: str | None, timeout: float) -> AsyncOpenAI:
            return real_client(
                api_key=api_key, base_url=base_url, timeout=timeout, http_client=http_client
            )

        monkeypatch.setattr(llm_module, "AsyncOpenAI", factory)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._responder(request)

    @property
    def last_body(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[-1].content)
        return body


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    fake = FakeProvider()
    fake.install(monkeypatch)
    return fake


@pytest.fixture
def client(provider: FakeProvider) -> LLMClient:
    # Depends on the provider so the transport is patched before the client
    # is constructed — the client builds its own HTTP client.
    return LLMClient(api_key="sk-test-key", model="test-model")


async def test_complete_returns_the_stripped_content(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(200, json=completion("  hello  "))

    result = await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert result == "hello"


async def test_complete_with_no_content_returns_an_empty_string(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(200, json=completion(""))

    result = await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert result == ""


async def test_complete_sends_the_model_and_the_messages(
    client: LLMClient, provider: FakeProvider
) -> None:
    await client.complete(
        messages=[
            ChatMessage(role="system", content="be brief"),
            ChatMessage(role="user", content="hi"),
        ]
    )

    body = provider.last_body
    assert body["model"] == "test-model"
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}


async def test_complete_json_parses_the_object(client: LLMClient, provider: FakeProvider) -> None:
    provider._responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    payload = await client.complete_json(messages=[ChatMessage(role="user", content="hi")])

    assert payload == {"name": "Sahil", "email": "s@example.com"}
    assert provider.last_body["response_format"] == {"type": "json_object"}


async def test_complete_json_with_invalid_json_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(200, json=completion("not json"))

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete_json(messages=[ChatMessage(role="user", content="hi")])

    assert "invalid JSON" in str(excinfo.value)


async def test_complete_json_with_an_array_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(200, json=completion("[1, 2]"))

    with pytest.raises(UpstreamError):
        await client.complete_json(messages=[ChatMessage(role="user", content="hi")])


async def test_complete_structured_validates_against_the_schema(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    result = await client.complete_structured(
        messages=[ChatMessage(role="user", content="book me an interview")], schema=Booking
    )

    assert isinstance(result, Booking)
    assert result.name == "Sahil"


async def test_complete_structured_tells_the_model_the_schema(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    await client.complete_structured(
        messages=[ChatMessage(role="user", content="hi")], schema=Booking
    )

    messages = provider.last_body["messages"]
    assert "name" in messages[-1]["content"]
    assert messages[0]["role"] == "user"


async def test_complete_structured_with_a_bad_payload_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(200, json=completion('{"name": "Sahil"}'))

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete_structured(
            messages=[ChatMessage(role="user", content="hi")], schema=Booking
        )

    assert excinfo.value.details["errors"]
    assert excinfo.value.details["raw"] == {"name": "Sahil"}


async def test_without_an_api_key_the_call_fails(provider: FakeProvider) -> None:
    client = LLMClient(api_key="", model="test-model")

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert "LLM_API_KEY" in str(excinfo.value)
    assert provider.requests == []


async def test_a_server_error_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 500


async def test_a_rate_limit_is_retried_and_then_reported(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider._responder = lambda request: httpx2.Response(
        429, json={"error": {"message": "slow down"}}
    )

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 429
    # Two retries on top of the first attempt.
    assert len(provider.requests) == 3


async def test_a_bad_request_is_not_retried(client: LLMClient, provider: FakeProvider) -> None:
    provider._responder = lambda request: httpx2.Response(400, json={"error": {"message": "nope"}})

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 400
    assert len(provider.requests) == 1


async def test_a_connection_error_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host", request=request)

    provider._responder = boom

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert "Could not reach" in str(excinfo.value)


def test_the_client_is_reused() -> None:
    assert get_llm_client() is get_llm_client()


async def test_the_api_key_is_never_logged(
    client: LLMClient, provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert caplog.text
    assert "sk-test-key" not in caplog.text
