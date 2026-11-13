"""Embedding service tests.

The unit tests run against a fake model — no download, no torch import. The
real model is exercised by the `model`-marked test at the bottom.
"""

import hashlib
import math
import random

import pytest

from app.core.config import get_settings
from app.services import embedding_service
from app.services.embedding_service import EmbeddingService, get_embedding_service

DIMENSION = 384


class FakeTokenizer:
    def encode(self, text: str) -> list[int]:
        return list(range(len(text.split())))


class FakeModel:
    """Stands in for SentenceTransformer: deterministic, unit-norm vectors."""

    def __init__(self, model_name: str, dimension: int = DIMENSION) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.tokenizer = FakeTokenizer()
        self.encoded: list[list[str]] = []

    def get_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
        self.encoded.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        values = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    """Patch the loader so no model is downloaded and torch is never imported."""
    fake = FakeModel("fake-model")

    def fake_load(model_name: str) -> FakeModel:
        fake.model_name = model_name
        return fake

    monkeypatch.setattr(embedding_service, "_load_model", fake_load)
    return fake


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def test_embed_query_returns_a_vector(model: FakeModel) -> None:
    vector = EmbeddingService().embed_query("hello")
    assert len(vector) == DIMENSION
    assert all(isinstance(value, float) for value in vector)


def test_embed_texts_returns_one_vector_per_text(model: FakeModel) -> None:
    vectors = EmbeddingService().embed_texts(["first", "second"])
    assert len(vectors) == 2
    assert all(len(vector) == DIMENSION for vector in vectors)


def test_empty_list_returns_nothing(model: FakeModel) -> None:
    assert EmbeddingService().embed_texts([]) == []


def test_blank_text_is_replaced_with_a_space(model: FakeModel) -> None:
    vectors = EmbeddingService().embed_texts(["", "   "])
    assert len(vectors) == 2
    assert model.encoded[0] == [" ", " "]


def test_same_text_gives_the_same_vector(model: FakeModel) -> None:
    service = EmbeddingService()
    assert service.embed_query("hello") == service.embed_query("hello")


def test_vectors_are_unit_norm(model: FakeModel) -> None:
    vector = EmbeddingService().embed_query("hello")
    assert norm(vector) == pytest.approx(1.0, abs=1e-3)


def test_model_name_comes_from_the_settings(model: FakeModel) -> None:
    assert EmbeddingService().model_name == get_settings().embedding_model
    assert EmbeddingService("other-model").model_name == "other-model"


def test_dimension_matches_the_model(model: FakeModel) -> None:
    assert EmbeddingService().dimension == DIMENSION


def test_the_model_is_loaded_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = 0

    def counting_load(_model_name: str) -> FakeModel:
        nonlocal loaded
        loaded += 1
        return FakeModel("fake-model")

    monkeypatch.setattr(embedding_service, "_load_model", counting_load)
    service = EmbeddingService()
    service.embed_texts(["one"])
    service.embed_texts(["two"])
    assert loaded == 1


def test_token_count_uses_the_model_tokenizer(model: FakeModel) -> None:
    count = EmbeddingService().token_count("hello world")
    assert isinstance(count, int)
    assert count > 0


def test_the_singleton_is_reused() -> None:
    assert get_embedding_service() is get_embedding_service()


@pytest.mark.model
def test_the_real_model_produces_384_dim_vectors() -> None:
    """Needs the model on disk — run with `uv run pytest -m model`."""
    service = EmbeddingService()
    assert service.dimension == 384

    vector = service.embed_query("hello")
    assert len(vector) == 384
    assert norm(vector) == pytest.approx(1.0, abs=1e-3)
