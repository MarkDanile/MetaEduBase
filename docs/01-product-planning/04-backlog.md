# Product Backlog — 需求池索引

本文件记录产品、工程和运营层面的候选任务索引。它不是 PRD，不承载完整设计；详细内容按需拆到 `docs/01-product-planning/05-requirements/*`、`docs/03-engineering-governance/technical-debt.md`、`docs/02-delivery-plans/01-specs/*` 或 `docs/02-delivery-plans/02-plans/*`。

## 使用规则

- 本表保留索引、优先级、状态、来源和下一步。
- 条目进入开发前，应具备清晰验收标准；复杂需求先进入 `Shaping`。
- 技术债详情不重复写在这里，只链接 `docs/03-engineering-governance/technical-debt.md`。
- 已进入当前执行窗口的任务，同步到 `docs/03-engineering-governance/current-work.md`。
- 已长期关闭的任务可移入对应需求文件、work-log 或外部系统，不让本表无限增长。

## Backlog

| ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
|----|------|------|--------|--------|------|--------|----------|
| REQ-001 | REQ | Idea | P2 | M1 | 知识资产处理链路的产品化验收视图 | 澄清目标用户、核心场景和验收指标 |  |
| REQ-002 | REQ | Idea | P2 | M2 | 模板化结构抽取能力的配置与复用体验 | 从历史 superpower 计划中提炼需求边界 |  |
| DOC-019 | DOC | Done | P1 | M4 | 建立产品规划层和复盘入口 | 已同步规则索引，验证通过后归档到工作日志 |  |
| DOC-024 | DOC | Idea | P2 | M6 | 工程协作规则模板化：将成熟的跨 AI IDE 规则、docs 分层、质量门禁和任务闭环抽象成可复用模板包 | 等本项目规则经过更多实践验证后，进入 Shaping，明确模板仓库边界、项目适配层和版本化策略 |  |

## 状态迁移

```text
Idea -> Candidate -> Shaping -> Ready -> Planned -> Doing -> Done
                         \                         \
                          -> Dropped                -> Blocked
```

`Blocked` 只用于有明确外部依赖或决策阻塞的条目；普通未排期仍保持 `Candidate` 或 `Ready`。
