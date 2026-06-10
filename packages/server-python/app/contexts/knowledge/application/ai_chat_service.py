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

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.retrievers import (
    ChunkRetriever,
    GraphRetriever,
    MetadataFilter,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
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
    ) -> None:
        self.chunk_retriever = chunk_retriever
        self.graph_retriever = graph_retriever
        self.metadata_filter = metadata_filter
        self.evidence_fusion = evidence_fusion
        self.ner_pipeline = ner_pipeline or RuleBasedNER()
        self.min_evidence_score = min_evidence_score

    async def _retrieve(
        self,
        message: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int,
    ) -> dict[str, list[EvidenceItem]]:
        chunk_coro = self._safe_retrieve_chunk(
            message, ner_result, tenant_id, session, top_k=top_k
        )
        graph_coro = self._safe_retrieve_graph(
            message, ner_result, tenant_id, session, top_k=top_k
        )
        chunk_results, graph_results = await asyncio.gather(
            chunk_coro, graph_coro, return_exceptions=False
        )

        all_candidates = (chunk_results or []) + (graph_results or [])
        await self.metadata_filter.filter(
            ner_result, tenant_id, session, all_candidates
        )

        channel_results: dict[str, list[EvidenceItem]] = {}
        if chunk_results:
            channel_results["chunk"] = chunk_results
        if graph_results:
            channel_results["graph"] = graph_results
        return channel_results

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

    def _build_prompt_context(self, fused: list[EvidenceItem]) -> str:
        """Build 「参考证据」 prompt segment with [1] / [2] numbering."""
        if not fused:
            return ""
        ctx = "\n\n参考证据：\n"
        for idx, ev in enumerate(fused, 1):
            source_label = self._evidence_source_label(ev)
            title_part = ev.title or ev.structured_path or ev.evidence_id
            content = ev.snippet or ev.content or ""
            channels = ",".join(ev.channels) if ev.channels else "—"
            ctx += (
                f"[{idx}] 来源: {source_label} | 标题: {title_part} | "
                f"命中: {channels}\n{content}\n"
            )
        return ctx

    @staticmethod
    def _evidence_source_label(ev: EvidenceItem) -> str:
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

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """HTTP call to LLM provider via ai_router._call_llm.

        This is overridden in tests. Kept thin so the service stays pure.
        """
        from app.contexts.knowledge.interfaces.api.ai_router import _call_llm

        return _call_llm(system_prompt, user_content)

    async def chat(
        self,
        request: ChatRequest,
        *,
        tenant_id: str = "default",
        session: AsyncSession | None = None,
    ) -> ChatResponse:
        if session is None:  # pragma: no cover - placeholder path
            raise ValueError("session is required for production chat path")

        ner_result = await self.ner_pipeline.extract(request.message)
        top_k = request.context_window

        channel_results = await self._retrieve(
            request.message, ner_result, tenant_id, session, top_k
        )

        fused = self.evidence_fusion.fuse(channel_results, top_k=min(top_k * 2, 15))

        # Filter by min score; if all dropped, keep empty fused (fallback path).
        fused = [e for e in fused if e.score is None or e.score >= self.min_evidence_score]

        # REQ-010 diagnostic log
        chunk_count = len(channel_results.get("chunk", []))
        graph_count = len(channel_results.get("graph", []))
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

        context_text = self._build_prompt_context(fused)
        user_content = (
            f"{context_text}\n\n学生问题：{request.message}"
            if context_text
            else f"学生问题：{request.message}"
        )

        reply_raw = self._call_llm(self.SYSTEM_PROMPT, user_content)
        reply = self._clean_llm_output(reply_raw)

        return ChatResponse(reply=reply, sources=fused)
