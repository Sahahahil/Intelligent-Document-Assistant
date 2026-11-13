"""Strategy B — recursive character chunking."""

from collections.abc import Sequence
from uuid import UUID

from app.chunking.base import DocumentChunk, count_tokens
from app.models.document import ChunkingStrategy


class RecursiveCharacterChunker:
    """Splits on the most structural separator available, then merges.

    Pure: no I/O, no globals, no config reads.
    """

    strategy = ChunkingStrategy.RECURSIVE

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        separators: Sequence[str] = ("\n\n", "\n", ". ", " ", ""),
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = tuple(separators)

    def split(self, text: str, *, document_id: UUID) -> list[DocumentChunk]:
        text = text.replace("\r\n", "\n")
        if not text.strip():
            return []

        pieces = self._split(text, self.separators, 0)
        chunks: list[DocumentChunk] = []
        for content, start_char, end_char in self._merge(pieces):
            if not content.strip():
                continue
            chunks.append(
                DocumentChunk(
                    content=content,
                    chunk_index=len(chunks),
                    document_id=document_id,
                    token_count=count_tokens(content),
                    metadata={
                        "strategy": self.strategy.value,
                        "start_char": start_char,
                        "end_char": end_char,
                    },
                )
            )
        return chunks

    def _split(self, text: str, separators: Sequence[str], base: int) -> list[tuple[str, int]]:
        """Split into pieces of at most `chunk_size` tokens.

        The pieces concatenate back to `text`, so each one keeps its offset
        in the original string.
        """
        if count_tokens(text) <= self.chunk_size:
            return [(text, base)]
        if not separators or separators[0] == "":
            # Nothing left to split on — this piece stays whole.
            return [(text, base)]

        sep, rest = separators[0], separators[1:]
        raw = text.split(sep)
        pieces: list[tuple[str, int]] = []
        offset = base
        for index, part in enumerate(raw):
            # The separator stays attached, so no punctuation is lost.
            part = part + (sep if index < len(raw) - 1 else "")
            start = offset
            offset += len(part)
            if count_tokens(part) <= self.chunk_size:
                pieces.append((part, start))
            else:
                pieces.extend(self._split(part, rest, start))
        return pieces

    def _merge(self, pieces: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
        """Group pieces into chunks of at most `chunk_size` tokens."""
        chunks: list[tuple[str, int, int]] = []
        buffer: list[tuple[str, int]] = []

        for piece, offset in pieces:
            if count_tokens(piece) > self.chunk_size:
                # An un-splittable piece: it becomes a chunk of its own.
                if buffer:
                    chunks.append(self._span(buffer))
                    buffer = []
                chunks.append(self._span([(piece, offset)]))
                continue

            candidate = "".join(text for text, _ in buffer) + piece
            if count_tokens(candidate) <= self.chunk_size:
                buffer.append((piece, offset))
                continue

            if buffer:
                chunks.append(self._span(buffer))
                # Carry the tail of the chunk we just emitted into the next
                # one, but never so much that the next chunk overflows.
                buffer = self._overlap_tail(buffer, self.chunk_size - count_tokens(piece))
            buffer.append((piece, offset))

        if buffer:
            chunks.append(self._span(buffer))
        return chunks

    def _overlap_tail(self, buffer: list[tuple[str, int]], limit: int) -> list[tuple[str, int]]:
        """The trailing pieces of the last chunk, at most `chunk_overlap` tokens."""
        limit = min(limit, self.chunk_overlap)
        tail: list[tuple[str, int]] = []
        candidate = ""
        for piece, offset in reversed(buffer):
            candidate = piece + candidate
            if count_tokens(candidate) > limit:
                break
            tail.insert(0, (piece, offset))
        return tail

    @staticmethod
    def _span(buffer: list[tuple[str, int]]) -> tuple[str, int, int]:
        """Join the pieces into a chunk and report its span in the original text."""
        content = "".join(piece for piece, _ in buffer)
        start_char = buffer[0][1]
        end_char = buffer[-1][1] + len(buffer[-1][0])
        return content.strip(), start_char, end_char
