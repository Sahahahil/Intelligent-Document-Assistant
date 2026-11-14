"""The conversational RAG endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_chat_orchestrator
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_orchestrator import ChatOrchestrator

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Send a message and get an answer")
async def chat(
    request: ChatRequest,
    orchestrator: Annotated[ChatOrchestrator, Depends(get_chat_orchestrator)],
) -> ChatResponse:
    """Answer a message from the ingested documents."""
    return await orchestrator.handle(request)
