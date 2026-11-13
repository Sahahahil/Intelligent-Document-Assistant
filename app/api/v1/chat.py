"""The conversational RAG endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.api.deps import get_chat_orchestrator, get_conversation_store
from app.schemas.chat import (
    SESSION_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    SessionHistoryResponse,
    SessionMessageModel,
)
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.conversation_service import ConversationStore

router = APIRouter(prefix="/chat", tags=["chat"])

SessionId = Annotated[str, Path(min_length=1, max_length=128, pattern=SESSION_ID_PATTERN)]


@router.post("", response_model=ChatResponse, summary="Send a message and get an answer")
async def chat(
    request: ChatRequest,
    orchestrator: Annotated[ChatOrchestrator, Depends(get_chat_orchestrator)],
) -> ChatResponse:
    """Answer a message from the ingested documents."""
    return await orchestrator.handle(request)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionHistoryResponse,
    summary="Inspect a stored conversation",
)
async def get_session(
    session_id: SessionId,
    store: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> SessionHistoryResponse:
    """The messages stored for a session, oldest first."""
    messages = await store.get_history(session_id)
    return SessionHistoryResponse(
        session_id=session_id,
        messages=[
            SessionMessageModel(
                role=message.role, content=message.content, created_at=message.created_at
            )
            for message in messages
        ],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear a stored conversation",
)
async def clear_session(
    session_id: SessionId,
    store: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> Response:
    """Forget everything stored for a session."""
    await store.clear(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
