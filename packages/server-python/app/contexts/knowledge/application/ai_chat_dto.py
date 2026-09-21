"""TD-085 Slice B — AI Chat 请求/响应 DTO 与证据 DTO 装配（knowledge 保留）。

从 ``ai_chat_service.py`` 按需拆出（spec ADR-085-2 DTO 行）：

- 公共契约 DTO：``ChatRequest`` / ``ChatResponse``（逐字迁移；
  ``ai_chat_service`` 模块继续 re-export，既有导入路径不变）。
- 工具 schema DTO：``QUERY_INTERNAL_DATA_TOOL``（REQ-052 Task 7 /
  REQ-056 Task 3 的 query_internal_data JSON Schema 字典；
  ``AIChatService._QUERY_INTERNAL_DATA_TOOL`` 类属性继续指向同一对象）。
- ``query_internal_data`` 工具业务执行：``dispatch_query_internal_data``
  （SemanticModel 双键/单键解析 + QueryService.ask + 降级 payload；
  仓储工厂与 QueryService 经参数注入，runtime 侧不携带该业务语义）。
- 证据 DTO 装配：``hydrate_graph_chunks``（graph 证据回填 chunk 正文）、
  ``build_document_sources``（响应用 DocumentSource 装配）、
  ``build_fallback_packed``（未注入 ContextPacker 时的最小 PackedContext）。

行为保持：所有函数体从 ``AIChatService`` 方法逐字迁移，SQL、参数绑定、
降级分支与排序规则不变。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.context_packer import (
    PackedContext,
    PackedContextBlock,
    PackedContextDiagnostics,
)
from app.contexts.knowledge.domain.evidence import (
    DocumentSource,
    DocumentSourceChunk,
    EvidenceItem,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatRequest:
    message: str
    context_window: int = 5


@dataclass
class ChatResponse:
    reply: str
    sources: list[EvidenceItem] = field(default_factory=list)
    document_sources: list[DocumentSource] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


# REQ-052 Task 7 — tool definition for ``query_internal_data``.
# REQ-056 Task 3 — ``catalog_id`` added so the LLM can route by catalog.
# When the LLM fills this field, AI Chat resolves the SemanticModel via
# ``get_active_by_catalog_and_entity_type`` (dual-key) so multi-catalog
# tenants don't accidentally hit the wrong ``bill``/``contract`` model.
# When omitted, AI Chat falls back to ``get_active_by_entity_type`` (V1
# legacy behavior — REQ-052 Task 7 path).
QUERY_INTERNAL_DATA_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_internal_data",
        "description": (
            "查询内部结构化业务数据（账单/合同/工单/租约/客户等）。"
            "当用户问金额、数量、统计、列表、明细等结构化数据问题时调用。"
            "若用户的问题明显属于某个数据库（catalog），必须把对应的 "
            "catalog_id 填到 catalog_id 参数；未指定时由系统按 entity_hint "
            "单键路由（可能命中错的 catalog）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "自然语言问题（包含具体想问的指标 / 时间范围 / 过滤条件）",
                },
                "entity_hint": {
                    "type": "string",
                    "enum": ["bill", "contract", "ticket", "lease", "customer"],
                    "description": "可选 — 实体类型提示；不填时由 QueryService 自动归类",
                },
                # REQ-056 Task 3 — catalog routing key. LLM fills this when
                # the user's question is scoped to a specific catalog
                # (e.g. "园区欠费" → park catalog). String form so the
                # model can emit it verbatim; the service parses to UUID
                # before calling the repository.
                "catalog_id": {
                    "type": "string",
                    "description": (
                        "数据库（catalog）的 UUID；不填时按 entity_hint 单键路由。"
                        "多 catalog 场景强烈建议填写，避免命中错误 schema。"
                    ),
                },
            },
            "required": ["question"],
        },
    },
}


def metadata_int(item: EvidenceItem, key: str) -> int | None:
    value = (item.metadata or {}).get(key)
    return value if isinstance(value, int) else None


def build_fallback_packed(
    fused: list[EvidenceItem],
    channel_top_k: dict[str, int],
) -> PackedContext:
    """No-packer 兼容路径：构造最小 PackedContext 供 prompt 段渲染。"""
    return PackedContext(
        blocks=[
            PackedContextBlock(
                evidence_index=i + 1,
                file_id=ev.file_id,
                chunk_ids=[ev.chunk_id] if ev.chunk_id else [],
                source_type=ev.source_type,
                title=ev.title or "",
                section_title=ev.metadata.get("section_title"),
                section_path=ev.metadata.get("section_path"),
                content=ev.content or ev.snippet or "",
                channels=ev.channels,
                score=ev.score,
                is_toc_like=False,
                expansion_type="hit",
            )
            for i, ev in enumerate(fused)
        ],
        evidence=fused,
        diagnostics=PackedContextDiagnostics(
            fused_count=len(fused),
            channel_top_k=channel_top_k,
        ),
    )


async def dispatch_query_internal_data(
    arguments: dict[str, Any],
    *,
    semantic_model_repository_factory: Any,
    query_service: Any | None,
    session: AsyncSession,
    tenant_id: str,
    user_id: uuid.UUID | None,
    role: str,
    message: str,
) -> dict[str, Any]:
    """REQ-052 Task 7 — execute the ``query_internal_data`` tool.

    Resolves the ``SemanticModel`` (REQ-056 Task 3 dual-key when the LLM
    filled ``catalog_id``) and calls ``QueryService.ask``; the audit log
    row is written inside ``QueryService.ask`` (REQ-052 §12). All failure
    modes degrade to a payload dict instead of raising so the chat flow
    always reaches the second LLM call. ``semantic_model_repository_factory``
    / ``query_service`` are injected by the caller (knowledge composition),
    keeping runtime free of this business Query semantics.
    """
    # ---- Resolve SemanticModel from entity_hint ----
    entity_hint = arguments.get("entity_hint") or "bill"
    question = arguments.get("question") or message

    # REQ-056 Task 3 — resolve catalog_id from the LLM-filled
    # tool argument. The LLM emits a string UUID; we defensively
    # parse to ``uuid.UUID`` so a malformed value degrades to the
    # legacy single-key path rather than crashing the chat.
    catalog_id_arg = arguments.get("catalog_id")
    resolved_catalog_id: uuid.UUID | None = None
    if catalog_id_arg:
        try:
            resolved_catalog_id = uuid.UUID(str(catalog_id_arg))
        except (TypeError, ValueError):
            logger.warning(
                "ai_chat_service: invalid catalog_id=%r from "
                "tool_call arguments; falling back to "
                "entity_type-only routing.",
                catalog_id_arg,
            )
            resolved_catalog_id = None

    # Resolve the SemanticModel via the injected repository factory
    # (production wires ``SemanticModelRepository(session)`` via
    # ``ai_router._build_evidence_service``; tests inject a fake).
    semantic_repo = semantic_model_repository_factory(session)
    tenant_uuid = (
        uuid.UUID(str(tenant_id))
        if not isinstance(tenant_id, uuid.UUID)
        else tenant_id
    )
    if resolved_catalog_id is not None:
        # Dual-key routing — REQ-054 catalog-scoped lookup. Safe
        # even when a tenant has multiple catalogs with the same
        # ``entity_type`` registered.
        semantic_model = (
            await semantic_repo.get_active_by_catalog_and_entity_type(
                tenant_id=tenant_uuid,
                catalog_id=resolved_catalog_id,
                entity_type=entity_hint,
            )
        )
    else:
        # Legacy single-key fallback — REQ-052 Task 7 path. Kept
        # for V1 backward compat: small/old models that don't
        # know the ``catalog_id`` field, and tenants without
        # multi-catalog schemas.
        semantic_model = await semantic_repo.get_active_by_entity_type(
            tenant_id=tenant_uuid, entity_type=entity_hint
        )

    if semantic_model is None:
        # No semantic model registered for this entity_hint —
        # degrade gracefully to a textual apology so the user
        # doesn't see a raw stack trace.
        logger.warning(
            "ai_chat_service: no semantic_model for entity_hint=%r "
            "(tenant=%s); skipping QueryService.ask.",
            entity_hint,
            tenant_uuid,
        )
        return {
            "ok": False,
            "errors": [
                f"entity_type '{entity_hint}' not configured for tenant"
            ],
            "suggestion": "请尝试更具体的问题。",
        }

    # ---- Call QueryService.ask (writes audit row) ----
    if query_service is None:
        # Production path: QueryService is built at lifespan
        # startup and bound to the request session. The router
        # is responsible for injecting it; if it's missing
        # here we degrade to a no-data reply rather than
        # crashing the chat.
        logger.warning(
            "ai_chat_service: query_service not injected; "
            "skipping tool execution."
        )
        return {
            "ok": False,
            "errors": ["query_service not available"],
            "suggestion": "请稍后重试。",
        }
    effective_user_id = user_id or uuid.uuid4()
    return await query_service.ask(
        question=question,
        semantic_model=semantic_model,
        user_id=effective_user_id,
        tenant_id=tenant_uuid,
        role=role,
        business_purpose=(
            f"AI Chat 工具调用 — question={question[:80]}"
        ),
    )


async def hydrate_graph_chunks(
    fused: list[EvidenceItem],
    tenant_id: str,
    session: AsyncSession,
) -> list[EvidenceItem]:
    """Graph 证据回填 chunk 正文（knowledge_node / knowledge_edge）。"""
    chunk_ids = {
        item.source_chunk_id or item.chunk_id
        for item in fused
        if item.source_type in {"knowledge_node", "knowledge_edge"}
        and (item.source_chunk_id is not None or item.chunk_id is not None)
    }
    if not chunk_ids:
        return fused

    placeholders = ", ".join(f":c{i}" for i in range(len(chunk_ids)))
    params: dict[str, Any] = {"tid": tenant_id}
    for i, cid in enumerate(chunk_ids):
        params[f"c{i}"] = cid

    try:
        result = await session.execute(
            text(
                "SELECT id, file_id, chunk_index, content, section_title, section_path "
                "FROM metaedu.document_chunks "
                f"WHERE tenant_id = :tid AND id IN ({placeholders})"
            ),
            params,
        )
        chunks = {row["id"]: row for row in result.mappings().all()}
    except Exception as e:  # noqa: BLE001
        logger.warning("graph chunk hydration failed: %s", e)
        return fused

    hydrated: list[EvidenceItem] = []
    for item in fused:
        chunk_id = item.source_chunk_id or item.chunk_id
        chunk = chunks.get(chunk_id) if chunk_id is not None else None
        if item.source_type not in {"knowledge_node", "knowledge_edge"} or chunk is None:
            hydrated.append(item)
            continue

        updated = item.model_copy(deep=True)
        content = chunk["content"] or updated.content
        updated.file_id = updated.file_id or chunk["file_id"]
        updated.chunk_id = chunk["id"]
        updated.source_chunk_id = chunk["id"]
        updated.content = content
        updated.snippet = content[:500]
        updated.metadata = {
            **(updated.metadata or {}),
            "chunk_index": chunk["chunk_index"],
            "section_title": chunk["section_title"],
            "section_path": chunk["section_path"],
            "content_source": "document_chunk",
        }
        hydrated.append(updated)
    return hydrated


async def build_document_sources(
    fused: list[EvidenceItem],
    tenant_id: str,
    session: AsyncSession,
) -> list[DocumentSource]:
    """装配响应用 DocumentSource 列表（按 file 分组 + best_score 排序）。"""
    file_ids = {item.file_id for item in fused if item.file_id is not None}
    if not file_ids:
        return []

    placeholders = ", ".join(f":f{i}" for i in range(len(file_ids)))
    params: dict[str, Any] = {"tid": tenant_id}
    for i, fid in enumerate(file_ids):
        params[f"f{i}"] = fid

    try:
        result = await session.execute(
            text(
                "SELECT id, filename, doc_type, tags "
                "FROM metaedu.files "
                f"WHERE tenant_id = :tid AND id IN ({placeholders})"
            ),
            params,
        )
        file_meta = {row["id"]: row for row in result.mappings().all()}
    except Exception as e:  # noqa: BLE001
        logger.warning("document source metadata lookup failed: %s", e)
        file_meta = {}

    grouped: dict[Any, DocumentSource] = {}
    for evidence_index, item in enumerate(fused, start=1):
        if item.file_id is None:
            continue
        row = file_meta.get(item.file_id)
        title = (
            row["filename"]
            if row is not None and row["filename"]
            else item.title or str(item.file_id)
        )
        doc = grouped.get(item.file_id)
        if doc is None:
            doc = DocumentSource(
                file_id=item.file_id,
                title=title,
                file_name=row["filename"] if row is not None else None,
                doc_type=row["doc_type"] if row is not None else None,
                tags=list(row["tags"] or []) if row is not None else [],
            )
            grouped[item.file_id] = doc

        doc.evidence_indices.append(evidence_index)
        doc.channels = sorted(set(doc.channels).union(item.channels or []))
        if item.score is not None:
            doc.best_score = (
                item.score
                if doc.best_score is None
                else max(doc.best_score, item.score)
            )

        if item.chunk_id is not None:
            doc.chunks.append(
                DocumentSourceChunk(
                    evidence_index=evidence_index,
                    chunk_id=item.chunk_id,
                    chunk_index=metadata_int(item, "chunk_index"),
                    title=item.metadata.get("section_title") or item.title,
                    snippet=item.snippet or item.content[:500],
                    score=item.score,
                    channels=list(item.channels or []),
                )
            )

    return sorted(
        grouped.values(),
        key=lambda source: source.best_score if source.best_score is not None else -1,
        reverse=True,
    )
