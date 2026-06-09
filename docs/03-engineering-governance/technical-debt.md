# 技术债总账

本文件是技术债任务的唯一事实源。记录时保持编号稳定、证据明确，并确保每项任务小到可以执行。

## 维护规则

- 本 Markdown 文件作为主记录载体。后续如果启用 GitHub Issues，仍保留本文件为总账，并在任务中增加 `Issue:` 字段。
- 任务编号一经创建不再重排。新增任务使用下一个 `TD-xxx` 编号。
- 状态值使用：`待办`、`就绪`、`进行中`、`阻塞`、`完成`。
- 任务卡片中的状态统一写成 `状态：颜色 状态名`，例如 `状态：🟡 进行中`。状态名仍是事实源，颜色只用于快速扫视。
- 每次开工前，只将 1 到 3 个任务从 `待办` 改为 `就绪`。
- 任务必须包含 `完成标准` 和 `验证方式`，否则不能进入 `就绪`。
- 低风险、单点技术债可以直接以本文件任务卡片为实施依据；跨 3 个以上文件、涉及 API / Schema / 数据一致性 / 安全 / 前端行为的技术债，开工前应补充对应 spec / plan 到 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`。
- 任务完成后不要删除记录，将状态改为 `完成`，并在 `交付记录` 中记录完成日期、PR / commit 和验证摘要。
- 任务详情只保留可执行和可复盘摘要；长交付细节放到 PR、spec、plan、矩阵文档或 `docs/03-engineering-governance/work-log.md`。

状态颜色：

| 状态 | 颜色标记 | 含义 |
|------|----------|------|
| `待办` | ⚫ | 已记录，但尚未准备开工 |
| `就绪` | 🔵 | 完成标准和验证方式齐全，可以开工 |
| `进行中` | 🟡 | 正在处理 |
| `阻塞` | 🔴 | 缺少信息、环境或外部依赖 |
| `完成` | 🟢 | 已验证完成并保留记录 |

## 定期复盘规范

建议每周或每两周进行一次技术债复盘。复盘目标不是一次性解决所有债务，而是持续识别风险、选择少量可执行任务，并验证已完成任务确实降低了后续维护成本。

### 复盘输入

- 本文件中的所有 `待办`、`就绪`、`进行中`、`阻塞` 任务。
- 最近提交、线上/本地报错、测试失败、构建失败、重复修复的问题。
- 新增的大文件、重复逻辑、临时绕过、硬编码配置、未跟踪生成物。

### 复盘流程

1. 更新现状：检查每项 `进行中` 和 `阻塞` 任务是否仍准确。
2. 关闭已完成项：将已验证完成的任务改为 `完成`，并在 `交付记录` 记录完成日期和提交。
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

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 领域 | 安全 / 交付 / 数据一致性 / 前端 / 测试 |
| 事实源 | Spec / Plan / PR / Issue，可选 |

**证据**
- 具体文件、行号、命令输出或可观察现象。

**问题**
- 为什么这是技术债。

**完成标准**
- 明确的完成条件。

**验证方式**
- 验证命令或验收场景。

**交付记录**
- 未完成，或记录完成日期、PR / commit、验证摘要。
```

## 任务总览

