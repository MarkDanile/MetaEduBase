"""`ContextPacker` tests — REQ-013 Slice 1/2.

覆盖：
- is_toc_like_chunk() 规则识别
- neighbor expansion：命中 chunk 51 → blocks 含 50/51/52
- 边界 chunk 0 不请求负 index
- 重复 evidence 去重
- TOC guard：目录 chunk 被降到 prompt 尾部，但不出现在 evidence 列表外
- 字符预算裁剪
- 块数预算裁剪
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.knowledge.application.context_packer import (
    ContextPacker,
    ContextPackingOptions,
    is_toc_like_chunk,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem

# ---------------------------------------------------------------------------
# Fake ChunkRepository
# ---------------------------------------------------------------------------

class FakeChunkRepo:
    """Fake implementing the ChunkRepositoryInterface used by ContextPacker."""

    def __init__(self, chunks: dict[uuid.UUID, list[dict]]) -> None:
        # chunks[fid] = list of {chunk_index, id, content, section_title, section_path}
        self._chunks = chunks

    async def get_chunks_by_file_and_indices(
        self,
        file_id: uuid.UUID,
        indices: list[int],
        tenant_id: uuid.UUID,
    ) -> dict[int, dict]:
        if file_id not in self._chunks:
            return {}
        rows = {row["chunk_index"]: row for row in self._chunks[file_id]}
        return {i: rows[i] for i in indices if i in rows}

    async def get_chunk_by_id(self, chunk_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        for f_chunks in self._chunks.values():
            for row in f_chunks:
                if row.get("id") == chunk_id:
                    return row
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def toc_chunk(fid) -> EvidenceItem:
    """High-score TOC / 目录 chunk — the "problem" in the failure scenario."""
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="目录",
        content=(
            "第 1 章 Python 基础 ........................... 1\n"
            "第 2 章 数据类型和变量 ......................... 5\n"
            "第 3 章 运算符和表达式 ......................... 9\n"
        ),
        snippet="目录",
        score=0.95,
        metadata={"chunk_index": 0, "section_path": "1", "section_title": "目录"},
    )


@pytest.fixture
def body_chunk(fid) -> EvidenceItem:
    """Lower-score 正文 chunk that should dominate the prompt."""
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="基本数据类型和变量",
        content=(
            "Python 的基本数据类型包括数字（int、float、complex）、字符串（str）、"
            "布尔值（bool）、列表（list）、元组（tuple）和字典（dict）。"
            "变量不需要声明类型，直接赋值即可使用。"
        ),
        snippet="Python 的基本数据类型包括数字、字符串...",
        score=0.85,
        metadata={"chunk_index": 3, "section_path": "1.1", "section_title": "基本数据类型和变量"},
    )


@pytest.fixture
def neighbor_chunks(fid) -> dict[uuid.UUID, list[dict]]:
    """Simulated DB rows for indices 2/3/4 around the body chunk (index 3)."""
    return {
        fid: [
            {
                "chunk_index": 2,
                "id": uuid.uuid4(),
                "content": "上一节介绍了 Python 的安装和环境配置。",
                "section_title": "环境配置",
                "section_path": "1.0",
            },
            {
                "chunk_index": 3,
                "id": uuid.uuid4(),
                "content": (
                    "Python 的基本数据类型包括数字（int、float、complex）、字符串（str）、"
                    "布尔值（bool）、列表（list）、元组（tuple）和字典（dict）。"
                    "变量不需要声明类型，直接赋值即可使用。"
                ),
                "section_title": "基本数据类型和变量",
                "section_path": "1.1",
            },
            {
                "chunk_index": 4,
                "id": uuid.uuid4(),
                "content": "在学习完数据类型后，接下来介绍运算符和表达式。",
                "section_title": "运算符和表达式",
                "section_path": "1.2",
            },
        ]
    }


# ---------------------------------------------------------------------------
# is_toc_like_chunk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "title,content,expected",
    [
        ("目录", "第 1 章 Python … 12\n第 2 章 … 5\n", True),
        ("Table of Contents", "Chapter 1 ... 1", True),
        ("第 1 章 Python 基础", "Python 基础内容… 12", False),  # title looks like heading, not TOC
        ("基本数据类型", "Python 的基本数据类型包括数字、字符串…", False),
        ("", "", False),
    ],
)
def test_is_toc_like_chunk(title: str, content: str, expected: bool) -> None:
    assert is_toc_like_chunk(title, content) == expected


# ---------------------------------------------------------------------------
# Slice 1: failure scenario — TOC高分 + 正文存在
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toc_guard_promotes_body_over_toc(
    fid, tenant_id, toc_chunk, body_chunk, neighbor_chunks
) -> None:
    """TOC chunk scores higher but body chunk content should dominate the prompt.

    Scenario: "Python 的基本数据类型有哪些？" asked on a Python tutorial.
    Vector search ranks TOC chunk (score=0.95) above body chunk (score=0.85).
    ContextPacker should still surface the body chunk content in the prompt,
    leaving TOC chunk as a navigation evidence item but not the sole context.
    """
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Evidence: TOC score=0.95, body score=0.85 — same file, different indices
    evidence = [toc_chunk, body_chunk]

    packed = await packer.pack(evidence)

    # TOC block must exist (TOC guard keeps it, just deprioritizes)
    toc_blocks = [b for b in packed.blocks if b.is_toc_like]
    body_blocks = [b for b in packed.blocks if not b.is_toc_like]

    assert len(toc_blocks) >= 1, "TOC block should be retained (guard = deprioritize, not drop)"
    assert len(body_blocks) >= 1, "Body chunk block should be included"

    # Body content must appear in prompt (not replaced by TOC)
    all_content = "\n".join(b.content for b in packed.blocks)
    assert "Python 的基本数据类型包括" in all_content, (
        "Body chunk content must appear in packed blocks — "
        "TOC should not be the sole context"
    )


@pytest.mark.asyncio
async def test_toc_guard_toc_block_not_only_context(
    fid, tenant_id, toc_chunk, body_chunk, neighbor_chunks
) -> None:
    """When TOC is the only chunk, guard should still allow it (no body to promote)."""
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Only TOC in evidence — no body to promote
    packed = await packer.pack([toc_chunk])

    assert len(packed.blocks) >= 1
    # Should still work, just with TOC content
    assert packed.diagnostics.toc_blocks_count == 1


# ---------------------------------------------------------------------------
# Slice 2: neighbor expansion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_neighbor_expansion_includes_adjacent_chunks(
    fid, tenant_id, body_chunk, neighbor_chunks
) -> None:
    """Hit chunk index=3 → blocks should include 2/3/4."""
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    packed = await packer.pack([body_chunk])

    # Should have hit + 2 neighbors
    hit_blocks = [b for b in packed.blocks if b.expansion_type == "hit"]
    neighbor_blocks = [b for b in packed.blocks if b.expansion_type == "neighbor"]

    assert len(hit_blocks) == 1
    assert len(neighbor_blocks) == 2, (
        f"Expected 2 neighbor blocks (index 2 and 4), got {len(neighbor_blocks)}"
    )
    assert all(b.expansion_type == "neighbor" for b in neighbor_blocks)


@pytest.mark.asyncio
async def test_neighbor_expansion_never_requests_negative_index(
    fid, tenant_id, neighbor_chunks
) -> None:
    """Chunk index=0 should not request -1 neighbor."""
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Manually create evidence for index=0 (chunk 0 — boundary)
    chunk0 = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="目录",
        content="目录内容",
        score=0.9,
        metadata={"chunk_index": 0},
    )

    packed = await packer.pack([chunk0])

    # No crash, and neighbor blocks only include index 0 and 1 (not -1)
    neighbor_blocks = [b for b in packed.blocks if b.expansion_type == "neighbor"]
    # chunk_index 0: neighbors should be [0] only (clamped at 0)
    # with window=1, range is [max(0, -1), 0+1] = [0, 1]
    # chunk 0 itself is the hit, chunk 1 is a valid neighbor
    assert all(
        (b.metadata.get("chunk_index") or 0) >= 0 for b in neighbor_blocks if b.metadata
    ), "Neighbor indices must never be negative"


@pytest.mark.asyncio
async def test_duplicate_evidence_same_chunk_appears_once(
    fid, tenant_id, body_chunk, neighbor_chunks
) -> None:
    """Same chunk hit by two channels appears only once in packed blocks."""
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Same evidence item duplicated — simulating vector + keyword both hitting same chunk
    evidence = [body_chunk, body_chunk]

    packed = await packer.pack(evidence)

    hit_blocks = [b for b in packed.blocks if b.expansion_type == "hit"]
    # Should de-duplicate to 1 hit block
    assert len(hit_blocks) == 1


# ---------------------------------------------------------------------------
# Slice 2: budget enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_chars_trims_blocks(fid, tenant_id, neighbor_chunks) -> None:
    """When total packed chars exceed max_chars, lower-ranked blocks are dropped."""
    body_chunk = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="Body",
        content="A" * 3000,
        score=0.9,
        metadata={"chunk_index": 3},
    )
    low_chunk = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="Low",
        content="B" * 3000,
        score=0.1,
        metadata={"chunk_index": 4},
    )

    repo = FakeChunkRepo(neighbor_chunks)
    opts = ContextPackingOptions(max_chars=1500, neighbor_window=0)
    packer = ContextPacker(repo, tenant_id, options=opts)

    packed = await packer.pack([body_chunk, low_chunk])

    total_chars = sum(len(b.content) for b in packed.blocks)
    assert total_chars <= 1500, f"Total chars {total_chars} exceeds budget 1500"


@pytest.mark.asyncio
async def test_max_blocks_trims(fid, tenant_id, neighbor_chunks) -> None:
    """When more blocks than max_blocks, only top-scoring survive."""
    blocks = []
    for i in range(10):
        blocks.append(EvidenceItem(
            evidence_id="",
            source_type="chunk",
            file_id=fid,
            chunk_id=uuid.uuid4(),
            title=f"Chunk {i}",
            content=f"content for chunk {i}",
            score=0.9 - i * 0.08,
            metadata={"chunk_index": i},
        ))

    repo = FakeChunkRepo(neighbor_chunks)
    opts = ContextPackingOptions(max_blocks=3, neighbor_window=0)
    packer = ContextPacker(repo, tenant_id, options=opts)

    packed = await packer.pack(blocks)

    assert len(packed.blocks) <= 3


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_diagnostics_count_toc_blocks(
    fid, tenant_id, toc_chunk, body_chunk, neighbor_chunks
) -> None:
    """Diagnostics must correctly count TOC-like blocks."""
    repo = FakeChunkRepo(neighbor_chunks)
    packer = ContextPacker(repo, tenant_id)

    packed = await packer.pack([toc_chunk, body_chunk])

    assert packed.diagnostics.toc_blocks_count == 1
    assert packed.diagnostics.fused_count == 2
    assert packed.diagnostics.total_blocks_before_trim >= 2


# ---------------------------------------------------------------------------
# Slice 3: graph-to-chunk expansion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_evidence_fetches_source_chunk_and_neighbors(fid, tenant_id) -> None:
    """AC-3: graph evidence with source_chunk_id fetches the chunk content."""
    source_cid = uuid.uuid4()
    neighbor_cid = uuid.uuid4()
    # Simulate DB rows: source chunk + one neighbor
    db_chunks = {
        fid: [
            {
                "chunk_index": 5,
                "id": source_cid,
                "content": "Python 的基本数据类型包括数字、字符串、布尔值等。",
                "section_title": "基本数据类型",
                "section_path": "1.2",
            },
            {
                "chunk_index": 4,
                "id": neighbor_cid,
                "content": "上一节介绍了环境配置。",
                "section_title": "环境配置",
                "section_path": "1.1",
            },
        ]
    }
    repo = FakeChunkRepo(db_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Knowledge node evidence pointing to source chunk
    node_ev = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        node_id=uuid.uuid4(),
        source_chunk_id=source_cid,
        chunk_id=source_cid,
        title="Python 数据类型节点",
        content="node desc",
        score=0.9,
        channels=["graph"],
    )

    packed = await packer.pack([node_ev])

    # Should have graph_source block + neighbor block
    graph_blocks = [b for b in packed.blocks if b.expansion_type == "graph_source"]
    assert len(graph_blocks) == 1
    assert "Python 的基本数据类型包括" in graph_blocks[0].content
    assert packed.diagnostics.graph_chunks_fetched == 1


@pytest.mark.asyncio
async def test_graph_evidence_no_source_chunk_id_skips_gracefully(fid, tenant_id) -> None:
    """Graph evidence without source_chunk_id does not crash."""
    node_ev = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        node_id=uuid.uuid4(),
        source_chunk_id=None,
        chunk_id=None,
        title="orphan node",
        content="node desc",
        score=0.9,
        channels=["graph"],
    )
    repo = FakeChunkRepo({})
    packer = ContextPacker(repo, tenant_id)

    packed = await packer.pack([node_ev])
    # Should not crash — blocks may be empty but no exception
    assert packed.diagnostics.graph_chunks_fetched == 0


# ---------------------------------------------------------------------------
# Slice 3: section expansion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_section_expansion_adds_same_section_chunks(fid, tenant_id) -> None:
    """Same-section chunks are included when section_path is stable."""
    db_chunks = {
        fid: [
            {
                "chunk_index": 3,
                "id": uuid.uuid4(),
                "content": "Python 变量不需要声明类型，直接赋值即可使用。",
                "section_title": "变量与赋值",
                "section_path": "1.1",
            },
            {
                "chunk_index": 4,
                "id": uuid.uuid4(),
                "content": "数字类型包括 int、float 和 complex。",
                "section_title": "数字类型",
                "section_path": "1.1",
            },
            {
                "chunk_index": 5,
                "id": uuid.uuid4(),
                "content": "字符串用单引号或双引号创建。",
                "section_title": "字符串类型",
                "section_path": "1.2",
            },
        ]
    }
    repo = FakeChunkRepo(db_chunks)
    packer = ContextPacker(repo, tenant_id)

    # Evidence points to chunk_index=3 (section_path="1.1")
    chunk_ev = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=db_chunks[fid][0]["id"],
        title="变量与赋值",
        content=db_chunks[fid][0]["content"],
        score=0.9,
        metadata={"chunk_index": 3, "section_path": "1.1", "section_title": "变量与赋值"},
    )

    packed = await packer.pack([chunk_ev])

    section_blocks = [b for b in packed.blocks if b.expansion_type == "section"]
    # Should include chunk 4 (same section "1.1") as section block
    assert len(section_blocks) >= 1
    section_contents = " ".join(b.content for b in section_blocks)
    assert "数字类型包括" in section_contents


@pytest.mark.asyncio
async def test_section_expansion_skips_bad_section_path(fid, tenant_id) -> None:
    """When section_path is empty or "?", section expansion is skipped gracefully."""
    db_chunks = {
        fid: [
            {
                "chunk_index": 0,
                "id": uuid.uuid4(),
                "content": "Some content",
                "section_title": "Unknown",
                "section_path": "?",  # bad path
            },
        ]
    }
    repo = FakeChunkRepo(db_chunks)
    packer = ContextPacker(repo, tenant_id)

    chunk_ev = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=db_chunks[fid][0]["id"],
        title="Unknown",
        content="Some content",
        score=0.9,
        metadata={"chunk_index": 0, "section_path": "?"},
    )

    packed = await packer.pack([chunk_ev])
    # Should not crash; section expansion skipped
    assert packed.diagnostics.sections_fallback_triggered is False

