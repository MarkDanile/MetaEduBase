"""Tests for TD-085 Slice B — ``runtime/application/prompt_builder.py``.

判别点（固定 fixture 逐字比对，锁定拆分前 ``AIChatService._build_prompt_context``
/ user_content 拼装行为）：

1. 空 blocks → 空字符串。
2. 单 block 渲染格式：`[idx] 来源: label | 标题: ... | 命中: channels` + content。
3. 非 "hit" expansion_type 追加 `` [tag]``；"hit" 不追加。
4. channels 为空 → "—" 占位。
5. block.title 为空 → 回退 ev.title；evidence_index 越界 → source_label 用
   block.source_type 且标题回退为 evidence_index。
6. source_type → 中文 label 映射（chunk / knowledge_node / knowledge_edge /
   structured_field / unknown / 其他原样）。
7. build_user_content：有/无 context_text 两态 byte-identical。

所有 fixture 使用真实 ``context_packer`` DTO + ``EvidenceItem``，不连接
DB / LLM。
"""

from __future__ import annotations

from app.contexts.knowledge.application.context_packer import (
    PackedContext,
    PackedContextBlock,
    PackedContextDiagnostics,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.runtime.application.prompt_builder import (
    build_prompt_context,
    build_user_content,
)


def _evidence(title: str = "证据标题", source_type: str = "chunk") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev-{source_type}",
        source_type=source_type,
        title=title,
        content="正文",
    )


def _packed(
    blocks: list[PackedContextBlock], evidence: list[EvidenceItem]
) -> PackedContext:
    return PackedContext(
        blocks=blocks,
        evidence=evidence,
        diagnostics=PackedContextDiagnostics(fused_count=len(evidence)),
    )


def _block(
    idx: int,
    *,
    title: str = "块标题",
    content: str = "块正文",
    channels: list[str] | None = None,
    expansion_type: str = "hit",
    source_type: str = "chunk",
) -> PackedContextBlock:
    return PackedContextBlock(
        evidence_index=idx,
        source_type=source_type,
        title=title,
        content=content,
        channels=channels or [],
        expansion_type=expansion_type,
    )


# --- 1. 空 blocks ----------------------------------------------------------


def test_empty_blocks_returns_empty_string():
    packed = _packed([], [])
    assert build_prompt_context(packed) == ""


# --- 2-4. 渲染格式 ----------------------------------------------------------


def test_single_block_hit_format_byte_exact():
    packed = _packed(
        [_block(1, content="第一段正文", channels=["vector", "keyword"])],
        [_evidence()],
    )
    ctx = build_prompt_context(packed)
    assert ctx == (
        "\n\n参考证据：\n"
        "[1] 来源: chunk | 标题: 块标题 | 命中: vector,keyword\n"
        "第一段正文\n"
    )


def test_non_hit_expansion_type_appends_tag():
    packed = _packed(
        [_block(1, expansion_type="neighbor")],
        [_evidence()],
    )
    ctx = build_prompt_context(packed)
    assert "来源: chunk [neighbor] |" in ctx


def test_hit_expansion_type_has_no_tag():
    packed = _packed([_block(1, expansion_type="hit")], [_evidence()])
    ctx = build_prompt_context(packed)
    assert " [hit]" not in ctx


def test_empty_channels_render_placeholder():
    packed = _packed([_block(1, channels=[])], [_evidence()])
    ctx = build_prompt_context(packed)
    assert "命中: —" in ctx


# --- 5-6. 标签与回退 --------------------------------------------------------


def test_block_title_empty_falls_back_to_evidence_title():
    packed = _packed([_block(1, title="")], [_evidence(title="证据原名")])
    ctx = build_prompt_context(packed)
    assert "标题: 证据原名" in ctx


def test_evidence_index_out_of_range_uses_block_source_type():
    # evidence_index=5 但只有 1 个 evidence → ev=None → label=block.source_type
    # block.title 置空才能触发标题回退（title_part = block.title or ...）
    packed = _packed(
        [_block(5, title="", source_type="knowledge_edge")], [_evidence()]
    )
    ctx = build_prompt_context(packed)
    assert "来源: knowledge_edge" in ctx
    # 标题回退为 evidence_index 本身
    assert "标题: 5" in ctx


def test_source_type_label_mapping():
    for source_type, label in [
        ("chunk", "chunk"),
        ("knowledge_node", "knowledge_node"),
        ("knowledge_edge", "knowledge_edge"),
        ("structured_field", "structured_field"),
    ]:
        packed = _packed([_block(1)], [_evidence(source_type=source_type)])
        ctx = build_prompt_context(packed)
        assert f"来源: {label} " in ctx or f"来源: {label}\n" in ctx or (
            f"来源: {label} |" in ctx
        ), f"{source_type} mapping broken: {ctx!r}"


def test_multiple_blocks_numbering_follows_evidence_index():
    packed = _packed(
        [_block(2), _block(1)],
        [_evidence(title="甲"), _evidence(title="乙")],
    )
    ctx = build_prompt_context(packed)
    # block 顺序保持 packed.blocks 顺序，编号用各自 evidence_index
    assert ctx.index("[2]") < ctx.index("[1]")


# --- 7. user_content 两态 ---------------------------------------------------


def test_build_user_content_with_context():
    assert build_user_content("CTX", "问题X") == "CTX\n\n学生问题：问题X"


def test_build_user_content_without_context():
    assert build_user_content("", "问题X") == "学生问题：问题X"
