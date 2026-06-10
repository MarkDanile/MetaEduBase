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
| TD-030 | RecallChannel Protocol vs concrete signature drift on parameter names | 🟢 完成 | P3 | 后端 / 测试 | REQ-003 / 2026-W23 iteration / [PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139) (`a934981`) |
| TD-031 | RAG 质量测试文件的预存 ruff 警告 | 🟢 完成 | P2 | 后端 / 测试 / 质量门禁 | [PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) |
| TD-032 | 治理超大源码文件并建立文件规模拆分原则 | 🟢 完成 | P2 | 可维护性 / 架构 / 前端 / 后端 / 工程治理 | 2026-06-08 源码行数扫描 |
| TD-033 | 拆分 `main.css` 设计系统级 CSS 模块 | 🟢 完成 | P2 | 前端 / 设计系统 / 可维护性 | [PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) (`25ca165`) + [行数基线](02-baselines/td-032-source-file-sizes.md) |
| TD-034 | `build_fields_desc` 在 `array + items=[]` 时丢失"成员为 object"提示 | 🟢 完成 | P3 | 后端 / LLM 抽取 / 可维护性 | REQ-005 / [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143) (`3077047` squash merge；代码随 DOC-042 一并合入 main；原 PR #142 已于 2026-06-10 由 DOC-055 关闭为 superseded，commit `1e9a012` 未独立合并) |
| TD-035 | 收口 REQ-005 新增测试文件 ruff 质量门禁 | 🟢 完成 | P2 | 后端 / 测试 / 质量门禁 | REQ-005 review / [PR #109](https://github.com/MarkDanile/MetaEduBase/pull/109) |
| TD-036 | `metaedu_test` 库 `document_tasks.updated_at` 列缺失（alembic 003 迁移与测试库 schema drift） | 🟢 完成 | P2 | 后端 / 测试 / 质量门禁 | REQ-006 Stage 1 探查 / [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) (`2780ff1`) |
| TD-037 | e2e 脚本无法直接走真实 Celery：沙箱无 Redis broker 时需 mock `chunk_document.delay` + patch `broker_url=memory://` | 🟢 完成 | P3 | 后端 / 测试 / 基础设施 | REQ-006 Stage 1 探查 / [PR #130](https://github.com/MarkDanile/MetaEduBase/pull/130) (`9419c4e`) |
| TD-038 | alembic 006 迁移用 `gin` operator class（`USING gin (doc_types gin)`），在全新 DB 上 `UndefinedObjectError` 阻塞 `alembic upgrade head` | 🟢 完成 | P2 | 后端 / 迁移 / 质量门禁 | TD-036 探查（并入 PR #122 一并修复） |
| DOC-051 | 一次性收口历史 plan 残留 TBD / `TD-???` / `未回填` 占位 | 🟢 完成 | P2 | 文档 / 工程流程 / 跨 AI 交接 | REQ-003 / REQ-004 / REQ-008 plan 残留占位扫描 / [PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124) (`d7a2ca7`) / DOC-055 收口跨事实源状态 |
| DOC-052 | 清理 `scripts/engineering/checks/_common.py` 中 `KNOWN_ISSUES` 残留的 TD-023 历史白名单 | 🟢 完成 | P3 | 文档 / 工程流程 / 跨 AI 交接 | 2026-06-09 全仓债务盘查 / [PR #128](https://github.com/MarkDanile/MetaEduBase/pull/128) (`3f39ec0`) |
| DOC-045 | 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | P2 | 文档 / 工程流程 / 跨 AI 交接 | TD-033 review / [#137](https://github.com/MarkDanile/MetaEduBase/pull/137) (`b815942`) |
| DOC-042 | 脚本化 TD-032 行数基线扫描 | 🟢 完成 | P2 | 文档 / 工程治理 / 工程脚本 | [Baseline](02-baselines/td-032-source-file-sizes.md) / [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143) |
| DOC-055 | 收口 DOC-042 / TD-034 PR 范围混入与事实源漂移 | 🟢 完成 | P1 | 文档 / 工程流程 / 质量门禁 | DOC-042 review / [Review Score Log](04-retrospectives/review-score-log.md) |
| TD-039 | 6 键保留集合在 TS 端抽到 `@metaedu/shared/schemas/document` + spec 单一来源落地 | ⚫ 待办 | P3 | 前端 / 共享 schema / 文档 | REQ-002-3 code review / 当前 `FileTabsPanel.vue:159-166` 硬编码 + spec 文字再列 1 次 / 后端 Python import 路径接入拆为 [TD-043](#td-043-打通后端-python-对-shared-schemasdocument-的-import-路径) |
| TD-040 | `FileTabsPanel.spec.ts` Vue 单元测试覆盖 AC-11（6 键过滤）/ AC-12（card 渲染 / 老数据隐藏 / layer none 分支 / version 为 null） | 🟢 完成 | P2 | 前端 / 测试 / 交付 | REQ-002-3 code review / [PR #167](https://github.com/MarkDanile/MetaEduBase/pull/167) (`c1cc0c9` squash merge) / 引入 vitest + @vue/test-utils + jsdom 首次前端单测基建 / 6 测试通过（5 AC-12 + 1 AC-11 加固）|
| TD-041 | FieldCard 递归渲染嵌套字段 + object children / array items 嵌套拖拽 | 🟢 完成 | P2 | 前端 / 架构 / 交付 | [PR #161](https://github.com/MarkDanile/MetaEduBase/pull/161) / [Spec](../02-delivery-plans/01-specs/2026-06-10-td-041-field-card-recursive-rendering.md) |
| TD-042 | REQ-002-2 后端集成测试在 PG 实例下验证（`test_template_reuse.py` 8 条用例） | 🟢 完成 | P2 | 后端 / 测试 / 交付 | REQ-002-2 交付时沙箱无 PG / [PR #159](https://github.com/MarkDanile/MetaEduBase/pull/159) / 修 007 迁移 inline FK 在 asyncpg 反射下的 PK 解析缺陷 / [PR TBD] |
| TD-043 | 打通后端 Python 对 `shared/schemas/document` 的 import 路径 | ⚫ 待办 | P2 | 后端 / 共享 schema / 基础设施 | 2026-06-10 并行批次 `td-039+td-040` 拆出（原属 TD-039 范围）/ 仓库无顶层 `metaedu` Python 包、`packages/shared/` 是 TS-only pnpm workspace 包，0 处 `import metaedu.shared.*` 命中 |
| DOC-056 | `check_req_status_consistency` 把父任务 `REQ-NNN` 与子任务 `REQ-NNN-K` 状态混聚到同一集合的算法 bug | 🟢 完成 | P2 | 文档 / 工程脚本 / 质量门禁 | REQ-002-3 收口 / 修复 `\bREQ-\d{3}\b` → `\bREQ-\d{3}(?:-\d+)?(?![-\d])` + 新增 `test_parent_and_child_req_with_different_status_do_not_collide` 锁定 / 顺带修 main `current-work.md:19` REQ-002-3 残留 Ready 行 |

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
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-015-databaseview-regressions.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-015-databaseview-regressions-plan.md), [等价矩阵](03-matrices/td-015-databaseview-equivalence.md), [PR #38](https://github.com/MarkDanile/MetaEduBase/pull/38), merge commit `f38fbbc` |

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
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-017-filedetailview-vue-query.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-017-filedetailview-vue-query-plan.md), [等价矩阵](03-matrices/td-017-filedetailview-equivalence.md), [PR #40](https://github.com/MarkDanile/MetaEduBase/pull/40), merge commit `5af2793` |

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
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-018-filedetailview-remaining.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-018-filedetailview-remaining-plan.md), [等价矩阵](03-matrices/td-018-filedetailview-remaining-equivalence.md), [PR #41](https://github.com/MarkDanile/MetaEduBase/pull/41), merge commit `8ad15e6` |

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
| 事实源 | [Spec](../02-delivery-plans/01-specs/2026-06-05-td-019-vue-query-self-reference.md), [Plan](../02-delivery-plans/02-plans/2026-06-05-td-019-vue-query-self-reference-plan.md), [等价矩阵](03-matrices/td-019-vue-query-self-reference-equivalence.md), [PR #42](https://github.com/MarkDanile/MetaEduBase/pull/42), merge commit `387d8f8` |

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

状态：🟢 完成

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
- 2026-06-10 完成（接手工具：Claude Code）。选任务卡推荐路线 A：`RecallChannel` Protocol 显式包含 `session: AsyncSession`，3 个具体类去除下划线前缀（`_query` → `query` / `_ner_result` → `ner_result`），契约测试去掉 `lstrip("_")` 退路并新增 `test_channel_recall_signature_matches_protocol` 严格校验 Protocol 形参与具体形参一致（modulo 默认值）。调用方 `app/contexts/knowledge/interfaces/api/ai_router.py:85` 已按 5 参数形式传 `session`，无需改动。[PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139)（merge `a934981`）。
  - `app/shared/domain/recall_channel.py` Protocol 新增 `session` 形参 + `AsyncSession` import + docstring 说明 `session` 由调用方注入（与现有 RAG 链路事务一致性约束一致）。
  - `app/contexts/knowledge/application/recall_service.py` 三个具体类去下划线前缀，3 行机械修改。
  - `tests/contexts/ai/test_recall_channels_contract.py` 新增 `test_channel_recall_signature_matches_protocol` 参数化 3 用例；保留 `test_channel_recall_signature_accepts_required_args` 作为最小覆盖。
- 验证摘要：`pytest tests/contexts/ai/test_recall_channels_contract.py -v` → 12 passed（基线 9 + 新增 3）；`pytest tests/contexts/ai tests/contexts/knowledge -q` → 60 passed；`pytest tests/ -q` → **228 passed**（基线 222 + 3）；`ruff check app/ tests/` → All checks passed!；`rg -n "lstrip" ...` → 0 命中（任务卡验证方式）；`scripts/check-engineering-docs` → engineering docs checks passed；`git diff --check` 干净。
- 行为变化声明：仅形参命名（去下划线前缀）与 Protocol 增 `session`；运行时行为不变；调用方签名已对齐无需改动。
- 2026-06-07 由 REQ-003 Task 5 收口时入账（commit `3bf8c10`）。任务详情见 `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md` 与 `docs/02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md`。
- 2026-06-10 跨事实源状态收口（PR #140）：技术债总览/详情翻 🟢 完成；Backlog REQ-003 行 "Protocol-vs-concrete drift 入账 TD-030" → 已收口 [PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139)；work-log REQ-003 详情行同步；review-score-log REQ-007 行扣分点 "TD-030 signature drift 仍开放" → 已收口。

**已知限制 / 后续接力（出账）**
- DOC-051 ([PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124)) 把 3 个 spec 的 `TD-???` 占位统一替换为 `TD-030（已锁定）` 字符串，但三处实际语义不同：
  - `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md:87` "FrequencyFusion.channel 重复/去重" 实为 AC-9 覆盖范围，与 RecallChannel signature drift 无关；
  - `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md:141` 与 `2026-W23-req-008-req-004-quality-follow-up.md:103` "L3 解析行为 / 空响应 / confidence 解析失败" 实为 REQ-008 spec 自身覆盖范围。
- 这3 处 "TD-030（已锁定）" 字面与本次收口的 `TD-030: RecallChannel Protocol vs concrete signature drift` 不是同一债；但已落在同一编号上，会误导后续 AI IDE 按"TD-030"去对照技术债总账时找不到对应事实。建议由独立 `DOC-xxx` 处理：(a) 重新核对 3 处占位的真实语义债；(b) 按需分配新 `TD-xxx` 编号或直接删除无效占位行；(c) 同步 `check_delivery_placeholders` 脚本补强"占位 → 编号"映射校验。本 TD-030 收口范围不含此项，仅登记发现。

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
- 扫描命令：`rg --files -0 packages scripts tests -g '*.py' -g '*.ts' -g '*.tsx' -g '*.vue' -g '*.css' -g '*.scss' -g '!**/.venv/**' -g '!**/uploads/**' -g '!**/node_modules/**' -g '!**/dist/**' | xargs -0 wc -l | sort -nr | head -40`。
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
- 2026-06-09 切片 7 已合并：[PR #98](https://github.com/MarkDanile/MetaEduBase/pull/98)，merge commit `3e7f827`。
  - 落地 4 个文件（1 改 3 新）：`FileDetailView.vue` 416 → 181 行（-57%）+ 3 个聚焦子组件（`FileMetaBar.vue` 41 / `FileDetailPipelineStatusPanel.vue` 97 / `FileTabsPanel.vue` 171）。
  - 验证（cwd=packages/web）：`pnpm typecheck` 退出码 0（零输出）；`pnpm lint` 退出码 0（零 warning）；`pnpm build` 退出码 0，✓ built in 3.00s；`scripts/check-engineering-docs` 退出码 0。
  - 实施时 3 处小修正（与切片 4 / 切片 6 经验一致）：`v-model` 改 `:value + @input` 显式 emit 链 + 子组件内部 helper（templateFieldLabel/getFieldLabel + labels 回退硬编码表）迁到 `FileTabsPanel` 内部 + `stepBgClass`/`stepIcon` 等 5 helper 迁到 `FileDetailPipelineStatusPanel` 内部（独立于切片 4 `PipelineStatusPanel` 因 document 5 步 vs structured_data 4 步 pipeline 不可复用）。
  - **TD-032 整体最终收口**：7 切片全部合并；500 附近全部拆分到位（document/router.py 29 / ResourceLibraryView 286 / FileDetailView 181）；仅 `main.css` 1343 保留 `🔵 例外已登记`（设计系统级别重构，TD-032 周期外）。

### TD-033: 拆分 `main.css` 设计系统级 CSS 模块

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 设计系统 / 可维护性 |
| 事实源 | [TD-032 行数基线](02-baselines/td-032-source-file-sizes.md)；`docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界`；[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) (merge `25ca165`) |

**证据**
- `packages/web/src/assets/css/main.css` 当前 1343 行，是 TD-032 收口后唯一仍超过 1000 行的源码文件。
- `main.css` 同时承载 Tailwind `@theme` token、4 套主题变量、surface / glass token、`ui-*` 设计系统类、`liquid-*` 兼容别名、动画、基础样式和历史装饰类。
- [TD-032 行数基线](02-baselines/td-032-source-file-sizes.md) 已将它登记为设计系统级例外，并注明后续应按 token / 组件 / 主题拆分。

**问题**
- 单文件承载设计 token、主题、组件类和兼容层，后续任何 UI 变更都容易在同一文件产生冲突。
- `ui-*` 与 `liquid-*` 兼容语义已经稳定，继续在一个 1000+ 行文件里追加样式会削弱可读性和审查质量。
- 该文件是设计系统事实源之一，若没有模块边界，后续 AI IDE 更容易把视觉重设、兼容类清理和纯机械拆分混在一个 PR 中。

**完成标准**
- 开工前先建立独立 spec / plan，明确目标 CSS 文件树、每个文件职责和 import 顺序。
- 推荐首个切片只做机械拆分，不做视觉重设、不删除 `liquid-*` 兼容别名、不重命名公开 CSS custom properties。
- `main.css` 收敛为入口聚合文件，目标不超过 200 行；拆出的 CSS 模块单文件默认不超过 500 行。
- 建议目标结构按职责拆分，例如：
  - `packages/web/src/assets/css/main.css`：Tailwind import + 模块 import 聚合。
  - `packages/web/src/assets/css/tokens.css`：`@theme` token 和常量 token。
  - `packages/web/src/assets/css/themes.css`：4 套 `data-theme` 变量。
  - `packages/web/src/assets/css/base.css`：全局基础样式、body、scrollbar 等。
  - `packages/web/src/assets/css/components.css`：`ui-*` 设计系统类。
  - `packages/web/src/assets/css/compat-liquid.css`：`liquid-*` 兼容别名和历史装饰类。
  - `packages/web/src/assets/css/animations.css`：动画和 transition 工具类。
- 拆分后 4 个主题、`ui-*` 类、`liquid-*` 兼容类和现有页面视觉行为保持等价。
- 回写 [TD-032 行数基线](02-baselines/td-032-source-file-sizes.md)：更新 `main.css` 状态、拆出文件行数、验证结果和扫描历史。

**验证方式**
- `cd packages/web && pnpm typecheck` 退出码 0。
- `cd packages/web && pnpm lint` 退出码 0。
- `cd packages/web && pnpm build` 退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。
- 人工复核 `main.css` 只承担入口聚合职责；拆出 CSS 模块均有单一职责，且公开类名 / CSS 变量未被无计划删除。

**交付记录**
- 2026-06-09 完成（接手工具：Claude Code）。纯机械拆分，**以 `pnpm typecheck / lint / build` 退出码 0 与 `git diff --check` 退出码 0 为依据**（无类名重命名、无 `liquid-*` 删除、无 CSS 变量重命名）。[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103)（merge `25ca165`）合并到 `main`。
  > **未建独立 spec / plan**：任务卡完成标准要求"开工前先建立独立 spec / plan"，但本任务未执行。事后不再补建（成本 > 收益），本事实已在 `docs/03-engineering-governance/04-retrospectives/review-score-log.md` 的 DOC-045 follow-up 中登记；后续同类任务须按 `git-workflow.md#开发前分支门禁` 切分支后先建 spec / plan。
  - `main.css` 1343 → 9 行（`@import` 入口聚合）：`@import "tailwindcss"` + 8 个模块 `@import`。
  - 8 个 CSS 模块（全部 ≤500 行）：
    1. `tokens.css` 119 行：`@theme` token 块（颜色 / surface / 排版 / 间距 / z-index）。
    2. `themes.css` 256 行：4 套 `:root[data-theme="..."]` CSS 变量（liquid / ink / navy / notion）。
    3. `base.css` 35 行：`@layer base` reset（body / heading / selection）。
    4. `components.css` 281 行：`@layer components` — `ui-*` 容器层（`ui-page-shell` / `ui-panel` / `ui-toolbar` / `ui-interactive-row`）+ `ui-*` 原子控件（`ui-input` / `ui-btn*` / `ui-tag*` / `ui-dialog*`）+ `sidebar-shell` + `liquid-card*` 兼容别名 + `liquid-card-scan` + liquid `ui-panel` 玻璃感覆盖。
    5. `compat-liquid.css` 313 行：`@layer components` — `liquid-input` / `liquid-btn*` / `liquid-tag*` / `liquid-dialog*` 兼容别名 + `:root[data-theme="notion"]` 的 `liquid-*` 主题覆盖（`liquid-card` / `liquid-btn*` / `liquid-input` / `liquid-tag*` / `liquid-dialog*` / `sidebar-shell` / `nav-item*` / `content-bg` / `animate-slide-up` / `stagger-*` / `liquid-rise*` / `liquid-card-scan::after` / `markdown-body blockquote::after`）。
    6. `animations.css` 86 行：`@layer components` — `@keyframes fade-in` / `dialog-in` / `slide-up` / `pulse-dot` / `scan-line` + `stagger-*` 延迟 + `liquid-rise-*` 转场 + `@media (prefers-reduced-motion: reduce)` 全局降级。
    7. `markdown.css` 214 行：`@layer components` — `content-bg` / `mesh-bg` + theme mesh 降级 + `.markdown-body` 全套（p / h1-h6 / strong / em / a / ul / ol / li / blockquote + `highlight-sweep` keyframe / code / pre / table / hr / img）+ `tabular-nums` / `wet-line`。
    8. `toast.css` 52 行：`@layer components` — `toast-container` / `toast-item` + 4 toast variant + `@keyframes toast-in` + `toast-leave-*`。
  - 验证摘要（按 `quality-gates.md#完成门禁`）：
    - 已运行：`pnpm --filter @metaedu/web typecheck` → 退出码 0（零输出）。
    - 已运行：`pnpm --filter @metaedu/web lint` → 退出码 0（零输出）。
    - 已运行：`pnpm --filter @metaedu/web build` → 退出码 0，✓ built in 3.34s。
    - 已运行：`python3 scripts/check-engineering-docs` → 退出码 0（`engineering docs checks passed`）。
    - 已运行：`git diff --check` → 退出码 0。
    - 人工复核：`main.css` 仅 9 行 `@import`；8 个模块文件职责单一；`tokens.css` 仅 `@theme`、`themes.css` 仅 4 `data-theme` 块、`base.css` 仅 `@layer base`、`components.css` 仅 `ui-*` + `liquid-card*`、`compat-liquid.css` 仅 `liquid-*` 兼容 + notion 覆盖、`animations.css` 仅 keyframes + reduced-motion、`markdown.css` 仅 `.markdown-body` + 装饰背景、`toast.css` 仅 toast 系统。
  - 行为变化声明：按 `quality-gates.md#行为变化声明检查` 的 7 类信号自查无变化（类名、CSS 变量、`@keyframes` 名称、token 值、import 顺序、主题结构、动画语义全部不变）；Vite 产物 CSS 应等价（基于 import 顺序与级联分析推断，未做 hash / diff 机械对比；本任务未做）。原 commit message / PR 描述中的"zero CSS byte changes / build output identical"为推断性表述，由 DOC-045 弱化为可复核范围。

### TD-034: `build_fields_desc` 在 `array + items=[]` 时丢失"成员为 object"提示

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 后端 / LLM 抽取 / 可维护性 |
| 事实源 | REQ-005（[Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md#ac-2) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md)） / [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143) (`3077047` squash merge；DOC-055 收口后由该 PR 承接，原 PR #142 已 close 为 superseded) |

**证据**
- 生产代码：`packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:60-62`：
  ```python
  elif ftype == "array" and f.get("items"):
      item_key = f["items"][0].get("key", "item") if f["items"] else "item"
      lines.append(f"{prefix}{key}({label})[array型，成员为object，含字段：{item_key}]")
  ```
  `f.get("items")` 对空 list（`[]`）为 falsy，**直接跳到 else 分支**输出 `[array型]`，丢失"成员为object"提示。
- 回归测试：`packages/server-python/tests/contexts/document/test_extract_template_prompts.py::test_build_fields_desc_array_without_items_falls_back_to_bare_type` 已锁定该行为：输入 `Field(type="array", items=[])` → 输出 `empty_array(空数组)[array型]`（无"成员为object"后缀）。
- 业务影响：当用户在模板编辑器配置一个"声明为 array 但 items 字段暂未填写"的字段时，LLM 拿到的 prompt 描述会从"[array型，成员为object，含字段：item]"降级为"[array型]"，可能导致 LLM 把 array 字段当成字符串返回（如 `"steps": "导入 讲授 总结"` 而非 `"steps": [{"step": "..."}]`），污染下游 `_merge_template_structured_data` 的浅拷贝契约与 KG 抽取。

**问题**
- "array 必含 items"是 LLM 抽取契约的一部分（详见 `extract_template_prompts.py:144-147` 的 prompt 段："array型字段（如teaching_process）的value必须是JSON数组，每个成员是包含子字段的object"）；`build_fields_desc` 的输出本应是 LLM 抽取契约的可执行提示。
- 当前 `f.get("items")` 的 falsy 兜底把"items 暂未填写"和"items 故意为空"两种情况混为同一种输出，模糊了"模板字段未配齐"的信号。
- REQ-005 的 11 条回归虽然锁定了现状，但现状本身偏离 spec 设计的"L1 → L2 → L3 抽取契约"目的。

**完成标准**
- 选择以下任一路线并落地（不强制立即动手；本 TD 主要目的是把问题记入总账并形成决策）：
  - **路线 A（推荐）**：把生产代码的判断从 `f.get("items")` 改为显式 `f.get("items") is not None`；当 `items=[]` 时输出 `key(label)[array型，成员为object，含字段：item]`（fallback 到 "item"），并在 prompt 段强调 "如果未配置 items 字段，请返回空数组 `[]`"。同时更新回归测试期望。
  - **路线 B**：把"array 必含 items"提到模板校验层（`init_by_ai` / Template API Pydantic schema），在创建/更新时拒绝 `type="array"` + `items=[]` 的模板，从源头杜绝模糊信号；`build_fields_desc` 维持现状。
  - **路线 C（保守）**：在 `build_fields_desc` 输出 `[array型]` 后追加注释"（未配置 items，默认推断为 string 数组）"，显式告诉 LLM 当前 array 退化为字符串数组；LLM 行为可预测但契约更弱。
- 无论哪条路线，必须更新 `packages/server-python/tests/contexts/document/test_extract_template_prompts.py::test_build_fields_desc_array_without_items_falls_back_to_bare_type` 的期望或拆分为更精确的测试。
- 更新 `extract_template_prompts.py` docstring 描述 array + items 三种状态的契约。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q` 退出码 0，回归期望已更新。
- 选路线 A 时需跑 `tests/contexts/document -q` 确认无其他回归。
- 选路线 B 时需补 Pydantic schema 校验测试（参考 `tests/contexts/template/test_template.py` 的 `Field.from_dict` 路径）。
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。选路线 A：`f.get("items")` 改为 `f.get("items") is not None` 的真值检查，`items=[]` 时进入 array 分支并 fallback 到 `item_key = "item"`，保留"成员为object"提示。`elif ftype == "array" and f.get("items")` 简化为 `elif ftype == "array"`。代码变更随 [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143)（squash merge `3077047`，DOC-042 行数扫描脚本）一并合入 main；原 [PR #142](https://github.com/MarkDanile/MetaEduBase/pull/142)（commit `1e9a012`）未独立合并，于 2026-06-10 由 DOC-055 关闭为 superseded。
  - `app/contexts/document/application/tasks/extract_template_prompts.py`：2 行逻辑修改 + docstring 更新（3 种 items 状态契约说明 + TD-034 引用）。
  - `tests/contexts/document/test_extract_template_prompts.py`：`test_build_fields_desc_array_without_items_falls_back_to_bare_type` → `test_build_fields_desc_array_without_items_falls_back_to_item_key`，期望从 `[array型]` 更新为 `[array型，成员为object，含字段：item]`。
- 行为变化声明：`items=[]` 的 array 字段 prompt 描述从 `[array型]` 变为 `[array型，成员为object，含字段：item]`，LLM 将收到更强的结构化提示（这正是 TD-034 的修复目标）。
- 验证摘要：`pytest tests/contexts/document/test_extract_template_prompts.py -q` 11 passed；`pytest tests/contexts/document/ -q` 50 passed；`ruff check app/contexts/document/application/tasks/extract_template_prompts.py tests/contexts/document/test_extract_template_prompts.py` → All checks passed!；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0。

### TD-035: 收口 REQ-005 新增测试文件 ruff 质量门禁

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 测试 / 质量门禁 |
| 事实源 | REQ-005 评审 / [PR #109](https://github.com/MarkDanile/MetaEduBase/pull/109) |

**证据**
- REQ-005 新增 `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`，单文件测试通过：`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q` → `11 passed`。
- 但同一文件 ruff 不通过：`cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/document/test_extract_template_prompts.py` 报 4 个可修复问题：
  - `I001` import block 未排序：`tests/contexts/document/test_extract_template_prompts.py:18`
  - `SIM300` Yoda condition：`tests/contexts/document/test_extract_template_prompts.py:101`
  - `SIM300` Yoda condition：`tests/contexts/document/test_extract_template_prompts.py:117`
  - `SIM300` Yoda condition：`tests/contexts/document/test_extract_template_prompts.py:139`

**问题**
- REQ-005 是测试补齐任务，但新增测试文件本身没有满足 Python lint 质量门禁。
- PR #109 的验证记录覆盖了 pytest、工程文档门禁和 `git diff --check`，但未记录 ruff 是否运行；后续同类测试补齐任务容易出现"测试可跑，但质量门禁不干净"的缺口。

**完成标准**
- 修复 `test_extract_template_prompts.py` 的 `I001` / `SIM300`，不改变测试语义。
- 不改业务代码。
- 如修复过程中发现更多历史 ruff 问题，只处理本文件或另行登记，不扩大范围。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/document/test_extract_template_prompts.py` 退出码 0。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q` 退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 2026-06-09 完成（接手工具：Claude Code）。[PR #114](https://github.com/MarkDanile/MetaEduBase/pull/114) 已合并。仅 `packages/server-python/tests/contexts/document/test_extract_template_prompts.py` 1 个文件核心变更 + 4 个 docs 同步。
  - `ruff check --fix` 4 个错误全部自动修复（1 个 I001 + 3 个 SIM300），共 4 行实质变化：1 个多余空行删除（I001 顺带处理）+ 3 处 Yoda 条件 `assert A == B` 翻转为 `assert B == A`（assertion 语义等价）。
  - 行为变化声明：无；纯语法糖（assertion 顺序、import 块格式），pytest 11 passed 完全保持。
  - 验证摘要：`ruff check tests/contexts/document/test_extract_template_prompts.py` 退出码 0（`All checks passed!`）；`pytest tests/contexts/document/test_extract_template_prompts.py -q` 11 passed；`ruff check app/ tests/` 退出码 0（无其他历史 ruff 问题引入）；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0；`git diff --name-status` 仅 1 个文件。

### TD-036: `metaedu_test` 库 `document_tasks.updated_at` 列缺失（alembic 003 迁移与测试库 schema drift）

状态：🟢 完成
（实际根因是 alembic 006 的 `gin` operator class 错误，详见 TD-038 与 PR #122 `2780ff1`。）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 测试 / 质量门禁 |
| 事实源 | REQ-006 Stage 1 探查（`feat/req-006-stage-1-e2e`） |

**证据**
- alembic head：`9466ea6e5d33`（`packages/server-python/alembic/versions/`），003 迁移 `003_add_updated_at_to_document_tasks.py:19-24` 显式 `op.add_column("document_tasks", sa.Column("updated_at", sa.DateTime(), nullable=True), schema="metaedu")`。
- `metaedu_test` 库实际列：`['id', 'tenant_id', 'file_id', 'dataset_id', 'task_type', 'status', 'progress', 'error_message', 'started_at', 'completed_at', 'created_at']` — **缺 `updated_at`**。
- 生产代码契约：`packages/server-python/app/shared/tasks/lifecycle.py:101` `update_task_status` 无差别写 `updated_at`。
- 触发失败：`UPDATE metaedu.document_tasks SET status = $1, progress = $2, updated_at = $3, started_at = $3 WHERE id = $4` → `UndefinedColumnError: column "updated_at" of relation "document_tasks" does not exist`。
- `files` 表有 `updated_at`（002 迁移加的），003 迁移应该已经 apply；但实际 schema 缺列 → 这是测试库与 alembic head 的真实 drift，需查 alembic upgrade 历史是否曾 downgrade 过 003。

**问题**
- 后端生产代码与测试库 schema 漂移；任何 e2e 脚本走 `parse_document` / `extract_template` / 其他 Celery 任务都会卡在这一步。
- `./dev.sh init-test-db` 跑 `alembic upgrade head` 不能修复——head 已是 003 之后；说明列从未被加入（或者被回退过）。
- 影响：所有依赖 `metaedu_test` 的 e2e 集成测试（含 REQ-006 端到端脚本）都受影响。

**完成标准**
- 修复 `metaedu_test` 库 `document_tasks.updated_at` 列：手工 `ALTER TABLE metaedu.document_tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP` 验证有效。
- 在 `init-test-db` 流程加入 `_ensure_critical_columns` 防御性 check：初始化完成后对照 production schema 校验关键列存在，缺则提示运行修复 SQL（不要 silently 修复，避免掩盖 alembic 真实 drift）。
- 如发现 alembic 003 迁移本身有 bug（downgrade 误删 / upgrade 失败回滚），修复迁移并补数据回归测试。
- `tests/e2e/test_p1_demo.py` 移除对 `ADD COLUMN IF NOT EXISTS` 的依赖；e2e 脚本可裸跑 `init-test-db` 完成后即通过。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m pytest tests/e2e/test_p1_demo.py -q` 退出码 0。
- `./dev.sh init-test-db` 一次后无需手工 `ALTER TABLE`。
- 复现：`DROP DATABASE metaedu_test && ./dev.sh init-test-db && pytest tests/e2e/test_p1_demo.py -q` → 3 passed，无手动修补。

**交付记录**
- 2026-06-09 PR #122 (`2780ff1`) 完成。根因不是 alembic 003 本身,而是 alembic 006 用 `postgresql_ops={"doc_types": "gin"}` 触发 `UndefinedObjectError: operator class "gin" does not exist for access method "gin"`,在全新 DB 上阻塞 `alembic upgrade head`,导致 003 的 `add_column updated_at` 永远跑不到。修复:
  - `alembic/versions/006_add_templates.py` 去掉 `gin` 字面 ops,改用默认 `array_ops`(追加注释指回 TD-036 / TD-038)。
  - `app/shared/infrastructure/test_db_setup._ensure_extensions_and_schema` 幂等 `CREATE EXTENSION IF NOT EXISTS btree_gin`。
  - 新增 `_ensure_critical_columns`,在 `init_test_database` 末尾对 `document_tasks.updated_at` / `files.updated_at` 做 post-upgrade 校验;漂移时 `logger.warning` + 给出修复 SQL,**不** silently ALTER(对齐任务卡完成标准第 2 条)。
  - `tests/e2e/test_p1_demo._ensure_test_db_columns` docstring 刷新为"TODO 036 closes the root cause";`ADD COLUMN IF NOT EXISTS` 兜底保留作 belt-and-suspenders。
- 验证摘要:`DROP DATABASE metaedu_test && python -m app.shared.infrastructure.test_db_setup` 一次成功(无需手工 ALTER),`alembic_version = 9466ea6e5d33`(head),`document_tasks` 列含 `updated_at`,`ix_templates_doc_types` 为 `USING gin (doc_types)`;`pytest tests/e2e/test_p1_demo.py -q` 3 passed;`pytest tests/ -q` 222 passed;`ruff check app/ tests/` 退出码 0;`scripts/check-engineering-docs` 退出码 0;`git diff --check` 退出码 0;幂等二次 `init-test-db` 无 already exists / 无 re-run。范围:`git diff --name-status` 仅 3 文件(006 迁移 + test_db_setup + e2e docstring)。详见 [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) (`2780ff1`)。

### TD-037: e2e 脚本无法直接走真实 Celery：沙箱无 Redis broker 时需 mock `chunk_document.delay` + patch `broker_url=memory://`

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 后端 / 测试 / 基础设施 |
| 事实源 | REQ-006 Stage 1 探查（`feat/req-006-stage-1-e2e`） |

**证据**
- 沙箱配置：`packages/server-python/app/celery_app.py:31-35` 显式 `broker="redis://localhost:6379/1", backend="redis://localhost:6379/2"`。
- REQ-006 e2e 路径：直接调 `parse_document(file_id, tenant_id)`（同步执行 task body）时，task body 内部 `chunk_document.delay(...)` 触发 broker 连接 → sandbox 无 Redis 时 `kombu.exceptions.OperationalError: [Errno 61] Connection refused`。
- 沙箱的 Redis 通过 `docker compose` 提供（`./dev.sh infra`）。

**问题**
- "端到端" e2e 在不启动 Redis 时需 mock `chunk_document.delay` + patch `broker_url=memory://`，实际是"半端到端"。
- `memory://` broker 在沙箱中可用但不可跨进程；CI 必须有 Redis 才能跑真实 e2e。
- `init-test-db` 不启动 broker；e2e 脚本默认 broker patch 与 Celery app 共享 `celery_app` 单例，多 e2e 测试并发可能互相影响 broker 状态。

**完成标准**
- 选择以下任一路线并落地：
  - 路线 A（推荐）：在 `tests/e2e/conftest.py` 中为 e2e 目录提供独立 Celery app fixture（broker / backend 默认 `memory://`），所有 e2e 脚本共用，避免污染全局 `celery_app`。
  - 路线 B：在 `init-test-db` 后启动一个 Redis 容器，e2e 脚本走真实 broker；沙箱无 docker 时降级到 `memory://`。
- Stage 1.5 实施时把 `chunk_document.delay` / `embed_chunks.delay` / `extract_template.delay` / `extract_knowledge_graph.delay` 的 mock 集中到一个 fixture（如 `mock_pipeline_chain`），避免每个测试都重复 patch。
- CI 端补一个 `e2e-real` 标记，依赖真实 Redis；本地默认 `e2e-mock`。

**验证方式**
- `cd packages/server-python && .venv/bin/python -m pytest tests/e2e/ -q` 退出码 0。
- 路线 B 选定时：`docker ps` 显示本地 redis 容器；`pytest tests/e2e/ -q` 不修改 `celery_app.conf`。
- `scripts/check-engineering-docs` 退出码 0。
- `ruff check app/ tests/` 退出码 0。
- `pytest tests/ -q` 222 passed 无回归。

**交付记录**
- 2026-06-10 [PR #130](https://github.com/MarkDanile/MetaEduBase/pull/130) (`9419c4e`)：选路线 B。新建 `tests/e2e/conftest.py`（`e2e_db_url` fixture）；Stage 1.0 的 inline broker-mock 模式维持不变（由 `tests/conftest.py` 的 autouse `mock_celery_tasks` + 各测试函数自己的 `patch.object(chunk_mod.chunk_document, "delay", ...)` 负责）。Redis 由 `./dev.sh infra` 提供，不做任何额外的 broker/delay patch 集中化。验证摘要：`pytest tests/e2e/test_p1_demo.py -q` 3 passed；`pytest tests/ -q` 222 passed；`ruff check tests/e2e/` All checks passed!；`ruff check app/ tests/` All checks passed!；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0。

### TD-038: alembic 006 迁移用 `gin` operator class（`USING gin (doc_types gin)`），在全新 DB 上 `UndefinedObjectError` 阻塞 `alembic upgrade head`

状态：🟢 完成
（并入 [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) `2780ff1` 一并修复；交付摘要见 TD-036 交付记录段。）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 迁移 / 质量门禁 |
| 事实源 | TD-036 探查 |

**证据**
- `packages/server-python/alembic/versions/006_add_templates.py:33` `op.create_index("ix_templates_doc_types", "templates", ["doc_types"], postgresql_using="gin", postgresql_ops={"doc_types": "gin"})`。
- SQLAlchemy 字面翻译为 `USING gin (doc_types gin)`，PG 实际只暴露 `array_ops`（内置）和 btree_gin 的具名 ops（`timestamp_ops` / `text_ops` 等），无名为 `gin` 的 opclass。
- 全新 `metaedu_test` 上 `alembic upgrade head` 失败：
  ```
  UndefinedObjectError: operator class "gin" does not exist for access method "gin"
  [SQL: CREATE INDEX ix_templates_doc_types ON templates USING gin (doc_types gin)]
  ```
- 已存在 `ix_templates_doc_types` 的库（早期 dev 库、prod）不重跑 create_index，所以未暴露问题；只有全新 DB 命中。

**问题**
- 任何使用 `python -m app.shared.infrastructure.test_db_setup` 的全新环境，会卡在 006，永远升不到 head。
- 连锁影响：003 的 `add_column updated_at` 永远跑不到 → `document_tasks` 缺列 → 任何 Celery 任务触发 `update_task_status` 即 `UndefinedColumnError`。这正是 TD-036 描述的现象。
- `make setup-db` 在 dev 库上不会重装 btree_gin，所以即便未来再加 `USING gin (xxx gin)` 也会重蹈覆辙。

**完成标准**
- 修 006 迁移：删除 `postgresql_ops={"doc_types": "gin"}`，让默认 `array_ops` 生效；保留 `postgresql_using="gin"`。
- `init-test-db._ensure_extensions_and_schema` 幂等 `CREATE EXTENSION IF NOT EXISTS btree_gin`，防未来 gin-on-scalar 迁移再次阻塞。
- 注释里点回本任务和 TD-036。

**验证方式**
- `DROP DATABASE metaedu_test && python -m app.shared.infrastructure.test_db_setup` 一次成功，alembic 走到 head (`9466ea6e5d33`)。
- `ix_templates_doc_types` 实际为 `USING gin (doc_types)`，无 `gin` 字面。

**交付记录**
- 2026-06-09 与 TD-036 一并在 [PR #122](https://github.com/MarkDanile/MetaEduBase/pull/122) (`2780ff1`) 修复。代码变更点:`alembic/versions/006_add_templates.py`（删 `postgresql_ops` + 注释指向 TD-036/TD-038）+ `app/shared/infrastructure/test_db_setup.py`（加 btree_gin 扩展）。验证见 TD-036 交付记录。

### DOC-051: 一次性收口历史 plan 残留 TBD / `TD-???` / `未回填` 占位

状态：🟢 完成（DOC-055 收口）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程流程 / 跨 AI 交接 |
| 事实源 | REQ-003 / REQ-004 / REQ-008 plan 残留占位扫描 / [PR #124](https://github.com/MarkDanile/MetaEduBase/pull/124) (`d7a2ca7`) |

**证据**
- 2026-06-09 评审（Codex 复评 PR #124，分数 74）发现：`docs/03-engineering-governance/technical-debt.md` 总览表中 DOC-051 仍为 `⚫ 待办`，与 Backlog / current-work / work-log 的 🟢 完成态不一致。
- 主任务本体（占位替换 + plan 链接回填）已通过 PR #124 (`d7a2ca7`) 完成，本任务卡的 12 处占位替换与 3 个 plan 链接回填事实保持。

**问题**
- DOC-051 跨事实源状态漂移会让后续 AI IDE 接手时按 `technical-debt.md` 总览表误判任务未完成，从而二次开 PR 重复替换。

**完成标准**
- `technical-debt.md` 总览表 DOC-051 行状态与 Backlog / current-work / work-log 一致为 `🟢 完成`。
- 本任务卡（DOC-055 收口）补完 DOC-051 详情区。

**验证方式**
- `rg -n "DOC-051" docs/03-engineering-governance/technical-debt.md` 显示总览表行 + 详情区均含 `🟢 完成`。
- `scripts/check-engineering-docs` 退出码 0。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。仅 `technical-debt.md` 总览表 DOC-051 行状态 `⚫ 待办` → `🟢 完成`，并在事实源列补 PR #124 + DOC-055 收口标注；本任务详情区同步新建。Backlog / current-work / work-log 早已是 `🟢 完成`，无需调整。零业务代码变更。

### DOC-045: 修正 TD-033 CSS 拆分交付声明与追踪证据

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程流程 / 跨 AI 交接 |
| 事实源 | TD-033 review / [PR #137](https://github.com/MarkDanile/MetaEduBase/pull/137) (`b815942`) |

**证据**
- TD-033 ([PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103), merge `25ca165`) 评审 [review-score-log.md#2026-06-09 td-033](04-retrospectives/review-score-log.md) 总分 81，"事实声明与追踪证据需修正"列为 DOC-045 必修 follow-up；具体扣分点：未建独立 spec / plan、"zero CSS 字节变化 / build output identical"声明过强、`work-log.md` 未补 PR / merge commit。
- TD-033 任务卡 `docs/03-engineering-governance/technical-debt.md#td-033` 的「行为变化声明」段在 DOC-045 启动前已经写入"原 commit message / PR 描述中的'zero CSS byte changes / build output identical'为推断性表述，由 DOC-045 弱化为可复核范围"，但 DOC-045 本身作为独立事实源未入账。
- `work-log.md` 索引行 `2026-06-09 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | ... | | | ...` PR / merge commit 列留空，与其它同档已完成任务（如 DOC-051 / DOC-052 / DOC-054）格式不一致。
- `04-backlog.md` 的 DOC-045 行状态 `⚫ Candidate`，事实源尚未与本次交付状态同步。

**问题**
- DOC-045 已在多份事实源（评审行、TD-033 行为变化声明、work-log 索引）中作为"被计划但未交付"的项目存在，没有自己的任务卡和统一完成状态，跨 AI IDE 接手时无法判断"是否已完成 / 由谁完成 / 通过哪个 PR 闭环"。
- work-log 行 PR / merge commit 留空会让后续评审和阶段复盘无法把 DOC-045 与具体 git 提交对齐，影响 `quality-gates.md#已记录评审数` 与 `复盘粒度细` 指标的准确性。

**完成标准**
- 在 `technical-debt.md` 总览表新增 DOC-045 行（🟢 完成），并在本任务详情区补独立任务卡（包含证据 / 问题 / 完成标准 / 验证方式 / 交付记录）。
- `docs/01-product-planning/04-backlog.md` DOC-045 行状态从 `⚫ Candidate` 翻为 `🟢 Done`，并把 PR 链接从"PR #103（实际是 TD-033 的 PR）"改为本次 DOC-045 自己的 PR。
- `docs/03-engineering-governance/work-log.md` 索引行的 PR / merge commit 列从空补为本 PR 链接与 merge commit。
- `docs/03-engineering-governance/current-work.md` 候选区 DOC-045 行移入最近完成区，状态写明 `🟢 完成`，并附 PR 链接。
- 不重复修改 TD-033 任务卡正文（其行为变化声明段已是本次弱化的目标态）；如需补充审查应绑定本 DOC-045 任务卡。

**验证方式**
- `python3 scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。
- `git diff --name-status` 仅包含 docs 路径（`docs/03-engineering-governance/technical-debt.md` / `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/work-log.md` / `docs/03-engineering-governance/current-work.md`），无业务代码。
- `rg -n "DOC-045" docs/03-engineering-governance/technical-debt.md` 命中 ≥ 2（总览表 + 任务详情标题）。
- `rg -n "DOC-045" docs/03-engineering-governance/current-work.md` 命中 ≥ 1（最近完成区）。
- `rg -n "DOC-045" docs/03-engineering-governance/work-log.md` 命中 ≥ 1（PR / merge commit 列已填）。
- `rg -n "DOC-045" docs/01-product-planning/04-backlog.md` 命中 ≥ 1 且状态列含 `🟢 Done`。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。DOC-045 启动前，TD-033 任务卡行为变化声明段已写明"由 DOC-045 弱化为可复核范围"，本次仅落地跨事实源索引闭环与本次 PR 自身的事实源记录，不重复修改 TD-033 任务卡正文（已对齐）。
- 落地 4 个文档文件（5 处编辑）：
  1. `docs/03-engineering-governance/technical-debt.md` 总览表新增 DOC-045 行（🟢 完成，PR #137 `b815942`），并在任务详情区追加独立任务卡（含证据 / 问题 / 完成标准 / 验证方式 / 交付记录）。
  2. `docs/01-product-planning/04-backlog.md` DOC-045 行状态翻 `🟢 Done`，"External"列 PR 链接从 `#103`（TD-033 链接）改为本次 `#137`。
  3. `docs/03-engineering-governance/work-log.md` DOC-045 索引行 PR 列补 `#137`，merge commit 列补 `b815942`。
  4. `docs/03-engineering-governance/current-work.md` 候选区 DOC-045 行移除；最近完成区按"最新优先"在顶部插入 `2026-06-10 | DOC-045 修正 TD-033 交付声明与追踪证据 | 🟢 完成 | ...` 一行。
- 行为变化声明：docs-only，无业务代码变更；不影响 runtime 行为。
- 验证摘要：`python3 scripts/check-engineering-docs` 退出码 0（`engineering docs checks passed`）；`git diff --check` 退出码 0；`git diff --name-status` 仅 4 个 docs 文件；6 条 `rg` 验收断言全过。
- 未建独立 spec / plan：本次为 docs-only 跨事实源补全（事实源仅文档），规模与 TD-033 的"未建 spec / plan 已事后登记"模式一致（详见 TD-033 任务卡 L1365 注释与 `04-retrospectives/review-score-log.md#2026-06-09 td-033`）；任务卡完成标准已记录此例外，本任务不扩大范围补建。

### DOC-042: 脚本化 TD-032 行数基线扫描

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程治理 / 工程脚本 |
| 事实源 | [Baseline](02-baselines/td-032-source-file-sizes.md) / `docs/01-product-planning/04-backlog.md` |

**证据**
- TD-032 行数基线扫描依赖手工命令 `rg --files -0 packages scripts tests -g '*.py' -g '*.ts' -g '*.tsx' -g '*.vue' -g '*.css' -g '*.scss' -g '!**/.venv/**' -g '!**/uploads/**' -g '!**/node_modules/**' -g '!**/dist/**' | xargs -0 wc -l | sort -nr | head -40`。
- 手工命令在文件路径含空格时可能出错；每次复盘需人工重跑并手动对比。
- `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 是当前唯一行数快照，但无法自动刷新。

**问题**
- 行数扫描不可复现、不可自动对比，TD-032 复盘依赖人工操作。
- 缺少脚本化扫描意味着后续无法在 `check-engineering-docs` 或 CI 中自动检测文件规模回归。

**完成标准**
- 将手工扫描命令固化为稳健脚本（如 `scripts/scan-source-sizes`），排除 `.venv` / `uploads` / `node_modules` / `dist` 并正确处理含空格路径。
- 脚本支持 `--json` 输出和 `--diff` 对比上次基线。
- 输出可被 `td-032-source-file-sizes.md` 引用或自动刷新。
- `scripts/check-engineering-docs` 退出码 0。

**验证方式**
- `scripts/scan-source-sizes` 幂等运行，输出与手工命令一致。
- `scripts/scan-source-sizes --diff` 能检测新增超大文件或行数增长。
- `scripts/check-engineering-docs` 退出码 0。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。将手工 `rg --files -0 | xargs -0 wc -l` 扫描命令固化为 Python 脚本，避免空格路径问题和手动复跑。[PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143)。
  - 新增 `scripts/engineering/scan_source_sizes.py`（335 行）：`scan_source_files` / `load_baseline` / `save_baseline` / `diff_baseline` / `refresh_sizes_md` / `format_text|json|diff` / `main`；支持 `--threshold` / `--json` / `--diff` / `--refresh`。
  - 新增 `scripts/scan-source-sizes` shell 入口（5 行 `runpy.run_path` 模式与 `check-engineering-docs` 一致）。
  - 新增 `scripts/engineering/checks/source_sizes.py` 门禁检查 `check_source_size_hard_limit`：扫描所有源码文件，仅在 >1000 行且未在 `td-032-source-file-sizes.md` 中标记 🟢/已拆分/已合规 时报错。
  - 注册到 `checks/__init__.py` 的 `KNOWN_CHECKS`；`SCRIPTED_GATE_CANDIDATES` 加 `"源码文件超过 1000 行硬限制检查"`。
  - `quality-gates.md` 候选清单新增对应行。
  - `td-032-source-file-sizes.md` 维护规则段更新扫描命令为脚本化形式（保留手工命令为历史参考）。
  - 新增 `docs/03-engineering-governance/02-baselines/source-sizes-baseline.json`（git 跟踪的机器可读基线）。
  - `tests/engineering/test_check_engineering_docs.py` 新增 2 条测试：无 >1000 行文件 → 0 issues；未登记的 >1000 行文件 → 1 issue。
- 行为变化声明：门禁新增一项检查 `source-size-over-limit`，仅在出现 >1000 行且未登记的文件时报告，不改变现有 15 项检查行为；扫描脚本是新增命令，不替换既有手工命令（保留为历史参考）。
- 验证摘要：`scripts/scan-source-sizes --threshold 300` 列出 18 个 ≥300 行的文件（最高 `tests/engineering/test_check_engineering_docs.py` 545 行 Python）；`--diff` 输出 `(no differences from baseline)`；`pytest tests/engineering/ -q` 19 passed（基线 17 + 新增 2）；`ruff check scripts/engineering/scan_source_sizes.py scripts/engineering/checks/source_sizes.py scripts/engineering/checks/__init__.py scripts/engineering/checks/_common.py` → All checks passed!；`python3 scripts/check-engineering-docs` → engineering docs checks passed（17 + 2 测试通过且门禁无 issue）；`git diff --check` 退出码 0。

### DOC-055: 收口 DOC-042 / TD-034 PR 范围混入与事实源漂移

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 领域 | 文档 / 工程流程 / 质量门禁 |
| 事实源 | DOC-042 review / [Review Score Log](04-retrospectives/review-score-log.md) / [PR #143](https://github.com/MarkDanile/MetaEduBase/pull/143) / [PR #142](https://github.com/MarkDanile/MetaEduBase/pull/142) (closed as superseded) |

**证据**
- DOC-042 的合并 PR #143 是 `MERGED`，但文件列表混入 TD-034 的生产代码和测试文件：`packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py`、`packages/server-python/tests/contexts/document/test_extract_template_prompts.py`。
- TD-034 的事实源原指向 [PR #142](https://github.com/MarkDanile/MetaEduBase/pull/142) / commit `1e9a012`，但 `gh pr view 142` 显示 `state=OPEN`、`mergeCommit=null`。
- `scripts/scan-source-sizes --diff` 当前输出 2 个差异：`extract_template_prompts.py` 88 -> 93，`test_extract_template_prompts.py` 263 -> 261，说明 DOC-042 交付记录里的 `(no differences from baseline)` 已不再成立。
- DOC-051 在 `docs/01-product-planning/04-backlog.md`、`current-work.md`、`work-log.md` 均为完成态，但 `technical-debt.md` 总览仍为 `⚫ 待办`。
- DOC-051 把 3 处 `TD-???` 占位统一替换为 `TD-030（已锁定）`，其中至少部分语义与 `TD-030: RecallChannel Protocol vs concrete signature drift` 不一致。

**问题**
- DOC-042 是工程脚本 / 基线门禁任务，PR 混入 TD-034 行为变更后，任务范围边界和交付事实不再清晰。
- TD-034 的实际合并路径、PR 状态和任务总账记录不一致，后续 AI IDE 可能误判任务是否已关闭。
- 行数基线脚本刚建立就出现 `--diff` 不干净，会削弱 TD-032 文件规模治理的可信度。
- DOC-051 的状态和编号映射漂移会污染后续占位扫描与技术债追踪。

**完成标准**
- TD-034 的事实源明确指向实际合并 PR / merge commit；若 PR #142 保留 OPEN，需在任务卡和 work-log 中解释 PR #142 与 PR #143 的关系。
- DOC-042 的交付记录修正为真实状态：要么刷新 `source-sizes-baseline.json` 并说明原因，要么记录当前 `--diff` 差异是 TD-034 混入造成的待处理状态。
- `scripts/scan-source-sizes --diff` 在收口后输出 `(no differences from baseline)`，或任务卡明确记录差异仍存在且绑定后续任务。
- DOC-051 在 Backlog / current-work / work-log / technical-debt 的状态一致。
- 3 处 `TD-030（已锁定）` 已逐条核对：保留、改成正确 `TD-xxx`，或移除误导性编号，并在必要时补脚本门禁候选。

**验证方式**
- `gh pr view 142 --json number,state,url,mergeCommit,title` 与 `gh pr view 143 --json number,state,url,mergeCommit,title` 输出已被记录或引用。
- `scripts/scan-source-sizes --diff` 输出符合完成标准。
- `rg -n "DOC-051|TD-030（已锁定）" docs/01-product-planning docs/02-delivery-plans docs/03-engineering-governance` 的结果与任务结论一致。
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。跨 4 处事实源、3 个 spec / 1 个任务总账 / 1 个行数基线共 7 处变更；零业务代码变更。任务交付原子拆分如下：
  1. **PR #142 关闭**：原 `OPEN` 状态，TD-034 的代码修复实际已通过 PR #143 squash merge (`3077047`) 合入 main，PR #142 已 close 为 `superseded`，关闭评论引用 PR #143 与 DOC-055。
  2. **TD-034 事实源统一修正**：`docs/03-engineering-governance/technical-debt.md` 总览表行、详情区 `事实源` 字段、`交付记录` 段首句共 3 处把 `PR #142 (commit 1e9a012)` 替换为 `PR #143 (squash merge 3077047)`，并补注"代码随 DOC-042 一并合入；原 PR #142 已 close 为 superseded"；`docs/03-engineering-governance/work-log.md` TD-034 行同步。
  3. **source-sizes baseline 刷新**：`bash scripts/scan-source-sizes --refresh` 把 DOC-042 收口时漏掉的 2 个差异（`extract_template_prompts.py` 88→93、`test_extract_template_prompts.py` 263→261）写回 `source-sizes-baseline.json`，`--diff` 恢复 `(no differences from baseline)`；`td-032-source-file-sizes.md` 「扫描历史」段去重 3 条重复 `--refresh` 记录为 1 条带 DOC-055 上下文条目，明确"本轮 refresh 吸收 PR #143 squash merge 时带入的 TD-034 代码行数变化"。
  4. **DOC-051 跨事实源状态同步**：`technical-debt.md` 总览表 DOC-051 行 `⚫ 待办` → `🟢 完成`，事实源列补 PR #124 (`d7a2ca7`) + DOC-055 收口标注；新建 DOC-051 详情任务卡（证据段引用 Codex 复评 74 分评审结论）。
  5. **3 处 `TD-030（已锁定）` 占位逐条核对**：`docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md:87`（FrequencyFusion.channel 重复/去重，AC-9 已覆盖）、`:req-004-template-match-explainability.md:141`（L3 解析行为，REQ-008 12+ 用例已覆盖）、`:req-008-req-004-quality-follow-up.md:103`（L3 解析行为，本 spec 自身 12+ 用例已覆盖）三处"不在范围 / 后续任务"表中 `ID` 列 `TD-030（已锁定）` → `TD-030（已锁定） → 占位说明`，`归属` 列加注 `（不属于 TD-030）`。判断依据：3 处本质是"边界已由 AC/用例覆盖，触发现入账"的占位声明句，技术债总账中 `TD-030` 实际是 `RecallChannel Protocol vs concrete signature drift`（已收口），语义不重叠；改为"占位说明"保留防退化语义但不误导后续 AI IDE 按编号对照技术债总账。
- 行为变化声明：零业务逻辑变更；零后端 / 前端代码变更；零脚本功能变更（仅 baseline 数据 + 文档同步）。
- 验证摘要（按 `quality-gates.md#完成门禁`）：
  - `gh pr view 142 --json state,mergeCommit` → `state=CLOSED, mergeCommit=null`（superseded）。
  - `gh pr view 143 --json state,mergeCommit` → `state=MERGED, mergeCommit.oid=3077047e4a41d07062e6be7ee4b550d94afbff49`。
  - `gh pr view 144 --json state,mergeCommit` → `state=MERGED, mergeCommit.oid=6acc552db8f9d43267ac05211b7f985c5acb9b64`（DOC-042 review follow-up）。
  - `bash scripts/scan-source-sizes --diff` → `(no differences from baseline)`（原 2 个差异已吸收）。
  - `rg -n "PR #142|1e9a012" docs/03-engineering-governance/technical-debt.md docs/03-engineering-governance/work-log.md` → 多处命中，但均以"原 PR #142 / commit `1e9a012` 已 close 为 superseded / 由 DOC-055 关闭"语境出现，是历史溯源说明而不是"TD-034 唯一事实源指向 #142"；TD-034 总览表行 / 详情区 `事实源` 字段 / 详情区 `交付记录` 段首句已统一为 `#143 / 3077047`。
  - `rg -n "TD-030（已锁定）" docs/02-delivery-plans/01-specs/` → 3 行命中，3 行均带 `→ 占位说明` 与 `（不属于 TD-030）` 标注。
  - `rg -n "DOC-051" docs/03-engineering-governance/technical-debt.md` → 总览表行 `🟢 完成` + 详情区 `🟢 完成`（DOC-055 收口）双命中。
  - `python3 scripts/check-engineering-docs` → 退出码 0（`engineering docs checks passed`）。
  - `git diff --check` → 退出码 0。
  - 未运行：lint / pytest —— DOC-055 范围是 docs-only + 状态收口 + baseline refresh，按 `quality-gates.md#验证表述规范` 不强制后端 lint / pytest 复跑。

### TD-039: 6 键保留集合在 TS 端抽到 `@metaedu/shared/schemas/document` + spec 单一来源落地

状态：⚫ 待办

| 字段 | 内容 |
|------|------|
| 优先级 | P3 |
| 领域 | 前端 / 共享 schema / 文档 |
| 事实源 | REQ-002-3 code review of Tasks 6+7（M-2） / [PR TBD] |
| 范围拆分 | 本卡 = 原 TD-039 收窄版（TS 端 + spec 落地）；后端 Python 路径接入拆为独立 [TD-043](#td-043-打通后端-python-对-shared-schemasdocument-的-import-路径) |

**证据**
- `packages/web/src/views/resource/FileTabsPanel.vue:159-166` 硬编码 6 键 `RESERVED_META_KEYS`。
- 后端 spec `docs/02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md:23` 文字再列 1 次。
- TS 端这两处重复实现，single source of truth 缺失；后续子任务（REQ-002-1 / REQ-002-2 / REQ-002-4 / 任何 schema 演进）容易在某一处漏改，触发 contract 漂移。
- 后端 `extract_template_prompts.py:19-20` 的同 6 键重复问题仍存在，由 [TD-043](#td-043-打通后端-python-对-shared-schemasdocument-的-import-路径) 独立处理（Python import 路径接入是跨语言基础设施工程，不应混入本卡）。

**问题**
- TS 端保留键契约在前端代码 + spec 文档两处重复实现。
- 后端 Python import 路径未打通（仓库无顶层 `metaedu` Python 包、`packages/shared/` 是 TS-only pnpm workspace 包）；把后端 import swap 塞进本卡需要顺手新建 `metaedu/` Python namespace shim，那是另一类工作。

**完成标准（TS 端）**
- 在 `packages/shared/src/schemas/document.ts`（已存在的 Zod schema 旁）导出 `TEMPLATE_META_RESERVED_KEYS: ReadonlySet<string>` 常量（命名沿用既有 helper 如 `getTemplateStructuredData`）。
- 前端 `FileTabsPanel.vue` 改为 `import { TEMPLATE_META_RESERVED_KEYS } from '@metaedu/shared/schemas/document'`，删除本地硬编码 6 键 Set。
- spec `docs/02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md:23` 文字列表改为"见 `TEMPLATE_META_RESERVED_KEYS`"。
- `rg -n "id|version|layer|matched_type|confidence|reason" packages/web/src/views/resource/FileTabsPanel.vue | grep "new Set\|(\"id\""` → 0 命中。
- `packages/web/src/views/resource/FileTabsPanel.spec.ts`（如已合入，依赖 TD-040 合并顺序）继续锁当前行为；本卡不得为了 import 调整而修改测试断言。

**验证方式**
- `pnpm typecheck` 退出码 0（前端仍能 import 共享 schema 包的 string-only 常量）。
- `pnpm --filter @metaedu/web lint` 退出码 0。
- `rg -rn "RESERVED_META_KEYS|6 个保留键" packages/web/ docs/02-delivery-plans/` 输出 1 个常量声明 + 1 个常量引用，0 个 TS 端硬编码。
  - 注意：本卡不再要求"0 个硬编码"覆盖 `packages/server-python/` —— 那是 TD-043 的范围。
- `python3 scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 未完成。
- 2026-06-10：原 TD-039 范围（前端 + 后端 + spec）经并行批次 `td-039+td-040` 实施探查，发现后端 Python import 路径 `metaedu.shared.schemas.document` 不可达（仓库无顶层 `metaedu` Python 包，`packages/shared/` 是 TS-only pnpm workspace 包，0 处 `import metaedu.shared.*` 命中）。按"只修该技术债定义的范围"原则，本卡收窄为 TS 端 + spec 落地；后端 Python 接入拆为新 TD-043，并行批次中本卡未产出代码改动（agent A 在 worktree `td-039-shared-meta-keys` 上干净退出）。

### TD-040: `FileTabsPanel.spec.ts` Vue 单元测试覆盖 AC-11 / AC-12

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 前端 / 测试 / 交付 / 质量门禁 |
| 事实源 | REQ-002-3 code review of Tasks 6+7（I-2） / 2026-06-10 PR #167 squash merge（merge commit `c1cc0c9`） |
| 工作分支 | `td-040-filtabspanel-vitest-coverage`（worktree `.claude/worktrees/agent-a9cfdaec8741f103c` 现场保留待后续清理） |

**证据**
- 当前 `FileTabsPanel.vue` 的 AC-11（6 键保留键过滤）与 AC-12（`template.id` 存在 → 显示溯源元信息卡；不存在 → 隐藏；`layer === "none"` 分支显示 `reason`）只能靠读代码 + `pnpm typecheck / lint` 验证。
- `data-testid="template-source-meta"` 已在 `FileTabsPanel.vue:25` 留好接口，但无消费方。
- 后端 Tasks 3+4 用 6 条 pytest 锁定 AC-1 ~ AC-5 / AC-9；前端 AC-11 / AC-12 缺对偶测试。
- 后续 PR 改动 `FileTabsPanel.vue` 时，CI 仅能拦截 type / lint 错误，无法拦截"6 键被错误渲染"或"card 在老数据下误显示"。

**问题**
- AC-11 / AC-12 是 spec-level 验收点，缺乏 Vue-level 自动化测试。
- 测试基础设施（vitest / @vue/test-utils）项目内尚无可参照用法，需要先评估引入成本（与 `td-031` / `td-035` 类似的"质量门禁"债务）。

**完成标准**
- [x] 评估 `packages/web` 当前测试基础设施状态（2026-06-10 并行批次 Phase 1 探查完成：vitest / @vue/test-utils / jsdom 全部缺失；无既有 spec 文件；安装成本低 ~3.7s；root package.json 与 lockfile 策略不受影响；GO 决策）。
- [x] 新增 `packages/web/src/views/resource/FileTabsPanel.spec.ts`（158 行 / 6 个 test case）：
  1. 给定 `structuredData.template = { id: "x", version: 1, layer: "L1", title: "..." }`：渲染 6 个保留键之外的字段；`data-testid="template-source-meta"` 元素存在并显示 `x` / `1` / `L1`。
  2. 给定 `structuredData.template = { id: "x", layer: "none", reason: "" }`：card 显示 `x` / `-` / `无匹配模板`。
  3. 给定 `structuredData.template = { title: "..." }`（老数据）：card 不渲染；过滤后 1 个字段。
  4. 给定 `structuredData.template = {}`（仅含保留键）：`EmptyState` 显示。
  5. 给定 `structuredData = null`：card 不渲染 + EmptyState 显示。
  6. **额外加固（超出完成标准最低要求，符合 AC-11 精神）**：显式断言"6 键全部不出现在渲染 DOM 中"—— 锁 AC-11 的字段过滤契约。
- [x] `pnpm --filter @metaedu/web test` 退出码 0；6 个 test case 全过。
- [ ] **未完成**：工作分支 `td-040-filtabspanel-vitest-coverage` 尚未 commit / push / PR / merge。当前 worktree 名 `worktree-agent-a9cfdaec8741f103c`（auto-generated），需 integrator rename 到正式分支名后再走提交。本卡状态保持 `🟡 进行中`，不进 `🟢 完成` 直至 Git 闭环收口。

**验证方式**
- `pnpm --filter @metaedu/web test` 退出码 0，6 test names 可见。
- `pnpm --filter @metaedu/web typecheck` 退出码 0。
- `pnpm --filter @metaedu/web lint` 退出码 0（`@metaedu/web#lint` 与 TD-039 备注的 `@metaedu/shared#lint` 阻塞无关联；本任务范围内绿色）。
- `rg -n "data-testid=\"template-source-meta\"" packages/web/src/` → 1 处定义 + 5 处测试断言。
- `python3 scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code；agent B 平行批次 in worktree `.claude/worktrees/agent-a9cfdaec8741f103c`，分支名 `worktree-agent-a9cfdaec8741f103c`，本 PR 合入前由 integrator rename 为 `td-040-filtabspanel-vitest-coverage`）。PR 描述中已声明 commit `edb4a08` 在 rebase 到 main `f0841f4` 时合并 main 引入的"TD-039 拆分 + TD-043 新建"元数据，冲突点仅在 TD-040 详细卡交付记录区（本节），手写合并保留 agent B 第一手实施细节 + 状态字段保持 `🟡 进行中` 直到合并后由 integrator 翻 `🟢 完成`。
  - 5 个文件变更（2 改 3 新 1 文档）：
    1. `packages/web/package.json`：`devDependencies` 新增 `vitest ^2.1.0` / `@vue/test-utils ^2.4.6` / `jsdom ^29.1.1`；`scripts` 新增 `test: "vitest run"`。
    2. `pnpm-lock.yaml`：与上述 3 个新增 devDep 同步锁定。
    3. `packages/web/vitest.config.ts`（NEW，14 行）：`vitest/config` + `@vitejs/plugin-vue` + `@` alias（与 `vite.config.ts` 对齐）+ `test.environment: "jsdom"`。零业务代码改动；不触碰 `vite.config.ts` 以保持开发 / 构建配置稳定。
    4. `packages/web/src/views/resource/FileTabsPanel.spec.ts`（NEW，163 行 / 6 个测试）：覆盖 TD-040 任务卡 5 个验收点（AC-12 case 1-5）+ 1 个 AC-11 字段过滤断言。6 键保留集合在测试文件内维护局部副本（`RESERVED_META_KEYS`），与 `FileTabsPanel.vue:159-166` 字面量保持一致；TD-039 合并后应改为 import `@metaedu/shared` 的 `TEMPLATE_META_RESERVED_KEYS`，并在交付记录里登记。
    5. `docs/03-engineering-governance/technical-debt.md`（本卡片交付记录）。
  - 行为变化声明：零。`FileTabsPanel.vue` 未被本任务改动；`vitest.config.ts` 是新增，不影响 `vite build` / `vite dev` / `vue-tsc` 链路；新增 `test` script 是新命令，不会被现有 CI / 门禁自动触发。
  - 验证摘要（cwd=packages/web）：`pnpm test` 退出码 0，6 passed in 19ms（verbose 输出 6 个 test 名：AC-11 / AC-12 case 1-5）；`pnpm typecheck` 退出码 0（零输出）；`pnpm lint` 退出码 0（零 warning）；`rg -n "data-testid="template-source-meta"" packages/web/src/` → 1 定义（`FileTabsPanel.vue:25`）+ 5 测试断言（`FileTabsPanel.spec.ts` 5 处 `.find(...)` / `.exists()` 引用，与 5 个 AC-12 case 一一对应）；`python3 scripts/check-engineering-docs` 退出码 0（`engineering docs checks passed`）；`git diff --check` 退出码 0。
  - Phase 1 探查记录（与 `td-031` / `td-035` 同结构）：
    - `vitest` / `@vue/test-utils` / `jsdom` 探查时**未**在 `packages/web/devDependencies`；`pnpm-lock.yaml` 也无相关条目。
    - 仓库内**无**任何 `*.spec.ts` / `*.test.ts` 文件（`packages/web/src/` 与全仓均 0 命中），属于引入"首次前端单测"基建的债。
    - `pnpm --filter @metaedu/web lint` 在 install 完成后 rc=0（ESLint v10 对 `@metaedu/web#lint` **不**阻塞；与 TD-039 备注"@metaedu/shared#lint 仍受 ESLint v10 阻塞"无关联）。
    - `pnpm add -D vitest@^2.1.0 @vue/test-utils@^2.4.6 jsdom` 在沙箱中 3.7s 完成，无网络 / lockfile 冲突；root `pnpm-workspace.yaml` 与根 `package.json` **未**被改动。
  - 已知限制 / 后续接力：
    - 本债不替换 `FileTabsPanel.vue:159-166` 的硬编码 6 键集合（TD-039 范围）；测试在 spec 文件内维护 `RESERVED_META_KEYS` 局部副本。TD-039 合并后，本 spec 应改为 `import { TEMPLATE_META_RESERVED_KEYS } from '@metaedu/shared/schemas/document'`，并在交付记录登记。任务卡备注已写明。
    - vitest 引入是**首次**前端单测基建。若后续需要 e2e / DOM 集成测试，本债未触达；可拆为独立 `TD-xxx`（"前端单测基线 + 共享测试 setup 文件"）。
    - `vitest.config.ts` 与 `vite.config.ts` 各自维护一份 `plugins([vue()])` + `resolve.alias` 是当前最小化做法（避免在 `vite.config.ts` 内加 `/// <reference types="vitest" />` + `test:` block 干扰 dev / build 链路）。若后续测试用例增多或需要共享 setup 文件，可考虑合并为 `defineConfig` + `vitest` 三斜线指令。
    - ESLint v10 状态：本任务因 `vue-tsc + vue-eslint-parser` 已稳定，未触发 v10 阻塞。`@metaedu/shared#lint` 的 v10 阻塞（TD-039 备注）**不**在本债范围。
### DOC-056: `check_req_status_consistency` 把父任务 `REQ-NNN` 与子任务 `REQ-NNN-K` 状态混聚的算法 bug

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 文档 / 工程脚本 / 质量门禁 |
| 事实源 | REQ-002-3 收口 / [PR TBD] |

**证据**
- `scripts/engineering/checks/_common.py:37` `REQ_ID_RE = re.compile(r"\bREQ-\d{3}\b")`：`\b` 在数字与 `-` 之间是 word boundary，导致 `REQ-002-3` 在 `search` / `match` 时匹到 `REQ-002`。
- `scripts/engineering/checks/product_planning.py:135` `REQ_ID_RE.search(path.name)`：把 requirement 文件名聚到父任务。
- `scripts/engineering/checks/product_planning.py:184` `REQ_ID_RE.search(cells[0] if ... else cells[1])`：把 current-work "最近完成" / "当前进行中" 任务列的子任务聚到父任务。
- 触发条件：父任务状态 ≠ 子任务状态时报警；2026-06-10 REQ-002-3 子任务翻 Done 时首次暴露（见 PR #154 提交注释中绕过说明）。
- REQ-006 子任务链（REQ-006 / REQ-006-1）此前未撞是因为子任务状态一直与父任务保持同步。

**问题**
- `check_req_status_consistency` 报警是 false-positive，导致后续维护者不敢对子任务状态单独维护。
- 当前合 main 仍存在此 bug 时，正确处理"父任务链收口"的方式只能是手动同步 4 处事实源 + 绕过 `current-work` 的"最近完成"区。

**完成标准**
- `REQ_ID_RE` 扩展为 `\bREQ-\d{3}(?:-\d+)?(?![-\d])`：识别 `REQ-NNN` 与 `REQ-NNN-K` 为不同 task id；不允许向后接续 `-数字`。
- 新增 `test_parent_and_child_req_with_different_status_do_not_collide` regression：父任务 Ready + 子任务 Done 不再报警。
- 仓库 `python3 scripts/check-engineering-docs` 在 REQ-002 / REQ-002-3 当前状态（父 Ready / 子 Done）下 rc=0。

**验证方式**
- `python3 -m pytest tests/engineering/test_check_engineering_docs.py -v` → 20 passed（19 既有 + 1 新增）。
- `python3 scripts/check-engineering-docs` → `engineering docs checks passed` rc=0。
- `git diff --check` clean。
- 行为边界检查：`fullmatch("REQ-002-3-extra")` → 0 命中（保留 `-\d+` 末端的字边界）；`fullmatch("REQ-00233")` → 0 命中（5 位数父任务不误匹为 4 位子任务）。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。代码 + 测试 + 状态同步 3 文件共 +5 / -3 行；零业务代码改动。原子拆分：
  1. `scripts/engineering/checks/_common.py`：`REQ_ID_RE` 模式扩为 `\bREQ-\d{3}(?:-\d+)?(?![-\d])`，允许 `REQ-NNN-K` 子任务格式；保留 `\b` 起始以避免误匹 `XREQ-002-3`；`(?![-\d])` 防止 `REQ-002-3` 回退到 `REQ-002`。
  2. `tests/engineering/test_check_engineering_docs.py`：新增 `test_parent_and_child_req_with_different_status_do_not_collide`，通过 minimal docs 模拟 backlog / milestone / current-work 三处父子状态不一致场景；测试同时在修脚本前 failing、修脚本后 passing。
  3. `docs/03-engineering-governance/current-work.md`：删除"当前进行中"区 REQ-002-3 残留 Ready 行（PR #153 merge 时残留，PR #154 撤回"最近完成"行时未触及此行；该行是脚本修复后暴露的真实不一致）。
- 行为变化声明：脚本逻辑收紧（更精确的 task_id 匹配），对 0 业务代码 / 0 API 行为有影响；仅影响 `check-engineering-docs` 跨事实源状态一致性 check。
- 验证摘要：脚本修复后自动暴露 main `current-work.md:19` 的 REQ-002-3 残留行；删除该行后 `check-engineering-docs` rc=0 恢复。
- 顺带说明：TD-039 / TD-040（REQ-002-3 code review follow-up）保持 ⚫ 待办。

### TD-041: FieldCard 递归渲染嵌套字段 + object children / array items 嵌套拖拽

状态：🟢 完成

**证据**
- REQ-002-1（PR #158）实现了 root 层 vuedraggable 拖拽排序，但 AC-2（object 子字段拖拽）和 AC-3（array items 拖拽）仅部分完成。
- `FieldCard.vue` 渲染 object / array 类型字段的展开详情时，**不渲染 `node.children` / `node.items`**——只有空态占位和"添加子字段"按钮，没有 `v-for` 迭代子字段。
- `FieldItem.vue` 仅在 root 层用 `<draggable :list="modelValue">` 包裹顶层 FieldCard 列表；组件树是**扁平**的（一层 draggable 列表），而数据树是**嵌套**的（Field 包含 `children?: Field[]` 和 `items?: Field[]`）。
- 当前架构下，object 子字段和 array items 在 UI 上不可见，也无法被拖拽排序。

**问题**
- REQ-002-1 spec 的 AC-2 / AC-3 明确要求 object 子字段和 array items 可拖拽排序，但当前实现因组件架构限制未达到。
- 嵌套字段在 UI 上不可见，用户无法直接查看和操作 object 的子字段列表或 array 的成员模板。
- 后续 REQ-002-4（容器互转二次确认）也需要嵌套字段的可见性。

**完成标准**
- `FieldCard.vue` 在 object 类型展开后，用 `<draggable :list="node.children">` 递归渲染 `FieldCard` 列表，使子字段可见且可拖拽排序。
- `FieldCard.vue` 在 array 类型展开后，用 `<draggable :list="node.items">` 递归渲染 `FieldCard` 列表，使成员模板可见且可拖拽排序。
- 递归 FieldCard 正确传递 `depth`（用于缩进）和事件冒泡（`remove` / `updateField` / `changeType` / `addChild` / `addColumn` / `removeColumn` / `copySubtree`）。
- 嵌套拖拽后 `template.fields` 的嵌套数组顺序与 UI 拖拽一致（保存后 reload 验证）。
- 不引入跨层级拖拽（vuedraggable `group` 跨级拖拽属于更复杂的 follow-up）。
- `pnpm typecheck` + `pnpm lint` 退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- REQ-002-1 spec AC-2 / AC-3 标记为完整完成。

**验证方式**
- `cd packages/web && pnpm typecheck && pnpm lint` 退出码 0。
- `scripts/check-engineering-docs` 退出码 0。
- 手测：打开含 object + array 字段的模板，展开 object → 子字段可见 → 拖拽子字段改变顺序 → 保存 → reload 确认顺序持久化。
- 手测：展开 array → 成员模板可见 → 拖拽改变顺序 → 保存 → reload 确认顺序。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。[PR #161](https://github.com/MarkDanile/MetaEduBase/pull/161) (squash merge commit `9d41b1e`) 合并到 main。
  - 新建 `packages/web/src/views/admin/FieldList.vue`：递归 draggable + FieldCard 包裹组件；props: fields, depth, expandedIds, matchedIds, searchQuery；MAX_DEPTH=5 守卫；CSS 嵌套缩进（margin-left + border-left）。
  - 修改 `packages/web/src/views/admin/FieldCard.vue`：新增 expandedIds/matchedIds/searchQuery props；expanded 从 local ref 改为 computed（从 expandedIds 读取）；object 子字段和 array items 区域替换为 FieldList 递归渲染；chevron 添加 rotate-180 动画。
  - 修改 `packages/web/src/views/admin/FieldItem.vue`：root 层改用 FieldList；新增 matchedIds computed；修 copySubtree 支持任意深度（新增 findNodeAndParent helper + 新 ID 分配）；修 removeColumn 事件 relay（不再硬编码 colIndex=0）；新增 collapseAll 方法（供父组件 template ref 调用）；defineExpose 暴露 collapseAll。
  - 修改 `packages/web/src/views/admin/TemplateEditorView.vue`：toggleAllCollapse 改为通过 template ref 调用 FieldItem.collapseAll；移除 window CustomEvent 逻辑。
  - Bug 修复：removeColumn 硬编码 colIndex=0 → 正确 relay (parentId, colIndex)；copySubtree root-only → findNodeAndParent 支持任意深度 + 新 UUID 分配。
  - [Spec](../02-delivery-plans/01-specs/2026-06-10-td-041-field-card-recursive-rendering.md) / [Plan](../02-delivery-plans/02-plans/2026-06-10-td-041-field-card-recursive-rendering-plan.md)。
- 行为变化声明：（1）object/array 子字段从不可见变为递归可见+可拖拽；（2）折叠/展开全部从 window CustomEvent 改为直接方法调用；（3）removeColumn 修复正确删除指定列；（4）copySubtree 修复支持任意深度复制。
- 验证摘要：`pnpm typecheck` 退出码 0；`pnpm lint` 退出码 0；`pnpm build` 退出码 0；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0；未运行：浏览器手测（沙箱无浏览器）。

### TD-042: REQ-002-2 后端集成测试在 PG 实例下验证

状态：🟢 完成

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 测试 / 交付 |
| 事实源 | REQ-002-2 交付时沙箱无 PG / [PR #159](https://github.com/MarkDanile/MetaEduBase/pull/159) |

**证据**
- `tests/contexts/template/test_template_reuse.py` 新增 8 条后端测试用例（clone / cross-tenant / version snapshot / pagination / rollback / import round-trip / key validation / duplicate sibling keys），但执行环境无 PG 实例，集成测试未实际运行。
- `packages/server-python/alembic/versions/007_template_versions.py` 迁移文件已提交但未在真实 DB 上执行 `make migrate`。
- `ruff check app/ tests/` + `import` 冒烟测试通过，证明代码语法正确，但功能正确性需集成测试验证。

**问题**
- REQ-002-2 的 6 个新端点 + version 快照 + 回滚逻辑未在真实 PG 环境下验证，可能存在运行时错误（如迁移不兼容、事务边界、并发 version_number）。
- 未验证 AC-20（DB 迁移可复现：upgrade / downgrade 成功）。

**完成标准**
- `make migrate` 升级成功；`make migrate-downgrade` 回退成功。
- `pytest tests/contexts/template/test_template_reuse.py -q` 全部通过。
- `pytest tests/contexts/template -q` 全部通过（回归）。

**验证方式**
- `cd packages/server-python && make migrate && make migrate-downgrade` 成功。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template/test_template_reuse.py -q` 全绿。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template -q` 全绿。

**交付记录**
- 2026-06-10 完成（接手工具：Claude Code）。在真 PG（`deploy-postgres-1`，pgvector/pgvector:pg16，监听 5432）下完成三条完成标准 + 顺带修 007 迁移 inline FK 在 asyncpg 反射下的 PK 解析缺陷。
  - **007 迁移 inline FK 修复**：`alembic/versions/007_template_versions.py` 在 `op.create_table` 之前先 `op.create_unique_constraint('uq_templates_id', 'templates', ['id'], schema='metaedu')` 给 `templates.id` 加显式 unique 约束；downgrade 顺序：`op.drop_table('template_versions')` → `op.drop_constraint('uq_templates_id', ...)`。根因：SQLAlchemy 2.0 + asyncpg 反射 `get_unique_constraints` 不返回 PK，inline `ForeignKeyConstraint(['template_id'], ['metaedu.templates.id'])` 编译时报"there is no unique constraint matching given keys"。PG 自身接受 FK 引用 PK（raw SQL 验证通过），但 asyncpg 走自己的 FK 解析路径不查 PK unique index，必须显式 unique。
  - **make migrate 升级成功**（cwd=packages/server-python）：`alembic upgrade head` → dev 库 `metaedu.alembic_version=007_template_versions`，`metaedu.template_versions` 表 11 列含 PK / `uq_template_versions_template_version` unique / `fk_template_versions_template_id` ON DELETE CASCADE / `fk_template_versions_tenant_id` / 2 index。rc=0。
  - **make migrate-downgrade 回退成功**：`alembic downgrade -1` → dev 库 `version_num=9466ea6e5d33`，`template_versions` 表 drop，`uq_templates_id` drop。rc=0。**再升回 head** 验证完整循环：dev 库回到 `007_template_versions`，所有约束回归，rc=0。
  - **init-test-db + 8 条 pytest 全绿**：`python -m app.shared.infrastructure.test_db_setup` → test 库 `metaedu_test.alembic_version` 从 `9466ea6e5d33` 升到 `007_template_versions`（走 `init_test_database` 内部 `_run_alembic_against(test_url_str)`，URL 覆盖为 test 库）。`pytest tests/contexts/template/test_template_reuse.py -v` → 8 passed（`test_clone_creates_deep_copy` / `test_clone_rejects_cross_tenant` / `test_update_writes_version_snapshot` / `test_list_versions_pagination` / `test_rollback_restores_snapshot` / `test_export_and_import_round_trip` / `test_import_rejects_invalid_key` / `test_import_rejects_duplicate_sibling_keys`），rc=0。
  - **回归**：`pytest tests/contexts/template -q` → 17 passed（8 reuse + 9 既有用例），rc=0。`ruff check app/ tests/` → All checks passed!，rc=0。
  - 行为变化声明：1) 新增约束 `metaedu.templates.uq_templates_id`（与 PK 并存，PG 允许且不冲突；不改变任何写入路径语义，仅作为 FK 反射的"匹配目标"）；2) `test_db_setup` 幂等初始化 test 库到 head。零业务代码、零 API 行为变化。
  - 验证摘要：dev 库 / test 库 两条迁移链路均经过 `upgrade → downgrade → upgrade` 循环验证；8 条 reuse + 9 条模板既有测试 + 全量 ruff 三条全过；零业务代码变更。
  - 未运行：浏览器手测（沙箱无浏览器；与本任务范围无关——本任务仅后端集成测试）。
  - 后续接力建议（不阻塞本任务完成）：在 PR review 时同步给 `app/contexts/template/application/service.py` 等使用 SQLAlchemy metadata 引用 `templates.id` 的位置加注释，说明"FK 引用 templates.id 依赖显式 uq_templates_id 约束"。

### TD-043: 打通后端 Python 对 `shared/schemas/document` 的 import 路径

状态：⚫ 待办

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 领域 | 后端 / 共享 schema / 基础设施 |
| 事实源 | 2026-06-10 并行批次 `td-039+td-040` 拆出（原属 TD-039 范围） / 关联 [TD-039](#td-039-6-键保留集合在-ts-端抽到-metaedusharedschemasdocument--spec-单一来源落地) |
| 父任务 | [TD-039](technical-debt.md#td-039-6-键保留集合在-ts-端抽到-metaedusharedschemasdocument--spec-单一来源落地)（范围拆分说明） |

**证据**
- 2026-06-10 并行批次 `td-039+td-040` 中，TD-039 agent 探查发现：仓库无顶层 `metaedu` Python 包；`packages/shared/` 是 TS-only pnpm workspace 包（`name: "@metaedu/shared"`，无 `__init__.py`、无 Python build）；`packages/server-python/pyproject.toml` 的 `tool.setuptools.packages.find` 只包含 `app*`；全仓 `grep "import metaedu.shared"` 0 命中。
- 后端 `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:19-20` 硬编码 6 键 `_TEMPLATE_META_KEYS` 仍存在。
- TD-039 收窄为 TS 端 + spec 落地后，本卡承接后端 Python 路径接入。

**问题**
- 后端 Python 端没有可达路径 import 共享 schema 常量；后端 `_TEMPLATE_META_KEYS` 与 TS 端 `TEMPLATE_META_RESERVED_KEYS` 仍是物理两个副本，contract drift 风险未消除。
- 后续子任务（REQ-002-4 引入 `schema_version` / 任何 schema 演进）扩展保留键时，后端不会自动跟上。

**完成标准（候选路线，spike 后定稿）**

> 本卡范围跨语言 + 跨包结构，属高风险技术债，进入实现前必须先做 spike 评估三条候选路线并选一：

- **路线 A：TS 端 codegen**
  - 在 `packages/shared/` 新增构建脚本（例 `scripts/codegen/shared-schemas.ts`），从 Zod schema 派生 string-only 常量（`TEMPLATE_META_RESERVED_KEYS`）并 emit Python 文件到 `packages/server-python/app/shared/schemas/document.py`。
  - 后端 import 路径 `from app.shared.schemas.document import TEMPLATE_META_RESERVED_KEYS`。
  - codegen 接入 `pnpm build` / `pre-commit` / CI 链路，确保 TS schema 变化时 Python 副本同步。
- **路线 B：Python 端 `metaedu/` namespace shim + 手动维护**
  - 新建 `packages/server-python/metaedu/shared/schemas/document.py`（与 `app/` 同级），`pyproject.toml` `tool.setuptools.packages.find` 扩为同时包含 `app*` 与 `metaedu*`。
  - Python 文件手工维护 6 键集合副本。
  - 风险：物理上仍是两份源，codegen / linter 需补断言"两份列表内容必须一致"。
- **路线 C：把后端常量反向引用 TS runtime 评估**
  - 用 Python 调 Node 子进程读取 `packages/shared/src/schemas/document.ts` 的导出（不推荐，CI 链路脆弱、运行期依赖过重）。

**默认推荐路线 A**：从契约稳定性 + 单点修改成本看，codegen 是唯一真"single source of truth"路径。**实现前先按 `task-modes.md#spike--调研` 跑 spike**，对比三条路线的时间盒 / 风险 / 维护成本，输出推荐 + 拒选理由，再进入实现。

**验证方式（路线 A 落地后）**
- `pnpm typecheck` 退出码 0（codegen 脚本与共享 schema 同步）。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py tests/contexts/document/test_extract_template_prompts.py -q` 仍 21 passed。
- `rg -rn "RESERVED_META_KEYS|TEMPLATE_META_KEYS|6 个保留键" packages/` 输出 1 个常量声明（TS 端）+ 1 个 codegen 引用（codegen 脚本）+ 1 个 Python 副本（codegen 产物），0 个手写硬编码。
- `python3 scripts/check-engineering-docs` 退出码 0。
- `git diff --check` 退出码 0。

**交付记录**
- 2026-06-10：TD-039 范围拆分登记（本卡从原 TD-039 拆出，承接后端 Python 路径接入）。
