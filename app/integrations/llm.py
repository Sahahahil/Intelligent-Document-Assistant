"""One async client for the configured LLM provider.

Any OpenAI-compatible endpoint works — OpenAI, Groq, Gemini's compatibility
layer, a local vLLM — by changing `.env`, not the code.

Retries are the SDK's: it retries 408, 409, 429 and 5xx twice with
exponential backoff, and never retries a 4xx like 400.
"""

import json
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Literal, TypeVar

from openai import APIConnectionError, APIError, APIStatusError, AsyncOpenAI, Omit
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


class ChatMessage(BaseModel):
    """One message in a conversation."""

    role: Role
    content: str


def _to_param(message: ChatMessage) -> ChatCompletionMessageParam:
    """The SDK types each role separately, so the role picks the shape."""
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role="system", content=message.content)
    if message.role == "assistant":
        return ChatCompletionAssistantMessageParam(role="assistant", content=message.content)
    return ChatCompletionUserMessageParam(role="user", content=message.content)


class LLMClient:
    """Talks to the configured LLM provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = settings.llm_api_key if api_key is None else api_key
        self._base_url = settings.llm_base_url if base_url is None else base_url
        self._model = settings.llm_model if model is None else model
        self._client = AsyncOpenAI(
            api_key=self._api_key or _PLACEHOLDER_KEY,
            base_url=self._base_url or None,
            timeout=60.0,
        )

    @property
    def model(self) -> str:
        return self._model

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

    async def complete_json(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """The assistant's reply as a JSON object."""
        content = await self._request(
            messages,
            temperature=temperature,
            max_tokens=None,
            response_format=ResponseFormatJSONObject(type="json_object"),
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise UpstreamError(
                "LLM returned invalid JSON", details={"raw": content[:500]}
            ) from exc
        if not isinstance(payload, dict):
            raise UpstreamError(
                "LLM returned JSON that is not an object", details={"raw": content[:500]}
            )
        return payload

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
        payload = await self.complete_json(
            messages=[*messages, ChatMessage(role="system", content=hint)],
            temperature=temperature,
        )
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            # The provider answered, but not in the shape we asked for.
            raise UpstreamError(
                "LLM output did not match the expected schema",
                details={
                    "errors": exc.errors(
                        include_url=False, include_context=False, include_input=False
                    )[:5],
                    "raw": payload,
                },
            ) from exc

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
