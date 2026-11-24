"""Interview booking: extraction (T18) and the booking state machine (T19).

The rule that matters: nothing is written to the database before the user
explicitly confirms.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.redis import redis_guard
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingExtraction, BookingFields, BookingModel

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 6

DRAFT_PREFIX = "booking_draft:"

# A small, explicit set - a fuzzy "is this a yes?" classifier is unsafe.
AFFIRMATIONS = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "sure",
        "confirm",
        "confirmed",
        "correct",
        "that is right",
        "that's right",
        "looks good",
        "sounds good",
        "go ahead",
        "do it",
        "book it",
    }
)
REJECTION_WORDS = ("cancel", "forget it", "never mind", "nevermind", "stop")

EXTRACTION_PROMPT = """Extract interview booking details from the conversation.
Rules:
1. is_booking_request is true only if the user wants to schedule/book an interview, call or meeting.
2. Extract ONLY values the user explicitly provided. Never guess or invent.
3. Resolve relative dates against today's date: {today}.
4. Dates are ISO YYYY-MM-DD. Times are 24h HH:MM. If a date or time is ambiguous, leave it null.
5. confirmed_by_user is true only if the user explicitly agreed to the full set of details
   (e.g. "yes", "confirm", "that's right").
6. Asking how to book is not booking - only an intent to schedule now counts.
7. cancels_booking is true only if the user asks to cancel or call off their interview
   booking. Asking about a cancellation policy is not cancelling."""


def missing_fields(fields: BookingFields) -> list[str]:
    """The details still absent, in the order they are asked for."""
    return [
        name
        for name, value in (
            ("name", fields.name),
            ("email", fields.email),
            ("date", fields.interview_date),
            ("time", fields.interview_time),
        )
        if value is None
    ]


def require_details(fields: BookingFields) -> tuple[str, str, date, time]:
    """The four details, or an error if any of them is missing.

    `missing_fields` decides whether to ask; this is the narrowing the
    write path needs.
    """
    name, email, when, at = (
        fields.name,
        fields.email,
        fields.interview_date,
        fields.interview_time,
    )
    if name is None or email is None or when is None or at is None:
        raise ValidationError(
            f"Cannot book an interview without: {', '.join(missing_fields(fields))}"
        )
    return name, email, when, at


@dataclass(frozen=True, slots=True)
class BookingTurn:
    """What one turn did to the booking."""

    is_booking: bool
    reply: str | None
    booking: BookingModel | None  # the booking block - `None` for a non-booking turn
    missing_fields: list[str]
    awaiting_confirmation: bool
    persisted: bool


async def extract_booking(
    llm: LLMClient, message: str, history: Sequence[ChatMessage]
) -> BookingExtraction:
    """What the message says about a booking - never raises."""
    messages = [
        ChatMessage(
            role="system",
            content=EXTRACTION_PROMPT.format(today=date.today().isoformat()),
        )
    ]
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append(ChatMessage(role="user", content=message))
    try:
        extraction = await llm.complete_structured(
            messages=messages, schema=BookingExtraction, temperature=0.0
        )
    except Exception:
        # A failed extraction is not a failed turn - the chat continues
        # without booking details.
        logger.warning("Booking extraction failed", exc_info=True)
        return BookingExtraction()
    if extraction.fields.interview_date is not None and (
        extraction.fields.interview_date < date.today()
    ):
        logger.warning(
            "Dropping an interview date in the past: %s", extraction.fields.interview_date
        )
        extraction.fields.interview_date = None
    return extraction


def merge_fields(draft: BookingFields | None, incoming: BookingFields) -> BookingFields:
    """The new value wins when the user gave one; otherwise keep the old."""
    base = draft or BookingFields()
    return BookingFields(
        name=incoming.name or base.name,
        email=incoming.email or base.email,
        interview_date=incoming.interview_date or base.interview_date,
        interview_time=incoming.interview_time or base.interview_time,
    )


def has_fields(fields: BookingFields) -> bool:
    return any(
        value is not None
        for value in (fields.name, fields.email, fields.interview_date, fields.interview_time)
    )


def clean_message(message: str) -> str:
    return re.sub(r"[^\w\s']", " ", message.lower()).strip()


def is_affirmation(message: str) -> bool:
    cleaned = clean_message(message)
    return cleaned in AFFIRMATIONS or cleaned.startswith("yes ")


def is_rejection(message: str) -> bool:
    cleaned = clean_message(message)
    if cleaned in {"no", "nope", "no thanks", "no thank you"}:
        return True
    return any(word in cleaned for word in REJECTION_WORDS)


def ask_for(missing: list[str]) -> str:
    listed = ", ".join(missing[:-1]) + " and " + missing[-1] if len(missing) > 1 else missing[0]
    return f"Sure - I need your {listed} to schedule the interview."


def summary(name: str, email: str, when: date, at: time) -> str:
    return (
        f"Here is what I have: Name: {name}, Email: {email}, "
        f"Date: {when.isoformat()}, Time: {at.strftime('%H:%M')}. "
        f"Please confirm to book."
    )


def confirmation_text(booking: Booking) -> str:
    return (
        f"Your interview request for {booking.interview_date.isoformat()} "
        f"at {booking.interview_time.strftime('%H:%M')} has been recorded."
    )


def pending_model(
    fields: BookingFields,
    *,
    missing: list[str] | None = None,
    awaiting_confirmation: bool = False,
) -> BookingModel:
    """The booking block for a turn that has not been written yet."""
    return BookingModel(
        name=fields.name,
        email=fields.email,
        interview_date=fields.interview_date,
        interview_time=fields.interview_time,
        status="pending",
        missing_fields=missing or [],
        awaiting_confirmation=awaiting_confirmation,
    )


def to_model(
    booking: Booking, *, status: Literal["confirmed", "cancelled"] = "confirmed"
) -> BookingModel:
    return BookingModel(
        id=booking.id,
        name=booking.name,
        email=booking.email,
        interview_date=booking.interview_date,
        interview_time=booking.interview_time,
        status=status,
        missing_fields=[],
        awaiting_confirmation=False,
    )


def draft_key(session_id: str) -> str:
    return f"{DRAFT_PREFIX}{session_id}"


class BookingService:
    """The booking state machine: draft, confirm, persist."""

    def __init__(
        self,
        *,
        repo: BookingRepository,
        redis: Redis,
    ) -> None:
        self._repo = repo
        self._redis = redis
        self._ttl = get_settings().session_ttl_seconds

    async def handle_turn(
        self, *, session_id: str, message: str, history: Sequence[ChatMessage]
    ) -> BookingTurn:
        """Run one turn of the booking conversation."""
        from app.integrations.llm import get_llm_client
        llm = get_llm_client()

        extraction = await extract_booking(llm, message, history)
        draft = await self.get_draft(session_id)

        if extraction.cancels_booking:
            return await self._cancel_booking(session_id, draft)

        if draft is not None and is_rejection(message):
            await self.clear_draft(session_id)
            return BookingTurn(
                is_booking=True,
                reply="No problem - I have cleared that request. "
                "Tell me when you would like to book.",
                booking=BookingModel(),
                missing_fields=[],
                awaiting_confirmation=False,
                persisted=False,
            )

        merged = merge_fields(draft, extraction.fields)
        if merged.interview_date is not None and merged.interview_date < date.today():
            # The draft outlived its date - ask for a new one.
            logger.warning("Dropping a stale interview date: %s", merged.interview_date)
            merged = merged.model_copy(update={"interview_date": None})

        missing = missing_fields(merged)
        if missing:
            if (
                not extraction.is_booking_request
                and draft is None
                and not has_fields(extraction.fields)
            ):
                return BookingTurn(
                    is_booking=False,
                    reply=None,
                    booking=None,
                    missing_fields=[],
                    awaiting_confirmation=False,
                    persisted=False,
                )
            await self.save_draft(session_id, merged)
            return BookingTurn(
                is_booking=True,
                reply=ask_for(missing),
                booking=pending_model(merged, missing=missing),
                missing_fields=missing,
                awaiting_confirmation=False,
                persisted=False,
            )

        # Everything is known - the slot has to be free before the user is
        # asked to confirm it.
        name, email, when, at = require_details(merged)
        conflict = await self._repo.find_conflict(when, at)
        if conflict is not None:
            return await self._slot_taken(session_id, merged, conflict)

        # The booking still needs an explicit yes. The model's own
        # `confirmed_by_user` flag only counts when the turn did not carry the
        # details: a small model sometimes reads "here are my details" as an
        # agreement, and that would write a row nobody confirmed.
        confirmed = is_affirmation(message) or (
            extraction.confirmed_by_user and merged == draft
        )
        if not confirmed:
            await self.save_draft(session_id, merged)
            return BookingTurn(
                is_booking=True,
                reply=summary(name, email, when, at),
                booking=pending_model(merged, awaiting_confirmation=True),
                missing_fields=[],
                awaiting_confirmation=True,
                persisted=False,
            )

        booking, created = await self._persist(session_id, name, email, when, at)
        if not created:
            # The slot was taken between the check and the insert.
            return await self._slot_taken(session_id, merged, booking)
        await self.clear_draft(session_id)
        return BookingTurn(
            is_booking=True,
            reply=confirmation_text(booking),
            booking=to_model(booking),
            missing_fields=[],
            awaiting_confirmation=False,
            persisted=True,
        )

    async def get_draft(self, session_id: str) -> BookingFields | None:
        """The details collected so far, if any."""
        async with redis_guard():
            raw = await self._redis.get(draft_key(session_id))
        if not raw:
            return None
        return BookingFields.model_validate_json(raw)

    async def save_draft(self, session_id: str, fields: BookingFields) -> None:
        """Keep the details collected so far."""
        async with redis_guard():
            await self._redis.set(
                draft_key(session_id), fields.model_dump_json(), ex=self._ttl
            )

    async def clear_draft(self, session_id: str) -> None:
        """Forget the details collected so far."""
        async with redis_guard():
            await self._redis.delete(draft_key(session_id))

    async def _persist(
        self, session_id: str, name: str, email: str, when: date, at: time
    ) -> tuple[Booking, bool]:
        """Write the booking - or report the slot that was taken first.

        The second element is False when the slot was gone: the caller has
        already checked, so this is the race the unique index catches.
        """
        booking = Booking(
            session_id=session_id,
            name=name,
            email=email,
            interview_date=when,
            interview_time=at,
        )
        try:
            return await self._repo.create(booking), True
        except IntegrityError:
            # The slot was taken between the check and the insert.
            conflict = await self._repo.find_conflict(when, at)
            if conflict is None:
                raise
            return conflict, False

    async def _slot_taken(
        self, session_id: str, fields: BookingFields, conflict: Booking
    ) -> BookingTurn:
        """The slot is gone: say so, and ask for another one."""
        if conflict.email == fields.email:
            # Their own booking - the interview is already set.
            await self.clear_draft(session_id)
            return BookingTurn(
                is_booking=True,
                reply=(
                    "You already have an interview booked for that time - "
                    "I have not booked it twice."
                ),
                booking=to_model(conflict),
                missing_fields=[],
                awaiting_confirmation=False,
                persisted=False,
            )
        trimmed = fields.model_copy(update={"interview_date": None, "interview_time": None})
        await self.save_draft(session_id, trimmed)
        return BookingTurn(
            is_booking=True,
            reply="That slot is already taken. Which other date and time would suit you?",
            booking=pending_model(trimmed, missing=["date", "time"]),
            missing_fields=["date", "time"],
            awaiting_confirmation=False,
            persisted=False,
        )

    async def _cancel_booking(self, session_id: str, draft: BookingFields | None) -> BookingTurn:
        """Cancel the booking of this session, if it has one."""
        booking = await self._repo.find_for_session(session_id)
        await self.clear_draft(session_id)
        if booking is None:
            reply = (
                "No problem - I have cleared that request. Tell me when you would like to book."
                if draft is not None
                else "There is no interview booking on file for this session to cancel."
            )
            return BookingTurn(
                is_booking=True,
                reply=reply,
                booking=BookingModel(),
                missing_fields=[],
                awaiting_confirmation=False,
                persisted=False,
            )
        await self._repo.delete(booking.id)
        return BookingTurn(
            is_booking=True,
            reply=(
                f"Your interview request for {booking.interview_date.isoformat()} "
                f"at {booking.interview_time.strftime('%H:%M')} has been cancelled."
            ),
            booking=to_model(booking, status="cancelled"),
            missing_fields=[],
            awaiting_confirmation=False,
            persisted=True,
        )
