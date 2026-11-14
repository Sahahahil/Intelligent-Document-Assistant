"""The bookings endpoint against a real PostgreSQL.

The rows are written by the repository and read back through the HTTP
layer, so the whole path is exercised - the endpoint, the session and the
query.

Run with:  uv run pytest -m integration
"""

from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository

pytestmark = pytest.mark.integration

TOMORROW = date.today() + timedelta(days=1)


async def test_the_persisted_booking_is_read_back(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    repo = BookingRepository(db_session)
    email = f"{uuid4().hex}@example.com"
    booking = await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        )
    )

    response = await client.get("/api/v1/bookings", params={"email": email})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(booking.id)
    assert item["name"] == "Sahil"
    assert item["email"] == email
    assert item["interview_date"] == TOMORROW.isoformat()
    assert item["interview_time"] == "14:00:00"


async def test_a_deleted_booking_is_not_listed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cancelling removes the row, so it disappears from the list."""
    repo = BookingRepository(db_session)
    email = f"{uuid4().hex}@example.com"
    booking = await repo.create(
        Booking(
            session_id="s1",
            name="Sahil",
            email=email,
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        )
    )
    await repo.delete(booking.id)

    response = await client.get("/api/v1/bookings", params={"email": email})

    assert response.status_code == 200
    assert response.json()["total"] == 0
