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
| REQ-001 | REQ | Idea | P2 | P1 | 知识资产处理链路的产品化验收视图 | 澄清目标用户、核心场景和验收指标 |  |
| REQ-002 | REQ | Idea | P2 | P1 / P2 | 模板化结构抽取能力的配置与复用体验 | 从历史 superpower 计划中提炼需求边界 |  |
| REQ-003 | REQ | Done | P1 | P1 | P1 RAG 质量链路验收与回归测试 | 为 NER、3 通道召回、频次融合和 sources 结构建立可复现验证 | 已建 spec/plan（[Spec](../02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md)）；2026-W23 迭代内完成 4 个回归测试文件、4 项轨道 B 验证翻结论。端到端 PG 集成由 REQ-006 接力；Protocol-vs-concrete drift 入账 TD-030。 |  |
| REQ-004 | REQ | Done | P1 | P1 | 模板匹配可解释化收口 | 已建 spec/plan；抽 `select_template` 纯函数 + 9 条分支回归 + 统一 `template.select` 日志前缀；轨道 B 翻结论 | [PR #77](https://github.com/MarkDanile/MetaEduBase/pull/77) |
| REQ-005 | REQ | Candidate | P1 | P1 | 结构化抽取嵌套结构稳定性验收 | 建立 object / array / table 抽取结果按模板结构落盘的样例回归 |  |
| REQ-006 | REQ | Candidate | P1 | P1 | P1 知识资产处理链路最终演示验收 | 组织上传、解析、抽取、图谱、RAG 问答和来源展示的阶段一闭环验收 |  |
| REQ-007 | REQ | Done | P1 | P1 | REQ-003 复盘缺口的 RAG 质量链路收口 | 补 3 通道 fake rows 行为级测试，修正 P1 / 迭代状态矛盾和过度验证声明，清理 e2e 测试漂移 | 已建 [Plan](../02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md)；5 AC 全部收口（[PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75)）。TD-031 ruff 预存问题入账并修复。 |
| APP-001 | APP | Candidate | P1 | P1 / P2 | 课程能力图谱智能体工具 | 优先进入 Shaping，明确课程样例、能力点 schema、图谱验收指标和首个最小闭环 |  |
| APP-002 | APP | Candidate | P1 | P2 | 智能预习规划与导学智能体 | 等 APP-001 能力图谱最小闭环明确后，塑形学情诊断、预习任务和资源推送 |  |
| APP-003 | APP | Candidate | P2 | P2 / P3 | 个性化学习资源推荐智能体 | 等资源类型、学生画像和能力图谱关联策略明确后塑形 |  |
| APP-004 | APP | Candidate | P2 | P2 | 智能复习规划与巩固智能体 | 等学习记录、知识点掌握状态和微测验机制明确后塑形 |  |
| DOC-019 | DOC | Done | P1 | P1 | 建立产品规划层和复盘入口 | 已同步规则索引，验证通过后归档到工作日志 |  |
| DOC-024 | DOC | Idea | P2 | P3 | 工程协作规则模板化：将成熟的跨 AI IDE 规则、docs 分层、质量门禁和任务闭环抽象成可复用模板包 | 等本项目规则经过更多实践验证后，进入 Shaping，明确模板仓库边界、项目适配层和版本化策略 |  |

## 状态迁移

```text
Idea -> Candidate -> Shaping -> Ready -> Planned -> Doing -> Done
                         \                         \
                          -> Dropped                -> Blocked
```

`Blocked` 只用于有明确外部依赖或决策阻塞的条目；普通未排期仍保持 `Candidate` 或 `Ready`。
