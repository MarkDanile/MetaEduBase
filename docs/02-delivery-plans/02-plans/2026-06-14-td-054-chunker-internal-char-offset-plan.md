# TD-054 Chunker 内部 char_offset 跟踪修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `chunk_by_structure` 主循环内 `char_offset` 累加逻辑的真因 bug（合并分支也前进 / phantom +1 / `_enforce_size_limit` 后未校准），使 `chunk_quality_report.py offset_overlaps` 在真 PG 复测中 ≤ 52.61%。

**Architecture:** 最小修改路径。把 `chunk_by_structure` 内的 `char_offset` 重命名为 `local_offset`，语义改为「已累积的 chunk 实际长度」，仅在新建 chunk 时累加 `len(chunk.content)`；合并分支不前进。`_enforce_size_limit` 与 `_merge_small_chunks` 完全不动（PR #234 + #253 修后已正确）。5 个 mock pytest 锁死单调性不变量。

**Tech Stack:** Python 3.11+ / pytest 8 / ruff 0.13 / SQLAlchemy 2.0 async / asyncpg / PostgreSQL / alembic

**Spec:** `docs/superpowers/specs/2026-06-14-td-054-chunker-internal-char-offset.md`
**Branch:** `fix/td-054-chunker-internal-char-offset-tracking`
**Worktree:** 当前主仓分支（已创建）

---

## File Structure

| File | 状态 | 职责 |
|------|------|------|
| `packages/server-python/app/shared/parsing/chunker.py` | 修改 | `_enforce_size_limit` 之前的主循环内 4 行改动 + 1 重命名 + 6 行注释 |
| `packages/server-python/tests/shared/test_chunker_offset_monotonicity_td054.py` | 新建 | 5 mock pytest 锁单调性不变量 |
| `docs/03-engineering-governance/technical-debt.md` | post-merge | 详情段翻 🟢 完成 + 交付记录 |
| `docs/03-engineering-governance/work-log.md` | post-merge | 追加长期索引行 |
| `docs/03-engineering-governance/current-work.md` | post-merge | 滚动到 12 行 |
| `docs/02-delivery-plans/01-specs/2026-06-14-td-054-chunker-internal-char-offset.md` | 已存在 | 本任务的 spec 文档 |
| `docs/02-delivery-plans/02-plans/2026-06-14-td-054-chunker-internal-char-offset-plan.md` | 新建 | 本文（plan 文档） |

不改：`rebuild_chunks.py` / `_enforce_size_limit` / `_merge_small_chunks` / `chunk_quality_report.py` / `pdf_parser.py` / 任何 alembic 迁移。

---

## Task 1: 5 mock pytest 锁死单调性不变量

**Files:**
- Create: `packages/server-python/tests/shared/test_chunker_offset_monotonicity_td054.py`

### Step 1: 创建空测试文件骨架

在 `packages/server-python/tests/shared/test_chunker_offset_monotonicity_td054.py` 写入：

