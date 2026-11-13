"""The chat orchestrator against a live Redis.

Run with:  uv run pytest -m integration

The RAG service is a fake - the point here is that the exchange really lands
in Redis and comes back out.
"""

from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.integrations.llm import ChatMessage
from app.schemas.chat import ChatRequest
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.conversation_service import KEY_PREFIX, ConversationStore
from app.services.rag_service import RAGAnswer, RAGService

pytestmark = pytest.mark.integration

SESSION_ID = f"test-{uuid4()}"


class FakeRagService:
    async def answer(
        self,
        message: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[UUID] | None = None,
    ) -> RAGAnswer:
        return RAGAnswer(
            answer="the answer",
            sources=[],
            rewritten_query=message,
            context_used=False,
        )


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def store(redis_client: Redis) -> AsyncIterator[ConversationStore]:
    conversation_store = ConversationStore(redis_client, ttl_seconds=60)
    yield conversation_store
    await redis_client.delete(f"{KEY_PREFIX}{SESSION_ID}")


@pytest.fixture
def orchestrator(store: ConversationStore) -> ChatOrchestrator:
    return ChatOrchestrator(
        rag=cast(RAGService, FakeRagService()),
        store=store,
    )


async def test_the_exchange_is_stored(
    orchestrator: ChatOrchestrator, store: ConversationStore
) -> None:
    await orchestrator.handle(ChatRequest(session_id=SESSION_ID, message="what is ml?"))

    history = await store.get_history(SESSION_ID)

    assert [message.role for message in history] == ["user", "assistant"]
    assert [message.content for message in history] == ["what is ml?", "the answer"]


async def test_the_second_turn_sees_the_first(
    orchestrator: ChatOrchestrator, store: ConversationStore
) -> None:
    await orchestrator.handle(ChatRequest(session_id=SESSION_ID, message="what is ml?"))

    history = await store.get_history(SESSION_ID)

    assert len(history) == 2
