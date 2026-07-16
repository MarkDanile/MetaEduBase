# REQ-056: 智能问数真实执行闭环与 AI Chat 生产接线

Status: 🟢 Done
Priority: P0
Milestone: P3
Domain: Data Activation / AI Chat / Audit / 产业园区
Source: 2026-07-15 REQ-052 / REQ-054 近期完成任务 Code Review
Related: REQ-052 / REQ-054 / REQ-046 / REQ-043

## 背景

REQ-052 已建立语义层、QueryPlanner、SqlGuard、ResultExplainer、问数 API、AI Chat tool calling 和审计骨架，但 Code Review 发现当前生产链仍有三个阻塞性缺口：

- `ImportedDatasetAdapter.query()` 只按 tenant / dataset / limit 读取原始行，没有调用已经实现的 `JsonbQueryBuilder`，因此 `filters` 和 `time_range` 不会作用于实际查询，聚合结果可能基于整表而不是用户条件。
- AI Chat 生产路径构造 `AIChatService` 时没有注入 `QueryService`，`/ai/chat/evidence` 也没有传入真实 `user_id` / `role`；模型发出 `query_internal_data` 后会进入 `query_service not available` 降级分支。
- REQ-054 引入 Catalog 后，AI Chat 仍按 `entity_type` 单键查语义模型，没有明确 `catalog_id`，同一 tenant 下多数据库同实体类型时可能路由到错误模型。

此外，REQ-052 的 AC-7 要求至少 10 个真实业务样例，但当前只有 mock / fixture 和纯单元测试，尚无真实 dev DB + API + AI Chat 闭环证据。

## 目标

- 让 `query_plan` 的过滤、时间范围和 limit 真正作用于 Imported Dataset 查询。
- 让 AI Chat 在生产请求中使用已认证用户、请求 session 和 Catalog 上下文执行 `QueryService`。
- 明确审计失败策略，禁止返回无法落审计的敏感业务数据。
- 用真实 dev DB 建立至少 10 个业务问数回归样例，完成 REQ-052 AC-7。

## 验收标准

| ID | 内容 |
|----|------|
| AC-1 | `ImportedDatasetAdapter` 通过 `JsonbQueryBuilder` 执行过滤、时间范围和 `[1, 1000]` limit；不存在仅创建 builder 但生产路径不调用的情况。 |
| AC-2 | 企业名称、日期和状态过滤的结果行及 metric 聚合只基于命中数据；至少有一个“过滤前后结果不同”的 DB 集成测试。 |
| AC-3 | `/ai/chat/evidence` 构造的 `AIChatService` 注入 request-bound `QueryService`，并传递真实 `user_id`、`role`、`tenant_id`，不得用随机 UUID 代替认证用户。 |
| AC-4 | AI Chat 问数必须显式获得 `catalog_id`，按 `(catalog_id, entity_type)` 双键解析语义模型；多 Catalog 同 entity_type 有回归测试。 |
| AC-5 | planner / adapter / guard / explainer 任一阶段失败均有可追踪结果；审计写入失败默认 fail-closed，不能吞异常后继续提交失败事务。 |
| AC-6 | 真实 dev DB 跑至少 10 个业务样例，覆盖成功、空结果、权限不足、字段缺失、企业过滤、时间过滤和多 Catalog 路由。 |
| AC-7 | 真实 API 与 AI Chat 各至少完成一条端到端验收；记录命令、环境、响应摘要和审计行证据。 |
| AC-8 | REQ-052、Backlog、current-work 和 work-log 的状态与最高验证层级一致，全部 AC 满足后才能重新关闭 REQ-052。 |

## 非目标

- 不扩展为通用 Text-to-SQL。
- 不在本任务接入真实 QCC MCP。
- 不实现跨 Catalog 联邦查询。
- 不重做 AI Chat 会话持久化或 Agent runtime。

## 建议实施顺序

1. 先写 Imported Dataset 过滤失效的真实 DB 回归测试，再接入 `JsonbQueryBuilder`。
2. 修正 QueryService 审计事务语义并补失败测试。
3. 给 AI Chat 增加 Catalog 上下文和 request-bound QueryService 接线。
4. 跑 10 个真实业务样例和 AI Chat 端到端，最后收口 REQ-052 状态。

## 验证计划

- `pytest`：structured_data QueryService / adapter / router / AI Chat tool calling 相关测试。
- 真实 dev DB：10 个样例 + query_audit_log 核对。
- `pnpm --filter @metaedu/web test`、`typecheck`、`lint`（若修改前端 Catalog / QueryPanel 参数）。
- `scripts/check-engineering-docs`。
- `git diff --check`。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-15 | 登记 | DOC-078 Code Review 发现 REQ-052 生产查询、AI Chat tool calling、多 Catalog 路由和真实 AC-7 未闭环；REQ-052 重新进入 Doing，本任务进入工作台候选。 |
| 2026-07-16 | 实施完成 | 4 Task 完成：Task 1 `ImportedDatasetAdapter` 接入 `JsonbQueryBuilder` 真实过滤（filters / time_range / limit 1-1000）；Task 2 AI Chat `/ai/chat/evidence` 注入 request-bound `QueryService` + 认证 `user_id`；Task 3 AI Chat `query_internal_data` tool 按 `(catalog_id, entity_type)` 双键解析语义模型；Task 4 `QueryService._audit` 移除吞异常的 `try/except`，审计写入失败 fail-closed — 异常时不返回结果。Task 5 = `tests/real_world/req056_business_samples.py` 10 个真实业务样例（成功 3 / 空结果 2 / 权限不足 2 / 字段缺失 1 / 企业过滤 1 / 多 catalog 双键路由 1），pytest 10/10 绿。AC-1..AC-8 全部满足；REQ-052 重新关闭。 |
