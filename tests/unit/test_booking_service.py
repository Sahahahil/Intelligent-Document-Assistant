"""Booking extraction tests - the LLM is a fake.

The fake mimics the real client: it validates the payload against the schema
it was given and raises `UpstreamError` when the payload does not fit, exactly
like `LLMClient.complete_structured` does.
"""

import logging
from collections.abc import Sequence
from datetime import date, time, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.models.booking import Booking, BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingExtraction, BookingFields
from app.services.booking_service import (
    BookingExtractor,
    BookingService,
    missing_fields,
)


class FakeLLM:
    def __init__(
        self, payload: dict[str, Any] | None = None, *, error: Exception | None = None
    ) -> None:
        self.payload = payload if payload is not None else {}
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def complete_structured(
        self,
        *,
        messages: Sequence[ChatMessage],
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel:
        self.calls.append(
            {"messages": list(messages), "schema": schema, "temperature": temperature}
        )
        if self.error is not None:
            raise self.error
        try:
            return schema.model_validate(self.payload)
        except ValidationError as exc:
            raise UpstreamError(
                "LLM output did not match the expected schema",
                details={"errors": exc.errors()},
            ) from exc

    @property
    def sent(self) -> list[ChatMessage]:
        return cast(list[ChatMessage], self.calls[0]["messages"])


def service_with(
    payload: dict[str, Any] | None = None, *, error: Exception | None = None
) -> tuple[BookingExtractor, FakeLLM]:
    llm = FakeLLM(payload, error=error)
    return BookingExtractor(cast(LLMClient, llm)), llm


async def test_a_booking_request_is_detected() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {}})

    result = await service.extract("I want to schedule an interview", [])

    assert result.is_booking_request is True
    assert result.fields.name is None
    assert result.fields.email is None
    assert result.fields.interview_date is None
    assert result.fields.interview_time is None


async def test_the_name_and_email_are_extracted() -> None:
    service, _ = service_with(
        {
            "is_booking_request": True,
            "fields": {"name": "Sahil Duwal", "email": "sahil@example.com"},
        }
    )

    result = await service.extract("My name is Sahil Duwal, email sahil@example.com", [])

    assert result.fields.name == "Sahil Duwal"
    assert result.fields.email == "sahil@example.com"
    assert result.fields.interview_date is None


async def test_the_date_is_extracted() -> None:
    service, _ = service_with(
        {"is_booking_request": True, "fields": {"interview_date": "2026-11-20"}}
    )

    result = await service.extract("November 20, 2026", [])

    assert result.fields.interview_date == date(2026, 11, 20)


async def test_the_time_is_extracted() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {"interview_time": "14:00"}})

    result = await service.extract("2 PM", [])

    assert result.fields.interview_time == time(14, 0)


async def test_the_date_and_time_are_extracted_together() -> None:
    service, _ = service_with(
        {
            "is_booking_request": True,
            "fields": {"interview_date": "2026-11-20", "interview_time": "14:30"},
        }
    )

    result = await service.extract("2 pm on 20 Nov 2026", [])

    assert result.fields.interview_date == date(2026, 11, 20)
    assert result.fields.interview_time == time(14, 30)


async def test_an_ordinary_question_is_not_a_booking_request() -> None:
    service, _ = service_with({"is_booking_request": False, "fields": {}})

    result = await service.extract("What is machine learning?", [])

    assert result.is_booking_request is False


async def test_asking_how_to_book_is_not_booking() -> None:
    service, llm = service_with({"is_booking_request": False, "fields": {}})

    result = await service.extract("How do I book a demo?", [])

    assert result.is_booking_request is False
    assert "Asking how to book is not booking" in llm.sent[0].content


async def test_an_empty_payload_gives_the_default() -> None:
    service, _ = service_with({})

    result = await service.extract("hello", [])

    assert result.is_booking_request is False
    assert result.fields.name is None
    assert result.missing_fields == ["name", "email", "date", "time"]


async def test_invalid_json_gives_the_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _ = service_with(error=UpstreamError("LLM returned invalid JSON"))

    with caplog.at_level(logging.WARNING):
        result = await service.extract("hello", [])

    assert result.is_booking_request is False
    assert "Booking extraction failed" in caplog.text


async def test_a_wrongly_typed_field_gives_the_default() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {"email": 123}})

    result = await service.extract("hello", [])

    assert result.is_booking_request is False
    assert result.fields.email is None


async def test_the_missing_fields_name_what_is_absent() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {"name": "Sahil Duwal"}})

    result = await service.extract("my name is Sahil Duwal", [])

    assert result.missing_fields == ["email", "date", "time"]


