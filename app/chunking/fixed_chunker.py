"""Strategy A — fixed-size chunking with overlap."""

import re
from uuid import UUID

from app.chunking.base import DocumentChunk, count_tokens
from app.models.document import ChunkingStrategy


class FixedSizeChunker:
    """Windows of `chunk_size` tokens, advancing by `chunk_size - chunk_overlap`.

    Pure: no I/O, no globals, no config reads.
    """

    strategy = ChunkingStrategy.FIXED_SIZE

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str, *, document_id: UUID) -> list[DocumentChunk]:
        if not text.strip():
            return []

        # Token boundaries with their character offsets, so every chunk can
        # point back into the original string.
        spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        step = self.chunk_size - self.chunk_overlap

        chunks: list[DocumentChunk] = []
        index = 0
        while index < len(spans):
            window = spans[index : index + self.chunk_size]
            start_char, end_char = window[0][0], window[-1][1]
            content = text[start_char:end_char].strip()
            if content:
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
            if index + self.chunk_size >= len(spans):
                # The rest of the text is covered — no duplicate trailing chunk.
                break
            index += step
        return chunks
