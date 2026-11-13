"""Response models for the documents API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.document import ChunkingStrategy, DocumentStatus


class DocumentIngestResponse(BaseModel):
    """What a successful ingest returns."""

    document_id: UUID
    filename: str
    status: DocumentStatus
    chunking_strategy: ChunkingStrategy
    total_chunks: int
    embedding_model: str
    embedding_dim: int
    duration_ms: int


class DocumentSummary(BaseModel):
    """A document in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    file_extension: str
    file_size: int
    chunking_strategy: ChunkingStrategy
    total_chunks: int
    embedding_model: str
    status: DocumentStatus
    created_at: datetime


class DocumentDetail(DocumentSummary):
    """Everything known about one document."""

    content_type: str
    file_hash: str
    chunk_size: int
    chunk_overlap: int
    embedding_dim: int
    error_message: str | None


class DocumentListResponse(BaseModel):
    """A page of documents."""

    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DocumentChunkPreview(BaseModel):
    """One stored chunk, as it sits in the vector store."""

    chunk_index: int
    content: str
    strategy: str


class DocumentChunksResponse(BaseModel):
    """A preview of the chunks stored for a document."""

    document_id: UUID
    total_chunks: int
    items: list[DocumentChunkPreview]
