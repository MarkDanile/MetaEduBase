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
| REQ-002-4 模板可维护性 | 🔵 Ready | P2 | Backend / Frontend | spec + plan 已建（[Spec](../02-delivery-plans/01-specs/2026-06-10-req-002-4-template-maintainability.md) / [Plan](../02-delivery-plans/02-plans/2026-06-10-req-002-4-template-maintainability-plan.md)）；分支 `docs/req-002-4-template-maintainability`（仅 spec/plan，尚未实现）；4 个新 DB 字段 + 2 个新端点 + 破坏性变更检测 + 字段命名校验 + 前端二次确认。 | 业务代码实现（Task 1-5 后端 + Task 6 测试 + Task 7-9 前端 + Task 10-11 文档+回归） | 待运行：`make migrate` + `pytest tests/contexts/template tests/contexts/document` + `pnpm typecheck` + `pnpm lint` + `scripts/check-engineering-docs` |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-041 FieldCard 递归渲染嵌套字段 + 嵌套拖拽 | ⚫ 待办 | P2 | 前端 / 架构 | 详看 `technical-debt.md#td-041`；需 FieldCard 自引用递归渲染 + vuedraggable 包裹 children/items |
| REQ-010 P1 真实 RAG 证据治理与 AI Chat 溯源体验 | 🟣 Shaping | P1 | RAG / AI Chat / Evidence / UX | 澄清 EvidenceItem 模型、chunk / KG / metadata / structured_data 证据关联、来源编号和参考文件列表交互，再进入 spec / plan |
| REQ-001 知识资产处理链路的产品化验收视图 | 🟣 Shaping | P2 | 需求 / 产品化验收 | 澄清目标用户、核心场景和验收指标 |

