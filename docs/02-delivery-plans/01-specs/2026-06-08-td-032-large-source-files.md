# TD-032 治理超大源码文件并建立文件规模拆分原则 — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
登记了 2026-06-08 源码行数扫描结果：

- **>1000 行**：`packages/web/src/assets/css/main.css` 1343 行；
  `scripts/engineering/check_engineering_docs.py` 1003 行。
- **>500 行业务 / 工程源码**：`packages/server-python/app/contexts/document/application/tasks.py`
  929 行；`packages/web/src/views/database/DatabaseView.vue` 701 行；
  `packages/server-python/app/contexts/structured_data/application/tasks.py` 671 行；
  `packages/web/src/views/admin/TemplateModal.vue` 665 行。
- **500 行附近高风险候选**：
  `packages/server-python/app/contexts/document/interfaces/api/router.py` 494 行；
  `packages/web/src/views/resource/ResourceLibraryView.vue` 490 行。

`docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界` 已经有原则
（默认 ≤500；>500 必须说明理由；>1000 不得堆新职责），但仓库里**没有**与该原则配套的
"基线 + 例外清单 + 拆分层级 + 切片记录"。结果是：原则只是文档里的一段话，没有事实源支撑
"哪些文件是已知例外、为什么例外、什么时候必须拆"。

本 spec 不一次性重写所有超大文件，而是固化"如何管理超大文件"这件事本身：建立基线 +
例外清单 + 拆分层级 + 后续按切片逐步拆分；并把"大需求 / 跨模块开发先给目录和文件结构"
作为开发顺序硬约束写入 `coding-style.md`。

## 目标

1. 在仓库内建立超大源码文件基线，登记例外与拆分状态，事实源是
   `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`。
2. 在 `docs/03-engineering-governance/01-rules/coding-style.md` 现有「文件规模与职责边界」
   段补全拆分层级与开发顺序硬约束，让原则有可执行细则。
3. 后续切片按"先 >1000、再 >500、最后 500 附近高风险候选"的顺序独立 PR、独立验证；每个
   切片交付后回写基线。
4. **本 spec 不承诺在一次 PR 内把上面 6 个超大文件全部拆分到 ≤500 行**；它建立的是治理
   框架与首批切片的可执行计划。

## 范围

### In scope

- 新建基线文件 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`，
  包含：
  - 扫描命令（与 `technical-debt.md#td-032` 证据段一致）。
  - 4 档分组（>1000 / >500 / 500 附近 / 合规基线）的文件清单 + 行数。
  - 每行的"状态"列：`🟢 已拆分` / `🔵 例外已登记` / `⚪ 待切片`。
  - 例外说明（生成文件、lockfile、快照、静态大数据、数据库迁移、历史兼容样式、明确登记
    的工程脚本）。
- 更新 `docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界`：
  - 复用现有原则（≤500 默认、>500 说明理由、>1000 不得堆新职责），**不**改写。
  - 新增"拆分层级"小节：横切 vs 业务、helper 抽取、视图分块、router / service 拆分、
    `__init__.py` 暴露面。
  - 新增"开发顺序硬约束"小节：大需求 / 跨模块开发进入实现前，先给目标目录和文件结构，
    再生成代码。
  - 新增"治理与切片记录"小节：基线文件路径、每切片交付后回写基线。
- 在 `docs/02-delivery-plans/02-plans/2026-06-08-td-032-large-source-files-plan.md` 给出
  4 个切片的执行顺序（基线 + 原则 / >1000 拆分 / >500 拆分 / 500 附近治理），每个切片
  独立 PR、独立验证。
- 在 `docs/03-engineering-governance/current-work.md` 移动 TD-032 任务卡到「当前进行中」。

### Out of scope

- 不在本次 spec / plan 内启动 >1000 业务代码的拆分重构；该工作由后续切片独立 spec / plan
  承载（避免一次性 PR 过大）。
- 不动业务行为；不删除任何历史兼容样式 / 装饰动效 / 业务映射。
- 不动 `main.css`（1343 行）的内容；其规模由设计系统 token 化与未来 CSS 分模块构建
  共同收敛，留到单独切片。
- 不动 `check_engineering_docs.py`（1003 行）的实现；其规模与门禁逻辑强耦合，留到单独
  切片。
- 不在 spec / plan 阶段就确定每个超大文件的具体拆分边界；切片开工时按当时实际职责
  重新规划。

## 设计要点

### 1. 拆分层级（写入 `coding-style.md`）

按"职责 → 边界"给后续切片提供可复用模板：

| 场景 | 推荐拆法 | 适用例子 |
|------|----------|----------|
| Celery 任务文件（任务编排 + 业务步骤混在一起） | 横切 helper 抽到 `app/shared/tasks/`；任务编排只负责拼装步骤 | `document/tasks.py`、`structured_data/tasks.py` |
| Router 聚合多个 endpoint | 按 `resource_type` 或 `action` 拆 `*_router.py` 子文件，主 router 暴露 namespace | `document/router.py`（>500 附近） |
| 单一 Vue 视图承载多个独立 tab / 区块 | 把稳定区块（meta bar、pipeline status、tab content）抽成子组件；视图只剩编排 | `DatabaseView.vue`、`ResourceLibraryView.vue` |
| 大型 Python service 同时承担编排与基础设施调用 | 编排逻辑保留在 service；基础设施调用按 `repository` / `client` 拆出 | 与 TD-005 / TD-006 经验一致 |
| CSS / 工程脚本 | 拆模块文件 + 入口聚合；或拆配置与执行 | `main.css`（按 token / 组件 / 主题分文件） / `check_engineering_docs.py`（按检查类型分文件） |

