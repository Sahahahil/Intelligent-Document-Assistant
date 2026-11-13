"""Turn a question into ranked context chunks."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.integrations.qdrant import RetrievedChunk, VectorStore
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Where an answer came from — a pointer, not the text."""

    document_id: UUID
    filename: str
    chunk_index: int
    score: float


class RetrievalService:
    """Embeds the query and searches the vector store for the best chunks."""

    def __init__(self, *, vector_store: VectorStore, embedding_service: EmbeddingService) -> None:
        self._vector_store = vector_store
        self._embeddings = embedding_service

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """The chunks that best answer the query, closest first.

        An empty result means the documents do not cover the question — the
        caller must say so rather than answer from the model's own priors.
        """
        if not query or not query.strip():
            raise ValidationError("Query must not be empty")

        settings = get_settings()
        limit = settings.top_k if top_k is None else top_k
        if limit < 1:
            raise ValidationError("top_k must be at least 1")
        threshold = settings.score_threshold if score_threshold is None else score_threshold

        # An empty list means "no filter", not "match nothing".
        ids = list(document_ids) if document_ids else None

        # The same model that embedded the documents must embed the query.
        vector = await asyncio.to_thread(self._embeddings.embed_query, query)
        # Qdrant returns the points ordered by descending score.
        return await self._vector_store.search(
            vector, top_k=limit, document_ids=ids, score_threshold=threshold
        )

    async def retrieve_sources(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[SourceReference]:
        """The same results, reduced to what the API shows the user."""
        chunks = await self.retrieve(
            query,
            top_k=top_k,
            document_ids=document_ids,
            score_threshold=score_threshold,
        )
        return [
            SourceReference(
                document_id=chunk.document_id,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
                score=round(chunk.score, 4),
            )
            for chunk in chunks
        ]
