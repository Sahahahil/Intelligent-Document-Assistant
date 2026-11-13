"""Application settings, loaded once from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every configurable value. Values come from the environment or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Intelligent Document Assistant"
    debug: bool = False

    # PostgreSQL — documents and bookings
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/document_db"

    # Redis — conversation memory
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant — vector store.
    # QDRANT_URL points at a Qdrant server; when it is empty the client uses
    # QDRANT_PATH and runs Qdrant embedded (same API, on-disk, no server).
    qdrant_url: str = ""
    qdrant_path: str = "./qdrant_data"
    qdrant_collection: str = "documents"

    # LLM — any OpenAI-compatible provider
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Chunking
    chunk_size: int = 200
    chunk_overlap: int = 40

    # Retrieval
    top_k: int = 5
    score_threshold: float = 0.0

    # Limits
    max_upload_mb: int = 20
    session_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings. Cached so `.env` is read once."""
    return Settings()
