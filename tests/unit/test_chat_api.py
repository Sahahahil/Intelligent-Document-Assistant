"""HTTP tests for the chat API.

The orchestrator and the conversation store are replaced with fakes through
FastAPI's dependency overrides - this exercises the HTTP layer only.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_chat_orchestrator, get_conversation_store
from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage
from app.main import app
from app.schemas.chat import ChatRequest, ChatResponse, SourceModel


class FakeOrchestrator:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []
        self.error: Exception | None = None

    async def handle(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ChatResponse(
            session_id=request.session_id,
            answer="an answer",
            sources=[
                SourceModel(
                    document_id=uuid4(),
                    filename="notes.pdf",
                    chunk_index=0,
                    score=0.87,
                )
            ],
            booking=None,
            context_used=True,
            created_at=datetime.now(UTC),
        )


class FakeConversationStore:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.cleared: list[str] = []

    async def get_history(self, session_id: str, *, limit: int = 20) -> list[ChatMessage]:
        return self.messages[:limit]

    async def clear(self, session_id: str) -> None:
        self.cleared.append(session_id)
        self.messages = []


@pytest.fixture
def orchestrator() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
def store() -> FakeConversationStore:
    return FakeConversationStore()


@pytest.fixture
async def client(
    orchestrator: FakeOrchestrator, store: FakeConversationStore
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_conversation_store] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_a_message_gets_an_answer(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat", json={"session_id": "s1", "message": "what is machine learning?"}
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["session_id"] == "s1"
    assert body["answer"] == "an answer"
    assert body["context_used"] is True
    assert body["booking"] is None
    assert body["sources"][0]["filename"] == "notes.pdf"
    assert body["created_at"]


async def test_the_document_scope_is_forwarded(
    client: AsyncClient, orchestrator: FakeOrchestrator
) -> None:
    document_id = str(uuid4())

    await client.post(
        "/api/v1/chat",
        json={"session_id": "s1", "message": "hello", "document_ids": [document_id]},
    )

    assert orchestrator.requests[0].document_ids == [UUID(document_id)]


async def test_an_empty_message_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"session_id": "s1", "message": ""})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "validation_error"


async def test_an_unsafe_session_id_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"session_id": "bad id!", "message": "hello"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_too_long_message_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"session_id": "s1", "message": "x" * 8001})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_an_llm_failure_is_a_502(client: AsyncClient, orchestrator: FakeOrchestrator) -> None:
    orchestrator.error = UpstreamError("LLM error: 500")

    response = await client.post("/api/v1/chat", json={"session_id": "s1", "message": "hello"})

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json()["error"]["code"] == "upstream_error"


async def test_the_session_history_is_returned(
    client: AsyncClient, store: FakeConversationStore
) -> None:
    store.messages = [
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi"),
    ]

    response = await client.get("/api/v1/chat/sessions/s1")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["session_id"] == "s1"
    assert [message["content"] for message in body["messages"]] == ["hello", "hi"]


async def test_an_unknown_session_has_an_empty_history(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chat/sessions/nobody")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["messages"] == []


async def test_clearing_a_session_empties_it(
    client: AsyncClient, store: FakeConversationStore
) -> None:
    store.messages = [ChatMessage(role="user", content="hello")]

    response = await client.delete("/api/v1/chat/sessions/s1")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert store.cleared == ["s1"]
    follow_up = await client.get("/api/v1/chat/sessions/s1")
    assert follow_up.json()["messages"] == []


async def test_an_unsafe_session_id_in_the_path_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chat/sessions/bad$id")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_routes_are_documented(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    paths = response.json()["paths"]
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/sessions/{session_id}" in paths
    assert "post" in paths["/api/v1/chat"]
    assert "get" in paths["/api/v1/chat/sessions/{session_id}"]
    assert "delete" in paths["/api/v1/chat/sessions/{session_id}"]
