"""FastAPI dependencies — the wiring between the API layer and the services."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.llm import LLMClient, get_llm_client
from app.integrations.qdrant import get_vector_store
from app.integrations.redis import get_redis_client
from app.repositories.booking_repository import BookingRepository
from app.repositories.document_repository import DocumentRepository
from app.services.booking_service import BookingExtractor, BookingService
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.conversation_service import ConversationStore
from app.services.embedding_service import get_embedding_service
from app.services.ingestion_service import IngestionService
from app.services.query_rewriter import QueryRewriter
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService


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


def get_retrieval_service() -> RetrievalService:
    """The retrieval service - the vector store and the embedder are singletons."""
    return RetrievalService(
        vector_store=get_vector_store(),
        embedding_service=get_embedding_service(),
    )


def get_rag_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    rewriter: Annotated[QueryRewriter, Depends(get_query_rewriter)],
) -> RAGService:
    """The RAG service for this request."""
    return RAGService(retrieval=retrieval, llm=llm, rewriter=rewriter)


def get_booking_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BookingRepository:
    """A repository bound to this request's database session."""
    return BookingRepository(session)


def get_booking_extractor(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> BookingExtractor:
    """The booking extractor for this request."""
    return BookingExtractor(llm)


def get_booking_service(
    extractor: Annotated[BookingExtractor, Depends(get_booking_extractor)],
    repo: Annotated[BookingRepository, Depends(get_booking_repository)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> BookingService:
    """The booking service for this request."""
    return BookingService(extractor=extractor, repo=repo, redis=redis)


def get_chat_orchestrator(
    rag: Annotated[RAGService, Depends(get_rag_service)],
    booking: Annotated[BookingService, Depends(get_booking_service)],
    store: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> ChatOrchestrator:
    """The chat orchestrator for this request."""
    return ChatOrchestrator(rag=rag, booking=booking, store=store)