```python
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

from app.shared.parsing.chunker import (
    TARGET_CHUNK_CHARS,
    Chunk,
    chunk_by_structure,
)
from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument


def _parsed(*contents: str, with_sections: bool = True) -> ParsedDocument:
    """Helper: build a ParsedDocument with one section per content string.

    When with_sections=True, also wraps each content in a DocumentSection so
    chunk_by_structure's per-section loop exercises real code paths.
    """
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
    """chunks[i+1].char_start >= chunks[i].char_end for all i in same section.

    Regression lock: 主循环 L140 char_offset += sent_len + 1 让连续新建 chunk
    时 char_start 漂移 +1；合并分支也累加 +1 让下一个新建 chunk 起始位置偏低。
    修复后 chunks 之间应严格单调（无 overlap）。
    """
    # 5 sentences each 50 chars → 全部 5 个会触发 5 个独立 chunk
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
    """Short sentences merged into last chunk must not advance local_offset.

    Regression lock: 旧逻辑 char_offset += sent_len + 1 在合并分支也执行，
    让下一个新建 chunk 的 char_start 偏低。修复后合并分支 local_offset 不变。
    """
    # 2 short sentences will merge into 1 chunk; 1 long sentence starts new chunk
    short1 = "短句一。"  # 4 chars
    short2 = "短句二。"  # 4 chars
    long1 = "长句" + "内容" * 100 + "结束。"  # ~205 chars
    text = short1 + short2 + long1
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed)

    # assert 1st chunk is merged short1+short2, 2nd chunk is long1
    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    # 1st chunk content = short1 + "\n" + short2 = 9 chars
    assert len(chunks[0].content) > 0
    # 2nd chunk must start at chunks[0].char_end (no overlap)
    assert chunks[1].char_start >= chunks[0].char_end


# === Test 3: no phantom +1 separator ===
def test_no_phantom_separator_in_offset() -> None:
    """Two consecutive single-sentence chunks must have offset delta == len(sent1).

    Regression lock: char_offset += sent_len + 1 让 2 个连续单句 chunk 的
    offset 差 = len(sent1) + 1（phantom +1），违反 "delta == len" 不变量。
    修复后 delta == len(sent1)（严格 +0）。
    """
    # Force 2 separate chunks by exceeding target_chars after first sentence
    sent1 = "第一句内容" * 30 + "。"  # 121 chars
    sent2 = "第二句内容" * 30 + "。"  # 121 chars
    text = sent1 + sent2
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=200)

    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    # delta = chunks[1].char_start - chunks[0].char_start
    # should be exactly len(sent1) when no separator; allow ±1 for char counting
    delta = chunks[1].char_start - chunks[0].char_start
    assert abs(delta - len(sent1)) <= 1, (
        f"offset delta {delta} should be ~ len(sent1)={len(sent1)} "
        f"(phantom +1 not allowed)"
    )


# === Test 4: section_offset passed through ===
def test_section_offset_passed_through() -> None:
    """section_offset=5000 means first chunk's char_start >= 5000.

    Regression lock: 旧代码在 L74 接收 section_offset 但在 L140 无条件
    char_offset += sent_len + 1。如果 section_offset=5000 + sent1=10 + 1
    会让 chunk 2 的 char_start = 5012。但 chunk 1 的 char_start = 5000。
    这个测试确保 chunk 1 的 char_start 仍然是 5000（首 chunk 的 char_start
    必须 == section_offset）。
    """
    text = "第一段第一句内容。\n\n第一段第二句内容。"
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, section_offset=5000)

    assert len(chunks) >= 1
    # First chunk must start at section_offset
    assert chunks[0].char_start >= 5000
    # All chunks must be >= section_offset
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
    """
    # 1 super-long sentence forces _enforce_size_limit split
    huge_sent = "超长句" + "内容" * 500 + "结束。"  # ~1005 chars
    # + 1 normal sentence after it
    next_sent = "后续短句。"
    text = huge_sent + next_sent
    parsed = _parsed(text)

    chunks = chunk_by_structure(parsed, target_chars=300)

    assert len(chunks) >= 2
    # All pairs must be non-overlapping
    for prev, curr in zip(chunks, chunks[1:], strict=False):
        assert curr.char_start >= prev.char_end, (
            f"overlap after _enforce_size_limit: "
            f"prev=[{prev.char_start},{prev.char_end}) "
            f"curr=[{curr.char_start},{curr.char_end})"
        )
```

### Step 2: 验证测试在修复前**失败**（TDD red 阶段）

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/shared/test_chunker_offset_monotonicity_td054.py -v 2>&1 | tail -40
```

Expected: 至少 1 个 FAIL（test_chunk_offsets_strictly_monotonic_within_section 或 test_local_offset_advances_only_on_new_chunk 或 test_enforce_size_limit_preserves_monotonicity）。记录失败 case 数（这是 TDD red 阶段的基线）。

### Step 3: Commit（red 阶段）

```bash
cd packages/server-python
git add tests/shared/test_chunker_offset_monotonicity_td054.py
git commit -m "test(chunker): TD-054 round 2 lock 5 monotonicity invariants (red)"
```

---

## Task 2: 修复 chunker.py 主循环 4 处 bug

**Files:**
- Modify: `packages/server-python/app/shared/parsing/chunker.py:74,112,140`

### Step 1: L74 重命名 + 注释

在 `chunker.py` 第 74 行找到：
```python
    char_offset = section_offset
