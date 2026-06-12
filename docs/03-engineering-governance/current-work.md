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
| TD-051 本机数据重建 + chunk quality 报告 | 🟡 进行中 | P1 | RAG / 数据完整性 / 文档解析 / AI Chat | 已写 `scripts/ai/chunk_quality_report.py`（7+1 指标 + before/after diff）；已采重建前基线（1551 chunks / section_path 100% 空 / char_start 100 个 null / orphan 100）；`cleanup_orphan_chunks` 删 100 orphan；`rebuild_document_chunks` 跑 25 文件全成功。重建后基线：char_start / char_end / orphan 全 0；section_title 325→202（-8%）；section_path 仍未改善（slice 5 fallback bug）+ offset_overlaps 反而 +3%（chunker bug）。技术债总账交付记录已追加。 | push 分支 + 创建 PR → 维护者合 main 后人工补 chain_embed=True + BUG-003 AC-2/AC-3 复测。 | 重建后基线 1562 chunks / 0 回归 / 25 文件 0 失败 / 3 follow-up bug 暴露（待入账 TD-051-FU）。 |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-051-FU 3 follow-up：rebuild fallback section_path + offset overlap + cleanup return | ⚫ 待办 | P1 | RAG / 数据完整性 | 详见 technical-debt.md TD-051 详情段"暴露的 follow-up bug"：① `_reconstruct_sections_from_full_text` fallback 未算 section_path ② 重建后 offset_overlaps +3% ③ `cleanup_orphan_chunks` task 未返回 rowcount。建议入账为 TD-053 跟踪。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-12 | TD-051 `document_chunks` 结构元数据治理 + 历史数据重建 | 🟢 完成 | PR #234 squash merge `ffccc6c`；7 slice 合 1 PR；AC-1~AC-7 全部覆盖；67 passed，ruff clean。 | [Spec](../02-delivery-plans/01-specs/2026-06-12-td-051-document-chunks-metadata-governance.md) / [Plan](../02-delivery-plans/02-plans/2026-06-12-td-051-document-chunks-metadata-governance-plan.md) / [PR #234](https://github.com/MarkDanile/MetaEduBase/pull/234)（merge `ffccc6c`） |
| 2026-06-12 | TD-052 `check-engineering-docs` 秒级反馈优化 | 🟢 完成 | PR #232 已合并：默认 source size 增量扫，`--full` 保留全量审计，`--timing` 输出耗时；git log 兜底批量化。默认门禁 0.36s。 | [TD-052](technical-debt.md#td-052-check-engineering-docs-秒级反馈优化增量-source-size--批量-git-log--timing) / [PR #232](https://github.com/MarkDanile/MetaEduBase/pull/232)（merge `2d3697c`） |
