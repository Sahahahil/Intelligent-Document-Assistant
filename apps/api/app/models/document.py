"""Document metadata model and the shared chunking-strategy enum."""

from datetime import datetime
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChunkingStrategy(StrEnum):
    """The chunking strategies a document can be ingested with.

    Lives here so the database column, the API schema and the chunker factory
    all read the same values.
    """

    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def _enum_column(enum_cls: type[Enum], length: int) -> SAEnum:
    """VARCHAR + CHECK constraint instead of a Postgres enum type.

    A native Postgres enum makes migrations painful (values can't be removed
    without dropping the type); a CHECK constraint does the same job.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class Document(Base):
    """Metadata for one ingested document. The vectors live in Qdrant."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)

    chunking_strategy: Mapped[ChunkingStrategy] = mapped_column(
        _enum_column(ChunkingStrategy, 32), nullable=False
    )
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chunks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        _enum_column(DocumentStatus, 16), nullable=False, default=DocumentStatus.PROCESSING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