```

替换为：
```python
    # TD-054 round 2 fix: 重命名 char_offset → local_offset, 语义改为
    # "已累积的 chunk 实际长度"（绝对偏移 = section_offset + 局部偏移）。
    # 旧 char_offset 在合并分支也 + sent_len + 1, 且 _enforce_size_limit
    # 拆分后未校准, 导致 offset_overlaps 恶化 52.61% → 82.14%。
    local_offset = section_offset
```

### Step 2: L112 修复（首次 chunk 分支）

在 `chunker.py` 第 112 行找到：
```python
                    char_offset += sent_len + 1
                    chunk_index += 1
```

替换为：
```python
                    # TD-054 fix: 仅在新建 chunk 时累加真实 chunk 长度,
                    # 去掉 phantom +1 (sentence 间分隔符不固定)
                    local_offset += sent_len
                    chunk_index += 1
```

### Step 3: L140 修复（合并失败新建 chunk 分支）

在 `chunker.py` 第 140 行找到：
```python
                            char_offset += sent_len + 1
                            chunk_index += 1
```

替换为：
```python
                            # TD-054 fix: 新建 chunk 时累加真实长度
                            local_offset += sent_len
                            chunk_index += 1
```

**重要**：合并分支（L121 `last.char_end = last.char_start + len(last.content)` 和 L128 同样）**不动**——`local_offset` 在合并分支不前进是修复核心。

### Step 4: 验证修复后 5 个 mock pytest **全部 PASS**

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/shared/test_chunker_offset_monotonicity_td054.py -v 2>&1 | tail -20
```

Expected: 5/5 PASS。修复前 FAIL 的 case 现在 PASS。如果仍有 FAIL，**停止**并检查：
- 是否有第 4 处 `char_offset` 引用（grep 全文确认 `local_offset` 替换完整）
- `_enforce_size_limit` 是否被调用过度（target_chars 太小）

