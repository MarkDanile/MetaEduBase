# REQ-057: Catalog 数据源 Adapter 路由与 entity_type 契约收口

Status: 🟢 Done
Priority: P1
Milestone: P3
Domain: Data Platform / Catalog / Adapter / 产业园区
Source: 2026-07-15 REQ-054 近期完成任务 Code Review
Related: REQ-054 / REQ-056 / REQ-052 / REQ-055

## 背景

REQ-054 的 Catalog CRUD、tenant 隔离、数据集归属、双键语义模型路由和前端主界面已经形成可用骨架，但交付声明与当前实现仍有两组差异：

- `DirectDBAdapter` 和 `MCPAdapter` 有独立类与单测，但 `QueryService.default_adapter_factory` 仍只接受 `imported_dataset`，真实 `/data-query/ask` 对 `direct_db` 返回 400，MCP 也无法进入编排链。
- PR #422 将 `entity_types` 从预设白名单改为数据集动态发现，但 Requirement、Spec、Plan、work-log 和 AC-1 / AC-4 仍大量声明“白名单校验已生效”和“AC-1~10 全覆盖”。

本任务先统一契约和可达路径，再决定真实 MCP 接入是否由 REQ-044 / REQ-046 承接。

## 目标

- 为 Imported Dataset / DirectDB / MCP 建立明确、可测试的 adapter registry / factory 路由。
- 明确 V1 的 entity_type 策略是“动态发现”还是“白名单”，代码、API、UI 和文档只保留一种事实。
- 用两个 Catalog、相同 entity_type 的样例验证隔离和路由。
- 修正 REQ-054 的完成声明，不把接口骨架写成真实数据源已可用。

## 待塑形决策

| 决策 | 选项 | 当前建议 |
|------|------|----------|
| entity_type | 动态发现 / 强白名单 | 保留动态发现；增加确认、重命名和治理入口，智能演化由 REQ-055 承接。 |
| DirectDB V1 | 仅 adapter 单测 / 接入 QueryService | 接入 registry，但只允许只读 SELECT、字段投影、limit 和明确凭证管理。 |
| MCP V1 | 空结果 skeleton / 显式 Not Implemented / 接真实 MCP | 未接 REQ-044 前返回明确 capability unavailable，不得伪装成功空结果。 |
| AC-10 | 三类全部可用 / 统一接口但能力分层 | 按能力分层验收，Imported 完整可用，DirectDB 受控可用，MCP 明确占位。 |

## 验收标准

| ID | 内容 |
|----|------|
| AC-1 | Adapter registry 能按配置解析 imported_dataset / direct_db / mcp；不支持类型返回稳定错误码和 capability 说明。 |
| AC-2 | DirectDB 若进入 V1，真实 API 路径可达，并覆盖只读、limit、表/字段白名单及连接失败；否则从“已完成”声明中移除。 |
| AC-3 | MCP 未真实接线时不得返回“成功 + 空数据”冒充查询完成；与 REQ-044 / REQ-046 的责任边界清晰。 |
| AC-4 | entity_type 策略在 Requirement、Spec、Plan、Backlog、API、前端和 migration 说明中一致。 |
| AC-5 | 两个 Catalog 使用相同 entity_type 时，语义模型、问数结果和审计 catalog_id 均正确隔离。 |
| AC-6 | REQ-054 的 AC 和 Delivery Record 按真实最高验证层级重写；PR #421 / #422 / #424 全部进入事实链。 |

## 非目标

- 不在本任务实现本体关系发现和孤儿检测，归 REQ-055。
- 不在本任务实现完整 MCP Registry，归 REQ-044。
- 不实现跨 Catalog 查询。

## 验证计划

- Adapter factory / registry 单测。
- DirectDB 集成测试或明确的未实现契约测试。
- 两 Catalog 同 entity_type 的真实 DB 集成测试。
- 前端 Catalog / QueryPanel 参数测试。
- `scripts/check-engineering-docs`、`git diff --check`。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-15 | 登记 | DOC-078 Code Review 发现 REQ-054 adapter 可达性和 entity_type 动态发现契约未收口；作为有条件关闭后的必修 follow-up。 |
| 2026-07-20 | Task 1 完成 | Adapter registry 3 类型路由：imported_dataset / direct_db / mcp 统一解析；MCP 改为显式抛 CapabilityUnavailableError（QueryService.ask 捕获后写审计 ok=False，不伪装成功空结果）；router 测试覆盖（commits `62aad607` / `5cf4b649`）。 |
| 2026-07-20 | Task 2 完成 | 两 Catalog 同 entity_type 隔离集成测试补齐（AC-5）：语义模型、问数结果和审计 catalog_id 均正确隔离（commit `736cf2e1`）。 |
| 2026-07-20 | Task 3 完成 | 文档统一：REQ-054 AC 按真实最高验证层级重写（白名单 → 动态发现 + AC-10 能力分层）；spec / plan 顶部加修正说明；backlog / current-work / work-log 状态同步。验证：structured_data 后端 226 tests pass / ruff 0。 |
