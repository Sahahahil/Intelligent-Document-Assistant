"""Persistence for interview bookings."""

from datetime import date, time
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
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

    async def get(self, booking_id: UUID) -> Booking | None:
        return await self._session.get(Booking, booking_id)

    async def list(
        self,
        *,
        session_id: str | None = None,
        email: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Booking], int]:
        rows_stmt = select(Booking)
        count_stmt = select(func.count()).select_from(Booking)
        if session_id is not None:
            rows_stmt = rows_stmt.where(Booking.session_id == session_id)
            count_stmt = count_stmt.where(Booking.session_id == session_id)
        if email is not None:
            rows_stmt = rows_stmt.where(Booking.email == email)
            count_stmt = count_stmt.where(Booking.email == email)

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

    async def update_status(self, booking_id: UUID, status: BookingStatus) -> bool:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Booking).where(Booking.id == booking_id).values(status=status)
            ),
        )
        await self._session.commit()
        return result.rowcount > 0
