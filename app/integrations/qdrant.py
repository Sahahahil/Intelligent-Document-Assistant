"""Qdrant client factory and the vector store adapter.

Embedded by default: `AsyncQdrantClient(path=...)` runs Qdrant on disk with no
server process. Set `QDRANT_URL` to point at a Qdrant server instead.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

from app.chunking.base import DocumentChunk
from app.core.config import get_settings
from app.core.exceptions import UpstreamError


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    """One client for the process — embedded mode takes a lock on its path."""
    settings = get_settings()
    if settings.qdrant_url:
        return AsyncQdrantClient(url=settings.qdrant_url)
    return AsyncQdrantClient(path=settings.qdrant_path)


async def close_qdrant_client() -> None:
    await get_qdrant_client().close()


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk that came back from a similarity search."""

    content: str
    document_id: UUID
    filename: str
    chunk_index: int
    score: float


@dataclass(frozen=True, slots=True)
class StoredChunk:
    """A chunk as it sits in the store — no score, it was never a search result."""

    chunk_index: int
    content: str
    strategy: str


@asynccontextmanager
async def _qdrant_guard() -> AsyncIterator[None]:
    """Turn any client failure into an `UpstreamError` (502)."""
    try:
        yield
    except UpstreamError:
        raise
    except Exception as exc:
        raise UpstreamError(f"Qdrant error: {exc}") from exc


class VectorStore:
    """Stores chunk embeddings in Qdrant and searches them."""

    def __init__(self, client: AsyncQdrantClient, collection: str, vector_size: int) -> None:
        self._client = client
        self._collection = collection
        self._vector_size = vector_size

    async def ensure_collection(self) -> None:
        """Create the collection if needed; verify its vector size if it exists."""
        async with _qdrant_guard():
            if not await self._client.collection_exists(self._collection):
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=models.VectorParams(
                        size=self._vector_size, distance=models.Distance.COSINE
                    ),
                )
                # The embedded client ignores payload indexes, but a server
                # needs one to filter and delete by document.
                await self._client.create_payload_index(
                    self._collection,
                    field_name="document_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                return

            info = await self._client.get_collection(self._collection)
            vectors = info.config.params.vectors
            # A collection created by us holds one unnamed vector; anything
            # else means someone changed it behind our back.
            size = vectors.size if isinstance(vectors, models.VectorParams) else None
            if size != self._vector_size:
                raise UpstreamError(
                    f"Qdrant collection '{self._collection}' stores vectors of size "
                    f"{size if size is not None else 'unknown'}, expected "
                    f"{self._vector_size}. Re-create the collection or change "
                    f"EMBEDDING_MODEL."
                )

    async def upsert_chunks(
        self,
        *,
        document_id: UUID,
        filename: str,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Store the chunks and their vectors. Returns the number of points."""
        if not chunks:
            return 0

        # The point id is derived from the document and the chunk index, so
        # re-ingesting the same document overwrites instead of duplicating.
        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk.chunk_index}")),
                vector=list(vector),
                payload={
                    **(extra or {}),
                    "document_id": str(document_id),
                    "filename": filename,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "strategy": chunk.metadata.get("strategy"),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        async with _qdrant_guard():
            await self._client.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """Find the closest chunks, optionally restricted to some documents."""
        query_filter = None
        if document_ids:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(
                            any=[str(document_id) for document_id in document_ids]
                        ),
                    )
                ]
            )
        async with _qdrant_guard():
            response = await self._client.query_points(
                collection_name=self._collection,
                query=list(vector),
                limit=top_k,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True,
            )
        return [
            RetrievedChunk(
                content=str(payload.get("content", "")),
                document_id=UUID(str(payload["document_id"])),
                filename=str(payload.get("filename", "")),
                chunk_index=int(payload.get("chunk_index", 0)),
                score=float(point.score),
            )
            for point in response.points
            if (payload := point.payload or {})
        ]

    async def delete_document(self, document_id: UUID) -> None:
        """Remove every chunk of a document. Unknown documents are a no-op."""
        async with _qdrant_guard():
            await self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
            )

    async def list_chunks(self, document_id: UUID, *, limit: int = 20) -> list[StoredChunk]:
        """The stored chunks of a document, for previewing.

        Scrolls the collection rather than searching, so there is no score —
        the order is by chunk index.
        """
        async with _qdrant_guard():
            points, _ = await self._client.scroll(
                collection_name=self._collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )
        chunks: list[StoredChunk] = []
        for point in points:
            payload = point.payload or {}
            chunks.append(
                StoredChunk(
                    chunk_index=int(payload.get("chunk_index", 0)),
                    content=str(payload.get("content", "")),
                    strategy=str(payload.get("strategy") or ""),
                )
            )
        return sorted(chunks, key=lambda chunk: chunk.chunk_index)

    async def count_document(self, document_id: UUID) -> int:
        """How many chunks a document has in the store."""
        async with _qdrant_guard():
            result = await self._client.count(
                collection_name=self._collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                ),
            )
        return int(result.count)


def get_vector_store() -> VectorStore:
    """Build the store from the shared client and the configured settings.

    The vector size comes from the embedding model, so the model is loaded
    the first time this is called — it is a process-wide singleton.
    """
    from app.services.embedding_service import get_embedding_service

    settings = get_settings()
    return VectorStore(
        get_qdrant_client(),
        settings.qdrant_collection,
        get_embedding_service().dimension,
    )
