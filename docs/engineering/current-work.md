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
- 提交前不得保留与事实不符的占位，例如 `验证状态：未运行`、`下一步：提交变更` 或过期的 `🟡 进行中`。

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

- `TD-004`：让后端测试数据库环境可复现。详见 `docs/engineering/technical-debt.md`。
- `TD-012`：治理后端全量 ruff 质量门禁。详见 `docs/engineering/technical-debt.md`。

## 最近完成

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
- 已按 `docs/engineering/rules/git-workflow.md` 回读并执行完整 Git 闭环；PR 和 merge commit 以最终交付回复为准。

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

### TD-002: 收敛文件清理的级联删除逻辑

状态：🟢 完成
类型：技术债
领域：Data Integrity / Backend
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-002-converge-cascade-delete`

需求来源：
- 技术债：`docs/engineering/technical-debt.md#td-002-收敛文件清理的级联删除逻辑`
- 架构约束：`docs/engineering/rules/data-integrity.md`

当前进展：
- 已完成：KnowledgeNodeRepository 新增 `delete_cascade_by_source_file` 和 `delete_cascade_by_source_dataset`；新建 DocumentTaskRepository；新建 `cleanup_file_derivatives` 和 `cleanup_dataset_derivatives` 清理函数；重构 document router 和 structured_data router；修复 `DELETE /datasets/{dataset_id}` 删 nodes 前未删 edges 的 bug；新增 3 个回归测试。PR #12 squash merge 到 `main`，merge commit `2eb59e8`。

验证状态：
- 已运行：`cd packages/server-python && .venv/bin/python -m pytest -q` 通过，86 passed；`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_cascade_cleanup.py -v` 通过，3 passed；router 中不再有内联级联 SQL；`cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/interfaces/api/router.py app/contexts/structured_data/interfaces/api/router.py` ruff 仍有 1 个历史 E501，属于 TD-012；TD-002/FOLLOWUP 触碰行未新增 ruff 问题。
- 未运行：
- 当前失败：无。

交接备注：
- PR #12：https://github.com/MarkDanile/MetaEduBase/pull/12；merge commit `2eb59e8`；完成日期：2026-06-04。

### TD-001: 拆分应用启动时的数据库迁移与默认种子数据

状态：🟢 完成
类型：技术债 / 基础设施
领域：Backend / Security / Delivery
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex/technical-debt-flow`

需求来源：
- Spec:
- Plan:
- 技术债：`docs/engineering/technical-debt.md#td-001-拆分应用启动时的数据库迁移与默认种子数据`
- 架构约束：
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`，`docs/engineering/task-modes.md#基础设施--依赖--工具链`

当前进展：
- 已完成：移除 FastAPI 启动生命周期中的隐式迁移和 seed；移除 Alembic 失败后 fallback `create_all` 的初始化路径；新增显式开发初始化入口 `make init-dev-db` 和 `./dev.sh init-db`；默认开发 seed 需要 `ALLOW_DEFAULT_SEED=true` 显式放行；同步 README 和本地开发命令；补充无数据库启动健康检查和 seed opt-in 测试；完成 PostgreSQL 可用后的显式初始化、迁移状态、健康检查和后端完整测试验证。
- 正在处理：
- 未完成：

下一步：
1. 后续处理测试环境可复现问题时进入 `TD-004`。

验证状态：
- 已运行：`./dev.sh init-db` 通过；`curl -sf http://localhost:8000/api/v1/health` 返回 `{"status":"ok","version":"0.1.0"}`；`cd packages/server-python && .venv/bin/alembic current` 返回 `9466ea6e5d33 (head)`；`cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_health.py -q` 通过，2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` 通过，83 passed；`cd packages/server-python && .venv/bin/python -m ruff check app/config.py app/main.py app/shared/infrastructure/database.py app/shared/infrastructure/seed.py app/shared/infrastructure/dev_setup.py tests/shared/test_health.py tests/shared/test_dev_seed.py` 通过。
- 未运行：
- 当前失败：无。

交接备注：
- 完成日期：2026-06-04；实现提交：`291dbbc`；最终验证结果见本任务卡片。

### TD-011: 治理前端 lint warning

状态：🟢 完成
类型：技术债 / 基础设施
领域：Frontend / Security / Testing / Delivery
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex/technical-debt-flow`

