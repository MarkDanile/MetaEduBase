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
| （空） | | | | | | |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-056 TD-055 审计：其他 `_run_in_session` task 也可能未返回值 | ⚪ 待澄清 | P1 | 后端 / Celery 任务 / 运维可观测性 | TD-055 修复合片审计发现 `rebuild_document_chunks`（rebuild_chunks.py:173）同样吞返回值。已在 `technical-debt.md` 详情段登记。下一步：grep 全仓 `asyncio.run(_run_in_session(`，每个调用点补 `return`。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-13 | TD-054 chunker `_split_oversized_chunk` 3 off-by-one | 🟢 完成 | PR #253 squash merge `1f8d8a0`：clause_cursor 累加 + 去掉 +1 错位。5 mock pytest 全过；16/16 chunker tests 0 回归。 | [TD-054](technical-debt.md#td-054) / [PR #253](https://github.com/MarkDanile/MetaEduBase/pull/253) |
| 2026-06-13 | BUG-004 cleanup_orphan_chunks 返 rowcount + 清 1178 orphan | 🟢 完成 | PR #251 squash merge `ce23ed2`：3 repo 返 int + CleanupReport + 真 PG 删 1178 → 0 + check_orphans.py 4 表扫描。 | [BUG-004](../01-product-planning/05-requirements/BUG-004-orphan-tasks-after-file-delete.md) / [PR #251](https://github.com/MarkDanile/MetaEduBase/pull/251) |
| 2026-06-13 | TD-053 fallback 合成 section_path | 🟢 完成 | PR #241 squash merge `d9c6a90`：sibling_index 累加。5 mock pytest 全过。 | [TD-053](technical-debt.md#td-053) / [PR #241](https://github.com/MarkDanile/MetaEduBase/pull/241) |
| 2026-06-13 | TD-055 cleanup_orphan_chunks 返 rowcount（1 行修复） | 🟢 完成 | PR #238 squash merge `e9c5223`：asyncio.run → return asyncio.run。4 mock pytest 全过。审计发现 TD-056。 | [TD-055](technical-debt.md#td-055) / [PR #238](https://github.com/MarkDanile/MetaEduBase/pull/238) |
| 2026-06-12 | BUG-003 AI Chat 体验回归（5 修复合片 + 入口 + 6 工作台同步 PR 收口） | 🟢 完成 | 12 PR 全部合 main：fix1~5 修复合片（backend embedding 降级 / layout 100dvh / reference UI / file open 新标签 / IME 兼容）。7 AC 全部覆盖。 | [BUG-003](../01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md) / [PR #219+#221+#223+#225+#227+#229](https://github.com/MarkDanile/MetaEduBase/pulls?q=is%3Apr+is%3Amerged+bug-003) |
| 2026-06-13 | DOC-067 分布式临时编号与正式任务编号归并规则 | 🟢 完成 | PR #248 merged `9bf177b`；正式编号保持短格式，`DRAFT-*` 只作临时来源，并加主表门禁。 | [Technical Debt](technical-debt.md#doc-067) / [PR #248](https://github.com/MarkDanile/MetaEduBase/pull/248) |
| 2026-06-13 | DOC-066 任务池主表插入顺序门禁 | 🟢 完成 | PR #246 merged `4a58906`；新增 `check_task_pool_order`，防止 Backlog / technical-debt 新编号插入历史编号中间。 | [Technical Debt](technical-debt.md#doc-066) / [PR #246](https://github.com/MarkDanile/MetaEduBase/pull/246) |
| 2026-06-13 | DOC-065 规则瘦身、任务池插入规则与开工硬门禁收口 | 🟢 完成 | PR #244 merged `6c31fe5`；规则文件全部 ≤100 行，`task-modes.md` 91 行；补开工三连、禁止绕过门禁、任务池插入规则。 | [Technical Debt](technical-debt.md#doc-065) / [PR #244](https://github.com/MarkDanile/MetaEduBase/pull/244) |
| 2026-06-12 | TD-051 `document_chunks` 结构元数据治理 + 历史数据重建 | 🟢 完成 | PR #234 squash merge `ffccc6c`；7 slice 合 1 PR；AC-1~AC-7 全部覆盖；67 passed，ruff clean。 | [Spec](../02-delivery-plans/01-specs/2026-06-12-td-051-document-chunks-metadata-governance.md) / [Plan](../02-delivery-plans/02-plans/2026-06-12-td-051-document-chunks-metadata-governance-plan.md) / [PR #234](https://github.com/MarkDanile/MetaEduBase/pull/234)（merge `ffccc6c`） |
| 2026-06-12 | TD-052 `check-engineering-docs` 秒级反馈优化 | 🟢 完成 | PR #232 已合并：默认 source size 增量扫，`--full` 保留全量审计，`--timing` 输出耗时；git log 兜底批量化。默认门禁 0.36s。 | [TD-052](technical-debt.md#td-052-check-engineering-docs-秒级反馈优化增量-source-size--批量-git-log--timing) / [PR #232](https://github.com/MarkDanile/MetaEduBase/pull/232)（merge `2d3697c`） |
