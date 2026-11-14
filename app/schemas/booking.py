"""Booking schemas: what the LLM extracts, and what the API returns."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.booking import BookingStatus


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
    cancels_booking: bool = False


class BookingModel(BaseModel):
    """A booking, as the API returns it.

    `pending` means a draft that is not stored yet - stored rows are only
    ever confirmed or cancelled.
    """

    id: UUID | None = None
    name: str | None = None
    email: str | None = None
    interview_date: date | None = None
    interview_time: time | None = None
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    missing_fields: list[str] = Field(default_factory=list)
    awaiting_confirmation: bool = False


class BookingSummary(BaseModel):
    """A stored booking in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    interview_date: date
    interview_time: time
    status: BookingStatus
    created_at: datetime


class BookingListResponse(BaseModel):
    """A page of bookings."""

    items: list[BookingSummary]
    total: int
    limit: int
    offset: int
