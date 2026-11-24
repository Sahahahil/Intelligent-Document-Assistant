"""Chunk data structure and token counting."""

from dataclasses import dataclass
from uuid import UUID

from app.models.document import ChunkingStrategy


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """One piece of a document, ready to be embedded."""

    content: str
    chunk_index: int
    document_id: UUID
    token_count: int
    strategy: ChunkingStrategy
    start_char: int
    end_char: int


def count_tokens(text: str) -> int:
    """Count whitespace-delimited tokens.

    ponytail: whitespace token estimate — swap in the embedding model's
    tokenizer if chunk-boundary precision matters for the model you ship.
    """
    return len(text.split())
