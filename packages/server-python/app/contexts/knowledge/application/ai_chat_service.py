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

TD-085 Slice B 拆分（spec ADR-085-2）：
- Prompt 构造 → `app.runtime.application.prompt_builder`
- Tool Calling 编排 → `app.runtime.application.tool_orchestrator`
- Diagnostics（trace DTO + 装配）→ `ai_chat_diagnostics`
- ChatRequest/ChatResponse/工具 schema/证据 DTO 装配 → `ai_chat_dto`
以上名字均在本模块 re-export，既有导入路径与 `patch.object` 测试缝不变。
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.ai_chat_diagnostics import (
    AIChatDiagnostics,
    PackedBlockTraceItem,
    RetrievalTraceItem,
    build_chat_diagnostics,
    enrich_fusion_diagnostics,
    log_retrieval_summary,
)
from app.contexts.knowledge.application.ai_chat_dto import (
    QUERY_INTERNAL_DATA_TOOL,
    ChatRequest,
    ChatResponse,
    build_document_sources,
    build_fallback_packed,
    dispatch_query_internal_data,
    hydrate_graph_chunks,
)
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
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.runtime.application.llm_provider import LlmProvider
from app.runtime.application.prompt_builder import (
    build_prompt_context,
    build_user_content,
)
from app.runtime.application.tool_orchestrator import run_tool_calling
from app.shared.domain.ner_pipeline import NERResult

__all__ = [
    "AIChatDiagnostics",
    "AIChatService",
    "ChatRequest",
    "ChatResponse",
    "PackedBlockTraceItem",
    "RetrievalTraceItem",
]

