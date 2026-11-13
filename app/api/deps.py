"""FastAPI dependencies — the wiring between the API layer and the services."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.llm import LLMClient, get_llm_client
from app.integrations.qdrant import get_vector_store
from app.integrations.redis import get_redis_client
from app.repositories.document_repository import DocumentRepository
from app.services.conversation_service import ConversationStore
from app.services.embedding_service import get_embedding_service
from app.services.ingestion_service import IngestionService
from app.services.query_rewriter import QueryRewriter


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


def get_redis() -> Redis:
    """The process-wide Redis client — the connection pool is reused."""
    return get_redis_client()


def get_conversation_store(
    redis: Annotated[Redis, Depends(get_redis)],
) -> ConversationStore:
    """The conversation store for this request."""
    return ConversationStore(redis)


def get_query_rewriter(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> QueryRewriter:
    """The query rewriter for this request."""
    return QueryRewriter(llm)
