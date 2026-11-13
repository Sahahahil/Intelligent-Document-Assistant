"""Text extraction tests. PDFs are built in memory with PyMuPDF."""

import io

import pymupdf
import pytest

from app.core.exceptions import ExtractionError, UnsupportedFileTypeError
from app.utils import get_extractor
from app.utils.pdf_extractor import PdfExtractor
from app.utils.text_extractor import PlainTextExtractor


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for content in pages:
        doc.new_page().insert_text((72, 72), content)
    data: bytes = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for content in pages:
        doc.new_page().insert_text((72, 72), content)
    buffer = io.BytesIO()
    doc.save(buffer, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    doc.close()
    return buffer.getvalue()


def make_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
    data: bytes = doc.tobytes()
    doc.close()
    return data


def test_plain_text_round_trips() -> None:
    result = PlainTextExtractor().extract(b"hello world", filename="a.txt")
    assert result.text == "hello world"
    assert result.page_count is None
    assert result.char_count == 11


def test_crlf_is_normalised() -> None:
    result = PlainTextExtractor().extract(b"line1\r\nline2", filename="a.txt")
    assert result.text == "line1\nline2"
    assert "\r" not in result.text


def test_invalid_utf8_falls_back_to_latin1() -> None:
    result = PlainTextExtractor().extract(b"\xff\xfe invalid utf8", filename="a.txt")
    assert "invalid utf8" in result.text


def test_utf8_bom_is_stripped() -> None:
    result = PlainTextExtractor().extract(b"\xef\xbb\xbfhello", filename="a.txt")
    assert result.text == "hello"


def test_trailing_spaces_are_stripped_per_line() -> None:
    result = PlainTextExtractor().extract(b"a   \nb\t\n", filename="a.txt")
    assert result.text == "a\nb\n"


def test_multipage_pdf_returns_every_page() -> None:
    data = make_pdf(["first page text", "second page text", "third page text"])
    result = PdfExtractor().extract(data, filename="a.pdf")
    assert result.page_count == 3
    for phrase in ("first page text", "second page text", "third page text"):
        assert phrase in result.text


def test_pdf_paragraphs_and_pages_stay_separated() -> None:
    """The recursive chunker splits on blank lines, so they must survive."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 500, 200), "First paragraph.", fontsize=11)
    page.insert_textbox(pymupdf.Rect(72, 250, 500, 400), "Second paragraph.", fontsize=11)
    second_page = doc.new_page()
    second_page.insert_textbox(pymupdf.Rect(72, 72, 500, 200), "Third paragraph.", fontsize=11)
    data: bytes = doc.tobytes()
    doc.close()

    result = PdfExtractor().extract(data, filename="a.pdf")
    assert result.text == "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."


def test_corrupt_pdf_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        PdfExtractor().extract(b"not a pdf", filename="a.pdf")


def test_encrypted_pdf_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError, match="password"):
        PdfExtractor().extract(make_encrypted_pdf(["secret text"]), filename="a.pdf")


def test_image_only_pdf_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError, match="no extractable text"):
        PdfExtractor().extract(make_image_only_pdf(), filename="a.pdf")


def test_whitespace_only_text_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError, match="no extractable text"):
        PlainTextExtractor().extract(b"   \n\t  ", filename="a.txt")


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        get_extractor("exe")


def test_extension_dispatch_is_case_insensitive() -> None:
    assert isinstance(get_extractor("PDF"), PdfExtractor)
    assert isinstance(get_extractor("txt"), PlainTextExtractor)
    assert isinstance(get_extractor(".TXT"), PlainTextExtractor)
