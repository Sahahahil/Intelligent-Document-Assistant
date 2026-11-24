"""Shared types for text extraction."""

from typing import Protocol

from app.core.exceptions import ExtractionError


class TextExtractor(Protocol):
    """Turns raw file bytes into plain text."""

    def extract(self, data: bytes, *, filename: str) -> str: ...


def require_text(text: str, *, filename: str) -> str:
    """Reject anything without usable content."""
    if not text.strip():
        raise ExtractionError(f"'{filename}' contains no extractable text")
    return text
