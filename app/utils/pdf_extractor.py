"""PDF extractor built on PyMuPDF. In-memory only — no temp files."""

import pymupdf

from app.core.exceptions import ExtractionError
from app.utils.base import ExtractedText, build_result


class PdfExtractor:
    """Reads a PDF with PyMuPDF and returns the text of every page."""

    def extract(self, data: bytes, *, filename: str) -> ExtractedText:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ExtractionError(f"'{filename}' is password protected")
                page_count = doc.page_count
                text = "\n\n".join(self._page_text(page) for page in doc)
        except ExtractionError:
            raise
        except Exception as exc:
            # Corrupt, truncated or otherwise unreadable files land here.
            raise ExtractionError(f"Could not read '{filename}': {exc}") from exc
        return build_result(text, page_count, filename=filename)

    @staticmethod
    def _page_text(page: pymupdf.Page) -> str:
        """Text of one page, with a blank line between its paragraphs.

        Blocks rather than plain `get_text()`: the default text mode flattens
        paragraphs into single newlines, and "\n\n" is the recursive chunker's
        primary split point.
        """
        blocks = page.get_text("blocks")
        return "\n\n".join(
            block[4].strip()
            for block in blocks
            if block[6] == 0 and block[4].strip()  # block_type 0 == text
        )
