# REQ-014: RAG 真实 PG 样例、数据回填与回答 grounding 验收

Status: 🟢 Done
Priority: P1
Milestone: P2
Parent: REQ-013
Related: REQ-012 / REQ-013 / BUG-006 / BUG-007 / TD-051 / TD-054

## Problem

REQ-012 / REQ-013 已经把 AI Chat 推进到 evidence-aware RAG 和 Context Packer，但近期评审仍看到一个共同缺口：代码与 mock 测试证明了机制存在，真实 PG 样例、历史数据回填、文档解析质量和最终回答质量还没有作为一个闭环验收。

典型风险：

- “python 的基本数据类型有哪些？”不能只命中目录或孤立 chunk，必须把正文上下文送入 prompt。
- BUG-007 修复了 `pdf_parser` section path 算法，但真实样例 reparse / backfill 结果需要集中验收。
- BUG-006 5 个子项已经合并，但 Backlog 仍记录“待真 PG 复测验证”。
- REQ-013 Slice 5 明确留下“真实 PG 样例待 backfill”。

## Scope

- 选定 3 到 5 个真实样例文件，至少包含 Python 操作指南 / 教程类文档，以及近期使用的课程标准、人才培养方案或教案样例。
- 对样例执行必要的数据初始化或重建：parse、chunk、embed、tsvector、KG 回源或等价维护入口。
- 跑 AI Chat 真实问题，记录 retrieval topN、fusion topN、packed context 摘要、最终回答和文档级来源。
- 验证引用 `[N]`、文档级来源列表、chunk 定位或降级行为与前端体验一致。
- 将结果回填到 Requirement、Iteration、Milestone、Backlog 和 work-log。

## Non-Goals

- 不在本需求中引入 Elasticsearch、Milvus、Neo4j 或完整 GraphRAG。
- 不重写 REQ-013 Context Packer 结构；只验证和补齐真实数据闭环。
- 不把所有历史文件默认全量重建；先用代表样例和可复现命令建立验收基线。

## Acceptance

- AC-1：真实 PG 样例完成数据重建或说明无需重建，且记录命令、环境、退出结果。
- AC-2：“python 的基本数据类型有哪些？”的 packed context 包含正文解释性内容，不以目录作为唯一主证据。
- AC-3：AI Chat 最终回答可用、可引用，并能展示文档级来源。
- AC-4：BUG-007 关联样例的 `sections.path` 在 reparse 后无异常空 path，或明确剩余样例和原因。
- AC-5：BUG-006 5 子项完成一次真 PG 综合复测，结论同步 Backlog。
- AC-6：如果真实样例仍失败，必须把失败归因到检索、数据、prompt、LLM、前端引用或文档解析，并登记后续 `REQ` / `BUG` / `TD`。

## Validation

- 后端相关 pytest 或 e2e。
- `scripts/check-engineering-docs`
- `git diff --check`
- 真 PG 样例问答验收记录：问题、命中文档、packed context 摘要、最终回答、来源列表。

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Iteration: `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
