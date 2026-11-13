"""Request and response models for the conversational RAG API."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.integrations.llm import Role

# The session id becomes a Redis key, so it is kept to a safe charset.
SESSION_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"


class ChatRequest(BaseModel):
    """One message in a session."""

    session_id: str = Field(min_length=1, max_length=128, pattern=SESSION_ID_PATTERN)
    message: str = Field(min_length=1, max_length=8000)
    document_ids: list[UUID] | None = None


class SourceModel(BaseModel):
    """A chunk the answer was built from."""

    document_id: UUID
    filename: str
    chunk_index: int
    score: float


class BookingModel(BaseModel):
    """The booking draft - populated by the booking flow (T18-T20)."""

    id: UUID | None = None
    name: str | None = None
    email: str | None = None
    interview_date: date | None = None
    interview_time: time | None = None
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    missing_fields: list[str] = Field(default_factory=list)
    awaiting_confirmation: bool = False


class ChatResponse(BaseModel):
    """The assistant's reply to one message."""

    session_id: str
    answer: str
    sources: list[SourceModel] = Field(default_factory=list)
    booking: BookingModel | None = None
    context_used: bool = True
    created_at: datetime


class SessionMessageModel(BaseModel):
    """One stored message."""

    role: Role
    content: str
    created_at: datetime | None = None


class SessionHistoryResponse(BaseModel):
    """A session's stored conversation."""

    session_id: str
    messages: list[SessionMessageModel] = Field(default_factory=list)