async def test_the_missing_fields_are_computed_in_order() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {}})

    result = await service.extract("schedule an interview", [])

    assert result.missing_fields == ["name", "email", "date", "time"]


async def test_the_history_reaches_the_prompt() -> None:
    service, llm = service_with({"is_booking_request": True, "fields": {}})

    await service.extract(
        "November 20",
        [
            ChatMessage(role="user", content="what date?"),
            ChatMessage(role="assistant", content="which one?"),
        ],
    )

    assert [message.content for message in llm.sent[1:3]] == [
        "what date?",
        "which one?",
    ]


async def test_todays_date_is_in_the_prompt() -> None:
    service, llm = service_with({"is_booking_request": True, "fields": {}})

    await service.extract("tomorrow", [])

    assert date.today().isoformat() in llm.sent[0].content


async def test_the_extraction_is_deterministic() -> None:
    service, llm = service_with({"is_booking_request": True, "fields": {}})

    await service.extract("schedule an interview", [])

    assert llm.calls[0]["temperature"] == 0.0


async def test_the_booking_schema_is_the_one_requested() -> None:
    service, llm = service_with({"is_booking_request": True, "fields": {}})

    await service.extract("schedule an interview", [])

    assert llm.calls[0]["schema"] is BookingExtraction


async def test_a_date_in_the_past_is_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _ = service_with(
        {"is_booking_request": True, "fields": {"interview_date": "2020-01-01"}}
    )

    with caplog.at_level(logging.WARNING):
        result = await service.extract("January 1, 2020", [])

    assert result.fields.interview_date is None
    assert "date" in result.missing_fields
    assert "past" in caplog.text


async def test_todays_date_is_kept() -> None:
    service, _ = service_with(
        {"is_booking_request": True, "fields": {"interview_date": date.today().isoformat()}}
    )

    result = await service.extract("today", [])

    assert result.fields.interview_date == date.today()


def test_the_missing_fields_helper_skips_what_is_present() -> None:
    fields = BookingFields(name="Sahil Duwal", email="sahil@example.com")

    assert missing_fields(fields) == ["date", "time"]


# --- the state machine (T19) ---

SESSION = "session-1"
TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)


