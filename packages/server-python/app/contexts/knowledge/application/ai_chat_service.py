"""`AIChatService` — REQ-010 AI Chat 编排层（Slice 3 入口）。

负责：
- 并发召回 chunk / graph retriever；
- 走 metadata filter 过滤；
- 用 EvidenceFusion 融合排序；
- 拼 prompt + 调 LLM；
- 返回 EvidenceItem[] sources + LLM answer text。

依赖 4 个抽象接口（ChunkRetriever / GraphRetriever / MetadataFilter /
EvidenceFusion），默认实例为 PostgreSQL adapter（见
`app.contexts.knowledge.infrastructure.retrievers.pg_*`），测试可通过
fake 注入。

注意：`RecallChannel` / `FrequencyFusion` 旧契约不动 — 旧 ai_chat 入口
行为由 ai_router 单独保留（如有遗留调用方）。本 service 是 RAG 编排层
唯一入口。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.context_packer import (
    ContextPacker,
    ContextPackingOptions,
    PackedContext,
)
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.retrievers import (
    ChunkRetriever,
    GraphRetriever,
    MetadataFilter,
)
from app.contexts.knowledge.domain.evidence import (
    DocumentSource,
    DocumentSourceChunk,
    EvidenceItem,
)
from app.shared.domain.ner_pipeline import NERResult

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


class RetrievalTraceItem(BaseModel):
    index: int
    evidence_id: str
    source_type: str
    title: str
    file_id: str | None = None
    chunk_id: str | None = None
    source_chunk_id: str | None = None
    score: float | None = None
    channels: list[str] = Field(default_factory=list)
    snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackedBlockTraceItem(BaseModel):
    evidence_index: int
    file_id: str | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    source_type: str
    title: str
    section_title: str | None = None
    section_path: str | None = None
    chars: int
    content: str
    channels: list[str] = Field(default_factory=list)
    score: float | None = None
    is_toc_like: bool = False
    expansion_type: str


class AIChatDiagnostics(BaseModel):
    query: str
    retrieval_topn: dict[str, list[RetrievalTraceItem]] = Field(default_factory=dict)
    fusion_topn: list[RetrievalTraceItem] = Field(default_factory=list)
    packed_blocks: list[PackedBlockTraceItem] = Field(default_factory=list)
    prompt_preview: str = ""
    packed: dict[str, Any] = Field(default_factory=dict)
    query_understanding: dict | None = None  # REQ-016 Slice 2
    # REQ-052 Task 7 — tool calling trace (None / list of tool-call summaries).
    tool_calls: list[dict] | None = None

    model_config = {"extra": "forbid"}


class AIChatService:
    """REQ-010 AI Chat 编排服务。

    P1 默认注入 PostgreSQL adapter（见
    `app/contexts/knowledge/infrastructure/retrievers/`）。测试可注入
    fake retriever 验证编排行为。
    """

    SYSTEM_PROMPT = (
        "你是 MetaEduBase 元知职教基座的 AI 助手，专注于职业教育领域的知识问答。"
        "请基于提供的「参考证据」回答，并按引用编号 [1]、[2] 标注。"
        "证据来源可能来自原文切片（chunk）、结构化字段或知识节点。"
        "如果证据不足，请直接说「未找到足够参考来源」，不要编造。"
        "回答请使用中文，结构清晰，适合教学场景使用。"
    )

    def __init__(
        self,
        chunk_retriever: ChunkRetriever,
        graph_retriever: GraphRetriever,
        metadata_filter: MetadataFilter,
        evidence_fusion: Any,
        ner_pipeline: Any | None = None,
        min_evidence_score: float = 0.3,
        context_packer: ContextPacker | None = None,
        context_packing_options: ContextPackingOptions | None = None,
        edge_retriever: GraphRetriever | None = None,  # REQ-018 Slice 2: graph edge channel
        # REQ-052 Task 7 — tool-calling wiring. The factory is invoked with
        # the request-bound ``AsyncSession`` so the resulting repo can issue
        # SQL inside the same transaction as the audit log commit. Production
        # wires ``SemanticModelRepository`` (Task 5); tests can inject a fake.
        semantic_model_repository_factory: Any | None = None,
        # REQ-052 Task 7 — REQ-052 ``QueryService`` (Task 5) used to execute
        # the ``query_internal_data`` tool. Wired by the router at request
        # time so the audit row commits with the response.
        query_service: Any | None = None,
    ) -> None:
        self.chunk_retriever = chunk_retriever
        self.graph_retriever = graph_retriever
        self.metadata_filter = metadata_filter
        self.evidence_fusion = evidence_fusion
        self.ner_pipeline = ner_pipeline or RuleBasedNER()
        self.min_evidence_score = min_evidence_score
        self._context_packer = context_packer
        self._packing_opts = context_packing_options or ContextPackingOptions()
        self.edge_retriever = edge_retriever
        # Default factory falls back to the real SemanticModelRepository
        # (REQ-052 Task 5). Lazy-imported to avoid pulling structured_data
        # into test paths that don't need it.
        if semantic_model_repository_factory is None:
            def _default_repo_factory(session: AsyncSession):
                from app.contexts.structured_data.infrastructure.semantic_model_repository import (
                    SemanticModelRepository,
                )
                return SemanticModelRepository(session)

            self.semantic_model_repository_factory = _default_repo_factory
        else:
            self.semantic_model_repository_factory = semantic_model_repository_factory
        self.query_service = query_service

    @staticmethod
    def _normalize_candidate_channels(
        candidates: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        normalized: list[EvidenceItem] = []
        for item in candidates:
            if item.source_type == "knowledge_node":
                updated = item.model_copy(deep=True)
                updated.channels = sorted(set(updated.channels or []).union({"graph"}))
                normalized.append(updated)
            elif item.source_type == "knowledge_edge":
                # Edge items: add "graph_edge" channel label
                updated = item.model_copy(deep=True)
                updated.channels = sorted(set(updated.channels or []).union({"graph_edge"}))
                normalized.append(updated)
            else:
                normalized.append(item)
        return normalized

    @staticmethod
    def _group_candidates_by_channel(
        candidates: list[EvidenceItem],
    ) -> dict[str, list[EvidenceItem]]:
        channel_results: dict[str, list[EvidenceItem]] = {}
        for item in candidates:
            channels = item.channels or [item.source_type]
            for channel in channels:
                channel_results.setdefault(channel, []).append(item)
        return channel_results

    @staticmethod
    def _uses_absolute_score_threshold(evidence_fusion: Any) -> bool:
        """Only absolute-score fusion should be filtered by min_evidence_score.

        RRF returns raw reciprocal-rank scores (typically around 0.0x), so the
        historical absolute threshold would wipe out valid evidence.
        """
        return getattr(evidence_fusion, "score_semantics", "absolute") == "absolute"

    @staticmethod
    def _trace_evidence(items: list[EvidenceItem]) -> list[RetrievalTraceItem]:
        traced: list[RetrievalTraceItem] = []
        for index, item in enumerate(items, start=1):
            traced.append(
                RetrievalTraceItem(
                    index=index,
                    evidence_id=item.evidence_id,
                    source_type=item.source_type,
                    title=item.title,
                    file_id=str(item.file_id) if item.file_id else None,
                    chunk_id=str(item.chunk_id) if item.chunk_id else None,
                    source_chunk_id=(
                        str(item.source_chunk_id) if item.source_chunk_id else None
                    ),
                    score=item.score,
                    channels=list(item.channels or []),
                    snippet=(item.snippet or item.content or "")[:240],
                    metadata=dict(item.metadata or {}),
                )
            )
        return traced

    @staticmethod
    def _trace_packed_blocks(packed: PackedContext) -> list[PackedBlockTraceItem]:
        traced: list[PackedBlockTraceItem] = []
        for block in packed.blocks:
            traced.append(
                PackedBlockTraceItem(
                    evidence_index=block.evidence_index,
                    file_id=str(block.file_id) if block.file_id else None,
                    chunk_ids=[str(cid) for cid in block.chunk_ids],
                    source_type=block.source_type,
                    title=block.title,
                    section_title=block.section_title,
                    section_path=block.section_path,
                    chars=len(block.content),
                    content=block.content[:500],
                    channels=list(block.channels or []),
                    score=block.score,
                    is_toc_like=block.is_toc_like,
                    expansion_type=block.expansion_type,
                )
            )
        return traced

    def _enrich_fusion_diagnostics(
        self,
        packed: PackedContext,
        channel_results: dict[str, list[EvidenceItem]],
        fused: list[EvidenceItem],
    ) -> PackedContext:
        """REQ-017 Slice 2: populate RRF fusion diagnostics.

        Fills fusion_method / rrf_k / rrf_weights_used / fusion_scores /
        channel_ranks on packed.diagnostics.
        """
        fusion = self.evidence_fusion
        diag = packed.diagnostics

        # Identify fusion type
        fusion_name = fusion.__class__.__name__
        diag.fusion_method = fusion_name

        # RRF-specific fields
        if hasattr(fusion, "k"):
            diag.rrf_k = fusion.k  # type: ignore[attr-defined]
        if hasattr(fusion, "channel_weights"):
            diag.rrf_weights_used = dict(fusion.channel_weights or {})  # type: ignore[attr-defined]

        # channel_ranks: channel -> evidence_id -> rank (1-based)
        channel_ranks: dict[str, dict[str, int]] = {}
        for ch, items in channel_results.items():
            channel_ranks[ch] = {
                it.evidence_id: rank + 1 for rank, it in enumerate(items)
            }
        diag.channel_ranks = channel_ranks

        # fusion_scores: evidence_id -> score from fusion output
        diag.fusion_scores = {e.evidence_id: e.score for e in fused}

        return packed

    async def _hydrate_graph_chunks(
        self,
        fused: list[EvidenceItem],
        tenant_id: str,
        session: AsyncSession,
    ) -> list[EvidenceItem]:
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

    async def _build_document_sources(
        self,
        fused: list[EvidenceItem],
        tenant_id: str,
        session: AsyncSession,
    ) -> list[DocumentSource]:
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
                        chunk_index=self._metadata_int(item, "chunk_index"),
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

    @staticmethod
    def _metadata_int(item: EvidenceItem, key: str) -> int | None:
        value = (item.metadata or {}).get(key)
        return value if isinstance(value, int) else None

    async def _safe_metadata_filter(
        self,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        candidates: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        try:
            return await self.metadata_filter.filter(
                ner_result, tenant_id, session, candidates
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("metadata filter failed: %s", e)
            return candidates

    async def _retrieve(
        self,
        message: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int,
    ) -> dict[str, list[EvidenceItem]]:
        # IMPORTANT: SQLAlchemy AsyncSession forbids concurrent operations on
        # the same session object. Run the chunk and graph retrievers in
        # sequence so the production chain stays stable on real PG.
        chunk_results = await self._safe_retrieve_chunk(
            message, ner_result, tenant_id, session, top_k=top_k
        )
        graph_results = await self._safe_retrieve_graph(
            message, ner_result, tenant_id, session, top_k=top_k
        )
        # REQ-018 Slice 2: 4th channel — edge retriever (knowledge_edges path)
        edge_results = await self._safe_retrieve_edge(
            message, ner_result, tenant_id, session, top_k=top_k
        )

        raw_candidates = (chunk_results or []) + (graph_results or []) + (edge_results or [])
        raw_candidates = self._normalize_candidate_channels(raw_candidates)
        filtered_candidates = await self._safe_metadata_filter(
            ner_result, tenant_id, session, raw_candidates
        )
        return self._group_candidates_by_channel(filtered_candidates)

    async def _safe_retrieve_chunk(self, *args, **kwargs) -> list[EvidenceItem]:
        try:
            return await self.chunk_retriever.retrieve(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("chunk retrieval failed: %s", e)
            return []

    async def _safe_retrieve_graph(self, *args, **kwargs) -> list[EvidenceItem]:
        try:
            return await self.graph_retriever.retrieve(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("graph retrieval failed: %s", e)
            return []

    async def _safe_retrieve_edge(self, *args, **kwargs) -> list[EvidenceItem]:
        """REQ-018 Slice 2: safe wrapper for edge retriever (4th recall channel)."""
        if self.edge_retriever is None:
            return []
        try:
            return await self.edge_retriever.retrieve(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("edge retrieval failed: %s", e)
            return []

    def _build_prompt_context(self, packed: PackedContext) -> str:
        """Build 「参考证据」 prompt segment with [1] / [2] numbering.

        Uses PackedContext.blocks[] for content (neighbor-expanded / section-expanded).
        Citation numbering follows block.evidence_index to stay consistent with
        the evidence[] citation sequence the caller sees in sources.
        """
        if not packed.blocks:
            return ""
        ctx = "\n\n参考证据：\n"
        for block in packed.blocks:
            evidence_idx = block.evidence_index
            # Look up the original EvidenceItem for stable source label
            ev = (
                packed.evidence[evidence_idx - 1]
                if evidence_idx <= len(packed.evidence)
                else None
            )
            source_label = (
                self._evidence_source_label(ev)
                if ev else block.source_type
            )
            title_part = block.title or (ev.title if ev else block.evidence_index)
            channels = ",".join(block.channels) if block.channels else "—"
            expansion_tag = (
                f" [{block.expansion_type}]"
                if block.expansion_type != "hit"
                else ""
            )
            ctx += (
                f"[{evidence_idx}] 来源: {source_label}{expansion_tag} | "
                f"标题: {title_part} | 命中: {channels}\n{block.content}\n"
            )
        return ctx

    @staticmethod
    def _evidence_source_label(ev: EvidenceItem | None) -> str:
        if ev is None:
            return "unknown"
        if ev.source_type == "chunk":
            return "chunk"
        if ev.source_type == "knowledge_node":
            return "knowledge_node"
        if ev.source_type == "knowledge_edge":
            return "knowledge_edge"
        if ev.source_type == "structured_field":
            return "structured_field"
        return ev.source_type

    def _clean_llm_output(self, content: str) -> str:
        content = re.sub(r"考量.*?生成", "", content, flags=re.DOTALL)
        content = re.sub(r"思路.*?回复", "", content, flags=re.DOTALL)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        return content.strip()

    async def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """HTTP call to LLM provider via ai_router._call_llm.

        This is overridden in tests. Kept thin so the service stays pure.
        """
        from app.contexts.knowledge.interfaces.api.ai_router import _call_llm

        return await _call_llm(system_prompt, user_content)

    async def _call_llm_with_tools(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """REQ-052 Task 7 — tool-calling-aware LLM call.

        Delegates to :func:`app.contexts.knowledge.interfaces.api.ai_router._call_llm_with_tools`.
        Accepts a full conversation history and returns
        ``{"content": str | None, "tool_calls": list | None}`` so the chat
        flow can decide whether to invoke the registered tool.

        Tests override this method via ``patch.object(AIChatService,
        "_call_llm_with_tools", ...)`` — see
        ``test_ai_chat_tool_calling.py``.
        """
        from app.contexts.knowledge.interfaces.api.ai_router import (
            _call_llm_with_tools as _router_call_llm_with_tools,
        )

        return await _router_call_llm_with_tools(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # REQ-052 Task 7 — tool definition for ``query_internal_data``. Declared
    # as a class attribute so tests can introspect it without re-creating it.
    # REQ-056 Task 3 — ``catalog_id`` added so the LLM can route by catalog.
    # When the LLM fills this field, AI Chat resolves the SemanticModel via
    # ``get_active_by_catalog_and_entity_type`` (dual-key) so multi-catalog
    # tenants don't accidentally hit the wrong ``bill``/``contract`` model.
    # When omitted, AI Chat falls back to ``get_active_by_entity_type`` (V1
    # legacy behavior — REQ-052 Task 7 path).
    _QUERY_INTERNAL_DATA_TOOL: dict[str, Any] = {
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

    async def chat(
        self,
        request: ChatRequest,
        *,
        tenant_id: str = "default",
        session: AsyncSession | None = None,
        user_id: uuid.UUID | None = None,
        role: str = "employee",
        # REQ-056 Task 2 — when the caller (router) has the authenticated
        # current_user dict from ``Depends(get_current_user)``, pass it here
        # so user_id / role / tenant_id are sourced from the verified JWT
        # rather than from per-call kwargs (which are easy to leave stale).
        # ``current_user`` wins over the legacy kwargs — it is the source of
        # truth for audit identity.
        current_user: dict | None = None,
    ) -> ChatResponse:
        if session is None:  # pragma: no cover - placeholder path
            raise ValueError("session is required for production chat path")

        # REQ-056 Task 2 — resolve request-bound identity. ``current_user``
        # is preferred when provided (carries the verified JWT user). Legacy
        # callers that only pass ``user_id``/``role``/``tenant_id`` still
        # work; if neither is given, fall back to a random UUID (test seams
        # only — production must inject a current_user).
        if current_user is not None:
            user_id = current_user.get("id", user_id)
            role = current_user.get("role", role) or role
            cu_tenant = current_user.get("tenant_id")
            if cu_tenant is not None:
                tenant_id = str(cu_tenant)

        ner_result = await self.ner_pipeline.extract(request.message)
        top_k = request.context_window

        channel_results = await self._retrieve(
            request.message, ner_result, tenant_id, session, top_k
        )
        retrieval_topn = {
            channel: self._trace_evidence(items)
            for channel, items in channel_results.items()
        }

        fused = self.evidence_fusion.fuse(channel_results, top_k=min(top_k * 2, 15))

        # Filter only when the fusion emits absolute scores. RRF/raw reciprocal
        # rank scores are intentionally small and must not be wiped out by the
        # historical 0.3 threshold.
        if self.min_evidence_score > 0 and self._uses_absolute_score_threshold(
            self.evidence_fusion
        ):
            fused = [
                e for e in fused
                if e.score is None or e.score >= self.min_evidence_score
            ]
        fused = await self._hydrate_graph_chunks(fused, tenant_id, session)

        # REQ-013: context packing — expand fused evidence with neighbors / section
        channel_top_k = {ch: len(items) for ch, items in channel_results.items()}
        if self._context_packer is not None:
            packed = await self._context_packer.pack(
                fused,
                channel_top_k=channel_top_k,
            )
        else:
            # No packer injected — build a minimal PackedContext for _build_prompt_context
            from app.contexts.knowledge.application.context_packer import (
                PackedContext,
                PackedContextBlock,
                PackedContextDiagnostics,
            )

            packed = PackedContext(
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

        # REQ-017 Slice 2: populate RRF fusion diagnostics
        packed = self._enrich_fusion_diagnostics(
            packed, channel_results, fused
        )

        document_sources = await self._build_document_sources(fused, tenant_id, session)

        # REQ-012 diagnostic log: channel labels may be vector/keyword/graph,
        # so count source types after grouping to keep the log faithful.
        all_channel_items = [
            item
            for items in channel_results.values()
            for item in items
        ]
        chunk_count = len(
            {
                item.evidence_id
                for item in all_channel_items
                if item.source_type == "chunk"
            }
        )
        graph_count = len(
            {
                item.evidence_id
                for item in all_channel_items
                if item.source_type == "knowledge_node"
            }
        )
        logger.info(
            "ai_chat_service: query=%r ner_domains=%r ner_levels=%r "
            "chunk=%d graph=%d fused=%d",
            request.message[:120],
            ner_result.domains,
            ner_result.levels,
            chunk_count,
            graph_count,
            len(fused),
        )

        context_text = self._build_prompt_context(packed)
        # REQ-016 Slice 2: include query_understanding trace when available
        qu = getattr(ner_result, "query_understanding", None)
        query_understanding_diag: dict[str, Any] | None = None
        if qu is not None:
            query_understanding_diag = {
                "method": qu.method,
                "confidence": qu.confidence,
                "normalized_query": qu.normalized_query,
                "core_terms": qu.core_terms,
                "expanded_terms": qu.expanded_terms,
                "entities": qu.entities,
                "filters": qu.filters,
                "trigger_reason": getattr(ner_result, "trigger_reason", None),
            }

        diagnostics_model = AIChatDiagnostics(
            query=request.message,
            retrieval_topn=retrieval_topn,
            fusion_topn=self._trace_evidence(fused),
            packed_blocks=self._trace_packed_blocks(packed),
            prompt_preview=context_text[:1200],
            packed=packed.diagnostics.model_dump(mode="json"),
            query_understanding=query_understanding_diag,
        )
        logger.info(
            "ai_chat_trace: %s",
            json.dumps(diagnostics_model.model_dump(mode="json"), ensure_ascii=False),
        )
        user_content = (
            f"{context_text}\n\n学生问题：{request.message}"
            if context_text
            else f"学生问题：{request.message}"
        )

        # ------------------------------------------------------------------
        # REQ-052 Task 7 — tool-calling orchestration
        #
        # Flow:
        #   1. LLM first call (with `tools=[query_internal_data]`)
        #      → either returns direct ``content`` (no tool needed)
        #      → or returns ``tool_calls`` requesting `query_internal_data`.
        #   2. If tool_calls present and the function name is supported,
        #      look up the ``SemanticModel`` by ``entity_hint`` (or fall back
        #      to a default) and call :meth:`QueryService.ask`. The audit
        #      log row is written inside ``QueryService.ask`` (REQ-052 §12).
        #   3. LLM second call (with full conversation history: system →
        #      user → assistant+tool_call → tool result) → final ``content``.
        # ------------------------------------------------------------------

        first_messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        first_result = await self._call_llm_with_tools(
            first_messages,
            tools=[self._QUERY_INTERNAL_DATA_TOOL],
            tool_choice="auto",
        )
        tool_calls = first_result.get("tool_calls")
        first_content = first_result.get("content")

        if not tool_calls:
            # LLM answered directly — no tool invocation, no second LLM call.
            reply = self._clean_llm_output(first_content or "")
            diagnostics_model.tool_calls = None
        else:
            # We have at least one tool call. We only handle one for V1;
            # the function name must be ``query_internal_data``.
            tool_call = tool_calls[0]
            fn_name = (tool_call.get("function") or {}).get("name")
            if fn_name != "query_internal_data":
                # Unknown / unsupported tool — fall back to first-response
                # content (or a polite fallback if the model returned None).
                logger.warning(
                    "ai_chat_service: unsupported tool_call name=%r; "
                    "falling back to direct content.",
                    fn_name,
                )
                reply = self._clean_llm_output(
                    first_content or "抱歉，我暂时无法执行该操作。"
                )
                diagnostics_model.tool_calls = [
                    {
                        "name": fn_name,
                        "skipped": True,
                        "reason": "unsupported_function_name",
                    }
                ]
            else:
                diagnostics_model.tool_calls = [
                    {"name": fn_name, "skipped": False}
                ]
                # ---- 3a. Resolve SemanticModel from entity_hint ----
                arguments_raw = (tool_call.get("function") or {}).get(
                    "arguments", "{}"
                )
                try:
                    arguments = json.loads(arguments_raw)
                except (TypeError, ValueError):
                    logger.warning(
                        "ai_chat_service: invalid tool_call arguments=%r; "
                        "treating as empty dict.",
                        arguments_raw,
                    )
                    arguments = {}
                entity_hint = arguments.get("entity_hint") or "bill"
                question = arguments.get("question") or request.message

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
                semantic_repo = self.semantic_model_repository_factory(session)
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
                    tool_result_payload = {
                        "ok": False,
                        "errors": [
                            f"entity_type '{entity_hint}' not configured for tenant"
                        ],
                        "suggestion": "请尝试更具体的问题。",
                    }
                else:
                    # ---- 3b. Call QueryService.ask (writes audit row) ----
                    query_service = getattr(self, "query_service", None)
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
                        tool_result_payload = {
                            "ok": False,
                            "errors": ["query_service not available"],
                            "suggestion": "请稍后重试。",
                        }
                    else:
                        effective_user_id = user_id or uuid.uuid4()
                        tool_result_payload = await query_service.ask(
                            question=question,
                            semantic_model=semantic_model,
                            user_id=effective_user_id,
                            tenant_id=tenant_uuid,
                            role=role,
                            business_purpose=(
                                f"AI Chat 工具调用 — question={question[:80]}"
                            ),
                            confirmed_company_name=None,  # V1: system prompt handles ambiguity
                        )

                # ---- 3c. Second LLM call with full conversation history ----
                second_messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(
                            tool_result_payload, ensure_ascii=False
                        ),
                    },
                ]
                second_result = await self._call_llm_with_tools(second_messages)
                second_content = second_result.get("content")
                reply = self._clean_llm_output(second_content or "")

        return ChatResponse(
            reply=reply,
            sources=fused,
            document_sources=document_sources,
            diagnostics=diagnostics_model.model_dump(mode="json"),
        )
