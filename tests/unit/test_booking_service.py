"""Booking extraction tests - the LLM is a fake.

The fake mimics the real client: it validates the payload against the schema
it was given and raises `UpstreamError` when the payload does not fit, exactly
like `LLMClient.complete_structured` does.
"""

import logging
from collections.abc import Sequence
from datetime import date, time
from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError

from app.core.exceptions import UpstreamError
from app.integrations.llm import ChatMessage, LLMClient
from app.schemas.booking import BookingExtraction, BookingFields
from app.services.booking_service import BookingService, missing_fields


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
) -> tuple[BookingService, FakeLLM]:
    llm = FakeLLM(payload, error=error)
    return BookingService(cast(LLMClient, llm)), llm


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
