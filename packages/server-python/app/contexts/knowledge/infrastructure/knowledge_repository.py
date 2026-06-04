import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeNodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_nodes(
        self,
        tenant_id: uuid.UUID,
        *,
        domain: str | None = None,
        parent_id: uuid.UUID | None = None,
        source_file_id: uuid.UUID | None = None,
        source_dataset_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        conditions = ["n.tenant_id = :tid"]
        params: dict = {"tid": tenant_id, "offset_": offset, "limit_": limit}

        if domain:
            conditions.append("n.domain = :domain")
            params["domain"] = domain
        if parent_id is not None:
            if parent_id:
                conditions.append("n.parent_id = :pid")
                params["pid"] = parent_id
            else:
                conditions.append("n.parent_id IS NULL")
        if source_file_id:
            conditions.append("n.source_file_id = :sfid")
            params["sfid"] = source_file_id
        if source_dataset_id:
            conditions.append("n.source_dataset_id = :sdid")
            params["sdid"] = source_dataset_id

        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(
                f"SELECT n.* FROM metaedu.knowledge_nodes n "
                f"WHERE {where} ORDER BY n.created_at OFFSET :offset_ LIMIT :limit_"
            ),
            params,
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_path(self, node_id: uuid.UUID, tenant_id: uuid.UUID) -> str | None:
        result = await self._session.execute(
            text(
                "SELECT path FROM metaedu.knowledge_nodes "
                "WHERE id = :pid AND tenant_id = :tid"
            ),
            {"pid": node_id, "tid": tenant_id},
        )
        return result.scalar_one_or_none()

    async def create_node(
        self,
        *,
        node_id: uuid.UUID,
        tenant_id: uuid.UUID,
        title: str,
        description: str | None,
        domain: str,
        level: str,
        parent_id: uuid.UUID | None,
        path: str | None,
        tags: list,
        metadata: dict,
        vec_str: str | None = None,
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        base_params = {
            "id": node_id,
            "tid": tenant_id,
            "title": title,
            "desc": description,
            "domain": domain,
            "level": level,
            "pid": parent_id,
            "path": path,
            "tags": json.dumps(tags),
            "meta": json.dumps(metadata),
            "now": now,
        }

        if vec_str is not None:
            await self._session.execute(
                text(
                    "INSERT INTO metaedu.knowledge_nodes "
                    "(id, tenant_id, title, description, domain, level, "
                    "parent_id, path, tags, metadata, embedding, created_at, updated_at) "
                    "VALUES (:id, :tid, :title, :desc, :domain, :level, "
                    ":pid, :path, :tags, :meta, :vec::vector, :now, :now)"
                ),
                {**base_params, "vec": vec_str},
            )
        else:
            await self._session.execute(
                text(
                    "INSERT INTO metaedu.knowledge_nodes "
                    "(id, tenant_id, title, description, domain, level, "
                    "parent_id, path, tags, metadata, created_at, updated_at) "
                    "VALUES (:id, :tid, :title, :desc, :domain, :level, "
                    ":pid, :path, :tags, :meta, :now, :now)"
                ),
                base_params,
            )

    async def get_by_id(self, node_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.knowledge_nodes WHERE id = :id"),
            {"id": node_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_id_and_tenant(
        self, node_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict | None:
        result = await self._session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": node_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def exists_by_id_and_tenant(
        self, node_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> bool:
        result = await self._session.execute(
            text(
                "SELECT id FROM metaedu.knowledge_nodes "
                "WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": node_id, "tid": tenant_id},
        )
        return result.scalar_one_or_none() is not None

    async def update_node(
        self,
        node_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list | None = None,
        metadata: dict | None = None,
    ) -> None:
        updates: list[str] = []
        params: dict = {"id": node_id, "tid": tenant_id}

        if title is not None:
            updates.append("title = :title")
            params["title"] = title
        if description is not None:
            updates.append("description = :desc")
            params["desc"] = description
        if tags is not None:
            updates.append("tags = :tags")
            params["tags"] = json.dumps(tags)
        if metadata is not None:
            updates.append("metadata = :meta")
            params["meta"] = json.dumps(metadata)

        if not updates:
            return

        set_clause = ", ".join(updates)
        await self._session.execute(
            text(
                f"UPDATE metaedu.knowledge_nodes "
                f"SET {set_clause} WHERE id = :id AND tenant_id = :tid"
            ),
            params,
        )

    async def delete_cascade(self, node_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_edges "
                "WHERE (source_id = :nid OR target_id = :nid) AND tenant_id = :tid"
            ),
            {"nid": node_id, "tid": tenant_id},
        )
        await self._session.execute(
            text(
                "UPDATE metaedu.resources SET is_deleted = true, updated_at = :now "
                "WHERE tenant_id = :tid AND is_deleted = false "
                "AND knowledge_point_ids @> ARRAY[:nid]::uuid[]"
            ),
            {"nid": node_id, "tid": tenant_id, "now": datetime.now(UTC).replace(tzinfo=None)},
        )
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_nodes "
                "WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": node_id, "tid": tenant_id},
        )

    async def delete_cascade_by_source_file(
        self, tenant_id: uuid.UUID, source_file_id: uuid.UUID
    ) -> None:
        """Delete all knowledge edges then nodes associated with a source file.

        Order: edges first (RESTRICT FK), then nodes.
        """
        # 1. Delete edges where source or target node belongs to this file
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_edges WHERE source_id IN "
                "(SELECT id FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_file_id = :fid) "
                "OR target_id IN "
                "(SELECT id FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_file_id = :fid)"
            ),
            {"tid": tenant_id, "fid": source_file_id},
        )
        # 2. Delete nodes
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_file_id = :fid"
            ),
            {"tid": tenant_id, "fid": source_file_id},
        )

    async def delete_cascade_by_source_dataset(
        self, tenant_id: uuid.UUID, source_dataset_id: uuid.UUID
    ) -> None:
        """Delete all knowledge edges then nodes associated with a source dataset.

        Order: edges first (RESTRICT FK), then nodes.
        """
        # 1. Delete edges where source or target node belongs to this dataset
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_edges WHERE source_id IN "
                "(SELECT id FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_dataset_id = :did) "
                "OR target_id IN "
                "(SELECT id FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_dataset_id = :did)"
            ),
            {"tid": tenant_id, "did": source_dataset_id},
        )
        # 2. Delete nodes
        await self._session.execute(
            text(
                "DELETE FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_dataset_id = :did"
            ),
            {"tid": tenant_id, "did": source_dataset_id},
        )

    async def search_semantic(
        self,
        tenant_id: uuid.UUID,
        vec_str: str,
        *,
        top_k: int = 5,
        domain: str | None = None,
    ) -> list[dict]:
        conditions = ["n.tenant_id = :tid", "n.embedding IS NOT NULL"]
        params: dict = {"tid": tenant_id, "vec": vec_str, "lim": top_k}

        if domain:
            conditions.append("n.domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(
                f"SELECT n.*, 1 - (n.embedding <=> :vec::vector) AS score "
                f"FROM metaedu.knowledge_nodes n WHERE {where} "
                f"ORDER BY n.embedding <=> :vec::vector LIMIT :lim"
            ),
            params,
        )
        return [dict(row) for row in result.mappings().all()]

    async def search_keyword(
        self,
        tenant_id: uuid.UUID,
        query_pattern: str,
        *,
        top_k: int = 5,
        domain: str | None = None,
    ) -> list[dict]:
        conditions = ["n.tenant_id = :tid"]
        params: dict = {"tid": tenant_id, "query": query_pattern, "lim": top_k}

        if domain:
            conditions.append("n.domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(
                f"SELECT n.* FROM metaedu.knowledge_nodes n "
                f"WHERE {where} AND "
                f"(n.title ILIKE :query OR COALESCE(n.description, '') ILIKE :query) "
                f"ORDER BY n.created_at LIMIT :lim"
            ),
            params,
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_tree_root(self, tenant_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND parent_id IS NULL "
                "ORDER BY domain, level, created_at LIMIT 100"
            ),
            {"tid": tenant_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_tree_by_path(self, tenant_id: uuid.UUID, path_prefix: str) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND path LIKE :prefix "
                "ORDER BY level, created_at LIMIT 100"
            ),
            {"tid": tenant_id, "prefix": f"{path_prefix}%"},
        )
        return [dict(row) for row in result.mappings().all()]

    async def list_edges_by_file(self, tenant_id: uuid.UUID, source_file_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT DISTINCT ke.* FROM metaedu.knowledge_edges ke "
                "JOIN metaedu.knowledge_nodes kn_src ON ke.source_id = kn_src.id "
                "JOIN metaedu.knowledge_nodes kn_tgt ON ke.target_id = kn_tgt.id "
                "WHERE ke.tenant_id = :tid "
                "AND (kn_src.source_file_id = :sfid OR kn_tgt.source_file_id = :sfid)"
            ),
            {"tid": tenant_id, "sfid": source_file_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def list_edges_by_dataset(self, tenant_id: uuid.UUID, source_dataset_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT DISTINCT ke.* FROM metaedu.knowledge_edges ke "
                "JOIN metaedu.knowledge_nodes kn_src ON ke.source_id = kn_src.id "
                "JOIN metaedu.knowledge_nodes kn_tgt ON ke.target_id = kn_tgt.id "
                "WHERE ke.tenant_id = :tid "
                "AND (kn_src.source_dataset_id = :sdid OR kn_tgt.source_dataset_id = :sdid)"
            ),
            {"tid": tenant_id, "sdid": source_dataset_id},
        )
        return [dict(row) for row in result.mappings().all()]
