# Iterations — 迭代计划

本目录记录当前和近期迭代。它服务于排期和阶段交接，不替代 `docs/03-engineering-governance/current-work.md` 的当前执行状态。

## 当前迭代

当前没有已批准的进行中迭代。P3 后续工作按 backlog 既定顺序进入 REQ-042 Workspace、REQ-043 Runtime/Tool Gateway 等独立事实源推进，阶段状态见 [P3 Milestone](../02-milestones/03-agent-platform-phase.md#current-iteration)。新的 P3 iteration 须另行立项后再登记到本表，不预建 W31。

最近关闭：[2026-W30 P3 企业 Agent 平台控制面塑形](2026-W30-p3-enterprise-agent-platform.md)（2026-10-09 收口；REQ-059 Architecture Gate 已完成，AG-1～AG-8 冻结决策继续以该文件为唯一详细事实源）。此前关闭：[2026-W25 P2 RAG 质量增强](2026-W25-p2-rag-quality-enhancement.md)。更早迭代（含 [2026-W23 P1 最终查漏补缺](2026-W23-p1-final-gap-closure.md)）只保留历史交接价值，不作为当前任务入口。

## 使用规则

- 只保留当前和近期 1 到 2 个迭代文件。
- 已结束迭代只保留摘要和链接，详细交付事实进入 work-log、PR、spec 或 plan。
- 迭代内任务必须指向 backlog、技术债、spec 或 plan，避免无编号事项。
- 迭代计划不是强制承诺；发现优先级变化时更新状态和原因。

## 模板

```md
# Iteration YYYY-WW: 主题

Status:
Dates:
Goal:

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|

## Out of Scope

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
```
