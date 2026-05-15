"""Folder repository — raw SQL implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_tree(self, tenant_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.folders WHERE tenant_id = :tid ORDER BY sort_order, name"),
            {"tid": tenant_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_by_id(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.folders WHERE id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def create(
        self, tenant_id: uuid.UUID, name: str, parent_id: uuid.UUID | None, sort_order: int
    ) -> dict:
        folder_id = uuid.uuid4()
        if parent_id:
            parent = await self.get_by_id(parent_id, tenant_id)
            if not parent:
                raise ValueError("父文件夹不存在")
            path = f"{parent['path']}.{folder_id.hex[:8]}"
        else:
            path = folder_id.hex[:8]

        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.folders (id, tenant_id, name, parent_id, path, sort_order, created_at, updated_at) "
                "VALUES (:id, :tid, :name, :pid, :path, :sort, :now, :now)"
            ),
            {
                "id": folder_id,
                "tid": tenant_id,
                "name": name,
                "pid": parent_id,
                "path": path,
                "sort": sort_order,
                "now": now,
            },
        )
        return {
            "id": folder_id,
            "tenant_id": tenant_id,
            "name": name,
            "parent_id": parent_id,
            "path": path,
            "sort_order": sort_order,
            "created_at": now,
            "updated_at": now,
        }

    async def update(self, folder_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs: object) -> None:
        sets: list[str] = []
        params: dict = {"fid": folder_id, "tid": tenant_id}
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = :{key}")
                params[key] = val
        if not sets:
            return
        sets.append("updated_at = :now")
        params["now"] = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                f"UPDATE metaedu.folders SET {', '.join(sets)} WHERE id = :fid AND tenant_id = :tid"
            ),
            params,
        )

    async def move(
        self, folder_id: uuid.UUID, tenant_id: uuid.UUID, new_parent_id: uuid.UUID | None
    ) -> None:
        folder = await self.get_by_id(folder_id, tenant_id)
        if not folder:
            raise ValueError("文件夹不存在")
        if new_parent_id:
            parent = await self.get_by_id(new_parent_id, tenant_id)
            if not parent:
                raise ValueError("目标父文件夹不存在")
            new_path = f"{parent['path']}.{folder_id.hex[:8]}"
        else:
            new_path = folder_id.hex[:8]
        await self.update(folder_id, tenant_id, parent_id=new_parent_id, path=new_path)

    async def delete(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.folders WHERE id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )

    async def count_files(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM metaedu.files WHERE folder_id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )
        return result.scalar() or 0
