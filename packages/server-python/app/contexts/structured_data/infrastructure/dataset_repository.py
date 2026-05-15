"""Dataset repository — raw SQL implementation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_datasets(
        self,
        tenant_id: uuid.UUID,
        tag: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["tenant_id = :tid"]
        params: dict = {"tid": tenant_id}
        if tag:
            conditions.append(":tag = ANY(tags)")
            params["tag"] = tag
        if status:
            conditions.append("status = :status")
            params["status"] = status
        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(
                f"SELECT * FROM metaedu.datasets WHERE {where} ORDER BY sort_order, created_at DESC LIMIT :lim OFFSET :off"
            ),
            {**params, "lim": limit, "off": offset},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_by_id(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.datasets WHERE id = :did AND tenant_id = :tid"),
            {"did": dataset_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        description: str | None,
        source_file: str | None,
        tags: list[str],
        created_by: uuid.UUID,
    ) -> dict:
        dataset_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.datasets "
                "(id, tenant_id, name, description, source_file, tags, status, kg_status, row_count, sort_order, created_by, created_at, updated_at) "
                "VALUES (:id, :tid, :name, :desc, :sfile, :tags, 'uploaded', 'pending', 0, 0, :uid, :now, :now)"
            ),
            {
                "id": dataset_id,
                "tid": tenant_id,
                "name": name,
                "desc": description,
                "sfile": source_file,
                "tags": tags,
                "uid": created_by,
                "now": now,
            },
        )
        return {
            "id": dataset_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "source_file": source_file,
            "tags": tags,
            "status": "uploaded",
            "kg_status": "pending",
            "row_count": 0,
            "sort_order": 0,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

    async def update(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs: object) -> None:
        sets: list[str] = []
        params: dict = {"did": dataset_id, "tid": tenant_id}
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
                f"UPDATE metaedu.datasets SET {', '.join(sets)} WHERE id = :did AND tenant_id = :tid"
            ),
            params,
        )

    async def update_column_metadata(
        self,
        dataset_id: uuid.UUID,
        column_names: list[str],
        column_types: list[str],
        row_count: int,
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "UPDATE metaedu.datasets SET column_names = :cnames::jsonb, column_types = :ctypes::jsonb, "
                "row_count = :rcount, status = 'processed', updated_at = :now WHERE id = :did"
            ),
            {
                "cnames": json.dumps(column_names),
                "ctypes": json.dumps(column_types),
                "rcount": row_count,
                "now": now,
                "did": dataset_id,
            },
        )

    async def delete(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.datasets WHERE id = :did AND tenant_id = :tid"),
            {"did": dataset_id, "tid": tenant_id},
        )

    # --- Rows ---

    async def list_rows(
        self,
        dataset_id: uuid.UUID,
        tenant_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT * FROM metaedu.dataset_rows "
                "WHERE dataset_id = :did AND tenant_id = :tid ORDER BY row_index LIMIT :lim OFFSET :off"
            ),
            {"did": dataset_id, "tid": tenant_id, "lim": limit, "off": offset},
        )
        return [dict(row) for row in result.mappings().all()]

    async def count_rows(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.dataset_rows WHERE dataset_id = :did AND tenant_id = :tid"
            ),
            {"did": dataset_id, "tid": tenant_id},
        )
        return result.scalar() or 0

    async def bulk_insert_rows(
        self, tenant_id: uuid.UUID, dataset_id: uuid.UUID, rows: list[dict]
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        for i, row_data in enumerate(rows):
            row_id = uuid.uuid4()
            await self._session.execute(
                text(
                    "INSERT INTO metaedu.dataset_rows (id, tenant_id, dataset_id, row_index, data, created_at) "
                    "VALUES (:id, :tid, :did, :idx, :data::jsonb, :now)"
                ),
                {
                    "id": row_id,
                    "tid": tenant_id,
                    "did": dataset_id,
                    "idx": i,
                    "data": json.dumps(row_data),
                    "now": now,
                },
            )

    async def delete_rows(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.dataset_rows WHERE dataset_id = :did AND tenant_id = :tid"),
            {"did": dataset_id, "tid": tenant_id},
        )
