# Product Backlog — 需求池索引

本文件记录产品、工程和运营层面的候选任务索引。它不是 PRD，不承载完整设计；详细内容按需拆到 `docs/01-product-planning/05-requirements/*`、`docs/03-engineering-governance/technical-debt.md`、`docs/02-delivery-plans/01-specs/*` 或 `docs/02-delivery-plans/02-plans/*`。

## 使用规则

- 本表保留索引、优先级、状态、来源和下一步。
- 条目进入开发前，应具备清晰验收标准；复杂需求先进入 `Shaping`。
- 技术债详情不重复写在这里，只链接 `docs/03-engineering-governance/technical-debt.md`。
- 已进入当前执行窗口的任务，同步到 `docs/03-engineering-governance/current-work.md`。
- 已长期关闭的任务可移入对应需求文件、work-log 或外部系统，不让本表无限增长。

## 状态图例

| 状态 | 含义 |
|------|------|
| ⚪ Idea | 只有想法，未确认价值和边界 |
| ⚫ Candidate | 值得保留，尚未排期 |
| 🟣 Shaping | 正在澄清目标、范围、验收标准 |
| 🔵 Ready | 可进入 spec / plan 或近期迭代 |
| 🟡 Planned | 已放入迭代 |
| 🟡 Doing | 已进入当前执行窗口 |
| 🔴 Blocked | 有明确外部依赖、环境阻塞或决策阻塞 |
| 🟢 Done | 已交付或关闭 |
| ⚪ Dropped | 明确不做，保留原因 |
| ⚪ Future | 远期候选，只保留方向 |

## Backlog

| ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
|----|------|------|--------|--------|------|--------|----------|
| REQ-001 | REQ | ⚪ Idea | P2 | P1 | 知识资产处理链路的产品化验收视图 | 澄清目标用户、核心场景和验收指标 |  |
| REQ-002 | REQ | ⚪ Idea | P2 | P1 / P2 | 模板化结构抽取能力的配置与复用体验 | 从历史 superpower 计划中提炼需求边界 |  |
| REQ-003 | REQ | 🟢 Done | P1 | P1 | P1 RAG 质量链路验收与回归测试 | 为 NER、3 通道召回、频次融合和 sources 结构建立可复现验证 | 已建 spec/plan（[Spec](../02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md)）；2026-W23 迭代内完成 4 个回归测试文件、4 项轨道 B 验证翻结论。端到端 PG 集成由 REQ-006 接力；Protocol-vs-concrete drift 入账 TD-030。 |
| REQ-004 | REQ | 🟢 Done | P1 | P1 | 模板匹配可解释化收口 | 已建 spec/plan；抽 `select_template` 纯函数 + 9 条分支回归 + 统一 `template.select` 日志前缀；复核发现的验收证据与质量门禁缺口由 REQ-008 承接 | [PR #77](https://github.com/MarkDanile/MetaEduBase/pull/77) |
| REQ-005 | REQ | ⚫ Candidate | P1 | P1 | 结构化抽取嵌套结构稳定性验收 | 建立 object / array / table 抽取结果按模板结构落盘的样例回归 |  |
| REQ-006 | REQ | ⚫ Candidate | P1 | P1 | P1 知识资产处理链路最终演示验收 | 组织上传、解析、抽取、图谱、RAG 问答和来源展示的阶段一闭环验收 |  |
| REQ-007 | REQ | 🟢 Done | P1 | P1 | REQ-003 复盘缺口的 RAG 质量链路收口 | 补 3 通道 fake rows 行为级测试，修正 P1 / 迭代状态矛盾和过度验证声明，清理 e2e 测试漂移 | 已建 [Plan](../02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md)；5 AC 全部收口（[PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75)）。TD-031 ruff 预存问题入账并修复。 |
| REQ-008 | REQ | 🟢 Done | P1 | P1 | 收口 REQ-004 验收证据与质量门禁缺口 | 已建 [Spec](../02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md)；修 5 项 ruff 失败（E501/UP035/I001）+ 4 分支 `template.select layer=...` caplog 断言 + 2 条 L3 解析失败 / 空响应用例 + 1 条生产代码漂移保护；行为不变（折行 + import 来源等价）；[PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79) 已合并。 | [Requirement](05-requirements/REQ-008-req-004-template-selection-quality-follow-up.md) |
| REQ-009 | REQ | ⚪ Idea | P2 | P1 / P2 | 开源 AI 平台能力对标与可插拔融合预演 | 后续 Shaping 时评估 RAGFlow、Dify、Nuwax、Pi、LangGraph、LlamaIndex / Haystack 等项目，明确哪些能力接入、对标或只借鉴 | [Requirement](05-requirements/REQ-009-ai-platform-benchmark-and-adapter-strategy.md) |
| APP-001 | APP | ⚫ Candidate | P1 | P1 / P2 | 课程能力图谱智能体工具 | 优先进入 Shaping，明确课程样例、能力点 schema、图谱验收指标和首个最小闭环 |  |
| APP-002 | APP | ⚫ Candidate | P1 | P2 | 智能预习规划与导学智能体 | 等 APP-001 能力图谱最小闭环明确后，塑形学情诊断、预习任务和资源推送 |  |
| APP-003 | APP | ⚫ Candidate | P2 | P2 / P3 | 个性化学习资源推荐智能体 | 等资源类型、学生画像和能力图谱关联策略明确后塑形 |  |
| APP-004 | APP | ⚫ Candidate | P2 | P2 | 智能复习规划与巩固智能体 | 等学习记录、知识点掌握状态和微测验机制明确后塑形 |  |
| DOC-041 | DOC | 🟢 Done | P2 | P1 | 清理 document router 与 task_router 重复路由 | [PR #99](https://github.com/MarkDanile/MetaEduBase/pull/99) 已合并：删 task_router.py 73 行 + 统一 tasks.py label 来源（`TASK_TYPE_LABELS` from `domain.entities`）+ main.py 删 3 行 import + include_router。启动仅 1 份 endpoint。 |  |
| DOC-019 | DOC | 🟢 Done | P1 | P1 | 建立产品规划层和复盘入口 | 已同步规则索引，验证通过后归档到工作日志 |  |
| DOC-024 | DOC | ⚪ Idea | P2 | P3 | 工程协作规则模板化：将成熟的跨 AI IDE 规则、docs 分层、质量门禁和任务闭环抽象成可复用模板包 | 等本项目规则经过更多实践验证后，进入 Shaping，明确模板仓库边界、项目适配层和版本化策略 |  |
| DOC-034 | DOC | 🟢 Done | P2 | P1 | 修正 REQ-008 spec AC-5 与实际测试行为不一致 | AC-5 期望由 `layer == "none"` 修为 `layer == "L3"` + `template is None` + `reason` 含 below threshold；「选择器契约（不变）」段同步改写为与实现和 `test_l3_ai_confidence_unparseable_falls_back_to_zero` 一致；不改代码。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md) / [PR #83](https://github.com/MarkDanile/MetaEduBase/pull/83) |
| DOC-036 | DOC | 🟢 Done | P2 | P1 | 收口 DOC-034 遗留的 REQ-008 spec 前文旧口径 | 已修 `2026-W23-req-008-req-004-quality-follow-up.md` 第 21 行，把 `教案\nabc` 的期望统一为 `layer == "L3"` + `template is None` + below threshold；不改代码。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md) |
| DOC-037 | DOC | 🟢 Done | P2 | P3 | 规则入口瘦身与脚本门禁候选清单整理 | 已压缩 `AGENTS.md` / `CLAUDE.md` 为导航入口；确认 `.claude/rules/*` 与 `.trae/rules/*` 仍为跳转入口；新增脚本门禁候选清单；不改业务代码。 | [Quality Gates](../03-engineering-governance/01-rules/quality-gates.md) |
| DOC-038 | DOC | 🟢 Done | P2 | P3 | 恢复基础工程原则为单一事实源 | 新增 `engineering-principles.md`，入口和 IDE 兼容规则只做链接，避免 DOC-037 瘦身后丢失“先想后写 / 极简主义 / 手术式改动 / 目标驱动”。 | [Engineering Principles](../03-engineering-governance/01-rules/engineering-principles.md) |
| DOC-039 | DOC | 🟢 Done | P2 | P3 | 增强工程文档脚本门禁 | 将稳定编号、Done 入账、入口同步和脚本候选清单反查纳入 `scripts/check-engineering-docs`，并补工程脚本回归测试。 | [Quality Gates](../03-engineering-governance/01-rules/quality-gates.md) |

## 状态迁移

```text
⚪ Idea -> ⚫ Candidate -> 🟣 Shaping -> 🔵 Ready -> 🟡 Planned -> 🟡 Doing -> 🟢 Done
                         \                         \
                          -> ⚪ Dropped             -> 🔴 Blocked
```

`Blocked` 只用于有明确外部依赖或决策阻塞的条目；普通未排期仍保持 `Candidate` 或 `Ready`。
