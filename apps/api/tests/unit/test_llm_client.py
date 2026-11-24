"""LLM client tests.

The provider is an `httpx2.MockTransport`, so the real SDK stack runs — request
building, response parsing and the SDK's retry policy — without a network.
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from app.core.exceptions import UpstreamError
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

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.responder: Callable[[httpx2.Request], httpx2.Response] = lambda request: (
            httpx2.Response(200, json=completion("ok"))
        )

    def http_client(self) -> httpx2.AsyncClient:
        """An HTTP client whose transport is this provider."""
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.responder(request)

    @property
    def last_body(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[-1].content)
        return body


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
async def client(provider: FakeProvider) -> AsyncIterator[LLMClient]:
    http_client = provider.http_client()
    yield LLMClient(api_key="sk-test-key", model="test-model", http_client=http_client)
    await http_client.aclose()


async def test_complete_returns_the_stripped_content(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(200, json=completion("  hello  "))

    result = await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert result == "hello"


async def test_complete_with_no_content_returns_an_empty_string(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(200, json=completion(""))

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


async def test_the_json_response_format_is_requested(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    await client.complete_structured(
        messages=[ChatMessage(role="user", content="hi")], schema=Booking
    )

    assert provider.last_body["response_format"] == {"type": "json_object"}


async def test_invalid_json_is_an_upstream_error(client: LLMClient, provider: FakeProvider) -> None:
    """Garbage from the provider is an upstream error, however it arrives."""
    provider.responder = lambda request: httpx2.Response(200, json=completion("not json"))

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete_structured(
            messages=[ChatMessage(role="user", content="hi")], schema=Booking
        )

    assert "no JSON that matches the schema" in str(excinfo.value)


async def test_json_that_is_not_an_object_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(200, json=completion("[1, 2]"))

    with pytest.raises(UpstreamError):
        await client.complete_structured(
            messages=[ChatMessage(role="user", content="hi")], schema=Booking
        )


async def test_complete_structured_validates_against_the_schema(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(
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
    provider.responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    await client.complete_structured(
        messages=[ChatMessage(role="user", content="hi")], schema=Booking
    )

    messages = provider.last_body["messages"]
    # The hint rides with the system prompt - a system message after the user
    # turn makes a small model echo the schema instead of filling it in.
    assert "name" in messages[0]["content"]
    assert messages[0]["role"] == "system"


async def test_complete_structured_keeps_the_schema_hint_with_the_system_prompt(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(
        200, json=completion('{"name": "Sahil", "email": "s@example.com"}')
    )

    await client.complete_structured(
        messages=[
            ChatMessage(role="system", content="You are a booking assistant."),
            ChatMessage(role="user", content="hi"),
        ],
        schema=Booking,
    )

    messages = provider.last_body["messages"]
    assert len(messages) == 2
    assert "booking assistant" in messages[0]["content"]
    assert "name" in messages[0]["content"]
    assert messages[1]["role"] == "user"


async def test_complete_structured_with_a_bad_payload_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(200, json=completion('{"name": "Sahil"}'))

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete_structured(
            messages=[ChatMessage(role="user", content="hi")], schema=Booking
        )

    assert excinfo.value.details["errors"]
    assert excinfo.value.details["raw"] == {"name": "Sahil"}


async def test_a_provider_without_json_mode_is_asked_again_in_plain_text(
    client: LLMClient, provider: FakeProvider
) -> None:
    """A local server that rejects the JSON mode still gets an answer."""

    def responder(request: httpx2.Request) -> httpx2.Response:
        if b"response_format" in request.content:
            return httpx2.Response(500, json={"error": {"message": "not supported"}})
        return httpx2.Response(
            200,
            json=completion('Sure!\n```json\n{"name": "Sahil", "email": "s@example.com"}\n```'),
        )

    provider.responder = responder

    result = await client.complete_structured(
        messages=[ChatMessage(role="user", content="book me an interview")], schema=Booking
    )

    assert isinstance(result, Booking)
    assert result.name == "Sahil"
    # The retry did not ask for the JSON mode again.
    assert "response_format" not in provider.last_body


async def test_a_model_that_echoes_the_schema_is_answered_anyway(
    client: LLMClient, provider: FakeProvider
) -> None:
    """The echoed schema is JSON too - but only the answer validates."""

    def responder(request: httpx2.Request) -> httpx2.Response:
        if b"response_format" in request.content:
            return httpx2.Response(500, json={"error": {"message": "not supported"}})
        return httpx2.Response(
            200,
            json=completion(
                '{"type": "object", "properties": {"name": {"type": "string"}}}\n'
                '{"name": "Sahil", "email": "s@example.com"}'
            ),
        )

    provider.responder = responder

    result = await client.complete_structured(
        messages=[ChatMessage(role="user", content="book me an interview")], schema=Booking
    )

    assert result.name == "Sahil"


async def test_a_misconfigured_provider_is_not_retried_in_plain_text(
    client: LLMClient, provider: FakeProvider
) -> None:
    """A 401 is a bad key, not a missing JSON mode - retrying would only hide it."""
    provider.responder = lambda request: httpx2.Response(
        401, json={"error": {"message": "bad key"}}
    )

    with pytest.raises(UpstreamError):
        await client.complete_structured(
            messages=[ChatMessage(role="user", content="hi")], schema=Booking
        )

    assert len(provider.requests) == 1


async def test_without_an_api_key_the_call_fails(provider: FakeProvider) -> None:
    http_client = provider.http_client()
    client = LLMClient(api_key="", model="test-model", http_client=http_client)

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert "LLM_API_KEY" in str(excinfo.value)
    assert provider.requests == []
    await http_client.aclose()


async def test_a_server_error_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 500


async def test_a_rate_limit_is_retried_and_then_reported(
    client: LLMClient, provider: FakeProvider
) -> None:
    provider.responder = lambda request: httpx2.Response(
        429, json={"error": {"message": "slow down"}}
    )

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 429
    # Two retries on top of the first attempt.
    assert len(provider.requests) == 3


async def test_a_bad_request_is_not_retried(client: LLMClient, provider: FakeProvider) -> None:
    provider.responder = lambda request: httpx2.Response(400, json={"error": {"message": "nope"}})

    with pytest.raises(UpstreamError) as excinfo:
        await client.complete(messages=[ChatMessage(role="user", content="hi")])

    assert excinfo.value.details["status_code"] == 400
    assert len(provider.requests) == 1


async def test_a_connection_error_is_an_upstream_error(
    client: LLMClient, provider: FakeProvider
) -> None:
    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host", request=request)

    provider.responder = boom

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
