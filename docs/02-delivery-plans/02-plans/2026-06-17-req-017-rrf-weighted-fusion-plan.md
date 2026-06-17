# REQ-017 RRF / Weighted RRF 融合排序收口 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-17-req-017-rrf-weighted-fusion.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-017-p2-rrf-weighted-fusion.md`

## Scope

本 plan 实现 REQ-017 的 weighted RRF 生产配置收口，不重复实现已有 `RRFFusion`，不为 REQ-018 的 graph_edge 通道提前关闭验收。

## Slice 1 — 配置入口与环境变量

**目标：** `RRF_CHANNEL_WEIGHTS` 可通过环境变量注入生产 service。

**建议动作：**
- 在 `ai_router.py` 的 `_build_evidence_service()` 读取 `RRF_CHANNEL_WEIGHTS` 环境变量或 `.env` 配置。
- 默认值 `{vector:1.0, keyword:1.0, graph_node:0.5}` 写入注释或常量。
- 生产 service 构造时把 `RRFFusion(channel_weights=weights)` 传入 `AIChatService.__init__`（需先确认 `__init__` 是否支持 `evidence_fusion` 参数化）。

**验收：**
- 环境变量为空时使用默认值，不抛错。
- 不同权重配置下，fixture 验证融合排序不同。
- `ruff clean` + `git diff --check`。

## Slice 2 — Fusion Diagnostics 扩展

**目标：** `diagnostics` 输出 RRF 分值、通道排名和权重配置。

**建议动作：**
- `PackedContextDiagnostics` 新增字段（向后兼容，Pydantic `extra="ignore"` 保证）。
- `AIChatService.chat()` 在调用 `context_packer.pack()` 后，把 `fusion_scores` 和 `channel_ranks` 填入 `packed.diagnostics`。
- `_build_prompt_context` 不变（diagnostics 只进入 trace，不进入 prompt）。

**验收：**
- 有 fixture 验证 `packed.diagnostics.fusion_scores` 非空。
- 有 fixture 验证 `packed.diagnostics.channel_ranks` 含每个通道的 evidence_id→rank。
- `pytest tests/contexts/knowledge/test_context_packer.py -q` 全部通过。

## Slice 3 — 通道降级与单通道异常保护

**目标：** 任一召回通道抛异常时，其他通道继续工作，diagnostics 记录失败原因。

**建议动作：**
- 检查 `CompositeChunkRetriever` 和 `PgGraphRetriever` 的通道级 try/except 是否完整。
- 补充 `graph_node` 通道异常的 fallback。
- 在 `FakeRetriever` 中增加 `raise_on_call` 标志用于测试通道降级。
- 新增测试：`test_ai_chat_service_continues_when_one_channel_fails`。

**验收：**
- 单通道抛异常时，回答仍返回（非空 reply），diagnostics 含 `channel_errors` 字段。
- 其他通道正常工作的 evidence 仍进入 prompt。

## Slice 4 — 真实样例 RRF 排序分析（依赖 REQ-015）

**目标：** 用 REQ-015 的真实 PG 样例验证 RRF 排序效果。

**建议动作：**
- 确认 REQ-015 已完成真实 PG 样例 fixture。
- 在 `scripts/validate_real_pg_rag.py` 或独立 script 中输出各通道 topN、融合前排名、RRF 权重配置、融合后排名、最终 evidence 列表。
- 对"目录 chunk 压过正文 chunk"场景验证权重配置能改变结果。

**验收：**
- 真实 PG 样例证明正文 chunk 排名在目录 chunk 之前。
- trace 可完整复盘每个 evidence 的通道来源和 RRF 分值。

**注意：** 如 REQ-015 的真实 PG 环境暂不可用，先用 mock fixture 覆盖上述验证维度。

## Files To Inspect First

- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
- `packages/server-python/app/contexts/knowledge/application/evidence_fusion.py`
- `packages/server-python/app/contexts/knowledge/application/context_packer.py`
- `packages/server-python/tests/contexts/knowledge/test_evidence_fusion.py`
- `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py`

## Required Checks

- `cd packages/server-python && pytest tests/contexts/knowledge/test_evidence_fusion.py tests/contexts/knowledge/test_ai_chat_service.py tests/contexts/knowledge/test_context_packer.py -q`
- `ruff check app/contexts/knowledge/`
- `scripts/check-engineering-docs`
- `git diff --check`

## Documentation Closure

完成后必须同步：
- `docs/01-product-planning/04-backlog.md`：REQ-017 状态
- `docs/01-product-planning/05-requirements/REQ-017-...`：Delivery Record
- `docs/01-product-planning/02-milestones/02-growth-phase.md`：P2 open item 状态
- `docs/03-engineering-governance/current-work.md`：候选 / 进行中 / 最近完成
- `docs/03-engineering-governance/work-log.md`：一行式索引
