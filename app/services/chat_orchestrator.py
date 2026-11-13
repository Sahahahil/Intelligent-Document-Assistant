"""One conversational turn: answer the question, then remember the exchange.

T20 adds the booking branch - a booking request is not a document question.
"""

from datetime import UTC, datetime

from app.schemas.chat import ChatRequest, ChatResponse, SourceModel
from app.services.conversation_service import ConversationStore
from app.services.rag_service import RAGService

MAX_HISTORY = 20


class ChatOrchestrator:
    """Runs one chat turn end to end."""

    def __init__(self, *, rag: RAGService, store: ConversationStore) -> None:
        self._rag = rag
        self._store = store

    async def handle(self, request: ChatRequest) -> ChatResponse:
        """Answer the message, then persist both sides of the exchange."""
        history = await self._store.get_history(request.session_id, limit=MAX_HISTORY)
        result = await self._rag.answer(
            request.message, history=history, document_ids=request.document_ids
        )
        await self._store.append(request.session_id, "user", request.message)
        await self._store.append(request.session_id, "assistant", result.answer)
        return ChatResponse(
            session_id=request.session_id,
            answer=result.answer,
            sources=[
                SourceModel(
                    document_id=source.document_id,
                    filename=source.filename,
                    chunk_index=source.chunk_index,
                    score=source.score,
                )
                for source in result.sources
            ],
            booking=None,
            context_used=result.context_used,
            created_at=datetime.now(UTC),
        )
