"""The chunk contract both chunking strategies implement."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.models.document import ChunkingStrategy


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """One piece of a document, ready to be embedded."""

    content: str
    chunk_index: int
    document_id: UUID
    token_count: int
    metadata: dict[str, Any]


class Chunker(Protocol):
    """Splits a document's text into chunks."""

    strategy: ChunkingStrategy
    chunk_size: int
    chunk_overlap: int

    def split(self, text: str, *, document_id: UUID) -> list[DocumentChunk]: ...


def count_tokens(text: str) -> int:
    """Count whitespace-delimited tokens.

    ponytail: whitespace token estimate — swap in the embedding model's
    tokenizer if chunk-boundary precision matters for the model you ship.
    """
    return len(text.split())
