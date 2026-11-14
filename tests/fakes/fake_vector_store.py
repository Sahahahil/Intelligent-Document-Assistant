"""An in-memory stand-in for the Qdrant-backed vector store."""

import math
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.chunking.base import DocumentChunk
from app.integrations.qdrant import RetrievedChunk


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class FakeVectorStore:
    """The real store's interface, over a list of points.

    The search ranks by cosine similarity the way Qdrant does, so the filters
    behave here as they do against the real thing.
    """

    def __init__(self) -> None:
        self.points: list[tuple[UUID, str, DocumentChunk, list[float]]] = []
        self.upserts: list[tuple[UUID, list[DocumentChunk], dict[str, Any]]] = []
        self.deleted: list[UUID] = []
        self.calls: list[dict[str, Any]] = []
        self.upsert_error: Exception | None = None
        self.search_error: Exception | None = None

    async def ensure_collection(self) -> None:
        return None

    async def upsert_chunks(
        self,
        *,
        document_id: UUID,
        filename: str,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
        extra: dict[str, Any] | None = None,
    ) -> int:
        if self.upsert_error is not None:
            raise self.upsert_error
        self.upserts.append((document_id, list(chunks), dict(extra or {})))
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.points.append((document_id, filename, chunk, list(vector)))
        return len(chunks)

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "vector": list(vector),
                "top_k": top_k,
                "document_ids": document_ids,
                "score_threshold": score_threshold,
            }
        )
        if self.search_error is not None:
            raise self.search_error
        results = []
        for document_id, filename, chunk, stored in self.points:
            if document_ids and document_id not in document_ids:
                continue
            score = _cosine(vector, stored)
            if score_threshold is not None and score < score_threshold:
                continue
            results.append(
                RetrievedChunk(
                    content=chunk.content,
                    document_id=document_id,
                    filename=filename,
                    chunk_index=chunk.chunk_index,
                    score=score,
                )
            )
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]

    async def delete_document(self, document_id: UUID) -> None:
        self.deleted.append(document_id)
        self.points = [point for point in self.points if point[0] != document_id]

    async def count_document(self, document_id: UUID) -> int:
        return sum(1 for point in self.points if point[0] == document_id)
