"""Persistence for interview bookings."""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, booking: Booking) -> Booking:
        self._session.add(booking)
        await self._session.commit()
        await self._session.refresh(booking)
        return booking

    async def find_conflict(self, email: str, when: date, at: time) -> Booking | None:
        """Return an existing confirmed booking for that person in that slot.

        Mirrors the `uq_bookings_slot` partial unique index, which only
        covers confirmed bookings — the repository and the database agree on
        what a conflict is.
        """
        result = await self._session.execute(
            select(Booking).where(
                Booking.email == email,
                Booking.interview_date == when,
                Booking.interview_time == at,
                Booking.status == BookingStatus.CONFIRMED,
            )
        )
        return result.scalar_one_or_none()
