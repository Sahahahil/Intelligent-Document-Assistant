"""Persistence for documents. The only place that talks to the `documents` table."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def get(self, document_id: UUID) -> Document | None:
        return await self._session.get(Document, document_id)

    async def get_by_hash(self, file_hash: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: DocumentStatus | None = None,
    ) -> tuple[list[Document], int]:
        rows_stmt = select(Document)
        count_stmt = select(func.count()).select_from(Document)
        if status is not None:
            rows_stmt = rows_stmt.where(Document.status == status)
            count_stmt = count_stmt.where(Document.status == status)

        total = (await self._session.execute(count_stmt)).scalar_one()
        rows = (
            (
                await self._session.execute(
                    rows_stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        total_chunks: int | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update only the given fields. Returns False if the row is gone."""
        values: dict[str, Any] = {"status": status}
        if total_chunks is not None:
            values["total_chunks"] = total_chunks
        if error_message is not None:
            values["error_message"] = error_message

        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Document).where(Document.id == document_id).values(**values)
            ),
        )
        await self._session.commit()
        return result.rowcount > 0

    async def delete(self, document_id: UUID) -> bool:
        document = await self.get(document_id)
        if document is None:
            return False
        await self._session.delete(document)
        await self._session.commit()
        return True
