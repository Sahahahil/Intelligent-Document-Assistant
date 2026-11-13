"""One conversational turn: route it, answer it, then remember the exchange.

A booking request is not a document question, so the booking check runs first:
the booking turns never pay for retrieval or an answer-generation call.
"""

from datetime import UTC, datetime

from app.schemas.chat import ChatRequest, ChatResponse, SourceModel
from app.services.booking_service import BookingService
from app.services.conversation_service import ConversationStore
from app.services.rag_service import RAGService

MAX_HISTORY = 20


class ChatOrchestrator:
    """Runs one chat turn end to end."""

    def __init__(
        self, *, rag: RAGService, booking: BookingService, store: ConversationStore
    ) -> None:
        self._rag = rag
        self._booking = booking
        self._store = store

    async def handle(self, request: ChatRequest) -> ChatResponse:
        """Route the message, answer it, then persist both sides of the exchange."""
        history = await self._store.get_history(request.session_id, limit=MAX_HISTORY)

        turn = await self._booking.handle_turn(
            session_id=request.session_id, message=request.message, history=history
        )
        if turn.is_booking:
            answer = turn.reply or ""
            sources: list[SourceModel] = []
            booking = turn.booking
            context_used = False
        else:
            result = await self._rag.answer(
                request.message, history=history, document_ids=request.document_ids
            )
            answer = result.answer
            sources = [
                SourceModel(
                    document_id=source.document_id,
                    filename=source.filename,
                    chunk_index=source.chunk_index,
                    score=source.score,
                )
                for source in result.sources
            ]
            booking = None
            context_used = result.context_used

        await self._store.append(request.session_id, "user", request.message)
        await self._store.append(request.session_id, "assistant", answer)
        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            sources=sources,
            booking=booking,
            context_used=context_used,
            created_at=datetime.now(UTC),
        )
