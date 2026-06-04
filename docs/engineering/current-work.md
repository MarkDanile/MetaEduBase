# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/engineering/task-modes.md`。

## 使用规则

- 任何正在开发、准备开发、阻塞或刚完成的任务都应在这里有一张任务卡片。
- 很小的即时修复或纯问答可以不新增任务卡片，但如果涉及跨文件开发、状态交接、计划执行或后续接力，必须登记。
- 任务卡片只记录当前状态和交接信息，详细需求和实施步骤放在对应 spec、plan 或技术债文档中。
- 新任务的长期 spec 默认放在 `docs/specs/*`，长期 plan 默认放在 `docs/plans/*`；`docs/superpowers/*` 仅作为历史或插件兼容来源。
- 每次开始开发前，先和用户确认本次要执行的任务卡片，以及需要读取的全套文档。
- 每次结束开发前，必须更新任务状态、当前进展、下一步和验证结果。
- 本文件是活文档，不是一次性日志。代码、验证或 Git 阶段发生变化后，必须回写任务卡片。
- 进入 Git 提交前，必须最后一次回读本文件，确认状态、验证结果和下一步与实际一致。
- 完整 Git 闭环结束后，任务卡片不得保留“以最终回复为准”“提交后更新”“待最终确认”等交付占位；PR、merge commit 和完成日期必须回填到仓库文档事实源。
- 本文件是交接工作台，不是历史档案。只保留当前任务、近期候选和少量最近完成任务；历史索引见 `docs/engineering/work-log.md`。
- 插件只作为执行工具使用；任务状态以本文件为准。
- 复核、测试、PR review 或交接中发现的未解决问题，如果不会在当前任务内立即修复，必须登记到对应事实源，例如 `technical-debt.md`、bug 任务或后续 plan；需要近期接手的，再加入“下一批候选任务”。

## 状态流

- `⚪ 待澄清`：目标或范围还不清楚，不能进入实施。
- `⚫ 待计划`：需求清楚，但缺少实施计划。
- `🔵 就绪`：计划、约束、验收标准齐全，可以开发。
- `🟡 进行中`：正在开发。
- `🔴 阻塞`：缺少信息、环境或外部依赖。
- `🟣 待验证`：代码已完成，等待测试或人工验收。
- `🟢 完成`：已验证完成，并记录提交或交付说明。

任务卡片中的状态统一写成 `状态：颜色 状态名`，例如 `状态：🟡 进行中`。状态名仍是事实源，颜色只用于快速扫视。

状态同步规则：

- 开工时可以写 `状态：🟡 进行中`，并记录计划验证项和当前分支。
- 代码完成但验证未完成时，状态应为 `🟣 待验证`，验证状态不得写成已通过。
- 验证通过后，如果仍未完成用户要求的 Git 阶段，状态可以保持任务活跃，但下一步必须写清当前停留阶段。
- 只有完成标准、验证结果和用户要求的交付阶段都已收口，才能写 `状态：🟢 完成`。
- 提交前不得保留与事实不符的占位，例如 `验证状态：未运行`、`下一步：提交变更`、过期的 `🟡 进行中` 或 `PR / merge commit 以最终回复为准`。

## 保留策略

- `当前进行中`：只保留正在开发、阻塞、待验证或正在走 Git 闭环的任务；一个 agent 默认只持有 1 个当前任务。
- `下一批候选任务`：最多保留 1 到 3 个近期候选；完整 backlog 回到对应总账或 plan。
- `最近完成`：最多保留最近 5 个完成任务，或最近 2 周内仍需要交接上下文的完成任务。
- 超出范围的完成任务应归档到对应事实源，并在 `docs/engineering/work-log.md` 保留一行索引。
- 任务卡片只写交接所需摘要；详细设计、实施步骤、长复盘和大段验证输出分别放到 spec、plan、技术债总账、PR 描述或复盘文档。

## 区域选择策略

`当前进行中` 是正在占用协作注意力的工作台，不是排期列表。任务满足以下任一条件时才放入本区：

- 已经开始改代码、改文档、跑验证或走 Git 闭环。
- 已经由用户指定为本轮要处理的任务。
- 当前被阻塞、待验证或等待人工验收，但后续仍要继续接手。