注：REQ-002 父任务（[Requirement](../01-product-planning/05-requirements/REQ-002-template-config-and-reuse.md)）及其子任务链（REQ-002-3 / REQ-002-1 / REQ-002-2 / REQ-002-4）均已在 backlog / milestone 中登记；本表只保留最近需接力的任务，避免与 backlog 重复维护状态。

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时再批量归档最旧记录，建议一次性压回 12 到 15 行左右；不要每完成一个任务就做单条搬运。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-10 | REQ-002-1 模板配置效率（编辑器 UX） | 🟢 完成 | 纯前端 UX：vuedraggable 拖拽 root 层 + 子树复制 + 撤销 toast + 折叠/展开 + 搜索过滤（30+ 阈值）+ normalize_status 脚本修复。AC-2/AC-3 嵌套拖拽部分完成（留 follow-up）。[PR #158](https://github.com/MarkDanile/MetaEduBase/pull/158) squash merge。 | [Spec](../02-delivery-plans/01-specs/2026-06-10-req-002-1-template-config-ux.md) / [Plan](../02-delivery-plans/02-plans/2026-06-10-req-002-1-template-config-ux-plan.md) / [PR #158](https://github.com/MarkDanile/MetaEduBase/pull/158) |
| 2026-06-10 | REQ-002-2 模板复用机制 | 🟢 完成 | 6 端点 + template_versions 表 + 版本快照 + 3 新组件 + 导入导出；8 条测试。[PR #159](https://github.com/MarkDanile/MetaEduBase/pull/159) | [Spec](../02-delivery-plans/01-specs/2026-06-10-req-002-2-template-reuse.md) / [PR #159](https://github.com/MarkDanile/MetaEduBase/pull/159) |
| 2026-06-10 | DOC-058 强化工作台规则渐进式披露入口 | 🟢 完成 | 将 `workbench.md` 从索引可见提升为”修改工作台或任务状态前必读”：入口、工作台自身、workflow、task-modes 和 Claude/Trae 兼容跳转同步补强。 | [Workbench](01-rules/workbench.md#使用规则) / [Workflow](workflow.md#开发前检查) / [Task Modes](task-modes.md#通用入口) |
| 2026-06-10 | DOC-057 建立并行开发模式与集成收口规则 | 🟢 完成 | 默认单任务闭环不变；新增用户显式触发的并行模式，要求可行性评估、独立分支/worktree、文件边界、合并顺序和集成者统一回填。 | [Task Modes](task-modes.md#并行开发模式) / [Workflow](workflow.md#并行开发模式) / [Workbench](01-rules/workbench.md#并行批次边界) / [Git Workflow](01-rules/git-workflow.md#并行分支规则) |
| 2026-06-10 | DOC-056 收口 `check_req_status_consistency` 父 / 子任务混聚 bug | 🟢 完成 | `REQ_ID_RE` 扩为 `\bREQ-\d{3}(?:-\d+)?(?![-\d])` + 新增 `test_parent_and_child_req_with_different_status_do_not_collide` regression（20 passed）。`check-engineering-docs` rc=0。 | [DOC-056](technical-debt.md#doc-056) / [Work Log](work-log.md) / [PR #155](https://github.com/MarkDanile/MetaEduBase/pull/155) |
| 2026-06-10 | REQ-002-3 模板抽取结果溯源字段扩展 | 🟢 完成 | 后端 `_merge_template_structured_data` 接受可选 `meta`（6 键白名单）+ `extract_template` 落盘 6 键溯源；前端 `FileTabsPanel` 过滤保留键 + 溯源元信息卡。pytest 71 passed + 全门禁过。follow-up：TD-039 / TD-040。 | [Work Log](work-log.md) / [PR #153](https://github.com/MarkDanile/MetaEduBase/pull/153) / [PR #154](https://github.com/MarkDanile/MetaEduBase/pull/154) |
| 2026-06-10 | DOC-055 收口 DOC-042 / TD-034 PR 范围混入与事实源漂移 | 🟢 完成 | PR #142 closed (superseded by PR #143) + TD-034 事实源统一为 PR #143/3077047 + `source-sizes --diff` 恢复 clean + DOC-051 跨事实源状态同步为 `🟢 完成` + 3 处 `TD-030（已锁定）` 占位改为 `占位说明`。docs-only，4 事实源 + 3 spec + 1 baseline 共 8 文件。 | [DOC-055](technical-debt.md#doc-055) / [Work Log](work-log.md) / [PR #142 (closed)](https://github.com/MarkDanile/MetaEduBase/pull/142) |
| 2026-06-10 | DOC-042 脚本化 TD-032 行数基线扫描 | 🟢 完成 | `scripts/scan-source-sizes` + `--refresh` + 门禁 `source-size-over-limit`；19 pytest passed；ruff 全过；check-engineering-docs 通过。 | [DOC-042](technical-debt.md#doc-042) / [Work Log](work-log.md) / [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143) |
| 2026-06-10 | TD-034 `build_fields_desc` 在 `array + items=[]` 时丢失"成员为object"提示 | 🟢 完成 | 路线 A：`f.get("items")` → `f.get("items") is not None`，保留"成员为object"提示；pytest 50 passed，ruff 全过。 | [TD-034](technical-debt.md#td-034) / [Work Log](work-log.md) / [PR #142](https://github.com/MarkDanile/MetaEduBase/pull/142) |
| 2026-06-10 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | technical-debt 总览表 + 独立任务卡 + Backlog 行翻 Done + work-log 补 PR/commit + 候选区移出。docs-only，4 文件，6 条 `rg` 验收全过。 | [DOC-045](technical-debt.md#doc-045) / [Work Log](work-log.md) / [PR #137](https://github.com/MarkDanile/MetaEduBase/pull/137) |
| 2026-06-10 | TD-030 RecallChannel Protocol vs concrete signature drift 收口（路线 A） | 🟢 完成 | Protocol 增 `session`，3 具体类去下划线前缀，契约测试去 `lstrip` 退路并新增 3 用例。pytest 228 passed。 | [TD-030](technical-debt.md#td-030) / [Work Log](work-log.md) / [PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139) |
| 2026-06-10 | REQ-006 Stage 1.0 → 1.5 → 2 完整交付 | 🟢 完成 | 6 步 e2e 闭环（225 passed），轨道 B / W23 / Backlog 同步 Done。 | [Work Log](work-log.md) / [PR #117](https://github.com/MarkDanile/MetaEduBase/pull/117) / [PR #132](https://github.com/MarkDanile/MetaEduBase/pull/132) |
| 2026-06-10 | TD-037 收口 e2e Redis broker（路线 B） | 🟢 完成 | 建 `tests/e2e/conftest.py`，恢复 Stage 1.0 基线。 | [Work Log](work-log.md) / [PR #130](https://github.com/MarkDanile/MetaEduBase/pull/130) |
| 2026-06-10 | DOC-051 一次性收口 W23 P1 历史 spec/plan 占位 | 🟢 完成 | 12 处占位替换 + 3 plan 链接回填。 | [Work Log](work-log.md) / [PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124) |
| 2026-06-10 | TD-036 / TD-038 修复全新测试库 alembic upgrade head 阻塞 | 🟢 完成 | 修 006 gin ops + init-test-db btree_gin + 防御 check。 | [Work Log](work-log.md) / [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) |
| 2026-06-10 | BUG-001 修正 document retry endpoint Celery dispatch | 🟢 完成 | 去 await + pipeline_version + try/except；3 条新回归。 | [Work Log](work-log.md) / [PR #120](https://github.com/MarkDanile/MetaEduBase/pull/120) |
