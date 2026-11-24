"""Repository tests against a real PostgreSQL database.

Run with:  uv run pytest -m integration
"""

from datetime import date, time
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.document import ChunkingStrategy, Document, DocumentStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.document_repository import DocumentRepository

pytestmark = pytest.mark.integration


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


async def test_document_crud(db_session: AsyncSession) -> None:
    repo = DocumentRepository(db_session)
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


async def test_document_list_paginates_and_filters(db_session: AsyncSession) -> None:
    repo = DocumentRepository(db_session)
    for _ in range(3):
        await repo.create(make_document())
    await repo.create(make_document(status=DocumentStatus.FAILED))

    rows, total = await repo.list(limit=2, offset=0)
    assert total == 4
    assert len(rows) == 2

    failed, failed_total = await repo.list(status=DocumentStatus.FAILED)
    assert failed_total == 1
    assert failed[0].status == DocumentStatus.FAILED


async def test_duplicate_file_hash_is_rejected(db_session: AsyncSession) -> None:
    repo = DocumentRepository(db_session)
    file_hash = uuid4().hex
    await repo.create(make_document(file_hash=file_hash))

    with pytest.raises(IntegrityError):
        await repo.create(make_document(file_hash=file_hash))
    await db_session.rollback()


async def test_booking_slot_conflict(db_session: AsyncSession) -> None:
    repo = BookingRepository(db_session)
    email = f"{uuid4().hex}@example.com"
    booking = Booking(
        session_id="s1",
        name="Sahil",
        email=email,
        interview_date=date(2026, 11, 20),
        interview_time=time(14, 0),
    )
    await repo.create(booking)

    found = await repo.find_conflict(date(2026, 11, 20), time(14, 0))
    assert found is not None
    assert found.id == booking.id

    assert await repo.find_conflict(date(2026, 11, 21), time(14, 0)) is None


async def test_two_bookings_in_the_same_slot_are_rejected(
    db_session: AsyncSession,
) -> None:
    """The slot is taken by whoever booked it - not by one person only."""
    repo = BookingRepository(db_session)
    when, at = date(2026, 11, 20), time(14, 0)

    def make(email: str) -> Booking:
        return Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=when,
            interview_time=at,
        )

    await repo.create(make(f"{uuid4().hex}@example.com"))
    with pytest.raises(IntegrityError):
        await repo.create(make(f"{uuid4().hex}@example.com"))
    await db_session.rollback()


async def test_a_booking_can_be_deleted_and_the_slot_freed(
    db_session: AsyncSession,
) -> None:
    """The row is the booking - removing it frees the slot."""
    repo = BookingRepository(db_session)
    when, at = date(2026, 11, 20), time(14, 0)
    booking = await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=f"{uuid4().hex}@example.com",
            interview_date=when,
            interview_time=at,
        )
    )

    await repo.delete(booking.id)

    assert await repo.find_conflict(when, at) is None
    assert await repo.find_for_session("s1") is None


async def test_the_booking_of_a_session_is_found(db_session: AsyncSession) -> None:
    repo = BookingRepository(db_session)
    booking = await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=f"{uuid4().hex}@example.com",
            interview_date=date(2026, 11, 20),
            interview_time=time(14, 0),
        )
    )

    found = await repo.find_for_session("s1")

    assert found is not None
    assert found.id == booking.id
    assert await repo.find_for_session("other") is None


async def test_bookings_are_listed_and_filtered(db_session: AsyncSession) -> None:
    repo = BookingRepository(db_session)
    await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email="sahil@example.com",
            interview_date=date(2026, 11, 20),
            interview_time=time(14, 0),
        )
    )
    await repo.create(
        Booking(
            session_id="s2",
            name="Someone Else",
            email="someone@example.com",
            interview_date=date(2026, 11, 21),
            interview_time=time(10, 0),
        )
    )

    rows, total = await repo.list()
    assert total == 2
    assert len(rows) == 2

    rows, total = await repo.list(email="sahil@example.com")
    assert total == 1
    assert rows[0].email == "sahil@example.com"

    rows, total = await repo.list(interview_date=date(2026, 11, 21))
    assert total == 1
    assert rows[0].email == "someone@example.com"

    rows, total = await repo.list(limit=1)
    assert total == 2
    assert len(rows) == 1