拆分层级不强制所有超大文件都按同一套执行；它提供"至少要能解释为什么这样拆"的可选方案。

### 2. 例外清单（写入基线文件）

按 `coding-style.md` 现有原则，下列文件**可以**不受 500 行目标约束，但仍要在基线里登记
"为什么是例外 + 后续是否需要治理"：

- 生成文件（如 `auto-imports.d.ts`、loc 锁定的 API 客户端、构建产物）。
- lockfile（`pnpm-lock.yaml`、`requirements*.txt`）。
- 静态大数据、数据库迁移、测试 fixture 大块文本。
- 历史兼容样式（如 `main.css` 早期主题与 `liquid-*` 兼容别名，迁移未完成阶段）。
- 明确登记的工程脚本（与门禁强耦合，单独切片治理）。

例外文件**不得**继续承担"新职责"；基线文件登记例外时，必须写"后续切片计划"或明确
"不拆分原因"。

### 3. 开发顺序硬约束（写入 `coding-style.md`）

在 `coding-style.md#文件规模与职责边界` 末尾新增：

> 大需求或跨模块开发进入实现前，**必须**先在 spec / plan 中给出目标目录和文件结构
> （含每个新文件预计承担什么、是否有横切 helper、是否需要把现有超大文件再切一档），再
> 生成代码。如果发现 spec / plan 阶段没有给出文件结构，回退到 plan 阶段补完再开始写
> 代码。

这条硬约束是 spec 层的"过程质量门禁"；它不替代 lint / typecheck / pytest，但保证
"未来新增的代码不再以单文件膨胀的方式成长"。

### 4. 切片记录格式（基线文件）

每行使用统一格式：

```md
| 文件 | 行数 | 档位 | 状态 | 例外/拆分说明 |
|------|------|------|------|---------------|
| `packages/web/src/assets/css/main.css` | 1343 | >1000 | 🔵 例外已登记 | 历史兼容样式与 4 主题 token；按设计系统 token 化 + CSS 分模块构建在后续切片治理 |
```

`档位` 是「>1000 / >500 / 500 附近 / 合规」；`状态` 是「🟢 已拆分 / 🔵 例外已登记 /
⚪ 待切片」。`例外/拆分说明` 至少 1 行。

## 完成标准

1. 新建 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`，包含：
   - 扫描命令。
   - 4 档分组的文件清单 + 行数（与 `technical-debt.md#td-032` 证据一致）。
   - 每行的"状态" + "例外/拆分说明"。
2. `docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界` 在现有
   原则基础上新增"拆分层级"和"开发顺序硬约束"两个小节；改动 diff 局限在本段内，不动
   其他段。
3. `docs/02-delivery-plans/02-plans/2026-06-08-td-032-large-source-files-plan.md` 落地
   4 切片计划，每个切片含目标、行数期望变化、验证方式、风险。
4. `docs/03-engineering-governance/current-work.md` 任务卡登记：分支
   `refactor/td-032-large-source-files`、spec / plan 链接、状态 🟡 进行中。
5. `scripts/check-engineering-docs` 退出码 0。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选文档-only
行（本次 spec / plan 阶段不写业务代码）：

```bash
scripts/check-engineering-docs
git diff --check
```

并按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为 docs-only 增量（新增 1 个基线文件、`coding-style.md` 段尾扩 2 个小节、新增
> 1 个 plan 文件、current-work 任务卡状态升级），**零业务代码变更**。`coding-style.md`
> 仅在「文件规模与职责边界」段内新增"拆分层级"和"开发顺序硬约束"两个小节，原有原则
> 措辞与示例不变。

## 风险与后续

- 风险：基线文件如果长期不更新，会重新退化成"历史快照"。已在基线文件加 `维护规则` 段
  要求每切片交付后回写；后续若 `scripts/check-engineering-docs` 能补一行扫描命令的
  一致性检查，会更稳。
- 风险：开发顺序硬约束目前只在 `coding-style.md` 写明，没有自动化检查。后续可由
  `compound-engineering-plugin` 的 plan 模板 / review 工具补强；本 spec 不强求自动化。
- 后续：每个切片单独 spec / plan；本 plan 仅承载切片 1（基线 + 原则 + 任务卡登记），
  切片 2/3/4 在 PR 时按"目标文件当时实际职责"重新规划。
- 后续：基线文件登记的所有 `🔵 例外已登记` 项目都应最终落到 `🟢 已拆分` 或明确
  `Dropped`（不会治理），不再保留为模糊状态。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把 TD-032 任务卡保留在
「当前进行中」并继续切片工作；待所有 4 切片交付后再归档到「最近完成」并把状态改为
`🟢 完成`。技术债总账 `technical-debt.md#td-032` 在切片全部交付时一次性回写交付记录。
