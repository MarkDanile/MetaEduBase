# BUG-007: pdf_parser 中 sections 段 path 计算错乱（font-size + 中文正则 level 混用）

Status: 🟢 Done (PR #303 merged)
Priority: P2
Milestone: P1 RAG 治理 / 资源库 UX
Source: 2026-06-16 用户重新上传 4 份文件真 PG 复测时发现（用户 + Claude Code 真 PG 审计）

## 背景

BUG-006 #2 (PR #299) 已合并 — `pdf_parser.py` 新增 `_detect_chinese_heading_level` + 5 类中文正则模式作为 font-size+bold heuristic 的 fallback。**中文一级/二级标题识别本身修复有效**，但**遗留 level 一致性 bug**：font-size heuristic 和中文正则 heuristic 给同一类标题分配的 level 数字不一致，导致 `section_counter` 状态污染 + `path` 字段计算错乱。

真 PG 复测 4 份新上传文件后现象：
- ✅ 人才培养方案（`/opt/homebrew/.../01-人才培养方案环境监测技术专业.pdf`）：29 段全部 path 正确（之前是 1 段空 path，BUG-006 #2 修复有效）
- ⚠️ 课程标准水环境（`02-《水环境监测》课程标准.pdf`）：8 段中 1 段 path 空
- ⚠️ 汽车底盘构造（`汽车底盘构造与检修.pdf`）：120 段中 2 段 path 空
- ✅ 教案：1 段 path 正确

## 根因

`_build_path` 函数 + `section_counter` 累加逻辑，依赖一个**单调层级假设**：font-size heuristic 给出的 level（1-4）和中文正则给出的 level（1-2）应当对同一类标题一致。但当同一 PDF 混用两类 heuristic 时：

| 真实场景 | font_lvl | regex_lvl | 最终 level | section_counter 状态 |
|---------|----------|-----------|-----------|---------------------|
| "附件1：授课计划"（15pt+bold） | **3** | 0 | 3 | `{3:1}` |
| "学期授课计划"（22pt+非bold） | 2 | 0 | **2** | `{3:1, 2:1}` |
| "18 环测1 班"（14.1pt+bold） | 4 | 0 | **4** | `{3:1, 2:1, 4:1}` |
| "2021 年1 月8 日"（14.1pt+bold） | **4** | 0 | 4 | `{3:1, 2:1, 4:2}`（**非标题被错误归入**）|
| "一、编制说明"（12pt+非bold） | 0 | **1** | **1** | `{3:1, 2:1, 4:3, 1:1}`（混进 level=1） |
| "二、授课计划"（12pt+非bold） | 0 | **1** | 1 | `{1:2}` |

**后续 path 计算混乱**：font-size 误判的 level=3/2/4 与中文正则 level=1 共享同一 section_counter，导致 path "1" 被反复重置（段 6 = "1"，段 8 = "3"，应分别为 "2.3" 和 "2.5"）。

**两个独立根因**：

1. **font-size heuristic 把非标题识别为标题**：日期"2021 年1 月8 日" 14.1pt+bold 但不是标题 — 当前启发法无文本长度阈值保护（已有 `len(line_text) < 200` 但 14.1pt 仍落 level=4 范围）
2. **font-size level 与中文正则 level 不统一**：font-size 4 级表 `{22:1, 18:2, 15:3, 13:4}` 和中文正则 level `{1, 2}` 在同 PDF 中并存，互相污染 section_counter

## 复现路径

1. 上传 `02-《水环境监测》课程标准.pdf` 到 Resource Library
2. 等 6 步流水线 success
3. 真 PG 查询：
   ```sql
   SELECT
     jsonb_array_length(coalesce(structured_data->'sections','[]'::jsonb)) AS section_count,
     (SELECT count(*) FROM jsonb_array_elements(structured_data->'sections') s
      WHERE s->>'path' = '' OR s->>'path' IS NULL) AS empty_path_count,
     (SELECT s->>'title' FROM jsonb_array_elements(structured_data->'sections') s
      WHERE s->>'path' = '' OR s->>'path' IS NULL LIMIT 1) AS empty_path_title
   FROM metaedu.files WHERE filename = '02-《水环境监测》课程标准.pdf';
   -- 实际：section_count=8, empty_path_count=1, empty_path_title='2021 年1 月8 日'
   -- 期望：empty_path_count=0
   ```
4. 同样检查 `汽车底盘构造与检修.pdf`：120 段中 2 段 path 空
5. 人才培养方案 / 教案：0 段 path 空（**这两类文档不触发本 bug** — 字体一致地命中一种 heuristic）

## 期望行为

- 任何 PDF 上传后，所有 sections 的 `path` 字段在结构正确时非空（除非是真正的 unnumbered heading）
- 同一 PDF 内 section 层级（1/2/3/4）一致性：font-size 命中的 level 与中文正则命中的 level 对同一类标题必须协调
- 非标题段落（如纯日期、纯数字编号）不应被识别为 heading
- path 字符串遵循 `1`, `1.1`, `1.1.1` 单调层级格式

## 怀疑点

- `pdf_parser.py` `_HEADING_SIZES` 表（L26-27）：4 级表与中文正则 2 级表无映射关系
- `pdf_parser.py` `extract_pdf_text` 主循环（L92-99）is_heading 判断：font-size 与正则 fallback **独立递增** section_counter，不做归一化
- `_build_path` 函数（L152-158）：依赖 counter 单调层级假设，混用 heuristic 时计算错位
- 缺失：text-pattern 优先级 / level 归一化 / 非标题白名单（如纯日期 `\d+ 年\d+ 月\d+ 日` / 纯数字 `\d{3,}`）

## 影响范围

- `pdf_parser.py`：font-size + 中文正则 level 归一化（约 20-40 行核心改动）
- 测试：`tests/shared/test_pdf_parser.py` 补充 fixture 用例（混用 heuristic 的 PDF）+ 边界用例（日期/数字不归为标题）
- 不涉及：`docx_parser.py`（用 Word style 已统一）/ `chunker.py`（消费 sections，不改）

## 关联债

- BUG-006 #2 (PR #299, merge `bd7b109`)：引入中文正则 heuristic 的**前置债**——只补 fallback，未统一 level
- TD-053 (`rebuild_document_chunks` fallback path 合成)：同源问题（fallback 时 section_path 100% 空）
- TD-051 (document_chunks 结构元数据治理)：上层 chain，本 BUG 修好后 chunk.section_title/path 全链路受益

## 完成标准

- 上传 `02-《水环境监测》课程标准.pdf` / `汽车底盘构造与检修.pdf` 等混用 heuristic 的 PDF：
  - 所有 sections 的 path 字段在结构正确时非空
  - path 字符串遵循层级格式（如 "1", "1.1", "2.1.1"）
- 测试覆盖：
  - `tests/shared/test_pdf_parser.py` 加 fixture 用例（混用 heuristic 的 PDF mock）
  - 纯日期 `\d+ 年\d+ 月\d+ 日` 不归为 heading
  - 纯数字 `\d{3,}` 不归为 heading
  - 中文一级标题（regex level=1）与 font-size 命中 title 共存时 path 正确（如 "2.3" 而非 "1"）
- 真 PG 复测：`02-《水环境监测》课程标准.pdf` empty_path_count = 0
- 不引入新 bug：人才培养方案（已被 BUG-006 #2 修复）保持 29/29 path 非空
- `ruff clean` / `git diff --check clean` / `scripts/check-engineering-docs` exit 0

## 不在范围

- BUG-006 #2 修复本身（已合并，已生效）
- docx_parser（用 Word style 已统一 level）
- LLM template 抽取字段 `-` 比例高（属 BUG-006 #3 跟进项，独立债）

## 拆分建议（实现时）

建议单 PR 完成（修复集中、相互依赖），但可拆 2 个提交：

1. **PR-1（核心修复）**：level 归一化 + section_counter 单调层级保证 + 非标题黑名单
2. **PR-2（测试加固）**：补 mock fixture 用例覆盖混用 heuristic 场景

## 交付记录

- 2026-06-16 登记（用户重新上传 4 份文件后真 PG 复测发现）。
- 本 BUG 5 字段齐全（事实源 / 证据 / 复现 / 期望 / 怀疑点），按 bug fix 模式入账 🔵 Ready。
- 关联债：BUG-006 #2 (PR #299)、TD-053、TD-051。
- 2026-06-16 修复合片已合并：PR #303 / merge `31fc4f0`，`pdf_parser.py` section path 改用 docling counters 算法并补非标题黑名单；mock tests pass。
- 真实 PG reparse / backfill 与 AI Chat 样例综合验收已统一分流到 REQ-014。