logger = logging.getLogger(__name__)


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

    # REQ-052 Task 7 — tool definition lives in `ai_chat_dto` (Slice B);
    # the class attribute keeps the historical introspection seam
    # (``AIChatService._QUERY_INTERNAL_DATA_TOOL``) pointing at the same dict.
    _QUERY_INTERNAL_DATA_TOOL = QUERY_INTERNAL_DATA_TOOL

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
        # TD-085 Slice A — LLM port injection. Composition root
        # (``ai_router._build_evidence_service``) constructs an
        # ``OpenAIProvider`` once and passes the same instance here so
        # application code never imports concrete adapters or
        # ``ai_router`` symbols. Falls back to a legacy ``_call_llm`` /
        # ``_call_llm_with_tools``-compatible callables for tests that
        # pre-date Slice A; the legacy fallback is recognised by the
        # ``LlmProvider`` protocol surface (duck-typed).
        llm_provider: LlmProvider | None = None,
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
        self.llm_provider = llm_provider

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

    def _enrich_fusion_diagnostics(
        self,
        packed: PackedContext,
        channel_results: dict[str, list[EvidenceItem]],
        fused: list[EvidenceItem],
    ) -> PackedContext:
        """REQ-017 Slice 2 compat seam — implementation moved to
        ``ai_chat_diagnostics.enrich_fusion_diagnostics`` (Slice B)."""
        return enrich_fusion_diagnostics(
            self.evidence_fusion, packed, channel_results, fused
        )

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

    def _clean_llm_output(self, content: str) -> str:
        content = re.sub(r"考量.*?生成", "", content, flags=re.DOTALL)
        content = re.sub(r"思路.*?回复", "", content, flags=re.DOTALL)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        return content.strip()

    async def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """Synchronous-style LLM call routed through the ``LlmProvider`` port.

        Composition root (``ai_router._build_evidence_service``) injects
        an ``OpenAIProvider`` wrapping ``ai_router._call_llm`` so this
        method stays a thin port call. Tests may either inject an
        explicit ``llm_provider`` argument to ``AIChatService(...)`` or
        ``patch.object(AIChatService, "_call_llm", ...)`` for legacy
        seams.
        """
        provider = self.llm_provider
        if provider is None:
            raise RuntimeError(
                "AIChatService.llm_provider is not configured; "
                "composition root must inject an LlmProvider before "
                "calling _call_llm."
            )
        return await provider.chat_text(system_prompt, user_content)

    async def _call_llm_with_tools(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """REQ-052 Task 7 — tool-calling-aware LLM call via ``LlmProvider``.

        Delegates to the injected ``LlmProvider`` port. Returns the
        legacy ``{"content": str | None, "tool_calls": list | None}``
        dict shape so the existing chat flow (and existing test patch
        sites that read ``chat_with_tools`` return values) keeps
        working.

        Tests may either inject an explicit ``llm_provider`` argument
        to ``AIChatService(...)`` or ``patch.object(AIChatService,
        "_call_llm_with_tools", ...)`` for legacy seams.
        """
        provider = self.llm_provider
        if provider is None:
            raise RuntimeError(
                "AIChatService.llm_provider is not configured; "
                "composition root must inject an LlmProvider before "
                "calling _call_llm_with_tools."
            )
        result = await provider.chat_with_tools(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Re-shape the port envelope to the historical dict form so
        # downstream chat-flow code (and existing tests) keep working.
        if result.tool_calls:
            tool_calls_payload: list[dict] | None = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments_json},
                }
                for tc in result.tool_calls
            ]
        else:
            tool_calls_payload = None
        return {"content": result.content, "tool_calls": tool_calls_payload}

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
        fused = await hydrate_graph_chunks(fused, tenant_id, session)

        # REQ-013: context packing — expand fused evidence with neighbors / section
        channel_top_k = {ch: len(items) for ch, items in channel_results.items()}
        if self._context_packer is not None:
            packed = await self._context_packer.pack(
                fused,
                channel_top_k=channel_top_k,
            )
        else:
            # No packer injected — minimal PackedContext compat shim.
            packed = build_fallback_packed(fused, channel_top_k)

        # REQ-017 Slice 2: populate RRF fusion diagnostics
        packed = self._enrich_fusion_diagnostics(
            packed, channel_results, fused
        )

        document_sources = await build_document_sources(fused, tenant_id, session)

        # REQ-012 diagnostic summary log (Slice B: moved to ai_chat_diagnostics)
        log_retrieval_summary(
            request.message, ner_result, channel_results, fused
        )

        context_text = build_prompt_context(packed)
        diagnostics_model = build_chat_diagnostics(
            query=request.message,
            channel_results=channel_results,
            fused=fused,
            packed=packed,
            context_text=context_text,
            ner_result=ner_result,
        )
        user_content = build_user_content(context_text, request.message)

        # ------------------------------------------------------------------
        # REQ-052 Task 7 — tool-calling orchestration (TD-085 Slice B:
        # generic two-round loop lives in runtime/tool_orchestrator; the
        # business dispatch below keeps SemanticModel resolution and
        # QueryService.ask on the knowledge side).
        # ------------------------------------------------------------------
        first_messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        outcome = await run_tool_calling(
            # Call-time attribute lookup keeps the
            # ``patch.object(AIChatService, "_call_llm_with_tools", ...)``
            # test seam working.
            self._call_llm_with_tools,
            first_messages,
            tools=[self._QUERY_INTERNAL_DATA_TOOL],
            supported_tool_names={"query_internal_data"},
            dispatch=lambda _fn_name, arguments: dispatch_query_internal_data(
                arguments,
                semantic_model_repository_factory=self.semantic_model_repository_factory,
                query_service=self.query_service,
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                message=request.message,
            ),
            unsupported_fallback_reply="抱歉，我暂时无法执行该操作。",
        )
        diagnostics_model.tool_calls = outcome.tool_calls_trace
        reply = self._clean_llm_output(outcome.reply_text)

        return ChatResponse(
            reply=reply,
            sources=fused,
            document_sources=document_sources,
            diagnostics=diagnostics_model.model_dump(mode="json"),
        )
