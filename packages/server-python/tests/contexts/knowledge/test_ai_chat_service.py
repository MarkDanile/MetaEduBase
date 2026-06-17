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

from app.contexts.knowledge.application.ai_chat_service import AIChatService
from app.contexts.knowledge.application.ai_chat_service import (
    ChatRequest as ServiceChatRequest,
)
from app.contexts.knowledge.application.composite_retriever import (
    CompositeChunkRetriever,
)
from app.contexts.knowledge.application.context_packer import (
    ContextPacker,
    ContextPackingOptions,
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


class _FakeRows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeRows:
        return _FakeRows(self._rows)


class FakeSession:
    def __init__(
        self,
        *,
        files: list[dict] | None = None,
        chunks: list[dict] | None = None,
    ) -> None:
        self.files = files or []
        self.chunks = chunks or []
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        stmt_text = str(stmt)
        self.statements.append(stmt_text)
        if "FROM metaedu.files" in stmt_text:
            return _FakeResult(self.files)
        if "FROM metaedu.document_chunks" in stmt_text:
            return _FakeResult(self.chunks)
        return _FakeResult([])


class FakeChunkRepo:
    def __init__(self, chunks: dict[uuid.UUID, list[dict]]) -> None:
        self.chunks = chunks

    async def get_chunks_by_file_and_indices(
        self,
        file_id: uuid.UUID,
        indices: list[int],
        tenant_id: uuid.UUID,
    ) -> dict[int, dict]:
        rows = {row["chunk_index"]: row for row in self.chunks.get(file_id, [])}
        return {i: rows[i] for i in indices if i in rows}

    async def get_chunk_by_id(self, chunk_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        for rows in self.chunks.values():
            for row in rows:
                if row["id"] == chunk_id:
                    return row
        return None

    async def get_chunks_by_file_and_section(
        self,
        file_id: uuid.UUID,
        section_path: str,
        tenant_id: uuid.UUID,
        *,
        limit: int = 12,
    ) -> list[dict]:
        return [
            row for row in self.chunks.get(file_id, [])
            if row.get("section_path") == section_path
        ][:limit]


SESSION = FakeSession()


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


def _session_for_file(
    file_id: uuid.UUID,
    *,
    filename: str = "Python 操作指南.pdf",
    doc_type: str = "操作指南",
    tags: list[str] | None = None,
) -> FakeSession:
    return FakeSession(
        files=[
            {
                "id": file_id,
                "filename": filename,
                "doc_type": doc_type,
                "tags": tags or ["python"],
            }
        ]
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


async def test_composite_chunk_retriever_calls_vector_and_keyword() -> None:
    """REQ-012 AC-1: chunk vector + keyword retriever both enter candidates."""
    fid = uuid.uuid4()
    vector_chunk = _chunk_evidence(fid, 1, score=0.9, content="vector content " * 20)
    keyword_chunk = _chunk_evidence(fid, 2, score=0.8, content="keyword content " * 20)

    vector = FakeChunkRetriever()
    vector.return_value = [vector_chunk]
    keyword = FakeChunkRetriever()
    keyword.return_value = [keyword_chunk]
    graph = FakeGraphRetriever()
    graph.return_value = []

    service = AIChatService(
        chunk_retriever=CompositeChunkRetriever([vector, keyword]),
        graph_retriever=graph,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )

    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="Python 基本数据类型", context_window=3),
            session=_session_for_file(fid),  # type: ignore[arg-type]
        )

    assert len(vector.calls) == 1
    assert len(keyword.calls) == 1
    assert {src.evidence_id for src in result.sources} == {
        vector_chunk.evidence_id,
        keyword_chunk.evidence_id,
    }


async def test_metadata_filter_return_value_affects_fusion_input() -> None:
    """REQ-012 AC-2: metadata filter 的返回值必须进入 fusion。"""
    fid = uuid.uuid4()
    keep = _chunk_evidence(fid, 1, score=0.9, content="keep content " * 20)
    drop = _chunk_evidence(fid, 2, score=0.8, content="drop content " * 20)

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [keep, drop]
    metadata_filter = FakeMetadataFilter()
    metadata_filter.return_value = [keep]

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=metadata_filter,
        evidence_fusion=SimpleFrequencyFusion(),
    )

    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=3),
            session=_session_for_file(fid),  # type: ignore[arg-type]
        )

    assert [src.evidence_id for src in result.sources] == [keep.evidence_id]
    assert metadata_filter.calls[0]["candidate_count"] == 2


