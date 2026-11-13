"""Business logic. Services never import from the API layer."""

from app.services.embedding_service import EmbeddingService, get_embedding_service

__all__ = ["EmbeddingService", "get_embedding_service"]
