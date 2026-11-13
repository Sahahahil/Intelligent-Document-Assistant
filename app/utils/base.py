"""Shared types for text extraction."""

from dataclasses import dataclass
from typing import Protocol

from app.core.exceptions import ExtractionError


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """Plain text pulled out of an uploaded file."""

    text: str
    page_count: int | None
    char_count: int


class TextExtractor(Protocol):
    """Turns raw file bytes into plain text."""

    def extract(self, data: bytes, *, filename: str) -> ExtractedText: ...


def build_result(text: str, page_count: int | None, *, filename: str) -> ExtractedText:
    """Wrap extracted text, rejecting anything without usable content."""
    if not text.strip():
        raise ExtractionError(f"'{filename}' contains no extractable text")
    return ExtractedText(text=text, page_count=page_count, char_count=len(text))
