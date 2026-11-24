"""Interview bookings: read them back, and write one by hand."""

from datetime import date
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_booking_repository
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import (
    BookingCreate,
    BookingListResponse,
    BookingResponse,
    BookingSummary,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=BookingListResponse, summary="List bookings")
async def list_bookings(
    booking_repo: Annotated[BookingRepository, Depends(get_booking_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    email: Annotated[str | None, Query(description="Exact email address")] = None,
    interview_date: Annotated[date | None, Query(description="The interview date")] = None,
) -> BookingListResponse:
    """A page of bookings, newest first."""
    rows, total = await booking_repo.list(
        limit=limit,
        offset=offset,
        email=email,
        interview_date=interview_date,
    )
    return BookingListResponse(
        items=[BookingSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{booking_id}", response_model=BookingResponse, summary="Get one booking")
async def get_booking(
    booking_id: UUID,
    booking_repo: Annotated[BookingRepository, Depends(get_booking_repository)],
) -> BookingResponse:
    """One booking, or 404."""
    booking = await booking_repo.get(booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    return BookingResponse.model_validate(booking)


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book an interview",
)
async def create_booking(
    payload: BookingCreate,
    booking_repo: Annotated[BookingRepository, Depends(get_booking_repository)],
) -> BookingResponse:
    """Book a slot directly.

    The chat flow books through the state machine; this is the same write
    for a slot someone picked by hand.
    """
    conflict = await booking_repo.find_conflict(
        payload.interview_date, payload.interview_time
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slot is already taken",
        )
    booking = Booking(
        session_id=f"manual-{uuid4().hex[:8]}",
        name=payload.name,
        email=payload.email,
        interview_date=payload.interview_date,
        interview_time=payload.interview_time,
    )
    return BookingResponse.model_validate(await booking_repo.create(booking))


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Cancel a booking")
async def delete_booking(
    booking_id: UUID,
    booking_repo: Annotated[BookingRepository, Depends(get_booking_repository)],
) -> None:
    """Cancel a booking - the row was the booking, so the slot is free again."""
    await booking_repo.delete(booking_id)
