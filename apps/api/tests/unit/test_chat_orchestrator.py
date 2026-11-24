"""Chat orchestrator tests - the RAG service and the store are fakes."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.integrations.llm import ChatMessage
from app.schemas.booking import BookingModel
from app.schemas.chat import ChatRequest
from app.services.booking_service import BookingService, BookingTurn
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.conversation_service import ConversationStore
from app.services.rag_service import RAGAnswer, RAGService
from app.services.retrieval_service import SourceReference


class FakeRagService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.reply = "the answer"

    async def answer(
        self,
        message: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[UUID] | None = None,
    ) -> RAGAnswer:
        self.calls.append({"message": message, "history": history, "document_ids": document_ids})
        return RAGAnswer(
            answer=self.reply,
            sources=[
                SourceReference(
                    document_id=uuid4(),
                    filename="notes.pdf",
                    chunk_index=3,
                    score=0.9123,  # the RAG service rounds the score
                )
            ],
            rewritten_query=message,
            context_used=True,
        )


class FakeBookingService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.turn = BookingTurn(
            is_booking=False,
            reply=None,
            booking=None,
            missing_fields=[],
            awaiting_confirmation=False,
            persisted=False,
        )

    async def handle_turn(
        self, *, session_id: str, message: str, history: Sequence[ChatMessage]
    ) -> BookingTurn:
        self.calls.append({"session_id": session_id, "message": message, "history": history})
        return self.turn


class FakeStore:
    def __init__(self) -> None:
        self.history: list[ChatMessage] = []
        self.appended: list[tuple[str, str, str]] = []

    async def get_history(self, session_id: str, *, limit: int = 20) -> list[ChatMessage]:
        return self.history[:limit]

    async def append(self, session_id: str, role: str, content: str) -> None:
        self.appended.append((session_id, role, content))


@pytest.fixture
def rag() -> FakeRagService:
    return FakeRagService()


@pytest.fixture
def booking() -> FakeBookingService:
    return FakeBookingService()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def orchestrator(
    rag: FakeRagService, booking: FakeBookingService, store: FakeStore
) -> ChatOrchestrator:
    return ChatOrchestrator(
        rag=cast(RAGService, rag),
        booking=cast(BookingService, booking),
        store=cast(ConversationStore, store),
    )


async def test_the_history_is_loaded_and_passed_on(
    orchestrator: ChatOrchestrator, rag: FakeRagService, store: FakeStore
) -> None:
    store.history = [ChatMessage(role="user", content="earlier")]

    await orchestrator.handle(ChatRequest(session_id="s1", message="and now?"))

    assert rag.calls[0]["history"] == store.history


async def test_both_sides_of_the_exchange_are_persisted(
    orchestrator: ChatOrchestrator, store: FakeStore
) -> None:
    await orchestrator.handle(ChatRequest(session_id="s1", message="what is ml?"))

    assert store.appended == [
        ("s1", "user", "what is ml?"),
        ("s1", "assistant", "the answer"),
    ]


async def test_the_response_carries_the_answer_and_the_sources(
    orchestrator: ChatOrchestrator,
) -> None:
    response = await orchestrator.handle(ChatRequest(session_id="s1", message="what is ml?"))

    assert response.session_id == "s1"
    assert response.answer == "the answer"
    assert response.context_used is True
    assert response.booking is None
    assert response.sources[0].filename == "notes.pdf"
    assert response.sources[0].chunk_index == 3
    assert response.sources[0].score == 0.9123
    assert response.created_at <= datetime.now(UTC)


async def test_the_document_scope_is_forwarded(
    orchestrator: ChatOrchestrator, rag: FakeRagService
) -> None:
    document_id = uuid4()

    await orchestrator.handle(
        ChatRequest(session_id="s1", message="what is ml?", document_ids=[document_id])
    )

    assert rag.calls[0]["document_ids"] == [document_id]


async def test_a_booking_turn_skips_the_rag_service(
    orchestrator: ChatOrchestrator, rag: FakeRagService, booking: FakeBookingService
) -> None:
    booking.turn = BookingTurn(
        is_booking=True,
        reply="Sure - I need your name, email, date and time.",
        booking=BookingModel(missing_fields=["name", "email", "date", "time"]),
        missing_fields=["name", "email", "date", "time"],
        awaiting_confirmation=False,
        persisted=False,
    )

    response = await orchestrator.handle(ChatRequest(session_id="s1", message="schedule one"))

    assert rag.calls == []
    assert response.answer == "Sure - I need your name, email, date and time."
    assert response.sources == []
    assert response.booking is not None
    assert response.booking.missing_fields == ["name", "email", "date", "time"]
    assert response.context_used is False


async def test_a_booking_turn_is_persisted_too(
    orchestrator: ChatOrchestrator, store: FakeStore, booking: FakeBookingService
) -> None:
    booking.turn = BookingTurn(
        is_booking=True,
        reply="Please confirm to book.",
        booking=BookingModel(awaiting_confirmation=True),
        missing_fields=[],
        awaiting_confirmation=True,
        persisted=False,
    )

    await orchestrator.handle(ChatRequest(session_id="s1", message="schedule one"))

    assert store.appended == [
        ("s1", "user", "schedule one"),
        ("s1", "assistant", "Please confirm to book."),
    ]


async def test_the_booking_service_gets_the_history(
    orchestrator: ChatOrchestrator, booking: FakeBookingService, store: FakeStore
) -> None:
    store.history = [ChatMessage(role="user", content="earlier")]

    await orchestrator.handle(ChatRequest(session_id="s1", message="and now?"))

    assert booking.calls[0]["history"] == store.history
    assert booking.calls[0]["session_id"] == "s1"


async def test_a_confirmed_booking_is_returned(
    orchestrator: ChatOrchestrator, booking: FakeBookingService
) -> None:
    booked = BookingModel(id=uuid4(), name="Sahil", status="confirmed")
    booking.turn = BookingTurn(
        is_booking=True,
        reply="Your interview request has been recorded.",
        booking=booked,
        missing_fields=[],
        awaiting_confirmation=False,
        persisted=True,
    )

    response = await orchestrator.handle(ChatRequest(session_id="s1", message="yes"))

    assert response.booking is not None
    assert response.booking.id == booked.id
    assert response.booking.status == "confirmed"
