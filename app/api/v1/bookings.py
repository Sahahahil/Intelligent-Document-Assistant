"""Interview bookings: read them back."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_booking_repository
from app.models.booking import BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingListResponse, BookingSummary

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=BookingListResponse, summary="List bookings")
async def list_bookings(
    booking_repo: Annotated[BookingRepository, Depends(get_booking_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    email: Annotated[str | None, Query(description="Exact email address")] = None,
    interview_date: Annotated[date | None, Query(description="The interview date")] = None,
    booking_status: Annotated[BookingStatus | None, Query(alias="status")] = None,
) -> BookingListResponse:
    """A page of bookings, newest first."""
    rows, total = await booking_repo.list(
        limit=limit,
        offset=offset,
        email=email,
        interview_date=interview_date,
        status=booking_status,
    )
    return BookingListResponse(
        items=[BookingSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
