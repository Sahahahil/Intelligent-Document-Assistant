"""A scripted stand-in for the LLM client."""

from collections.abc import Sequence
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from app.integrations.llm import ChatMessage

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeLLM:
    """Replays queued replies and records what it was asked.

    Queue a string to be returned, or an exception to be raised. `complete`
    hands the reply back as text; `complete_structured` parses it as JSON and
    validates it against the schema it was given.
    """

    def __init__(self, *replies: str | Exception) -> None:
        self.replies: list[str | Exception] = list(replies)
        self.calls: list[dict[str, Any]] = []

    def queue(self, *replies: str | Exception) -> "FakeLLM":
        """Queue replies — the next calls get them, in order."""
        self.replies[0:0] = replies
        return self

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append({"messages": list(messages), "temperature": temperature, "schema": None})
        reply = self._next()
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def complete_structured(
        self,
        *,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        temperature: float = 0.0,
    ) -> SchemaT:
        self.calls.append(
            {"messages": list(messages), "temperature": temperature, "schema": schema}
        )
        reply = self._next()
        if isinstance(reply, Exception):
            raise reply
        return schema.model_validate_json(reply)

    def _next(self) -> str | Exception:
        if not self.replies:
            raise AssertionError("FakeLLM has no queued reply")
        return self.replies.pop(0)

    @property
    def sent(self) -> list[ChatMessage]:
        """The messages of the first call."""
        return cast(list[ChatMessage], self.calls[0]["messages"])
