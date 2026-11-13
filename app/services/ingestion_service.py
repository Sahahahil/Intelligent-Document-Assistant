"""The end-to-end ingestion flow: upload → extract → chunk → embed → index.

PostgreSQL and Qdrant cannot share a transaction, so the two stores are kept
consistent by compensation: if a step fails, the document row is marked
`failed` and any vectors already written are deleted.
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.chunking.base import DocumentChunk
from app.chunking.factory import get_chunker
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConflictError,
    ExtractionError,
    PayloadTooLargeError,
    UnsupportedFileTypeError,
    ValidationError,
)
from app.integrations.qdrant import VectorStore
from app.models.document import ChunkingStrategy, Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.utils import get_extractor

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({"pdf", "txt"})
_ERROR_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What the caller gets back after a successful ingest."""

    document_id: UUID
    filename: str
    status: str
    chunking_strategy: str
    total_chunks: int
    embedding_model: str
    embedding_dim: int
    duration_ms: int


def _validate_upload(filename: str, data: bytes, settings: Settings) -> tuple[str, str]:
    """Check the upload is one we accept. Returns `(name, extension)`."""
    name = os.path.basename(filename)
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: '{name}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File is larger than {settings.max_upload_mb} MB")
    if not data:
        raise ValidationError("Uploaded file is empty")
    return name, extension


def _parse_strategy(strategy: ChunkingStrategy | str) -> ChunkingStrategy:
    """Normalise the requested strategy, or say what the valid ones are."""
    value = str(strategy).strip().lower()
    try:
        return ChunkingStrategy(value)
    except ValueError:
        raise ValidationError(
            f"Unknown chunking strategy '{value}'. Valid options: "
            f"{', '.join(option.value for option in ChunkingStrategy)}"
        ) from None


def _resolve_chunk_params(
    chunk_size: int | None, chunk_overlap: int | None, settings: Settings
) -> tuple[int, int]:
    """The chunk parameters actually used, so the row records the truth."""
    size = settings.chunk_size if chunk_size is None else chunk_size
    overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap
    if size <= 0:
        raise ValidationError("chunk_size must be > 0")
    if overlap < 0:
        raise ValidationError("chunk_overlap must be >= 0")
    if overlap >= size:
        raise ValidationError("chunk_overlap must be < chunk_size")
    return size, overlap


class IngestionService:
    """Turns an uploaded file into stored chunks and a document row."""

    def __init__(
        self,
        *,
        document_repo: DocumentRepository,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
    ) -> None:
        self._document_repo = document_repo
        self._vector_store = vector_store
        self._embedding_service = embedding_service

    async def ingest(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        chunking_strategy: ChunkingStrategy | str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> IngestionResult:
        started = time.perf_counter()
        settings = get_settings()
        name, extension = _validate_upload(filename, data, settings)
        strategy = _parse_strategy(chunking_strategy)
        size, overlap = _resolve_chunk_params(chunk_size, chunk_overlap, settings)

        file_hash = hashlib.sha256(data).hexdigest()
        await self._clear_previous_attempt(file_hash)

        document = await self._create_row(
            filename=name,
            content_type=content_type,
            data=data,
            extension=extension,
            file_hash=file_hash,
            strategy=strategy,
            size=size,
            overlap=overlap,
        )

        try:
            chunks, vectors = await self._build_chunks(
                document, data, extension, strategy, size, overlap
            )
            await self._vector_store.ensure_collection()
            await self._vector_store.upsert_chunks(
                document_id=document.id,
                filename=name,
                chunks=chunks,
                vectors=vectors,
                extra={
                    "chunking_strategy": strategy.value,
                    "chunk_size": size,
                    "chunk_overlap": overlap,
                    "embedding_model": self._embedding_service.model_name,
                },
            )
            await self._document_repo.update_status(
                document.id, DocumentStatus.COMPLETED, total_chunks=len(chunks)
            )
        except Exception as exc:
            await self._compensate(document.id, exc)
            raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return IngestionResult(
            document_id=document.id,
            filename=name,
            status=DocumentStatus.COMPLETED.value,
            chunking_strategy=strategy.value,
            total_chunks=len(chunks),
            embedding_model=self._embedding_service.model_name,
            embedding_dim=self._embedding_service.dimension,
            duration_ms=max(1, elapsed_ms),
        )

    async def _clear_previous_attempt(self, file_hash: str) -> None:
        """Refuse a duplicate; let a previously failed file be retried."""
        existing = await self._document_repo.get_by_hash(file_hash)
        if existing is None:
            return
        if existing.status != DocumentStatus.FAILED:
            raise ConflictError(f"Document already ingested (id={existing.id})")
        # The old row still holds the unique file hash, so it has to go
        # before the retry can be written.
        await self._document_repo.delete(existing.id)

    async def _create_row(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        extension: str,
        file_hash: str,
        strategy: ChunkingStrategy,
        size: int,
        overlap: int,
    ) -> Document:
        document = Document(
            id=uuid4(),
            filename=filename,
            content_type=content_type,
            file_size=len(data),
            file_hash=file_hash,
            file_extension=extension,
            chunking_strategy=strategy,
            chunk_size=size,
            chunk_overlap=overlap,
            embedding_model=self._embedding_service.model_name,
            embedding_dim=self._embedding_service.dimension,
            status=DocumentStatus.PROCESSING,
        )
        try:
            return await self._document_repo.create(document)
        except IntegrityError as exc:
            # Another request inserted the same file between our check and
            # this write. The session needs a rollback, which the caller does.
            raise ConflictError("Document already ingested") from exc

    async def _build_chunks(
        self,
        document: Document,
        data: bytes,
        extension: str,
        strategy: ChunkingStrategy,
        size: int,
        overlap: int,
    ) -> tuple[list[DocumentChunk], list[list[float]]]:
        """Extract, chunk and embed. Off the event loop — all three are CPU-bound."""
        extractor = get_extractor(extension)
        extracted = await asyncio.to_thread(extractor.extract, data, filename=document.filename)
        chunker = get_chunker(strategy, chunk_size=size, chunk_overlap=overlap)
        chunks = await asyncio.to_thread(chunker.split, extracted.text, document_id=document.id)
        if not chunks:
            raise ExtractionError(f"'{document.filename}' produced no chunks")
        vectors = await asyncio.to_thread(
            self._embedding_service.embed_texts, [chunk.content for chunk in chunks]
        )
        return chunks, vectors

    async def _compensate(self, document_id: UUID, exc: Exception) -> None:
        """Mark the row failed and drop any vectors that reached Qdrant."""
        try:
            await self._vector_store.delete_document(document_id)
        except Exception:
            logger.exception("Could not clean up vectors for document %s", document_id)
        try:
            await self._document_repo.update_status(
                document_id,
                DocumentStatus.FAILED,
                error_message=str(exc)[:_ERROR_LIMIT],
            )
        except Exception:
            logger.exception("Could not mark document %s as failed", document_id)
