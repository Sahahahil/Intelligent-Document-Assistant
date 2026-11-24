"""Turns text into dense vectors with a local sentence-transformers model."""

from collections.abc import Callable, Sequence
from functools import cached_property, lru_cache

from app.core.config import get_settings

_BATCH_SIZE = 64


def _load_model(model_name: str) -> "SentenceTransformer":
    """Import and instantiate the model.

    The import is inside the function on purpose: `torch` is a 2 GB
    dependency, and importing it at module import time would slow every
    uvicorn boot and every test run.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


class EmbeddingService:
    """Embeds text for ingestion and for queries — always the same model.

    A mismatch between the two silently destroys retrieval quality, so the
    model name is stored on every document row.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        loader: Callable[[str], "SentenceTransformer"] | None = None,
    ) -> None:
        """The service.

        `loader` is the seam the tests use: they pass a fake model, so no
        model is downloaded and torch is never imported.
        """
        self._model_name = model_name or get_settings().embedding_model
        self._loader = loader or _load_model

    @property
    def model_name(self) -> str:
        return self._model_name

    @cached_property
    def _model(self) -> "SentenceTransformer":
        return self._loader(self._model_name)

    @property
    def dimension(self) -> int:
        """The vector length of the loaded model (384 for all-MiniLM-L6-v2)."""
        return int(self._model.get_embedding_dimension())

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts, in the order they were given."""
        if not texts:
            return []
        # The model rejects empty input, so blank chunks become a single space.
        cleaned = [text if text.strip() else " " for text in texts]
        vectors = self._model.encode(
            cleaned,
            batch_size=_BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self.embed_texts([text])[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """The process-wide service — the model is too expensive to load twice."""
    return EmbeddingService()
