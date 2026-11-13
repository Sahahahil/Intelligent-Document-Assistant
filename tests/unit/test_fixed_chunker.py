"""Fixed-size chunker tests."""

import dataclasses
from uuid import UUID

import pytest

from app.chunking import DocumentChunk, FixedSizeChunker, count_tokens

DOC_ID = UUID("00000000-0000-0000-0000-000000000001")


def make_text(tokens: int) -> str:
    return " ".join(f"t{i}" for i in range(tokens))


def test_count_tokens() -> None:
    assert count_tokens("a b  c") == 3


def test_empty_text_yields_no_chunks() -> None:
    chunker = FixedSizeChunker()
    assert chunker.split("", document_id=DOC_ID) == []
    assert chunker.split("   \n\t ", document_id=DOC_ID) == []


def test_windows_over_the_text() -> None:
    """step = 500 - 100 = 400, so the windows start at 0, 400 and 800."""
    chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.split(make_text(1200), document_id=DOC_ID)

    assert len(chunks) == 3
    assert [c.token_count for c in chunks] == [500, 500, 400]


def test_no_chunk_exceeds_the_size() -> None:
    chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.split(make_text(1200), document_id=DOC_ID)
    assert all(c.token_count <= 500 for c in chunks)


def test_consecutive_chunks_overlap_exactly() -> None:
    chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.split(make_text(1200), document_id=DOC_ID)

    for current, following in zip(chunks, chunks[1:], strict=False):
        assert current.content.split()[-100:] == following.content.split()[:100]


def test_chunk_indexes_are_contiguous() -> None:
    chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.split(make_text(1200), document_id=DOC_ID)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_short_text_becomes_one_chunk() -> None:
    text = "  only ten tokens here  "
    chunks = FixedSizeChunker(chunk_size=500).split(text, document_id=DOC_ID)
    assert len(chunks) == 1
    assert chunks[0].content == text.strip()


def test_no_trailing_chunk_when_text_is_shorter_than_overlap() -> None:
    chunks = FixedSizeChunker(chunk_size=500, chunk_overlap=100).split(
        make_text(100), document_id=DOC_ID
    )
    assert len(chunks) == 1


@pytest.mark.parametrize(
    ("size", "overlap"),
    [(500, 500), (0, 10), (-1, 0), (500, -1)],
)
def test_invalid_configuration_raises(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        FixedSizeChunker(chunk_size=size, chunk_overlap=overlap)


def test_metadata_points_back_into_the_original_text() -> None:
    text = make_text(1200)
    chunks = FixedSizeChunker(chunk_size=500, chunk_overlap=100).split(text, document_id=DOC_ID)

    for chunk in chunks:
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]
        assert text[start:end].strip() == chunk.content
        assert chunk.metadata["strategy"] == "fixed_size"


def test_chunk_is_frozen() -> None:
    chunk = FixedSizeChunker().split("hello", document_id=DOC_ID)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.content = "changed"  # type: ignore[misc]


def test_chunker_is_pure() -> None:
    chunker = FixedSizeChunker(chunk_size=500, chunk_overlap=100)
    text = make_text(1200)
    assert chunker.split(text, document_id=DOC_ID) == chunker.split(text, document_id=DOC_ID)


def test_unicode_is_handled() -> None:
    text = "héllo wörld 😀 emoji 🎉 tokens"
    chunks = FixedSizeChunker(chunk_size=3, chunk_overlap=1).split(text, document_id=DOC_ID)
    assert all(c.content for c in chunks)
    assert "😀" in " ".join(c.content for c in chunks)


def test_single_huge_token_is_one_chunk() -> None:
    """A 5000-character 'word' is a single token — accepted, documented."""
    text = "x" * 5000
    chunks = FixedSizeChunker(chunk_size=500, chunk_overlap=100).split(text, document_id=DOC_ID)
    assert len(chunks) == 1
    assert chunks[0].token_count == 1


def test_document_chunk_fields() -> None:
    chunk = FixedSizeChunker().split("hello world", document_id=DOC_ID)[0]
    assert isinstance(chunk, DocumentChunk)
    assert chunk.document_id == DOC_ID
    assert chunk.token_count == 2
