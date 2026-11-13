"""Booking state machine against a live Redis and a real PostgreSQL.

Run with:  uv run pytest -m integration

The LLM is faked; everything else is real.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import date, time, timedelta
from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, engine
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

SESSION_ID = f"test-{uuid4()}"
TOMORROW = date.today() + timedelta(days=1)


class ScriptedExtractor:
    """Stands in for the LLM-backed extractor."""

    def __init__(self) -> None:
        self.extractions: dict[str, BookingExtraction] = {}

    async def extract(self, message: str, history: Sequence[ChatMessage]) -> BookingExtraction:
        return self.extractions.get(message, BookingExtraction())


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, encoding="utf-8", decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db_session:
        await db_session.execute(text("DELETE FROM bookings"))
        await db_session.commit()
        yield db_session
    await engine.dispose()


@pytest.fixture
async def extractor() -> ScriptedExtractor:
    return ScriptedExtractor()


@pytest.fixture
async def service(
    session: AsyncSession, redis_client: Redis, extractor: ScriptedExtractor
) -> AsyncIterator[BookingService]:
    booking_service = BookingService(
        extractor=cast(BookingExtractor, extractor),
        repo=BookingRepository(session),
        redis=redis_client,
    )
    yield booking_service
    await redis_client.delete(f"{DRAFT_PREFIX}{SESSION_ID}")


async def test_the_draft_lives_in_redis_with_the_session_ttl(
    service: BookingService, redis_client: Redis
) -> None:
    await service.save_draft(SESSION_ID, BookingFields(name="Sahil"))

    ttl = await redis_client.ttl(f"{DRAFT_PREFIX}{SESSION_ID}")

    assert 0 < ttl <= get_settings().session_ttl_seconds


async def test_no_row_is_written_before_the_confirmation(
    service: BookingService, session: AsyncSession, extractor: ScriptedExtractor
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
        session_id=SESSION_ID, message="schedule an interview", history=[]
    )

    assert turn.awaiting_confirmation is True
    assert turn.persisted is False
    count = await session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 0


async def test_the_confirmation_writes_one_row(
    service: BookingService, session: AsyncSession, extractor: ScriptedExtractor
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
    await service.handle_turn(session_id=SESSION_ID, message="schedule an interview", history=[])

    turn = await service.handle_turn(session_id=SESSION_ID, message="yes", history=[])

    assert turn.persisted is True
    count = await session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1
    row = (await session.execute(select(Booking))).scalar_one()
    assert row.name == "Sahil"
    assert row.email == "sahil@example.com"
    assert row.interview_date == TOMORROW
    assert row.interview_time == time(14, 0)
    assert row.session_id == SESSION_ID
    assert row.status.value == "confirmed"


async def test_the_draft_is_deleted_after_the_booking(
    service: BookingService, redis_client: Redis, extractor: ScriptedExtractor
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
    await service.handle_turn(session_id=SESSION_ID, message="schedule an interview", history=[])
    await service.handle_turn(session_id=SESSION_ID, message="yes", history=[])

    assert await redis_client.exists(f"{DRAFT_PREFIX}{SESSION_ID}") == 0


async def test_the_same_slot_is_not_booked_twice(
    service: BookingService, session: AsyncSession, extractor: ScriptedExtractor
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

    await service.handle_turn(session_id=SESSION_ID, message="schedule an interview", history=[])
    first = await service.handle_turn(session_id=SESSION_ID, message="yes", history=[])

    extractor.extractions["schedule an interview again"] = extraction
    await service.handle_turn(
        session_id=SESSION_ID, message="schedule an interview again", history=[]
    )
    second = await service.handle_turn(session_id=SESSION_ID, message="yes", history=[])

    assert first.persisted is True
    assert second.persisted is False
    assert second.booking is not None
    assert second.booking.id == first.booking.id  # type: ignore[union-attr]
    count = await session.execute(select(func.count()).select_from(Booking))
    assert count.scalar_one() == 1
