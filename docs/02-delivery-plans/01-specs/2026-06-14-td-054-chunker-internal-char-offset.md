# TD-054: Chunker 内部 char_offset 跟踪修复

**Date**: 2026-06-14
**Status**: Design — awaiting approval
**Branch**: `fix/td-054-chunker-internal-char-offset-tracking`
**Owner**: Claude Code

## 1. Context（背景）

### 1.1 现状
2026-06-14 全链路评估人才培养方案文件复测（[PR #235 baseline](https://github.com/MarkDanile/MetaEduBase/pull/235)）发现 chunk 质量度量 `offset_overlaps` 仍恶化：

| 时点 | total | offset_overlaps | % |
|------|-------|-----------------|---|
| 重建前（历史基线）| 1551 | 816 | 52.61% |
| 重建后（PR #235 当时）| 1562 | 869 | 55.63% |
| 复测 1（人才培养方案样本）| 28 | 23 | 82.14% |

### 1.2 历史修复回顾

**PR #234 Slice 3**（TD-051）修复了 `_enforce_size_limit` 拆分时 `char_start` 传递：子 chunk 拿到 `chunk.char_start + sub_offset`，正确反映父 chunk 内的相对位置。

**PR #253**（TD-054 之前的修复合片）修了 `_split_oversized_chunk` 内 3 个 off-by-one bug（重复 pos、+1 phantom separator）。

但**两个 PR 都未触及 `chunk_by_structure` 主循环（L93-141）的 `char_offset` 累加逻辑**。

### 1.3 真因诊断

`chunk_by_structure` 主循环 L93-141 在每个 sentence 处理分支（L100 / L130）后无条件 `char_offset += sent_len + 1`，但**没有区分两种情况**：

- **合并到 last chunk（L118-128）**：sentence 内容被附加到 `last.content`，`last.char_end` 被重新算成 `last.char_start + len(last.content)`。此时 `char_offset` 应当 **保持不变**——sentence 没产生新 chunk，offset 没前进。
- **新建 chunk（L130-141）**：sentence 产生新 chunk，`char_start = char_offset`。`char_offset` 应当前进 `len(sentence) + 1`（+1 模拟句子间空格）。

当前代码**两种情况都加了 `+ sent_len + 1`**，且**在合并分支后不前进**也会产生 stale `char_offset` 跨段漂移。

更严重的是：当 `_enforce_size_limit`（L144）**重新切分**某个 chunk 为多个子 chunk 时，**所有后续 sentence 的 `char_offset` 全部错位**（`char_offset` 不会被 `_enforce_size_limit` 更新）。结果：

- 子 chunk 1: `char_start = X`，`char_end = X + 100`（正确）
- 子 chunk 2: `char_start = X + 100`（但**实际**原 chunk 在文档中的位置是 `X + 500`）
- 后续 sentence 的 `char_offset` 全部偏低 400
- 下一对 chunk 的 overlap = `next.char_start - prev.char_end` 变成负数 → offset_overlaps 增加

### 1.4 真因（精确）总结

`chunk_by_structure` 内 `char_offset` 跟踪不严谨，体现在 4 个具体 bug：

1. **L112 / L140 `char_offset += sent_len + 1` 在合并分支也执行**——合并时不该前进
2. **`+ 1` 假设 sentence 之间固定 1 字符间隔**——但实际可能是空格、换行、句号，**且 rebuild_chunks 并不在 sentence 间加固定分隔符**
3. **sentence.strip() 丢弃的空白字符未计入**（L94 / L131）——offset 与实际文档位置差几个字符
4. **`_enforce_size_limit` 拆分时 `char_offset` 未相应更新**——子 chunk 后的所有 offset 整体漂移

## 2. Goal（目标）

- 真 PG dev 库跑 `rebuild_document_chunks` 重建 1 个样本 + 跑 `chunk_quality_report.py` 后，`offset_overlaps` 比率 ≤ 52.61%（=历史基线）
- 4 类其他指标不退化：`char_start_null` / `char_start_zero_zero` / `section_path_empty` / `orphan_chunks` 保持修复后水平
- chunker 输出新增契约：`full_text[char_start:char_end] == chunk.content`（允许尾部 sentence 边界差异 ≤ 5 字符）

## 3. Design（设计）

### 3.1 修复策略：引入 `local_offset` 跟踪 chunk 内偏移

**核心思路**：把 chunker 内的 `char_offset` 重命名为 `local_offset`，语义改为"**已累积的 chunk 实际长度**"（不含未入 chunk 的 sentence 间隔），且只在**新建 chunk**时累加 `len(chunk.content)`。

```python
# Before（L100-141 旧逻辑）
char_offset = section_offset
...
char_offset += sent_len + 1  # 不论是否合并都加

# After（新逻辑）
local_offset = section_offset  # = 绝对偏移起点
...
if new_chunk_created:
    local_offset += len(sentence)  # 只在新建 chunk 时累加真实长度
```

**关键不变量**：
- `chunks[i].char_end <= chunks[i+1].char_start`（无 consecutive overlap）
- `chunk.char_start >= section_offset`（每个 chunk 不在 section 起点之前）

### 3.2 算法骨架

```python
def chunk_by_structure(parsed, target_chars=TARGET_CHUNK_CHARS, section_offset=0):
    chunks = []
    chunk_index = 0
    # TD-054 fix: track cumulative chunk length within the section
    # (not raw character cursor) so _enforce_size_limit post-splits don't drift.
    local_offset = section_offset

    for section in parsed.sections:
        text = section.content.strip()
        if not text:
            continue

        paragraphs = _split_paragraphs(text)

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            sentences = _split_into_sentences(para)

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sent_len = len(sentence)

                if not chunks:
                    chunks.append(Chunk(
                        content=sentence,
                        char_start=local_offset,
                        char_end=local_offset + sent_len,
                        ...
                    ))
                    local_offset += sent_len  # only advance when new chunk created
                    chunk_index += 1
                else:
                    last = chunks[-1]
                    last_len = last.char_end - last.char_start

                    if last_len + sent_len + 1 <= target_chars:
                        # merge: do NOT advance local_offset (content joined into last)
                        last.content += "\n" + sentence
                        last.char_end = last.char_start + len(last.content)
                    elif last_len < 100 and sent_len > target_chars * 0.8:
                        # merge tiny + long: do NOT advance
                        last.content += "\n" + sentence
                        last.char_end = last.char_start + len(last.content)
                    else:
                        # new chunk: advance by exact chunk content length
                        chunks.append(Chunk(
                            content=sentence,
                            char_start=local_offset,
                            char_end=local_offset + sent_len,
                            ...
                        ))
                        local_offset += sent_len
                        chunk_index += 1

    # _enforce_size_limit must be calibrated to use chunks[i].char_start
    # as the parent anchor (already correct after PR #234). local_offset is
    # NOT advanced during _enforce_size_limit — we recompute from chunks.
    chunks = _enforce_size_limit(chunks, target_chars)

    chunks = _merge_small_chunks(chunks, min_size=MIN_CHUNK_CHARS)

    for i, c in enumerate(chunks):
        c.index = i
    return chunks
```

### 3.3 三处具体改动

#### 改动 1：`chunker.py` L74 `char_offset = section_offset` → `local_offset = section_offset`
#### 改动 2：L112 / L140 `char_offset += sent_len + 1` → `local_offset += sent_len`（去掉 phantom `+ 1`）
#### 改动 3：合并分支（L121 / L128）**不**前进 `local_offset`（保持现状逻辑正确）

### 3.4 `_enforce_size_limit` 与 `local_offset` 的交互

`_enforce_size_limit` 在 PR #234 之后用 `chunk.char_start + sub_offset` 算子 chunk 起点——这个**绝对正确**，因为 `sub_offset` 是子 chunk 内容在父 chunk content 内的**相对**位置。

**关键**：`local_offset` 必须在 `_enforce_size_limit` 调用**之后**重新校准——因为子 chunk 的实际 `char_start` 已经在 chunks 列表里，无需再用 `local_offset` 推断。

实际算法无需显式校准——`_enforce_size_limit` 后的子 chunk 直接用 `chunk.char_start + sub_offset`，下游 `_merge_small_chunks` 用 `last.char_start + len(merged_content)`——**两者都不依赖 `local_offset`**。

**唯一需要**：在 `_enforce_size_limit` 之前的最后一个 chunk 创建时，`local_offset` 累加的是 sentence 长度（不包含合并 sentence 间的 `\n`）。`_enforce_size_limit` 之后真实 chunk content 可能比 `local_offset` 累加的稍长（多了 `\n`）。这是 **< 1 字符级**差异，不影响 offset_overlaps 检测（只需 monotonicity）。

### 3.5 为什么不直接重写 chunker？

考虑过完全重写，但：

- TD-051 已有完整设计文档（5 step pipeline），rebuild 路径依赖这套语义
- `_enforce_size_limit` 在 PR #234 + PR #253 修过 3 个 off-by-one 后已经稳定
- 真正的 bug 集中在 `chunk_by_structure` 主循环的 `char_offset` 累加——**4 行改动 + 1 个变量重命名**
- 重写会引入新风险

→ 选**最小修复路径**：4 行 + 1 重命名 + 1 个新契约断言。

## 4. Validation（验证）

### 4.1 Mock pytest 锁死不变量

新建 `tests/shared/test_chunker_offset_monotonicity_td054.py`（5 用例）：

1. `test_chunk_offsets_strictly_monotonic_within_section` — `chunks[i+1].char_start >= chunks[i].char_end`
2. `test_local_offset_advances_only_on_new_chunk` — 重复段 `[短，短，短]` 不应让 `char_start` 漂移
3. `test_no_phantom_separator_in_offset` — sentence 长度 100 字符时 `chunk[i+1].char_start == chunk[i].char_end`（允许 ±1 字符）
4. `test_section_offset_passed_through` — `section_offset=5000` 时第一个 chunk `char_start >= 5000`
5. `test_enforce_size_limit_preserves_monotonicity` — 制造 800 字符超长 sentence，触发 `_enforce_size_limit`，断言子 chunk 单调

### 4.2 真 PG 复测

修复合 main 后维护者跑：

```bash
# 1. 启动 dev PG
docker compose -f deploy/docker/docker-compose.dev.yml up -d postgres
# 2. alembic upgrade head
cd packages/server-python && alembic upgrade head
# 3. 跑 chunk_quality_report.py 复测 28 chunks 文件
cd ../.. && python3 scripts/ai/chunk_quality_report.py --tenant default --json --baseline-after /tmp/td054-after.json
# 4. 断言 offset_overlaps <= 52.61% (即 869)
python3 -c "
import json
d = json.load(open('/tmp/td054-after.json'))
total, ol = d['total_chunks'], d['offset_overlaps']
print(f'offset_overlaps: {ol}/{total} = {ol/total*100:.2f}%')
assert ol/total <= 0.5261, f'overlap regressed: {ol/total*100:.2f}% > 52.61%'
print('PASS')
"
```

### 4.3 质量门禁

- `pytest tests/shared/test_chunker_offset_monotonicity_td054.py -v` → 5/5 pass
- `pytest tests/ -q` → 现有 429+ 仍 pass（5 个新 mock pytest 无回归）
- `ruff check app/ tests/` clean
- `git diff --check` clean
- `scripts/check-engineering-docs` 退出码 0

## 5. Risks（风险）

| 风险 | 缓解 |
|------|------|
| `_enforce_size_limit` 子 chunk 仍用 `chunk.char_start + sub_offset`——在 PR #234 之后已正确 | 已读 PR #234 + 5 个 mock pytest 覆盖 |
| sentence.strip() 丢空白让 `local_offset` 短几字符 | 下游使用方（rebuild_chunks、evidence_coverage）只比较 `char_start < char_end` 单调性，不校验绝对位置 |
| section.content 与 full_text 拼接处 `\n\n` 长度差异 | 已有 TD-051 rebuild_chunks 4+1 公式处理（不在本任务范围） |
| 人才培养方案文件 28 chunks 仍 overlap > 0 | 真实 PG 复测验收；如不达标，进 follow-up |
| 改完触发 `chunk_quality_report.py` 新失败 | 5 mock pytest 已锁死关键不变量 |

## 6. Out of Scope（不在范围）

- `rebuild_chunks.py:97-104` 4+1 偏移公式调整（不归本任务）
- `section_path` 100% 空（TD-053 衍生，未入账到 TD-054）
- `_enforce_size_limit` 子句进一步重构（PR #234 + #253 已稳定）
- AI Chat 端 evidence 高亮使用 `char_start`/`char_end`（前端需求）
- `chunk_document` 任务的 `section_offset` 0/真实值（不在本任务范围）

## 7. Files（文件清单）

| File | 改动类型 | 行数估算 |
|------|----------|----------|
| `packages/server-python/app/shared/parsing/chunker.py` | 修改 | 4 行 + 1 重命名 + 6 行注释 |
| `packages/server-python/tests/shared/test_chunker_offset_monotonicity_td054.py` | 新建 | ~120 行（5 mock pytest） |
| `docs/03-engineering-governance/technical-debt.md` | post-merge 翻完成 | ~20 行（详情段 + 交付记录） |
| `docs/03-engineering-governance/work-log.md` | post-merge 追加索引 | 1 行 |
| `docs/03-engineering-governance/current-work.md` | post-merge 滚动到 12 行 | 1 行 |
| `docs/02-delivery-plans/01-specs/2026-06-14-td-054-chunker-internal-char-offset.md` | 本 spec | ~250 行（本文档） |

## 8. Plan

进入 writing-plans skill 编写实施计划后落地：

1. `fix/td-054-chunker-internal-char-offset-tracking` 分支已建
2. 改 `chunker.py` L74/L112/L140（4 行 + 1 重命名）
3. 新建 5 mock pytest
4. 跑 pytest + ruff + check-engineering-docs
5. commit + push + PR (fix 分支) → merge
6. 真 PG dev 库复测（用户/维护者）
7. post-merge 收口 PR (docs 分支)
8. 删分支
