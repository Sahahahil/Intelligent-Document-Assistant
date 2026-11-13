"""Chunker factory tests."""

from pathlib import Path

import pytest

from app.chunking import FixedSizeChunker, RecursiveCharacterChunker, get_chunker
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.models.document import ChunkingStrategy


def test_strategy_names_select_the_chunker() -> None:
    assert isinstance(get_chunker("fixed_size"), FixedSizeChunker)
    assert isinstance(get_chunker("recursive"), RecursiveCharacterChunker)


def test_enum_selects_the_chunker() -> None:
    assert isinstance(get_chunker(ChunkingStrategy.RECURSIVE), RecursiveCharacterChunker)
    assert isinstance(get_chunker(ChunkingStrategy.FIXED_SIZE), FixedSizeChunker)


def test_strategy_name_is_normalised() -> None:
    assert isinstance(get_chunker("  Recursive "), RecursiveCharacterChunker)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(ValidationError) as excinfo:
        get_chunker("bogus")
    message = str(excinfo.value)
    assert "fixed_size" in message
    assert "recursive" in message


def test_explicit_size_wins() -> None:
    chunker = get_chunker("recursive", chunk_size=1000)
    assert chunker.chunk_size == 1000


def test_defaults_come_from_the_settings() -> None:
    settings = get_settings()
    chunker = get_chunker("recursive")
    assert chunker.chunk_size == settings.chunk_size
    assert chunker.chunk_overlap == settings.chunk_overlap


def test_overlap_must_be_smaller_than_the_size() -> None:
    with pytest.raises(ValueError):
        get_chunker("recursive", chunk_size=500, chunk_overlap=999)


def test_each_call_returns_a_new_instance() -> None:
    assert get_chunker("recursive") is not get_chunker("recursive")


def test_none_strategy_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        get_chunker(None)  # type: ignore[arg-type]


def test_no_direct_chunker_imports_outside_the_package() -> None:
    """The factory is the only way to reach a concrete chunker."""
    app_root = Path(__file__).resolve().parents[2] / "app"
    offenders = [
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if "chunking" not in path.parts
        and (
            "FixedSizeChunker" in path.read_text()
            or "RecursiveCharacterChunker" in path.read_text()
        )
    ]
    assert offenders == []
