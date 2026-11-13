"""Conversation memory in Redis - one list per session, with a sliding TTL.

A list (not a string) so concurrent turns in the same session cannot
overwrite each other.
"""

import json
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import get_settings
from app.integrations.llm import ChatMessage
from app.integrations.redis import redis_guard

logger = logging.getLogger(__name__)

KEY_PREFIX = "conversation:"


class ConversationStore:
    """Append-only per-session history, capped in length and expiring when idle."""

    def __init__(
        self,
        redis: Redis,
        *,
        ttl_seconds: int | None = None,
        max_messages: int = 40,
    ) -> None:
        settings = get_settings()
        self._redis = redis
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.session_ttl_seconds
        self._max = max_messages

    async def get_history(self, session_id: str, *, limit: int = 20) -> list[ChatMessage]:
        """The most recent messages, oldest first."""
        if limit <= 0:
            return []
        key = self._key(session_id)
        async with redis_guard():
            raw = await self._redis.lrange(key, -limit, -1)
        messages: list[ChatMessage] = []
        for item in raw:
            try:
                payload = json.loads(item)
                messages.append(
                    ChatMessage(
                        role=payload["role"],
                        content=payload["content"],
                        created_at=datetime.fromisoformat(payload["created_at"]),
                    )
                )
            except (ValueError, KeyError, TypeError):
                logger.warning("Skipping a corrupt conversation entry in %s", key)
        return messages

    async def append(self, session_id: str, role: str, content: str) -> None:
        """Store a message, cap the list and refresh the session's TTL."""
        payload = json.dumps(
            {"role": role, "content": content, "created_at": datetime.now(UTC).isoformat()}
        )
        key = self._key(session_id)
        # One round trip, and the trim cannot be seen without the expiry.
        async with redis_guard(), self._redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -self._max, -1)
            pipe.expire(key, self._ttl)
            await pipe.execute()

    async def clear(self, session_id: str) -> None:
        """Forget the session."""
        async with redis_guard():
            await self._redis.delete(self._key(session_id))

    async def exists(self, session_id: str) -> bool:
        """Whether the session has any stored messages."""
        async with redis_guard():
            return bool(await self._redis.exists(self._key(session_id)))

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{KEY_PREFIX}{session_id}"
