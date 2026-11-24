"""Plain-text extractor for .txt uploads."""

from app.utils.base import require_text


class PlainTextExtractor:
    """Reads a text file as UTF-8, falling back to latin-1."""

    def extract(self, data: bytes, *, filename: str) -> str:
        text = self._decode(data)
        # Trailing spaces carry no meaning and only inflate the chunks.
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        return require_text(text, filename=filename)

    @staticmethod
    def _decode(data: bytes) -> str:
        """Decode to text. utf-8-sig also strips a byte-order mark."""
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            # latin-1 maps every byte to a code point, so it cannot fail.
            return data.decode("latin-1")
