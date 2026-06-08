# TD-032 治理超大源码文件并建立文件规模拆分原则 — Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-08-td-032-large-source-files.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 卡片
- 当前执行模式: `superpower`（跨 3+ 文件、涉及架构 / 前端 / 后端 / 工程治理、需先 spec / plan）
- 分支: `refactor/td-032-large-source-files`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 切片总览

按 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁` 与
`docs/03-engineering-governance/01-rules/quality-gates.md#验证表述规范` 的精神，本任务
拆 4 个独立 PR。每个 PR 独立验证、PR 描述遵循 Summary / Scope / Validation / Risks / Docs。

| 切片 | 范围 | 状态 | 期望行数变化 | 必跑验证 |
|------|------|------|--------------|----------|
| 1 | 基线 + 原则登记 + 任务卡 | ⚪ 待切片 | 无业务代码变化；新增 1 个基线文件 + 1 个 plan / spec 已在仓库 | `scripts/check-engineering-docs`、`git diff --check` |
| 2 | >1000 行的工程脚本（`check_engineering_docs.py`）拆分 | ⚪ 待切片 | 1003 → 拆出 ≥2 个聚焦模块 | 文档门禁 + 脚本自身能继续运行且输出不变 |
| 3 | >500 行的后端业务源码（`document/tasks.py` / `structured_data/tasks.py`）拆分 | ⚪ 待切片 | 929 / 671 → 横切 helper 抽到 `app/shared/tasks/lifecycle.py`（参考 TD-005） | `pytest -q`、`ruff check app/ tests/` |
| 4 | >500 行的前端业务视图（`DatabaseView.vue` / `TemplateModal.vue`）拆分 | ⚪ 待切片 | 701 / 665 → 子组件化或视图编排化 | `pnpm --filter @metaedu/web typecheck && lint && build` |

切片 5+（500 附近候选 `document/router.py` / `ResourceLibraryView.vue` 与 CSS / 设计系统
拆分）由后续任务独立 spec / plan 承载，本 plan 不展开。

## 切片 1：基线 + 原则登记 + 任务卡

### 1.1 新建基线文件

- [ ] 起草 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：
  - 顶部「维护规则」段：扫描命令、4 档分组、每切片交付后必须回写基线。
  - 表格 1：>1000 行（`main.css` 1343 / `check_engineering_docs.py` 1003），状态 `🔵 例外已登记`。
  - 表格 2：>500 行业务 / 工程源码（`document/tasks.py` 929 / `DatabaseView.vue` 701 /
    `structured_data/tasks.py` 671 / `TemplateModal.vue` 665），状态 `⚪ 待切片`。
  - 表格 3：500 行附近高风险候选（`document/router.py` 494 / `ResourceLibraryView.vue`
    490），状态 `⚪ 待切片`。
  - 表格 4：合规基线样例（`<=500` 行的关键共享 / 入口文件，如 `coding-style.md` 本身、
    `LayoutView.vue` 387 / `LoginView.vue` 377 / `FieldCard.vue` 368），证明原则可被
    满足，状态 `🟢 已合规`。
  - 每行至少有 1 句「例外 / 拆分说明」。
- [ ] 与 `technical-debt.md#td-032` 证据段中的行数核对一次，差异记录为「维护规则」段的
  注意事项（避免漂移）。

**验证点**：表格 4 档齐全；每行有状态 + 说明；行数与 `technical-debt.md#td-032` 一致。

### 1.2 更新 `coding-style.md`

- [ ] 复用 `docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界`
  现有原则（≤500 默认；>500 必须说明理由；>1000 不得堆新职责），**不**改写现有措辞。
- [ ] 在该段末尾新增「拆分层级」小节，按 spec §1 表格给出 5 种场景的推荐拆法。
- [ ] 在该段末尾新增「开发顺序硬约束」小节：spec / plan 阶段先给目录和文件结构再写代码。
- [ ] 在该段末尾新增「治理与切片记录」小节：基线文件路径 + 每切片交付后回写。

**验证点**：`git diff docs/03-engineering-governance/01-rules/coding-style.md` 只命中
该段；其他段不变。

### 1.3 升级任务卡

- [ ] `docs/03-engineering-governance/current-work.md`「当前进行中」表格新增 TD-032 行：
  - 状态：`🟡 进行中`
  - 优先级：P2
  - 领域：可维护性 / 架构 / 前端 / 后端 / 工程治理
  - 当前进展：spec / plan 起草完成，基线与 `coding-style.md` 段尾扩写完成
  - 下一步：切片 2（`check_engineering_docs.py` 拆分）单独 spec / plan
  - 验证：见本切片验证
- [ ] 「下一批候选任务」移除 TD-032（已升到「当前进行中」），候选区补一个 P3 候选（例如
  REQ-005 / REQ-006，由当前 `current-work.md` 候选区剩余 2 项中挑选；本次默认不替换，由
  切片 1 完成后视情况再调整）。

