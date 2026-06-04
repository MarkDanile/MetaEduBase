"""Document task repository — raw SQL implementation."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_by_file(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Delete all document tasks linked to a file."""
        await self._session.execute(
            text(
                "DELETE FROM metaedu.document_tasks "
                "WHERE file_id = :fid AND tenant_id = :tid"
            ),
            {"fid": file_id, "tid": tenant_id},
        )

    async def delete_by_dataset(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Delete all document tasks linked to a dataset."""
        await self._session.execute(
            text(
                "DELETE FROM metaedu.document_tasks "
                "WHERE dataset_id = :did AND tenant_id = :tid"
            ),
            {"did": dataset_id, "tid": tenant_id},
        )
