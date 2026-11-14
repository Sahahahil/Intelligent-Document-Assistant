"""Booking state machine against a live Redis and a real PostgreSQL.

Run with:  uv run pytest -m integration

The LLM is faked; everything else is real.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import date, time, timedelta
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.llm import ChatMessage
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingExtraction, BookingFields
from app.services.booking_service import (
    DRAFT_PREFIX,
    BookingExtractor,
    BookingService,
)

pytestmark = pytest.mark.integration

TOMORROW = date.today() + timedelta(days=1)


class ScriptedExtractor:
    """Stands in for the LLM-backed extractor."""

    def __init__(self) -> None:
        self.extractions: dict[str, BookingExtraction] = {}

    async def extract(self, message: str, history: Sequence[ChatMessage]) -> BookingExtraction:
        return self.extractions.get(message, BookingExtraction())


@pytest.fixture
async def extractor() -> ScriptedExtractor:
    return ScriptedExtractor()


@pytest.fixture
async def service(
    db_session: AsyncSession, redis_client: Redis, extractor: ScriptedExtractor, session_id: str
) -> AsyncIterator[BookingService]:
    booking_service = BookingService(
        extractor=cast(BookingExtractor, extractor),
        repo=BookingRepository(db_session),
        redis=redis_client,
    )
    yield booking_service
    await redis_client.delete(f"{DRAFT_PREFIX}{session_id}")


async def test_the_draft_lives_in_redis_with_the_session_ttl(
    service: BookingService, redis_client: Redis, session_id: str
) -> None:
    await service.save_draft(session_id, BookingFields(name="Sahil"))

    ttl = await redis_client.ttl(f"{DRAFT_PREFIX}{session_id}")

    assert 0 < ttl <= get_settings().session_ttl_seconds


async def test_no_row_is_written_before_the_confirmation(
    service: BookingService,
    db_session: AsyncSession,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extractor.extractions["schedule an interview"] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )

    turn = await service.handle_turn(
        session_id=session_id, message="schedule an interview", history=[]
    )

    assert turn.awaiting_confirmation is True
    assert turn.persisted is False
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 0


async def test_the_confirmation_writes_one_row(
    service: BookingService,
    db_session: AsyncSession,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extractor.extractions["schedule an interview"] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    await service.handle_turn(session_id=session_id, message="schedule an interview", history=[])

    turn = await service.handle_turn(session_id=session_id, message="yes", history=[])

    assert turn.persisted is True
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1
    row = (await db_session.execute(select(Booking))).scalar_one()
    assert row.name == "Sahil"
    assert row.email == "sahil@example.com"
    assert row.interview_date == TOMORROW
    assert row.interview_time == time(14, 0)
    assert row.session_id == session_id


async def test_the_draft_is_deleted_after_the_booking(
    service: BookingService,
    redis_client: Redis,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extractor.extractions["schedule an interview"] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    await service.handle_turn(session_id=session_id, message="schedule an interview", history=[])
    await service.handle_turn(session_id=session_id, message="yes", history=[])

    assert await redis_client.exists(f"{DRAFT_PREFIX}{session_id}") == 0


async def test_the_same_slot_is_not_booked_twice(
    service: BookingService,
    db_session: AsyncSession,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extraction = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    extractor.extractions["schedule an interview"] = extraction

    await service.handle_turn(session_id=session_id, message="schedule an interview", history=[])
    first = await service.handle_turn(session_id=session_id, message="yes", history=[])

    extractor.extractions["schedule an interview again"] = extraction
    second = await service.handle_turn(
        session_id=session_id, message="schedule an interview again", history=[]
    )

    assert first.persisted is True
    assert second.persisted is False
    assert second.booking is not None
    assert second.booking.id == first.booking.id  # type: ignore[union-attr]
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1


async def test_another_person_cannot_take_the_same_slot(
    service: BookingService,
    db_session: AsyncSession,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extractor.extractions["schedule an interview"] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    await service.handle_turn(session_id=session_id, message="schedule an interview", history=[])
    await service.handle_turn(session_id=session_id, message="yes", history=[])

    extractor.extractions["someone else"] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Someone Else",
            email="someone@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    turn = await service.handle_turn(session_id=session_id, message="someone else", history=[])

    assert turn.persisted is False
    assert turn.reply is not None
    assert "already taken" in turn.reply
    assert turn.missing_fields == ["date", "time"]
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1


async def test_a_cancelled_booking_frees_the_slot(
    service: BookingService,
    db_session: AsyncSession,
    extractor: ScriptedExtractor,
    session_id: str,
) -> None:
    extraction = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        ),
    )
    extractor.extractions["schedule an interview"] = extraction
    await service.handle_turn(session_id=session_id, message="schedule an interview", history=[])
    await service.handle_turn(session_id=session_id, message="yes", history=[])

    extractor.extractions["cancel my interview"] = BookingExtraction(cancels_booking=True)
    cancelled = await service.handle_turn(
        session_id=session_id, message="cancel my interview", history=[]
    )

    assert cancelled.persisted is True
    assert cancelled.booking is not None
    assert cancelled.booking.status == "cancelled"
    # The row was the booking - cancelling removed it.
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 0

    # The slot is free again - cancelling removed the row.
    extractor.extractions["schedule an interview again"] = extraction
    again = await service.handle_turn(
        session_id=session_id, message="schedule an interview again", history=[]
    )
    assert again.awaiting_confirmation is True
    booked = await service.handle_turn(session_id=session_id, message="yes", history=[])
    assert booked.persisted is True
    count = await db_session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1