从“下一批候选任务”开工时，必须把任务移动到“当前进行中”，状态改为 `🟡 进行中`，并写清当前执行模式、最近接手工具、分支和验证计划。任务完成后，必须移出“当前进行中”，进入“最近完成”或归档到对应事实源。

`下一批候选任务` 是近期接力池，不是完整 backlog。候选任务可以由 AI 在复核、测试失败、PR review 或技术债复盘中提出，但进入本区前必须满足以下条件：

- 已经在对应事实源登记，例如 `technical-debt.md`、spec、plan 或 bug 任务。
- 有明确证据、完成标准和验证方式。
- 用户已明确选择，或该任务是当前任务直接拆出的近期 follow-up。
- 不超过 1 到 3 个候选；超过上限时，只保留风险最高或最需要接力的任务。

未达到这些条件的问题只登记到对应总账，不放入本文件；否则本文件会退化成第二个 backlog。

## 任务卡片模板

```md
### FEAT-000: 任务标题

状态：⚫ 待计划
类型：功能 / 修复 / 技术债 / 重构 / 调研 / 基础设施 / 数据迁移 / 发布 / 文档
领域：Frontend / Backend / API / Data Integrity / Security / Testing / Delivery / AI / Docs
当前执行模式：plan-do / superpower / compound-engineering / manual
最近接手工具：Codex / Claude Code / Other
分支：

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：
- 插件输出：
- 任务模式：

当前进展：
- 已完成：
- 正在处理：
- 未完成：

下一步：
1.
2.

验证状态：
- 已运行：真实执行的命令 + 结果；退出码非 0 不得写“通过”
- 未运行：未运行的命令和原因；验证完成后不得保留占位
- 当前失败：失败摘要；若属于历史问题，绑定对应 TD-xxx

交接备注：
-
```

验证命令选择参见 `docs/engineering/rules/quality-gates.md`。

## 当前进行中

当前无正在执行的任务。

## 下一批候选任务

### DOC-006: 修复 current-work 重复完成区标题

状态：🔵 就绪
类型：文档 / 工程规范
领域：Docs / Delivery
当前执行模式：plan-do
最近接手工具：Codex 复核后登记，待 Claude Code 接手
分支：

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：`docs/engineering/current-work.md`，`docs/engineering/workflow.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#通用收尾回查`

当前进展：
- 已完成：Codex 复核 TD-013 后发现 `docs/engineering/current-work.md` 出现两个 `## 最近完成` 标题。
- 正在处理：
- 未完成：等待 Claude Code 接手修复。

下一步：
1. 删除重复的 `## 最近完成` 标题，只保留一个最近完成区。
2. 确认 TD-013、DOC-005、TD-004 等完成任务仍位于同一个最近完成区，且 current-work 区域顺序保持为“当前进行中 / 下一批候选任务 / 最近完成”。

验证状态：
- 已运行：仅完成任务登记，未修改业务代码。
- 未运行：`rg -n "^## 当前进行中|^## 下一批候选任务|^## 最近完成" docs/engineering/current-work.md`，原因是本轮只形成 follow-up 任务。
- 当前失败：无。

交接备注：
- 本任务是 TD-013 复核后拆出的文档结构修复，不应混入业务代码或其他技术债。

## 最近完成

### TD-014: 加强测试数据库 legacy stamp 的列级形态校验

状态：🟢 完成
类型：技术债 / follow-up
领域：Testing / Delivery / Data Integrity
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-014-test-db-legacy-column-shape`

需求来源：
- Spec:
- Plan: `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`
- 技术债：`docs/engineering/technical-debt.md#td-014-加强测试数据库-legacy-stamp-的列级形态校验`
- 架构约束：`docs/engineering/rules/local-development.md`，`docs/engineering/rules/quality-gates.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`

当前进展：
- 已完成：新增 `_LEGACY_REQUIRED_COLUMNS`（`tenants` / `users` 的代表列清单）与 `_has_legacy_create_all_columns` 纯函数；收紧 `_stamp_if_legacy_schema` 为「表集合齐全 + INSERT 目标表关键列齐全 + 缺 alembic_version」三件齐备才 stamp；新增 7 个聚焦测试覆盖列级判定；完成完整 Git 闭环并回填交付事实。
- 正在处理：
- 未完成：

下一步：
1.

