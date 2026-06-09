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
| REQ-006 P1 知识资产处理链路最终演示验收 | 🟡 进行中 | P1 | Product / Document / AI / Testing | Stage 1.0 收口：`feat/req-006-stage-1-e2e` 分支已建 `tests/e2e/test_p1_demo.py` 3 步 e2e 脚本（`test_p1_demo_step1_upload` / `step2_parse` / `step2b_parse_idempotent` 共 3 passed）+ UI 演示手册骨架（`req-006-p1-final-demo-ui.md` 6 步截图位 + 4 主题验收降级）。Stage 1 探查发现 2 个新债：TD-036 `metaedu_test.document_tasks.updated_at` 缺失（alembic 003 漂移，e2e 自带 `ALTER TABLE IF NOT EXISTS` 兜底）；TD-037 e2e 沙箱无 Redis 时需 mock `chunk_document.delay` + patch `broker_url=memory://`。 | Stage 1.5：接入 `extract_template` / KG / RAG / sources 渲染（AC-3 ~ AC-6 字段层）；Stage 1.5 收口后 Stage 2 翻 `🟢 Done`：轨道 B / W23 / Backlog / current-work / work-log 文档回填。 | `pytest tests/e2e/test_p1_demo.py -q` 3 passed；`ruff check tests/e2e/test_p1_demo.py` All checks passed!；`ruff check app/ tests/` All checks passed!；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0 |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-037 e2e 沙箱无 Redis broker 适配 | ⚫ 候选 | P3 | Backend / 测试 / 基础设施 | 选路线 A（独立 e2e Celery app fixture with `memory://` broker）或路线 B（`init-test-db` 启 dev Redis），把 `chunk_document.delay` 等 mock 集中到 `mock_pipeline_chain` fixture；CI 端补 `e2e-real` 标记；详情见 [TD-037](../03-engineering-governance/technical-debt.md#td-037)。 |
| DOC-052 清理 `scripts/engineering/checks/_common.py` 中 `KNOWN_ISSUES` 残留的 TD-023 历史白名单 | ⚫ 候选 | P3 | Docs / Governance | TD-023 任务已结案（PR 未配置 CI / 本地门禁已通过）；其 `KNOWN_ISSUES` 4 条白名单（`td-020-*` plan 2 条 + `td-020-*` spec 1 条 + `td-023` 1 条）已无拦截价值，长期保留会掩盖新漂移；逐条评估能否删除；删除后跑 `scripts/check-engineering-docs` 退出码 0。 |
| DOC-054 收口 review-score-log PR 字段与倒排顺序一致性 | ⚫ 候选 | P2 | Docs / Governance / Review | 修正 `review-score-log.md`：DOC-049 行 `本 PR` → PR #113；按"最新评审置顶"重新整理同日登记顺序；同步 Metrics Snapshot 计数（当前表已超过 7 条）；运行 `scripts/check-engineering-docs` + `git diff --check`。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时再批量归档最旧记录，建议一次性压回 12 到 15 行左右；不要每完成一个任务就做单条搬运。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-09 | DOC-051 一次性收口 W23 P1 历史 spec/plan 占位 | 🟢 完成 | 12 处占位一次性替换（3 spec `TD-???` → `TD-030（已锁定）`+ 2 `未回填` → 具体失败条件；3 plan commit / PR 链接回填到 `337238b` / `2e6d097`+`d8e9bcb` / `29fa1d0`+`54a0a1c`+`c236216`=`PR #79` `302ec2d`）；W23 迭代卡 PG 行 + `quality-gates.md` 占位扫描候选阻塞解除。 | [Work Log](work-log.md) / [PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124) (`d7a2ca7`) |
| 2026-06-09 | TD-036 / TD-038 修复全新测试库 `alembic upgrade head` 卡在 006 的根因 | 🟢 完成 | 修 006 `gin` ops + `init-test-db` 加 `btree_gin` + `_ensure_critical_columns` 防御 check。`DROP DATABASE metaedu_test && init-test-db` 一次到 head。 | [Work Log](work-log.md) / [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) (`2780ff1`) |
| 2026-06-09 | BUG-001 修正 document retry endpoint 的 Celery dispatch 语义 | 🟢 完成 | 修 `POST /files/{file_id}/retry` 三处缺陷（去 `await`、补 `pipeline_version`、加 `try/except` 兜 broker 抖动），3 条新回归用例，`pytest tests/ -q` 222 passed。 | [Work Log](work-log.md) / [PR #120](https://github.com/MarkDanile/MetaEduBase/pull/120) (`c24f3e9`) |
| 2026-06-09 | DOC-053 补齐高频流程启动语入口 | 🟢 完成 | 在 `task-modes.md#常见启动语` 增补评审、完整 Git 闭环、复盘、阶段收口、APP 应用塑形和只登记不实现等短启动语；保持入口文件只导航、不复制长规则。 | [Task Modes](task-modes.md#常见启动语) / [Work Log](work-log.md) |
| 2026-06-09 | DOC-050 优化 current-work 最近完成窗口与评分总账排序 | 🟢 完成 | 最近完成窗口从 5 行改为 20 行，超过后批量归档到 12-15 行；评分总账明确最新评审置顶；文档门禁脚本和测试同步。 | [Work Log](work-log.md) / [Workbench](01-rules/workbench.md#保留策略) / [Review Score Log](04-retrospectives/review-score-log.md) |
| 2026-06-09 | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁 | 🟢 完成 | `ruff check --fix` 自动修 1 个 I001 + 3 个 SIM300（assertion 顺序翻转 + 1 行多余空行）；pytest 11 passed 不变；ruff app/ tests/ 全过。 | [TD-035 Delivery Record](technical-debt.md#td-035) |
| 2026-06-09 | DOC-049 收口结构化抽取完成态占位与验证声明漂移 | 🟢 完成 | 修正 REQ-005 spec AC-8 浅拷贝口径 / AC-10 失败条件 / `TD-???` → TD-034；plan 提交占位 TBD 补 `4773741` / 11 条用例真实计数；评估把完成态占位扫描以候选形式登记到 `quality-gates.md#脚本门禁候选清单`（推迟）。0 业务代码改动。 | [Backlog](../01-product-planning/04-backlog.md) / [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Quality Gates](01-rules/quality-gates.md#脚本门禁候选清单) |
| 2026-06-09 | REQ-005 结构化抽取嵌套结构稳定性验收 | 🟢 完成 | 为 `extract_template_prompts` 补 11 条 object / array / table 嵌套回归用例；锁定 `build_fields_desc` 嵌套描述 / `try_parse` 嵌套 JSON 与 think 剥离 / `_merge_template_structured_data` 浅拷贝契约；轨道 B 翻结论。0 业务代码改动。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md) |
| 2026-06-09 | BUG-002 修复登录后主面板外边距巨大、内容显示容器过小 | 🟢 完成 | 移除 `ui-page-shell` 的 `max-width: 1120px; margin: 0 auto`，保留 width/padding/background；消除与各 View 自带 max-w 嵌套冲突。`pnpm typecheck / lint / build` 退出 0；`check-engineering-docs` passed。 | [Work Log](work-log.md) / [Backlog](../01-product-planning/04-backlog.md) / [PR #107](https://github.com/MarkDanile/MetaEduBase/pull/107) (`76fe2d2`) |
| 2026-06-09 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | 弱化 TD-033 任务卡 4 处"零 CSS 字节变化 / build output identical"过强声明；6 处事实源补 `PR #103` / `25ca165` 追踪；显式登记 TD-033 未建 spec / plan 的处置方式（事后不补建）。docs-only，`check-engineering-docs` 退出码 0。 | [Work Log](work-log.md) / [TD-033 Delivery Record](technical-debt.md#td-033) / [PR #106](https://github.com/MarkDanile/MetaEduBase/pull/106) |
| 2026-06-09 | DOC-048 增加评审高分质量校准规则 | 🟢 完成 | 最近 5 条评审平均分 >92 时，阶段复盘必须抽查评分是否偏宽；发现问题需在评分总账标记并登记 follow-up。 | [Review Scorecard](01-rules/review-scorecard.md#高分质量校准) / [Retrospectives](04-retrospectives/README.md) |
| 2026-06-09 | DOC-047 建立评审评分总账与落盘规则 | 🟢 完成 | 新增评审评分总账，回填 TD-033 评分 81；复杂评审后必须把总分、follow-up、流程扣分点和规则改进结论落盘。 | [Review Score Log](04-retrospectives/review-score-log.md) / [Review Scorecard](01-rules/review-scorecard.md) |
