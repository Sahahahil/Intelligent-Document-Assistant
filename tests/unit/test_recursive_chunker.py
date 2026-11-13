"""Recursive character chunker tests."""

import dataclasses
import time
from collections import Counter
from uuid import UUID

import pytest

from app.chunking import DocumentChunk, FixedSizeChunker, RecursiveCharacterChunker

DOC_ID = UUID("00000000-0000-0000-0000-000000000002")


def words(count: int, marker: str) -> str:
    return " ".join(f"{marker}{i}" for i in range(count))


def shared_tokens(first: str, second: str) -> int:
    """How many trailing tokens of `first` are the leading tokens of `second`."""
    a, b = first.split(), second.split()
    for size in range(min(len(a), len(b)), 0, -1):
        if a[-size:] == b[:size]:
            return size
    return 0


def test_paragraphs_are_not_split() -> None:
    paragraphs = [words(100, f"p{i}_") for i in range(3)]
    text = "\n\n".join(paragraphs)
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )

    assert chunks
    for paragraph in paragraphs:
        assert any(paragraph in chunk.content for chunk in chunks)


def test_sentences_are_not_split() -> None:
    sentences = [words(10, f"s{i}_") for i in range(100)]
    text = ". ".join(sentences)
    chunks = RecursiveCharacterChunker(chunk_size=500, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )

    assert chunks
    for sentence in sentences:
        assert any(sentence in chunk.content for chunk in chunks)


def test_no_chunk_exceeds_the_size() -> None:
    text = "\n\n".join(words(100, f"p{i}_") for i in range(10))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=50).split(
        text, document_id=DOC_ID
    )
    assert all(chunk.token_count <= 250 for chunk in chunks)


def test_consecutive_chunks_overlap() -> None:
    text = "\n\n".join(words(100, f"p{i}_") for i in range(10))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )

    for current, following in zip(chunks, chunks[1:], strict=False):
        shared = shared_tokens(current.content, following.content)
        assert shared > 0
        assert shared <= 100


def test_empty_text_yields_no_chunks() -> None:
    chunker = RecursiveCharacterChunker()
    assert chunker.split("", document_id=DOC_ID) == []
    assert chunker.split("  \n\t ", document_id=DOC_ID) == []


def test_invalid_configuration_raises() -> None:
    with pytest.raises(ValueError):
        RecursiveCharacterChunker(chunk_size=500, chunk_overlap=500)


def test_single_giant_token_is_one_chunk() -> None:
    text = "x" * 10_000
    started = time.monotonic()
    chunks = RecursiveCharacterChunker(chunk_size=500, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )
    assert len(chunks) == 1
    assert time.monotonic() - started < 1.0


def test_paragraph_only_separators_keep_oversized_paragraphs_whole() -> None:
    paragraphs = [words(300, f"p{i}_") for i in range(2)]
    text = "\n\n".join(paragraphs)
    chunks = RecursiveCharacterChunker(
        chunk_size=100, chunk_overlap=10, separators=("\n\n",)
    ).split(text, document_id=DOC_ID)

    assert len(chunks) == 2
    for paragraph in paragraphs:
        assert any(paragraph in chunk.content for chunk in chunks)


def test_chunk_fields_match_the_fixed_chunker() -> None:
    fixed = FixedSizeChunker().split("hello world", document_id=DOC_ID)[0]
    recursive = RecursiveCharacterChunker().split("hello world", document_id=DOC_ID)[0]

    assert isinstance(fixed, DocumentChunk)
    assert isinstance(recursive, DocumentChunk)
    assert [f.name for f in dataclasses.fields(fixed)] == [
        f.name for f in dataclasses.fields(recursive)
    ]
    for field in dataclasses.fields(fixed):
        assert type(getattr(fixed, field.name)) is type(getattr(recursive, field.name))


def test_no_text_is_lost() -> None:
    text = "\n\n".join(words(100, f"p{i}_") for i in range(5))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )

    source = Counter(text.split())
    kept = Counter(" ".join(chunk.content for chunk in chunks).split())
    assert not (source - kept)


def test_chunker_is_deterministic() -> None:
    chunker = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=100)
    text = "\n\n".join(words(100, f"p{i}_") for i in range(5))
    assert chunker.split(text, document_id=DOC_ID) == chunker.split(text, document_id=DOC_ID)


def test_metadata_reports_the_strategy_and_offsets() -> None:
    text = "\n\n".join(words(100, f"p{i}_") for i in range(3))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=100).split(
        text, document_id=DOC_ID
    )

    for chunk in chunks:
        assert chunk.metadata["strategy"] == "recursive"
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]
        assert text[start:end].strip() == chunk.content


def test_whitespace_only_chunks_are_dropped() -> None:
    chunks = RecursiveCharacterChunker(chunk_size=10, chunk_overlap=0).split(
        "   \n\n   ", document_id=DOC_ID
    )
    assert chunks == []


def test_text_without_a_trailing_separator_keeps_the_last_piece() -> None:
    text = "\n\n".join(words(100, f"p{i}_") for i in range(4))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=50).split(
        text, document_id=DOC_ID
    )
    assert any(words(100, "p3_") in chunk.content for chunk in chunks)


def test_crlf_text_is_handled() -> None:
    text = "\r\n\r\n".join(words(100, f"p{i}_") for i in range(3))
    chunks = RecursiveCharacterChunker(chunk_size=250, chunk_overlap=50).split(
        text, document_id=DOC_ID
    )
    assert all("\r" not in chunk.content for chunk in chunks)