验证状态：
- 已运行：`pytest tests/shared/test_test_db_setup.py -v` → 27 passed（TD-013 20 + TD-014 7）；`ruff check app/shared/infrastructure/test_db_setup.py tests/shared/test_test_db_setup.py` → All checks passed；`ruff check app/ tests/` → All checks passed；`./dev.sh init-test-db` 退出码 0；`pytest -q` → 114 passed in 23.49s。
- 未运行：
- 当前失败：无。

交接备注：
- 行为变化（非「零业务逻辑变更」）：legacy stamp 新增 `information_schema.columns` 查询；「表齐全 + 列缺失」分支不再 stamp + 显式日志；新增 `_has_legacy_create_all_columns` 私有 helper。详细行为变化与覆盖矩阵见 PR #28 描述。
- PR #28（https://github.com/MarkDanile/MetaEduBase/pull/28）；merge commit `af7d246`；完成日期：2026-06-05。

### TD-013: 收口 TD-004 测试数据库初始化安全与文档占位

状态：🟢 完成
类型：技术债 / follow-up
领域：Testing / Delivery / Security
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-013-test-db-init-safety`

需求来源：
- Spec:
- Plan: `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`
- 技术债：`docs/engineering/technical-debt.md#td-013-收口-td-004-测试数据库初始化安全与文档占位`
- 架构约束：`docs/engineering/rules/local-development.md`，`docs/engineering/rules/quality-gates.md`，`docs/engineering/rules/security.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`

当前进展：
- 已完成：新增 `_validate_database_name` 白名单校验与 `DatabaseNameError` 异常；收窄 `_stamp_if_legacy_schema` 为「旧 conftest `create_all` 形态核心表全集 + 缺 alembic_version」；新增 20 个聚焦测试覆盖校验和 legacy 判定；清理 TD-004 plan 中 `<TASK-8 输出>` / `PR / merge commit 在 Git 闭环后回填` 等活动式占位，plan 头部补「交付历史」段；完成完整 Git 闭环并回填交付事实。
- 正在处理：
- 未完成：

下一步：
1.

验证状态：
- 已运行：`pytest tests/shared/test_test_db_setup.py -v` → 20 passed；`ruff check app/shared/infrastructure/test_db_setup.py tests/shared/test_test_db_setup.py` → All checks passed；`ruff check app/ tests/` → All checks passed；`./dev.sh init-test-db` 跑两次均退出码 0；`pytest -q` → 107 passed in 24.76s；`rg -n "<TASK|PR / merge commit 在 Git 闭环后回填|以最终回复为准|待最终确认" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md` → CLEAN。
- 未运行：
- 当前失败：无。

交接备注：
- 行为变化（非「零业务逻辑变更」）：脚本拒绝带特殊字符的数据库名（抛 `DatabaseNameError`）；legacy stamp 仅在 12 张核心业务表全在 + 缺版本时触发；plan 文档清理为非代码改动。详细行为变化与覆盖矩阵见 PR #27 描述。
- PR #27（https://github.com/MarkDanile/MetaEduBase/pull/27）；merge commit `8f25b20`；完成日期：2026-06-05。

## 最近完成

### DOC-005: 补强复核入账与候选任务选择策略

状态：🟢 完成
类型：文档 / 工程规范
领域：Docs / Delivery / Testing
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex-docs-review-intake-policy`

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：`docs/engineering/current-work.md`，`docs/engineering/workflow.md`，`docs/engineering/rules/quality-gates.md`，`docs/engineering/rules/git-workflow.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#通用收尾回查`

当前进展：
- 已完成：新增 TD-013 follow-up 任务；补强复核发现入账、三账一致、候选任务选择和当前进行中区域边界规则；完成完整 Git 闭环并回填交付事实。
- 正在处理：
- 未完成：

下一步：
1. 后续让 Claude Code 按新规范接手 TD-013，并由 Codex 复核流程执行情况。

验证状态：
- 已运行：`git diff --check` 退出码 0；`rg -n "DOC-005|TD-013|复核发现|三账一致|区域选择策略|下一批候选任务|当前进行中|PR / merge commit|以最终回复为准|待最终确认" docs/engineering/current-work.md docs/engineering/technical-debt.md docs/engineering/workflow.md docs/engineering/rules/quality-gates.md docs/engineering/rules/git-workflow.md` 命中预期规则和任务落点；`git diff --name-status` 确认范围仅为 5 个工程规范 / 任务文档；`gh pr view 25 --json state,mergeCommit,url,headRefName,baseRefName` 确认 PR #25 已合并，merge commit `7a4241c`。
- 未运行：业务代码测试，原因是本次仅修改工程规范和任务登记文档。
- 当前失败：无。

