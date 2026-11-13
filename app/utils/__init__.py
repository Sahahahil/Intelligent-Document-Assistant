"""File text extraction. Pick an extractor with `get_extractor`."""

from app.core.exceptions import UnsupportedFileTypeError
from app.utils.base import ExtractedText, TextExtractor
from app.utils.pdf_extractor import PdfExtractor
from app.utils.text_extractor import PlainTextExtractor

_text = PlainTextExtractor()
_pdf = PdfExtractor()

_EXTRACTORS: dict[str, TextExtractor] = {
    "txt": _text,
    "md": _text,
    "text": _text,
    "pdf": _pdf,
}

__all__ = ["ExtractedText", "PdfExtractor", "PlainTextExtractor", "TextExtractor", "get_extractor"]


def get_extractor(extension: str) -> TextExtractor:
    """Return the extractor for a file extension, or raise 415."""
    key = extension.lower().lstrip(".")
    try:
        return _EXTRACTORS[key]
    except KeyError:
        raise UnsupportedFileTypeError(f"Unsupported file type: .{key}") from None
