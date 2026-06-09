# Retrospectives — 复盘与根因追踪

本目录记录跨任务的复盘信号和根因分析。目标是把失败、Review 发现、交接漏项和质量门禁问题转成可追踪任务，避免问题只停留在聊天记录。

## 使用规则

- 小问题直接登记到 `TD` / `BUG` / `DOC` / `REQ`，不必新建复盘文件。
- 同类问题重复出现、影响多个工具或暴露系统性流程缺口时，才新建复盘文件。
- 复盘必须有后续任务编号；没有编号的“建议”不算闭环。
- 复盘文件只记录事实、根因和纠正动作，不写长篇过程叙事。
- 评审评分统一记录在 `review-score-log.md`；阶段复盘统计平均分、一次关闭率、返工率、流程违规率时，以该总账为事实源。
- 若最近 5 条评审平均分 > 92，必须按 `review-scorecard.md#高分质量校准` 抽查评分是否偏宽。

## 模板

```md
# YYYY-MM-DD: 复盘主题

Trigger:
Scope:

## Signals

| 信号 | 证据 | 影响 |
|------|------|------|

## Root Causes

| 根因 | 类型 | 说明 |
|------|------|------|

## Corrective Actions

| ID | 类型 | 状态 | 动作 | 验证 |
|----|------|------|------|------|

## Follow-up Check

| 日期 | 检查项 | 结果 |
|------|--------|------|
```

## 任务归口

| 问题类型 | 后续编号 | 事实源 |
|----------|----------|--------|
| 产品能力缺口 | `REQ-xxx` | `docs/01-product-planning/04-backlog.md` 或 `docs/01-product-planning/05-requirements/*` |
| 缺陷或回归 | `BUG-xxx` | `docs/01-product-planning/04-backlog.md`，必要时进入 spec / plan |
| 技术债 | `TD-xxx` | `docs/03-engineering-governance/technical-debt.md` |
| 规则、文档或流程缺口 | `DOC-xxx` | `docs/03-engineering-governance/work-log.md`、对应规则文件或 plan |
| 发布、环境或运营事项 | `OPS-xxx` | `docs/01-product-planning/04-backlog.md` 或外部系统 |