async def test_graph_evidence_hydrates_prompt_from_source_chunk() -> None:
    """REQ-012 AC-4: graph evidence 有 source_chunk_id 时 prompt 使用 chunk 原文。"""
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    node = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        chunk_id=cid,
        source_chunk_id=cid,
        node_id=uuid.uuid4(),
        title="Python 数据类型",
        content="node desc",
        snippet="node desc",
        score=0.9,
        channels=["vector"],
    )
    graph = FakeGraphRetriever()
    graph.return_value = [node]
    chunk_text = "Python 的基本数据类型包括数字、字符串、列表、元组、字典和集合。"
    session = FakeSession(
        files=[{"id": fid, "filename": "Python 操作指南.pdf", "doc_type": "指南", "tags": []}],
        chunks=[
            {
                "id": cid,
                "file_id": fid,
                "chunk_index": 7,
                "content": chunk_text,
                "section_title": "基本数据类型",
                "section_path": "1.2",
            }
        ],
    )

    captured: dict = {}

    async def fake_llm(self, system: str, user: str) -> str:
        captured["user"] = user
        return "ok"

    service = AIChatService(
        chunk_retriever=FakeChunkRetriever(),
        graph_retriever=graph,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(AIChatService, "_call_llm", fake_llm):
        result = await service.chat(
            ServiceChatRequest(message="Python 有哪些基本数据类型？", context_window=3),
            session=session,  # type: ignore[arg-type]
        )

    assert chunk_text in captured["user"]
    assert result.sources[0].metadata["content_source"] == "document_chunk"
    assert result.sources[0].metadata["chunk_index"] == 7


async def test_context_packer_diagnostics_include_python_body_context() -> None:
    """REQ-015: Python regression checks packed content, not only response shape."""
    tenant_id = uuid.uuid4()
    fid = uuid.uuid4()
    hit_cid = uuid.uuid4()
    body_cid = uuid.uuid4()
    hit = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=hit_cid,
        title="数据类型和变量",
        content="本节介绍 Python 数据类型。",
        snippet="本节介绍 Python 数据类型。",
        score=0.9,
        channels=["keyword"],
        metadata={"chunk_index": 3, "section_path": "1.1", "section_title": "数据类型和变量"},
    )
    chunks = {
        fid: [
            {
                "id": hit_cid,
                "file_id": fid,
                "chunk_index": 3,
                "content": "本节介绍 Python 数据类型。",
                "section_title": "数据类型和变量",
                "section_path": "1.1",
            },
            {
                "id": body_cid,
                "file_id": fid,
                "chunk_index": 8,
                "content": (
                    "Python 的基本数据类型包括 int、float、str、bool、"
                    "list、tuple、dict 和 set。"
                ),
                "section_title": "数据类型和变量",
                "section_path": "1.1",
            },
        ]
    }
    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [hit]

    captured: dict = {}

    async def fake_llm(self, system: str, user: str) -> str:
        captured["user"] = user
        return "Python 的基本数据类型包括 int、float、str、bool、list、tuple、dict 和 set。[1]"

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
        context_packer=ContextPacker(
            FakeChunkRepo(chunks),
            tenant_id,
            ContextPackingOptions(neighbor_window=0, max_blocks=8, max_chars=4000),
        ),
    )
    with patch.object(AIChatService, "_call_llm", fake_llm):
        result = await service.chat(
            ServiceChatRequest(message="python 的基本数据类型有哪些？", context_window=3),
            tenant_id=str(tenant_id),
            session=_session_for_file(fid),  # type: ignore[arg-type]
        )

    assert "int、float、str、bool" in captured["user"]
    packed_blocks = result.diagnostics["packed_blocks"]
    assert any(block["expansion_type"] == "section" for block in packed_blocks)
    assert any("int、float、str、bool" in block["content"] for block in packed_blocks)
    assert result.diagnostics["retrieval_topn"]["keyword"][0]["title"] == "数据类型和变量"


async def test_document_sources_group_by_file_and_skip_unattributed_graph() -> None:
    """REQ-012 AC-7/AC-9: 底部来源按文档聚合，无 file_id 不伪装为文档。"""
    fid = uuid.uuid4()
    chunk_a = _chunk_evidence(fid, 1, score=0.9, content="content A " * 20)
    chunk_b = _chunk_evidence(fid, 2, score=0.7, content="content B " * 20)
    orphan_graph = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=None,
        node_id=uuid.uuid4(),
        title="来源待细化节点",
        content="node desc",
        score=0.95,
        channels=["graph"],
    )

    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk_a, chunk_b]
    graph = FakeGraphRetriever()
    graph.return_value = [orphan_graph]

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=graph,
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    with patch.object(service, "_call_llm", AsyncMock(return_value="ok")):
        result = await service.chat(
            ServiceChatRequest(message="hi", context_window=3),
            session=_session_for_file(fid),  # type: ignore[arg-type]
        )

    assert len(result.document_sources) == 1
    doc = result.document_sources[0]
    assert doc.file_id == fid
    assert doc.title == "Python 操作指南.pdf"
    assert len(doc.chunks) == 2
    assert doc.evidence_indices == [2, 3]
    assert all(chunk.chunk_id is not None for chunk in doc.chunks)
