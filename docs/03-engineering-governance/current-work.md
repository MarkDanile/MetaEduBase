# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；详细规则见 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| TD-034 `build_fields_desc` 在 `array + items=[]` 时丢失"成员为object"提示 | 🟡 进行中 | P3 | 后端 / LLM 抽取 / 可维护性 | 代码修复完成（路线 A），11 测试通过 + ruff + check-engineering-docs | 更新文档 → commit → push → PR | `pytest tests/contexts/document/ -q` 50 passed；ruff 全过 |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时再批量归档最旧记录，建议一次性压回 12 到 15 行左右；不要每完成一个任务就做单条搬运。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-10 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | technical-debt 总览表 + 独立任务卡 + Backlog 行翻 Done + work-log 补 PR/commit + 候选区移出。docs-only，4 文件，6 条 `rg` 验收全过。 | [DOC-045](technical-debt.md#doc-045) / [Work Log](work-log.md) / [PR #137](https://github.com/MarkDanile/MetaEduBase/pull/137) |
| 2026-06-10 | TD-030 RecallChannel Protocol vs concrete signature drift 收口（路线 A） | 🟢 完成 | Protocol 增 `session`，3 具体类去下划线前缀，契约测试去 `lstrip` 退路并新增 3 用例。pytest 228 passed（+3），ruff 干净。 | [TD-030](technical-debt.md#td-030) / [Work Log](work-log.md) / [PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139) |
| 2026-06-10 | REQ-006 🟢 Done（Stage 1.0 → 1.5 → 2 完整交付） | 🟢 完成 | 6 步 e2e 闭环（225 passed），轨道 B / W23 / Backlog 同步 Done。 | [Work Log](work-log.md) / [PR #117](https://github.com/MarkDanile/MetaEduBase/pull/117) / [PR #132](https://github.com/MarkDanile/MetaEduBase/pull/132) |
| 2026-06-10 | TD-037 收口 e2e Redis broker（路线 B） | 🟢 完成 | 建 `tests/e2e/conftest.py`，恢复 Stage 1.0 基线。 | [Work Log](work-log.md) / [PR #130](https://github.com/MarkDanile/MetaEduBase/pull/130) |
| 2026-06-09 | DOC-051 一次性收口 W23 P1 历史 spec/plan 占位 | 🟢 完成 | 12 处占位替换 + 3 plan 链接回填，W23 迭代卡 PG 行更新，占位扫描候选解除。 | [Work Log](work-log.md) / [PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124) |
| 2026-06-09 | TD-036 / TD-038 修复全新测试库 alembic upgrade head 阻塞 | 🟢 完成 | 修 006 gin ops + init-test-db btree_gin + _ensure_critical_columns 防御 check。 | [Work Log](work-log.md) / [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) |
| 2026-06-09 | DOC-052 清理 KNOWN_ISSUES TD-023 历史白名单 | 🟢 完成 | 删 4 条白名单；脚本验证删除前后 active=0 known=0 门禁一致。 | [Work Log](work-log.md) / [PR #128](https://github.com/MarkDanile/MetaEduBase/pull/128) |
| 2026-06-09 | BUG-001 修正 document retry endpoint Celery dispatch | 🟢 完成 | 去 await + pipeline_version + try/except；3 条新回归用例。 | [Work Log](work-log.md) / [PR #120](https://github.com/MarkDanile/MetaEduBase/pull/120) |
| 2026-06-09 | DOC-054 收口 review-score-log PR / 倒排 / Metrics | 🟢 完成 | DOC-049 行 本 PR → PR #113；Score Log 10 条倒排；Metrics 全量重算（10 / 82.6 / 40% / 60% / 100% / 90%）。 | [Work Log](work-log.md) / [PR #126](https://github.com/MarkDanile/MetaEduBase/pull/126) |
| 2026-06-09 | DOC-053 补齐高频流程启动语入口 | 🟢 完成 | `task-modes.md#常见启动语` 增补评审 / Git 闭环 / 复盘 / 阶段收口等短启动语。 | [Work Log](work-log.md) |
| 2026-06-09 | DOC-050 优化 current-work 最近完成窗口与评分总账排序 | 🟢 完成 | 窗口 5→20 行；评分总账最新评审置顶；门禁脚本同步。 | [Work Log](work-log.md) |
| 2026-06-09 | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁 | 🟢 完成 | `ruff check --fix` 修 1 I001 + 3 SIM300；pytest 11 passed 不变；`ruff check app/ tests/` 退出码 0。 | [TD-035](technical-debt.md#td-035) |
| 2026-06-09 | DOC-049 收口结构化抽取完成态占位与验证声明漂移 | 🟢 完成 | 修正 AC-8 浅拷贝 / AC-10 失败条件 / TD-???；plan TBD 回填；候选门禁登记。 | [Backlog](../01-product-planning/04-backlog.md) |
| 2026-06-09 | REQ-005 结构化抽取嵌套结构稳定性验收 | 🟢 完成 | 11 条对象/数组/表格嵌套回归；轨道 B 翻结论。0 业务代码改动。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) |
