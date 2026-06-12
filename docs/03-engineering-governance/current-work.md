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

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| （空） | | | | |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-12 | REQ-012 RAG 多路召回与知识图谱证据链收口 | 🟢 完成 | PR #216 已合并：接入 vector + keyword chunk 复合召回、metadata filter 生效、graph 回源 chunk、`document_sources`、当前消息 `[N]` 点击和文档级来源 UI。 | [Requirement](../01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md) / [Plan](../02-delivery-plans/02-plans/2026-06-12-req-012-rag-retrieval-document-sources-plan.md) / [PR #216](https://github.com/MarkDanile/MetaEduBase/pull/216)（merge `5c5ad81`） |
| 2026-06-12 | DOC-059 新建 `check_task_completion_pr_consistency_fallback` 兜底脚本扫『任务卡完成 → PR 真实存在』 | 🟢 完成 | 2 PR 收口（PR-A 业务脚本 + PR-B docs-only）：git log 兜底扫『任务卡完成但无 PR 字段』；14 个 task_id 维度 KNOWN_ISSUES 白名单；25 pytest 零回归。 | [DOC-059](technical-debt.md#doc-059) / PR #214（merge `e29497e`） |
| 2026-06-12 | DOC-064 pre-existing 警告收口（`check-engineering-docs` 退出码 1 → 0） | 🟢 完成 | 1 docs-only PR（#211 / merge `e6f9ea9`）：2 类修复——① current-work.md L37-L41 五条"最近完成"行重写为 ≤ 220 字符（短摘要 + work-log 回链）；② spec 路径 `../../../` → `../../` 修对层级。0.77 秒 + 退出码 **0** + 22 pytest passed 零回归。 | [DOC-064](technical-debt.md#doc-064) / PR #211（merge `e6f9ea9`） |
| 2026-06-12 | DOC-057 历史"验证通过声明缺可复核证据"格式收口（technical-debt 总账版） | 🟢 完成 | 1 PR（#204 / merge `f1a8bd0`）：修复要求在 main 上已自然满足（历史任务合 main 时补齐了 `gh pr view` / `退出码 0` 命中），本轮按任务卡交付项收口：技术债总账 L148 翻 🟢 + L1948 任务卡补 PR 链接 + work-log 索引行追加。`git diff --check` clean；0 业务代码变更；`gh pr view 204` state=MERGED。 | [DOC-057](technical-debt.md#doc-057) / PR #204（merge `f1a8bd0`） |
| 2026-06-12 | DOC-058 显式加"任务分支未合 main 不得翻 🟢 完成；`gh pr view <PR>` state 必须为 MERGED"规则 | 🟢 完成 | 1 PR（#202 / merge `8b0ceb8`）：3 个规则文件（workbench + git-workflow + quality-gates）追加硬规则段。`scripts/check-engineering-docs` 退出码 0（本任务新增 0 警告）；20 pytest passed 零回归；`git diff --check` clean；0 业务代码 / 0 测试代码 / 0 脚本变更。 | [DOC-058](technical-debt.md#doc-058) / PR #202（merge `8b0ceb8`） |
| 2026-06-12 | TD-049 `tests/conftest.py` `sys.path.insert` 块导致 8 E402 pre-existing | 🟢 完成 | 新建 `tests/_paths.py` 持有 sys.path 副作用；`tests/conftest.py` 改为 `from tests._paths import _REPO_ROOT`，ruff E402 + I001 全消除。`pytest tests/engineering/test_evidence_coverage_report.py -v` 4 passed；mock-based 子集 219 passed。 | [TD-049](technical-debt.md#td-049) / PR #200（merge `cfad2b4`） |
| 2026-06-11 | TD-048 `SourceItem` 旧字段下个迭代删除（契约 deprecation 窗口） | 🟢 完成 | 3 切片 3 PR（#196 docs-only 修事实源 / #197 业务代码 / #198 跨事实源收口）。mock-based pytest 47 passed 零回归；ruff 8 个 TD-049 pre-existing 兼容；DOC-057 pre-existing validation-claim 提示由独立 PR 收口。 | [TD-048](technical-debt.md#td-048) / PR #196 + #197 |
| 2026-06-11 | TD-050 `EvidenceItem` 缺 `source_chunk_id` 字段 / spec 与实现错位（路线 A2） | 🟢 完成 | 3 切片 3 PR 收口：PR-1 docs-only 同步（#193） + PR-2 业务代码 + pytest（#194，4 业务文件 + 2 pytest 文件 / 10 新 pytest） + PR-3 docs-only 跨事实源收口（本 PR）。全量 pytest 336 passed + 1 skipped 零回归；ruff 8 个 TD-049 pre-existing 兼容；Recall Protocol 形参不变。 | [TD-050](technical-debt.md#td-050-evidenceitem-缺-source_chunk_id-字段--spec-与实现错位) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through-plan.md) / PR #193 + #194 |
| 2026-06-11 | TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector） | 🟢 完成 | 6 切片 5 commit 收口：zhparser + chinese_zh + plainto_tsquery；dev 库 70/252 file_only → chunk_resolved（总覆盖率 74.95% → 81.91%，+6.96 pct）；runtime 镜像增量 23MB。 | [TD-047](technical-debt.md#td-047-中文分词回填-iliike-限制p1-数据债衍生) / [Spec](../02-delivery-plans/01-specs/2026-06-11-td-047-zhparser-chinese-tsvector.md) / [Plan](../02-delivery-plans/02-plans/2026-06-11-td-047-zhparser-chinese-tsvector-plan.md) |
| 2026-06-11 | DOC-060 针对全部评审评分做阶段复盘 | 🟢 完成 | 基于 40 条评分记录完成阶段复盘：平均分 84.8，一次关闭率 60%，返工率 40%，流程扣分率约 63%；结论是 Harness 已有价值，但需求类 AC、真实数据验证和多事实源收口仍是重点。 | [Retrospective](04-retrospectives/2026-06-11-review-score-retrospective.md) / [Review Score Log](04-retrospectives/review-score-log.md) |
| 2026-06-11 | DOC-059 点名任务入口解析门禁与最近完成固定裁剪规则 | 🟢 完成 | 新增 `task-modes.md#任务入口解析门禁`，明确 Backlog / Requirement / Milestone / TD 点名任务进入实现前必须先定位事实源并登记工作台；最近完成区超过 20 行时固定裁到最新 12 行。 | [Task Modes](task-modes.md#任务入口解析门禁) / [Workbench](01-rules/workbench.md#保留策略) / [Workflow](workflow.md#开发前检查) |
| 2026-06-11 | TD-046 P1 RAG 数据债批次（3 个 backfill 真跑） | 🟢 完成 | 真 PG 跑通 3 个 backfill (node-source-chunk 754/1006, file-metadata 25/25, chunk-embedding 100/100)。P1 RAG 基线 4 指标全部提升，详见 TD-046。0 业务代码改动。[PR #187](https://github.com/MarkDanile/MetaEduBase/pull/187) | [TD-046](technical-debt.md#td-046) |
