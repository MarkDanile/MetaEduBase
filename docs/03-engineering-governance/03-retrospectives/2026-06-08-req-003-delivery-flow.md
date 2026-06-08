# REQ-003 / REQ-007 交付流程复盘

日期：2026-06-08

## Signals

- REQ-003 完成后，复核发现部分验收声明强于实际测试覆盖范围。
- REQ-007 收口过程中，产品规划层、工程工作台和技术债总账曾出现状态、AC 数量和交付记录漂移。
- 同一验证命令在不同执行环境下含义不同：mock-based 路径可复现，依赖 PostgreSQL 的集成测试仍受本机环境阻塞。

## Root Cause

- Follow-up 类型分流不够明确，需求验收缺口、技术债、流程问题容易混成一个后续任务。
- 完成门禁要求“状态不矛盾”，但没有把 Backlog、Requirement、Iteration、Milestone 和 current-work 明确为同一组事实源。
- 文档门禁脚本缺少跨事实源状态一致性、最近完成索引和交付占位检查。

## Corrective Actions

- `DOC-031` 在 `task-modes.md` 中补充 Follow-up 分流规则。
- `DOC-031` 在 `quality-gates.md` 中明确关闭 `REQ-xxx` 时必须回查产品规划层和工程工作台状态组。
- `DOC-031` 增强 `scripts/check-engineering-docs`，用脚本拦截可机械判断的状态漂移和占位残留。

## Follow-up Policy

- 原需求验收缺口继续走 `REQ-xxx`，并使用 `Parent:` 指向来源需求。
- 可维护性、测试基础设施或质量门禁问题走 `TD-xxx`。
- 规则、文档、流程和门禁问题走 `DOC-xxx`。
- 需要执行的后续问题必须有稳定编号、证据、完成标准和验证方式。
