# REQ-014 RAG 真实 PG 样例、数据回填与回答 grounding 验收 — Spec

> Requirement: `docs/01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md`
> Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
> Iteration: `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`
> Validation Report: `docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md`
> 验收脚本: `scripts/validate_real_pg_rag.py`

## Summary

REQ-012 / REQ-013 / BUG-006 / BUG-007 已经把代码与 mock 测试推进到机制可用，但评审和后端都观察到：**真实 PG 样例 + 数据回填 + 最终回答质量还没有作为闭环验收过**。本 spec 把这些缺口统一收口：

1. 选定 3-5 个真实样例文件，覆盖 Python 教程 / 人才培养方案 / 课程标准或教案。
2. 检查并按需补齐 parse / chunk / embed / tsvector / KG。
3. 跑 4-5 个固定问题，验收 Context Packer 的 packed context、文档级来源、最终回答。
4. 用真 PG 复测 BUG-007 section path 与 BUG-006 五子项。
5. 输出 Markdown 验收报告，作为本任务的交付依据。

不重写 Context Packer，不在验收中发现新 bug 时改 BUG-006/007 实现（另开 BUG-xxx）。

## Current Findings

| 发现 | 证据 | 影响 |
|------|------|------|
| REQ-013 Slice 5 真实 PG 样例未 backfill | [REQ-013 Backlog 行](../../01-product-planning/04-backlog.md) "Slice 5 真实 PG 样例待 backfill" | Context Packer 真实问答未验证 |
| BUG-007 真 PG reparse 未集中验收 | [BUG-007 状态](../../01-product-planning/04-backlog.md) 🟢 Done；复测在 PR 中只跑 mock | section path 在真实文件上仍可能有边缘 case |
| BUG-006 五子项真 PG 综合复测未做 | [BUG-006 状态](../../01-product-planning/04-backlog.md) "真 PG 综合复测接力 REQ-014" | 5 子项在真 PG 上未集中验证 |
| REQ-013 Acceptance AC-8 未跑真问题 | [REQ-013 Spec AC-8](../../02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md#acceptance-criteria) | "python 的基本数据类型有哪些？" 仅 mock 验证 |

## Goals

- 把 REQ-013 / BUG-006 / BUG-007 的真实数据回填 + 回答 grounding + BUG 复测，统一收口到一次真 PG 验收。
- 生成可读、可复核、可 Git 跟踪的 Markdown 验收报告。
- 任何未通过的项必须归因到「检索 / 数据 / prompt / LLM / 前端引用 / 文档解析」其中之一，并登记新 REQ / BUG / TD。
- 跨事实源同步：Backlog、Milestone、Iteration、current-work、work-log。

## Non-Goals

- 不引入 Elasticsearch / Milvus / Neo4j / 完整 GraphRAG。
- 不重写 Context Packer、EvidenceItem、DocumentSource 实现。
- 不把"全量历史文件"全量 reparse；只针对代表样例。
- 不在 BUG-006 / BUG-007 复测中修改原实现；如发现明显问题另开 BUG-xxx。
- 不动前端 AI Chat 页面 UI；只验"问答返回 + 文档级来源"在 dev 环境的 API 行为。

## Proposed Design

### 1. 样例文件清单

按需求侧建议的「3-5 个代表样例」，从 dev 库中选定：

| 类别 | 用途 | 选择标准 |
|------|------|----------|
| Python 教程 PDF | 验收 AC-2 "python 的基本数据类型有哪些？" 的正文证据 | 已有正文 / 已 parse / 已 chunk |
| 人才培养方案 PDF | 验收 BUG-005 files.doc_type / template_id 回写 | 已 L1 / L2 / L3 命中；已填 doc_type |
| 课程标准 / 教案 PDF | 验收 BUG-007 section path 解析稳定性 | 真实结构 + 含中文章节 |

样例文件的具体 file_id 在 Plan 阶段通过查询 dev 库 `files` 表确定，记录到验收报告。本 spec 不绑定具体 file_id，避免塑形期就锁死环境。

### 2. 数据回填

按"按需补齐"原则，对每个样例文件做：

1. **状态扫描**：调用内部 helper 或 SQL 读取
   - `files.parse_status` / `files.chunk_status` / `files.template_id` / `files.doc_type`
   - `chunks` count / `chunk_embeddings` 覆盖率 / `chunk_tsvectors` 覆盖率
   - `knowledge_nodes` / `knowledge_edges` 是否存在
2. **缺失补齐**：
   - `parse_status` 失败 → 调用 `POST /api/v1/files/{file_id}/retry` 或 `reinitialize`
   - chunk 缺 embedding → 通过 worker 重跑 embedding pipeline
   - 缺 tsvector → 跑 `docs/03-engineering-governance/01-rules/local-development.md` 里的回填脚本
   - KG 缺失 → 通过 KG 提取 worker 重建
3. **记录**：每个文件的 before / after 状态 + 触发的命令 + 退出码 + 退出结果摘要。

脚本入口：`scripts/validate_real_pg_rag.py backfill` 子命令。

### 3. Context Packer 真实问答验收

4-5 个固定问题，至少包含：

| 问题 | 期望命中 | 验收点 |
|------|----------|--------|
| "python 的基本数据类型有哪些？" | Python 教程 PDF | AC-2 packed context 含正文解释；不以目录为主证据 |
| "XXX（人才培养方案 1 个具体问题）" | 人才培养方案 PDF | AC-3 文档级来源展示 |
| "XXX（课程标准 / 教案 1 个具体问题）" | 课程标准 PDF | AC-3 文档级来源 + AC-4 section path 正常 |
| 1 个跨样例问题（可选） | 多个文档 | DocumentSource 聚合 |
| 1 个故意无答案问题 | 兜底 | AC 保留 evidence 不足兜底 |

每个问题记录：

- 各 channel 召回 topN（vector / keyword / graph / metadata）
- fusion 后 topN
- packed block 摘要：`file_id` / `chunk_ids` / 字符数 / 标题 / section 路径
- 是否触发 section fallback
- 最终回答文本（截断到 500 字）
- `document_sources`（来自 `DocumentSource`）
- `evidence_indices`（与回答 `[N]` 顺序一致性）

调用入口：`scripts/validate_real_pg_rag.py ask` 子命令 + `POST /api/v1/ai/chat/evidence`（或等价内部 API）。

### 4. BUG-007 真 PG reparse 复测

对每个 PDF 样例：

1. 调用 `POST /api/v1/files/{file_id}/reparse` 或等价内部 helper。
2. 解析完成后，查询 `document_sections.path` / `document_sections.title`：
   - 是否有空 path？
   - 是否有同 level 错乱？
   - 中文章节标题是否正常（BUG-006 #2 修复）？
3. 输出结构化表格：file_id / section count / 空 path 数 / 错乱 path 数 / 修复点状态。

### 5. BUG-006 五子项真 PG 综合复测

| 子项 | 验收方式 | 真 PG 验证点 |
|------|----------|-------------|
| #1 模板字段名 label | 通过 `GET /api/v1/templates/{id}` 取 schema + 在前端 dev 渲染 | 字段 label 是否含中文 key path |
| #2 pdf_parser 中文章节正则 | 与 BUG-007 复测共享 | section title 正常 |
| #3 嵌套 schema 描述 + few-shot 前移 + 截断扩展 | `extract_template_prompts.build_fields_desc` 单元 + 真实抽取 | 嵌套字段在 prompt 中可读 |
| #4 KG > 50 节点白屏 | `GET /api/v1/knowledge/files/{file_id}/kg-bundle` | 返回 200，节点数 / 边数与 DB 一致 |
| #5 文件详情页返回按钮 | dev 环境手测 + 验证 router.replace | goBack 后 URL 不残留错乱 query |

只记录结果，不修代码。

### 6. 验收报告

报告文件：`docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md`

结构：

```text
# REQ-014 真实 PG 验收报告 — YYYY-MM-DD

## 环境
- DB: postgresql://...
- 时间: ...
- LLM: ...
- 执行人: ...

## 1. 样例文件清单与回填状态
| file_id | name | doc_type | template_id | chunks | embeddings | tsvectors | kg_nodes | kg_edges | before/after |
...

## 2. Context Packer 问答验收
### Q1: "python 的基本数据类型有哪些？"
- retrieval topN: ...
- fusion topN: ...
- packed blocks: ...
- 最终回答: ...
- document_sources: ...
- evidence_indices: ...
- 结论: AC-2/AC-3 ✅ / ❌

## 3. BUG-007 真 PG reparse
| file_id | section_count | empty_path | abnormal_path | 结论 |
...

## 4. BUG-006 五子项真 PG 复测
| 子项 | 验证命令 / 路径 | 结论 | 备注 |
...

## 5. 失败归因与新登记
| 现象 | 归因类别 | 新 REQ / BUG / TD |
...

## 6. AC 收口
| AC | 状态 | 证据 |
| AC-1 | ✅ | ... |
...
```

报告由 `scripts/validate_real_pg_rag.py report` 子命令生成。脚本接受 `--out` 参数指定输出路径。

### 7. 跨事实源同步

完成报告后必须同步：

- `docs/01-product-planning/04-backlog.md` REQ-014 行：🟡 Shaping → 🟢 Done / 🟡 Planned（按实际收口状态）
- `docs/01-product-planning/02-milestones/02-growth-phase.md` REQ-014 行：同步状态 + 链接
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-014 行：同步状态
- `docs/01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md` Status 字段：同步
- `docs/03-engineering-governance/current-work.md`：REQ-014 移到最近完成区
- `docs/03-engineering-governance/work-log.md`：新增 REQ-014 索引行（PR / merge commit / 验收命令）
- BUG-006 / BUG-007 Backlog 行：「真 PG 复测」字段补齐

## Acceptance Criteria

- AC-1：验收报告存在，5 个样例文件的状态扫描 + 缺失补齐命令 + 退出码全部记录；或明确说明"无需重建"并附依据。
- AC-2："python 的基本数据类型有哪些？" 的 packed context 包含 Python 教程 PDF 的正文 chunk（不是目录 / 简介），且 `packed_block.content` 中能找到基本数据类型的解释性内容（如 `int / float / str / bool` 等定义性描述）。
- AC-3：AI Chat 最终回答可读、含引用 `[N]`、并展示 `document_sources` 列表；`evidence_indices` 与回答 `[N]` 顺序一致。
- AC-4：BUG-007 复测：3-5 个 PDF 样例的 `document_sections.path` 无空 path / 同 level 错乱 / 中文章节异常；若有失败，归因 + 登记新 BUG。
- AC-5：BUG-006 五子项真 PG 复测：5 子项各至少一条结构化结论；若有失败，归因 + 登记新 BUG / TD。
- AC-6：任何未通过项必须归因到「检索 / 数据 / prompt / LLM / 前端引用 / 文档解析」其中之一；归因为 "未知" 或 "已通过但实际没通过" 视为 AC-6 失败。
- AC-7：跨事实源同步：Backlog / Milestone / Iteration / Requirement / current-work / work-log / BUG-006/007 行的"真 PG 复测"字段全部更新；无互相矛盾的状态。
- AC-8：交付门禁：`scripts/check-engineering-docs` 退出码 0；`git diff --check` 干净；PR 描述含 Summary / Scope / Validation / Risks / Docs。

## Validation

- Backend / 验收脚本：
  - `python scripts/validate_real_pg_rag.py backfill --out <report>` 退出码 0
  - `python scripts/validate_real_pg_r.py ask --out <report>` 退出码 0
  - `python scripts/validate_real_pg_r.py report --out <report>` 退出码 0
  - 报告文件存在，结构与 spec §6 一致
- Quality gates：
  - `scripts/check-engineering-docs` 退出码 0
  - `git diff --check` 干净
  - PR 描述齐全
- Required:
  - 真 PG 必跑；环境与命令在报告中记录
  - 不通过项必须登记新 REQ / BUG / TD

## Risks

| 风险 | 缓解 |
|------|------|
| PG 环境不可用 | 脚本明确报错，验收报告不伪造通过 |
| 样例文件不在 dev 库 | Plan 阶段先 list；不满足则降级为"已尽力，无样例" + 记归因 |
| LLM 不可用 / 慢 | ask 子命令显式记录 LLM 调用耗时；超时则不通过 |
| 验收脚本本身有 bug | Plan 阶段先 dry-run 一次；不进入正式验收 |
| 发现明显 BUG-006/007 残留问题 | 不在同 PR 修；登记新 BUG-xxx，记 AC-4/5 状态为"未通过但已登记" |
| scripts 目录不接受 | 落到 `scripts/validation/` 之类子目录；保持与现有 `scripts/engineering/` 区分 |
| PR 范围扩张 | 严格只包含：spec / plan / report / 验收脚本 / 跨事实源同步 / 必要文档状态更新 |
