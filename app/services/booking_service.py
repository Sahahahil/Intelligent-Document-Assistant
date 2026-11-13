"""Interview booking: intent detection and field extraction.

The state machine (draft, confirmation, persistence) lands in T19.
"""

import logging
from collections.abc import Sequence
from datetime import date

from app.integrations.llm import ChatMessage, LLMClient
from app.schemas.booking import BookingExtraction, BookingFields

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 6

EXTRACTION_PROMPT = """Extract interview booking details from the conversation.
Rules:
1. is_booking_request is true only if the user wants to schedule/book an interview, call or meeting.
2. Extract ONLY values the user explicitly provided. Never guess or invent.
3. Resolve relative dates against today's date: {today}.
4. Dates are ISO YYYY-MM-DD. Times are 24h HH:MM. If a date or time is ambiguous, leave it null.
5. confirmed_by_user is true only if the user explicitly agreed to the full set of details
   (e.g. "yes", "confirm", "that's right").
6. Asking how to book is not booking - only an intent to schedule now counts."""


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


class BookingService:
    """Reads booking intent and details out of a message."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def extract(self, message: str, history: Sequence[ChatMessage]) -> BookingExtraction:
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
            extraction = await self._llm.complete_structured(
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
        extraction.missing_fields = missing_fields(extraction.fields)
        return extraction
