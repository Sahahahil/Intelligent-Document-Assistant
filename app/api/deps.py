"""FastAPI dependencies — the wiring between the API layer and the services."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.qdrant import get_vector_store
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import get_embedding_service
from app.services.ingestion_service import IngestionService


def get_document_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentRepository:
    """A repository bound to this request's database session."""
    return DocumentRepository(session)


def get_ingestion_service(
    document_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> IngestionService:
    """The ingestion service for this request.

    The vector store and the embedder are process-wide singletons — the model
    is too expensive to load per request.
    """
    return IngestionService(
        document_repo=document_repo,
        vector_store=get_vector_store(),
        embedding_service=get_embedding_service(),
    )
