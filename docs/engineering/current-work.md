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
- 已运行：
- 未运行：
- 当前失败：

交接备注：
-
```

验证命令选择参见 `docs/engineering/rules/quality-gates.md`。

## 当前进行中

### TD-001: 拆分应用启动时的数据库迁移与默认种子数据

状态：🟣 待验证
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
- 已完成：移除 FastAPI 启动生命周期中的隐式迁移和 seed；移除 Alembic 失败后 fallback `create_all` 的初始化路径；新增显式开发初始化入口 `make init-dev-db` 和 `./dev.sh init-db`；默认开发 seed 需要 `ALLOW_DEFAULT_SEED=true` 显式放行；同步 README 和本地开发命令；补充无数据库启动健康检查和 seed opt-in 测试。
- 正在处理：
- 未完成：待本机 PostgreSQL 可用后验证 `make init-dev-db` 或 `./dev.sh init-db` 的完整迁移 + seed 成功路径。

下一步：
1. 启动 PostgreSQL / Docker 基础设施。
2. 运行 `./dev.sh init-db` 或 `cd packages/server-python && make init-dev-db`。
3. 再运行需要数据库的后端测试或至少 `tests/shared/test_health.py::test_health_check`。

验证状态：
- 已运行：`cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_health.py::test_health_check_without_database_initialization tests/shared/test_dev_seed.py -q` 通过；`cd packages/server-python && .venv/bin/python -m ruff check app/config.py app/main.py app/shared/infrastructure/database.py app/shared/infrastructure/seed.py app/shared/infrastructure/dev_setup.py tests/shared/test_health.py tests/shared/test_dev_seed.py` 通过；`cd packages/server-python && .venv/bin/python -m pytest --collect-only -q` 收集 83 个测试；导入检查输出 `MetaEduBase`。
- 未运行：完整 `make test` 和实际 `make init-dev-db` 成功路径，原因是本机 `localhost:5432` 没有 PostgreSQL 监听。
- 当前失败：`python -m app.shared.infrastructure.dev_setup` 在本机数据库不可用时失败，错误为 `Connect call failed ('127.0.0.1', 5432)`；对应环境可复现问题已由 `TD-004` 跟踪。

交接备注：
- 代码侧改动已完成；当前只等待本地数据库环境做最终验收。

## 下一批候选任务

- `TD-002`：收敛文件清理的级联删除逻辑。详见 `docs/engineering/technical-debt.md`。

## 最近完成

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
- 本任务从 TD-003 收尾风险中拆出；完成日期：2026-06-04。

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
- 采用补齐 ESLint 依赖/配置的策略；历史 warning 不在 TD-003 中扩大治理。

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
- `docs/engineering/*` 是共享规则事实源；工具私有目录只保留跳转入口。
