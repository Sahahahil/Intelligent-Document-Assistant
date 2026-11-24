"""One async client for the configured LLM provider.

Any OpenAI-compatible endpoint works — OpenAI, Groq, Gemini's compatibility
layer, a local vLLM — by changing `.env`, not the code.

Retries are the SDK's: it retries 408, 409, 429 and 5xx twice with
exponential backoff, and never retries a 4xx like 400.
"""

import json
import logging
from collections.abc import Iterator, Sequence
from datetime import datetime
from functools import lru_cache
from typing import Literal, TypeVar

import httpx2
from openai import APIConnectionError, APIError, APIStatusError, AsyncOpenAI, Omit
from openai.types.chat import ChatCompletionChunk
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import UpstreamError

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

Role = Literal["system", "user", "assistant"]

# The SDK refuses to be constructed without a key, but the app must still boot
# without one — a missing key is the call's problem, not startup's.
_PLACEHOLDER_KEY = "not-configured"

# A provider that does not implement the JSON mode rejects the parameter or
# fails the request outright. Those are the statuses worth a second, plain-text
# attempt — a 401 or a 404 is a misconfiguration, and retrying would only hide
# it.
_JSON_MODE_RETRY_STATUSES = frozenset({400, 422, 500})


def _balanced_object(text: str, start: int) -> str | None:
    """The JSON object that starts at `start`, or None if it never closes."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _json_objects(text: str) -> Iterator[str]:
    """Every JSON object in the text, in order."""
    for start in range(len(text)):
        if text[start] != "{":
            continue
        candidate = _balanced_object(text, start)
        if candidate is not None:
            yield candidate


class ChatMessage(BaseModel):
    """One message in a conversation.

    `created_at` is stamped by the conversation store (T13); the LLM client
    ignores it.
    """

    role: Role
    content: str
    created_at: datetime | None = None


def _to_param(message: ChatMessage) -> ChatCompletionMessageParam:
    """The SDK types each role separately, so the role picks the shape."""
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role="system", content=message.content)
    if message.role == "assistant":
        return ChatCompletionAssistantMessageParam(role="assistant", content=message.content)
    return ChatCompletionUserMessageParam(role="user", content=message.content)


def _with_schema_hint(messages: Sequence[ChatMessage], hint: str) -> list[ChatMessage]:
    """The schema hint belongs with the system prompt.

    A system message *after* the user turn is not what a chat model expects:
    asked that way, a small model answers by echoing the schema instead of
    filling it in. So the hint is merged into the system prompt, and only
    becomes a system message of its own when there is none.
    """
    payload = list(messages)
    for index, message in enumerate(payload):
        if message.role == "system":
            payload[index] = ChatMessage(role="system", content=f"{message.content}\n\n{hint}")
            return payload
    return [ChatMessage(role="system", content=hint), *payload]


class LLMClient:
    """Talks to the configured LLM provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        """The client.

        `http_client` is the seam the tests use: they pass one whose transport
        is a mock, so the whole SDK stack runs without a network.
        """
        settings = get_settings()
        self._api_key = settings.llm_api_key if api_key is None else api_key
        self._base_url = settings.llm_base_url if base_url is None else base_url
        self._model = settings.llm_model if model is None else model
        self._client = AsyncOpenAI(
            api_key=self._api_key or _PLACEHOLDER_KEY,
            base_url=self._base_url or None,
            timeout=60.0,
            http_client=http_client,
        )

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """The assistant's reply as plain text."""
        content = await self._request(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=Omit(),
        )
        return content.strip()

    async def astream(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ):
        """Stream the assistant's reply token by token."""
        self._require_configured()
        logger.debug("LLM stream request: model=%s messages=%d", self._model, len(messages))
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[_to_param(message) for message in messages],
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else Omit(),
                stream=True,
            )
        except APIStatusError as exc:
            raise UpstreamError(
                f"LLM stream request failed with status {exc.status_code}",
                details={"status_code": exc.status_code, "body": str(exc.body)[:500]},
            ) from exc
        except APIConnectionError as exc:
            raise UpstreamError(f"Could not reach the LLM provider: {exc}") from exc
        except APIError as exc:
            raise UpstreamError(f"LLM stream request failed: {exc}") from exc

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def complete_structured(
        self,
        *,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        temperature: float = 0.0,
    ) -> SchemaT:
        """The assistant's reply, validated against a Pydantic schema."""
        hint = (
            "Respond with a JSON object only, matching this schema exactly:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        payload = _with_schema_hint(messages, hint)
        content = await self._structured_request(payload, schema, temperature=temperature)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise UpstreamError(
                "LLM returned invalid JSON", details={"raw": content[:500]}
            ) from exc
        if not isinstance(parsed, dict):
            raise UpstreamError(
                "LLM returned JSON that is not an object", details={"raw": content[:500]}
            )
        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            # The provider answered, but not in the shape we asked for.
            raise UpstreamError(
                "LLM output did not match the expected schema",
                details={
                    "errors": exc.errors(
                        include_url=False, include_context=False, include_input=False
                    )[:5],
                    "raw": parsed,
                },
            ) from exc

    async def _structured_request(
        self, payload: Sequence[ChatMessage], schema: type[SchemaT], *, temperature: float
    ) -> str:
        """The JSON answer, asking again in plain text if the JSON mode fails.

        A provider that does not implement the JSON mode either rejects the
        parameter or answers with something that is not JSON. Both are worth
        one plain-text retry, because the model can still produce the object.
        """
        try:
            content = await self._request(
                payload,
                temperature=temperature,
                max_tokens=None,
                response_format=ResponseFormatJSONObject(type="json_object"),
            )
            json.loads(content)  # it only counts as a success if it is JSON
            return content
        except UpstreamError as exc:
            if exc.details.get("status_code") not in _JSON_MODE_RETRY_STATUSES:
                raise
        except json.JSONDecodeError:
            pass
        logger.info("JSON mode unusable; retrying the request in plain text")
        raw = await self._request(
            payload, temperature=temperature, max_tokens=None, response_format=Omit()
        )
        return self._object_matching(raw, schema)

    @staticmethod
    def _object_matching(text: str, schema: type[SchemaT]) -> str:
        """The first object in the text that fits the schema.

        A model asked for JSON often wraps it in prose or a code fence, and it
        sometimes answers with the schema itself - so every object in the
        answer is tried until one validates.
        """
        for candidate in _json_objects(text):
            try:
                payload = json.loads(candidate)
                schema.model_validate(payload)
            except (json.JSONDecodeError, ValidationError):
                continue
            return candidate
        raise UpstreamError(
            "LLM returned no JSON that matches the schema", details={"raw": text[:500]}
        )

    async def _request(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float,
        max_tokens: int | None,
        response_format: ResponseFormat | Omit,
    ) -> str:
        """One chat completion, with every provider failure mapped to 502."""
        self._require_configured()
        logger.debug("LLM request: model=%s messages=%d", self._model, len(messages))
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[_to_param(message) for message in messages],
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else Omit(),
                response_format=response_format,
            )
        except APIStatusError as exc:
            raise UpstreamError(
                f"LLM request failed with status {exc.status_code}",
                details={"status_code": exc.status_code, "body": str(exc.body)[:500]},
            ) from exc
        except APIConnectionError as exc:
            raise UpstreamError(f"Could not reach the LLM provider: {exc}") from exc
        except APIError as exc:
            raise UpstreamError(f"LLM request failed: {exc}") from exc

        content = response.choices[0].message.content or ""
        logger.debug("LLM response: %s", content[:500])
        return content

    def _require_configured(self) -> None:
        if not self._api_key:
            raise UpstreamError("LLM_API_KEY is not configured")
        if not self._model:
            raise UpstreamError("LLM_MODEL is not configured")


@lru_cache
def get_llm_client() -> LLMClient:
    """The process-wide client — it holds the connection pool."""
    return LLMClient()
