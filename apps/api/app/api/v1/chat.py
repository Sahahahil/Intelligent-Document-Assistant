"""The conversational RAG endpoint."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

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


@router.post("/stream", summary="Stream a message answer via SSE")
async def chat_stream(
    request: ChatRequest,
    orchestrator: Annotated[ChatOrchestrator, Depends(get_chat_orchestrator)],
) -> EventSourceResponse:
    """Stream an answer via Server-Sent Events."""

    async def event_generator():
        async for item in orchestrator.astream(request):
            yield {"data": json.dumps(item)}

    return EventSourceResponse(event_generator())
