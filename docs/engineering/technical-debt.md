# 技术债总账

本文件是技术债任务的唯一事实源。记录时保持编号稳定、证据明确，并确保每项任务小到可以执行。

## 维护规则

- 本 Markdown 文件作为主记录载体。后续如果启用 GitHub Issues，仍保留本文件为总账，并在任务中增加 `Issue:` 字段。
- 任务编号一经创建不再重排。新增任务使用下一个 `TD-xxx` 编号。
- 状态值使用：`待办`、`就绪`、`进行中`、`阻塞`、`完成`。
- 任务卡片中的状态统一写成 `状态：颜色 状态名`，例如 `状态：🟡 进行中`。状态名仍是事实源，颜色只用于快速扫视。

状态颜色：

| 状态 | 颜色标记 | 含义 |
|------|----------|------|
| `待办` | ⚫ | 已记录，但尚未准备开工 |
| `就绪` | 🔵 | 完成标准和验证方式齐全，可以开工 |
| `进行中` | 🟡 | 正在处理 |
| `阻塞` | 🔴 | 缺少信息、环境或外部依赖 |
| `完成` | 🟢 | 已验证完成并保留记录 |
- 每次开工前，只将 1 到 3 个任务从 `待办` 改为 `就绪`。
- 任务必须包含 `完成标准` 和 `验证方式`，否则不能进入 `就绪`。
- 任务完成后不要删除记录，将状态改为 `完成`，并在 `备注` 中记录完成日期和相关提交。

## 定期复盘规范

建议每周或每两周进行一次技术债复盘。复盘目标不是一次性解决所有债务，而是持续识别风险、选择少量可执行任务，并验证已完成任务确实降低了后续维护成本。

### 复盘输入

- 本文件中的所有 `待办`、`就绪`、`进行中`、`阻塞` 任务。
- 最近提交、线上/本地报错、测试失败、构建失败、重复修复的问题。
- 新增的大文件、重复逻辑、临时绕过、硬编码配置、未跟踪生成物。

### 复盘流程

1. 更新现状：检查每项 `进行中` 和 `阻塞` 任务是否仍准确。
2. 关闭已完成项：将已验证完成的任务改为 `完成`，并在 `备注` 记录完成日期和提交。
3. 补充新债务：只记录有明确证据的债务，避免把想法或愿望写成任务。
4. 重排优先级：优先处理安全、交付、数据一致性，再处理可维护性和体验。
5. 选择下轮工作：最多将 1 到 3 个任务从 `待办` 改为 `就绪`。
6. 明确验收：确认进入 `就绪` 的任务都有 `完成标准` 和 `验证方式`。

### 复盘输出

- 本文件更新后的任务状态和优先级。
- 下轮要处理的 1 到 3 个 `就绪` 任务。
- 新增任务的证据、完成标准和验证方式。
- 已完成任务的完成日期和相关提交。

### 复盘检查问题

- 是否有 P0 任务连续两次复盘仍未进入 `就绪`？如果有，需要说明原因。
- 是否有 `进行中` 任务超过一次复盘周期没有进展？如果有，改为 `阻塞` 或拆小。
- 是否出现同类问题反复修复？如果有，新增或升级对应技术债。
- 是否有任务缺少证据、完成标准或验证方式？如果有，不能进入 `就绪`。

## 任务模板

```md
### TD-000: 任务标题

状态：⚫ 待办
优先级：P0
领域：安全 / 交付 / 数据一致性 / 前端 / 测试
证据：具体文件、行号、命令输出或可观察现象。
问题：为什么这是技术债。
完成标准：明确的完成条件。
验证方式：验证命令或验收场景。
备注：可选，记录上下文、Issue 链接、完成日期或提交。
```

## 任务清单

### TD-001: 拆分应用启动时的数据库迁移与默认种子数据

