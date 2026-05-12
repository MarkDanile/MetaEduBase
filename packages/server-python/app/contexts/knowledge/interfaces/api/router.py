import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.dto import (
    KnowledgeNodeCreate,
    KnowledgeNodeDTO,
    KnowledgeNodeUpdate,
    KnowledgeSearchDTO,
    SearchResultDTO,
)

router = APIRouter()


def _row_to_dto(row: dict) -> KnowledgeNodeDTO:
    return KnowledgeNodeDTO(
        id=row["id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        description=row.get("description"),
        domain=row["domain"],
        level=row["level"],
        parent_id=row.get("parent_id"),
        path=row.get("path"),
        tags=row.get("tags", []),
        metadata=row.get("metadata", {}),
    )


@router.get("/nodes", response_model=list[KnowledgeNodeDTO])
async def list_knowledge_nodes(
    domain: str | None = None,
    parent_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    conditions = ["n.tenant_id = :tenant_id"]
    params: dict = {"tenant_id": tid, "offset_": offset, "limit_": limit}

    if domain:
        conditions.append("n.domain = :domain")
        params["domain"] = domain
    if parent_id:
        conditions.append("n.parent_id = :parent_id")
        params["parent_id"] = uuid.UUID(parent_id)
    else:
        conditions.append("n.parent_id IS NULL")

    where = " AND ".join(conditions)
    result = await session.execute(
        text(f"SELECT n.* FROM metaedu.knowledge_nodes n WHERE {where} ORDER BY n.created_at OFFSET :offset_ LIMIT :limit_"),
        params,
    )
    return [_row_to_dto(dict(row)) for row in result.mappings().all()]


@router.post("/nodes", response_model=KnowledgeNodeDTO, status_code=201)
async def create_knowledge_node(
    data: KnowledgeNodeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    node_id = uuid.uuid4()
    path = None

    if data.parent_id:
        parent_result = await session.execute(
            text("SELECT path FROM metaedu.knowledge_nodes WHERE id = :pid AND tenant_id = :tid"),
            {"pid": data.parent_id, "tid": tid},
        )
        parent_path = parent_result.scalar_one_or_none()
        if parent_path is None:
            raise HTTPException(status_code=404, detail="父节点不存在")
        path = f"{parent_path}.{str(node_id)[:8]}" if parent_path else str(node_id)[:8]
    else:
        path = str(node_id)[:8]

    import json
    from datetime import datetime
    from app.contexts.knowledge.application.embedding_service import get_embedding

    now = datetime.utcnow()

    embed_text = f"{data.title}"
    if data.description:
        embed_text += f" {data.description}"
    embedding = await get_embedding(embed_text)

    if embedding is not None:
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        await session.execute(
            text(
                "INSERT INTO metaedu.knowledge_nodes "
                "(id, tenant_id, title, description, domain, level, parent_id, path, tags, metadata, embedding, created_at, updated_at) "
                "VALUES (:id, :tid, :title, :desc, :domain, :level, :pid, :path, :tags, :meta, :vec::vector, :now, :now)"
            ),
            {
                "id": node_id,
                "tid": tid,
                "title": data.title,
                "desc": data.description,
                "domain": str(data.domain.value) if hasattr(data.domain, 'value') else str(data.domain),
                "level": str(data.level.value) if hasattr(data.level, 'value') else str(data.level),
                "pid": data.parent_id,
                "path": path,
                "tags": json.dumps(data.tags),
                "meta": json.dumps(data.metadata),
                "vec": vec_str,
                "now": now,
            },
        )
    else:
        await session.execute(
            text(
                "INSERT INTO metaedu.knowledge_nodes "
                "(id, tenant_id, title, description, domain, level, parent_id, path, tags, metadata, created_at, updated_at) "
                "VALUES (:id, :tid, :title, :desc, :domain, :level, :pid, :path, :tags, :meta, :now, :now)"
            ),
            {
                "id": node_id,
                "tid": tid,
                "title": data.title,
                "desc": data.description,
                "domain": str(data.domain.value) if hasattr(data.domain, 'value') else str(data.domain),
                "level": str(data.level.value) if hasattr(data.level, 'value') else str(data.level),
                "pid": data.parent_id,
                "path": path,
                "tags": json.dumps(data.tags),
                "meta": json.dumps(data.metadata),
                "now": now,
            },
        )

    result = await session.execute(
        text("SELECT * FROM metaedu.knowledge_nodes WHERE id = :id"),
        {"id": node_id},
    )
    return _row_to_dto(dict(result.mappings().first()))


@router.get("/nodes/{node_id}", response_model=KnowledgeNodeDTO)
async def get_knowledge_node(
    node_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    result = await session.execute(
        text("SELECT * FROM metaedu.knowledge_nodes WHERE id = :id AND tenant_id = :tid"),
        {"id": uuid.UUID(node_id), "tid": tid},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="知识节点不存在")
    return _row_to_dto(dict(row))


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeDTO)
async def update_knowledge_node(
    node_id: str,
    data: KnowledgeNodeUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    uid = uuid.UUID(node_id)

    existing = await session.execute(
        text("SELECT * FROM metaedu.knowledge_nodes WHERE id = :id AND tenant_id = :tid"),
        {"id": uid, "tid": tid},
    )
    if existing.mappings().first() is None:
        raise HTTPException(status_code=404, detail="知识节点不存在")

    updates = []
    params: dict = {"id": uid, "tid": tid}
    if data.title is not None:
        updates.append("title = :title")
        params["title"] = data.title
    if data.description is not None:
        updates.append("description = :desc")
        params["desc"] = data.description
    if data.tags is not None:
        updates.append("tags = :tags")
        params["tags"] = str(data.tags).replace("'", '"')
    if data.metadata is not None:
        updates.append("metadata = :meta")
        params["meta"] = str(data.metadata).replace("'", '"')

    if updates:
        set_clause = ", ".join(updates)
        await session.execute(
            text(f"UPDATE metaedu.knowledge_nodes SET {set_clause} WHERE id = :id AND tenant_id = :tid"),
            params,
        )

    result = await session.execute(
        text("SELECT * FROM metaedu.knowledge_nodes WHERE id = :id"),
        {"id": uid},
    )
    return _row_to_dto(dict(result.mappings().first()))


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_knowledge_node(
    node_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    result = await session.execute(
        text("DELETE FROM metaedu.knowledge_nodes WHERE id = :id AND tenant_id = :tid"),
        {"id": uuid.UUID(node_id), "tid": tid},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="知识节点不存在")


@router.post("/search", response_model=list[SearchResultDTO])
async def search_knowledge(
    data: KnowledgeSearchDTO,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    from app.contexts.knowledge.application.embedding_service import get_embedding

    tid = get_tenant_id()
    search_mode = data.search_mode or "hybrid"
    top_k = data.top_k or 5

    embedding = await get_embedding(data.query)

    if embedding and search_mode in ("semantic", "hybrid"):
        import json as _json

        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        conditions = ["n.tenant_id = :tid", "n.embedding IS NOT NULL"]
        params: dict = {"tid": tid, "vec": vec_str, "lim": top_k}

        if data.domain:
            conditions.append("n.domain = :domain")
            params["domain"] = data.domain

        where = " AND ".join(conditions)
        result = await session.execute(
            text(
                f"SELECT n.*, 1 - (n.embedding <=> :vec::vector) AS score "
                f"FROM metaedu.knowledge_nodes n WHERE {where} "
                f"ORDER BY n.embedding <=> :vec::vector LIMIT :lim"
            ),
            params,
        )
        rows = result.mappings().all()
        if rows:
            return [SearchResultDTO(node=_row_to_dto(dict(r)), score=float(r["score"])) for r in rows]

    conditions = ["n.tenant_id = :tid"]
    params = {"tid": tid, "query": f"%{data.query}%", "lim": top_k}

    if data.domain:
        conditions.append("n.domain = :domain")
        params["domain"] = data.domain

    where = " AND ".join(conditions)
    result = await session.execute(
        text(
            f"SELECT n.* FROM metaedu.knowledge_nodes n "
            f"WHERE {where} AND (n.title ILIKE :query OR COALESCE(n.description, '') ILIKE :query) "
            f"ORDER BY n.created_at LIMIT :lim"
        ),
        params,
    )
    rows = result.mappings().all()
    return [SearchResultDTO(node=_row_to_dto(dict(r)), score=1.0) for r in rows]


@router.get("/tree/{parent_id}", response_model=list[KnowledgeNodeDTO])
async def get_knowledge_tree(
    parent_id: str,
    depth: int = Query(default=2, ge=1, le=5),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()

    if parent_id == "root":
        result = await session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND parent_id IS NULL "
                "ORDER BY domain, level, created_at LIMIT 100"
            ),
            {"tid": tid},
        )
    else:
        node_result = await session.execute(
            text("SELECT path FROM metaedu.knowledge_nodes WHERE id = :pid AND tenant_id = :tid"),
            {"pid": uuid.UUID(parent_id), "tid": tid},
        )
        path = node_result.scalar_one_or_none()
        if path is None:
            raise HTTPException(status_code=404, detail="节点不存在")

        result = await session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND path LIKE :path_prefix "
                "ORDER BY level, created_at LIMIT 100"
            ),
            {"tid": tid, "path_prefix": f"{path}%"},
        )

    return [_row_to_dto(dict(row)) for row in result.mappings().all()]
