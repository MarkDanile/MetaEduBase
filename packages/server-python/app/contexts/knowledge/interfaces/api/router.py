import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.dto import (
    KnowledgeEdgeDTO,
    KnowledgeNodeCreate,
    KnowledgeNodeDTO,
    KnowledgeNodeUpdate,
    KnowledgeSearchDTO,
    SearchResultDTO,
)
from app.contexts.knowledge.application.embedding_service import get_embedding
from app.contexts.knowledge.infrastructure.knowledge_repository import (
    KnowledgeNodeRepository,
)
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter()


_VALID_DOMAINS = {
    "electronics_info",
    "smart_manufacturing",
    "finance_commerce",
    "medical_health",
    "education_sports",
    "civil_engineering",
    "transportation",
    "agriculture",
    "art_design",
    "public_service",
}
_VALID_LEVELS = {
    "professional",
    "course",
    "chapter",
    "knowledge_point",
    "skill_point",
    "operation_step",
}


def _row_to_dto(row: dict) -> KnowledgeNodeDTO:
    domain = row["domain"]
    level = row["level"]
    # Map unknown values to defaults (LLM-extracted nodes may use arbitrary names)
    if domain not in _VALID_DOMAINS:
        domain = "education_sports"
    if level not in _VALID_LEVELS:
        level = "knowledge_point"
    return KnowledgeNodeDTO(
        id=row["id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        description=row.get("description"),
        domain=domain,
        level=level,
        parent_id=row.get("parent_id"),
        path=row.get("path"),
        tags=row.get("tags", []),
        metadata=row.get("metadata", {}),
    )


@router.get("/edges", response_model=list[KnowledgeEdgeDTO])
async def list_knowledge_edges(
    source_file_id: str | None = None,
    source_dataset_id: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    if source_file_id:
        rows = await repo.list_edges_by_file(tid, uuid.UUID(source_file_id))
    elif source_dataset_id:
        rows = await repo.list_edges_by_dataset(tid, uuid.UUID(source_dataset_id))
    else:
        rows = []
    return [
        KnowledgeEdgeDTO(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            weight=row["weight"],
            metadata=row.get("metadata", {}),
        )
        for row in rows
    ]


@router.get("/nodes", response_model=list[KnowledgeNodeDTO])
async def list_knowledge_nodes(
    domain: str | None = None,
    parent_id: str | None = None,
    source_file_id: str | None = None,
    source_dataset_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    rows = await repo.list_nodes(
        tid,
        domain=domain,
        parent_id=uuid.UUID(parent_id) if parent_id else None,
        source_file_id=uuid.UUID(source_file_id) if source_file_id else None,
        source_dataset_id=uuid.UUID(source_dataset_id) if source_dataset_id else None,
        offset=offset,
        limit=limit,
    )
    return [_row_to_dto(r) for r in rows]


@router.post("/nodes", response_model=KnowledgeNodeDTO, status_code=201)
async def create_knowledge_node(
    data: KnowledgeNodeCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    node_id = uuid.uuid4()
    path = None

    if data.parent_id:
        parent_path = await repo.get_path(data.parent_id, tid)
        if parent_path is None:
            raise HTTPException(status_code=404, detail="父节点不存在")
        path = f"{parent_path}.{str(node_id)[:8]}" if parent_path else str(node_id)[:8]
    else:
        path = str(node_id)[:8]

    embed_text = data.title
    if data.description:
        embed_text += f" {data.description}"
    embedding = await get_embedding(embed_text)

    vec_str = None
    if embedding is not None:
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

    domain_val = str(data.domain.value) if hasattr(data.domain, "value") else str(data.domain)
    level_val = str(data.level.value) if hasattr(data.level, "value") else str(data.level)

    await repo.create_node(
        node_id=node_id,
        tenant_id=tid,
        title=data.title,
        description=data.description,
        domain=domain_val,
        level=level_val,
        parent_id=data.parent_id,
        path=path,
        tags=data.tags,
        metadata=data.metadata,
        vec_str=vec_str,
    )

    row = await repo.get_by_id(node_id)
    return _row_to_dto(row)


@router.get("/nodes/{node_id}", response_model=KnowledgeNodeDTO)
async def get_knowledge_node(
    node_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    row = await repo.get_by_id_and_tenant(uuid.UUID(node_id), tid)
    if row is None:
        raise HTTPException(status_code=404, detail="知识节点不存在")
    return _row_to_dto(row)


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeDTO)
async def update_knowledge_node(
    node_id: str,
    data: KnowledgeNodeUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    uid = uuid.UUID(node_id)
    repo = KnowledgeNodeRepository(session)

    existing = await repo.get_by_id_and_tenant(uid, tid)
    if existing is None:
        raise HTTPException(status_code=404, detail="知识节点不存在")

    await repo.update_node(
        uid,
        tid,
        title=data.title,
        description=data.description,
        tags=data.tags,
        metadata=data.metadata,
    )

    row = await repo.get_by_id(uid)
    return _row_to_dto(row)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_knowledge_node(
    node_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    nid = uuid.UUID(node_id)
    repo = KnowledgeNodeRepository(session)

    if not await repo.exists_by_id_and_tenant(nid, tid):
        raise HTTPException(status_code=404, detail="知识节点不存在")

    await repo.delete_cascade(nid, tid)


@router.post("/search", response_model=list[SearchResultDTO])
async def search_knowledge(
    data: KnowledgeSearchDTO,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    search_mode = data.search_mode or "hybrid"
    top_k = data.top_k or 5

    embedding = await get_embedding(data.query)

    if embedding and search_mode in ("semantic", "hybrid"):
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        rows = await repo.search_semantic(tid, vec_str, top_k=top_k, domain=data.domain)
        if rows:
            return [SearchResultDTO(node=_row_to_dto(r), score=float(r["score"])) for r in rows]

    rows = await repo.search_keyword(
        tid,
        f"%{data.query}%",
        top_k=top_k,
        domain=data.domain,
    )
    return [SearchResultDTO(node=_row_to_dto(r), score=1.0) for r in rows]


@router.get("/tree/{parent_id}", response_model=list[KnowledgeNodeDTO])
async def get_knowledge_tree(
    parent_id: str,
    depth: int = Query(default=2, ge=1, le=5),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)

    if parent_id == "root":
        rows = await repo.get_tree_root(tid)
    else:
        node_path = await repo.get_path(uuid.UUID(parent_id), tid)
        if node_path is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        rows = await repo.get_tree_by_path(tid, node_path)

    return [_row_to_dto(r) for r in rows]
