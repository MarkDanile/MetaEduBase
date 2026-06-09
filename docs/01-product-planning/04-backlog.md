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
| REQ-005 | REQ | 🟢 Done | P1 | P1 | 结构化抽取嵌套结构稳定性验收 | 已建 spec/plan；为 `extract_template_prompts.build_fields_desc` / `try_parse` / `_merge_template_structured_data` 补 11 条 object / array / table 嵌套回归用例；行为不变声明：0 业务代码改动（仅补测试与文档）。 |  |
| REQ-006 | REQ | 🟡 Doing | P1 | P1 | P1 知识资产处理链路最终演示验收 | 已建 [Spec](../02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md) 骨架（[PR #115](https://github.com/MarkDanile/MetaEduBase/pull/115) 已合并）；Stage 1.0 收口：`tests/e2e/test_p1_demo.py` 3 步 e2e 脚本（上传 / 解析 / `processing` 中间态 / 幂等性）跑通 + UI 演示手册骨架；Stage 1.0 探查发现并入账 TD-036（`metaedu_test` schema drift）+ TD-037（e2e 沙箱 Celery broker 缺）；Stage 1.5 待实施（接入 `extract_template` / KG / RAG / sources AC-3 ~ AC-6）；Stage 2 待文档回填翻 `🟢 Done`。 |  |
| REQ-007 | REQ | 🟢 Done | P1 | P1 | REQ-003 复盘缺口的 RAG 质量链路收口 | 补 3 通道 fake rows 行为级测试，修正 P1 / 迭代状态矛盾和过度验证声明，清理 e2e 测试漂移 | 已建 [Plan](../02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md)；5 AC 全部收口（[PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75)）。TD-031 ruff 预存问题入账并修复。 |
| REQ-008 | REQ | 🟢 Done | P1 | P1 | 收口 REQ-004 验收证据与质量门禁缺口 | 已建 [Spec](../02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md)；修 5 项 ruff 失败（E501/UP035/I001）+ 4 分支 `template.select layer=...` caplog 断言 + 2 条 L3 解析失败 / 空响应用例 + 1 条生产代码漂移保护；行为不变（折行 + import 来源等价）；[PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79) 已合并。 | [Requirement](05-requirements/REQ-008-req-004-template-selection-quality-follow-up.md) |
| REQ-009 | REQ | ⚪ Idea | P2 | P1 / P2 | 开源 AI 平台能力对标与可插拔融合预演 | 后续 Shaping 时评估 RAGFlow、Dify、Nuwax、Pi、LangGraph、LlamaIndex / Haystack 等项目，明确哪些能力接入、对标或只借鉴 | [Requirement](05-requirements/REQ-009-ai-platform-benchmark-and-adapter-strategy.md) |
| APP-001 | APP | ⚫ Candidate | P1 | P1 / P2 | 课程能力图谱智能体工具 | 优先进入 Shaping，明确课程样例、能力点 schema、图谱验收指标和首个最小闭环 |  |
| APP-002 | APP | ⚫ Candidate | P1 | P2 | 智能预习规划与导学智能体 | 等 APP-001 能力图谱最小闭环明确后，塑形学情诊断、预习任务和资源推送 |  |
| APP-003 | APP | ⚫ Candidate | P2 | P2 / P3 | 个性化学习资源推荐智能体 | 等资源类型、学生画像和能力图谱关联策略明确后塑形 |  |
| APP-004 | APP | ⚫ Candidate | P2 | P2 | 智能复习规划与巩固智能体 | 等学习记录、知识点掌握状态和微测验机制明确后塑形 |  |
| BUG-001 | BUG | ⚫ Candidate | P1 | P1 | 修正 document retry endpoint 的 Celery dispatch 语义 | `retry_file_tasks` 当前仍 `await parse_document.delay(...)`，需改为正确派发语义并补 `POST /files/{file_id}/retry` 行为测试 | `packages/server-python/app/contexts/document/interfaces/api/tasks.py:83` |
| BUG-002 | BUG | 🟢 Done | P1 | P1 | 修复登录后主面板外层容器巨大外边距、内容区过小 | TD-008 引入的 `ui-page-shell` 在 LayoutView 包裹 `<RouterView>`，用 `max-width: 1120px; margin: 0 auto` 强制限宽，与各 View 自带的 `max-w-[1000/1600px] mx-auto` 嵌套冲突：在 1920px 屏上左右空白巨大（margin auto 居中后 1120px 容器两侧各 ~400px），而 DatabaseView/ResourceLibraryView/FileDetailView 的 1600px 容器被外层直接卡到 1120px。修复：移除 `ui-page-shell` 的 `max-width: 1120px; margin: 0 auto`（保留 `width: 100%; padding; background`），让各 View 自决 max-width，容器仍具 token 化背景与 padding。验证：`pnpm typecheck` 退出 0；`pnpm lint` 退出 0；`pnpm build` 退出 0；产物 CSS 确认 `ui-page-shell{width:100%;padding:var(--spacing-page);background:var(--color-bg-base)}`。 | [Work Log](../03-engineering-governance/work-log.md) |
| DOC-041 | DOC | 🟢 Done | P2 | P1 | 清理 document router 与 task_router 重复路由 | [PR #99](https://github.com/MarkDanile/MetaEduBase/pull/99) 已合并：删 task_router.py 73 行 + 统一 tasks.py label 来源（`TASK_TYPE_LABELS` from `domain.entities`）+ main.py 删 3 行 import + include_router。启动仅 1 份 endpoint。 |  |
| DOC-042 | DOC | ⚫ Candidate | P2 | P3 | 脚本化 TD-032 行数基线扫描 | 将 TD-032 手工 `rg --files ... | xargs wc -l` 扫描固化为稳健命令或脚本，排除 `.venv` / `uploads` / `node_modules` 并支持空格路径 | [Baseline](../03-engineering-governance/02-baselines/td-032-source-file-sizes.md) |
| DOC-044 | DOC | 🟢 Done | P3 | P1 | 修正工程治理目录编号重复 | 保留基线目录编号 02；矩阵目录改为编号 03；复盘目录改为编号 04，并同步全仓引用。 | [Engineering Governance](../03-engineering-governance/README.md) |
| DOC-045 | DOC | ⚫ Candidate | P2 | P3 | 修正 TD-033 CSS 拆分交付声明与追踪证据 | 将“零 CSS 字节变化 / build output identical”等过强声明修正为“无计划行为变化 + 构建和人工复核证据”；补 `work-log.md` 的 PR #103 / merge commit；记录 TD-033 未建 spec / plan 的处置方式或例外原因。 | [PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) / [TD-033](../03-engineering-governance/technical-debt.md#td-033) |
| DOC-046 | DOC | 🟢 Done | P3 | P1 | 修正 P1 轨道 B 检索 / 抽取质量展示 | 已给轨道 B 增加可视化状态列，并保留“实现事实 / 验证结论”证据分栏；不改变真实验收结论。 | [P1 Milestone](02-milestones/01-validation-phase.md#轨道-b检索--抽取质量) |
| DOC-047 | DOC | 🟢 Done | P2 | P3 | 建立评审评分总账与落盘规则 | 新增 `review-score-log.md`，回填 TD-033 评分 81，并要求复杂评审把总分、follow-up、流程扣分点和规则改进结论落盘。 | [Review Score Log](../03-engineering-governance/04-retrospectives/review-score-log.md) |
| DOC-048 | DOC | 🟢 Done | P2 | P3 | 增加评审高分质量校准规则 | 当最近 5 条评审平均分 >92 时，阶段复盘必须抽查评分是否偏宽；若发现问题，在评分总账标记并登记 follow-up。 | [Review Scorecard](../03-engineering-governance/01-rules/review-scorecard.md#高分质量校准) |
| DOC-049 | DOC | 🟢 Done | P2 | P1 | 收口 REQ-005 完成态占位与验证声明漂移 | 修正 REQ-005 spec 中 AC-8 浅拷贝口径（与 `dict(template_data)` 实现和测试 `is` 断言对齐：外层新 dict、内嵌 list/dict 同引用）、AC-10 失败条件（`未回填` → 状态未翻等具体描述）、"不在范围"段 `TD-???` → TD-034 稳定编号；修正 plan 中 `Task 1 | TBD` / `Task 2 | TBD` 提交占位（补 `4773741` 和本 PR 链接）、`8+ 条` 任务标题 / 文件结构 / placeholder scan 互证为 11 条、交付记录的 12 新增计数错误、AC-8 self-review 描述（外层新 dict + 内嵌同引用），全部对齐到 11 条用例真实测试输出；评估 `check_delivery_placeholders` 补强：`TBD` / `TD-???` / `未回填` 模式脚本化已加入 `quality-gates.md#脚本门禁候选清单`（推迟实施，因 REQ-003 / REQ-008 plan 仍有 5 处 TBD，会一次性拦截失败，列入后续 `DOC-xxx` 单独收口）。 | [PR #113](https://github.com/MarkDanile/MetaEduBase/pull/113) / [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md) |
| DOC-050 | DOC | 🟢 Done | P2 | P3 | 优化 current-work 最近完成窗口与评分总账排序 | `review-score-log.md` 明确最新评审置顶；`current-work.md` 最近完成从 5 行调整为 20 行，超过后批量归档到 12-15 行；同步 `workbench.md`、`quality-gates.md`、文档门禁脚本和测试。 | [Workbench](../03-engineering-governance/01-rules/workbench.md#保留策略) / [Review Score Log](../03-engineering-governance/04-retrospectives/review-score-log.md) |
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
