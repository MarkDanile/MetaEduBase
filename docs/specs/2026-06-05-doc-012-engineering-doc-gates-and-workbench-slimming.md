# DOC-012 工程文档自动门禁与工作台瘦身 — Spec

## 背景

近期跨 Codex / Claude Code 协作已经形成基本闭环：任务入口统一到
`docs/engineering/current-work.md`，技术债进入 `technical-debt.md`，长期
spec / plan 进入 `docs/specs/*` 和 `docs/plans/*`。

但 TD-020 复核暴露了几类仍容易反复出现的问题：

- 文档描述与代码实现不一致。
- plan 中存在断链。
- `work-log.md` 回填时误替换已有索引。
- 验证声明写成无条件通过，但缺少可复核的命令输出、CI 链接或环境说明。
- `current-work.md` 为了承载规则说明逐渐变长，增加 AI IDE 每次开工的阅读成本。

继续把所有问题写成更多自然语言规则，会增加 token 消耗和 checklist fatigue。
更合适的方向是：入口规则保持短，能自动检查的事项改成脚本门禁。

## 目标

建立一个轻量工程文档门禁，并瘦身当前工作台入口，让后续 AI IDE 在提交前
能用固定命令发现常见文档和流程问题。

## 范围

### In scope

- 新增一个工程文档检查命令或脚本，例如 `scripts/check-engineering-docs`；主实现收敛到 `scripts/engineering/*`。
- 检查 `docs/engineering/current-work.md` 的区域约束：
  - “下一批候选任务”只允许 1 到 3 个未完成候选。
  - 候选区不得出现 `🟢 完成`。
  - “最近完成”最多 5 行。
- 检查已完成计划文件不得残留活动式 `- [ ]`，但允许明确标记为 out of scope
  或已绑定后续任务的未完成项。
- 检查关键 Markdown 链接或任务事实源路径，至少覆盖 `docs/plans/*`、
  `docs/specs/*`、`docs/engineering/*.md` 内的相对链接。
- 检查 `work-log.md` 的追加式索引原则，避免无说明删除或替换近期任务索引。
- 检查验证声明的证据格式，避免把无法复核的“全量 pytest passed”写成无条件通过。
- 将 `current-work.md` 的长规则说明迁移或压缩到更合适的规则文档，例如
  `docs/engineering/rules/workbench.md`。
- 在 `quality-gates.md` 或 `git-workflow.md` 中引用该文档门禁命令，避免重复展开规则。
- `scripts/*` 只作为稳定兼容入口，仓库治理工具实现优先放在 `scripts/engineering/*`。

### Out of scope

- 不改变业务代码。
- 不改变现有技术债、功能需求或 Git 分支策略的语义。
- 不引入大型项目管理工具或复杂 CI 平台。
- 不强制所有历史 Markdown 一次性完全符合新检查；必要时允许脚本先聚焦当前事实源
  或提供明确白名单。

## 设计原则

### 1. 规则短，检查硬

入口文档只告诉执行者“运行哪个命令”和“失败要修复或登记”，不要把脚本已经能检查的
细节重复写成大段自然语言。

### 2. 先检查高频漏项

第一版只覆盖近期反复出现的问题：

- 候选区混入完成任务。
- 最近完成无限扩张。
- 已完成 plan 残留活动式 `- [ ]`。
- plan/spec 链接断裂。
- `work-log.md` 索引误删。
- 验证声明缺少证据。

### 3. 失败信息必须可操作

脚本失败时应输出文件、行号、问题和建议动作。不要只输出“failed”。

### 4. 保留渐进式披露

`AGENTS.md` / `CLAUDE.md` 仍作为短入口；`current-work.md` 作为工作台；
专项细节进入 `docs/engineering/rules/*`；脚本作为完成门禁的一部分。

## 验收标准

- 有一个固定命令可以运行工程文档门禁。
- 工程文档门禁有聚焦的实现目录，兼容入口不会迫使执行者记住内部文件路径。
- 该命令能发现至少以下问题类型：
  - 候选区 `🟢 完成` 行。
  - 最近完成超过 5 行。
  - 已完成 plan 残留活动式 `- [ ]`。
  - 相对 Markdown 链接断裂。
  - `work-log.md` 近期索引被删除或替换。
  - 无证据的“全量 pytest passed”类声明。
- `current-work.md` 的入口说明更短，长模板或细则迁移到规则文档。
- `quality-gates.md#完成门禁` 或 `git-workflow.md#快速交付通道` 引用新命令。
- 文档-only 验证命令能在本地复现，失败时能定位到具体文件和行。

## 验证方式

- 运行新增工程文档门禁命令，退出码 0。
- 直接运行 `scripts/engineering/check_engineering_docs.py`，确认与兼容入口行为一致。
- 人工临时制造一个候选区完成行或断链，确认脚本能失败并给出可操作提示；验证后还原。
- `rg -n "check-engineering-docs|工程文档门禁" docs/engineering AGENTS.md CLAUDE.md` 能命中新命令入口。
- `current-work.md` 的“当前进行中 / 下一批候选任务 / 最近完成”区域仍可直接扫视当前任务。
