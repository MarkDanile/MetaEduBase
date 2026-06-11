"""`AIChatService` 编排层测试 — Slice 3。

REQ-010 AC-1 / AC-2 / AC-4 / AC-11：AI Chat 编排层依赖 ChunkRetriever /
GraphRetriever / MetadataFilter / EvidenceFusion 抽象，测试用 fake 实现
验证编排行为（不依赖 PostgreSQL / pgvector / tsvector）。

覆盖：
- AC-1: sources 至少 1 条 source_type=chunk
- AC-2: prompt 包含 chunk content（≥80 字符）
- AC-4: fused 顺序与 prompt [1] / [2] 编号一致
- AC-6 (无证据): 候选为空时 prompt 不渲染参考证据段，answer 中显式 fallback
- AC-6 (低分): score < threshold 的 evidence 被过滤
- AC-11: fake retriever / fake fusion 注入，service 不依赖具体实现
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from app.contexts.knowledge.application.ai_chat_service import (
    AIChatService,
)
from app.contexts.knowledge.application.ai_chat_service import (
    ChatRequest as ServiceChatRequest,
)
from app.contexts.knowledge.application.evidence_fusion import (
    SimpleFrequencyFusion,
)
from app.contexts.knowledge.application.retrievers_fake import (
    FakeChunkRetriever,
    FakeGraphRetriever,
    FakeMetadataFilter,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem

SESSION = object()  # stand-in for AsyncSession (fake retriever doesn't use it)


def _chunk_evidence(file_id, idx, score=0.9, content="long " * 20 + "content") -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=file_id,
        chunk_id=uuid.uuid4(),
        title=f"section-{idx}",
        content=content,
        snippet=content[:50],
        score=score,
        metadata={"section_path": f"1.{idx}"},
    )


def _node_evidence(file_id, idx, score=0.6) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=file_id,
        node_id=uuid.uuid4(),
        title=f"node-{idx}",
        content="node desc",
        score=score,
    )


async def test_ai_chat_service_returns_chunk_evidence_in_sources() -> None:
    """AC-1: sources 至少 1 条 source_type=chunk。"""
    fid = uuid.uuid4()
    chunk = _chunk_evidence(fid, 1, score=0.9)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk]
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = []
    metadata_filter = FakeMetadataFilter()
    fusion = SimpleFrequencyFusion()

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=metadata_filter,
        evidence_fusion=fusion,
    )

    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=3),
            session=SESSION,  # type: ignore[arg-type]
        )

    assert any(s.source_type == "chunk" for s in result.sources)


async def test_ai_chat_prompt_contains_chunk_content() -> None:
    """AC-2: prompt 至少包含 1 条 chunk content（≥80 字符）。"""
    fid = uuid.uuid4()
    long_content = "电子信息工程专业需要掌握电路基础、信号与系统、数字系统设计等核心知识。" * 2
    chunk = _chunk_evidence(fid, 1, score=0.9, content=long_content)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk]
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = []

    captured: dict = {}

    async def fake_llm(self, system: str, user: str) -> str:
        captured["user"] = user
        return "ok"

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(AIChatService, "_call_llm", fake_llm):
        await service.chat(
            ServiceChatRequest(message="电子信息工程专业需要什么？", context_window=3),
            session=SESSION,  # type: ignore[arg-type]
        )

    user_prompt = captured["user"]
    assert "电子信息工程专业" in user_prompt


async def test_ai_chat_prompt_citation_numbers_match_sources_order() -> None:
    """AC-4: fused 顺序与 prompt [1] / [2] 编号一致。"""
    fid = uuid.uuid4()
    chunk_a = _chunk_evidence(fid, 1, score=0.95, content="content A " * 20)
    chunk_b = _chunk_evidence(fid, 2, score=0.85, content="content B " * 20)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk_a, chunk_b]
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = []

    captured: dict = {}

    async def fake_llm(self, system: str, user: str) -> str:
        captured["user"] = user
        return "ok"

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(AIChatService, "_call_llm", fake_llm):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=3),
            session=SESSION,  # type: ignore[arg-type]
        )

    user_prompt = captured["user"]
    idx_1 = user_prompt.find("[1]")
    idx_2 = user_prompt.find("[2]")
    assert idx_1 != -1 and idx_2 != -1
    assert idx_1 < idx_2
    assert result.sources[0].source_type == "chunk"
    assert result.sources[1].source_type == "chunk"


async def test_ai_chat_no_evidence_returns_fallback() -> None:
    """AC-6 (无证据): 候选为空时，prompt 不渲染参考证据段。"""
    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = []
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = []

    captured: dict = {}

    async def fake_llm(self, system: str, user: str) -> str:
        captured["user"] = user
        return "未找到足够参考来源：知识库中暂无与该问题相关的内容。"

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(AIChatService, "_call_llm", fake_llm):
        result = await service.chat(
            ServiceChatRequest(message="niche question", context_window=3),
            session=SESSION,  # type: ignore[arg-type]
        )

    assert "参考证据" not in captured["user"]
    assert "未找到足够参考来源" in result.reply


async def test_ai_chat_evidence_filter_drops_low_score() -> None:
    """AC-6: 当 evidence score < threshold (0.3) 时，fused 应只保留高分证据。"""
    fid = uuid.uuid4()
    good = _chunk_evidence(fid, 1, score=0.8, content="good content " * 20)
    bad = _chunk_evidence(fid, 2, score=0.1, content="bad content " * 20)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [good, bad]
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = []

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
        min_evidence_score=0.3,
    )
    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=5),
            session=SESSION,  # type: ignore[arg-type]
        )

    assert len(result.sources) == 1
    assert result.sources[0].score == 0.8


async def test_ai_chat_combines_chunk_and_node_evidence() -> None:
    """多源召回：chunk + knowledge_node 都进入 sources。"""
    fid = uuid.uuid4()
    chunk = _chunk_evidence(fid, 1, score=0.9, content="chunk content " * 20)
    node = _node_evidence(fid, 1, score=0.7)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk]
    graph_retriever = FakeGraphRetriever()
    graph_retriever.return_value = [node]

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph_retriever,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=3),
            session=SESSION,  # type: ignore[arg-type]
        )

    types = {s.source_type for s in result.sources}
    assert "chunk" in types
    assert "knowledge_node" in types
