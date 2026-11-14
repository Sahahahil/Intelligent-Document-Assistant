"""A deterministic stand-in for the embedding service."""

import hashlib
import math
from collections.abc import Callable, Sequence

DEFAULT_DIMENSION = 384


class FakeEmbeddingService:
    """Unit vectors that depend only on the text.

    The hash is `sha256`, not Python's `hash()`, which is salted per process:
    the same text gives the same vector in every run, so a test can seed a
    store with a vector it knows. `mapper` replaces the hash with a function
    of the text, for the tests that need a specific ranking.
    """

    model_name = "fake-model"

    def __init__(
        self,
        dimension: int = DEFAULT_DIMENSION,
        *,
        mapper: Callable[[str], Sequence[float]] | None = None,
    ) -> None:
        self.dimension = dimension
        self.error: Exception | None = None
        self.queries: list[str] = []
        self.embedded: list[str] = []
        self.last_vector: list[float] = []
        self._mapper = mapper

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if self.error is not None:
            raise self.error
        self.embedded.extend(texts)
        vectors = [self._vector(text) for text in texts]
        self.last_vector = vectors[-1] if vectors else []
        return vectors

    def embed_query(self, text: str) -> list[float]:
        if self.error is not None:
            raise self.error
        self.queries.append(text)
        vector = self._vector(text)
        self.last_vector = vector
        return vector

    def _vector(self, text: str) -> list[float]:
        if self._mapper is not None:
            return [float(value) for value in self._mapper(text)]
        digest = hashlib.sha256(text.encode()).digest()
        values = [digest[index % len(digest)] / 255.0 for index in range(self.dimension)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]
