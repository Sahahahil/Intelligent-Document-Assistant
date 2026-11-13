"""Conversation store tests against a live Redis.

Run with:  uv run pytest -m integration

Every test uses its own session id and cleans up after itself.
"""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.exceptions import UpstreamError
from app.services.conversation_service import KEY_PREFIX, ConversationStore

pytestmark = pytest.mark.integration

TTL = 60
MAX_MESSAGES = 5


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def store(redis_client: Redis) -> AsyncIterator[ConversationStore]:
    conversation_store = ConversationStore(redis_client, ttl_seconds=TTL, max_messages=MAX_MESSAGES)
    yield conversation_store
    await redis_client.delete(f"{KEY_PREFIX}{SESSION_ID}")


SESSION_ID = f"test-{uuid4()}"


async def test_the_messages_come_back_in_order(
    store: ConversationStore, redis_client: Redis
) -> None:
    await store.append(SESSION_ID, "user", "hello")
    await store.append(SESSION_ID, "assistant", "hi there")

    history = await store.get_history(SESSION_ID)

    assert [message.role for message in history] == ["user", "assistant"]
    assert [message.content for message in history] == ["hello", "hi there"]
    assert history[0].created_at is not None


async def test_an_unknown_session_has_no_history(store: ConversationStore) -> None:
    assert await store.get_history(f"nobody-{uuid4()}") == []


async def test_the_key_is_namespaced_and_expires(
    store: ConversationStore, redis_client: Redis
) -> None:
    await store.append(SESSION_ID, "user", "hello")

    ttl = await redis_client.ttl(f"{KEY_PREFIX}{SESSION_ID}")

    assert 0 < ttl <= TTL


async def test_the_ttl_is_refreshed_on_every_append(
    redis_client: Redis,
) -> None:
    session_id = f"test-{uuid4()}"
    store = ConversationStore(redis_client, ttl_seconds=2, max_messages=MAX_MESSAGES)
    key = f"{KEY_PREFIX}{session_id}"
    try:
        await store.append(session_id, "user", "hello")
        await asyncio.sleep(1.2)
        assert await redis_client.ttl(key) <= 1

        await store.append(session_id, "user", "again")

        assert await redis_client.ttl(key) == 2
    finally:
        await redis_client.delete(key)


async def test_the_list_never_grows_past_the_maximum(store: ConversationStore) -> None:
    for index in range(MAX_MESSAGES + 5):
        await store.append(SESSION_ID, "user", f"message {index}")

    history = await store.get_history(SESSION_ID, limit=100)

    assert len(history) == MAX_MESSAGES
    assert history[0].content == "message 5"
    assert history[-1].content == f"message {MAX_MESSAGES + 4}"


async def test_the_history_is_limited_to_the_last_messages(store: ConversationStore) -> None:
    for index in range(4):
        await store.append(SESSION_ID, "user", f"message {index}")

    history = await store.get_history(SESSION_ID, limit=2)

    assert [message.content for message in history] == ["message 2", "message 3"]


async def test_a_zero_limit_returns_nothing(store: ConversationStore) -> None:
    await store.append(SESSION_ID, "user", "hello")

    assert await store.get_history(SESSION_ID, limit=0) == []


async def test_clearing_forgets_the_session(store: ConversationStore) -> None:
    await store.append(SESSION_ID, "user", "hello")
    assert await store.exists(SESSION_ID) is True

    await store.clear(SESSION_ID)

    assert await store.exists(SESSION_ID) is False
    assert await store.get_history(SESSION_ID) == []


async def test_an_unreachable_redis_becomes_an_upstream_error() -> None:
    client = Redis.from_url(
        "redis://localhost:6399/0",
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=1,
    )
    store = ConversationStore(client, ttl_seconds=TTL)
    try:
        with pytest.raises(UpstreamError):
            await store.get_history(SESSION_ID)
    finally:
        await client.aclose()


async def test_unicode_and_newlines_round_trip(store: ConversationStore) -> None:
    content = "línea uno\nlínea dos — ünïcode ✨"

    await store.append(SESSION_ID, "user", content)

    history = await store.get_history(SESSION_ID)
    assert history[0].content == content


async def test_a_session_id_with_a_colon_works(store: ConversationStore) -> None:
    await store.append("a:b", "user", "hello")

    history = await store.get_history("a:b")
    assert history[0].content == "hello"
    await store.clear("a:b")


async def test_a_corrupt_entry_is_skipped(store: ConversationStore, redis_client: Redis) -> None:
    key = f"{KEY_PREFIX}{SESSION_ID}"
    await redis_client.rpush(key, "not json")
    await store.append(SESSION_ID, "user", "hello")

    history = await store.get_history(SESSION_ID)

    assert [message.content for message in history] == ["hello"]


async def test_concurrent_appends_both_land(store: ConversationStore) -> None:
    await asyncio.gather(
        store.append(SESSION_ID, "user", "first"),
        store.append(SESSION_ID, "assistant", "second"),
    )

    history = await store.get_history(SESSION_ID)

    assert [message.content for message in history] == ["first", "second"]