class FakeRedis:
    """Just enough Redis for the draft."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.data[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.data.pop(key, None) is not None else 0


class FakeRepository:
    def __init__(self) -> None:
        self.created: list[Booking] = []
        self.conflicts: dict[tuple[str, date, time], Booking] = {}
        self.error: Exception | None = None

    async def find_conflict(self, email: str, when: date, at: time) -> Booking | None:
        return self.conflicts.get((email, when, at))

    async def create(self, booking: Booking) -> Booking:
        if self.error is not None:
            raise self.error
        booking.id = uuid4()
        self.created.append(booking)
        return booking


class FakeExtractor:
    """Returns the extraction scripted for each message."""

    def __init__(self) -> None:
        self.extractions: dict[str, BookingExtraction] = {}
        self.calls: list[str] = []

    async def extract(self, message: str, history: Sequence[ChatMessage]) -> BookingExtraction:
        self.calls.append(message)
        return self.extractions.get(message, BookingExtraction())


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def booking_service(
    extractor: FakeExtractor, repo: FakeRepository, redis: FakeRedis
) -> BookingService:
    return BookingService(
        extractor=cast(BookingExtractor, extractor),
        repo=cast(BookingRepository, repo),
        redis=cast(Redis, redis),
    )


def script(extractor: FakeExtractor, message: str, **fields: str | date | time | None) -> None:
    """The extraction the model returns for `message`."""
    extractor.extractions[message] = BookingExtraction(
        is_booking_request=True,
        fields=BookingFields(**fields),
    )


async def test_the_first_turn_asks_for_everything(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(extractor, "schedule an interview")

    turn = await booking_service.handle_turn(
        session_id=SESSION, message="schedule an interview", history=[]
    )

    assert turn.is_booking is True
    assert turn.missing_fields == ["name", "email", "date", "time"]
    assert turn.reply is not None
    assert "name" in turn.reply
    assert repo.created == []


async def test_the_second_turn_merges_the_draft(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(extractor, "schedule an interview")
    script(
        extractor,
        "my name is Sahil, email sahil@example.com",
        name="Sahil",
        email="sahil@example.com",
    )

    await booking_service.handle_turn(
        session_id=SESSION, message="schedule an interview", history=[]
    )
    turn = await booking_service.handle_turn(
        session_id=SESSION,
        message="my name is Sahil, email sahil@example.com",
        history=[],
    )

    assert turn.missing_fields == ["date", "time"]
    draft = await booking_service.get_draft(SESSION)
    assert draft is not None
    assert draft.name == "Sahil"
    assert draft.email == "sahil@example.com"
    assert repo.created == []


async def test_a_complete_draft_asks_for_confirmation(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )

    turn = await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    assert turn.missing_fields == []
    assert turn.awaiting_confirmation is True
    assert turn.persisted is False
    assert turn.reply is not None
    assert "Sahil" in turn.reply
    assert "sahil@example.com" in turn.reply
    assert "confirm" in turn.reply.lower()
    assert repo.created == []


async def test_the_confirmation_writes_exactly_one_row(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    turn = await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert turn.persisted is True
    assert turn.awaiting_confirmation is False
    assert len(repo.created) == 1
    booking = repo.created[0]
    assert booking.name == "Sahil"
    assert booking.email == "sahil@example.com"
    assert booking.interview_date == TOMORROW
    assert booking.interview_time == time(14, 0)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.session_id == SESSION
    assert turn.booking is not None
    assert turn.booking.status == "confirmed"


async def test_the_draft_is_cleared_after_the_booking(
    booking_service: BookingService, extractor: FakeExtractor
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert await booking_service.get_draft(SESSION) is None


async def test_a_normal_question_is_not_a_booking_turn(
    booking_service: BookingService, repo: FakeRepository
) -> None:
    turn = await booking_service.handle_turn(
        session_id=SESSION, message="what is machine learning?", history=[]
    )

    assert turn.is_booking is False
    assert turn.reply is None
    assert turn.booking is None
    assert repo.created == []


async def test_maybe_is_not_a_confirmation(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    turn = await booking_service.handle_turn(session_id=SESSION, message="maybe", history=[])

    assert turn.persisted is False
    assert turn.awaiting_confirmation is True
    assert repo.created == []


async def test_a_new_name_overwrites_the_old_one(
    booking_service: BookingService, extractor: FakeExtractor
) -> None:
    script(extractor, "first", name="Sahil")
    await booking_service.handle_turn(session_id=SESSION, message="first", history=[])
    script(extractor, "second", name="Sahil Duwal")
    await booking_service.handle_turn(session_id=SESSION, message="second", history=[])

    draft = await booking_service.get_draft(SESSION)

    assert draft is not None
    assert draft.name == "Sahil Duwal"


async def test_a_duplicate_booking_is_not_written_twice(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    existing = Booking(
        id=uuid4(),
        session_id="other",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        raw_payload={},
    )
    repo.conflicts[("sahil@example.com", TOMORROW, time(14, 0))] = existing
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    turn = await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert repo.created == []
    assert turn.booking is not None
    assert turn.booking.id == existing.id
    assert turn.persisted is False


async def test_an_integrity_error_returns_the_existing_booking(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    existing = Booking(
        id=uuid4(),
        session_id="other",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        raw_payload={},
    )
    repo.conflicts[("sahil@example.com", TOMORROW, time(14, 0))] = existing
    repo.error = IntegrityError("insert", {}, Exception("duplicate key"))
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    turn = await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert turn.booking is not None
    assert turn.booking.id == existing.id
    assert turn.persisted is False


async def test_a_stale_date_is_asked_for_again(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    # The date goes by between the two turns.
    script(
        extractor,
        "yes",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TODAY - timedelta(days=1),
        interview_time=time(14, 0),
    )
    turn = await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert turn.persisted is False
    assert turn.missing_fields == ["date"]
    assert repo.created == []


async def test_the_confirmation_reply_says_a_request_was_recorded(
    booking_service: BookingService, extractor: FakeExtractor
) -> None:
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )
    await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    turn = await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])

    assert turn.reply is not None
    assert "request" in turn.reply
    assert "recorded" in turn.reply
    assert "scheduled" not in turn.reply


async def test_a_rejection_clears_the_draft(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    script(extractor, "first", name="Sahil")
    await booking_service.handle_turn(session_id=SESSION, message="first", history=[])

    turn = await booking_service.handle_turn(
        session_id=SESSION, message="no, cancel that", history=[]
    )

    assert turn.is_booking is True
    assert await booking_service.get_draft(SESSION) is None
    assert repo.created == []


async def test_an_expired_draft_asks_for_the_details_again(
    booking_service: BookingService, extractor: FakeExtractor, redis: FakeRedis
) -> None:
    script(extractor, "first", name="Sahil")
    await booking_service.handle_turn(session_id=SESSION, message="first", history=[])

    redis.data.clear()  # the session expired
    script(extractor, "second")

    turn = await booking_service.handle_turn(session_id=SESSION, message="second", history=[])

    assert turn.missing_fields == ["name", "email", "date", "time"]
