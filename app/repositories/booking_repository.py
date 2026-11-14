"""Persistence for interview bookings."""

from datetime import date, time

from sqlalchemy import func, select
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

    async def find_conflict(self, when: date, at: time) -> Booking | None:
        """Return the confirmed booking that occupies that slot, whoever it is.

        Mirrors the `uq_bookings_slot` partial unique index, which only
        covers confirmed bookings — the repository and the database agree on
        what a conflict is.
        """
        result = await self._session.execute(
            select(Booking).where(
                Booking.interview_date == when,
                Booking.interview_time == at,
                Booking.status == BookingStatus.CONFIRMED,
            )
        )
        return result.scalar_one_or_none()

    async def find_confirmed(self, session_id: str) -> Booking | None:
        """The confirmed booking this session made, if it still has one."""
        result = await self._session.execute(
            select(Booking).where(
                Booking.session_id == session_id,
                Booking.status == BookingStatus.CONFIRMED,
            )
        )
        return result.scalar_one_or_none()

    async def cancel(self, booking: Booking) -> Booking:
        """Give the slot back: a cancelled booking no longer occupies it."""
        booking.status = BookingStatus.CANCELLED
        await self._session.commit()
        await self._session.refresh(booking)
        return booking

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        email: str | None = None,
        interview_date: date | None = None,
        status: BookingStatus | None = None,
    ) -> tuple[list[Booking], int]:
        """A page of bookings, newest first.

        The email is matched exactly - it is the address the user gave.
        """
        rows_stmt = select(Booking)
        count_stmt = select(func.count()).select_from(Booking)
        filters = []
        if email is not None:
            filters.append(Booking.email == email)
        if interview_date is not None:
            filters.append(Booking.interview_date == interview_date)
        if status is not None:
            filters.append(Booking.status == status)
        if filters:
            rows_stmt = rows_stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total = (await self._session.execute(count_stmt)).scalar_one()
        rows = (
            (
                await self._session.execute(
                    rows_stmt.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total