| 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
|------|------|------|--------|------|--------|
| TD-001 | 拆分应用启动时的数据库迁移与默认种子数据 | 🟢 完成 | P0 | 安全 / 交付 | `291dbbc` |
| TD-002 | 收敛文件清理的级联删除逻辑 | 🟢 完成 | P0 | 数据一致性 | [PR #12](https://github.com/MarkDanile/MetaEduBase/pull/12) |
| TD-003 | 让前端 lint 质量门禁可运行 | 🟢 完成 | P0 | 前端 / 交付 | `090242a` |
| TD-004 | 让后端测试数据库环境可复现 | 🟢 完成 | P1 | 测试 / 交付 | [PR #23](https://github.com/MarkDanile/MetaEduBase/pull/23) |
| TD-005 | 拆分大型后端任务流水线文件 | 🟢 完成 | P1 | 后端 / 可维护性 | [PR #34](https://github.com/MarkDanile/MetaEduBase/pull/34) |
| TD-006 | 集中 LLM provider 和模型 fallback 策略 | 🟢 完成 | P1 | 后端 / AI | [PR #35](https://github.com/MarkDanile/MetaEduBase/pull/35) |
| TD-007 | 减少前端请求状态处理重复 | 🟢 完成 | P2 | 前端 / 可维护性 | [PR #36](https://github.com/MarkDanile/MetaEduBase/pull/36) |
| TD-008 | 明确从 `liquid-*` 类到语义 UI 层的迁移路径 | 🟢 完成 | P2 | 前端 / 设计系统 | [PR #53](https://github.com/MarkDanile/MetaEduBase/pull/53) |
| TD-009 | 减少前后端契约漂移 | 🟢 完成 | P2 | API / 类型 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-009-structured-data-contract.md) / [Plan](../02-delivery-plans/02-plans/2026-06-05-td-009-structured-data-contract-plan.md) |
| TD-010 | 治理生成物 `outputs/` 对工作区的污染 | 🟢 完成 | P2 | 交付 / 仓库卫生 | `outputs/` 已删除 |
| TD-011 | 治理前端 lint warning | 🟢 完成 | P1 | 前端 / 安全 / 交付 | `090242a` |
| TD-012 | 治理后端全量 ruff 质量门禁 | 🟢 完成 | P1 | 后端 / 测试 / 交付 | [PR #17](https://github.com/MarkDanile/MetaEduBase/pull/17) |
| TD-013 | 收口 TD-004 测试数据库初始化安全与文档占位 | 🟢 完成 | P1 | 测试 / 交付 / 安全 | [PR #27](https://github.com/MarkDanile/MetaEduBase/pull/27) |
| TD-014 | 加强测试数据库 legacy stamp 的列级形态校验 | 🟢 完成 | P1 | 测试 / 交付 / 数据一致性 | [PR #28](https://github.com/MarkDanile/MetaEduBase/pull/28) |
| TD-015 | 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归 | 🟢 完成 | P1 | 前端 / API / 可维护性 | [PR #38](https://github.com/MarkDanile/MetaEduBase/pull/38) |
| TD-016 | 收敛 knowledge ai_router 的 LLM provider 选择重复逻辑 | 🟢 完成 | P1 | 后端 / AI / 可维护性 | [PR #39](https://github.com/MarkDanile/MetaEduBase/pull/39) |
| TD-017 | 将 Vue Query 请求生命周期治理推广到 FileDetailView | 🟢 完成 | P2 | 前端 / 可维护性 | [PR #40](https://github.com/MarkDanile/MetaEduBase/pull/40) |
| TD-018 | FileDetailView 剩余手写 load 迁到 Vue Query | 🟢 完成 | P3 | 前端 / 可维护性 | [PR #41](https://github.com/MarkDanile/MetaEduBase/pull/41) |
| TD-019 | 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 | 🟢 完成 | P0 | 前端 / 运行时稳定性 / 测试 | [PR #42](https://github.com/MarkDanile/MetaEduBase/pull/42) |
| TD-020 | 统一 LLM provider resolver 与 factory 优先级事实源 | 🟢 完成 | P2 | 后端 / AI / 可维护性 | [PR #46](https://github.com/MarkDanile/MetaEduBase/pull/46) |
| TD-021 | 收口已完成计划文件和候选区状态同步漏洞 | 🟢 完成 | P1 | 文档 / 工程流程 / 跨 AI 交接 | `quality-gates.md` |
| TD-022 | 收口早期已完成计划文件的活动式未勾选项 | 🟢 完成 | P2 | 文档 / 工程流程 / 跨 AI 交接 | [PR #44](https://github.com/MarkDanile/MetaEduBase/pull/44) |
| TD-023 | 收口 TD-020 文档一致性、断链与归档索引 | 🟢 完成 | P2 | 文档 / 工程流程 / 跨 AI 交接 | `docs/03-engineering-governance/current-work.md` |
| TD-024 | 收口 TD-023 复核发现的副本文件与旧归一化表述 | 🟢 完成 | P2 | 文档 / 工程流程 / 仓库卫生 | TD-023 复核 |
| TD-025 | 业务页面 `liquid-card` 容器统一迁移到 `ui-panel`（业务视图部分完成） | 🟢 完成 | P2 | 前端 / 设计系统 | [PR #54](https://github.com/MarkDanile/MetaEduBase/pull/54) + [PR #55](https://github.com/MarkDanile/MetaEduBase/pull/55) + [PR #56](https://github.com/MarkDanile/MetaEduBase/pull/56) |
| TD-026 | 共享组件 `liquid-card` 残留验证 | 🟢 完成 | P3 | 前端 / 设计系统 | [PR #58](https://github.com/MarkDanile/MetaEduBase/pull/58) |
| TD-027 | 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展） | 🟢 完成 | P3 | 前端 / 设计系统 | [PR #59](https://github.com/MarkDanile/MetaEduBase/pull/59) |
| TD-028 | 业务视图与共享组件的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 存量替换 | 🟢 完成 | P3 | 前端 / 设计系统 | [PR #61](https://github.com/MarkDanile/MetaEduBase/pull/61) |
| TD-029 | 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 🟢 完成 | P1 | 前端 / 类型 / 交付 | [Spec](../02-delivery-plans/01-specs/2026-06-06-td-029-shared-schema-gate.md) / [Plan](../02-delivery-plans/02-plans/2026-06-06-td-029-shared-schema-gate-plan.md) |
| TD-030 | RecallChannel Protocol vs concrete signature drift on parameter names | ⚫ 待办 | P3 | 后端 / 测试 | REQ-003 / 2026-W23 iteration |
| TD-031 | RAG 质量测试文件的预存 ruff 警告 | 🟢 完成 | P2 | 后端 / 测试 / 质量门禁 | [PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) |
| TD-032 | 治理超大源码文件并建立文件规模拆分原则 | 🟢 完成 | P2 | 可维护性 / 架构 / 前端 / 后端 / 工程治理 | 2026-06-08 源码行数扫描 |

## 任务详情

### TD-001: 拆分应用启动时的数据库迁移与默认种子数据

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 领域 | 安全 / 交付 |
| 事实源 | `291dbbc` |

**证据**
- `packages/server-python/app/main.py:22-25` 在应用生命周期中执行 `init_db_with_seed()`。
- `packages/server-python/app/shared/infrastructure/database.py:40-59` 在 Alembic 失败后回退到 `Base.metadata.create_all`。
- `packages/server-python/app/shared/infrastructure/seed.py:38-56` 使用 `admin123` 创建默认管理员。

**问题**
- 应用启动会直接修改数据库，并可能掩盖迁移失败。
- 默认种子数据容易让开发账号误入不安全环境。

**完成标准**
- 生产应用启动不再自动执行迁移或默认管理员种子写入。
- 开发和测试环境仍有明确、显式、已文档化的初始化方式。

**验证方式**
- 启动后端不会触发 Alembic 或 seed 写入。
- 显式开发初始化命令仍能创建 schema 和默认开发管理员。
- 准备好 schema 后健康检查仍能通过。

**交付记录**
- 2026-06-04 完成，提交 `291dbbc`。
- 移除启动时隐式迁移和 seed；新增 `make init-dev-db` / `./dev.sh init-db`；默认 seed 需要 `ALLOW_DEFAULT_SEED=true`。
- 验证摘要：`./dev.sh init-db` 通过；健康检查返回 ok；`pytest -q` 83 passed；相关 ruff 通过。

### TD-002: 收敛文件清理的级联删除逻辑

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 领域 | 数据一致性 |
| 事实源 | [PR #12](https://github.com/MarkDanile/MetaEduBase/pull/12), merge commit `2eb59e8` |

**证据**
- `packages/server-python/app/contexts/document/interfaces/api/router.py:265-309` 和 `:330-380` 都手写 SQL 删除 chunks、knowledge edges、knowledge nodes 和 document tasks。

**问题**
- 清理顺序和清理范围重复写在 API handler 中，后续修复很容易只覆盖其中一条路径。

**完成标准**
- 文件删除和文件重新初始化共用同一个清理 service 或 repository 函数。
- API handler 不再重复书写级联 SQL。

**验证方式**
- 现有文件删除和重新初始化测试通过。
- 回归场景验证文件派生节点关联的 knowledge edges 会先于节点被清理。

**交付记录**
- 2026-06-04 完成，PR #12 合并。
- 新增 knowledge node / document task repository 清理方法，并抽出 `cleanup_file_derivatives` / `cleanup_dataset_derivatives`。
- 修复 `DELETE /datasets/{dataset_id}` 删 knowledge_nodes 前未删 knowledge_edges 的 bug。
- 验证摘要：`pytest -q` 86 passed；`tests/contexts/document/test_cascade_cleanup.py` 3 passed；router 中不再有内联级联 SQL。
- 后续补充：TD-002-FOLLOWUP 已补 dataset reinitialize 回归测试、ruff E501 和状态收口。

### TD-003: 让前端 lint 质量门禁可运行

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 领域 | 前端 / 交付 |
| 事实源 | `090242a` |

**证据**
- `packages/web/package.json:11` 定义 `lint` 为 `eslint src/`，但前端包未声明 ESLint 依赖。
- 执行 `pnpm --filter @metaedu/web lint` 曾失败并输出 `sh: eslint: command not found`。

**问题**
- 仓库声明了 lint 门禁，但实际无法运行，本地和 CI 都无法强制执行静态检查。

**完成标准**
- 前端 lint 能基于明确 ESLint 配置成功运行，或脚本替换为项目真实采用的质量门禁。

**验证方式**
- `pnpm --filter @metaedu/web lint` 退出码为 0。
- `pnpm --filter @metaedu/web typecheck` 退出码为 0。

**交付记录**
- 2026-06-04 完成，提交 `090242a`。
- 验证摘要：lint 和 typecheck 均可运行；当时剩余 warning 后续由 TD-011 收口。

### TD-004: 让后端测试数据库环境可复现

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 测试 / 交付 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-04-td-004-test-database-reproducibility.md), [Plan](../02-delivery-plans/02-plans/2026-06-04-td-004-test-database-reproducibility-plan.md), [PR #23](https://github.com/MarkDanile/MetaEduBase/pull/23), merge commit `b8b34a6` |

**证据**
- `packages/server-python/tests/conftest.py:13` 硬编码 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`。
- 新环境中不依赖数据库的测试能通过，但集成测试会在连接本地 PostgreSQL 时失败。

**问题**
- 测试执行依赖隐式本地数据库，新环境或 CI 中很难稳定复现。

**完成标准**
- 测试数据库 URL 可配置。
- 提供明确的测试数据库启动或初始化方式。

**验证方式**
- 全新环境可启动所需测试数据库。
- `cd packages/server-python && .venv/bin/python -m pytest -q` 无需猜测手动建库步骤即可运行。

**交付记录**
- 2026-06-04 完成，PR #23 合并。
- 新增 `test_db_setup.py`、`./dev.sh init-test-db`、`make init-test-db`，并让 conftest 读取 `TEST_DATABASE_URL`。
- 验证摘要：`./dev.sh init-test-db` 幂等通过；`pytest -q` 87 passed；`ruff check app/ tests/` 退出码 0。
- 后续严谨性收口见 TD-013 和 TD-014。

### TD-005: 拆分大型后端任务流水线文件

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 后端 / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-005-task-lifecycle-helpers.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md), [PR #34](https://github.com/MarkDanile/MetaEduBase/pull/34), merge commit `e5197a5` |

**证据**
- `packages/server-python/app/contexts/document/application/tasks.py` 和 `structured_data/application/tasks.py` 均为大型流程文件。

**问题**
- 解析、抽取、状态更新、知识图谱处理和异常处理集中在大型流程文件中，小改动也容易带来回归风险。

**完成标准**
- 至少将稳定横切逻辑抽成聚焦 helper 或 service，例如任务状态更新、prompt 构造、文件派生 KG 清理、解析器分发。

**验证方式**
- 现有后端测试通过。
- 对被抽出的稳定单元补充聚焦测试。
- 除重构目标外不改变业务行为。

**交付记录**
- 2026-06-05 完成，PR #34 合并。
- 新增 `app/shared/tasks/lifecycle.py`，集中 session、任务状态和任务创建 helper；两个任务文件删除本地重复 helper。
- 可观察行为变化：structured_data 路径下 `update_task_status` 现在会写 `updated_at`，PR 已明确说明。
- 验证摘要：`tests/shared/test_task_lifecycle.py` 12 passed；`pytest -q` 126 passed；`ruff check app/ tests/` 通过。

### TD-006: 集中 LLM provider 和模型 fallback 策略

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 后端 / AI |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-006-llm-model-fallback.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-006-llm-model-fallback-plan.md), [PR #35](https://github.com/MarkDanile/MetaEduBase/pull/35), merge commit `042e4a9` |

**证据**
- `packages/server-python/app/shared/llm/factory.py:34-77` 定义 provider 优先级和可用性选择。
- `packages/server-python/app/contexts/template/application/service.py:181-212` 又硬编码 DeepSeek flash 到默认模型的 fallback。

**问题**
- 模型和 provider 策略分散在共享 LLM 基础设施与业务 service 中，后续调整容易不一致。

**完成标准**
- 模板 AI 生成使用集中化的模型/provider 策略，或使用命名明确的共享 helper 表达快速模型 fallback 行为。

**验证方式**
- 模板 AI 生成仍优先尝试预期快速模型，并能按预期 fallback。
- 测试或 mock 覆盖 fallback 路径。

**交付记录**
- 2026-06-05 完成，PR #35 合并。
- 新增 `chat_with_model_fallback`，template service 删除私有 `_call_llm`。
- 验证摘要：`tests/shared/test_chat_model_fallback.py` 6 passed；`pytest -q` 132 passed；`ruff check app/ tests/` 通过。
- 后续 provider 选择重复已拆为 TD-016 并完成；provider/factory 策略漂移仍保留为 TD-020。

### TD-007: 减少前端请求状态处理重复

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-007-databaseview-vue-query.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-007-databaseview-vue-query-plan.md), [PR #36](https://github.com/MarkDanile/MetaEduBase/pull/36), merge commit `350acd2` |

**证据**
- `packages/web/src/main.ts` 注册了 `VueQueryPlugin`。
- `packages/web/src/views/database/DatabaseView.vue` 仍手动管理大量 loading、错误提示、轮询刷新和 toast 流程。

**问题**
- 请求生命周期逻辑在多个视图中重复，loading、刷新、错误处理行为难以保持一致。

**完成标准**
- 选择高变更页面，将重复请求生命周期逻辑迁移到 composable 或 Vue Query 用法中。
- 不改变用户可见行为。

**验证方式**
- 前端 typecheck 和 build 通过。
- 手动验证列表、详情、上传、重试、重新初始化和 tab 刷新流程。

**交付记录**
- 2026-06-05 完成，PR #36 合并。
- `DatabaseView` 迁入 Vue Query：集中 5 个 query、5 个 mutation、query key 和全局错误 toast。
- 验证摘要：`pnpm --filter @metaedu/web typecheck` / `build` / `lint` 均退出码 0。
- 迁移后发现的行为回归拆为 TD-015 并完成；FileDetailView 推广拆为 TD-017 / TD-018 并完成。

### TD-008: 明确从 `liquid-*` 类到语义 UI 层的迁移路径

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 设计系统 |
| 事实源 | `docs/90-compat-legacy/superpowers/plans/2026-05-22-frontend-ui-foundation-redesign.md`（历史方案，不直接执行） + `docs/03-engineering-governance/01-rules/coding-style.md`（迁移说明落地位置） |

**证据**
- `packages/web/src/assets/css/main.css:411-690` 定义了 `liquid-card / liquid-input / liquid-btn* / liquid-tag* / liquid-dialog / liquid-rise-* / content-bg`，没有 `ui-page-shell / ui-panel / ui-toolbar / ui-interactive-row` 等语义化类。
- `packages/web/src/views/database/DatabaseView.vue`（23 处）、`resource/ResourceView.vue`（22）、`resource/ResourceLibraryView.vue`（18）、`knowledge/KnowledgeBaseView.vue`（16）、`resource/FileDetailView.vue`（12）、`admin/TemplateModal.vue`（8）、`admin/TemplateEditorView.vue`（6）、`views/auth/LoginView.vue`（4）、`ai-chat/AiChatView.vue`（4）仍以 `liquid-*` 类为主。
- `docs/90-compat-legacy/superpowers/plans/2026-05-22-frontend-ui-foundation-redesign.md`（10 个 task）已提出 `ui-*` 体系但未执行。
- `docs/03-engineering-governance/01-rules/coding-style.md:52` 已预告"当前代码仍以 `liquid-*` 类为主，后续会逐步迁移到语义化 `ui-*` workspace 层"。

**问题**
- 设计系统处于过渡状态，新增页面或组件容易继续在 `liquid-*` 上堆叠，风格治理成本上升。
- `liquid-card-scan` 装饰动效、`wet-line` 装饰条等历史视觉与"calm workspace"目标不一致。
- 缺乏明确规则：何时使用 `liquid-*`、何时使用 `ui-*`，导致跨 AI IDE 接手时各自选边。

**完成标准**
- `docs/03-engineering-governance/01-rules/coding-style.md` 设计系统章节补一段"迁移说明"，明确 `ui-*` 语义层适用场景、`liquid-*` 保留场景、新增/修改 UI 的优先级。
- `packages/web/src/assets/css/main.css` 追加 4 个 `ui-*` 共享类（`ui-page-shell` / `ui-panel` / `ui-toolbar` / `ui-interactive-row`），全部 token 化，不引入新硬编码。
- 至少迁移 1 个代表性页面/组件族：本次选 `LayoutView.vue` + `PageHeader.vue` + `EmptyState.vue` 三个共享骨架组件。`LayoutView` 的 `main` 容器切到 `ui-page-shell`；`PageHeader` 去掉 `wet-line` 装饰条和 `stagger-*` 动画；`EmptyState` 改用 `ui-panel` 容器。
- 现有 `liquid-*` 类全部保留，不删不动，作为兼容别名。
- 4 主题视觉表现不发生可观察退化。

**验证方式**
- `cd packages/web && pnpm typecheck` 退出码 0。
- `cd packages/web && pnpm build` 退出码 0。
- `cd packages/web && pnpm lint` 退出码 0 且无新增 warning。
- `scripts/check-engineering-docs` 退出码 0。
- `rg -n "ui-page-shell|ui-panel|ui-toolbar|ui-interactive-row" packages/web/src/` 能命中 `LayoutView` / `PageHeader` / `EmptyState`。
- `rg -n "wet-line|stagger-1" packages/web/src/components/PageHeader.vue packages/web/src/components/EmptyState.vue` 不再命中。
- 4 主题（liquid / ink / navy / notion）下 `/`、`/admin`、`/skill-editor` 手工验收视觉无退化（按 superpowers plan 验证矩阵）。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code）。共 8 个文件变更，无业务行为变化。
  1. `docs/03-engineering-governance/01-rules/coding-style.md` 设计系统章节新增「迁移说明」段落：明确 5 个 `ui-*` 共享类用途、`ui-*` 优先 / `liquid-*` 兼容的边界、第一个迁移目标；新增/修改 UI 优先级清单（1. 复用 `ui-*` → 2. 复用既有局部风格 → 3. 不重复造样式 → 4. 不硬编码 → 5. 修改共享组件前查调用方）。
  2. `packages/web/src/assets/css/main.css` 第 403 行附近 `@layer components` 段头部追加 5 个 `ui-*` 共享类（`ui-page-shell` / `ui-page-section` / `ui-panel` / `ui-toolbar` / `ui-interactive-row`），全部 token 化。
  3. `packages/web/src/views/LayoutView.vue` 第 139-149 行 `main` 容器从 `content-bg` 切到 `ui-page-shell`，保留 `liquid-rise` 转场与 `RouterView` 不变。
  4. `packages/web/src/components/PageHeader.vue` 重构为 `ui-page-section` 语义块：去掉 `wet-line` 装饰条 + `animate-slide-up` + `stagger-*` + `lineWidth/stagger` props（公共 API 收窄）；保留 `greeting` / `title` / `subtitle` / `extra` 4 个 slot 与 `title` / `subtitle` props。
  5. `packages/web/src/components/EmptyState.vue` 容器从裸居中改用 `ui-panel p-6`，去掉 `animate-slide-up stagger-1`；icon 尺寸 48→40，stroke 1→1.25。
  6. `packages/web/src/views/HomeView.vue` 第 3 行去掉 `PageHeader` 的 `:line-width="48"` 传参（公共 API 收窄的同步修复）。
  7. `docs/03-engineering-governance/current-work.md` 任务卡片登记（开工 → 完成）。
  8. `docs/03-engineering-governance/technical-debt.md` 本卡片（开工 → 完成）。

- 行为变化声明（按 `quality-gates.md#行为变化声明检查`）：
  - **可观察行为变化 1**：`PageHeader` 去掉 `wet-line` 装饰条（视觉差异：标题下方不再有渐变小条）。
  - **可观察行为变化 2**：`PageHeader` 与 `EmptyState` 去掉 `animate-slide-up` + `stagger-*` 入场动画（视觉差异：组件挂载时不再有上滑+延迟）。
  - **可观察行为变化 3**：`EmptyState` 加 `ui-panel` 容器（视觉差异：现在有浅色边框 + 圆角面板，与裸居中不同）。
  - **公共 API 收窄**：`PageHeader` 删除 `lineWidth` / `stagger` props。已确认 `HomeView` 唯一外部调用方并同步修复。
  - 4 主题视觉表现**不发生**其他可观察变化（颜色全部走 token，自动适配）。

- 验证摘要（按 `quality-gates.md#完成门禁`）：
  - 已运行：`pnpm --filter @metaedu/web typecheck` → 退出码 0（vue-tsc --noEmit 无输出）。
  - 已运行：`pnpm --filter @metaedu/web build` → 退出码 0，✓ built in 2.92s。
  - 已运行：`pnpm --filter @metaedu/web lint` → 退出码 0，eslint 无 warning。
  - 已运行：`scripts/check-engineering-docs` → 退出码 0（`engineering docs checks passed`）。
  - 已运行：`rg -n "ui-page-shell|ui-panel|ui-toolbar|ui-interactive-row" packages/web/src/` → 命中 `main.css` 定义段 + `LayoutView.vue:144` + `EmptyState.vue:2` + 2 个历史 `Template*` 视图（与本任务无关）。
  - 已运行：`rg -n "wet-line|stagger-1|stagger-2|stagger-3|stagger-4|stagger-5" packages/web/src/components/PageHeader.vue packages/web/src/components/EmptyState.vue` → 0 命中。
  - 已运行：`rg -n ":line-width=|:stagger=" packages/web/src/views/` → 0 命中（`PageHeader` API 收窄后无残留调用）。
  - 已运行：`git status --short --branch` → 工作区仅 8 个文件被本任务改动，无未跟踪垃圾。
  - 未运行：`./dev.sh frontend` + 浏览器 4 主题手工验收 — 沙箱无浏览器。

- 后续接力建议（不阻塞本任务完成）：
  - 业务页面（`DatabaseView` / `ResourceView` / `ResourceLibraryView` / `KnowledgeBaseView` / `FileDetailView`）的 `liquid-card` → `ui-panel` 迁移可以拆为后续 `TD-xxx`（P2/P3）。当前 TD-008 完成标准是"至少 1 个代表性页面/组件族"，已由 3 个共享骨架组件满足。
  - `EmptyState` 的 `compact` prop 未声明问题在 `DatabaseView.vue:59` 仍存在（与本任务无关，是历史 prop 拼写错误）；是否登记为 `TD-xxx` 由后续判断。

### TD-025: 业务页面 `liquid-card` 容器统一迁移到 `ui-panel`

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 设计系统 |
| 事实源 | `docs/03-engineering-governance/technical-debt.md#td-008` 交付记录 + `docs/03-engineering-governance/01-rules/coding-style.md#迁移说明-td-008` + `docs/03-engineering-governance/01-rules/coding-style.md#业务页面迁移清单-td-025` |

**证据**
- TD-008 完成（2026-06-05）后，`ui-page-shell` / `ui-panel` / `ui-toolbar` / `ui-interactive-row` 已落地为共享类，`coding-style.md` 迁移说明已明确"`ui-*` 优先 / `liquid-*` 兼容"。
- 业务视图残留量（TD-008 完成时快照）：`DatabaseView.vue` 23 处、`ResourceView.vue` 22、`ResourceLibraryView.vue` 18、`KnowledgeBaseView.vue` 16、`FileDetailView.vue` 12、`TemplateModal.vue` 8、`TemplateEditorView.vue` 6、`LoginView.vue` 4（按 TD-008 规则保持兼容，本次不迁）、`AiChatView.vue` 4、`HomeView.vue` 3。
- 共享组件残留：`FieldEditor.vue` 12、`KGDetailPanel.vue` 4、`ConfirmDialog.vue` 5、`KGGraph.vue` 1（共享组件按 TD-008 规则不在本次范围，列入后续接力）。

**问题**
- 业务页面与共享组件仍以 `liquid-card` 为主，TD-008 的 `ui-panel` 规范在 `LayoutView` / `PageHeader` / `EmptyState` 落地后没有跟随到实际页面。
- 设计系统迁移说明虽明确"优先 `ui-*`"，但缺接力任务，导致后续 AI IDE 接手时仍按"老习惯"继续堆 `liquid-card`，与新规范脱节。
- 4 主题下页面外壳与面板在视觉上不同源（外壳走 `ui-panel`、内容走 `liquid-card`），calm workspace 目标只完成一半。

**完成标准**
- **切片 1：3 个高残留业务页面**（按当前数据：`DatabaseView` / `ResourceView` / `ResourceLibraryView`）的 `liquid-card` 容器统一替换为 `ui-panel`，行为不变；保留 hover 语义（必要时加 `ui-interactive-row`）、保留 `liquid-card-scan::after` 装饰效果在受控的卡片上不动。
- **切片 2：2 个次高残留业务页面**（`KnowledgeBaseView` / `FileDetailView`）完成同样的 `liquid-card` → `ui-panel` 替换；保留 `ring-1 ring-[var(--color-accent)]` 等选中态的 raw token 用法。
- **切片 3：业务页面的 `liquid-btn-*` / `liquid-input` 显式登记例外**：在 PR 描述中明确这些类按 TD-008 规则保持兼容，本次不替换。
- **切片 4：文档同步**：`coding-style.md#迁移说明` 增补一段"业务页面迁移清单 + 进度"，把已完成页面加链接；TD-025 卡片 `交付记录` 记录每个切片的 PR / commit。
- 不替换：`LoginView` 品牌背景 / `liquid-card-scan::after` 装饰 / `liquid-btn-*` / `liquid-input` / `liquid-tag-*` / `liquid-dialog` / `liquid-rise-*` / `wet-line`。
- 4 主题视觉不发生可观察退化（仅容器视觉 token 切换）。

**验证方式**
- 每个切片都跑：`cd packages/web && pnpm typecheck && pnpm lint && pnpm build`，全部退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- 切片完成后 `rg "liquid-card" packages/web/src/views/database/DatabaseView.vue` 等已迁入页面的命中数从原值降到 0。
- 覆盖矩阵：每页面至少覆盖"卡片容器替换"和"hover / 选中态保留"两行；不引入新功能。
- 4 主题（liquid / ink / navy / notion）下 `DatabaseView` / `ResourceView` / `ResourceLibraryView` 三个最高残留页面手工验收（`./dev.sh frontend` 启动后浏览器切换主题）；沙箱无浏览器时降级为 typecheck + lint + 视觉对照 `git diff` 自检。

**交付记录**
- **切片 1 完成**（2026-06-05）：接手工具 Claude Code；`main.css` 新增 `:root[data-theme="liquid"] .ui-panel` 玻璃感覆盖（复用 `--_surface-card-bg` + `--_surface-glass-blur`），3 个页面 `liquid-card` 容器全部替换为 `ui-panel`，附加类（`group` / `animate-slide-up` / `stagger-N` / 自定义 hover）原样保留。PR #54，merge commit `558884e`。
- **切片 2 完成**（2026-06-05）：2 个业务页（`KnowledgeBaseView` 1 处 + `FileDetailView` 3 处 = 4 处）`liquid-card` → `ui-panel` 替换；保留 KBView 节点列表卡 `ring-1 ring-[var(--color-accent)] ring-offset-2` 选中态、保留 KBView `animate-slide-up` + `stagger-N` 装饰动效；保留 FileDetailView 三个面板（meta bar / pipeline status / tabs）的所有 inline token 容器与 `liquid-tag-*` / `liquid-btn-*`。PR #55，merge commit `90763d1`。
- **切片 3 完成**（2026-06-05）：2 个业务页（`HomeView` 3 处 + `AiChatView` 1 处 = 4 处）`liquid-card` → `ui-panel` 替换；`HomeView:10` 统计卡保留 `liquid-card-scan` 装饰动效；`coding-style.md` 显式例外清单段（6 类）记录按 TD-008 规则保持兼容的 `liquid-btn-primary` / `liquid-btn-ghost` / `liquid-input` / `liquid-tag-*` / `liquid-card-scan`（装饰） / `stagger-N` & `animate-slide-up`。PR #56，merge commit `26d4654`。
- **任务卡残留量与实际差异说明**（已记入 coding-style.md 清单 + 切片 2/3 交付记录）：TD-025 任务卡证据段记录的残留量（`DatabaseView` 23 / `ResourceView` 22 / `ResourceLibraryView` 18 / `KnowledgeBaseView` 16 / `FileDetailView` 12 / `TemplateModal` 8 / `TemplateEditorView` 6 / `AiChatView` 4 / `HomeView` 3）是 **TD-008 完成时（2026-06-05）** 的快照。实际开工时（切片 1: 2026-06-05；切片 2: 2026-06-05；切片 3: 2026-06-05）的 grep 命中数为：DB 8、Resource 1、Library 3、KBView 1、FileDetail 3、Template 0 + 0（实测 0 处 `liquid-card`）、AiChat 1、HomeView 3，合计 20 处。`TemplateModal` / `TemplateEditorView` 实测无 `liquid-card` 残留（仅 `liquid-btn-*` / `liquid-input` / `liquid-tag-*`，按例外清单保持兼容）。差异原因：任务卡编写时把页面里所有 `liquid-*`（含 `liquid-btn-*` / `liquid-input` / `liquid-tag-*` / `liquid-dialog` / `liquid-rise-*` / `liquid-card`）都计入了"liquid-card 残留"，而非精确 grep 后的 `liquid-card` 命中数。后续 TD-026 共享组件迁移以 grep 实测为准，不再使用原任务卡残留量作为目标。
- **TD-025 业务视图迁移整体收尾**：3 切片累计 **7 业务页面 20 处 `liquid-card` → `ui-panel`** + `HomeView` 1 处 `liquid-card-scan` 装饰保留 + 4 处 `LoginView` 例外登记。`TemplateModal` / `TemplateEditorView` 实测无 `liquid-card` 残留（仅 `liquid-btn-*` / `liquid-input` / `liquid-tag-*`）。`rg -c "liquid-card" packages/web/src/views/` 最终仅剩 `LoginView:1`（4 处 `liquid-btn-*` 等）+ `HomeView:1`（`liquid-card-scan` 装饰）；其他 7 业务视图全部 0 命中。共享组件（`FieldEditor` 12 / `KGDetailPanel` 4 / `ConfirmDialog` 5 / `KGGraph` 1 = 22 处）未在本次范围，建议拆为 `TD-026`。
- 切片 4（文档同步）合并到切片 1-3 三个提交中：每个提交都同步 `coding-style.md` 迁移清单对应切片行；切片 3 额外追加「显式例外清单」段。

### TD-009: 减少前后端契约漂移

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | API / 类型 |
| 事实源 | `docs/03-engineering-governance/01-rules/contracts.md`；[Spec](../02-delivery-plans/01-specs/2026-06-05-td-009-structured-data-contract.md)；[Plan](../02-delivery-plans/02-plans/2026-06-05-td-009-structured-data-contract-plan.md) |

**证据**
- `packages/shared` 中存在 Zod schemas 和共享 TypeScript 类型。
- 前端 service DTO 与后端 Pydantic DTO 仍主要各自维护。

**问题**
- 模板字段、结构化抽取结果、任务状态等复杂契约容易在前后端之间漂移。

**完成标准**
- 选择一个高价值契约族，优先模板字段或任务状态。
- 建立明确的共享来源或 schema 检查流程。

**验证方式**
- typecheck 通过。
- 所选契约族出现字段不匹配时，能被测试、生成类型或 schema 校验捕获。

**交付记录**
- 2026-06-06 完成（接手工具：Claude Code）。本轮选择结构化抽取结果容器作为契约族：`packages/shared` 新增 `FileStructuredDataSchema` / `FileStructuredData` / `getTemplateStructuredData`；前端 `FileDTO.structured_data` 复用 shared 类型，`FileDetailView` 读取 `template` 前通过 shared helper 窄化；后端抽出 parse/extract structured_data 写入 helper 并补聚焦测试。
- 行为变化声明：正常 `template` object 展示不变；如果后端或历史数据把 `structured_data.template` 写成非 object，前端不再强转展示，而是按无抽取结果处理。
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/shared --filter @metaedu/web typecheck`（pnpm 并行执行，shared 由于无依赖会先于 web 完成 `tsc --noEmit`，从而填充 project reference 所需的类型信息）退出码 0；`pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed；`ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py` 退出码 0；`scripts/check-engineering-docs` 退出码 0。干净 checkout 上单独运行 `pnpm --filter @metaedu/web typecheck` 因 shared composite project reference 缺少 `dist/*.d.ts` 而报 `TS6305`；该门禁缺口已由 [TD-029](#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误) 收口。

### TD-010: 治理生成物 `outputs/` 对工作区的污染

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 交付 / 仓库卫生 |
| 事实源 | 用户确认根目录 `outputs/` 无用并已删除 |

**证据**
- `git status --short` 曾显示未跟踪的 `outputs/`。
- `find outputs -type f | wc -l` 曾报告 413 个文件。

**问题**
- 生成物污染仓库状态和搜索结果，会让真实代码变更更难检查。

**完成标准**
- 项目明确 `outputs/` 应该被忽略、移动，还是作为特定 artifact 工作流被有选择地跟踪。

**验证方式**
- 正常本地工作后，`git status --short` 不再出现意外生成物噪音。

**交付记录**
- 2026-06-05 用户确认 `outputs/` 无用且已删除。
- 补充根目录 `outputs/` 忽略规则，防止同类生成物再次污染工作区。
- 验证摘要：`test -d outputs` 退出码 1；`git status --short` 无生成物噪音。

### TD-011: 治理前端 lint warning

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 前端 / 安全 / 交付 |
| 事实源 | `090242a` |

**证据**
- `pnpm --filter @metaedu/web lint` 可运行，但曾报告 9 个 warning。
- warning 包含 `vue/no-v-html`、`vue/no-template-shadow` 和模板换行提示。

**问题**
- 长期保留 warning 会削弱 lint 输出信号质量，其中 `v-html` 还包含潜在 XSS 风险提示。

**完成标准**
- `pnpm --filter @metaedu/web lint` 退出码为 0 且 warning 数为 0。
- 不通过关闭核心安全规则来掩盖 `v-html` 风险。

**验证方式**
- `pnpm --filter @metaedu/web lint` 通过且无 warning。
- `pnpm --filter @metaedu/web typecheck` 通过。

**交付记录**
- 2026-06-04 完成，提交 `090242a`。
- 静态 SVG `v-html` 改为 lucide 组件；AI Markdown 渲染改为受控边界；修复模板变量遮蔽和换行提示。
- 验证摘要：lint 退出码 0 且无 warning；typecheck 退出码 0。

### TD-012: 治理后端全量 ruff 质量门禁

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 后端 / 测试 / 交付 |
| 事实源 | [PR #17](https://github.com/MarkDanile/MetaEduBase/pull/17), merge commit `a4dcb2a` |

**证据**
- 合并前验证 `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 曾报告 162 个历史 lint 问题。
- 问题覆盖 `app/celery_app.py`、document tasks、template router、`tests/conftest.py` 等文件。

**问题**
- `make lint` 不能作为稳定后端质量门禁运行，历史 lint 噪音和新增问题会混在一起。

**完成标准**
- 后端全量 ruff 门禁可运行并退出码为 0，或明确收敛规则范围并文档化暂缓项。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0。
- 若同步治理 mypy，则补充 `cd packages/server-python && .venv/bin/mypy app/`。

**交付记录**
- 2026-06-04 完成，PR #17 合并。
- 收口 import、E501、B008、SIM、B905、E741、N806、UP046 等 ruff 问题；保留必要 celery task 注册 noqa。
- 修复 `match_prompt` 中 `\\n` 到换行的 prompt 回归。
- 验证摘要：`ruff check app/ tests/` 退出码 0；`pytest -q` 87 passed。

### TD-013: 收口 TD-004 测试数据库初始化安全与文档占位

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 测试 / 交付 / 安全 |
| 事实源 | [PR #27](https://github.com/MarkDanile/MetaEduBase/pull/27), merge commit `8f25b20` |

**证据**
- `test_db_setup.py` 曾使用可控数据库名拼接 `CREATE DATABASE`。
- legacy stamp 曾只依据核心表存在且缺 `alembic_version`。
- TD-004 plan 曾残留 `<TASK-8 输出>` 和 `PR / merge commit 在 Git 闭环后回填` 等占位。

**问题**
- 测试库初始化已可复现，但仍存在 SQL identifier 拼接、过宽 legacy stamp 和完成 plan 占位误导风险。

**完成标准**
- 数据库名在 `CREATE DATABASE` 前经过严格校验或安全 quote。
- legacy stamp 不掩盖残缺 schema。
- TD-004 plan 不再保留活动式交付占位。

**验证方式**
- 新增或更新的后端聚焦测试通过。
- `ruff check app/shared/infrastructure/test_db_setup.py tests/` 退出码 0。
- TD-004 plan 中活动式占位不再命中。

**交付记录**
- 2026-06-05 完成，PR #27 合并。
- 新增 `_validate_database_name` 和 `DatabaseNameError`；收窄 legacy create_all 形态判定；TD-004 plan 补交付历史。
- 验证摘要：`tests/shared/test_test_db_setup.py` 20 passed；全量 ruff 通过；`./dev.sh init-test-db` 幂等通过；`pytest -q` 107 passed。

### TD-014: 加强测试数据库 legacy stamp 的列级形态校验

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 测试 / 交付 / 数据一致性 |
| 事实源 | [PR #28](https://github.com/MarkDanile/MetaEduBase/pull/28), merge commit `af7d246` |

**证据**
- TD-013 后 `_is_legacy_create_all_shape` 仍主要检查核心表集合和 `alembic_version` 缺失。
- 测试未覆盖“核心表全在但关键列缺失”的残缺 schema。

**问题**
- 核心表全在但关键列缺失时，仍可能被误判为旧 `Base.metadata.create_all` 形态并 `stamp head`。

**完成标准**
- legacy stamp 判定除了表集合外，还校验代表旧形态的关键列。
- 关键列缺失时不执行 `stamp head`。
- 新增测试覆盖核心表全在但关键列缺失的负例。

**验证方式**
- `pytest tests/shared/test_test_db_setup.py -q` 退出码 0。
- `ruff check app/shared/infrastructure/test_db_setup.py tests/shared/test_test_db_setup.py` 退出码 0。
- 必要时补充 `./dev.sh init-test-db` 幂等验证。

**交付记录**
- 2026-06-05 完成，PR #28 合并。
- 新增 `_LEGACY_REQUIRED_COLUMNS` 和 `_has_legacy_create_all_columns`，legacy stamp 改为表集合、关键列、缺 alembic_version 三件齐备才触发。
- 验证摘要：`tests/shared/test_test_db_setup.py` 27 passed；全量 ruff 通过；`./dev.sh init-test-db` 通过；`pytest -q` 114 passed。

### TD-015: 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 前端 / API / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-015-databaseview-regressions.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-015-databaseview-regressions-plan.md), [等价矩阵](02-matrices/td-015-databaseview-equivalence.md), [PR #38](https://github.com/MarkDanile/MetaEduBase/pull/38), merge commit `f38fbbc` |

**证据**
- TD-007 后上传数据集名称可能被空字符串覆盖。
- 任务轮询条件、KG overview 懒加载时机和 DTO adapter 存在行为等价缺口。

**问题**
- lint、typecheck 和 build 通过，但未覆盖请求参数、轮询、lazy-load 和 DTO 形态，导致行为回归风险。

**完成标准**
- 上传保留用户填写的 trim 后名称。
- 无 running / pending 任务时停止轮询。
- KG overview 懒加载，且 DTO adapter 明确，不再依赖 `unknown as`。
- 行为等价矩阵覆盖请求参数、enabled、polling、cache invalidation、toast 和 loading 状态。

**验证方式**
- `pnpm --filter @metaedu/web lint` / `typecheck` / `build` 均退出码 0。
- 通过 mock、组件测试或浏览器 / DevTools 验收确认关键行为。

**交付记录**
- 2026-06-05 完成，PR #38 合并。
- 修复上传名称、轮询条件、KG overview 懒加载和 DTO adapter。
- 验证摘要：前端 lint、typecheck、build 均退出码 0。

### TD-016: 收敛 knowledge ai_router 的 LLM provider 选择重复逻辑

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 后端 / AI / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-016-ai-router-provider.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-016-ai-router-provider-plan.md), [PR #39](https://github.com/MarkDanile/MetaEduBase/pull/39), merge commit `4e6cf42` |

**证据**
- TD-006 删除了 template service 私有 `_call_llm`。
- `knowledge/interfaces/api/ai_router.py` 仍手写 provider 选择和 key fallback 顺序。

**问题**
- LLM provider 选择策略仍有第二处业务层重复实现，后续修改 provider、模型配置、无 key 提示或 httpx 行为时可能继续分叉。

**完成标准**
- `ai_router.py` 不再手写 provider if/elif 选择链。
- 保留“未配置 API Key 时返回中文提示”的用户可见行为。
- mock 测试覆盖默认 provider、fallback provider 和无 key 提示。

**验证方式**
- 相关 provider resolver / ai_router 测试通过。
- `ruff check app/ tests/` 退出码 0。
- 若完整 pytest 可运行，补充全量 pytest。

**交付记录**
- 2026-06-05 完成，PR #39 合并。
- 新增 `resolve_chat_provider()` 和 `ProviderConfig`，`ai_router._call_llm` 改用共享 resolver。
- 可观察行为变化：默认 provider 没 key 时 fallback 顺序调整为 `minimax -> deepseek -> qwen`。
- 验证摘要：`tests/shared/test_provider_resolver.py` 7 passed；`pytest -q` 139 passed；全量 ruff 通过。

### TD-017: 将 Vue Query 请求生命周期治理推广到 FileDetailView

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-017-filedetailview-vue-query.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-017-filedetailview-vue-query-plan.md), [等价矩阵](02-matrices/td-017-filedetailview-equivalence.md), [PR #40](https://github.com/MarkDanile/MetaEduBase/pull/40), merge commit `5af2793` |

**证据**
- TD-007 仅迁移了 `DatabaseView`。
- `FileDetailView.vue` 仍手写 tasks、chunks、KG、loading、轮询和 mutation 后刷新逻辑。

**问题**
- 前端请求生命周期治理只覆盖一个高变更页面，FileDetailView 仍存在同类重复和回归风险。

**完成标准**
- 在 TD-015 收口后迁移 FileDetailView 的稳定请求族。
- 迁移前列出行为等价矩阵，覆盖请求参数、tab lazy-load、轮询、mutation 后刷新、toast 和 loading。
- 用户可见行为不变，除非在任务卡片和 PR 中明确声明。

**验证方式**
- `pnpm --filter @metaedu/web lint` / `typecheck` / `build` 均退出码 0。
- 通过自动化 mock、组件测试或浏览器验收关键流程。

**交付记录**
- 2026-06-05 完成，PR #40 合并。
- FileDetailView 的 tasks query、3 个 mutation 和轮询迁到 Vue Query；错误 toast 由 QueryCache 统一。
- Out of scope：`loadFile` / `loadChunks` / `loadKg` / `loadTemplates`，后续已拆为 TD-018。
- 验证摘要：前端 lint、typecheck、build 均退出码 0。

### TD-018: FileDetailView 剩余手写 load 迁到 Vue Query

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 前端 / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-018-filedetailview-remaining.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-018-filedetailview-remaining-plan.md), [等价矩阵](02-matrices/td-018-filedetailview-remaining-equivalence.md), [PR #41](https://github.com/MarkDanile/MetaEduBase/pull/41), merge commit `8ad15e6` |

**证据**
- TD-017 后 FileDetailView 仍有 `loadFile`、`loadChunks`、`loadKg`、`loadTemplates` 四个手写 load。
- `refreshAll`、tab watch 和 polling watch 仍直接调手写 load。

**问题**
- 页面仍混用 Vue Query 状态机和手写 fetch，维护方式不一致。

**完成标准**
- 四个手写 load 迁到 Vue Query。
- `loading*` ref 改由 query 状态派生。
- `watch(activeTab)`、`refreshAll`、polling true->false 全部改为 query refetch 或 enabled。
- 保留 `loadTemplates` 静默失败行为。

**验证方式**
- `pnpm --filter @metaedu/web lint` / `typecheck` / `build` 均退出码 0。
- 行为等价矩阵覆盖 4 个 load 和关键触发路径。

**交付记录**
- 2026-06-05 完成，PR #41 合并。
- 扩展 resource queries，迁移 file / chunks / kg / templates 四类 load；删除手写 loading ref 和 service API import。
- 验证摘要：前端 lint、typecheck、build 均退出码 0。

### TD-019: 修复 Vue Query 轮询自引用导致的页面初始化运行时错误

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 领域 | 前端 / 运行时稳定性 / 测试 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-019-vue-query-self-reference.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-019-vue-query-self-reference-plan.md), [等价矩阵](02-matrices/td-019-vue-query-self-reference-equivalence.md), [PR #42](https://github.com/MarkDanile/MetaEduBase/pull/42), merge commit `387d8f8` |

**证据**
- `DatabaseView` 和 `FileDetailView` 在 query 初始化参数中引用正在声明的 query 变量。
- 最小 Vue Query 复现脚本输出 `ReferenceError: Cannot access 'q' before initialization`。
- lint、typecheck、build 均无法捕获该运行时问题。

**问题**
- 页面 setup 阶段可能直接崩溃，且迁移模式可能继续复制同类错误。

**完成标准**
- query 初始化参数不再引用正在声明的 query 变量。
- 保留“仅存在 running / pending 任务时 3s 轮询”的用户可见行为。
- 补充或记录覆盖两个页面 setup 的 smoke / mount / 浏览器验证。

**验证方式**
- 前端 lint、typecheck、build 均退出码 0。
- 打开或挂载 `DatabaseView` 与 `FileDetailView` 不抛 ReferenceError。
- `rg -n "tasksQuery\\.data\\.value"` 不再命中 query 初始化参数内自引用。

**交付记录**
- 2026-06-05 完成，PR #42 合并。
- 轮询判断下沉到 query hook 内部，用 `refetchInterval: (query) => ...` 从 `query.state.data` 派生。
- 验证摘要：前端 typecheck、build、lint 均退出码 0；最小复现脚本修复前后对照通过；自引用 rg 只命中声明后的 computed 行。

### TD-020: 统一 LLM provider resolver 与 factory 优先级事实源

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / AI / 可维护性 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md), [PR #46](https://github.com/MarkDanile/MetaEduBase/pull/46), merge commit `2c15868` |

**证据**
- `packages/server-python/app/shared/llm/provider_resolver.py:29` 定义 `_PROVIDER_CANDIDATES = ["minimax", "deepseek", "qwen"]`。
- `packages/server-python/app/shared/llm/factory.py:15-37` 使用 `_ALL_PROVIDERS = ["deepseek", "minimax", "siliconflow", "dashscope"]`，并将 `qwen` 归一化到 `dashscope`。
- TD-016 备注记录了 `provider_resolver` 与 `factory.PRIORITY_CHAIN` 仍走不同顺序。

**问题**
- resolver 和 factory 仍是两套 provider 顺序 / 命名事实源。
- 后续调整默认 provider、qwen / dashscope 映射或 fallback 顺序时，knowledge chat 与共享 LLM client 仍可能分叉。

**完成标准**
- provider 顺序、provider 命名归一化和 key/base_url/model 完整性检查收敛到一个共享事实源。
- 或者有命名明确且测试覆盖的 adapter 说明为什么 knowledge chat 与 factory 不同。
- 不再出现互相矛盾的硬编码 provider 顺序。
- 测试覆盖默认 provider、qwen / dashscope 映射、fallback 顺序和 provider 配置不完整跳过逻辑。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_provider_resolver.py <新增或调整的 LLM factory/provider 测试> -q`
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/`
- 若完整后端测试可运行，补充 `cd packages/server-python && .venv/bin/python -m pytest -q`。

**交付记录**
- 2026-06-05 完成，PR #46 合并，merge commit `2c15868`。
- 路线 A：收敛到单一事实源。`factory` 暴露 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`；`provider_resolver` 改为薄壳，仅保留 alias → `settings.<alias>_*` 字段映射。
- `qwen` 走自己的 alias 域（不再归一化为 `dashscope`），保留 `ai_router` 中文提示文案与 `provider_name == "qwen"` 不变。
- 新增 `tests/shared/test_factory.py`（10 用例），扩充 `tests/shared/test_provider_resolver.py`（9 → 11 用例）。
- 验证摘要：`tests/shared/test_provider_resolver.py` + `tests/shared/test_factory.py` 共 20 passed；本地全量 pytest 152 passed（执行环境为本地开发沙箱，依赖 `TEST_DATABASE_URL` 指向的 `metaedu_test`；`gh pr checks 46` 状态为 no checks reported，即 PR #46 未配置 GitHub Actions，本次 152 passed 来自本地复跑，非 CI 证据）；`ruff check app/ tests/` 退出码 0。
- 行为变化声明：零业务逻辑变更。函数签名、提示文案、URL 拼接、API 参数、排序顺序、错误返回均不变。

### TD-021: 收口已完成计划文件和候选区状态同步漏洞

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 文档 / 工程流程 / 跨 AI 交接 |
| 事实源 | `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁` |

**证据**
- `current-work.md` 的“下一批候选任务”曾保留已完成任务。
- TD-016 / TD-017 / TD-018 等已完成 plan 曾残留活动式 `- [ ]`。

**问题**
- 候选区混入完成任务会把近期接力池变成历史索引。
- 已完成 plan 残留未勾选步骤会让后续 AI IDE 误判任务尚未完成。

**完成标准**
- 已完成 plan 补齐交付历史或勾选真实已完成步骤。
- `current-work.md` 候选区只保留 1 到 3 个未完成且已登记的近期候选。
- 规则中有提交前硬检查，防止完成任务残留在候选区或 plan。

**验证方式**
- 目标 plan 的活动式 `- [ ]` 不再命中。
- `current-work.md` 候选区无 `🟢 完成` 行且总数不超过 3。
- 相关规则文档能检索到候选区完成任务清理检查。

**交付记录**
- 2026-06-05 完成。
- TD-016 / TD-017 / TD-018 / TD-019 历史 plan 增加交付历史并收口未勾选项。
- 工作台候选区和最近完成窗口完成清理。
- 后续 DOC-010 已把分散的收尾硬检查收敛为 `quality-gates.md#完成门禁`。

### TD-022: 收口早期已完成计划文件的活动式未勾选项

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程流程 / 跨 AI 交接 |
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-022-close-early-plan-checkboxes.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-022-close-early-plan-checkboxes-plan.md), [PR #44](https://github.com/MarkDanile/MetaEduBase/pull/44), merge commit `f33c19c` |

**证据**
- `rg -n "^- \\[ \\]" docs/02-delivery-plans/02-plans` 仍命中多个早期已完成任务的历史 plan。
- 命中范围包括 TD-004、TD-005、TD-006、TD-007、TD-015 的历史 plan。

**问题**
- 已完成任务对应 plan 残留活动式 `- [ ]`，会让后续 AI IDE 误判任务尚未完成。

**完成标准**
- 早期已完成 plan 增加交付历史说明。
- 真实已完成步骤改为 `- [x]` 或改写为历史记录。
- 无法确认或实际未完成的项必须迁成稳定编号任务或明确标成 out of scope。

**验证方式**
- 目标 5 个 plan 的活动式 `- [ ]` 不再命中。
- 对应技术债总账、work-log 和 plan 的完成事实一致。

**交付记录**
- 2026-06-05 完成，PR #44 合并。
- 5 个早期 plan 增加交付历史；154 行行首 `- [ ]` 收口为 `- [x]`。
- 验证摘要：目标 5 个 plan 活动式 `- [ ]` 命中 0；`交付历史` 每个 plan 至少 1 行命中。
- 合并后复核发现 TD-022 自己的 plan 未闭合，已在 DOC-010 同批文档治理中补交付历史并收口。

### TD-023: 收口 TD-020 文档一致性、断链与归档索引

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程流程 / 跨 AI 交接 |
| 事实源 | TD-020 复核 |

**证据**
- `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md:151`（修复前）描述 `resolver_default_provider()` 会把 `dashscope → qwen`，但实现 `packages/server-python/app/shared/llm/factory.py:51-74` 和测试 `packages/server-python/tests/shared/test_factory.py:71-78` 均锁定 `dashscope` 返回 `None`。
- `docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md:5`（修复前）的 Spec 链接指向当前目录下同名文件 `2026-06-05-td-020-provider-resolver-factory.md`，实际文件在 `docs/02-delivery-plans/01-specs/`，plan 中相对路径断链。
- `docs/03-engineering-governance/work-log.md` 的 TD-020 backfill（commit `97c45d0`）替换了原 DOC-011 索引，导致 DOC-011 从长期工作日志索引中消失。
- `docs/03-engineering-governance/technical-debt.md`、TD-020 spec 和 plan 顶部写有“全量 pytest 152 passed”，但 `gh pr checks 46` 显示 no checks reported（PR #46 未配置 GitHub Actions）；该声明缺少 CI 证据，仅来自本地复跑。Codex 沙箱曾报 `::1:5432` 连接权限失败，但在 Claude Code 沙箱 `cd packages/server-python && .venv/bin/python -m pytest -q` 实际复跑得到 152 passed；TD-023 收口后该事实统一表述为“本地复跑 152 passed，非 CI 证据”。

**问题**
- TD-020 代码实现本身已通过聚焦验证，但交付文档存在行为描述矛盾、断链、归档索引丢失和验证声明证据不足。
- 这些问题会误导后续 AI IDE 接手，降低跨工具交接可信度。

**完成标准**
- TD-020 spec 中 `resolver_default_provider()`、`qwen` 和 `dashscope` 的描述与实现、测试保持一致。
- TD-020 plan 的 Spec 链接能正确跳转到 `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md`。
- `docs/03-engineering-governance/work-log.md` 同时保留 TD-020 和 DOC-011 的长期索引。
- TD-020 相关文档中的全量 pytest 声明改为可复核表述：保留聚焦 pytest 与 ruff 通过事实，明确“全量 pytest 152 passed”为本地复跑结果并注明 `gh pr checks 46` no checks reported（PR #46 未配置 CI）。

**验证方式**
- `rg -n "dashscope → qwen|把 factory 归一化结果再翻译回 resolver 子集别名" docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md` 不再命中误导描述。
- `test -f docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md`，并人工确认 plan 中 Spec 链接使用 `../02-delivery-plans/01-specs/`。
- `rg -n "TD-020|DOC-011" docs/03-engineering-governance/work-log.md` 同时命中两条索引。
- `rg -n "全量 pytest 152 passed|no checks reported" docs/03-engineering-governance/technical-debt.md docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md` 的结果与实际验证证据一致（聚焦 pytest 20 passed；本地全量 pytest 152 passed；`gh pr checks 46` no checks reported；`ruff check app/ tests/` 退出码 0）。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code）。4 项修复均落地，docs-only 无业务代码变更。
  1. `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md` 第 4.1、4.3、4.4 节中 `dashscope → qwen` 描述与代码示例同步改成“独立 trim/lowercase 后 `dashscope` 仍在子集外，返回 `None`”，与 `factory.resolver_default_provider()` 实现和 `test_factory.py::test_dashscope_is_not_a_resolver_alias` 一致。
  2. `docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md` Spec 链接从同级 `2026-06-05-...` 改为 `../02-delivery-plans/01-specs/2026-06-05-...`，可正确跳转。
  3. `docs/03-engineering-governance/work-log.md` 顶部索引表恢复 DOC-011 行（DOC-010 上方），与 TD-020 同行被替换前一致。
  4. 三份文档（`technical-debt.md`、spec、plan）顶部“交付历史 / 验证摘要”中的全量 pytest 声明补充“执行环境为本地开发沙箱 + `gh pr checks 46` no checks reported / PR #46 未配置 CI”，明确本地非 CI 证据。
- 验证摘要（按 `quality-gates.md#完成门禁`）：
  - 已运行：`scripts/check-engineering-docs` 退出码 0（`engineering docs checks passed`）。
  - 已运行：`cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_provider_resolver.py tests/shared/test_factory.py -q` → 20 passed。
  - 已运行：`cd packages/server-python && .venv/bin/python -m pytest -q` → 152 passed in 24.52s（本地沙箱复跑，非 CI 证据）。
  - 已运行：`gh pr checks 46` → `no checks reported on the 'chore/td-020-llm-provider-factsource' branch`；`gh pr view 46 --json state,mergeCommit` → `state=MERGED, mergeCommit=2c15868`。
  - 4 条 `rg` 验收断言全部通过：spec 误导描述 0 命中；plan Spec 链接 2 处使用 `../02-delivery-plans/01-specs/`；work-log 同时命中 `TD-020`（行 19）和 `DOC-011`（行 20）；3 份目标文档“全量 pytest 152 passed / no checks reported”表述一致。
  - 未运行：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` —— 执行环境（auto mode）拒绝 lint 工具调用，按 `quality-gates.md#验证表述规范` 标注为 `未运行`，不替代 TD-020 已记录的 `ruff check app/ tests/` 退出码 0 事实。

### TD-024: 收口 TD-023 复核发现的副本文件与旧归一化表述

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程流程 / 仓库卫生 |
| 事实源 | TD-023 复核 |

**证据**
- `git status --short --branch` 在 `main...origin/main` 上显示未跟踪文件 `scripts/engineering/check_engineering_docs 2.py`。
- `shasum -a 256 scripts/engineering/check_engineering_docs.py "scripts/engineering/check_engineering_docs 2.py"` 显示两个文件哈希一致，说明它是正式文档门禁实现的重复副本。
- `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md:42` 仍写 `provider_resolver` 复用 `factory` 的”归一化”逻辑；实际 `resolver_default_provider()` 不复用 `_normalize_default_provider`。
- `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md:44` 仍写 `qwen→dashscope` 归一化测试覆盖，但 resolver 语义是 `qwen` 保持 alias，`dashscope` 不是 resolver alias。
- `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md:137` 仍写 `dashscope` 归一化路径由 `factory.resolver_default_provider` 集中维护，容易与后文”`dashscope` 返回 `None`”冲突。
- `docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md:46` 仍保留”优先复用 `_normalize_default_provider`，再决定是否翻译回 `qwen`”的历史风险描述，与最终实现和 TD-023 修复后的 spec 不一致。

**问题**
- 未跟踪副本文件会污染后续工作区，后续 agent 如果批量暂存 `scripts/engineering`，可能把无关副本带入 PR。
- TD-023 已修正核心行为表和代码示例，但 TD-020 spec / plan 中仍有少量旧目标或旧风险表述，会继续误导后续 AI IDE 对 `qwen` / `dashscope` alias 边界的判断。

**完成标准**
- 工作区不再出现未跟踪的 `scripts/engineering/check_engineering_docs 2.py` 副本文件。
- TD-020 spec 的目标、测试覆盖和 4.2 要点统一改成：resolver 复用 `factory.RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()` 这两个公开事实源；`resolver_default_provider()` 采用 resolver 专用 alias 判定，不复用 `_normalize_default_provider`。
- TD-020 spec 和 plan 不再把 `dashscope` 描述成 resolver alias 或 `dashscope → qwen` / `qwen → dashscope` 的 resolver 归一化路径。
- 不改业务代码。

**验证方式**
- `git status --short --branch` 不显示 `scripts/engineering/check_engineering_docs 2.py`。
- `rg -n "复用 .*归一化|qwen→dashscope|dashscope → qwen|dashscope.*归一化路径|翻译回 \`qwen\`" docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md` 不再命中旧误导表述；若命中 factory 内部 `_normalize_default_provider` 的历史现状说明，必须语义明确为 factory 内部行为，不是 resolver 行为。
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --name-status` 只包含文档和副本清理相关变更，不包含业务代码。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code）。docs-only + 副本清理，无业务代码变更。
  1. 删除未跟踪副本 `scripts/engineering/check_engineering_docs 2.py`（与正式实现 SHA-256 一致，正式文件保留）。
  2. `docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md` §3.1 目标第 2 条改为：`provider_resolver` 复用 `factory` 暴露的 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()` 两个公开事实源，并显式说明 `resolver_default_provider()` 走 resolver 专用 alias 判定、不复用 `factory._normalize_default_provider`。
  3. 同 spec §3.1 目标第 4 条改为：测试覆盖 `resolver_default_provider()` 的 resolver alias 判定（含 `dashscope` / `siliconflow` / `openai` 等不在子集时返回 `None`），并明确”resolver 不做 `qwen → dashscope` 翻译”。
  4. 同 spec §4.2 要点改为：`qwen` alias 由 `factory.RESOLVER_PROVIDER_NAMES` 集中声明；resolver 路径**不**走 `dashscope` 归一化路径，也**不**复用 `factory._normalize_default_provider`。
  5. `docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md` 范围段改为：复用 `factory` 公开事实源 `RESOLVER_PROVIDER_NAMES` 与 `resolver_default_provider()`（resolver 走专用 alias 判定，不复用 `factory._normalize_default_provider`）。
  6. 同 plan TASK-1 风险段改为：明确 `_normalize_default_provider` 是 factory 内部 helper，`resolver_default_provider()` 不复用它，且不翻译回 `qwen`。
- 验证摘要（按 `quality-gates.md#完成门禁`）：
  - 已运行：`scripts/check-engineering-docs` 退出码 0（`engineering docs checks passed`）。
  - 已运行：`git status --short --branch` 不再包含 `scripts/engineering/check_engineering_docs 2.py`（已 `rm`）。
  - 已运行：`rg -n "复用 .*归一化|qwen→dashscope|dashscope → qwen|dashscope.*归一化路径|翻译回 \`qwen\`" docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md` 命中 2 行（spec L137、plan L46），均为 factory 内部 `_normalize_default_provider` 行为说明且明确为"不"走 / "不"复用 / "不"翻译回的反向表述，符合"白名单例外"约束。
  - 已运行：`test -f docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md` → 退出码 0。
  - 已运行：`git diff --name-status` 仅包含 4 个文档变更（`docs/03-engineering-governance/current-work.md`、`docs/03-engineering-governance/technical-debt.md`、`docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md`、`docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md`），无业务代码变更。
  - 未运行：lint / 业务测试 —— TD-024 任务范围是 docs-only + 副本清理，按 `quality-gates.md#验证表述规范` 不强制后端 lint 或 pytest 复跑。

### TD-026: 共享组件 `liquid-card` 残留验证

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 前端 / 设计系统 |
| 事实源 | [PR #58](https://github.com/MarkDanile/MetaEduBase/pull/58) |

**证据**
- TD-025 完成（2026-06-05）后，业务视图的 `liquid-card` 已全部迁到 `ui-panel`（除 `LoginView` 品牌背景与 `HomeView` 1 处 `liquid-card-scan` 装饰保留外）。
- 任务卡线索的"4 个共享组件 22 处 `liquid-card` 残留"源于 TD-008 完成时的快照，把 `liquid-card` 与 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 都计入了同一类。
- `rg -n "liquid-card" packages/web/src/components/FieldEditor.vue packages/web/src/components/KGDetailPanel.vue packages/web/src/components/ConfirmDialog.vue packages/web/src/components/KGGraph.vue` 实测：**0 命中**。

**问题**
- 任务卡残留量与实际不符的规律在 TD-025 切片 1/2/3 已经出现 3 次（`TemplateModal` / `TemplateEditorView` 实测 0 处），TD-026 共享组件同样：写 22 处、实测 0 处。
- 如果不验证就按原任务卡 22 处直接动手，会强行"扩大设计系统范围"去替换 4 个共享组件里的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` —— 这些类没有 `ui-*` 等价物，需要先扩设计系统（已拆为 TD-027）。

**完成标准**
- 严格按 `rg` 验证 4 个共享组件（`FieldEditor` / `KGDetailPanel` / `ConfirmDialog` / `KGGraph`）的 `liquid-card` 命中数为 0。
- 任务卡总览表与详情段状态从 `⚫ 待办` / 缺失 改为 `🟢 完成`。
- `coding-style.md` 迁移清单加 4 个共享组件行（标记 `🟢 完成`、备注"实测 0 处 `liquid-card`，本组件未使用 `liquid-card` 容器"）。
- `current-work.md` 当前进行中清空；下一批候选加上 TD-027。
- 4 个共享组件里现有的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 仍按 TD-008 规则保持兼容（不在本债范围；留给 TD-027 启动时再决定是否替换）。

**验证方式**
- `rg -n "liquid-card" packages/web/src/components/FieldEditor.vue packages/web/src/components/KGDetailPanel.vue packages/web/src/components/ConfirmDialog.vue packages/web/src/components/KGGraph.vue` → 0 命中。
- `rg -c "liquid-card" packages/web/src/components/` → 每个文件 0 命中。
- `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0（本 PR 不改业务代码，但保持基线）。
- `scripts/check-engineering-docs` 退出码 0。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code）。docs-only PR，0 业务代码变更。
  1. `docs/03-engineering-governance/technical-debt.md` 任务总览表新增 TD-026（🟢 完成）/ TD-027（⚫ 待办）两行；任务详情区追加 TD-026 任务卡（包含证据、问题、完成标准、验证方式、交付记录）和 TD-027 任务卡（新债登记，包含完成标准、验证方式）。
  2. `docs/03-engineering-governance/01-rules/coding-style.md` 业务页面迁移清单（原表格）后追加"共享组件迁移清单"小节，列出 4 个共享组件与"实测 0 处 `liquid-card`"的说明。
  3. `docs/03-engineering-governance/current-work.md` 当前进行中清空；下一批候选任务加 TD-027；最近完成区追加 TD-026 一行。
- 验证摘要：4 条 `rg` 断言全过；`pnpm typecheck / lint / build` 退出码 0；`scripts/check-engineering-docs` 退出码 0；`git diff --name-status` 仅包含 3 个 docs 文件。

### TD-027: 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展）

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 前端 / 设计系统 |
| 事实源 | [PR #59](https://github.com/MarkDanile/MetaEduBase/pull/59) |

**证据**
- TD-008（2026-06-05）建立 `ui-page-shell` / `ui-page-section` / `ui-panel` / `ui-toolbar` / `ui-interactive-row` 5 个共享类，但**没有** button / input / tag / dialog 的对应物。
- TD-025 / TD-026 业务视图与共享组件里的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 仍按例外清单保持兼容。
- 4 个共享组件（`FieldEditor` 12 处 `liquid-input` + 3 处 `liquid-btn-ghost` / `KGDetailPanel` 2 处 `liquid-btn-ghost` + 3 处 `liquid-tag-*` / `ConfirmDialog` 4 处 `liquid-btn/dialog*` / `KGGraph` 1 处 `liquid-card` —— 但 `KGGraph` 的 `liquid-card` 实测 0 命中，仅有 1 处 `liquid-card` 提及在任务卡中）与 9 个业务视图里的存量使用，是设计系统迁移的下一段路径。

**问题**
- `ui-*` 体系目前只有"容器"层（`ui-page-shell` / `ui-panel` 等），没有"原子"层（button / input / tag / dialog）。如果后续要做"全 `ui-*` 化"或"未来业务视图逐步替换 `liquid-input` / `liquid-btn-*` 等"，需要先把这 4 类原子控件补齐。
- 4 个共享组件继续用 `liquid-input` / `liquid-btn-*` 是历史"兼容例外"妥协，不是设计系统目标状态。

**完成标准**
- **最小范围（必选）**：仅在 `main.css` 追加以下共享类（不替换业务视图与共享组件里的存量使用）：
  - `ui-input`：替代 `liquid-input`；复用现有 `--color-*` / `--radius-*` / `--shadow-*` / `--duration-*` token。
  - `ui-btn` / `ui-btn-primary` / `ui-btn-ghost` / `ui-btn-danger`：替代 `liquid-btn*`；token 化；`ui-btn-primary` 在 `liquid` 主题下走 `:root[data-theme="liquid"] .ui-btn-primary` 玻璃感覆盖（与 `ui-panel` 切片 1 行为一致）。
  - `ui-tag` / `ui-tag-blue` / `ui-tag-green` / `ui-tag-amber` / `ui-tag-purple`：替代 `liquid-tag*`；5 个变体。
  - `ui-dialog` / `ui-dialog-overlay`：替代 `liquid-dialog*`。
- 4 主题视觉表现不发生可观察退化（`ui-*` 颜色全部 token 化、自动适配）。
- `liquid-*` 类全部保留作为兼容别名（不删不动）。
- 不替换业务视图与共享组件里的存量 `liquid-input` / `liquid-btn-*` 等（这部分留 TD-028 接力）。
- `coding-style.md#迁移说明` 增补 4 类 `ui-*` 共享类用途、`ui-*` 优先 / `liquid-*` 兼容的边界、新增/修改 UI 的优先级（与 TD-008 同结构）。
- `scripts/check-engineering-docs` 退出码 0。

**验证方式**
- `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0。
- `rg -n "ui-input|ui-btn|ui-tag|ui-dialog" packages/web/src/assets/css/main.css` 命中新增类定义。
- `rg -n "ui-(input|btn|tag|dialog)" packages/web/src/views/ packages/web/src/components/` → 0 命中（本债不替换存量）。
- `rg -n "liquid-(input|btn|primary|ghost|danger|tag|dialog)" packages/web/src/` 仍命中存量（保持兼容）。
- 4 主题（liquid / ink / navy / notion）下 `LoginView`（仅 `liquid-input` / `liquid-btn-primary` 实际显示）手工验收视觉不退化。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code），PR #59，merge commit `040f7ad`。
  - `packages/web/src/assets/css/main.css` 新增 12 个 `ui-*` 原子控件共享类：`ui-input`、`ui-btn` / `ui-btn-primary` / `ui-btn-ghost` / `ui-btn-danger`、`ui-tag` / 4 个颜色变体、`ui-dialog-overlay` / `ui-dialog`。
  - 新增 `--overlay-bg` / `--btn-ripple` 主题 token，避免 `ui-*` 类复制历史 `rgba(...)` 硬编码。
  - `docs/03-engineering-governance/01-rules/coding-style.md` 同步扩展迁移说明，明确容器层与原子控件层的关系。
  - 业务视图与共享组件存量替换已拆到 TD-028 并完成。
  - 验证摘要：`pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0；`scripts/check-engineering-docs` 退出码 0。

### TD-028: 业务视图与共享组件的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 存量替换

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 前端 / 设计系统 |
| 事实源 | [PR #61](https://github.com/MarkDanile/MetaEduBase/pull/61) |

**证据**
- TD-027（2026-06-05，PR #59 / merge commit `040f7ad`）落地 12 个 `ui-*` 原子控件共享类（`ui-input` / `ui-btn` 4 类 / `ui-tag` 5 类 / `ui-dialog` 2 类），与 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 是 token-for-token 1:1 镜像。
- 业务视图与共享组件的存量 `liquid-*-atomic` 残留（`rg -c "liquid-(input|btn|tag|dialog)" packages/web/src/views/ packages/web/src/components/` 共 119 处）。

**问题**
- 业务视图与共享组件仍以 `liquid-*-atomic` 为主，`ui-*-atomic` 在业务代码里 0 处使用（TD-027 完成后已 grep 确认），设计系统迁移只完成一半。
- 不替换存量 → `ui-*` 体系实际上没被采用；后续每次新增 UI 都会重蹈 `liquid-*` 覆辙。

**完成标准**
- 业务视图（10 个）+ 共享组件（3 个）共 13 文件中，所有 `liquid-input` / `liquid-btn` / `liquid-btn-primary` / `liquid-btn-ghost` / `liquid-btn-danger` / `liquid-tag` / `liquid-tag-blue` / `liquid-tag-green` / `liquid-tag-amber` / `liquid-tag-purple` / `liquid-dialog` / `liquid-dialog-overlay` 替换为对应的 `ui-*` 类。
- `\`liquid-tag-${color}\`` 模板字符串（5 处）替换为 `\`ui-tag-${color}\``。
- `LoginView` 的 `liquid-input` / `liquid-btn-*` 也参与替换；`LoginView` 品牌背景与 `--_login-brand-gradient` 仍按 TD-008 规则保持兼容。
- 4 主题视觉不发生可观察退化（`ui-*` 与 `liquid-*` 在 `main.css` 中 byte-identical 镜像）。
- `main.css` 中 `liquid-*` 声明保持兼容别名（不动）。
- `HomeView` / `KGGraph` 0 处 `liquid-*` 残留（TD-025 切片 3 + 历史已清），跳过。

**验证方式**
- `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- `rg -c "ui-(input|btn|tag|dialog)" packages/web/src/views/ packages/web/src/components/` 12 文件全部 > 0；`rg -c "liquid-(input|btn|tag|dialog)" packages/web/src/views/ packages/web/src/components/` 每个文件 0 命中。
- `rg 'ui-tag-\$\{color\}' packages/web/src/views/ packages/web/src/components/` 命中 5 处（DatabaseView 2 + FileDetailView 2 + ResourceLibraryView 1），模板字符串迁移到位。
- 4 主题（liquid / ink / navy / notion）下业务视图与共享组件手工验收视觉不退化；沙箱无浏览器时降级为 typecheck + lint + `git diff` 自检。

**交付记录**
- 2026-06-05 完成（接手工具：Claude Code）。一次性 token-for-token 机械替换，1 个原子提交。
  - 12 文件 119 处 `liquid-*-atomic` → `ui-*-atomic` 替换（从长到短顺序：`liquid-btn-primary/ghost/danger` → `liquid-btn` 基类 → `liquid-tag-blue/green/amber/purple` → `liquid-tag` 基类 → `liquid-input` → `liquid-dialog-overlay` → `liquid-dialog`），保证 `liquid-btn` 不被 `liquid-btn-primary` 部分覆盖。
  - 5 处 `\`liquid-tag-${color}\`` 模板字符串（DatabaseView 2 + FileDetailView 2 + ResourceLibraryView 1）随 sed 一起替换为 `\`ui-tag-${color}\``；运行时 `color` 仅 blue/green/amber/purple（4 个都有 `ui-tag-*` 对应；`red` 走 inline `text-red-500` 不经过此模板，安全）。
  - 排除 `HomeView`（0 处）、`KGGraph`（0 处）、`main.css`（`liquid-*` 声明保持兼容别名）、`LoginView` 品牌背景（TD-008 例外保留，仅 input/btn 参与替换）。
- PR #61，merge commit `349c743`。

### TD-029: 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 前端 / 类型 / 交付 |
| 事实源 | TD-009 复核（2026-06-06）；[PR #67](https://github.com/MarkDanile/MetaEduBase/pull/67)；[Spec](../02-delivery-plans/01-specs/2026-06-06-td-029-shared-schema-gate.md)；[Plan](../02-delivery-plans/02-plans/2026-06-06-td-029-shared-schema-gate-plan.md) |

**证据**
- `pnpm --filter @metaedu/web typecheck` 当前退出码 2，报 `TS6305`：`packages/shared/dist/schemas/document.d.ts` 未从 `packages/shared/src/schemas/document.ts` 构建。
- `pnpm typecheck` 当前同样失败，说明不是单包命令误用，而是当前 monorepo 门禁真实不通过。
- `pnpm --filter @metaedu/web build` 当前退出码 2，报相同 `TS6305`，并额外报 `packages/web/src/views/resource/FileDetailView.vue:107` 的 `TS2345`：`number` 不能传给 `templateFieldLabel(key: string)`。
- `packages/shared/package.json` 当前没有 `build` script，`packages/shared/dist/` 也未入库；`packages/web/tsconfig.json` 通过 project reference 依赖 `../shared`。
- TD-009 交付记录当前声明 `pnpm --filter @metaedu/web typecheck` 退出码 0，与复核时实际输出不一致。

**问题**
- TD-009 引入 shared schema 后，前端 typecheck / build 门禁没有真正打通，导致“契约治理”这一步本身破坏了交付链路。
- `FileDetailView` 的 `template` 展示分支仍有真实类型错误，说明契约窄化后的 UI 使用点没有完全收口。
- 验证记录把失败命令写成通过，会误导后续 AI IDE 和人工协作者对当前主分支质量状态的判断。

**完成标准**
- `pnpm --filter @metaedu/web typecheck` 退出码 0。
- `pnpm typecheck` 退出码 0。
- `pnpm --filter @metaedu/web build` 退出码 0。
- shared schema 的消费方式与 workspace 构建方式一致：要么补齐 `@metaedu/shared` 的构建/声明产物链路，要么调整 imports / tsconfig，使 web 在不依赖未生成 `dist/*.d.ts` 的情况下稳定 typecheck。
- 修复 `FileDetailView` 中 `templateFieldLabel(key)` 的类型错误，不再依赖隐式 `string` 假设。
- 同步修正 TD-009 的交付记录与验证摘要，确保文档声明和真实命令输出一致。

**验证方式**
- `pnpm --filter @metaedu/shared typecheck`
- `pnpm --filter @metaedu/web typecheck`
- `pnpm typecheck`
- `pnpm --filter @metaedu/web build`
- `scripts/check-engineering-docs`

**交付记录**
- 2026-06-06 完成（接手工具：Claude Code）。删除 `packages/web/tsconfig.json` 中对 `../shared` 的 project reference，让 TS 通过 `@metaedu/shared` 的 `exports` 直接读 `src/*.ts`，消除 `TS6305`；`FileDetailView.vue:107` 的 `templateFieldLabel(key)` 改为 `templateFieldLabel(String(key))`，把 `v-for` 推断的 `string | number` 收敛到 `string`，并对未来 templateData 类型变化做防御；同步修正 TD-009 交付记录验证摘要表述。
- 行为变化声明：无 runtime 行为变化；仅影响 TypeScript 编译时模块解析路径与一个 v-for key 的类型收敛。
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/web typecheck` 退出码 0；`pnpm typecheck` 退出码 0；`pnpm --filter @metaedu/web build` 退出码 0；`pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed（TD-009 后端回归）；`scripts/check-engineering-docs` 退出码 0。

### TD-030: RecallChannel Protocol vs concrete signature drift on parameter names

状态：⚫ 待办

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 后端 / 测试 |
| 事实源 | REQ-003 / 2026-W23 iteration（commit `bccde6d`） |

**证据**
- Protocol 声明：`packages/server-python/app/shared/domain/recall_channel.py:22-32` `RecallChannel.recall` 形参为 `query: str, ner_result: NERResult, tenant_id: str, top_k: int = 5`，**不**含 `session: AsyncSession`。
- 具体类 1：`packages/server-python/app/contexts/knowledge/application/recall_service.py:23-30` `PgVectorRecallChannel.recall` 形参为 `query: str, _ner_result: NERResult, tenant_id: str, session: AsyncSession, top_k: int = 5`。
- 具体类 2：`packages/server-python/app/contexts/knowledge/application/recall_service.py:67-74` `PgKeywordRecallChannel.recall` 形参为 `query: str, _ner_result: NERResult, tenant_id: str, session: AsyncSession, top_k: int = 5`。
- 具体类 3：`packages/server-python/app/contexts/knowledge/application/recall_service.py:124-131` `PgMetadataRecallChannel.recall` 形参为 `_query: str, ner_result: NERResult, tenant_id: str, session: AsyncSession, top_k: int = 5`。
- 遮蔽漂移的契约测试：`packages/server-python/tests/contexts/ai/test_recall_channels_contract.py:40` 使用 `{p.lstrip("_") for p in sig.parameters}`，对下划线前缀做了归一化；无此 `lstrip` 退路，测试会在下划线命名的参数上失败。计划原文是 `list(sig.parameters)`，实现采用了 `lstrip` 退路（被 spec compliance reviewer 判定为可接受）。

**问题**
- Protocol 形参与三个具体类的形参存在两层漂移：① 下划线前缀（`ner_result` vs `_ner_result` / `query` vs `_query`）；② 是否包含 `session: AsyncSession`（Protocol 没有；具体类有）。
- 若后续加 `runtime_checkable` 严格检查或 `mypy --strict-override` / `pyright` 严格契约校验，漂移会让 Protocol 与具体类不再互相满足。
- 契约测试使用 `lstrip("_")` 退路把漂移遮蔽，掩盖了真实漂移。
- Protocol 的契约本身不够清晰：调用方按 Protocol 推不出还要再传 `session`，也无法预期哪些参数允许下划线前缀。

**完成标准**
- 选择以下任一路线并落地（不允许“靠 `lstrip` 继续遮蔽”）：
  - 路线 A（推荐）：把具体类的形参改成 Protocol 同形参（`query` / `ner_result` 不加下划线、`session: AsyncSession` 显式纳入 Protocol），同时调用方按新 Protocol 传 `session`。
  - 路线 B：把 Protocol 形参改成 `_query` / `_ner_result` 下划线风格 + 显式 `session`，承认“具体类的下划线是私有约定”并由 Protocol 显式声明。
- 无论哪条路线，`packages/server-python/tests/contexts/ai/test_recall_channels_contract.py:40` 都要去掉 `lstrip("_")` 退路，改回 `set(sig.parameters)`（或 `{p for p in sig.parameters}`）并继续通过。
- `app/shared/domain/recall_channel.py` 的 Protocol 注释说明 `session` 的来源（注入 vs 调用方传入），避免再次漂移。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_recall_channels_contract.py -v` 退出码 0，且不依赖 `lstrip("_")` 退路（grep `lstrip` 在该文件 0 命中）。
- `RecallChannel` Protocol 形参与三个具体类形参一致（modulo 默认值）。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q` 退出码 0（无回归）。
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0。

**交付记录**
- 2026-06-07 由 REQ-003 Task 5 收口时入账（commit `3bf8c10`）。任务详情见 `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` 与 `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md`。

### TD-031: RAG 质量测试文件的预存 ruff 警告

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 测试 / 质量门禁 |
| 事实源 | REQ-007 Task 4 复核 |

**证据**
- `packages/server-python/tests/contexts/ai/test_frequency_fusion.py:1` 存在 F401：`import pytest` 未使用（REQ-003 PR #74 留下的预存问题）。
- `packages/server-python/tests/contexts/ai/test_recall_channels_contract.py:1` 存在 I001：import 块未按 ruff 规则排序（REQ-003 PR #74 留下的预存问题）。
- 两个问题均带 `[*]` 标记，`ruff check --fix` 可自动修复。

**问题**
- 仓库 `docs/03-engineering-governance/01-rules/coding-style.md` 与 `quality-gates.md#完成门禁` 期望 `ruff check` 在改动范围内通过；遗留警告会让 `scripts/check-engineering-docs` 之外的本地 ruff 检查产生噪声。
- 这两个文件**不是 REQ-007 引入的**，但落到 REQ-007 的 AC-3"测试覆盖描述准确"边界——描述准确的门禁干净也是描述准确的一部分。

**完成标准**
- `cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/ai/` 退出码 0。
- `pytest tests/contexts/ai/` 全绿。
- 2 个测试文件改动幅度仅 -1 / -1 行（`pytest` import 删除 + import 块重排），无业务代码或行为变化。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/ai/` 退出码 0。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/ -q` 全绿。

**交付记录**
- 2026-06-08 由 REQ-007 Task 4 收口时入账并修复，随 [PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) 合并到 `main`（merge commit `45db478b`）。任务详情见 `docs/01-product-planning/05-requirements/REQ-007-req-003-rag-quality-gate-follow-up.md` 与 `docs/02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md`。
- 行为变化声明：无；`ruff check --fix` 是 `[*]` 标记的自动修复，仅删除 1 行 `import pytest` + 1 行 import 排序，无业务代码或测试行为变化。
- 验证摘要：`cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/ai/` 退出码 0（`All checks passed!`）；`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/ -q` 38 passed。

### TD-032: 治理超大源码文件并建立文件规模拆分原则

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 可维护性 / 架构 / 前端 / 后端 / 工程治理 |
| 事实源 | 2026-06-08 源码行数扫描 |

**证据**
- 扫描命令：`rg --files packages scripts tests -g '*.py' -g '*.ts' -g '*.tsx' -g '*.vue' -g '*.css' -g '*.scss' | xargs wc -l | sort -nr | head -40`。
- 当前超过 1000 行：`packages/web/src/assets/css/main.css` 1343 行；`scripts/engineering/check_engineering_docs.py` 1003 行。
- 当前超过 500 行的业务或工程源码：`packages/server-python/app/contexts/document/application/tasks.py` 929 行；`packages/web/src/views/database/DatabaseView.vue` 701 行；`packages/server-python/app/contexts/structured_data/application/tasks.py` 671 行；`packages/web/src/views/admin/TemplateModal.vue` 665 行。
- 500 行附近的高风险候选：`packages/server-python/app/contexts/document/interfaces/api/router.py` 494 行；`packages/web/src/views/resource/ResourceLibraryView.vue` 490 行。

**问题**
- 超大单文件会显著增加阅读成本、变更冲突概率和回归风险，后续 AI IDE 或人工接手时也更容易遗漏状态、职责边界和验证范围。
- 多职责逻辑集中在同一文件，会削弱测试切片、复用边界和代码审查质量。
- 若继续在超过 500 行或 1000 行的文件上叠加功能，技术债会随需求迭代持续放大。

**完成标准**
- 建立超大源码文件基线清单，并明确哪些属于业务源码、工程脚本、历史兼容样式或可接受例外。
- 对超过 1000 行的文件优先拆分或登记例外原因；后续不得继续在这些文件中堆叠新职责。
- 对超过 500 行的业务源码按职责拆分，或在任务卡 / plan 中说明暂缓拆分原因和后续切片。
- 大需求或跨模块开发进入实现前，先给目标目录和文件结构，再生成代码。
- `coding-style.md` 中的文件规模与拆分原则被后续开发遵循。

**验证方式**
- 重跑源码行数扫描命令，确认目标文件行数下降或例外已登记。
- 被拆分模块对应的 `ruff` / `mypy` / `typecheck` / 单元测试或行为验收通过。
- `scripts/check-engineering-docs` 通过。

**交付记录**
- 2026-06-08 切片 1 已合并：[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92)，merge commit `3de4de5`。
  - 落地 5 个文件（2 改 3 新）：spec / plan / 行数基线 / `coding-style.md#文件规模与职责边界` 段尾扩写 3 个小节 / `current-work.md` 任务卡升级；零业务代码变更。
  - 验证：`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0；`gh pr checks 92` no checks reported（PR #92 未配置 GitHub Actions；本地门禁已通过）。
  - 后续切片 2-4（>1000 工程脚本 / >500 后端 tasks / >500 前端视图）由各自独立 spec / plan 承载；任务整体待全部切片交付后改为 `🟢 完成`。
- 2026-06-08 切片 2 已合并：[PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93)，merge commit `7e468fb`。
  - 落地 13 个文件（1 改 12 新）：入口主文件 `scripts/engineering/check_engineering_docs.py` 1003 → 72 行 + 8 个聚焦 `checks/*.py` 模块（38-233 行/个）+ `checks/__init__.py` 注册表 + spec / plan / `current-work.md` 任务卡刷新。
  - 验证：`python scripts/engineering/check_engineering_docs.py --root .` 退出码 0，stdout `engineering docs checks passed`；`scripts/check-engineering-docs` 退出码 0，stdout `engineering docs checks passed`；`pytest tests/engineering/test_check_engineering_docs.py -v` 16 passed；`git diff --check` 退出码 0；`gh pr checks 93` no checks reported（PR #93 未配置 CI；本地门禁已通过）。
  - 后续切片 3-4 仍未开工：后端 `document|tasks.py` + `structured_data|tasks.py` 走 TD-005 模式；前端 `DatabaseView.vue` + `TemplateModal.vue` 抽子组件。任务整体保持 `🔵 就绪`，待全部切片交付后改为 `🟢 完成`。
- 2026-06-08 切片 3 已合并：[PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94)，merge commit `5beb938`。
  - 落地 18 个文件（4 改 14 新 2 删 删原 2 个 tasks.py）：`document/application/tasks.py` 929 → 0 行 + `document/application/tasks/` 包 9 文件 1000 行；`structured_data/application/tasks.py` 671 → 0 行 + `structured_data/application/tasks/` 包 5 文件 746 行；spec / plan / `current-work.md` 任务卡 / `tests/contexts/document/test_extract_template_selection.py` 物理读路径跟随包形式。
  - 验证（cwd=packages/server-python）：`pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q` → **55 passed**（12 + 36 + 7）；`ruff check app/ tests/` → All checks passed!（12 I001 由 `ruff --fix` 自动修）；`python -c "from app.contexts.X.application.tasks import (...)"` 4/4 外部 import 路径 OK；`scripts/check-engineering-docs` 退出码 0；`gh pr checks 94` no checks reported（PR #94 未配置 CI；本地门禁已通过）。
  - 实施时 3 处小修正（spec 末尾"实施记录"段已记录）：`__init__.py` re-export 2 helper / `extract_template.py` 顶部 logger name 硬编码 / `test_extract_template_selection.py` 物理读路径跟随包形式。3 处均零业务逻辑变化。
  - 后续切片 4（`DatabaseView.vue` 701 + `TemplateModal.vue` 665 抽子组件）仍未开工。任务整体保持 `🔵 就绪`，待切片 4 全部交付后改为 `🟢 完成`。
- 2026-06-08 切片 4 已合并：[PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95)，merge commit `d4d2720`。
  - 落地 12 个文件（2 改 10 新）：`DatabaseView.vue` 701 → 320（-54%）+ 6 个聚焦子组件（`DatasetListPanel` 132 / `KgOverviewPanel` 52 / `DatasetDetailMetaBar` 40 / `PipelineStatusPanel` 101 / `DatasetTabsPanel` 139 / `UploadDatasetDialog` 116）；`TemplateModal.vue` 665 → 333（-50%）+ 2 个聚焦子组件（`TemplateFormFields` 255 / `TemplateAiPanel` 207）；spec / plan / `current-work.md` 任务卡。
  - 验证（cwd=packages/web）：`pnpm typecheck` 退出码 0（零输出）；`pnpm lint` 退出码 0（零 warning）；`pnpm build` 退出码 0，✓ built in 2.72s；`DatabaseView.js` 28.45 kB（vs baseline 25.22 kB，+13%）；`TemplateListView.js` 27.63 kB（vs baseline 25.44 kB，+9%）；`scripts/check-engineering-docs` 退出码 0。
  - 实施时 5 处小修正（与切片 1-3 经验一致）：`v-model` 改 `:value + @input` 显式 emit 链（4 处） + `PipelineStatusPanel` helper 改"脚本级闭包捕获 tasks" + `UploadDatasetDialog` hidden input 用 ref + `.click()` 内部触发 + `TemplateFormFields.ensureIds` dead code 移除 + `TemplateAiPanel` 独立实现 ensureIds。零业务逻辑变化。
  - 任务整体进入收口：1 切片（1）后端 tasks 拆分 + 1 切片（2）工程脚本拆分 + 1 切片（3）业务后端 tasks 拆分 + 1 切片（4）前端视图拆分。**TD-032 整体收口**：4 切片全部合并，TD-032 状态改为 `🟢 完成`。
- 2026-06-08 切片 1-4 收口后回写 baseline（commit `200e342`）：
  - 更新 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：「合规样例」段扩展 5 项（`TemplateModal.vue` 333 / `DatabaseView.vue` 320 / `chunker.py` 320 / `ResourceView.vue` 305 / `AiChatView.vue` 304）；「500 行附近高风险候选」段新增 `FileDetailView.vue` 416（新出现接近 500 候选）；新增「切片 5+ 候选清单」段（`document/router.py` 494 P2 + `ResourceLibraryView.vue` 490 P2 + `FileDetailView.vue` 416 P3 + `main.css` 1343 P3）；「扫描历史」段追加本次回写条目。
  - 验证：`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0；`git diff --name-status` 仅包含 `td-032-source-file-sizes.md` + `current-work.md` 两文件。
  - 任务整体保持 `🟢 完成`；切片 5+ 候选需独立 spec / plan 启动（本回写仅登记，不启动新切片）。
- 2026-06-08 切片 5 已合并：[PR #96](https://github.com/MarkDanile/MetaEduBase/pull/96)，merge commit `4b03064`。
  - 落地 9 个文件（1 改 8 新）：`document/interfaces/api/router.py` 494 → 29 行（-94%）+ 4 个聚焦子 router `folders.py` 123 / `files.py` 231 / `chunks.py` 43 / `tasks.py` 121；spec / plan / `current-work.md` 任务卡 / `backlog.md` 登记 DOC-041 候选。
  - 验证（cwd=packages/server-python）：`pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q` → **115 passed**（沙箱本次连到 metaedu_test 数据库；baseline 55 仅含 3 个子目录，本次全量覆盖）；`ruff check app/ tests/` → All checks passed!（5 I001 已手工修正：4 个子 router 文件 + 主 router 删 1 个空行 + `parse_document` import 注释缩短避开 line-length 100）；import 探针 all import OK（`router as document_router` + `parse_document` + 4 个子 router 模块）；`@router.*` endpoint 数 13 个（与 baseline 一致）。
  - 实施时 3 处小修正（与切片 1-4 经验一致）：`router.py:16` 顶层 re-export `parse_document` 让 `patch()` 仍工作 / 4 个子 router 文件中 `from sqlalchemy import text` 保留函数内 import / 4 个子 router 文件双空行收紧。
  - **pre-existing 重复路由**（`router.py` 与 `task_router.py` 各定义 `GET /files/{file_id}/tasks` + `POST /files/{file_id}/retry`）**不**在本切片处理；已登记为 `DOC-041` 候选（`docs/01-product-planning/04-backlog.md`），由独立 spec / plan 启动清理。
  - 任务整体保持 `🟢 完成`；TD-032 切片 1-5 全部合并。
- 2026-06-09 切片 6 已合并：[PR #97](https://github.com/MarkDanile/MetaEduBase/pull/97)，merge commit `6728151`。
  - 落地 6 个文件（1 改 5 新）：`ResourceLibraryView.vue` 490 → 286 行（-42%）+ 3 个聚焦子组件（`FolderTreePanel.vue` 142 / `FileListPanel.vue` 160 / `UploadOptionsDialog.vue` 51）；spec / plan / `current-work.md` 任务卡。
  - 验证（cwd=packages/web）：`pnpm typecheck` 退出码 0（零输出）；`pnpm lint` 退出码 0（零 warning；emit 名 kebab-case 化后无 `vue/v-on-event-hyphenation` 警告）；`pnpm build` 退出码 0，✓ built in 3.04s；`scripts/check-engineering-docs` 退出码 0。
  - 实施时 5 处小修正（与切片 4 / 切片 5 经验一致）：`v-model` 改 `:value + @input` 显式 emit 链（4 处 `v-model`）+ `fileInput` ref 在 `FileListPanel` 内部持有（沿用切片 4 `UploadDatasetDialog` 模式）+ emit 名 kebab-case 化（`update:new-folder-name` / `update:inline-renaming-name` / `update:filter-status` / `update:doc-type`）+ `flatFolders` computed 保留在主入口（避免子组件重复 walk 递归）+ `@click.stop` 在 menu 面板保持（避免事件冒泡到外层 button）。
  - 任务整体保持 `🟢 完成`；TD-032 切片 1-6 全部合并。