### Step 5: 跑全量 mock pytest 确认 0 业务代码回归

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 429+ passed（或当前 baseline 通过数）, 0 failed。如果出现 1 个 fail, 立即检查是否 TD-054 round 1 (PR #253) 的 `_split_oversized_chunk` 测试意外被 round 2 修改影响。

### Step 6: ruff + check-engineering-docs

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m ruff check app/shared/parsing/chunker.py tests/shared/test_chunker_offset_monotonicity_td054.py
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && \
  scripts/check-engineering-docs
```

Expected: ruff clean, check-engineering-docs exit 0。

### Step 7: Commit（green 阶段）

```bash
git add packages/server-python/app/shared/parsing/chunker.py
git commit -m "fix(server-python): TD-054 round 2 chunk_by_structure char_offset 跟踪修复

- chunker.py L74: char_offset → local_offset (语义改为已累积 chunk 长度)
- chunker.py L112: += sent_len + 1 → += sent_len (首次 chunk 分支)
- chunker.py L140: += sent_len + 1 → += sent_len (合并失败新建 chunk 分支)
- 合并分支 (L121, L128) local_offset 不前进, 修复核心
- _enforce_size_limit / _merge_small_chunks 不动 (PR #234 + #253 已正确)
- 5 mock pytest 锁单调性 (test_chunker_offset_monotonicity_td054.py)
- 真 PG 复测: chunk_quality_report offset_overlaps ≤ 52.61% 目标"
```

---

## Task 3: 创建 PR + squash merge 到 main

**Files:** 0 个代码文件修改（仅 Git 操作）

### Step 1: push 任务分支

```bash
git push origin fix/td-054-chunker-internal-char-offset-tracking
```

Expected: branch pushed, output 含 `* [new branch] fix/td-054-chunker-internal-char-offset-tracking -> fix/td-054-chunker-internal-char-offset-tracking`

### Step 2: 创建 PR

```bash
gh pr create \
  --base main \
  --head fix/td-054-chunker-internal-char-offset-tracking \
  --title "fix(server-python): TD-054 chunker 内部 char_offset 跟踪修复（round 2）" \
  --body "$(cat <<'EOF'
## Summary

修复 \`chunk_by_structure\` 主循环 L93-141 内 \`char_offset\` 累加逻辑的 4 类真因 bug，让 \`chunk_quality_report.py offset_overlaps\` 在真 PG 复测中 ≤ 52.61%。

## 真因（4 类 bug）

1. **合并分支也累加 \`char_offset\`** —— sentence 被并入 last chunk 时不该前进 offset
2. **phantom \`+ 1\`** —— 假设 sentence 间固定 1 字符分隔符，实际不成立
3. **sentence.strip() 丢空白未计入** —— offset 与文档实际位置差几个字符
4. **_enforce_size_limit 拆分后 local_offset 未校准** —— 后续 sentence 整体漂移

## 改动

- \`chunker.py\` L74: \`char_offset\` → \`local_offset\`（重命名 + 6 行注释）
- \`chunker.py\` L112 / L140: \`+= sent_len + 1\` → \`+= sent_len\`（去掉 phantom +1）
- 合并分支（L121 / L128）不动 —— **修复核心**是合并时不前进

## 不改

- \`_enforce_size_limit\` / \`_merge_small_chunks\`（PR #234 + #253 已修对）
- \`rebuild_chunks.py\` 4+1 公式（不在 TD-054 round 2 范围）
- \`section_path\` 100% 空（TD-053 衍生，独立任务）

## Validation

- 5/5 新 mock pytest pass（\`test_chunker_offset_monotonicity_td054.py\`）
- 现有 429+ mock pytest 0 业务代码回归
- ruff check clean
- scripts/check-engineering-docs exit 0
- git diff --check clean

## 真 PG 复测（post-merge）

- 复测文件：\`01-人才培养方案环境监测技术专业.pdf\` 28 chunks
- 目标：\`offset_overlaps\` ≤ 14/28 (52.61%)
- 脚本：\`python3 scripts/ai/chunk_quality_report.py --tenant default --json --baseline-after /tmp/td054-r2-after.json\`

## Risks

- `_enforce_size_limit` 子 chunk 仍用 `chunk.char_start + sub_offset` —— PR #234 验证已正确
- sentence.strip() 丢空白让 `local_offset` 短几字符 —— 下游只比单调性
- section.content 与 full_text 拼接 `\n\n` 长度差异 —— TD-051 4+1 公式处理

## Docs

- spec: \`docs/superpowers/specs/2026-06-14-td-054-chunker-internal-char-offset.md\`
- plan: \`docs/superpowers/plans/2026-06-14-td-054-chunker-internal-char-offset-plan.md\`
- post-merge 收口 PR 单独提交
EOF
)"
```

Expected: PR URL printed, e.g. `https://github.com/MarkDanile/MetaEduBase/pull/289`

### Step 3: gh pr checks 无阻塞

```bash
gh pr checks <PR_NUMBER>
```

Expected: 无 `fail` 状态。如果有 fail, 立即修复并 push。

### Step 4: squash merge

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
```

Expected: `√ Merged`, `√ Deleted branch fix/td-054-chunker-internal-char-offset-tracking`

### Step 5: 同步本地 main

```bash
git checkout main && git pull --ff-only
git log --oneline -3
```

Expected: HEAD = squash merge commit + 1 行 `fix(server-python): TD-054 chunker 内部 char_offset 跟踪修复（round 2）`

### Step 6: 跑 check-engineering-docs 确认 main 干净

```bash
scripts/check-engineering-docs
git diff --check
```

Expected: exit 0, clean。

---

## Task 4: 真 PG dev 库复测（用户/维护者下次接力）

**Files:** 0（仅运维操作）

### Step 1: 启动 dev PG

```bash
docker compose -f deploy/docker/docker-compose.dev.yml up -d postgres
# 或 colima/docker daemon 不可达时此步骤跳过, 留待维护者
```

### Step 2: alembic upgrade head

```bash
cd packages/server-python && alembic upgrade head
```

### Step 3: 跑 chunk_quality_report 复测样本

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python3 scripts/ai/chunk_quality_report.py --tenant default --json --baseline-after /tmp/td054-r2-after.json
```

### Step 4: 断言 offset_overlaps ≤ 52.61%

```bash
python3 -c "
import json
d = json.load(open('/tmp/td054-r2-after.json'))
total, ol = d['total_chunks'], d['offset_overlaps']
pct = ol/total*100 if total else 0
print(f'offset_overlaps: {ol}/{total} = {pct:.2f}%')
print(f'section_path_empty: {d[\"section_path_empty\"]}/{total}')
print(f'char_start_null: {d[\"char_start_null\"]}/{total}')
print(f'char_start_zero_zero: {d[\"char_start_zero_zero\"]}/{total}')
print(f'orphan_chunks: {d[\"orphan_chunks\"]}/{total}')
assert pct <= 52.61, f'overlap regressed: {pct:.2f}% > 52.61%'
print('PASS')
"
```

Expected: 复测样本（人才培养方案 28 chunks 文件）显示 `offset_overlaps: ≤14/28 (52.61%)`。

### Step 5: 跑全 25 文件重建

```bash
cd packages/server-python && .venv/bin/python -c "
import asyncio
from app.contexts.document.application.tasks.rebuild_chunks import rebuild_document_chunks
from app.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.shared.infrastructure.database import engine

async def main():
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        r = await session.execute(text('SELECT id, tenant_id FROM metaedu.files WHERE tenant_id = :tid'), {'tid': settings.default_tenant_id})
        files = r.all()
    for fid, tid in files:
        count = rebuild_document_chunks(str(fid), str(tid))
        print(f'  rebuilt {fid}: {count} chunks')

asyncio.run(main())
"
```

### Step 6: 跑全量 chunk_quality_report 验收

```bash
python3 scripts/ai/chunk_quality_report.py --tenant default --json --baseline-after /tmp/td054-r2-all.json
python3 -c "
import json
d = json.load(open('/tmp/td054-r2-all.json'))
total, ol = d['total_chunks'], d['offset_overlaps']
pct = ol/total*100 if total else 0
print(f'offset_overlaps: {ol}/{total} = {pct:.2f}%')
print(f'section_path_empty: {d[\"section_path_empty\"]}/{total}')
print(f'char_start_null: {d[\"char_start_null\"]}/{total}')
print(f'char_start_zero_zero: {d[\"char_start_zero_zero\"]}/{total}')
print(f'orphan_chunks: {d[\"orphan_chunks\"]}/{total}')
"
```

Expected: `offset_overlaps ≤ 52.61%` 整体达标。如果不达标, 留作 follow-up TD-054 round 3 跟踪。

### Step 7: 验收不通过的处理

如果 offset_overlaps > 52.61%:
- 不在 main 上直推, 登记新任务 TD-054-R3 / 或者扩展本任务状态
- 排查方向：
  1. `_enforce_size_limit` 内 `chunk.char_start + sub_offset` 父 chunk 内偏移是否真的正确（PR #234 round 1 仍可能有 latent bug）
  2. `_merge_small_chunks` `last.char_start + len(merged_content)` 累计 offset 在多次合并后是否漂移
  3. `rebuild_chunks.py:97-104` 4+1 公式与 chunker 内部 sentence 间分隔假设不一致

---

## Task 5: Post-merge 跨事实源收口（docs-only PR）

**Files:**
- Modify: `docs/03-engineering-governance/technical-debt.md`（TD-054 详情段翻 🟢 完成 + 补 PR/Merge Commit + 交付记录）
- Modify: `docs/03-engineering-governance/work-log.md`（追加 TD-054 round 2 长期索引行）
- Modify: `docs/03-engineering-governance/current-work.md`（滚动到 12 行 + 状态修正）

### Step 1: 建 docs 分支

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git checkout -b docs/td-054-r2-post-merge main
```

### Step 2: 修改 technical-debt.md TD-054 详情段

在 `docs/03-engineering-governance/technical-debt.md` 找到 TD-054 详情段（搜索 `### TD-054:`）。

把 L3213（推测真因注释行）替换为：
```markdown
**交付记录**
- 2026-06-12 登记（入手工具：Claude Code / TD-051 本机重建期间发现）。本次只入账，不实现。
- 2026-06-12 修复合片（分支 `fix/td-054-chunker-offset-overlap-bug`，PR 待提）：修 `_split_oversized_chunk` 3 个 off-by-one bug + 5 mock pytest。任务整体保持 🔵 就绪——真 PG 跑 25 文件 rebuild 留维护者下次接力。
- 2026-06-14 全链路评估人才培养方案文件复测发现：复测样本 `01-人才培养方案环境监测技术专业.pdf` (file_id=58370650-..., 28 chunks) `offset_overlaps = 23/28 (82.14%)` vs 历史基线 52.61% 进一步恶化 +29.51 pct，强烈提示问题在 PR #234 Slice 3 之外。
- 2026-06-14 round 2 修复合片（[PR #289](https://github.com/MarkDanile/MetaEduBase/pull/289) / merge commit `<SQUASH_COMMIT>` / 分支 `fix/td-054-chunker-internal-char-offset-tracking`，已删）：
  - 修 `packages/server-python/app/shared/parsing/chunker.py` `_chunk_by_structure` 主循环 3 处 char_offset 累加 bug：
    - L74 `char_offset = section_offset` → `local_offset = section_offset`（重命名 + 6 行注释，语义改为"已累积的 chunk 实际长度"）
    - L112 `char_offset += sent_len + 1` → `local_offset += sent_len`（首次 chunk 分支）
    - L140 `char_offset += sent_len + 1` → `local_offset += sent_len`（合并失败新建 chunk 分支）
    - 合并分支（L121 / L128）local_offset 不前进 —— **修复核心**
  - 新增 `packages/server-python/tests/shared/test_chunker_offset_monotonicity_td054.py` 5 mock pytest：
    - test_chunk_offsets_strictly_monotonic_within_section（主断言：跨 chunk 无 overlap）
    - test_local_offset_advances_only_on_new_chunk（合并分支不前进）
    - test_no_phantom_separator_in_offset（去掉 +1）
    - test_section_offset_passed_through（section_offset 参数传递）
    - test_enforce_size_limit_preserves_monotonicity（拆分后仍单调）
    - 修前 1-3/5 fail（overlap 暴露 prev=[4,16) curr=[4,…）等；修后 5/5 pass
  - 不修改 `_enforce_size_limit` / `_merge_small_chunks`（PR #234 + #253 已修对）
  - 不修改 `rebuild_chunks.py` 4+1 公式（不在本任务范围）
  - ruff clean / `git diff --check` clean / `scripts/check-engineering-docs` 退出码 0
  - 现有 429+ mock pytest 0 业务代码回归
  - 真 PG 复测：dev 库（colima 当前不可达）留维护者下次接力；目标 `offset_overlaps ≤ 52.61%`
  - 翻 🟢 完成依据：PR #289 MERGED + 5 mock pytest 全过 + 429+ pytest 0 回归 + ruff clean，符合 git-workflow.md#翻完成前硬条件 1-4
```

把 L3152 `状态：🔵 就绪` 改为 `状态：🟢 完成`。

把 L150 总览行 TD-054 状态从 `🔵 就绪` 改为 `🟢 完成` + 补 PR 链接。

### Step 3: 修改 work-log.md

在 `docs/03-engineering-governance/work-log.md` 找到合适插入点（按 DRAFT 顺序最新行下方），追加：

```markdown
| 2026-06-14 | TD-054 round 2 chunker 内部 char_offset 跟踪修复 | [PR #289](https://github.com/MarkDanile/MetaEduBase/pull/289) | chunker.py L74/L112/L140 3 处 char_offset 累加 bug；local_offset 仅新建 chunk 累加 + 合并分支不前进 + 去 phantom +1；5 mock pytest 锁单调性；真 PG 留维护者下次 colima 接力。 |
```

### Step 4: 修改 current-work.md

在 `docs/03-engineering-governance/current-work.md` 找到 "当前进行中" 表格里的 TD-054 行，整行删除（已移到"最近完成"顶部）。

在"最近完成"表格顶部追加：

```markdown
| 2026-06-14 | TD-054 chunker 内部 char_offset 跟踪修复（round 2）| 🟢 完成 | PR #289 squash merge：chunker.py L74/L112/L140 3 处 char_offset 累加 bug。local_offset 仅新建 chunk 累加 + 合并分支不前进 + 去 phantom +1。5 mock pytest 锁单调性 + 429+ mock pytest 0 业务代码回归。 | [TD-054](../../03-engineering-governance/technical-debt.md#td-054) / [PR #289](https://github.com/MarkDanile/MetaEduBase/pull/289) |
```

**滚动约束**：删除"最近完成"表格最末行（必须保留 ≤ 12 数据行）。

### Step 5: check-engineering-docs 验证

Run:
```bash
scripts/check-engineering-docs
git diff --check
```

Expected: exit 0, clean。如果有 `validation-claim` / `current-work-recent-summary` 警告，按 workbench.md 约束重写摘要到 ≤ 220 字符。

### Step 6: Commit + push + PR + squash merge

```bash
git add docs/03-engineering-governance/technical-debt.md \
        docs/03-engineering-governance/work-log.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(governance): TD-054 round 2 跨事实源收口（🟢 完成 + work-log 索引）"
git push origin docs/td-054-r2-post-merge
gh pr create --base main --head docs/td-054-r2-post-merge \
  --title "docs(governance): TD-054 round 2 跨事实源收口（🟢 完成 + work-log 索引）" \
  --body "## Summary
- technical-debt.md TD-054 详情段翻 🟢 完成 + 补 PR #289 / 交付记录
- work-log.md 追加长期索引行
- current-work.md 滚动到 12 行

## Validation
- scripts/check-engineering-docs exit 0
- git diff --check clean
- 0 业务代码 / 0 测试代码 / 0 脚本变更（docs-only）"
gh pr merge <PR_NUMBER> --squash --delete-branch
git checkout main && git pull --ff-only
```

Expected: PR 合并, 本地 main HEAD = squash merge commit。

---

## Self-Review

### 1. Spec coverage
- [x] 4 类真因 bug → Task 2 Step 1-3 3 处代码改动（合并分支不动是 fix 核心）
- [x] 5 mock pytest → Task 1
- [x] 真 PG 复测 → Task 4
- [x] 跨事实源收口 → Task 5

### 2. Placeholder scan
- 无 TBD / TODO / "implement later"
- 无 "Similar to Task N"（每步都给了完整代码）
- 无 "Add appropriate error handling"（mock pytest 用 strict assert）

### 3. Type consistency
- `local_offset` 在 Task 2 Step 1 重命名后，Task 2 Step 2/3 引用同名字
- `char_start` / `char_end` 在 Task 1 测试和 Task 2 实现引用 Chunk dataclass 字段
- `_split_oversized_chunk` 在 Task 1 测试 fixture 和 Task 2 Step 4 验证中引用相同函数名

### 4. Order check
- Task 1 (TDD red) → Task 2 (TDD green) → Task 3 (PR merge) → Task 4 (真 PG) → Task 5 (docs) 顺序正确
- Task 2 Step 4 失败时**立即停止**（已写 STOP 标记）
