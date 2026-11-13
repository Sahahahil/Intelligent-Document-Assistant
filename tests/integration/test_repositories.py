"""Repository tests against a real PostgreSQL database.

Run with:  uv run pytest -m integration
"""

from collections.abc import AsyncIterator
from datetime import date, time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.models.booking import Booking, BookingStatus
from app.models.document import ChunkingStrategy, Document, DocumentStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.document_repository import DocumentRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db_session:
        await db_session.execute(text("DELETE FROM documents"))
        await db_session.execute(text("DELETE FROM bookings"))
        await db_session.commit()
        yield db_session
    # Each test runs in its own event loop, so pooled connections from the
    # previous loop must not be reused.
    await engine.dispose()


def make_document(**overrides: object) -> Document:
    values: dict[str, object] = {
        "filename": "doc.pdf",
        "content_type": "application/pdf",
        "file_size": 1234,
        "file_hash": uuid4().hex,
        "file_extension": "pdf",
        "chunking_strategy": ChunkingStrategy.RECURSIVE,
        "chunk_size": 200,
        "chunk_overlap": 40,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "status": DocumentStatus.PROCESSING,
    }
    values.update(overrides)
    return Document(**values)


async def test_document_crud(session: AsyncSession) -> None:
    repo = DocumentRepository(session)
    document = await repo.create(make_document())

    assert (await repo.get(document.id)) is not None
    assert (await repo.get_by_hash(document.file_hash)) is not None
    assert (await repo.get_by_hash("nope")) is None

    updated = await repo.update_status(document.id, DocumentStatus.COMPLETED, total_chunks=7)
    assert updated is True
    stored = await repo.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.COMPLETED
    assert stored.total_chunks == 7

    assert await repo.delete(document.id) is True
    assert await repo.delete(document.id) is False
    assert await repo.get(document.id) is None


async def test_document_list_paginates_and_filters(session: AsyncSession) -> None:
    repo = DocumentRepository(session)
    for _ in range(3):
        await repo.create(make_document())
    await repo.create(make_document(status=DocumentStatus.FAILED))

    rows, total = await repo.list(limit=2, offset=0)
    assert total == 4
    assert len(rows) == 2

    failed, failed_total = await repo.list(status=DocumentStatus.FAILED)
    assert failed_total == 1
    assert failed[0].status == DocumentStatus.FAILED


async def test_duplicate_file_hash_is_rejected(session: AsyncSession) -> None:
    repo = DocumentRepository(session)
    file_hash = uuid4().hex
    await repo.create(make_document(file_hash=file_hash))

    with pytest.raises(IntegrityError):
        await repo.create(make_document(file_hash=file_hash))
    await session.rollback()


async def test_booking_slot_conflict(session: AsyncSession) -> None:
    repo = BookingRepository(session)
    email = f"{uuid4().hex}@example.com"
    booking = Booking(
        session_id="s1",
        name="Sahil",
        email=email,
        interview_date=date(2026, 11, 20),
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        raw_payload={},
    )
    await repo.create(booking)

    found = await repo.find_conflict(email, date(2026, 11, 20), time(14, 0))
    assert found is not None
    assert found.id == booking.id

    assert await repo.find_conflict(email, date(2026, 11, 21), time(14, 0)) is None

    rows, total = await repo.list(session_id="s1")
    assert total == 1
    assert rows[0].email == email


async def test_only_confirmed_bookings_occupy_a_slot(session: AsyncSession) -> None:
    """A pending or cancelled booking must not block the same slot."""
    repo = BookingRepository(session)
    email = f"{uuid4().hex}@example.com"
    when, at = date(2026, 11, 20), time(14, 0)

    await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=when,
            interview_time=at,
            status=BookingStatus.PENDING,
            raw_payload={},
        )
    )
    assert await repo.find_conflict(email, when, at) is None

    # The database agrees: a pending row does not block a confirmed one.
    await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=when,
            interview_time=at,
            status=BookingStatus.CONFIRMED,
            raw_payload={},
        )
    )
    assert await repo.find_conflict(email, when, at) is not None


async def test_two_confirmed_bookings_in_the_same_slot_are_rejected(
    session: AsyncSession,
) -> None:
    repo = BookingRepository(session)
    email = f"{uuid4().hex}@example.com"
    when, at = date(2026, 11, 20), time(14, 0)

    def make() -> Booking:
        return Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=when,
            interview_time=at,
            status=BookingStatus.CONFIRMED,
            raw_payload={},
        )

    await repo.create(make())
    with pytest.raises(IntegrityError):
        await repo.create(make())
    await session.rollback()
