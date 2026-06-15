# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| （无 — 当前进行中为空） | | | | | | |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| （无 — 下一批候选任务空） | | | | |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-15 | BUG-006 #1 模板抽取页面字段名渲染 label（递归 children + keyPath + multi-template）| 🟢 完成 | PR #297 squash merge：抽 getTemplateFieldLabel 到 utils/templateLabels.ts；3 轮迭代（round 1 children+dot-path / round 2 items+columns+keyPath / round 2.5 multi-template）。9 vitest + 64/64 frontend tests 0 回归。 | [BUG-006 #1](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #297](https://github.com/MarkDanile/MetaEduBase/pull/297) |
| 2026-06-15 | BUG-006 #4 KG > 50 节点白屏（kg-bundle 原子端点）| 🟢 完成 | PR #295 squash merge：后端新增 GET /api/v1/knowledge/files/{file_id}/kg-bundle 双端 IN 过滤保证 edges.source/target 都在 nodes 列表。3 PG pytest + 437 mock pytest 0 回归 + 真 PG 复测教案 65 / 课程标准 70 / 人才培养方案 58 三文件 dangling=0。 | [BUG-006 #4](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #295](https://github.com/MarkDanile/MetaEduBase/pull/295) |
| 2026-06-14 | TD-054 chunker 内部 char_offset / local_offset 同步修复（round 2+3）| 🟢 完成 | PR #289 + #290 squash merge：chunker 主循环 + 合并分支 + _split_oversized_chunk pos 同步。10/10 mock pytest + 439 mock pytest 0 业务代码回归。真 PG 复测 28 chunks offset_overlaps 23/28 (82.14%) → 0/28 (0.00%)。 | [TD-054](technical-debt.md#td-054) / [PR #289](https://github.com/MarkDanile/MetaEduBase/pull/289) + [PR #290](https://github.com/MarkDanile/MetaEduBase/pull/290) |
| 2026-06-14 | TD-067 LLM 抽取 `teaching_plan` / `practice_links` 失败返 `-` | 🟢 完成 | PR #287 squash merge `2b983b2`：extract_template_prompts 新增 `build_few_shot_examples` 锚定 schema (3 例)；简单模板零开销。8/8 新 pytest + 429/429 全 pytest 0 业务代码回归。 | [TD-067](technical-debt.md#td-067) / [PR #287](https://github.com/MarkDanile/MetaEduBase/pull/287) |
| 2026-06-14 | BUG-005 `parse` 完成后未回写 `files.doc_type` / `template_id` | 🟢 完成 | PR #285 squash merge `df94203`：alembic 011 + extract_template helper + 7 mock pytest 全过。dev 库 `evidence_coverage file_metadata 0% → 100%`；421/421 pytest 0 业务代码回归。 | [BUG-005](../01-product-planning/05-requirements/BUG-005-files-doc-type-not-backfilled.md) / [PR #285](https://github.com/MarkDanile/MetaEduBase/pull/285) |
| 2026-06-13 | TD-057 task 函数返回值契约（10 个 `_do` 修复合片系列） | 🟢 完成 | 10 follow-up PR #258/#260/#262/#264/#267/#269/#271/#273/#275/#280 全部 MERGED；414/414 mock pytest 0 业务代码回归。 | [TD-057](technical-debt.md#td-057) / [PR #258](https://github.com/MarkDanile/MetaEduBase/pull/258) (slice 1) + [PR #280](https://github.com/MarkDanile/MetaEduBase/pull/280) (TD-066) |
| 2026-06-13 | TD-066 ds_build_cross_dataset_edges 返 edge count | 🟢 完成 | PR #280 squash merge `c343de7`：`_do` 返 `edges_created` int + outer 补 return。4 mock pytest 全过；414/414 mock pytest 0 业务代码回归。 | [TD-066](technical-debt.md#td-066) / [PR #280](https://github.com/MarkDanile/MetaEduBase/pull/280) |
| 2026-06-13 | TD-065 ds_embed 返 embedded count | 🟢 完成 | PR #275 squash merge `f878303`：`_do` 返 `success_count` int + outer 补 return。4 mock pytest 全过；44/44 mock pytest 0 业务代码回归。 | [TD-065](technical-debt.md#td-065) / [PR #275](https://github.com/MarkDanile/MetaEduBase/pull/275) |
| 2026-06-13 | TD-064 ds_extract_kg 返 KG entity/relation counts | 🟢 完成 | PR #273 squash merge `8bb8b82`：`_do` 返 `{"entities": N, "relations": M}` dict + outer 补 return。4 mock pytest 全过；12/12 mock pytest 0 业务代码回归。 | [TD-064](technical-debt.md#td-064) / [PR #273](https://github.com/MarkDanile/MetaEduBase/pull/273) |
| 2026-06-13 | TD-063 ds_parse 返 parsed row count | 🟢 完成 | PR #271 squash merge `86bd88c`：`_do` 返 `len(parsed.rows)` int + outer 补 return。4 mock pytest 全过；40/40 mock pytest 0 业务代码回归。 | [TD-063](technical-debt.md#td-063) / [PR #271](https://github.com/MarkDanile/MetaEduBase/pull/271) |
| 2026-06-13 | TD-062 extract_knowledge_graph 返 KG 概要 dict | 🟢 完成 | PR #269 squash merge `855a4c7`：`_do` 返 `{"nodes": len(node_name_map), "edges": edges_inserted}` dict + outer 补 return。4 mock pytest 全过；56/56 mock pytest 0 业务代码回归。 | [TD-062](technical-debt.md#td-062) / [PR #269](https://github.com/MarkDanile/MetaEduBase/pull/269) |
| 2026-06-13 | TD-061 extract_template 返 extracted field count | 🟢 完成 | PR #267 squash merge `c6fd467`：`_do` 返 `len(template_data)` int + outer 补 return。4 mock pytest 全过；52/52 mock pytest 0 业务代码回归。 | [TD-061](technical-debt.md#td-061) / [PR #267](https://github.com/MarkDanile/MetaEduBase/pull/267) |
| 2026-06-13 | TD-059 embed_chunks 返 chunk count | 🟢 完成 | PR #262 squash merge `683652d`：`_do` 返 `len(chunks)` int + outer 补 return。4 mock pytest 全过；44/44 mock pytest 0 业务代码回归。 | [TD-059](technical-debt.md#td-059) / [PR #262](https://github.com/MarkDanile/MetaEduBase/pull/262) |