**验证点**：`scripts/check-engineering-docs` 退出码 0；候选区 1-3 项且无 `🟢 完成`。

### 1.4 验证

- [ ] `scripts/check-engineering-docs` 退出码 0
- [ ] `git diff --check` 退出码 0
- [ ] `git diff --name-status` 只包含：`docs/02-delivery-plans/01-specs/2026-06-08-td-032-large-source-files.md`、
  `docs/02-delivery-plans/02-plans/2026-06-08-td-032-large-source-files-plan.md`（本文件）、
  `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`、
  `docs/03-engineering-governance/01-rules/coding-style.md`、
  `docs/03-engineering-governance/current-work.md`，无业务代码、无生成物。
- [ ] 行为变化声明：docs-only 增量，零业务代码变更。

### 1.5 Git 闭环（切片 1）

- [ ] 提交：`docs(governance): establish TD-032 large source file baseline and rule`
- [ ] push：`git push -u origin refactor/td-032-large-source-files`
- [ ] PR：`gh pr create --title "docs(governance): TD-032 baseline + file-size rule" --body "..."`，
  body 含 Summary / Scope / Validation / Risks / Docs
- [ ] `gh pr checks` 通过
- [ ] `gh pr merge --squash --delete-branch`
- [ ] 合并后回写 `docs/03-engineering-governance/work-log.md` 索引 + `current-work.md` 切片
  1 状态行 + `technical-debt.md#td-032` 备注追加「切片 1 已合并」+ 基线文件表头
  `最后回写` 字段写本切片 merge commit

## 切片 2：>1000 工程脚本拆分（`check_engineering_docs.py`）

由单独 spec / plan 承载；本切片开工时按当时实际职责重新规划（候选：按检查类型拆
`checks/*.py`，主文件只做入口聚合；或拆 `checks/config.py` 单独承载稳定编号与索引配置）。

预期验证：
- `scripts/check-engineering-docs` 退出码 0，且对 baseline 行为零变化（同样的输入产出
  同样的「engineering docs checks passed」 / 失败摘要）。
- `tests/engineering/test_check_engineering_docs.py` 继续全绿。
- 主文件行数显著下降（目标：≤600 行）。

## 切片 3：>500 后端业务源码拆分

由单独 spec / plan 承载；优先采用 TD-005 已验证过的模式（横切 helper 抽到
`app/shared/tasks/lifecycle.py` 等）。

预期验证：
- `pytest -q` 全量通过（baseline 期望与最近一次一致或更多）。
- `ruff check app/ tests/` 退出码 0。
- 两文件 + 抽出的 helper 模块总行数相比原行数有可观察下降；新增 helper 模块有聚焦测试。

## 切片 4：>500 前端业务视图拆分

由单独 spec / plan 承载；优先把稳定区块抽成子组件（`DatabaseView` 的 meta bar / pipeline
status / tab content / KG 概览；`TemplateModal` 的字段编辑 / 预览 / 操作按钮）。

预期验证：
- `pnpm --filter @metaedu/web typecheck && lint && build` 退出码 0。
- 4 主题视觉不退化（沙箱无浏览器时降级为 typecheck + lint + `git diff` 自检）。
- 行为不变：用户可见交互（上传 / 解析 / 抽取 / KG 加载 / 编辑）一致；如声明行为变化
  必须落到 `quality-gates.md#行为变化声明检查`。

## 任务拆分（按 plan-do 步骤）

1. 完成 spec / plan 起草（已完成）。
2. 切片 1：基线 + 原则 + 任务卡登记。
3. 切片 2：单独 spec / plan → 拆分 `check_engineering_docs.py`。
4. 切片 3：单独 spec / plan → 拆分 `document/tasks.py` / `structured_data/tasks.py`。
5. 切片 4：单独 spec / plan → 拆分 `DatabaseView.vue` / `TemplateModal.vue`。
6. 全 4 切片完成后：`technical-debt.md#td-032` 状态从 `🔵 就绪` 改为 `🟢 完成`；基线文件
   表格更新；work-log 追加总索引。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 基线文件长期不更新退化为历史快照 | 「维护规则」段明确每切片必须回写；后续可由 `check_engineering-docs` 增一致性检查 |
| 开发顺序硬约束没有自动化检查 | 当前靠 PR review 拦截；后续可由 plan 模板 / review 工具补强 |
| 切片 2/3/4 一次性 PR 过大 | 本 plan 强制每切片单独 spec / plan + 独立 PR + 独立验证 |
| 业务视图拆分引入行为回归 | 切片 4 强制走 `quality-gates.md#前端请求生命周期等价矩阵` + 行为变化声明 |
| `main.css` 1343 行无人接手 | 基线文件登记 `🔵 例外已登记` + 「后续切片计划」段说明由设计系统 token 化 + CSS 分模块构建共同收敛 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件。
- [ ] `git diff --name-status` 只包含本任务相关文件；无业务代码、无生成物。