状态：🟢 完成
优先级：P0
领域：安全 / 交付
证据：`packages/server-python/app/main.py:22-25` 在应用生命周期中执行 `init_db_with_seed()`。`packages/server-python/app/shared/infrastructure/database.py:40-59` 在 Alembic 失败后回退到 `Base.metadata.create_all`。`packages/server-python/app/shared/infrastructure/seed.py:38-56` 使用 `admin123` 创建默认管理员。
问题：应用启动会直接修改数据库，并可能掩盖迁移失败。默认种子数据也容易让开发账号误入不安全环境。
完成标准：生产应用启动不再自动执行迁移或默认管理员种子写入；开发和测试环境仍有明确、显式、已文档化的初始化方式。
验证方式：启动后端不会触发 Alembic 或 seed 写入；显式开发初始化命令仍能创建 schema 和默认开发管理员；准备好 schema 后健康检查仍能通过。
备注：2026-06-04 按流程开始处理。2026-06-04 完成。实现提交：`291dbbc`。代码侧改动：移除 FastAPI 启动时的隐式迁移和 seed；移除 Alembic 失败后 fallback `create_all` 的初始化路径；新增显式开发初始化入口 `make init-dev-db` 和 `./dev.sh init-db`；默认开发 seed 需要 `ALLOW_DEFAULT_SEED=true` 显式放行；同步 README 和本地开发命令。最终验证：`./dev.sh init-db` 通过；`curl -sf http://localhost:8000/api/v1/health` 返回 `{"status":"ok","version":"0.1.0"}`；`cd packages/server-python && .venv/bin/alembic current` 返回 `9466ea6e5d33 (head)`；`cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_health.py -q` 通过，2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` 通过，83 passed；相关 ruff 通过。

### TD-002: 收敛文件清理的级联删除逻辑

状态：🟢 完成
优先级：P0
领域：数据一致性
证据：`packages/server-python/app/contexts/document/interfaces/api/router.py:265-309` 和 `packages/server-python/app/contexts/document/interfaces/api/router.py:330-380` 都手写 SQL 删除 chunks、knowledge edges、knowledge nodes 和 document tasks。
问题：清理顺序和清理范围重复写在 API handler 中，后续修复很容易只覆盖其中一条路径。
完成标准：文件删除和文件重新初始化共用同一个清理 service 或 repository 函数；API handler 不再重复书写级联 SQL。
验证方式：现有文件删除和重新初始化测试通过；新增或更新一个回归场景，验证文件派生节点关联的 knowledge edges 会先于节点被清理。
备注：2026-06-04 按流程开始处理。2026-06-04 完成。PR #12（https://github.com/MarkDanile/MetaEduBase/pull/12），merge commit `2eb59e8`。改动：KnowledgeNodeRepository 新增 `delete_cascade_by_source_file` 和 `delete_cascade_by_source_dataset`；新建 DocumentTaskRepository（`delete_by_file`、`delete_by_dataset`）；新建 `cleanup_file_derivatives` 和 `cleanup_dataset_derivatives` 清理函数；重构 document router 和 structured_data router 使用共享清理函数；修复 `DELETE /datasets/{dataset_id}` 删 knowledge_nodes 前未删 knowledge_edges 的 bug；新增 3 个回归测试覆盖 edges-before-nodes 清理顺序。验证：`pytest -q` 86 passed；`pytest tests/contexts/document/test_cascade_cleanup.py -v` 3 passed；router 中不再有内联级联 SQL。TD-002-FOLLOWUP：补充 dataset reinitialize 回归测试（4 个回归测试总计）；修正 TD-002 触碰行的 2 个 ruff E501；修正 `current-work.md` 收口状态。

### TD-003: 让前端 lint 质量门禁可运行

状态：🟢 完成
优先级：P0
领域：前端 / 交付
证据：原始问题为 `packages/web/package.json:11` 定义 `lint` 为 `eslint src/`，但 `packages/web/package.json` 没有声明 ESLint 依赖，执行 `pnpm --filter @metaedu/web lint` 会失败并输出 `sh: eslint: command not found`。
问题：仓库声明了 lint 门禁，但实际无法运行，导致本地和 CI 都无法强制执行这类静态检查。
完成标准：前端 lint 能基于明确的 ESLint 配置成功运行，或者该脚本被替换为项目真实采用的质量门禁。
验证方式：`pnpm --filter @metaedu/web lint` 退出码为 0；`pnpm --filter @metaedu/web typecheck` 仍退出码为 0。
备注：2026-06-04 选为流程试跑任务，模式为技术债修复 + 基础设施 / 依赖 / 工具链。2026-06-04 完成。完成提交：`090242a`。验证：`pnpm --filter @metaedu/web lint` 通过，退出码 0，仍有 9 个 warning；`pnpm --filter @metaedu/web typecheck` 通过，退出码 0。

### TD-004: 让后端测试数据库环境可复现

状态：🟢 完成
优先级：P1
领域：测试 / 交付
证据：`packages/server-python/tests/conftest.py:13` 硬编码 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`。当前环境中，`pytest` 收集到 81 个测试，其中 15 个不依赖数据库的测试通过，66 个集成测试在连接本地 PostgreSQL 时失败。
问题：测试执行依赖隐式本地数据库，新环境或 CI 中很难稳定复现。
完成标准：测试数据库 URL 可配置，并通过文档或 dev/test compose profile 提供明确的测试数据库启动方式。
验证方式：全新环境能启动所需测试数据库，并执行 `cd packages/server-python && .venv/bin/python -m pytest -q`，无需猜测手动建库步骤。
备注：2026-06-04 按流程开始处理。2026-06-04 完成。Spec：`docs/specs/2026-06-04-td-004-test-database-reproducibility.md`；Plan：`docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`。改动：新增 `app/shared/infrastructure/test_db_setup.py`（asyncpg 幂等建库 + vector/ltree 扩展 + Alembic upgrade head，含 `_stamp_if_legacy_schema` 兼容遗留环境）；conftest 改读 `TEST_DATABASE_URL` env 并移除 `Base.metadata.create_all`；新增 `./dev.sh init-test-db` 与 `make init-test-db`；同步 local-development、quality-gates、README。验证：`./dev.sh init-test-db` 跑两次均退出码 0；`TEST_DATABASE_URL=... .venv/bin/python -m pytest tests/shared/test_health.py -q` → 2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` → 87 passed in 23.36s；`.venv/bin/python -m ruff check app/ tests/` 退出码 0；7 个文件 `init-test-db|TEST_DATABASE_URL` 落点齐全。PR #23（merge commit `b8b34a6`）。

### TD-013: 收口 TD-004 测试数据库初始化安全与文档占位

状态：🟢 完成
优先级：P1
领域：测试 / 交付 / 安全
证据：`packages/server-python/app/shared/infrastructure/test_db_setup.py:56` 使用 `f'CREATE DATABASE "{url.database}"'` 拼接由 `TEST_DATABASE_URL` 控制的数据库名；`packages/server-python/app/shared/infrastructure/test_db_setup.py:109-122` 只要 `metaedu.tenants` 存在且 `metaedu.alembic_version` 不存在就 `stamp head`；`docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md` 仍有 `<TASK-8 输出>` 和 `PR / merge commit 在 Git 闭环后回填` 等模板占位。
问题：TD-004 已让测试库初始化可复现，但初始化脚本仍有可控 SQL identifier 拼接和过宽 legacy stamp 风险；完成后的 plan 仍残留活动式占位，容易误导后续 agent 判断任务状态。
完成标准：数据库名在 `CREATE DATABASE` 前经过严格校验或安全 quote；legacy stamp 只在确认是旧 `Base.metadata.create_all` 形态时触发，或改为不会掩盖残缺 schema 的实现；补充聚焦测试覆盖数据库名校验和 legacy stamp 判断；TD-004 plan 中不再保留活动式交付占位。
验证方式：新增或更新的后端聚焦测试通过；`cd packages/server-python && .venv/bin/python -m ruff check app/shared/infrastructure/test_db_setup.py tests/` 退出码 0；`rg -n "<TASK|PR / merge commit 在 Git 闭环后回填|以最终回复为准|待最终确认" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md` 不再命中活动式占位。
备注：2026-06-04 Codex 复核 TD-004 后新增。2026-06-05 由 Claude Code 接手完成。改动：新增 `_validate_database_name`（PostgreSQL identifier 白名单）与 `DatabaseNameError` 异常，替换裸 `f-string` 拼接路径；`_stamp_if_legacy_schema` 改为基于 12 张核心业务表集合是否**全部**存在 + 缺 `alembic_version` 才 stamp 的 `_is_legacy_create_all_shape` 判定；新增 `tests/shared/test_test_db_setup.py` 覆盖 6 类合法 / 9 类非法数据库名与 5 类 legacy 形态判定；plan 头部新增「交付历史」段并把 `<TASK-8 输出>` / `PR / merge commit 在 Git 闭环后回填` 等占位替换为真实 PR #23 / merge commit `b8b34a6` / 完成日期 2026-06-04。验证：`pytest tests/shared/test_test_db_setup.py -v` → 20 passed；`ruff check app/shared/infrastructure/test_db_setup.py tests/shared/test_test_db_setup.py` → All checks passed；`ruff check app/ tests/` → All checks passed；`./dev.sh init-test-db` 跑两次均退出码 0；`pytest -q` → 107 passed in 24.76s；plan 占位 `rg` → CLEAN。PR #27（https://github.com/MarkDanile/MetaEduBase/pull/27），merge commit `8f25b20`，完成日期 2026-06-05。

### TD-005: 拆分大型后端任务流水线文件

状态：⚫ 待办
优先级：P1
领域：后端 / 可维护性
证据：`packages/server-python/app/contexts/document/application/tasks.py` 约 924 行，`packages/server-python/app/contexts/structured_data/application/tasks.py` 约 707 行。
问题：解析、抽取、状态更新、知识图谱处理和异常处理集中在大型流程文件中，小改动也容易带来回归风险。
完成标准：至少将最稳定的横切逻辑抽成聚焦的 helper 或 service，例如任务状态更新、prompt 构造、文件派生 KG 清理、解析器分发。
验证方式：现有后端测试通过；对被抽出的稳定单元补充聚焦测试；除重构目标外不改变业务行为。
备注：

### TD-006: 集中 LLM provider 和模型 fallback 策略

状态：⚫ 待办
优先级：P1
领域：后端 / AI
证据：`packages/server-python/app/shared/llm/factory.py:34-77` 定义 provider 优先级和可用性选择；`packages/server-python/app/contexts/template/application/service.py:181-212` 又硬编码 DeepSeek flash 到默认模型的 fallback。
问题：模型和 provider 策略分散在共享 LLM 基础设施与业务 service 中，后续调整容易不一致。
完成标准：模板 AI 生成使用集中化的模型/provider 策略，或使用一个命名明确的共享 helper 表达其快速模型 fallback 行为。
验证方式：模板 AI 生成仍会优先尝试预期的快速模型，并能按预期 fallback；测试或 mock 覆盖 fallback 路径。
备注：

### TD-007: 减少前端请求状态处理重复

状态：⚫ 待办
优先级：P2
领域：前端 / 可维护性
证据：`packages/web/src/main.ts` 注册了 `VueQueryPlugin`，但 `packages/web/src/views/database/DatabaseView.vue:496-652` 等页面仍手动管理大量 loading 状态、错误提示、轮询刷新和 toast 流程。
问题：请求生命周期逻辑在多个视图中重复，loading、刷新、错误处理行为难以保持一致。
完成标准：选择一个高变更页面，优先 `DatabaseView` 或 `FileDetailView`，将重复请求生命周期逻辑迁移到 composable 或 Vue Query 用法中，且不改变用户可见行为。
验证方式：前端 typecheck 和 build 通过；手动验证列表、详情、上传、重试、重新初始化和 tab 刷新流程仍正常。
备注：

### TD-008: 明确从 `liquid-*` 类到语义 UI 层的迁移路径

状态：⚫ 待办
优先级：P2
领域：前端 / 设计系统
证据：`packages/web/src/assets/css/main.css` 的组件层仍以 `liquid-*` 类为中心，而 `docs/superpowers/plans/2026-05-22-frontend-ui-foundation-redesign.md` 提出了语义化 `ui-*` workspace 层。
问题：设计系统处于过渡状态，后续页面可能混用旧类和新约定，导致风格治理成本上升。
完成标准：补充一份简短的设计系统迁移说明，明确何时使用 `liquid-*`、何时使用 `ui-*`，以及第一个迁移页面或组件族。
验证方式：迁移说明被本总账或 README 链接；至少一个代表性页面遵循选定约定。
备注：

### TD-009: 减少前后端契约漂移

状态：⚫ 待办
优先级：P2
领域：API / 类型
证据：`packages/shared` 中存在 Zod schemas 和共享 TypeScript 类型，但前端 service DTO 与后端 Pydantic DTO 仍主要各自维护。
问题：模板字段、结构化抽取结果、任务状态等复杂契约容易在前后端之间漂移。
完成标准：选择一个高价值契约族，优先模板字段或任务状态，建立明确的共享来源或 schema 检查流程。
验证方式：typecheck 通过；所选契约族出现字段不匹配时，能被测试、生成类型或 schema 校验捕获。
备注：契约治理规则见 `docs/engineering/rules/contracts.md`。

### TD-010: 治理生成物 `outputs/` 对工作区的污染

状态：⚫ 待办
优先级：P2
领域：交付 / 仓库卫生
证据：`git status --short` 显示未跟踪的 `outputs/`。`find outputs -type f | wc -l` 曾报告 413 个文件。
问题：生成物污染仓库状态和搜索结果，会让真实代码变更更难检查。
完成标准：项目明确 `outputs/` 应该被忽略、移动，还是作为特定 artifact 工作流被有选择地跟踪。
验证方式：正常本地工作后，`git status --short` 不再出现意外生成物噪音。
备注：

### TD-011: 治理前端 lint warning

状态：🟢 完成
优先级：P1
领域：前端 / 安全 / 交付
证据：`pnpm --filter @metaedu/web lint` 退出码为 0，但仍报告 9 个 warning，包含 `vue/no-v-html`、`vue/no-template-shadow` 和少量 Vue 模板换行提示。
问题：lint 门禁虽然可运行，但 warning 中包含潜在 XSS 风险提示和模板可维护性问题。长期保留 warning 会削弱 lint 输出的信号质量。
完成标准：`pnpm --filter @metaedu/web lint` 退出码为 0 且 warning 数为 0；不通过关闭核心安全规则来掩盖 `v-html` 风险。
验证方式：`pnpm --filter @metaedu/web lint` 通过且无 warning；`pnpm --filter @metaedu/web typecheck` 通过。
备注：2026-06-04 从 TD-003 收尾风险中拆出并开始处理。2026-06-04 完成。完成提交：`090242a`。验证：`pnpm --filter @metaedu/web lint` 通过，退出码 0，无 warning；`pnpm --filter @metaedu/web typecheck` 通过，退出码 0。处理范围：静态 SVG `v-html` 改为 lucide 组件；AI Markdown 渲染改为阻断原始 HTML、危险链接和图片的受控边界；修复模板变量遮蔽和换行提示。

### TD-012: 治理后端全量 ruff 质量门禁

状态：🟢 完成
优先级：P1
领域：后端 / 测试 / 交付
证据：2026-06-04 合并前验证执行 `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/`，报告 162 个历史 lint 问题，覆盖 `app/celery_app.py`、`app/contexts/document/application/tasks.py`、`app/contexts/template/interfaces/api/router.py`、`tests/conftest.py` 等文件。
问题：`packages/server-python/Makefile` 中的 `make lint` 不能作为稳定后端质量门禁运行，后续提交容易把历史 lint 噪音和新增问题混在一起。
完成标准：后端全量 ruff 门禁可运行并退出码为 0，或者仓库明确收敛规则范围并文档化暂缓项。
验证方式：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码为 0；若同步治理 mypy，则补充 `cd packages/server-python && .venv/bin/mypy app/`。
备注：2026-06-04 按流程开始处理。2026-06-04 完成。PR #17（merge commit `a4dcb2a`）。改动：spec 落盘到 `docs/superpowers/specs/2026-06-04-ruff-quality-gate-design.md`；plan 落盘到 `docs/superpowers/plans/2026-06-04-ruff-quality-gate.md`；自动修复 3 个 I001 + 1 个 F401（chat.py）；手工修复 107 E501（22 个文件）+ 17 B008（Annotated 迁移）+ 2 SIM105 + 1 B007 + 1 B905 + 1 E741 + 1 N806 + 1 SIM117 + 1 UP046 + 10 F401 noqa（celery task 注册）+ 2 I001 重排；`match_prompt` 中 `\\n → \n` 回归已修复（LLM prompt 字符串）。验证：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0；`cd packages/server-python && .venv/bin/python -m pytest -q` 87 passed（含 87 个测试 baseline 与 TD-002-FOLLOWUP 一致）。Celery 10 个 task 仍正确注册。`Repository[T](ABC)` PEP 695 语法被 `app.contexts.knowledge.domain.repositories` 消费并 import 成功。
