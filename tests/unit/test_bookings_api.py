"""HTTP tests for the bookings API.

The repository is replaced with a fake through FastAPI's dependency override
— this exercises the HTTP layer only.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.api.deps import get_booking_repository
from app.main import app
from app.models.booking import Booking


def make_booking(**overrides: object) -> Booking:
    values: dict[str, object] = {
        "id": uuid4(),
        "session_id": "s1",
        "name": "Sahil Duwal",
        "email": "sahil@example.com",
        "interview_date": date(2026, 11, 20),
        "interview_time": time(14, 0),
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Booking(**values)


class FakeBookingRepository:
    def __init__(self) -> None:
        self.bookings: list[Booking] = []
        self.calls: list[dict[str, object]] = []

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        email: str | None = None,
        interview_date: date | None = None,
    ) -> tuple[list[Booking], int]:
        self.calls.append(
            {
                "limit": limit,
                "offset": offset,
                "email": email,
                "interview_date": interview_date,
            }
        )
        rows = [
            booking
            for booking in self.bookings
            if (email is None or booking.email == email)
            and (interview_date is None or booking.interview_date == interview_date)
        ]
        return rows[offset : offset + limit], len(rows)


@pytest.fixture
def repo() -> FakeBookingRepository:
    return FakeBookingRepository()


@pytest.fixture(autouse=True)
def _overrides(repo: FakeBookingRepository) -> Iterator[None]:
    app.dependency_overrides[get_booking_repository] = lambda: repo
    yield
    app.dependency_overrides.clear()


async def test_the_bookings_are_listed(client: AsyncClient, repo: FakeBookingRepository) -> None:
    repo.bookings = [make_booking()]

    response = await client.get("/api/v1/bookings")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0]["email"] == "sahil@example.com"
    assert body["items"][0]["interview_date"] == "2026-11-20"
    assert body["items"][0]["interview_time"] == "14:00:00"


async def test_the_list_is_paginated(client: AsyncClient, repo: FakeBookingRepository) -> None:
    repo.bookings = [make_booking() for _ in range(5)]

    response = await client.get("/api/v1/bookings", params={"limit": 2, "offset": 1})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert len(body["items"]) == 2


async def test_the_limit_is_bounded(client: AsyncClient) -> None:
    response = await client.get("/api/v1/bookings", params={"limit": 1000})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_list_can_be_filtered_by_email(
    client: AsyncClient, repo: FakeBookingRepository
) -> None:
    repo.bookings = [
        make_booking(email="sahil@example.com"),
        make_booking(email="someone@example.com"),
    ]

    response = await client.get("/api/v1/bookings", params={"email": "sahil@example.com"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "sahil@example.com"


async def test_the_list_can_be_filtered_by_date(
    client: AsyncClient, repo: FakeBookingRepository
) -> None:
    repo.bookings = [
        make_booking(interview_date=date(2026, 11, 20)),
        make_booking(interview_date=date(2026, 11, 21)),
    ]

    response = await client.get("/api/v1/bookings", params={"interview_date": "2026-11-21"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["interview_date"] == "2026-11-21"


async def test_an_unknown_date_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/bookings", params={"interview_date": "20-11-2026"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_filters_are_passed_to_the_repository(
    client: AsyncClient, repo: FakeBookingRepository
) -> None:
    await client.get(
        "/api/v1/bookings",
        params={
            "email": "sahil@example.com",
            "interview_date": "2026-11-20",
        },
    )

    assert repo.calls[0]["email"] == "sahil@example.com"
    assert repo.calls[0]["interview_date"] == date(2026, 11, 20)


async def test_the_responses_leak_no_orm_fields(
    client: AsyncClient, repo: FakeBookingRepository
) -> None:
    repo.bookings = [make_booking()]

    response = await client.get("/api/v1/bookings")

    assert set(response.json()["items"][0]) == {
        "id",
        "name",
        "email",
        "interview_date",
        "interview_time",
        "created_at",
    }


async def test_the_route_is_documented(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert "/api/v1/bookings" in response.json()["paths"]
