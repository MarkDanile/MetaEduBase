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

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| DOC-058 显式加"任务分支未合 main 不得翻 🟢 完成；`gh pr view <PR>` state 必须为 MERGED"规则（workbench.md + git-workflow.md + quality-gates.md） | 🟡 进行中 | P2 | 文档 / 工程流程 / 跨 AI 交接 | 分支 `docs/doc-058-branch-merge-required-to-complete` 已建（base `58c332c`）；3 规则文件待改：workbench.md 末尾追加 1 段"任务分支未合 main 不得翻完成"硬规则；git-workflow.md"完整交付闭环" 6 阶段后追加"翻完成前硬条件"段；quality-gates.md 完成门禁第 3 条"状态"项补"任务分支未合 main 视为未走完 Git 阶段" | 改 3 文件 → `scripts/check-engineering-docs` → `pytest tests/engineering/test_check_engineering_docs.py` → `git diff --check` → 提交 → push → 开 PR → 合 main → 翻 🟢 | 待跑 |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| REQ-012 RAG 多路召回与知识图谱证据链收口 | 🟣 Shaping | P1 | RAG / AI Chat / Evidence / KG | 详看 [Requirement](../01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md)；REQ-010 质量 follow-up 的正式稳定编号。**TD-047 + TD-050 均已收口**（zhparser + chinese_zh 全文检索升级 + node 类型 evidence 透传 source_chunk_id）；REQ-012 启动时把"TD-047 + TD-050 已收口"作为前置依赖写进 spec，直接进入 RAG 链路收口工作。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-12 | TD-049 `tests/conftest.py` `sys.path.insert` 块导致 8 E402 pre-existing（TD-012 收口后遗留） | 🟢 完成 | 新建 `packages/server-python/tests/_paths.py` 持有 `_REPO_ROOT` + `sys.path.insert` 副作用；`tests/conftest.py` 删除 sys.path 块改为 `from tests._paths import _REPO_ROOT`，ruff E402 + I001 全部消除退出码 0；`pytest --collect-only tests/engineering` 4 tests collected 0.00s exit 0；`pytest tests/engineering/test_evidence_coverage_report.py -v` 4 passed exit 0；mock-based 子集 219 passed in 26.21s exit 0；`scripts/engineering/check_engineering_docs.py` exit 0（4 条 pre-existing 警告来自 TD-048 PR #199 merge 与本债无关）；0 业务代码变更。 | [TD-049](technical-debt.md#td-049) / PR #200（merge `cfad2b4`） |
| 2026-06-11 | TD-048 `SourceItem` 旧字段下个迭代删除（契约 deprecation 窗口） | 🟢 完成 | 3 切片 3 PR 收口：PR-1 docs-only 修事实源（#196，merge `ba7f441`，修工作台假完成 + technical-debt 翻 🟡 + work-log L21 加 ⚠️ 标注 + 入账 DOC-057）+ PR-2 业务代码（#197，merge `760d147`，4 业务文件 + 1 矩阵 + 2 新建 spec/plan）+ PR-3 docs-only 跨事实源收口（本 PR）。mock-based pytest 47 passed 零回归（沙箱无 PG，全量 pytest 由 CI 接力）；ruff 8 个 TD-049 pre-existing 兼容；DOC-057 pre-existing validation-claim 提示由独立 PR 收口。 | [TD-048](technical-debt.md#td-048) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-048-sourceitem-deprecation-removal-plan.md) / PR #196 + #197 |
| 2026-06-11 | TD-050 `EvidenceItem` 缺 `source_chunk_id` 字段 / spec 与实现错位（路线 A2） | 🟢 完成 | 3 切片 3 PR 收口：PR-1 docs-only 同步（#193） + PR-2 业务代码 + pytest（#194，4 业务文件 + 2 pytest 文件 / 10 新 pytest） + PR-3 docs-only 跨事实源收口（本 PR）。全量 pytest 336 passed + 1 skipped 零回归；ruff 8 个 TD-049 pre-existing 兼容；Recall Protocol 形参不变。 | [TD-050](technical-debt.md#td-050-evidenceitem-缺-source_chunk_id-字段--spec-与实现错位) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through-plan.md) / PR #193 + #194 |
| 2026-06-11 | TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector） | 🟢 完成 | 6 切片 5 commit 收口：zhparser + chinese_zh + plainto_tsquery；dev 库 70/252 file_only → chunk_resolved（总覆盖率 74.95% → 81.91%，+6.96 pct）；runtime 镜像增量 23MB。 | [TD-047](technical-debt.md#td-047-中文分词回填-iliike-限制p1-数据债衍生) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-047-zhparser-chinese-tsvector.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-047-zhparser-chinese-tsvector-plan.md) |
| 2026-06-11 | DOC-060 针对全部评审评分做阶段复盘 | 🟢 完成 | 基于 40 条评分记录完成阶段复盘：平均分 84.8，一次关闭率 60%，返工率 40%，流程扣分率约 63%；结论是 Harness 已有价值，但需求类 AC、真实数据验证和多事实源收口仍是重点。 | [Retrospective](04-retrospectives/2026-06-11-review-score-retrospective.md) / [Review Score Log](04-retrospectives/review-score-log.md) |
| 2026-06-11 | DOC-059 点名任务入口解析门禁与最近完成固定裁剪规则 | 🟢 完成 | 新增 `task-modes.md#任务入口解析门禁`，明确 Backlog / Requirement / Milestone / TD 点名任务进入实现前必须先定位事实源并登记工作台；最近完成区超过 20 行时固定裁到最新 12 行。 | [Task Modes](task-modes.md#任务入口解析门禁) / [Workbench](01-rules/workbench.md#保留策略) / [Workflow](workflow.md#开发前检查) |
| 2026-06-11 | TD-046 P1 RAG 数据债批次（3 个 backfill 真跑） | 🟢 完成 | 真 PG 跑通 3 个 backfill (node-source-chunk 754/1006, file-metadata 25/25, chunk-embedding 100/100)。P1 RAG 基线 4 指标全部提升，详见 TD-046。0 业务代码改动。[PR #187](https://github.com/MarkDanile/MetaEduBase/pull/187) | [TD-046](technical-debt.md#td-046) |
| 2026-06-11 | TD-043 打通后端 Python 对 `@metaedu/shared/schemas/document` 的 import 路径（路线 A codegen） | 🟢 完成 | TS 端 codegen 生成 Python frozenset；后端 `extract_template_prompts.py` 删除硬编码改为 import；codegen 脚本 + 生成的 Python schema package 已就绪。详见 technical-debt.md。 | [TD-043](technical-debt.md#td-043-打通后端-python-对-shared-schemasdocument-的-import-路径) / [PR #185](https://github.com/MarkDanile/MetaEduBase/pull/185) |
| 2026-06-11 | TD-039 6 键保留集合在 TS 端抽到 `@metaedu/shared/schemas/document` + spec 单一来源落地 | 🟢 完成 | `document.ts` 新增 `TEMPLATE_META_RESERVED_KEYS` 导出；`FileTabsPanel.vue` 删除硬编码，改为 import 共享常量；全门禁通过。Python 路径接入见 TD-043。 | [TD-039](technical-debt.md#td-039-6-键保留集合在-ts-端抽到-metaedusharedschemasdocument--spec-单一来源落地) / [PR #182](https://github.com/MarkDanile/MetaEduBase/pull/182) |
| 2026-06-10 | REQ-010 P1 RAG 证据治理与 AI Chat 溯源体验 | 🟢 完成 | 8 Slice 收口（Slice 1-6 历史 PR + Slice 7 PR #181 + Slice 8 fixture+e2e+跨事实源同步）。P1 RAG 基线：node_source_chunk 0% / chunk_embedding 100% / chunk_tsvector 93.55% / file_metadata 0%。e2e 沙箱 skip。详见 TD-044。 | [TD-044](technical-debt.md#td-044) / [Spec](../02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md) / [Plan](../02-delivery-plans/02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md) / [PR #181](https://github.com/MarkDanile/MetaEduBase/pull/181) |
| 2026-06-11 | REQ-011 AI 应用广场与应用注册中心 | 🟢 完成 | 4 Slice 全部完成：数据模型 + API CRUD（#174）+ 前端路由/菜单/广场列表/详情页（#175）+ 管理列表/编辑页（#178）+ 分享页/Token 端点（#179）；APP-001~004 种子数据就绪。 | [Spec](../02-delivery-plans/01-specs/2026-06-11-req-011-ai-app-marketplace.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-req-011-ai-app-marketplace-plan.md) / PR #174/#175/#178/#179 |
| 2026-06-10 | REQ-002-4 模板可维护性 | 🟢 完成 | schema_version 演进 + 容器互转二次确认 + deprecated 标记 + 6 键保留键校验。16 条新 pytest + 89/89 全过；前端弃用 UI + 二次确认 + 红框校验。REQ-002 子任务链收口。 | [Spec](../02-delivery-plans/01-specs/2026-06-10-req-002-4-template-maintainability.md) / [Plan](../02-delivery-plans/02-plans/2026-06-10-req-002-4-template-maintainability-plan.md) / [PR #170](https://github.com/MarkDanile/MetaEduBase/pull/170) (merge `e8fd5474`) |
| 2026-06-10 | TD-042 模板复用后端集成测试在 PG 实例下验证 | 🟢 完成 | 真 PG 跑通 `make migrate` 升 007 / `downgrade` / `init-test-db`；reuse 8 条 pytest + 模板目录回归均通过；顺带修 007 迁移 inline FK + asyncpg 反射 PK 缺陷。详见 technical-debt 总账与 work-log。 | [TD-042](technical-debt.md#td-042) / [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) |
| 2026-06-10 | TD-041 FieldCard 递归渲染嵌套字段 + 嵌套拖拽 | 🟢 完成 | 新建 FieldList.vue 递归组件；FieldCard 递归渲染 children/items + 同层拖拽；修 removeColumn/copySubtree bug。[PR #161](https://github.com/MarkDanile/MetaEduBase/pull/161) | [TD-041](technical-debt.md#td-041) / [Spec](../02-delivery-plans/01-specs/2026-06-10-td-041-field-card-recursive-rendering.md) / [PR #161](https://github.com/MarkDanile/MetaEduBase/pull/161) |
