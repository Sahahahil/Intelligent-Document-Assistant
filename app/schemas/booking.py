"""Booking schemas: what the LLM extracts, and what the API returns."""

from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BookingFields(BaseModel):
    """The four details a booking needs. All optional - a partial answer is valid."""

    name: str | None = None
    email: EmailStr | None = None
    interview_date: date | None = None
    interview_time: time | None = None


class BookingExtraction(BaseModel):
    """What the LLM read out of one message."""

    is_booking_request: bool = False
    fields: BookingFields = Field(default_factory=BookingFields)
    confirmed_by_user: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class BookingModel(BaseModel):
    """A booking, as the API returns it."""

    id: UUID | None = None
    name: str | None = None
    email: str | None = None
    interview_date: date | None = None
    interview_time: time | None = None
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    missing_fields: list[str] = Field(default_factory=list)
    awaiting_confirmation: bool = False