交接备注：
- 本任务回应 TD-004 / TD-012 复核中暴露的 follow-up 入账、候选任务选择和提交前三账一致问题。
- PR #25（https://github.com/MarkDanile/MetaEduBase/pull/25）；merge commit `7a4241c`；完成日期：2026-06-04。

### TD-004: 让后端测试数据库环境可复现

状态：🟢 完成
类型：技术债 / 基础设施
领域：Testing / Delivery
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-004-test-db-reproducibility`

需求来源：
- Spec: `docs/specs/2026-06-04-td-004-test-database-reproducibility.md`
- Plan: `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`
- 技术债：`docs/engineering/technical-debt.md#td-004-让后端测试数据库环境可复现`
- 架构约束：`docs/engineering/rules/local-development.md`，`docs/engineering/rules/quality-gates.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`

当前进展：
- 已完成：spec / plan 落盘；新增 `app/shared/infrastructure/test_db_setup.py`（asyncpg 幂等建库 + 扩展 + Alembic upgrade head + 旧 schema stamp 兼容分支）；conftest 改读 `TEST_DATABASE_URL` env 并移除 `Base.metadata.create_all`；新增 `./dev.sh init-test-db` 与 `make init-test-db`；同步 local-development、quality-gates、README；端到端验证通过。
- 正在处理：
- 未完成：

下一步：
1.

验证状态：
- 已运行：`./dev.sh init-test-db` 跑两次均退出码 0；`TEST_DATABASE_URL=postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test .venv/bin/python -m pytest tests/shared/test_health.py -q` → 2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` → 87 passed in 23.36s（与 TD-012 baseline 一致）；`.venv/bin/python -m ruff check app/ tests/` → All checks passed (exit 0)；`rg -n "init-test-db|TEST_DATABASE_URL" docs/engineering/rules/{local-development,quality-gates}.md README.md packages/server-python/Makefile packages/server-python/tests/conftest.py packages/server-python/app/shared/infrastructure/test_db_setup.py dev.sh` 7 个文件全部命中。
- 未运行：
- 当前失败：无。

交接备注：
- 行为变化（非「零业务逻辑变更」，已按 `docs/engineering/rules/quality-gates.md#行为变化声明检查` 显式声明）：测试 schema 由 conftest 内 `Base.metadata.create_all` 改为前置 `init-test-db`（Alembic upgrade head）；未跑 init-test-db 的环境会显式失败而非隐式建表。默认 URL 与现状一致，conftest 仍执行 `CREATE SCHEMA IF NOT EXISTS metaedu` 与 `TRUNCATE templates`。
- 实施踩坑：旧测试库有「业务表已建好但 alembic_version 缺失」遗留状态，模块加入 `_stamp_if_legacy_schema` 自愈分支；`make_url(...)` 的 `str()` 会 mask 密码为 `***`，alembic 必须接原始连接串。spec / plan 已回写。
- PR #23（https://github.com/MarkDanile/MetaEduBase/pull/23）；merge commit `b8b34a6`；完成日期：2026-06-04。

### DOC-004: 优化完整 Git 提交流程与合并后回填规则

状态：🟢 完成
类型：文档 / 工程规范
领域：Docs / Delivery
当前执行模式：plan-do
最近接手工具：Codex
分支：

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：`docs/engineering/rules/git-workflow.md`，`docs/engineering/workflow.md`，`docs/engineering/task-modes.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#通用收尾回查`

当前进展：
- 已完成：新增完整 Git 交付快速通道；明确合并后不得保留交付占位，必须回填 PR、merge commit 和完成日期；把中间汇报收敛为关键阶段。
- 正在处理：
- 未完成：

下一步：
1. 后续按快速通道执行小型文档或低风险回填提交。

验证状态：
- 已运行：`git diff --check`；`rg` 检查“快速通道”“合并后回填”“最终回复为准”等规则落点。
- 未运行：业务代码测试，原因是本次仅修改工程规范文档。
- 当前失败：无。