需求来源：
- Spec:
- Plan:
- 技术债：`docs/engineering/technical-debt.md#td-011-治理前端-lint-warning`
- 架构约束：
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`，`docs/engineering/task-modes.md#基础设施--依赖--工具链`

当前进展：
- 已完成：将首页和资源列表的静态 SVG 字符串渲染替换为 lucide 组件；将 AI 回复 Markdown 渲染收敛为阻断原始 HTML、危险链接和图片的受控边界；修复 RouterView 插槽变量遮蔽；清理 Vue 模板换行 warning。
- 正在处理：
- 未完成：

下一步：
1. 后续新增 Markdown / 富文本渲染时继续遵守 `docs/engineering/rules/security.md#xss-防护`。

验证状态：
- 已运行：`pnpm --filter @metaedu/web lint` 通过，退出码 0，无 warning；`pnpm --filter @metaedu/web typecheck` 通过，退出码 0。
- 未运行：
- 当前失败：无。

交接备注：
- 本任务从 TD-003 收尾风险中拆出；完成日期：2026-06-04；完成提交：`090242a`。

### TD-003: 让前端 lint 质量门禁可运行

状态：🟢 完成
类型：技术债 / 基础设施
领域：Frontend / Testing / Delivery
当前执行模式：plan-do
最近接手工具：Codex
分支：`codex/technical-debt-flow`

需求来源：
- Spec:
- Plan:
- 技术债：`docs/engineering/technical-debt.md#td-003-让前端-lint-质量门禁可运行`
- 架构约束：
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`，`docs/engineering/task-modes.md#基础设施--依赖--工具链`

当前进展：
- 已完成：补齐前端 ESLint 依赖与 flat config；将 lint 脚本收敛到 `src/**/*.{ts,vue}`；清理阻塞 lint 的 8 个 error；同步质量门禁文档。
- 正在处理：
- 未完成：

下一步：
1. lint warning 已拆为 TD-011。

验证状态：
- 已运行：`pnpm --filter @metaedu/web lint` 通过，退出码 0，仍有 9 个 warning；`pnpm --filter @metaedu/web typecheck` 通过，退出码 0。
- 未运行：
- 当前失败：无。

交接备注：
- 采用补齐 ESLint 依赖/配置的策略；历史 warning 拆为 TD-011 继续治理；完成提交：`090242a`。

### DOC-001: 统一并优化跨 AI 工程规则

状态：🟢 完成
类型：文档 / 工程规范
领域：Docs
当前执行模式：manual
最近接手工具：Codex
分支：`codex/technical-debt-flow`

需求来源：
- Spec:
- Plan:
- 技术债：`TD-009`
- 架构约束：`ARCHITECTURE.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md`

当前进展：
- 已完成：统一 AGENTS.md / CLAUDE.md 入口索引；补充质量门禁、契约治理、跨 AI 工作流、技术债复盘规范和任务模式检查表；拆分 Git 流程与本地开发命令；新增插件无关的 `docs/specs` / `docs/plans` 目录规则；为 `.claude/rules` 保留兼容跳转入口。
- 正在处理：
- 未完成：

下一步：
1. 后续进入具体功能或技术债处理时，从本文件新增对应任务卡片。
2. 本地启动或调试时阅读 `docs/engineering/rules/local-development.md`；提交和 PR 时阅读 `docs/engineering/rules/git-workflow.md`。
3. 处理 API / DTO / shared schema 变更时，先阅读 `docs/engineering/rules/contracts.md`。

验证状态：
- 已运行：`rg` 检查旧规则路径、旧测试数量、旧文件名、新增规则索引、任务模式索引、superpower 兼容引用和 `docs/specs` / `docs/plans` 默认目录约定。
- 未运行：业务代码测试，原因是本次仅修改工程规范文档。
- 当前失败：无。

交接备注：
- `docs/engineering/*` 是共享规则事实源；工具私有目录只保留跳转入口；完成提交：`c0bac8a`。
