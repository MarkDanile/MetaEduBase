# Iterations — 迭代计划

本目录记录当前和近期迭代。它服务于排期和阶段交接，不替代 `docs/03-engineering-governance/current-work.md` 的当前执行状态。

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