交接备注：
- 本任务回应 DOC-003 合并后回填遗漏和完整提交流程偏慢的问题。

### DOC-003: 补强跨插件计划、行为声明和 PR 范围边界规则

状态：🟢 完成
类型：文档 / 工程规范
领域：Docs / Delivery / Testing
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex-current-work-process-hardening`

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：`docs/engineering/workflow.md`，`docs/engineering/task-modes.md`，`docs/engineering/rules/quality-gates.md`，`docs/engineering/rules/git-workflow.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#通用收尾回查`

当前进展：
- 已完成：补强 superpower / compound-engineering-plugin 输出迁移或镜像到 `docs/specs/*` / `docs/plans/*` 的硬规则；补强 current-work 区域同步检查；补充“零业务逻辑变更”行为变化信号检查；补充 PR 范围边界检查，防止技术债 PR 混入无关资产清理；同步 AGENTS.md / CLAUDE.md 入口提醒；按保留策略收敛最近完成区。
- 正在处理：
- 未完成：

下一步：
1. 后续让 Claude Code 按新规范处理下一个技术债，并由 Codex 复核流程执行情况。

验证状态：
- 已运行：`git diff --check` 通过；`rg -n "迁入|迁移|镜像|docs/specs|docs/plans|插件输出|区域同步|当前进行中|下一批候选任务|最近完成|零业务逻辑|仅格式化|仅 lint|行为变化|PR 范围|范围边界|无关资产|mockup PNG|outputs/" AGENTS.md CLAUDE.md docs/engineering/current-work.md docs/engineering/work-log.md docs/engineering/workflow.md docs/engineering/task-modes.md docs/engineering/rules/docs.md docs/engineering/rules/git-workflow.md docs/engineering/rules/quality-gates.md docs/specs/README.md docs/plans/README.md` 确认 4 条规则有入口、流程、门禁和 Git 落点；`rg -n "^## 当前进行中|^## 下一批候选任务|^## 最近完成|^### " docs/engineering/current-work.md` 确认区域同步和最近完成区数量符合保留策略；`git status --short --branch` 确认本次范围仅包含工程规范和入口文档。
- 未运行：业务代码测试，原因是本次仅修改工程规范文档。
- 当前失败：无。

交接备注：
- 本任务回应 TD-012 复核后识别出的跨插件计划位置、current-work 动态同步、行为声明和 PR 范围边界四类流程缺口。
- PR #20（https://github.com/MarkDanile/MetaEduBase/pull/20）；merge commit `3b883ea`；完成日期：2026-06-04。

### DOC-002: 强化跨 AI 提交前回查与验证声明规范

状态：🟢 完成
类型：文档 / 工程规范
领域：Docs / Delivery / Testing
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex-pre-submit-verification-rules`

需求来源：
- Spec:
- Plan:
- 技术债：
- 架构约束：`docs/engineering/workflow.md`，`docs/engineering/rules/git-workflow.md`，`docs/engineering/rules/quality-gates.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#通用收尾回查`

当前进展：
- 已完成：将 Claude Code 在 TD-002 / TD-002-FOLLOWUP 中暴露的状态回写、覆盖矩阵和验证表述问题沉淀为硬检查；补强 `current-work.md` 活文档规则、`workflow.md` 最终声明回查、`quality-gates.md` 覆盖矩阵和验证表述规范、`git-workflow.md` 提交前回读规则、`task-modes.md` 通用收尾回查。
- 正在处理：
- 未完成：

下一步：
1. 后续让 Claude Code 按新规范处理下一个技术债，并由 Codex 复核流程执行情况。

验证状态：
- 已运行：`git diff --check` 通过；`rg -n "活文档|最终声明回查|覆盖矩阵|验证表述规范|git add|退出码非 0|历史失败|验证后最终同步" docs/engineering/current-work.md docs/engineering/workflow.md docs/engineering/rules/quality-gates.md docs/engineering/rules/git-workflow.md docs/engineering/task-modes.md` 确认新增规则落点。
- 未运行：业务代码测试，原因是本次仅修改工程规范文档。
- 当前失败：无。

交接备注：
- 已按 `docs/engineering/rules/git-workflow.md` 回读并执行完整 Git 闭环；PR #16（https://github.com/MarkDanile/MetaEduBase/pull/16）；merge commit `f438307`；完成日期：2026-06-04。
