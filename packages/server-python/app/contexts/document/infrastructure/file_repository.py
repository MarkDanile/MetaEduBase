"""File repository — raw SQL implementation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_files(
        self,
        tenant_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        tag: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["tenant_id = :tid"]
        params: dict = {"tid": tenant_id}
        if folder_id is not None:
            conditions.append("folder_id = :fid")
            params["fid"] = folder_id
        if tag:
            conditions.append(":tag = ANY(tags)")
            params["tag"] = tag
        if status:
            conditions.append("status = :status")
            params["status"] = status
        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(f"SELECT * FROM metaedu.files WHERE {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {**params, "lim": limit, "off": offset},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_by_id(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def create(
        self,
        tenant_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        filename: str,
        file_type: str,
        doc_type: str | None,
        file_size: int | None,
        storage_key: str,
        tags: list[str],
        uploaded_by: uuid.UUID,
    ) -> dict:
        file_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.files "
                "(id, tenant_id, folder_id, filename, file_type, doc_type, file_size, storage_key, tags, status, uploaded_by, created_at, updated_at) "
                "VALUES (:id, :tid, :fid, :name, :ftype, :dtype, :fsize, :skey, :tags, 'uploaded', :uid, :now, :now)"
            ),
            {
                "id": file_id, "tid": tenant_id, "fid": folder_id, "name": filename,
                "ftype": file_type, "dtype": doc_type, "fsize": file_size,
                "skey": storage_key, "tags": tags, "uid": uploaded_by, "now": now,
            },
        )
        return {"id": file_id, "tenant_id": tenant_id, "folder_id": folder_id, "filename": filename,
                "file_type": file_type, "doc_type": doc_type, "file_size": file_size,
                "storage_key": storage_key, "tags": tags, "status": "uploaded",
                "structured_data": None, "uploaded_by": uploaded_by, "created_at": now, "updated_at": now}

    async def update(self, file_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs: object) -> None:
        sets: list[str] = []
        params: dict = {"fid": file_id, "tid": tenant_id}
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = :{key}")
                params[key] = val
        if not sets:
            return
        sets.append("updated_at = :now")
        params["now"] = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(f"UPDATE metaedu.files SET {', '.join(sets)} WHERE id = :fid AND tenant_id = :tid"),
            params,
        )

    async def update_status(self, file_id: uuid.UUID, tenant_id: uuid.UUID, status: str) -> None:
        await self.update(file_id, tenant_id, status=status)

    async def update_structured_data(self, file_id: uuid.UUID, tenant_id: uuid.UUID, data: dict) -> None:
        await self._session.execute(
            text("UPDATE metaedu.files SET structured_data = :data::jsonb, updated_at = :now WHERE id = :fid AND tenant_id = :tid"),
            {"data": json.dumps(data), "fid": file_id, "tid": tenant_id, "now": datetime.now(UTC).replace(tzinfo=None)},
        )

    async def delete(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
