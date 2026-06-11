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
| TD-050 `EvidenceItem` 缺 `source_chunk_id` 字段 / spec 与实现错位 | 🟡 进行中 | P3 | 后端 / RAG / API 契约 / 文档 | **路线 A2 已拍板**（用户 2026-06-11）：A1 全部 + `EvidenceItem` 新增 `source_chunk_id` 字段 + 双写 `chunk_id` / `source_chunk_id`。债项卡 `🔵 就绪`、spec [§4 推荐理由](../02-delivery-plans/01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md) 重写为 A2。**未动业务代码**（路线拍板 docs-only 第一阶段）。分支 `chore/td-050-evidence-item-source-chunk-id-pass-through` 已建。 | 1. 写 plan [§5.2 路线 A2 细化切片](../02-delivery-plans/01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md) → 2. 在 dev 库跑 SQL 验证 `knowledge_nodes.source_file_id` / `source_chunk_id` 数据存在（预计 81.91% 节点有值）→ 3. 业务代码 8 文件改动（3 SQL + RecallResult + EvidenceItem + PgGraphRetriever + contracts.md）→ 4. 写 2 个新 pytest（透传 + 字段访问）→ 5. 同步 REQ-010 spec L40 + spec §3.1 末尾"AC-3 解读说明" + plan Step 3.1 注 → 6. 跑全量后端 pytest + ruff + check-engineering-docs → 7. 提交 + PR。 | 文档-only 第一阶段已完成：technical-debt 任务卡补全（状态 `🔵 就绪`）；spec 三路线对比写完 + 推荐路线 A2 理由重写；workbench 当前进行中行登记。**未运行**后端 pytest / ruff（业务代码未动，按路线 A2 切片执行）。**未提交** commit（用户未显式触发提交；按 git-workflow "按流程提交" 才推进到 commit / push / PR）。 |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| REQ-012 RAG 多路召回与知识图谱证据链收口 | 🟣 Shaping | P1 | RAG / AI Chat / Evidence / KG | 详看 [Requirement](../01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md)；REQ-010 质量 follow-up 的正式稳定编号。**TD-047 已收口**（zhparser + chinese_zh，剩 182 file_only 节点属 embedding 召回范围），**TD-050 是 REQ-012 启动的前置依赖**（node 类型 evidence 需透传 source_chunk_id 才能在 RAG 链路收口里完整给 embedding 召回用）。REQ-012 启动时把"TD-047 + TD-050 已收口"作为前置依赖写进 spec，直接进入 RAG 链路收口工作。 |
| TD-049 `tests/conftest.py` 8 E402 pre-existing（TD-012 收口后遗留） | ⚫ 待办 | P3 | 后端 / 测试 / 质量门禁 / 工程治理 | 详看 `technical-debt.md#td-049`；8 个 E402 全在 `tests/conftest.py:13-20`，根因 L11 `sys.path.insert` 块；修复方案已记（挪到新建 `tests/_paths.py`）。低风险，下一批可独立 PR。 |
| （TD-050 已移出候选区，进入"当前进行中"） | | | | |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-11 | TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector） | 🟢 完成 | 6 切片 5 commit 收口：zhparser + chinese_zh + plainto_tsquery；dev 库 70/252 file_only → chunk_resolved（总覆盖率 74.95% → 81.91%，+6.96 pct）；runtime 镜像增量 23MB。 | [TD-047](technical-debt.md#td-047-中文分词回填-iliike-限制p1-数据债衍生) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-047-zhparser-chinese-tsvector.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-047-zhparser-chinese-tsvector-plan.md) |
| 2026-06-11 | TD-048 `SourceItem` 旧字段下个迭代删除（契约 deprecation 窗口） | 🟢 完成 | 删 ai_router.py 旧 SourceItem/ChatResponse/_recall_to_source/ai_chat handler/`@router.post('/chat')`；迁 3 测试 + 1 docs 矩阵到 evidence 端点；319 passed + 1 skipped 零回归。分支 `chore/td-048-remove-sourceitem-legacy-contract`。 | [TD-048](technical-debt.md#td-048-sourceitem-旧字段下个迭代删除契约-deprecation-窗口) |
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
