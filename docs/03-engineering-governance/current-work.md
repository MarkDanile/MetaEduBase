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

### TASK-R1-S4B-IMPL: R1-S4-B 实现（migration 040 + backfill）

状态：🟡 实现完成，停在 PR 交接（待独立 max/Codex 复审，不自行合并）
类型：新需求开发（Slice schema+backfill 实现）
领域：Backend（composition / agent_workspace / agent_execution transport schema + backfill）
当前执行模式：superpower / plan-do
最近接手工具：Claude Code
分支：feat/req041-047-r1-s4b-schema-backfill

需求来源：
- Spec: docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md（§5.2/§6/§7 owner 边界、external ref、迟到写）
- Plan: docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4transport-ownerexternal-payload-与迟到写（§S4-A D1-D8 + §S4-B B1-B8 契约冻结块）
- 架构约束：docs/03-engineering-governance/01-rules/architecture.md

当前进展：M1-M4 已实现完成 + 前五轮独立复核全部修复闭合（第一轮 #1-#7 / 第二轮 #1-#7 / 第三轮 6 项 / 第四轮 4 项 / 第五轮 5 项 P1×2+P2×2+P3×1：transport 依赖图锁序 + CLI exit 优先级 + verify owner/issue_code 精确绑定 + rows_attempted 预算 + partial batch 间隔 + 工作台文案）。**第六轮独立复审（当前）**：P1×1（第五轮提交未推送进 PR——已 push `9d63ab33` 修复）+ P2×1（CLI 参数校验可绕过：前置 `_validate_backfill_params` 于 tenant 循环前统一校验，空 tenant 也拒绝非法参数）+ P3×1（模块 docstring 冲突契约改 `conversation_scope` -> `tenant_scope`）。六轮修复全部落地并有判别力回归测试（TDD red/green 已验证）。
下一步：PR #530 已建，第五轮提交已推送（PR HEAD = `9d63ab33`），第六轮 P2/P3 修复随本次提交推送，随后等待第七轮独立 max/Codex 定向复审，不自行合并。erase_available 保持 False。
验证状态：`uv run ruff check`（changed files 0 错误）/ `scripts/check_mypy_baseline.py`（243 historical，0 回归）/ `scripts/check-engineering-docs --full` 通过（32 allowlisted）/ `git diff --check` 干净；`pytest tests/composition/test_agent_transport_*.py` S4-B 专项 58 passed（含第六轮 2 新测试）；第五轮修复点 TDD red/green 已验证（旧逻辑 4 测试全红、修复后全绿）；第六轮修复点 TDD red/green 已验证（旧逻辑 2 测试全红、修复后全绿）；全量回归 `pytest tests/ -q -m "not external_network"` 2090 passed / 0 failed / 4 deselected（6m59s）。
交接备注：S4 拆分 S4-A~F；PR 至少 4 个。明确排除：S4-C/D/E/F、S5 scheduler、真实 Pi Worker、云对象存储生产 adapter；migration 034-039 已冻结，S4-B 新增 040（expand-only）；erase_available 保持 False（writer fence 在 S4-C，purge 在 S5）。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1-P | REQ-042 Agent Workspace 塑形 | 🔵 Ready for Docs Only | 可并行塑形 Conversation/Run/Event UI 契约；完整代码实现等待 R1/C1 | [Requirement](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md) |
| P1 | REQ-047 C1 Durable Core 总验收 | ⚫ Blocked by R1-S1..S6 | R1 全部验收后执行联合 conformance 与文档收口 | [Joint Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-c1durable-core-总验收与文档收口) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-08-04 | R1-S4-B Transport/External Schema + Backfill 契约冻结 | 🟢 完成 | 冻结 migration 040 schema（四表 scope 列 + 两 ledger + inbox tombstone）+ 回填矩阵 + 三态 reconcile（advisory lock 集合锁入 D8）+ external 空 allowlist + 041 guard 冻结 + scope/epoch 双维 verify；七轮复审 0/0/0/1 | [PR #528](https://github.com/MarkDanile/MetaEduBase/pull/528)（squash merge `b2020d4c`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-04 | R1-S4-A Transport/External/Late-write 契约冻结 | 🟢 完成 | 盘点 4 张 inbox/outbox 与 transport owner 映射；冻结 D1-D8（结构化 owner scope、epoch 传播链 + 六元组 CAS、历史不确定行三态 reconcile、tombstone 留 digest、external ref ledger 全覆盖、部分 ACK 不标 completed、runtime fake 仅证明协议、claim/Guard 顺序）；三轮复审 0/0/0/0 | [PR #526](https://github.com/MarkDanile/MetaEduBase/pull/526)（squash merge `cf4c8374`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-04 | R1-S3-E Dispatch、竞态与收口 | 🟢 完成 | dispatch_output deterministic late-write 终态化（幂等原语 + claim CAS）+ purge-fenced projection/read 重分类 deterministic + race/幂等真实 PG 反例 + backfill 钉住 execution.core.v1 + no-bypass 守卫；三轮复审 0/0/0/0；变异逐项 KILLED；三路 CI 全绿 | [PR #524](https://github.com/MarkDanile/MetaEduBase/pull/524)（squash merge `916699db`）/ [work-log](work-log.md) / [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| 2026-08-03 | R1-S3-D ExecutionErasureParticipant（execution.core.v1 正文清除 + final scan + ACK fencing） | 🟢 完成 | migration 039 行级守卫白名单 + 正文清除 + final scan + 完整 fencing + blocked 三方一致 + 真实计数 ACK digest；四轮复审 0/0/0/0；变异逐项 KILLED；erase_available 翻 True；Backend 2016 passed / 0 failed；三路 CI 全绿 | [PR #522](https://github.com/MarkDanile/MetaEduBase/pull/522)（squash merge `99142f15`）/ [work-log](work-log.md) / [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| 2026-08-02 | R1-S3-C Writer fence（13 接线 + 9 writer 矩阵 + 锁链修复 + 真 e2e） | 🟢 完成 | composition-owned FencedExecutionPort + 9 writer wrapper + 13 call site；锁链全路径 Spec §6.1 与 S3-D 同序无 AB-BA；verdict 内建 + Run 归属绑定 + 跨边界 Protocol；变异 2 组 + 真 e2e 6 组；复审 0/0/0；Backend 1951 passed | [PR #519](https://github.com/MarkDanile/MetaEduBase/pull/519)（merge `eb911b9a`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-07-31 | R1-S3-B Schema 与基础契约（actor tombstone + shared digest + per-owner source key） | 🟢 完成 |  migration 038 + shared digest helper + per-owner source key + tombstone 契约（6 处 fail-closed guard + `DirectRagTerminalReplayError` 透传）；6 轮 max 复审收口 0/0/0；23 文件 / 1689 增；三路 CI 全绿（Backend 8m52s） |
| 2026-07-30 | R1-S3-A Execution owner 契约注记/plan delta（先于代码冻结） | 🟢 完成 | 纯文档冻结 execution.core.v1 participant 设计（fenced port + 9 writer 矩阵 + migration 038 actor tombstone + per-owner source key + event 计数器 + S3/S6 拆分）；两轮 max 复审 + 轻量复核 0/0/0；S3-A~E PR 拆分冻结；三路 CI 全绿 | [PR #515](https://github.com/MarkDanile/MetaEduBase/pull/515)（merge `2d4f8091`）/ [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-30 | R1-S2-D/E workspace 正文清除 + participant ACK + final body scan | 🟢 完成 | workspace.core.v1 participant 正文清除 + body scan + ACK；V1 冻结契约（fingerprint 持久化 migration 037 + 构造器禁覆盖 + placeholder denylist）；7 轮 max 复审 P0/P1/P2=0/0/0；全量 1908 passed；三路 CI 全绿 | [PR #513](https://github.com/MarkDanile/MetaEduBase/pull/513)（merge `5db40361`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-29 | R1-S2-C ingress checkpoint source key + title/create fence + backfill 锁序 | 🟢 完成 | ingress 真实 source key + verdict/advance 拆分 + title/create 接 fence + backfill 消 AB-BA + deleted 410/redacted envelope + migration 036 归一；四轮 max 复审清零；全量 1849 passed；三路 CI 全绿 | [PR #511](https://github.com/MarkDanile/MetaEduBase/pull/511)（merge `2ceaffd0`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-28 | R1-S1 Fence/Hold/Purge schema 基座 | 🟢 完成 | owner key 锁 + owner registry + 四协调表 + tombstone + fence 状态机（16 边）+ backfill 恢复契约；六轮 max 复审 P0/P1/P2=0/0/0；全量 1777 passed；dev 已 reset 到 034 head | [PR #506](https://github.com/MarkDanile/MetaEduBase/pull/506)（merge `b8cbdf14`）/ [Plan §R1-S1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-27 | REQ-060 Slice 4 移动端 + a11y + Playwright + 收口 | 🟢 完成 | useMobileDrawer + LayoutView 重构（30 新增 vitest）+ Playwright 3 组 spec（55/55）；326/326 vitest；三路 CI 全绿；六轮复审 P0/P1/P2=0/0/0；评分 95 | [PR #503](https://github.com/MarkDanile/MetaEduBase/pull/503)（）/ [Plan §Slice 4](../02-delivery-plans/02-plans/2026-07-23-req060-console-ia-nav-rbac-plan.md) / [work-log](work-log.md) / [scorecard](04-retrospectives/review-score-log.md) |