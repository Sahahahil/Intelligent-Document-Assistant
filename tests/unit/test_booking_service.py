"""Booking extraction tests - the LLM is a fake.

The fake validates the payload against the schema it was given, the way
`LLMClient.complete_structured` does - a payload that does not fit raises,
and the extractor falls back to an empty extraction.
"""

import json
import logging
from collections.abc import Sequence
from datetime import date, time, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import UpstreamError, ValidationError
from app.integrations.llm import ChatMessage, LLMClient
from app.models.booking import Booking, BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingExtraction, BookingFields
from app.services.booking_service import (
    BookingExtractor,
    BookingService,
    missing_fields,
    require_details,
)
from tests.fakes import FakeLLM


def service_with(
    payload: dict[str, Any] | None = None, *, error: Exception | None = None
) -> tuple[BookingExtractor, FakeLLM]:
    """An extractor whose model answers with `payload` - or fails with `error`."""
    llm = FakeLLM(error) if error is not None else FakeLLM(json.dumps(payload or {}, default=str))
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
    assert missing_fields(result.fields) == ["name", "email", "date", "time"]


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

    assert missing_fields(result.fields) == ["email", "date", "time"]


async def test_the_missing_fields_are_computed_in_order() -> None:
    service, _ = service_with({"is_booking_request": True, "fields": {}})

    result = await service.extract("schedule an interview", [])

    assert missing_fields(result.fields) == ["name", "email", "date", "time"]


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
    assert "date" in missing_fields(result.fields)
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
        self.conflicts: dict[tuple[date, time], Booking] = {}
        # A slot taken between the check and the insert - invisible until
        # an insert has been attempted.
        self.raced: dict[tuple[date, time], Booking] = {}
        self.cancelled: list[Booking] = []
        self.error: Exception | None = None
        self.attempted = False

    async def find_conflict(self, when: date, at: time) -> Booking | None:
        found = self.conflicts.get((when, at))
        if found is None and self.attempted:
            found = self.raced.get((when, at))
        return found

    async def find_confirmed(self, session_id: str) -> Booking | None:
        for booking in [*self.created, *self.conflicts.values(), *self.raced.values()]:
            if booking.session_id == session_id and booking.status == BookingStatus.CONFIRMED:
                return booking
        return None

    async def create(self, booking: Booking) -> Booking:
        self.attempted = True
        if self.error is not None:
            raise self.error
        booking.id = uuid4()
        self.created.append(booking)
        return booking

    async def cancel(self, booking: Booking) -> Booking:
        booking.status = BookingStatus.CANCELLED
        self.cancelled.append(booking)
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


async def test_a_slot_taken_by_someone_else_is_not_booked(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    taken = Booking(
        id=uuid4(),
        session_id="other",
        name="Someone Else",
        email="someone@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
    )
    repo.conflicts[(TOMORROW, time(14, 0))] = taken
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )

    turn = await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    assert repo.created == []
    assert turn.persisted is False
    assert turn.missing_fields == ["date", "time"]
    assert turn.reply is not None
    assert "already taken" in turn.reply
    # The name and the email are kept - only the slot has to be replaced.
    draft = await booking_service.get_draft(SESSION)
    assert draft is not None
    assert draft.name == "Sahil"
    assert draft.email == "sahil@example.com"
    assert draft.interview_date is None
    assert draft.interview_time is None


async def test_the_same_person_does_not_book_a_slot_twice(
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
    )
    repo.conflicts[(TOMORROW, time(14, 0))] = existing
    script(
        extractor,
        "everything",
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
    )

    turn = await booking_service.handle_turn(session_id=SESSION, message="everything", history=[])

    assert repo.created == []
    assert turn.persisted is False
    assert turn.booking is not None
    assert turn.booking.id == existing.id
    assert turn.reply is not None
    assert "already have an interview booked" in turn.reply


async def test_a_slot_taken_between_the_check_and_the_insert_is_caught(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    taken = Booking(
        id=uuid4(),
        session_id="other",
        name="Someone Else",
        email="someone@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
    )
    repo.raced[(TOMORROW, time(14, 0))] = taken
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

    assert repo.created == []
    assert turn.persisted is False
    assert turn.reply is not None
    assert "already taken" in turn.reply


async def test_an_integrity_error_that_is_not_a_slot_conflict_is_raised(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
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

    with pytest.raises(IntegrityError):
        await booking_service.handle_turn(session_id=SESSION, message="yes", history=[])


async def test_a_cancel_turn_cancels_the_confirmed_booking(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    booked = Booking(
        id=uuid4(),
        session_id=SESSION,
        name="Sahil",
        email="sahil@example.com",
        interview_date=TOMORROW,
        interview_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
    )
    repo.created.append(booked)
    extractor.extractions["cancel my interview"] = BookingExtraction(cancels_booking=True)

    turn = await booking_service.handle_turn(
        session_id=SESSION, message="cancel my interview", history=[]
    )

    assert turn.is_booking is True
    assert turn.persisted is True
    assert repo.cancelled == [booked]
    assert booked.status == BookingStatus.CANCELLED
    assert turn.booking is not None
    assert turn.booking.status == "cancelled"
    assert turn.reply is not None
    assert "cancelled" in turn.reply


async def test_cancelling_without_a_booking_says_so(
    booking_service: BookingService, extractor: FakeExtractor, repo: FakeRepository
) -> None:
    extractor.extractions["cancel my interview"] = BookingExtraction(cancels_booking=True)

    turn = await booking_service.handle_turn(
        session_id=SESSION, message="cancel my interview", history=[]
    )

    assert turn.is_booking is True
    assert turn.persisted is False
    assert turn.reply is not None
    assert "no interview booking on file" in turn.reply
    assert repo.cancelled == []


async def test_a_cancel_turn_clears_an_unconfirmed_draft(
    booking_service: BookingService, extractor: FakeExtractor
) -> None:
    script(extractor, "first", name="Sahil")
    await booking_service.handle_turn(session_id=SESSION, message="first", history=[])
    extractor.extractions["cancel that"] = BookingExtraction(cancels_booking=True)

    turn = await booking_service.handle_turn(session_id=SESSION, message="cancel that", history=[])

    assert turn.is_booking is True
    assert await booking_service.get_draft(SESSION) is None
    assert turn.reply is not None
    assert "cleared" in turn.reply


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


# --- the details a booking needs ---


def test_require_details_returns_the_four_details() -> None:
    details = require_details(
        BookingFields(
            name="Sahil",
            email="sahil@example.com",
            interview_date=TOMORROW,
            interview_time=time(14, 0),
        )
    )

    assert details == ("Sahil", "sahil@example.com", TOMORROW, time(14, 0))


def test_require_details_rejects_an_incomplete_booking() -> None:
    with pytest.raises(ValidationError) as error:
        require_details(BookingFields(name="Sahil"))

    assert "date" in str(error.value)


async def test_a_cancellation_policy_is_not_a_cancellation() -> None:
    service, llm = service_with({"is_booking_request": False, "fields": {}})

    await service.extract("what is the cancellation policy?", [])

    assert "cancellation policy is not cancelling" in llm.sent[0].content
