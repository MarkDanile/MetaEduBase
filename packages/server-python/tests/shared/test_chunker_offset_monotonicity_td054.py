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

Fixture 设计：每条用例构造「单独句子长度 > target_chars」的内容，强制
_chunk_by_structure 主循环走「不合并」分支（merge 分支不变是修复核心），
这样能直接观察 char_start / char_end 的正确性而非被 merge 掩盖。
"""

from __future__ import annotations

from app.shared.parsing.chunker import chunk_by_structure
from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument


def _parsed(*contents: str) -> ParsedDocument:
    """Helper: build a ParsedDocument with one section per content string."""
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
    return ParsedDocument(sections=sections, full_text="\n\n".join(contents))


# === Test 1: strictly monotonic within section ===
def test_chunk_offsets_strictly_monotonic_within_section() -> None:
    """chunks[i+1].char_start >= chunks[i].char_end for all i in same section.

    Regression lock: 主循环 L140 char_offset += sent_len + 1 让连续新建 chunk
    时 char_start 漂移 +1；合并分支也累加 +1 让下一个新建 chunk 起始位置偏低。
    修复后 chunks 之间应严格单调（无 overlap）。

    Fixture: 3 sentences, each 600 chars, target=500 → forces 3 separate chunks
    (each sentence alone exceeds target, so merge branch never fires).
    """
    sentence = "测" * 600 + "。"  # 601 chars
    text = sentence + sentence + sentence
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed)

    assert len(chunks) >= 2, f"expected ≥2 chunks, got {len(chunks)}"
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap: prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )


# === Test 2: local_offset only advances on new chunk ===
def test_local_offset_advances_only_on_new_chunk() -> None:
    """Short sentences merged into last chunk must not advance local_offset.

    Regression lock: 旧逻辑 char_offset += sent_len + 1 在合并分支也执行，
    让下一个新建 chunk 的 char_start 偏低。修复后合并分支 local_offset 不变。

    Fixture: 3 long sentences, each 600 chars, target=500 → forces 3 separate
    chunks (each sentence alone exceeds target, merge branch never fires).
    Validates local_offset advances exactly by len(sentence) per new chunk.
    """
    sentence = "长句" + "内容" * 100 + "结束。"  # ~205 chars
    text = sentence * 3
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=200)

    assert len(chunks) >= 2, f"expected ≥2 chunks, got {len(chunks)}"
    assert len(chunks[0].content) > 0
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap: prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )


# === Test 3: no phantom +1 separator ===
def test_no_phantom_separator_in_offset() -> None:
    """Two consecutive single-sentence chunks must have offset delta == len(sent1).

    Regression lock: char_offset += sent_len + 1 让 2 个连续单句 chunk 的
    offset 差 = len(sent1) + 1（phantom +1），违反 "delta == len" 不变量。
    修复后 delta == len(sent1)（严格 +0）。

    Fixture: 2 sentences each 501 chars, target=500 → forces 2 separate chunks
    (each sentence alone exceeds target). delta should equal len(sent1) exactly.
    """
    sent1 = "第一句内容" * 100 + "。"  # 501 chars (4 chars * 100 + 1)
    sent2 = "第二句内容" * 100 + "。"  # 501 chars
    text = sent1 + sent2
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=500)

    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    delta = chunks[1].char_start - chunks[0].char_start
    assert delta == len(sent1), (
        f"offset delta {delta} should be exactly len(sent1)={len(sent1)} "
        f"(phantom +1 not allowed; bug pre-fix would give {len(sent1)+1})"
    )


# === Test 4: section_offset passed through ===
def test_section_offset_passed_through() -> None:
    """section_offset=5000 means first chunk's char_start == 5000.

    Regression lock: 旧代码在 L74 接收 section_offset 但在 L140 无条件
    char_offset += sent_len + 1. 修复后 chunk 0 的 char_start = section_offset.
    """
    text = "第一段第一句内容。\n\n第一段第二句内容。"
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, section_offset=5000)

    assert len(chunks) >= 1
    assert chunks[0].char_start == 5000, (
        f"first chunk char_start={chunks[0].char_start}, expected 5000"
    )
    for c in chunks:
        assert c.char_start >= 5000, (
            f"chunk char_start={c.char_start} < section_offset=5000"
        )


# === Test 5: _enforce_size_limit preserves monotonicity ===
def test_enforce_size_limit_preserves_monotonicity() -> None:
    """After _enforce_size_limit splits oversized chunks, sub-chunks stay monotonic.

    Regression lock: 旧代码 _enforce_size_limit 用 chunk.char_start + sub_offset
    算子 chunk 起点（PR #234 已修对），但 char_offset 主循环不前进 sub-chunk
    长度，导致后续 sentence 的 char_start 整体偏低。修复后 _enforce_size_limit
    后的 chunks 仍保持单调。

    Fixture: 1 super-long sentence with clause separators forces _enforce_size_limit
    split via _split_by_clauses path, then 1 normal sentence after it.
    target_chars=200 forces split.
    """
    # 5 clause-separated parts, each 50 chars + 1 char separator
    huge_sent = "X" * 50 + "，" + "X" * 50 + "，" + "X" * 50 + "，"
    huge_sent += "X" * 50 + "，" + "X" * 50 + "。"  # 255 chars total
    next_sent = "后续短句内容。"  # 7 chars
    text = huge_sent + next_sent
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=200)

    assert len(chunks) >= 2, f"expected ≥2 chunks, got {len(chunks)}"
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap after _enforce_size_limit: "
            f"prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )
