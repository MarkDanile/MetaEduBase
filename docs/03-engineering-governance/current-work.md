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
| DOC-066 任务池主表插入顺序门禁 | 🟡 进行中 | P2 | 文档 / 工程脚本 / 任务池 | 分支 `docs/doc-066-task-pool-insertion-gate`；已补规则、`check_task_pool_order` 门禁和 2 条回归测试。 | 推进 Git 闭环；PR merged 后回填完成状态。 | 已运行：`packages/server-python/.venv/bin/python -m pytest tests/engineering/test_check_engineering_docs.py -q` exit 0；`scripts/check-engineering-docs --timing` exit 0；`ruff check ...` exit 0；`git diff --check` exit 0。 |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-054 重建后 offset_overlaps 反而 +3% | ⚪ 待澄清 | P1 | RAG / 数据完整性 / 文档解析 | 已在 `technical-debt.md` 详情段登记。下一步：先判断是设计性 neighbor overlap 还是 off-by-one bug——看 `chunker.py` 顶部注释和 `_enforce_size_limit` 实现。 |
| TD-056 TD-055 审计：其他 `_run_in_session` task 也可能未返回值 | ⚪ 待澄清 | P1 | 后端 / Celery 任务 / 运维可观测性 | TD-055 修复合片审计发现 `rebuild_document_chunks`（rebuild_chunks.py:173）同样吞返回值。已在 `technical-debt.md` 详情段登记。下一步：grep 全仓 `asyncio.run(_run_in_session(`，每个调用点补 `return`。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-13 | DOC-065 规则瘦身、任务池插入规则与开工硬门禁收口 | 🟢 完成 | PR #244 merged `6c31fe5`；规则文件全部 ≤100 行，`task-modes.md` 91 行；补开工三连、禁止绕过门禁、任务池插入规则。 | [Technical Debt](technical-debt.md#doc-065) / [PR #244](https://github.com/MarkDanile/MetaEduBase/pull/244) |
| 2026-06-12 | TD-051 `document_chunks` 结构元数据治理 + 历史数据重建 | 🟢 完成 | PR #234 squash merge `ffccc6c`；7 slice 合 1 PR；AC-1~AC-7 全部覆盖；67 passed，ruff clean。 | [Spec](../02-delivery-plans/01-specs/2026-06-12-td-051-document-chunks-metadata-governance.md) / [Plan](../02-delivery-plans/02-plans/2026-06-12-td-051-document-chunks-metadata-governance-plan.md) / [PR #234](https://github.com/MarkDanile/MetaEduBase/pull/234)（merge `ffccc6c`） |
| 2026-06-12 | TD-052 `check-engineering-docs` 秒级反馈优化 | 🟢 完成 | PR #232 已合并：默认 source size 增量扫，`--full` 保留全量审计，`--timing` 输出耗时；git log 兜底批量化。默认门禁 0.36s。 | [TD-052](technical-debt.md#td-052-check-engineering-docs-秒级反馈优化增量-source-size--批量-git-log--timing) / [PR #232](https://github.com/MarkDanile/MetaEduBase/pull/232)（merge `2d3697c`） |
