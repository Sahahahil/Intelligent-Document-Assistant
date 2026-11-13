"""Document ingestion and management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import get_document_repository, get_ingestion_service
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError
from app.integrations.qdrant import VectorStore, get_vector_store
from app.models.document import ChunkingStrategy, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentChunkPreview,
    DocumentChunksResponse,
    DocumentDetail,
    DocumentIngestResponse,
    DocumentListResponse,
    DocumentSummary,
)
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/ingest",
    response_model=DocumentIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a document",
)
async def ingest_document(
    file: Annotated[UploadFile, File(description="PDF or TXT document")],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    chunking_strategy: Annotated[ChunkingStrategy, Form()] = ChunkingStrategy.RECURSIVE,
    chunk_size: Annotated[int | None, Form()] = None,
    chunk_overlap: Annotated[int | None, Form()] = None,
) -> DocumentIngestResponse:
    """Run an uploaded document through the ingestion pipeline."""
    settings = get_settings()
    # The upload is spooled to disk by the multipart parser, so the size is
    # known before the bytes are copied into memory.
    if file.size is not None and file.size > settings.max_upload_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File is larger than {settings.max_upload_mb} MB")

    data = await file.read()
    result = await service.ingest(
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return DocumentIngestResponse(
        document_id=result.document_id,
        filename=result.filename,
        status=result.status,
        chunking_strategy=result.chunking_strategy,
        total_chunks=result.total_chunks,
        embedding_model=result.embedding_model,
        embedding_dim=result.embedding_dim,
        duration_ms=result.duration_ms,
    )


@router.get("", response_model=DocumentListResponse, summary="List documents")
async def list_documents(
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
) -> DocumentListResponse:
    """A page of documents, newest first."""
    rows, total = await document_repo.list(limit=limit, offset=offset, status=document_status)
    return DocumentListResponse(
        items=[DocumentSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail, summary="Document detail")
async def get_document(
    document_id: UUID,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> DocumentDetail:
    """Everything known about one document."""
    document = await document_repo.get(document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    return DocumentDetail.model_validate(document)


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunksResponse,
    summary="Preview the stored chunks",
)
async def get_document_chunks(
    document_id: UUID,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentChunksResponse:
    """The first chunks of a document, as they were indexed."""
    document = await document_repo.get(document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    chunks = await vector_store.list_chunks(document_id, limit=limit)
    return DocumentChunksResponse(
        document_id=document_id,
        total_chunks=document.total_chunks,
        items=[
            DocumentChunkPreview(
                chunk_index=chunk.chunk_index, content=chunk.content, strategy=chunk.strategy
            )
            for chunk in chunks
        ],
    )


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a document"
)
async def delete_document(
    document_id: UUID,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> Response:
    """Remove the document row and its vectors."""
    document = await document_repo.get(document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    # Vectors first: if this fails the row survives and the delete can be
    # retried, which is better than a row pointing at vectors that are gone.
    await vector_store.delete_document(document_id)
    await document_repo.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
