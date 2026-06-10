# 工程工作日志索引

本文件记录已完成任务的一行式历史索引，避免 `current-work.md` 无限扩张。详细事实仍以对应技术债总账、spec、plan、PR 或架构文档为准。

## 记录规则

- 每个已完成且需要长期追踪的任务保留一行。
- `current-work.md` 中移出的完成任务，应在这里有索引。
- 本文件只记录检索信息，不承载详细复盘、设计或验证输出。
- 任务详情优先链接到对应事实源：`technical-debt.md`、`docs/02-delivery-plans/01-specs/*`、`docs/02-delivery-plans/02-plans/*` 或 PR。
- PR 是默认交付事实源；本表的 PR 和 merge commit 都是可选追踪字段，只有已有历史、审计需要或任务总账明确要求时记录，缺省可留空并通过 GitHub PR 查询。
- `current-work.md` 的“最近完成”只保留短摘要；本文件保留长期检索索引，避免入口文档无限扩张。

## 索引

| 日期 | 任务 | 类型 | PR 可选 | Merge Commit 可选 | 归档位置 |
|------|------|------|----|-------------------|----------|
| 2026-06-10 | REQ-011 AI 应用广场与应用注册中心规划 | 产品规划 / AI 应用组合 / 应用广场 / 需求塑形 |  |  | `docs/01-product-planning/05-requirements/REQ-011-ai-application-marketplace-and-registry.md` / `docs/01-product-planning/06-ai-applications/README.md` / `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | TD-040 `FileTabsPanel.spec.ts` Vue 单元测试覆盖 AC-11 / AC-12 + 引入 vitest 首次前端单测基建 | 技术债 / 前端 / 测试 / AC 锁 / 基建引入 | [#167](https://github.com/MarkDanile/MetaEduBase/pull/167) | `c1cc0c9` (squash merge) | `docs/03-engineering-governance/technical-debt.md#td-040` / `packages/web/src/views/resource/FileTabsPanel.spec.ts` / `packages/web/vitest.config.ts` / `packages/web/package.json` / `pnpm-lock.yaml` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | TD-042 模板复用后端集成测试在 PG 实例下验证 | 技术债 / 后端 / 测试 / 集成 / 迁移 / 缺陷修复（007 inline FK + asyncpg 反射 PK 不返回） |  |  | `docs/03-engineering-governance/technical-debt.md#td-042` / `packages/server-python/alembic/versions/007_template_versions.py` / `packages/server-python/tests/contexts/template/test_template_reuse.py` / `packages/server-python/tests/contexts/template/test_template.py` |
| 2026-06-10 | TD-041 FieldCard 递归渲染嵌套字段 + object children / array items 嵌套拖拽 | 技术债 / 前端 / 架构 / 递归组件 / 拖拽 / Bug 修复（removeColumn + copySubtree） | [#161](https://github.com/MarkDanile/MetaEduBase/pull/161) | `9d41b1e` (squash merge) | `docs/03-engineering-governance/technical-debt.md#td-041` / `docs/02-delivery-plans/01-specs/2026-06-10-td-041-field-card-recursive-rendering.md` / `docs/02-delivery-plans/02-plans/2026-06-10-td-041-field-card-recursive-rendering-plan.md` / `packages/web/src/views/admin/FieldList.vue` / `packages/web/src/views/admin/FieldCard.vue` / `packages/web/src/views/admin/FieldItem.vue` / `packages/web/src/views/admin/TemplateEditorView.vue` |
| 2026-06-10 | DOC-058 强化工作台规则渐进式披露入口 | 文档 / 工程治理 / 工作台 / 渐进式披露 / 跨 AI 交接 |  |  | `AGENTS.md` / `CLAUDE.md` / `.claude/rules/currentWork.md` / `.trae/rules/currentWork.md` / `docs/03-engineering-governance/current-work.md` / `docs/03-engineering-governance/01-rules/workbench.md` / `docs/03-engineering-governance/workflow.md` / `docs/03-engineering-governance/task-modes.md` |
| 2026-06-10 | DOC-057 建立并行开发模式与集成收口规则 | 文档 / 工程治理 / 多 agent 协作 / Git 分支 / 工作台边界 |  |  | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/task-modes.md#并行开发模式` / `docs/03-engineering-governance/workflow.md#并行开发模式` / `docs/03-engineering-governance/01-rules/workbench.md#并行批次边界` / `docs/03-engineering-governance/01-rules/git-workflow.md#并行分支规则` |
| 2026-06-10 | DOC-056 收口 `check_req_status_consistency` 父 / 子任务混聚 bug | 工程脚本 / 质量门禁 / 跨事实源状态一致性 | [PR TBD] |  | `docs/03-engineering-governance/technical-debt.md#doc-056` / `scripts/engineering/checks/_common.py` / `tests/engineering/test_check_engineering_docs.py` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | REQ-002-3 模板抽取结果溯源字段扩展 | 后端 contract / 前端溯源卡 / structured_data 新增 `id` / `version` / `layer` 等 6 键 | [#153](https://github.com/MarkDanile/MetaEduBase/pull/153) | `98b986c` (squash merge) | `docs/01-product-planning/04-backlog.md` / `docs/01-product-planning/02-milestones/01-validation-phase.md` / `docs/01-product-planning/02-milestones/02-growth-phase.md` / `docs/02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md` / `docs/02-delivery-plans/02-plans/2026-06-10-req-002-3-template-source-tracking-plan.md` / `docs/03-engineering-governance/technical-debt.md#td-039` / `docs/03-engineering-governance/technical-debt.md#td-040` / `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py` / `packages/server-python/app/contexts/document/application/tasks/extract_template.py` / `packages/server-python/tests/contexts/document/test_structured_data_contract.py` / `packages/server-python/tests/contexts/document/test_extract_template_prompts.py` / `packages/server-python/tests/e2e/test_p1_demo.py` / `packages/web/src/views/resource/FileTabsPanel.vue` |
| 2026-06-10 | REQ-010 P1 真实 RAG 证据治理与 AI Chat 溯源体验 | 需求 / RAG / AI Chat / Evidence / UX / P1 目标校准 |  |  | `docs/01-product-planning/05-requirements/REQ-010-p1-rag-evidence-governance.md` / `docs/01-product-planning/04-backlog.md` / `docs/01-product-planning/02-milestones/01-validation-phase.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | DOC-055 收口 DOC-042 / TD-034 PR 范围混入与事实源漂移 | 文档 / 工程治理 / PR 范围边界 / 事实源漂移 / baseline refresh | [#142](https://github.com/MarkDanile/MetaEduBase/pull/142) (closed as superseded) |  | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md#doc-055` / `docs/03-engineering-governance/technical-debt.md#td-034` / `docs/03-engineering-governance/technical-debt.md#doc-051` / `docs/03-engineering-governance/technical-debt.md#doc-042` / `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` / `docs/03-engineering-governance/02-baselines/source-sizes-baseline.json` / `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | DOC-042 脚本化 TD-032 行数基线扫描 | 文档 / 工程治理 / 工程脚本 / 质量门禁 | [#143](https://github.com/MarkDanile/MetaEduBase/pull/143) |  | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md#doc-042` / `docs/03-engineering-governance/current-work.md` / `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` / `docs/03-engineering-governance/02-baselines/source-sizes-baseline.json` / `scripts/engineering/scan_source_sizes.py` / `scripts/engineering/checks/source_sizes.py` / `scripts/scan-source-sizes` / `tests/engineering/test_check_engineering_docs.py` |
| 2026-06-10 | TD-034 `build_fields_desc` 在 `array + items=[]` 时保留"成员为object"提示（路线 A） | 技术债 / 后端 / LLM 抽取 / 可维护性 | [#143](https://github.com/MarkDanile/MetaEduBase/pull/143) | `3077047` (squash merge，原 PR #142 commit `1e9a012` 由 DOC-055 关闭为 superseded) | `docs/03-engineering-governance/technical-debt.md#td-034` / `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py` / `packages/server-python/tests/contexts/document/test_extract_template_prompts.py` |
| 2026-06-10 | REQ-006 Stage 2 — 🟢 Done（6 步 e2e + 文档回填完毕） | 需求 / 后端 / e2e / Celery / LLM / 文档回填 | [#132](https://github.com/MarkDanile/MetaEduBase/pull/132) | `a39f7a3` | `docs/01-product-planning/04-backlog.md` / `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md` / `docs/03-engineering-governance/current-work.md` / `packages/server-python/tests/e2e/test_p1_demo.py` |
| 2026-06-10 | REQ-006 Stage 1.5 — e2e AC-3~AC-6 补全 | 需求 / 后端 / e2e / Celery / LLM | [#132](https://github.com/MarkDanile/MetaEduBase/pull/132) | `a39f7a3` | `docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-006-p1-final-demo-plan.md` / `docs/03-engineering-governance/current-work.md` / `packages/server-python/tests/e2e/test_p1_demo.py` |
| 2026-06-10 | TD-037 收口 e2e 沙箱 Redis broker（路线 B） | 技术债 / 后端 / e2e / 基础设施 / Celery | [#130](https://github.com/MarkDanile/MetaEduBase/pull/130) | `9419c4e` | `docs/03-engineering-governance/technical-debt.md#td-037` / `docs/03-engineering-governance/current-work.md` / `packages/server-python/tests/e2e/conftest.py` / `packages/server-python/tests/e2e/test_p1_demo.py` |
| 2026-06-09 | DOC-053 补齐高频流程启动语入口 | 文档 / 工程治理 / 任务模式 / AI 协作 |  |  | `docs/03-engineering-governance/task-modes.md#常见启动语` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-09 | DOC-052 清理 `_common.py` `KNOWN_ISSUES` 残留的 TD-023 历史白名单 | 文档 / 工程治理 / 工程脚本 / 跨 AI 交接 / 白名单收口 | [#128](https://github.com/MarkDanile/MetaEduBase/pull/128) | `3f39ec0` | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md#doc-052` / `docs/03-engineering-governance/current-work.md` / `scripts/engineering/checks/_common.py` |
| 2026-06-09 | DOC-054 收口 review-score-log PR 字段与倒排顺序一致性 | 文档 / 工程治理 / 复盘 / 评分总账 / 跨事实源 | [#126](https://github.com/MarkDanile/MetaEduBase/pull/126) | `2d6efd3` | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/04-retrospectives/review-score-log.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-09 | DOC-051 一次性收口 W23 P1 历史 spec/plan 占位 | 文档 / 工程治理 / 计划回填 / 跨事实源 | [#124](https://github.com/MarkDanile/MetaEduBase/pull/124) | `d7a2ca7` | `docs/01-product-planning/04-backlog.md` / `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md` / `docs/03-engineering-governance/01-rules/quality-gates.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-09 | TD-036 / TD-038 修复全新测试库 `alembic upgrade head` 卡在 006 的根因 | 技术债 / 后端 / 迁移 / 测试基础设施 / 质量门禁 | [#122](https://github.com/MarkDanile/MetaEduBase/pull/122) | `2780ff1` | `docs/01-product-planning/04-backlog.md` (无对应行,纯技术债) / `docs/03-engineering-governance/current-work.md` / `docs/03-engineering-governance/technical-debt.md#td-036` / `docs/03-engineering-governance/technical-debt.md#td-038` / `packages/server-python/alembic/versions/006_add_templates.py` / `packages/server-python/app/shared/infrastructure/test_db_setup.py` / `packages/server-python/tests/e2e/test_p1_demo.py` |
| 2026-06-09 | BUG-001 修正 document retry endpoint 的 Celery dispatch 语义 | Bug 修复 / 后端 / Celery 派发 / pipeline_version / try-except 兜底 | [#120](https://github.com/MarkDanile/MetaEduBase/pull/120) | `c24f3e9` | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/current-work.md` / `packages/server-python/app/contexts/document/interfaces/api/tasks.py` / `packages/server-python/tests/contexts/document/test_tasks_router.py` |
| 2026-06-09 | DOC-050 优化 current-work 最近完成窗口与评分总账排序 | 文档 / 工程治理 / 工作台 / 评分总账 / 门禁脚本 |  |  | `docs/03-engineering-governance/current-work.md` / `docs/03-engineering-governance/01-rules/workbench.md#保留策略` / `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁` / `docs/03-engineering-governance/04-retrospectives/review-score-log.md` / `scripts/engineering/checks/current_work.py` |
| 2026-06-09 | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁 | 技术债 / 后端 / 测试 / ruff 修复 |  |  | `packages/server-python/tests/contexts/document/test_extract_template_prompts.py` / `docs/03-engineering-governance/technical-debt.md#td-035` |
| 2026-06-09 | REQ-006 Stage 1.0 端到端脚本 + UI 演示手册骨架 | 需求 / 后端 / e2e / Celery 沙箱适配 / 文档 |  |  | `packages/server-python/tests/e2e/test_p1_demo.py` / `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md` / `docs/03-engineering-governance/technical-debt.md#td-036` / `docs/03-engineering-governance/technical-debt.md#td-037` |
| 2026-06-09 | DOC-049 收口结构化抽取完成态占位与验证声明漂移 | 文档 / 工程治理 / spec-plan 占位 / 浅拷贝口径 / 计数 / 候选门禁登记 |  |  | `docs/01-product-planning/04-backlog.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md` / `docs/03-engineering-governance/01-rules/quality-gates.md#脚本门禁候选清单` |
| 2026-06-09 | REQ-005 结构化抽取嵌套结构稳定性验收 | 需求 / 测试 / P1 轨道 B 翻结论 |  |  | `docs/01-product-planning/02-milestones/01-validation-phase.md#轨道-b检索--抽取质量` / `docs/01-product-planning/04-backlog.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md` / `packages/server-python/tests/contexts/document/test_extract_template_prompts.py` |
| 2026-06-09 | BUG-002 修复登录后主面板外边距巨大、内容显示容器过小 | Bug 修复 / 前端 / CSS / 容器布局 | [#107](https://github.com/MarkDanile/MetaEduBase/pull/107) | `76fe2d2` | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/current-work.md` / `packages/web/src/assets/css/components.css` |
| 2026-06-10 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 文档 / 工程治理 / 事实源修正 / follow-up | [#137](https://github.com/MarkDanile/MetaEduBase/pull/137) | `b815942` | `docs/03-engineering-governance/04-retrospectives/review-score-log.md#td-033` / `docs/03-engineering-governance/technical-debt.md#doc-045` / `docs/03-engineering-governance/technical-debt.md#td-033` / `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/current-work.md` |
| 2026-06-10 | TD-030 RecallChannel Protocol vs concrete signature drift 收口（路线 A） | 技术债 / 后端 / 测试 / Protocol 契约治理 | [#139](https://github.com/MarkDanile/MetaEduBase/pull/139) | `a934981` | `docs/03-engineering-governance/technical-debt.md#td-030` / `docs/03-engineering-governance/current-work.md` / `packages/server-python/app/shared/domain/recall_channel.py` / `packages/server-python/app/contexts/knowledge/application/recall_service.py` / `packages/server-python/tests/contexts/ai/test_recall_channels_contract.py` |
| 2026-06-09 | DOC-048 增加评审高分质量校准规则 | 文档 / 工程治理 / 评审 / 复盘数据 |  |  | `docs/03-engineering-governance/01-rules/review-scorecard.md#高分质量校准` / `docs/03-engineering-governance/04-retrospectives/README.md` |
| 2026-06-09 | DOC-047 建立评审评分总账与落盘规则 | 文档 / 工程治理 / 评审 / 复盘数据 |  |  | `docs/03-engineering-governance/04-retrospectives/review-score-log.md` / `docs/03-engineering-governance/01-rules/review-scorecard.md` |
| 2026-06-09 | DOC-046 修正 P1 轨道 B 检索 / 抽取质量展示 | 文档 / 产品规划 / 里程碑展示 |  |  | `docs/01-product-planning/02-milestones/01-validation-phase.md#轨道-b检索--抽取质量` |
| 2026-06-09 | TD-033 拆分 `main.css` 设计系统级 CSS 模块 | 技术债 / 重构 / 前端 CSS / 设计系统 | [#103](https://github.com/MarkDanile/MetaEduBase/pull/103) | `25ca165` | `docs/03-engineering-governance/technical-debt.md#td-033` / `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` |
| 2026-06-09 | DOC-044 修正工程治理目录编号重复 | 文档 / 工程治理 / 目录结构 |  |  | `docs/03-engineering-governance/README.md` / `docs/03-engineering-governance/02-baselines/` / `docs/03-engineering-governance/03-matrices/` / `docs/03-engineering-governance/04-retrospectives/` |
| 2026-06-09 | DOC-043 登记 TD-032 评审 follow-up 与规则改进 | 文档 / 工程治理 / 评审 / follow-up |  |  | `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/01-rules/review-scorecard.md` / `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` |
| 2026-06-08 | DOC-040 登记超大源码文件治理技术债 | 文档 / 工程治理 / 技术债 / 代码可维护性 |  |  | `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则` / `docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界` |
| 2026-06-08 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 1：基线 + 原则 + 任务卡） | 技术债 / 工程治理 / 重构 | [#92](https://github.com/MarkDanile/MetaEduBase/pull/92) | `3de4de5` | `docs/02-delivery-plans/01-specs/2026-06-08-td-032-large-source-files.md` / `docs/02-delivery-plans/02-plans/2026-06-08-td-032-large-source-files-plan.md` / `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` |
| 2026-06-08 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 2：拆分 `check_engineering_docs.py` 1003 → 72） | 技术债 / 重构 / 工程脚本 | [#93](https://github.com/MarkDanile/MetaEduBase/pull/93) | `7e468fb` | `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-2-check-engineering-docs-split.md` / `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-2-check-engineering-docs-split-plan.md` |
| 2026-06-08 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 3：拆分 `document/tasks.py` 929 + `structured_data/tasks.py` 671 → 各自 Python 包） | 技术债 / 重构 / 后端 Celery | [#94](https://github.com/MarkDanile/MetaEduBase/pull/94) | `5beb938` | `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-3-backend-tasks-split.md` / `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-3-backend-tasks-split-plan.md` |
| 2026-06-08 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 4：拆分 `DatabaseView.vue` 701 + `TemplateModal.vue` 665 → 各自聚焦子组件） | 技术债 / 重构 / 前端视图 | [#95](https://github.com/MarkDanile/MetaEduBase/pull/95) | `d4d2720` | `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-4-frontend-views-split.md` / `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-4-frontend-views-split-plan.md` |
| 2026-06-08 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 5：拆分 `document/router.py` 494 → 5 个聚焦子 router） | 技术债 / 重构 / 后端 FastAPI | [#96](https://github.com/MarkDanile/MetaEduBase/pull/96) | `4b03064` | `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-5-document-router-split.md` / `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-5-document-router-split-plan.md` |
| 2026-06-09 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 7：拆分 `FileDetailView.vue` 416 → 3 个聚焦子组件 + 主入口） | 技术债 / 重构 / 前端 Vue | [#98](https://github.com/MarkDanile/MetaEduBase/pull/98) | `3e7f827` | `views/resource/FileDetailView.vue` / `views/resource/FileMetaBar.vue` / `views/resource/FileDetailPipelineStatusPanel.vue` / `views/resource/FileTabsPanel.vue` |
| 2026-06-09 | DOC-041 清理 document_router 与 document_task_router 重复路由 | 文档 / 后端 / FastAPI / follow-up | [#99](https://github.com/MarkDanile/MetaEduBase/pull/99) | `ef4392e` | `document/interfaces/api/task_router.py` (removed) / `document/interfaces/api/tasks.py` (label source unified) / `app/main.py` (duplicate mount removed) |
| 2026-06-09 | TD-032 治理超大源码文件并建立文件规模拆分原则（切片 6：拆分 `ResourceLibraryView.vue` 490 → 3 个聚焦子组件 + 主入口） | 技术债 / 重构 / 前端 Vue | [#97](https://github.com/MarkDanile/MetaEduBase/pull/97) | `6728151` | `docs/02-delivery-plans/01-specs/2026-06-09-td-032-slice-6-resource-library-view-split.md` / `docs/02-delivery-plans/02-plans/2026-06-09-td-032-slice-6-resource-library-view-split-plan.md` |
| 2026-06-08 | TD-032 baseline 刷新（切片 1-4 收口后回写） | 文档 / 工程治理 / 维护 |  |  | `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` |
| 2026-06-08 | DOC-039 增强工程文档脚本门禁 | 文档 / 工程治理 / 门禁脚本 / 测试 |  |  | `scripts/engineering/check_engineering_docs.py` / `tests/engineering/test_check_engineering_docs.py` / `docs/03-engineering-governance/01-rules/quality-gates.md` |
| 2026-06-08 | DOC-038 恢复基础工程原则为单一事实源 | 文档 / 工程治理 / 规则入口 / 基础原则 |  |  | `docs/03-engineering-governance/01-rules/engineering-principles.md` / `AGENTS.md` / `CLAUDE.md` / `.claude/rules/engineeringPrinciples.md` / `.trae/rules/engineeringPrinciples.md` |
| 2026-06-08 | DOC-037 规则入口瘦身与脚本门禁候选清单整理 | 文档 / 工程治理 / 规则瘦身 / 门禁候选 |  |  | `AGENTS.md` / `CLAUDE.md` / `docs/03-engineering-governance/01-rules/quality-gates.md` / `.claude/rules/` / `.trae/rules/` |
| 2026-06-08 | DOC-036 收口 DOC-034 遗留的 REQ-008 spec 前文旧口径 | 文档 / 验收口径修正 / follow-up |  |  | `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/01-product-planning/04-backlog.md` |
| 2026-06-08 | DOC-035 建立任务评审评分卡与复盘数据口径 | 文档 / 工程治理 / 复盘 / 评分卡 |  |  | `docs/03-engineering-governance/01-rules/review-scorecard.md` / `docs/03-engineering-governance/04-retrospectives/README.md` |
| 2026-06-08 | DOC-034 修正 REQ-008 spec AC-5 与实际测试行为不一致 | 文档 / 验收口径修正 / follow-up | [#83](https://github.com/MarkDanile/MetaEduBase/pull/83) | `cfdbb23` | `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/01-product-planning/04-backlog.md` |
| 2026-06-08 | REQ-008 收口 REQ-004 验收证据与质量门禁缺口 | 需求 / follow-up / 质量门禁 | [#79](https://github.com/MarkDanile/MetaEduBase/pull/79) | `302ec2d` | `docs/01-product-planning/05-requirements/REQ-008-req-004-template-selection-quality-follow-up.md` / `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md` |
| 2026-06-08 | DOC-033 开发前分支门禁前移与产品规划状态可视化 | 文档 / 工程治理 / 产品规划 / 门禁脚本 |  |  | `docs/03-engineering-governance/01-rules/git-workflow.md` / `docs/03-engineering-governance/workflow.md` / `docs/01-product-planning/04-backlog.md` / `scripts/engineering/check_engineering_docs.py` |
| 2026-06-08 | REQ-004 模板匹配可解释化收口 | 需求 / 重构 / 测试 / P1 轨道 B 翻结论 | [#77](https://github.com/MarkDanile/MetaEduBase/pull/77) | `2e6d097` | `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md` |
| 2026-06-08 | DOC-031 补强 REQ follow-up 分流与跨事实源状态门禁 | 文档 / 工程治理 / 门禁脚本 |  |  | `docs/03-engineering-governance/task-modes.md` / `scripts/engineering/check_engineering_docs.py` / `docs/03-engineering-governance/04-retrospectives/2026-06-08-req-003-delivery-flow.md` |
| 2026-06-08 | REQ-007 收口 REQ-003 RAG 质量链路验收缺口 | 需求 / 测试 / follow-up | [#75](https://github.com/MarkDanile/MetaEduBase/pull/75) | `45db478` | `docs/01-product-planning/05-requirements/REQ-007-req-003-rag-quality-gate-follow-up.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md` |
| 2026-06-08 | REQ-003 P1 RAG 质量链路验收与回归测试 | 需求 / 测试 / P1 收口 | [#74](https://github.com/MarkDanile/MetaEduBase/pull/74) | `337238b` | `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md` |
| 2026-06-07 | DOC-030 建立真实 AI 应用组合轻量规划入口 | 文档 / 产品规划 / AI 应用组合 |  |  | `docs/01-product-planning/06-ai-applications/README.md` / `docs/01-product-planning/04-backlog.md` |
| 2026-06-07 | DOC-029 明确 P1/P2/P3 检索架构演进边界 | 文档 / 产品规划 / 架构 |  |  | `docs/01-product-planning/02-milestones/01-validation-phase.md` / `docs/01-product-planning/02-milestones/02-growth-phase.md` / `docs/01-product-planning/02-milestones/03-scale-phase.md` |
| 2026-06-07 | DOC-028 复核 P1 验证期并建立最终查漏补缺迭代 | 文档 / 产品规划 / 复核 |  |  | `docs/01-product-planning/02-milestones/01-validation-phase.md` / `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` |
| 2026-06-07 | DOC-027 恢复产品规划三阶段里程碑结构 | 文档 / 产品规划 |  |  | `docs/01-product-planning/01-roadmap.md` / `docs/01-product-planning/02-milestones/` |
| 2026-06-07 | DOC-026 移除 CodeGraph 工具选择范围约束 | 文档 / 工程治理 / 工具链 |  |  | `docs/03-engineering-governance/01-rules/local-development.md` / `docs/03-engineering-governance/workflow.md` |
| 2026-06-07 | DOC-025 补回 ARCHITECTURE 系统架构图与新路径索引 | 文档 / 架构 / 工程治理 |  |  | `ARCHITECTURE.md` |
| 2026-06-07 | DOC-023 补齐 Claude / Trae 流程级跳转入口 | 文档 / 工程治理 / AI 协作 |  |  | `.claude/rules/currentWork.md` / `.trae/rules/currentWork.md` |
| 2026-06-07 | DOC-022 复核技术债到交付闭环与插件输出门禁 | 文档 / 工程治理 / AI 协作 |  |  | `docs/03-engineering-governance/workflow.md` / `docs/03-engineering-governance/01-rules/quality-gates.md` |
| 2026-06-07 | DOC-021 docs 子层目录编号排序 | 文档 / 工程治理 / AI 协作 |  |  | `docs/01-product-planning/README.md` / `docs/02-delivery-plans/README.md` / `docs/03-engineering-governance/README.md` |
| 2026-06-07 | DOC-020 docs 分层目录完全迁移 | 文档 / 工程治理 / AI 协作 |  |  | `docs/README.md` / `docs/03-engineering-governance/01-rules/docs.md` |
| 2026-06-07 | DOC-019 建立产品规划层与复盘入口 | 文档 / 产品规划 / 工程治理 / AI 协作 |  |  | `docs/01-product-planning/README.md` / `docs/03-engineering-governance/04-retrospectives/README.md` |
| 2026-06-06 | DOC-018 增补 CodeGraph / `rg` 工具选择基线 | 文档 / 工具链 / AI 协作 |  |  | `docs/03-engineering-governance/01-rules/local-development.md#代码探索与搜索工具选择` |
| 2026-06-06 | DOC-017 Contracts / Task Modes 长期化重构 | 文档 / 工作流 / AI 协作 |  |  | `docs/02-delivery-plans/01-specs/2026-06-06-doc-017-contracts-task-modes-long-lived.md` |
| 2026-06-06 | DOC-016 Testing / Local Development 长期化重构 | 文档 / 测试 / Developer Experience |  |  | `docs/02-delivery-plans/01-specs/2026-06-06-doc-016-testing-local-development-long-lived.md` |
| 2026-06-06 | DOC-015 README / ARCHITECTURE 长期化重构 | 文档 / 架构 / AI 协作 |  |  | `docs/02-delivery-plans/01-specs/2026-06-06-doc-015-long-lived-entry-docs.md` |
| 2026-06-06 | TD-029 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 技术债 / 修复 / follow-up |  |  | `docs/03-engineering-governance/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误` |
| 2026-06-06 | TD-009 减少前后端契约漂移（结构化抽取容器契约） | 技术债 / 重构 |  |  | `docs/03-engineering-governance/technical-debt.md#td-009-减少前后端契约漂移` |
| 2026-06-05 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展） | 技术债 / 设计系统 | [#59](https://github.com/MarkDanile/MetaEduBase/pull/59) |  | `docs/03-engineering-governance/technical-debt.md#td-027-补-ui-input-ui-btn-ui-tag-ui-dialog-共享类设计系统扩展` |
| 2026-06-05 | TD-026 共享组件 `liquid-card` 残留验证 | 技术债 / 文档 / follow-up | [#58](https://github.com/MarkDanile/MetaEduBase/pull/58) |  | `docs/03-engineering-governance/technical-debt.md#td-026-共享组件-liquid-card-残留验证` |
| 2026-06-05 | DOC-014 刷新 README / ARCHITECTURE 项目入口文档 | 文档 / 架构 / 交接 |  |  | `README.md` / `ARCHITECTURE.md` |
| 2026-06-05 | DOC-013 工程文档门禁增强与 UI 迁移事实源收口 | 文档 / 工程规范 / 工具链 |  |  | `scripts/engineering/check_engineering_docs.py` |
| 2026-06-05 | TD-023 收口 TD-020 文档一致性、断链与归档索引 | 文档 / 工程流程 / 跨 AI 交接 / follow-up |  |  | `docs/03-engineering-governance/technical-debt.md#td-023-收口-td-020-文档一致性-断链与归档索引` |
| 2026-06-05 | DOC-012 工程文档自动门禁与工作台瘦身 | 文档 / 工程规范 / 工具链 |  |  | `docs/02-delivery-plans/02-plans/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming-plan.md` |
| 2026-06-05 | TD-020 统一 LLM provider resolver 与 factory 优先级事实源 | 技术债 / 重构 | [#46](https://github.com/MarkDanile/MetaEduBase/pull/46) | `2c15868` | `docs/03-engineering-governance/technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源` |
| 2026-06-05 | DOC-011 技术债总账结构化展示优化 | 文档 / 工程规范 |  |  | `docs/03-engineering-governance/technical-debt.md` |
| 2026-06-05 | DOC-010 收敛完成门禁并瘦身重复流程规则 | 文档 / 工程规范 |  |  | `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁` |
| 2026-06-05 | TD-021 收口已完成计划文件和候选区状态同步漏洞 | 技术债 / 文档 / 工程流程 |  |  | `docs/03-engineering-governance/technical-debt.md#td-021-收口已完成计划文件和候选区状态同步漏洞` |
| 2026-06-05 | TD-022 收口早期已完成计划文件的活动式未勾选项 | 技术债 / 文档 / 工程流程 / follow-up | [#44](https://github.com/MarkDanile/MetaEduBase/pull/44) | `f33c19c` | `docs/03-engineering-governance/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项` |
| 2026-06-05 | DOC-009 生成 TD-005/006/007 follow-up 与规则补强 | 文档 / 工程规范 |  |  | `docs/03-engineering-governance/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归` |
| 2026-06-05 | TD-005 拆分大型后端任务流水线文件（抽任务生命周期 helper） | 技术债 / 重构 | [#34](https://github.com/MarkDanile/MetaEduBase/pull/34) | `e5197a5` | `docs/03-engineering-governance/technical-debt.md#td-005-拆分大型后端任务流水线文件` |
| 2026-06-05 | TD-006 集中 LLM provider 和模型 fallback 策略 | 技术债 / 重构 | [#35](https://github.com/MarkDanile/MetaEduBase/pull/35) | `042e4a9` | `docs/03-engineering-governance/technical-debt.md#td-006-集中-llm-provider-和模型-fallback-策略` |
| 2026-06-05 | TD-007 减少前端请求状态处理重复（DatabaseView 迁到 Vue Query） | 技术债 / 重构 | [#36](https://github.com/MarkDanile/MetaEduBase/pull/36) | `350acd2` | `docs/03-engineering-governance/technical-debt.md#td-007-减少前端请求状态处理重复` |
| 2026-06-05 | TD-015 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归 | 技术债 / 修复 / follow-up | [#38](https://github.com/MarkDanile/MetaEduBase/pull/38) | `f38fbbc` | `docs/03-engineering-governance/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归` |
| 2026-06-05 | TD-016 收敛 knowledge ai_router 的 LLM provider 选择重复逻辑 | 技术债 / 重构 / follow-up | [#39](https://github.com/MarkDanile/MetaEduBase/pull/39) | `4e6cf42` | `docs/03-engineering-governance/technical-debt.md#td-016-收敛-knowledge-ai_router-的-llm-provider-选择重复逻辑` |
| 2026-06-05 | TD-017 将 Vue Query 请求生命周期治理推广到 FileDetailView | 技术债 / 重构 / follow-up | [#40](https://github.com/MarkDanile/MetaEduBase/pull/40) | `5af2793` | `docs/03-engineering-governance/technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview` |
| 2026-06-05 | TD-018 FileDetailView 剩余手写 load 迁到 Vue Query | 技术债 / 重构 / follow-up | [#41](https://github.com/MarkDanile/MetaEduBase/pull/41) | `8ad15e6` | `docs/03-engineering-governance/technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query` |
| 2026-06-05 | TD-019 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 | 技术债 / 修复 / follow-up | [#42](https://github.com/MarkDanile/MetaEduBase/pull/42) | `387d8f8` | `docs/03-engineering-governance/technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误` |
| 2026-06-05 | DOC-008 将合并后 backfill 改为条件触发 | 文档 / 工程规范 |  |  | `docs/03-engineering-governance/01-rules/git-workflow.md` |
| 2026-06-05 | DOC-007 压缩 current-work 最近完成区并强化渐进式披露 | 文档 / 工程规范 | [#30](https://github.com/MarkDanile/MetaEduBase/pull/30) | `3b36023` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-05 | DOC-006 修复 current-work 重复完成区标题 | 文档 / 工程规范 | [#29](https://github.com/MarkDanile/MetaEduBase/pull/29) | `7d0f427` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-05 | TD-014 加强测试数据库 legacy stamp 的列级形态校验 | 技术债 / follow-up | [#28](https://github.com/MarkDanile/MetaEduBase/pull/28) | `af7d246` | `docs/03-engineering-governance/technical-debt.md#td-014-加强测试数据库-legacy-stamp-的列级形态校验` |
| 2026-06-05 | TD-013 收口 TD-004 测试数据库初始化安全与文档占位 | 技术债 / follow-up | [#27](https://github.com/MarkDanile/MetaEduBase/pull/27) | `8f25b20` | `docs/03-engineering-governance/technical-debt.md#td-013-收口-td-004-测试数据库初始化安全与文档占位` |
| 2026-06-04 | DOC-005 补强复核入账与候选任务选择策略 | 文档 / 工程规范 | [#25](https://github.com/MarkDanile/MetaEduBase/pull/25) | `7a4241c` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-04 | TD-004 让后端测试数据库环境可复现 | 技术债 / 基础设施 | [#23](https://github.com/MarkDanile/MetaEduBase/pull/23) | `b8b34a6` | `docs/03-engineering-governance/technical-debt.md#td-004-让后端测试数据库环境可复现` |
| 2026-06-04 | DOC-003 补强跨插件计划、行为声明和 PR 范围边界规则 | 文档 / 工程规范 | [#20](https://github.com/MarkDanile/MetaEduBase/pull/20) | `3b883ea` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-04 | DOC-002 强化跨 AI 提交前回查与验证声明规范 | 文档 / 工程规范 | [#16](https://github.com/MarkDanile/MetaEduBase/pull/16) | `f438307` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-04 | TD-012 治理后端全量 ruff 质量门禁 | 技术债 | [#17](https://github.com/MarkDanile/MetaEduBase/pull/17) | `a4dcb2a` | `docs/03-engineering-governance/technical-debt.md#td-012-治理后端全量-ruff-质量门禁` |
| 2026-06-04 | TD-002-FOLLOWUP 收口 TD-002 流程与测试遗留 | 技术债 / 修复 / 文档 | [#13](https://github.com/MarkDanile/MetaEduBase/pull/13) | `ea34271` | `docs/03-engineering-governance/current-work.md` |
| 2026-06-04 | TD-002 收敛文件清理的级联删除逻辑 | 技术债 | [#12](https://github.com/MarkDanile/MetaEduBase/pull/12) | `2eb59e8` | `docs/03-engineering-governance/technical-debt.md#td-002-收敛文件清理的级联删除逻辑` |
| 2026-06-04 | TD-001 拆分应用启动时的数据库迁移与默认种子数据 | 技术债 / 基础设施 |  | `291dbbc` | `docs/03-engineering-governance/technical-debt.md#td-001-拆分应用启动时的数据库迁移与默认种子数据` |
| 2026-06-04 | TD-011 治理前端 lint warning | 技术债 / 基础设施 |  | `090242a` | `docs/03-engineering-governance/technical-debt.md#td-011-治理前端-lint-warning` |
| 2026-06-04 | TD-003 让前端 lint 质量门禁可运行 | 技术债 / 基础设施 |  | `090242a` | `docs/03-engineering-governance/technical-debt.md#td-003-让前端-lint-质量门禁可运行` |
| 2026-06-04 | DOC-001 统一并优化跨 AI 工程规则 | 文档 / 工程规范 |  | `c0bac8a` | `docs/03-engineering-governance/workflow.md` |

## 段落归档

当一段工作由多个连续 PR / 任务组成、并构成一个相对独立的工程主题时，在此用一节记录总览，避免单行索引表把段落切碎。详细事实仍以对应 PR、merge commit、`technical-debt.md` 任务卡、`coding-style.md` 迁移说明为准。

### 2026-06-05 设计系统迁移：`liquid-*` → `ui-*`

一段连贯的 5 任务工作，把前端样式体系从「以 `liquid-*` 类为中心」迁移到「`ui-*` 优先 / `liquid-*` 兼容」。完成「calm workspace / token 化 / 不带装饰动效」的统一目标。

**任务链与 PR**：

| # | 任务 | 切片 | PR | Merge Commit | 关键事实 |
|---|------|------|-----|--------------|----------|
| 1 | TD-008 明确从 `liquid-*` 类到语义 UI 层的迁移路径 | 共享骨架 | [#53](https://github.com/MarkDanile/MetaEduBase/pull/53) | `1f32e4a` | 5 个 `ui-*` 容器层共享类（`ui-page-shell` / `ui-page-section` / `ui-panel` / `ui-toolbar` / `ui-interactive-row`）+ 3 个共享骨架组件迁移（`LayoutView` / `PageHeader` / `EmptyState`）；建立迁移规范（`coding-style.md#迁移说明-td-008`） |
| 2 | TD-025 业务页面 `liquid-card` 容器统一迁移到 `ui-panel` | 业务视图（3 切片） | [#54](https://github.com/MarkDanile/MetaEduBase/pull/54) + [#55](https://github.com/MarkDanile/MetaEduBase/pull/55) + [#56](https://github.com/MarkDanile/MetaEduBase/pull/56) | `558884e` + `90763d1` + `26d4654` | 7 业务页面 20 处 `liquid-card` → `ui-panel`；`liquid` 主题下 `ui-panel` 加玻璃感覆盖（`main.css` 行 1154） |
| 3 | TD-026 共享组件 `liquid-card` 残留验证 | 零代码收口 | [#58](https://github.com/MarkDanile/MetaEduBase/pull/58) | `7735046` | 严格 `rg "liquid-card"` 验证 4 个共享组件 0 命中；任务卡残留量 22 处为 TD-008 快照误计 |
| 4 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类 | 设计系统扩展 | [#59](https://github.com/MarkDanile/MetaEduBase/pull/59) | `040f7ad` | 12 个 `ui-*` 原子层共享类（`ui-input` / `ui-btn` 4 类 / `ui-tag` 5 类 / `ui-dialog` 2 类）+ 2 个新 token（`--overlay-bg` / `--btn-ripple`，4 主题分别给值） |
| 5 | TD-028 业务视图与共享组件的 `liquid-*-atomic` 存量替换 | 机械批量替换 | [#61](https://github.com/MarkDanile/MetaEduBase/pull/61) | `349c743` | 12 文件 119 处 `liquid-input` / `liquid-btn*` / `liquid-tag*` / `liquid-dialog*` → `ui-*` + 5 处 `\`liquid-tag-${color}\`` 模板字符串迁移 |

**段落级 PR（状态回填）**：[#57](https://github.com/MarkDanile/MetaEduBase/pull/57) (TD-008/TD-025 状态回填) + [#60](https://github.com/MarkDanile/MetaEduBase/pull/60) (TD-027 状态回填) + [#62](https://github.com/MarkDanile/MetaEduBase/pull/62) (TD-028 状态回填)。

**最终成果**：
- `ui-*` 容器层（5）+ 原子层（12）= **17 个共享类**，全部 token 化复用现有 `--color-*` / `--radius-*` / `--shadow-*` / `--duration-*` / `--ease-*` / `--surface-*` token
- 业务视图与共享组件 100% 切到 `ui-*`（容器 + 原子）
- 4 主题（liquid / ink / navy / notion）视觉不发生可观察退化（除 `liquid-card:hover` 上浮取消、`wet-line` 装饰条移除、`animate-slide-up` 入场动画移除、`liquid-card-scan` 装饰保留等已声明的有意行为变化外）
- `liquid-*` 类全部保留为兼容别名（`main.css` 中），无破坏性删除
- `LoginView` 品牌背景 / `liquid-card` / `liquid-card-scan` 装饰动效按 TD-008 规则保持兼容

**过程中的关键决策**（按"先想后写 + 用户确认"原则）：
- TD-008 范围：ui-panel 玻璃感覆盖在 liquid 主题下加；其他 3 主题维持白底细边框
- TD-025 切片 1：保留 `liquid-card-scan` 装饰动效；保留 `animate-slide-up` + `stagger-N`
- TD-025 切片 3：保留 `HomeView` `liquid-card-scan` 装饰；`coding-style.md` 显式登记 6 类例外（`liquid-btn-primary` / `liquid-btn-ghost` / `liquid-input` / `liquid-tag-*` / `liquid-card-scan` / `stagger-N` & `animate-slide-up`）
- TD-026 路径选择：用户从三选项中选"实测收口"（任务卡残留量与实际不符规律已在 TD-025 切片 2/3 出现 3 次）；设计系统扩展拆为 TD-027（补类）+ TD-028（替换）
- TD-027 自动模式 build 拒批硬编码 rgba → 用户选"确实抽 2 个新 token" → 补 `--overlay-bg` / `--btn-ripple` 4 主题分别给值
- TD-027 用户选择 ui-btn-primary 保留装饰（点按泠漪）+ 动效节奏与 liquid-* 一致 + 5 个 ui-tag 变体
- TD-028 一次完成 119 处（杠杆最大）；LoginView 也迁（仅 input/btn，品牌背景仍例外）；零差异

**复盘 / 经验**：
1. **任务卡残留量与实际不符的规律在 TD-025 切片 2/3 + TD-026 反复出现**（4 次：TemplateModal 8→0、TemplateEditorView 6→0、FieldEditor 12→0、KGDetailPanel 4→0、ConfirmDialog 5→0、KGGraph 1→0）。任务卡编写时把页面里所有 `liquid-*` 类（`liquid-btn-*` / `liquid-input` / `liquid-tag-*` / `liquid-dialog*` / `liquid-card`）都误计入 `liquid-card` 残留。后续技术债应明确"以 `rg` 实测为准，不使用任务卡原残留量"作为新债编写约定。
2. **从长到短的 sed 替换顺序是机械替换的安全保证**（`liquid-btn-primary` → `liquid-btn` 基类 → `liquid-tag-blue/green/amber/purple` → `liquid-tag` 基类 → `liquid-input` → `liquid-dialog-overlay` → `liquid-dialog`），保证子串不被父串吞掉。
3. **token 化与命名一致性是设计系统扩展的前提**。TD-027 在 PR #59 第一次提交时，`ui-dialog-overlay` 与 `ui-btn-primary::after` 仍使用硬编码 `rgba(0, 0, 0, 0.2)` 与 `rgba(255, 255, 255, 0.25)`（从 `liquid-*` 1:1 复制），自动模式 build 分类器拒批后必须补 `--overlay-bg` / `--btn-ripple` 2 个新 token（4 主题分别给值）。事后看，TD-008 应在建 `ui-panel` 玻璃覆盖时同步补 2 个 token，但当时是"`ui-panel` 单独覆盖"未扩到 4 类。**建议把 `--overlay-bg` / `--btn-ripple` 路径在 `coding-style.md` 写明"任何 `ui-*` 新类必须在 main.css 中以 token 形式引用颜色，不允许硬编码 rgba"**——但本工作已通过 TD-027 满足此约束。
4. **状态回填 PR 是 docs-only 的"小 PR"模式**。3 个状态回填 PR（#57、#60、#62）每次 2-3 个文件 + 1 个原子提交，专门把 `current-work.md` 候选区清理 + 最近完成区追加 + `technical-debt.md` 总览表状态修正，保持 `quality-gates.md#完成门禁#3`（状态不自相矛盾）。这种 PR 没有代码变更但对跨 AI 交接极重要。
5. **`liquid-*` 作为兼容别名长期保留是设计系统迁移的正确策略**。5 个任务全部完成，但 `main.css` 中 `liquid-*` 类未删除（也不应该删）；新增 `ui-*` 体系与 `liquid-*` 1:1 镜像，纯属"新约定优先"+"历史兼容保留"的并存模式。后续 AI IDE 接手时只需遵循 `coding-style.md#迁移说明-td-008` 即可。

**未来接力**：
- TD-009 减少前后端契约漂移（P2，API / 类型）：选高价值契约族（模板字段或任务状态），建共享 schema 检查。

**主要文档事实源**：
- 迁移规范：[docs/03-engineering-governance/01-rules/coding-style.md#迁移说明-td-008](01-rules/coding-style.md)
- 任务清单：[docs/03-engineering-governance/01-rules/coding-style.md#业务页面迁移清单-td-025](01-rules/coding-style.md) + [docs/03-engineering-governance/01-rules/coding-style.md#共享组件迁移清单-td-026](01-rules/coding-style.md)
- 任务总账：5 个 TD 任务卡（[TD-008](technical-debt.md) / [TD-025](technical-debt.md) / [TD-026](technical-debt.md) / [TD-027](technical-debt.md) / [TD-028](technical-debt.md)）

### 2026-06-08 REQ-003 / REQ-007 P1 RAG 质量链路收口

一段连贯的 2 任务工作：先按 REQ-003 收口 P1 验证期 RAG 质量链路（4 块验收），再按 REQ-007 收口 REQ-003 复盘发现的几类缺口（5 AC）。本段落用于承载需要长期追踪的验证声明与环境区分事实，避免 `current-work.md` 摘要膨胀。

**任务链与 PR**：

| # | 任务 | 切片 | PR | Merge Commit | 关键事实 |
|---|------|------|-----|--------------|----------|
| 1 | REQ-003 P1 RAG 质量链路验收与回归测试 | 4 测试文件 + 5 AC | [#74](https://github.com/MarkDanile/MetaEduBase/pull/74) | `337238b` | 24 个新测试用例覆盖 NER / 融合 / 3 通道契约 / ai_chat e2e；轨道 B 4 行翻结论；Protocol-vs-concrete drift 由 [TD-030](technical-debt.md#td-030) / [PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139) (merge `a934981`) 于 2026-06-10 收口 |
| 2 | REQ-007 收口 REQ-003 RAG 质量链路验收缺口 | 5 AC 收口 | [#75](https://github.com/MarkDanile/MetaEduBase/pull/75) | `45db478b` | 1 个新行为级测试文件（9 用例：fake rows + SQL 参数绑定 + 空输入早退）；e2e 死代码 -35 行；P1 / 迭代 / Backlog / current-work 状态同步；P1 轨道 B 4 行过度验证声明改写；`TD-031` ruff 预存警告入账并自动修复 |

**验证声明（按环境区分）**：

- **CLAUDE.md 本地环境（mock-based 路径，当前可复现）**：
  - `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/ -q` → `5 个测试文件 38/38 passed`，exit 0。
  - `cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/ai/` → `All checks passed!` exit 0。
  - REQ-007 引入的所有 4 个新测试文件均走 mock（`AsyncMock` + `MagicMock`），**不依赖 PostgreSQL**，因此当前环境可复现。
  - `scripts/check-engineering-docs` → `engineering docs checks passed` exit 0。

- **Codex / 依赖 PG 集成测试的环境（不可复现部分）**：
  - `tests/contexts/ai` 之外的某些测试（如 `test_ai_chat.py::test_chat_with_mock_llm` 等依赖 `client` fixture 的用例）需要 `metaedu_test` 库。
  - 本机 `metaedu_test` 不可达（迭代卡 Review 段已记录），跑 `tests/contexts/ai/test_ai_chat.py` 的 5 个用例会出现 DB 连接错误。
  - **这不在 REQ-007 验收范围**——REQ-007 的 5 个 AC 都用 mock 路径。端到端 PostgreSQL 集成验收由 **REQ-006** 接力，要求先修复本机 DB 连通性。

**复盘 → 流程改进**：
- 验证结果**必须区分执行环境**（如本段），不得把不同环境跑出的 `38 passed` 与 `DB connection error` 直接等同或互相覆盖。该信号已归档到 [REQ-003 / REQ-007 交付流程复盘](04-retrospectives/2026-06-08-req-003-delivery-flow.md)。
