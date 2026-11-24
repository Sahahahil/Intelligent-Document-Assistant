"""The one place that maps a strategy name to a chunker implementation."""

from app.chunking.base import Chunker
from app.chunking.fixed_chunker import FixedSizeChunker
from app.chunking.recursive_chunker import RecursiveCharacterChunker
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.models.document import ChunkingStrategy


def get_chunker(
    strategy: ChunkingStrategy | str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> Chunker:
    """Build a chunker for `strategy`, defaulting the size from the settings.

    ponytail: explicit if/elif mapping — add a registry only if a third
    strategy appears.
    """
    settings = get_settings()
    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    value = str(strategy).strip().lower()
    if value == ChunkingStrategy.FIXED_SIZE.value:
        return FixedSizeChunker(chunk_size=size, chunk_overlap=overlap)
    if value == ChunkingStrategy.RECURSIVE.value:
        return RecursiveCharacterChunker(chunk_size=size, chunk_overlap=overlap)
    raise ValidationError(
        f"Unknown chunking strategy '{value}'. Valid options: "
        f"{', '.join(option.value for option in ChunkingStrategy)}"
    )
