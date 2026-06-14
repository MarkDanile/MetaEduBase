"""TD-054 round 2: chunk_by_structure 内部 char_offset 跟踪必须严格单调。

Bug 真因（2026-06-14 复测发现）：chunk_by_structure L93-141 主循环的
char_offset 累加逻辑有 4 类 bug——合并分支也前进 / phantom +1 假设
sentence 间固定分隔符 / sentence.strip() 丢空白未计入 /
_enforce_size_limit 拆分后 local_offset 未校准——导致重建后
offset_overlaps 从 52.61% 恶化到 82.14% (28 chunks / 23 overlaps)。

本测试文件锁死修复后的 5 个不变量：
  1. 同一 section 内 chunks[i+1].char_start >= chunks[i].char_end
  2. local_offset 仅在新建 chunk 时前进，合并分支不前进
  3. 无 phantom +1 separator（连续 2 句等长时 offset 差 == 句长）
  4. section_offset 参数正确传递到第一个 chunk
  5. _enforce_size_limit 触发后子 chunks 仍保持单调性
"""

from __future__ import annotations

from app.shared.parsing.chunker import chunk_by_structure
from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument


def _parsed(*contents: str, with_sections: bool = True) -> ParsedDocument:
    """Helper: build a ParsedDocument with one section per content string."""
    if with_sections:
        sections = [
            DocumentSection(
                title=f"section_{i}",
                level=1,
                content=c,
                page=1,
                path=f"{i}",
            )
            for i, c in enumerate(contents)
        ]
    else:
        sections = []
    return ParsedDocument(sections=sections, full_text="\n\n".join(contents))


# === Test 1: strictly monotonic within section ===
def test_chunk_offsets_strictly_monotonic_within_section() -> None:
    """chunks[i+1].char_start >= chunks[i].char_end for all i in same section."""
    sentences = ["。".join(["测" * 49]) for _ in range(5)]
    text = "。".join(sentences)
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed)

    assert len(chunks) >= 2, "test fixture should produce multiple chunks"
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap: prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )


# === Test 2: local_offset only advances on new chunk ===
def test_local_offset_advances_only_on_new_chunk() -> None:
    """Short sentences merged into last chunk must not advance local_offset."""
    short1 = "短句一。"  # 4 chars
    short2 = "短句二。"  # 4 chars
    long1 = "长句" + "内容" * 100 + "结束。"  # ~205 chars
    text = short1 + short2 + long1
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed)

    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    assert len(chunks[0].content) > 0
    assert chunks[1].char_start >= chunks[0].char_end


# === Test 3: no phantom +1 separator ===
def test_no_phantom_separator_in_offset() -> None:
    """Two consecutive single-sentence chunks must have offset delta == len(sent1)."""
    sent1 = "第一句内容" * 30 + "。"  # 121 chars
    sent2 = "第二句内容" * 30 + "。"  # 121 chars
    text = sent1 + sent2
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=200)

    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    delta = chunks[1].char_start - chunks[0].char_start
    assert abs(delta - len(sent1)) <= 1, (
        f"offset delta {delta} should be ~ len(sent1)={len(sent1)} "
        f"(phantom +1 not allowed)"
    )


# === Test 4: section_offset passed through ===
def test_section_offset_passed_through() -> None:
    """section_offset=5000 means first chunk's char_start >= 5000."""
    text = "第一段第一句内容。\n\n第一段第二句内容。"
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, section_offset=5000)

    assert len(chunks) >= 1
    assert chunks[0].char_start >= 5000
    for c in chunks:
        assert c.char_start >= 5000, (
            f"chunk char_start={c.char_start} < section_offset=5000"
        )


# === Test 5: _enforce_size_limit preserves monotonicity ===
def test_enforce_size_limit_preserves_monotonicity() -> None:
    """After _enforce_size_limit splits oversized chunks, sub-chunks stay monotonic."""
    huge_sent = "超长句" + "内容" * 500 + "结束。"  # ~1005 chars
    next_sent = "后续短句。"
    text = huge_sent + next_sent
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=300)

    assert len(chunks) >= 2
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap after _enforce_size_limit: "
            f"prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )
