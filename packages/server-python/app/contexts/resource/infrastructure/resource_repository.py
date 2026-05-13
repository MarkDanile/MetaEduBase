import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(
        self,
        tenant_id: uuid.UUID,
        *,
        resource_type: str | None = None,
        domain: str | None = None,
    ) -> int:
        conditions = ["r.tenant_id = :tid", "r.is_deleted = false"]
        params: dict = {"tid": tenant_id}

        if resource_type:
            conditions.append("r.resource_type = :rtype")
            params["rtype"] = resource_type
        if domain:
            conditions.append("r.domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(f"SELECT count(*) FROM metaedu.resources r WHERE {where}"),
            params,
        )
        return result.scalar_one()

    async def list_resources(
        self,
        tenant_id: uuid.UUID,
        *,
        resource_type: str | None = None,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["r.tenant_id = :tid", "r.is_deleted = false"]
        params: dict = {"tid": tenant_id, "limit": limit, "offset": offset}

        if resource_type:
            conditions.append("r.resource_type = :rtype")
            params["rtype"] = resource_type
        if domain:
            conditions.append("r.domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(
                f"SELECT r.id, r.tenant_id, r.title, r.description, "
                f"r.resource_type, r.status, r.domain, r.file_size, "
                f"r.file_type, r.storage_key, r.knowledge_point_ids, "
                f"r.uploaded_by, r.created_at, r.updated_at "
                f"FROM metaedu.resources r WHERE {where} "
                f"ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        return [dict(row) for row in result.mappings().all()]

    async def create(
        self,
        *,
        resource_id: uuid.UUID,
        tenant_id: uuid.UUID,
        title: str,
        description: str | None,
        resource_type: str,
        domain: str | None,
        knowledge_point_ids: list[uuid.UUID] | None,
        file_size: int,
        file_type: str,
        storage_key: str,
        uploaded_by: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.resources "
                "(id, tenant_id, title, description, resource_type, status, domain, "
                "knowledge_point_ids, file_size, file_type, storage_key, metadata, "
                "uploaded_by, is_deleted, created_at, updated_at) "
                "VALUES (:id, :tid, :title, :desc, :rtype, 'uploaded', :domain, "
                ":kp_ids, :fsize, :ftype, :skey, '{}', :uid, false, :now, :now)"
            ),
            {
                "id": resource_id,
                "tid": tenant_id,
                "title": title,
                "desc": description,
                "rtype": resource_type,
                "domain": domain,
                "kp_ids": knowledge_point_ids if knowledge_point_ids else None,
                "fsize": file_size,
                "ftype": file_type,
                "skey": storage_key,
                "uid": uploaded_by,
                "now": now,
            },
        )

    async def get_by_id_and_tenant(
        self,
        resource_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        result = await self._session.execute(
            text(
                "SELECT r.id, r.tenant_id, r.title, r.description, "
                "r.resource_type, r.status, r.domain, r.file_size, "
                "r.file_type, r.storage_key, r.knowledge_point_ids, "
                "r.uploaded_by, r.is_deleted, r.created_at, r.updated_at "
                "FROM metaedu.resources r WHERE r.id = :rid AND r.tenant_id = :tid"
            ),
            {"rid": resource_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_storage_info(
        self,
        resource_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict | None:
        result = await self._session.execute(
            text(
                "SELECT storage_key, title, file_type FROM metaedu.resources "
                "WHERE id = :rid AND tenant_id = :tid AND is_deleted = false"
            ),
            {"rid": resource_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def soft_delete(
        self,
        resource_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> int:
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await self._session.execute(
            text(
                "UPDATE metaedu.resources SET is_deleted = true, updated_at = :now "
                "WHERE id = :rid AND tenant_id = :tid AND is_deleted = false"
            ),
            {"rid": resource_id, "tid": tenant_id, "now": now},
        )
        return result.rowcount
