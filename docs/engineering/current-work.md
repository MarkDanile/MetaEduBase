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

- `当前进行中`：保留所有正在开发、阻塞或待验证任务。
- `下一批候选任务`：最多保留 1 到 3 个近期候选；完整 backlog 回到对应总账或 plan。
- `最近完成`：最多保留最近 5 个完成任务，或最近 2 周内仍需要交接上下文的完成任务。
- 超出范围的完成任务应归档到对应事实源，并在 `docs/engineering/work-log.md` 保留一行索引。
- 任务卡片只写交接所需摘要；详细设计、实施步骤、长复盘和大段验证输出分别放到 spec、plan、技术债总账、PR 描述或复盘文档。

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

### TD-004: 让后端测试数据库环境可复现

状态：🟡 进行中
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
- 已完成：spec 落盘并通过 self-review；plan 落盘并通过 self-review；任务卡片登记；分支创建
- 正在处理：实施 Plan Task 1-7
- 未完成：端到端验证、状态收尾、Git 闭环

下一步：
1. 按 plan 推进 Task 1-7
2. 执行 Task 8 端到端验证
3. 按用户要求推进 Git 闭环

验证状态：
- 已运行：
- 未运行：完整 pytest，将在 Task 8 执行
- 当前失败：

交接备注：
- 行为变化：测试 schema 由 conftest 内的 `Base.metadata.create_all` 改为前置 `init-test-db`（Alembic upgrade head）；未跑 init-test-db 的环境会显式失败而非隐式建表。这不是「零业务逻辑变更」，按 `docs/engineering/rules/quality-gates.md#行为变化声明检查` 在 PR 描述与最终回复中显式声明。

## 下一批候选任务

当前无候选任务。

## 最近完成

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

### TD-012: 治理后端全量 ruff 质量门禁

状态：🟢 完成
类型：技术债
领域：Backend / Testing / Delivery
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-012-ruff-quality-gate`

需求来源：
- Spec: `docs/superpowers/specs/2026-06-04-ruff-quality-gate-design.md`
- Plan: `docs/superpowers/plans/2026-06-04-ruff-quality-gate.md`
- 技术债：`docs/engineering/technical-debt.md#td-012-治理后端全量-ruff-质量门禁`
- 架构约束：`docs/engineering/rules/quality-gates.md`，`docs/engineering/rules/git-workflow.md`

当前进展：
- 已完成：spec 落盘并通过 self-review 与用户复核；plan 落盘并通过 self-review；按 plan 推进 Task 1（自动修复层 + celery_app.py docstring 改写）、Task 2（E501 折行 22 个文件）、Task 3（B008 Annotated 迁移 17 处）、Task 4（其它规则 + 10 F401 noqa + 2 I001 重排）；`match_prompt` 的 `\\n → \n` 回归已修复；Task 5 端到端验证通过；状态同步。
- 正在处理：
- 未完成：

下一步：
1. 后续由 Codex 复核并决定是否需要 TD-012-FOLLOWUP。

验证状态：
- 已运行：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0；`cd packages/server-python && .venv/bin/python -m pytest -q` 87 passed；Celery 10 task 注册正常。
- 未运行：
- 当前失败：无。

交接备注：
- PR #17（merge commit `a4dcb2a`）；完成日期 2026-06-04。

### TD-002-FOLLOWUP: 收口 TD-002 流程与测试遗留

状态：🟢 完成
类型：技术债 / 修复 / 文档
领域：Data Integrity / Backend / Docs / Delivery
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`fix/td-002-followup`

需求来源：
- 技术债：`docs/engineering/technical-debt.md#td-002-收敛文件清理的级联删除逻辑`
- 架构约束：`docs/engineering/rules/data-integrity.md`，`docs/engineering/rules/git-workflow.md`

当前进展：
- 已完成：补充 `test_reinitialize_dataset_cleans_knowledge_edges_before_nodes` 回归测试（4 个 cascade cleanup 测试总计）；修正 TD-002 触碰行的 2 个 ruff E501；修正 `current-work.md` 和 `technical-debt.md` 收口状态；强化 `git-workflow.md` 和 `workflow.md` 提交前阅读要求。PR #13 squash merge 到 `main`，merge commit `ea34271`。

验证状态：
- 已运行：`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_cascade_cleanup.py -v` 通过，4 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` 通过，87 passed；`cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/interfaces/api/router.py app/contexts/structured_data/interfaces/api/router.py` ruff 仍有 1 个历史 E501，属于 TD-012；TD-002/FOLLOWUP 触碰行未新增 ruff 问题。
- 未运行：
- 当前失败：无。

交接备注：
- PR #13：https://github.com/MarkDanile/MetaEduBase/pull/13；merge commit `ea34271`；完成日期：2026-06-04。
