"""Document ingestion and management."""

import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_document_repository, get_ingestion_service
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError
from app.integrations.qdrant import VectorStore, get_vector_store
from app.models.document import ChunkingStrategy, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
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
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document and index it in the background",
)
async def ingest_document(
    file: Annotated[UploadFile, File(description="PDF or TXT document")],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    chunking_strategy: Annotated[
        ChunkingStrategy, Form(description="How the text is split into chunks")
    ] = ChunkingStrategy.RECURSIVE,
    chunk_size: Annotated[
        int | None, Form(description="Words per chunk. 0 or empty uses CHUNK_SIZE")
    ] = None,
    chunk_overlap: Annotated[
        int | None,
        Form(description="Words shared by neighbouring chunks. 0 or empty uses CHUNK_OVERLAP"),
    ] = None,
) -> DocumentIngestResponse:
    """Accept an uploaded document and start indexing it.

    The row is written before this returns, so the document can be listed and
    followed while it is still being chunked and embedded.
    """
    settings = get_settings()
    # The upload is spooled to disk by the multipart parser, so the size is
    # known before the bytes are copied into memory.
    if file.size is not None and file.size > settings.max_upload_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"File is larger than {settings.max_upload_mb} MB")

    data = await file.read()
    document = await service.start(
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return DocumentIngestResponse(
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        chunking_strategy=document.chunking_strategy,
        total_chunks=document.total_chunks,
        embedding_model=document.embedding_model,
        embedding_dim=document.embedding_dim,
        duration_ms=0,
    )


@router.get("", response_model=DocumentListResponse, summary="List documents")
async def list_documents(
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(description="Match part of the filename")] = None,
) -> DocumentListResponse:
    """A page of documents, newest first."""
    rows, total = await document_repo.list(
        limit=limit, offset=offset, status=document_status, search=search
    )
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


@router.get("/{document_id}/status/stream", summary="Stream document processing status via SSE")
async def document_status_stream(
    document_id: UUID,
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> EventSourceResponse:
    """Stream document processing status via Server-Sent Events."""

    async def event_generator():
        while True:
            doc = await document_repo.get(document_id)
            if not doc:
                yield {"data": json.dumps({"stage": "error", "progress": 0, "error": "Not found"})}
                break

            # The pipeline publishes the stage it has reached; the row is the
            # fallback for a document whose progress has already expired.
            published = await service.get_progress(document_id)
            if published is not None:
                yield {"data": json.dumps(published)}
            else:
                stage_map = {
                    DocumentStatus.PROCESSING: "processing",
                    DocumentStatus.COMPLETED: "completed",
                    DocumentStatus.FAILED: "failed",
                }
                yield {"data": json.dumps({
                    "stage": stage_map[doc.status],
                    "progress": 100 if doc.status != DocumentStatus.PROCESSING else 50,
                    "total_chunks": doc.total_chunks,
                })}

            if doc.status != DocumentStatus.PROCESSING:
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())
