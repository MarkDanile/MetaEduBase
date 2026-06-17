# REQ-015: RAG 生产链路 grounding 与真实验收收口

Status: 🟣 待验证
Priority: P0
Milestone: P2
Parent: REQ-013 / REQ-014
Related: REQ-010 / REQ-012 / P2-SEARCH / P2-RRF / BUG-003 / BUG-006 / BUG-007 / BUG-008
External:

## Delivery Record

| Date | What | Details |
|------|------|---------|
| 2026-06-17 | Production wiring + mock regression | 已把生产 AI Chat endpoint 改为按请求注入 `ContextPacker(ChunkRepository(session), tenant_id)`；默认融合切到 `RRFFusion` 并支持 weighted RRF；`AIChatService` 返回 diagnostics；`validate_real_pg_rag.py` 对齐真实接口字段、认证 token、当前 `metaedu.*` schema、`document_chunks` section 统计和 BUG-006 / BUG-007 真实复测入口；新增 Python 基本数据类型 packed context 行为回归，并锁定 hit block 优先使用 `document_chunks.content` 完整正文。验证：40 focused pytest passed；`test_ai_chat.py` 5 passed；ruff passed；`py_compile scripts/validate_real_pg_rag.py` passed；web typecheck / docs gate / diff check passed。真 PG 样例仍需 dev DB + LLM key 后执行，不能视为已通过。 |
| 2026-06-17 | Real dev validation without external LLM | 已启动真实 dev DB、后端服务，并用开发账号获取真实 JWT。`backfill` / `bug007` / `bug006` / `report` 非外发验收通过运行，报告见 [REQ-015 validation report](../../02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-validation-report.md)。截停在 LLM 前的真实链路发现：样例数据完整，但生产编排仍未把 Python 数据类型正文 chunk 放入 prompt；根因分流到 [BUG-009](BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md)。外部 LLM 调用会发送 dev 文档内容到第三方 provider，本次因安全风险未执行，需用户显式批准。 |

## Problem

REQ-013 已实现 Context Packer 模块，REQ-014 已建立真实 PG 验收脚本入口，但复核发现二者没有形成真实生产闭环：

- 生产 `/api/v1/ai/chat/evidence` 默认服务未注入 `ContextPacker`，真实 AI Chat 仍可能只使用融合后的原始 evidence。
- 接口没有返回 diagnostics，无法确认 query、各通道 topN、fusion topN、packed context 和 prompt 片段。
- 真实 PG 验收脚本与接口契约不一致：脚本发送 `question/top_k` 并读取 `answer/evidence/diagnostics`，接口实际是 `message/context_window` 与 `reply/sources/document_sources`。
- “python 的基本数据类型有哪些？”仍缺生产级回归样例，不能只证明 response shape。
- 默认融合仍是 `SimpleFrequencyFusion`，P2 规划的 RRF / weighted RRF 未进入生产默认路径。
- 图谱 evidence 有 `source_chunk_id` 时可以回源，但缺少“最终落到 chunk / section”可观测验证。
- 切片、metadata、`source_chunk_id` 调整后的历史数据重建 / 重新索引仍没有真实样例验收结果。

## Users / Scenarios

- 学生在 AI Chat 中询问资源库已有正文内容，例如“python 的基本数据类型有哪些？”。
- 教师用 AI Chat 检查上传教材、课程标准或人才培养方案能否被准确引用。
- 后续 APP-001 到 APP-004 需要复用同一套可观测、可验证的 RAG grounding 基座。

## Scope

### Backend

- 生产 AI Chat endpoint 必须按请求注入 `ContextPacker`，并使用请求绑定的 DB session 和 tenant。
- `AIChatService` 返回 diagnostics，至少包含：
  - `query`
  - `retrieval_topn`
  - `fusion_topn`
  - `packed_blocks`
  - `prompt_preview`
  - packer summary
- 默认融合切换为 `RRFFusion`，并保留 weighted RRF 参数能力。
- `ContextPacker` 支持相邻 chunk 和同 section / 父章节扩展；graph evidence 有 `source_chunk_id` 时，最终 packed block 内容来自 `document_chunks.content`。

### Validation Tooling

- 修正 `scripts/validate_real_pg_rag.py` 与真实接口契约对齐。
- 样例问题至少包含“python 的基本数据类型有哪些？”。
- 报告必须能记录真实 retrieval / fusion / packed / answer / document sources。

### Data / Reindex

- 如果现有样例数据缺 metadata、chunk、embedding、tsvector 或 KG 回源字段，必须记录重建 / reinitialize / backfill 命令和退出结果。
- 不默认全量重建所有历史资源；先对样例文件建立可复现路径。

## Non-Goals

- 不在本需求引入 Elasticsearch、Milvus、Neo4j 或完整 GraphRAG。
- 不重写文档解析器或 chunker；若真实样例证明解析质量仍不足，另开 BUG / TD。
- 不做 AI Chat 前端视觉改版；只保持新增 diagnostics 对现有 UI 兼容。

## Acceptance

- AC-1：生产 `/api/v1/ai/chat/evidence` 默认路径实际使用 `ContextPacker`，不是只在 mock 测试中使用。
- AC-2：接口响应包含 `diagnostics`，并能追踪各通道 topN、融合 topN、packed blocks 和 prompt 片段。
- AC-3：真实验收脚本请求 / 响应字段与接口一致，能消费 `reply/sources/document_sources/diagnostics`。
- AC-4：“python 的基本数据类型有哪些？”回归样例验证 packed context 含正文解释性内容，不只测 response shape。
- AC-5：默认融合使用 `RRFFusion`；weighted RRF 参数能力有单测覆盖。
- AC-6：graph evidence 有 `source_chunk_id` 时，packed block 最终落到 chunk 内容；无 `source_chunk_id` 时 diagnostics 能暴露缺口。
- AC-7：样例数据重建 / 重新索引动作有命令、退出码、环境和结果记录；未能执行时记录为环境阻塞而不是完成。
- AC-8：Backlog、Milestone、Iteration、Requirement、current-work、work-log 状态同步；不能把“工具存在”写成“真实验收已通过”。

## Open Questions

- 真实 PG 样例 file_id 由执行者从 dev 库选择，还是由用户指定固定资源？默认由执行者在 dev 库选择并记录。
- `diagnostics` 是否长期暴露给前端？首版作为接口字段保留，前端可忽略；后续若涉及权限或脱敏，再独立收口。

## Delivery Links

- Spec: `docs/02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-closure.md`
- Plan: `docs/02-delivery-plans/02-plans/2026-06-17-req-015-rag-production-grounding-closure-plan.md`
- Backlog: `docs/01-product-planning/04-backlog.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Iteration: `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`
- Current Work: `docs/03-engineering-governance/current-work.md`
