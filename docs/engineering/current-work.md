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
- 完整 Git 闭环结束后，任务卡片不得保留“以最终回复为准”“提交后更新”“待最终确认”等交付占位；PR 链接优先作为交付事实源，merge commit 默认可通过 PR 查询，只有文档已存在占位或任务总账明确要求时才需要回填。
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
- `最近完成`：最多保留最近 5 个完成任务摘要；详细交付事实回到 `docs/engineering/work-log.md`、对应总账、plan 或 PR。
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

### TD-020: 统一 LLM provider resolver 与 factory 优先级事实源

状态：🟡 进行中
类型：技术债
领域：Backend / AI / 可维护性
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`chore/td-020-llm-provider-factsource`

需求来源：
- Spec: [docs/specs/2026-06-05-td-020-provider-resolver-factory.md](../specs/2026-06-05-td-020-provider-resolver-factory.md)
- Plan: [docs/plans/2026-06-05-td-020-provider-resolver-factory-plan.md](../plans/2026-06-05-td-020-provider-resolver-factory-plan.md)
- 技术债: [docs/engineering/technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源](technical-debt.md)
- 架构约束: 后端 LLM 模块集中在 `packages/server-python/app/shared/llm/`
- 任务模式: 技术债修复（按 task-modes.md#技术债修复 路由；plan-do 路径执行，因为 spec/plan 已落在 docs/ 下无需插件目录）

当前进展：
- 已完成：扫描 `factory` / `provider_resolver` / `chat` / `embed` / `chat_with_fallback` / `ai_router` / `tests/shared/test_provider_resolver.py`；spec/plan 落档；用户确认路线 A（收敛到单一事实源）与本轮一直合并 main。
- 正在处理：TASK-1 `factory.RESOLVER_PROVIDER_NAMES` + `resolver_default_provider()`。
- 未完成：TASK-2 重写 `provider_resolver.py`；TASK-3 测试；TASK-4 端到端验证；TASK-5 文档同步。

下一步：
1. 切分支 `chore/td-020-llm-provider-factsource` 并实现 TASK-1/2。
2. 跑 TASK-3 单测 + TASK-4 端到端 pytest + ruff。
3. 提交 → push → gh pr create → squash merge → 回 main 收口。
4. 更新 `technical-debt.md` / `current-work.md` / `work-log.md` 与本 plan 顶部交付历史。

验证状态：
- 未运行：暂未跑验证（代码未改）。
- 已运行：扫描阶段未执行 pytest / ruff，将在 TASK-4 收口。

交接备注：
- 路线 A：resolver 复用 factory 子集与归一化；零业务行为变化；中文提示文案与 provider_name 仍为 `qwen`。

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/engineering/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| （暂无；TD-020 已移至「当前进行中」） | - | - | - | - |

## 最近完成

最近完成区只保留摘要，详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | DOC-011 技术债总账结构化展示优化 | 🟢 完成 | `technical-debt.md` 增加任务总览表和结构化任务卡片；长 `备注` 压缩为交付记录、事实源和验证摘要，降低扫视成本。 | `docs/engineering/technical-debt.md` |
| 2026-06-05 | DOC-010 收敛完成门禁并瘦身重复流程规则 | 🟢 完成 | 将通用收尾检查集中到 `quality-gates.md#完成门禁` 6 项；`workflow.md`、`task-modes.md`、`git-workflow.md` 和 AI 入口文件改为引用，减少重复规则和 token 开销。 | `docs/engineering/rules/quality-gates.md#完成门禁` |
| 2026-06-05 | TD-022 收口早期已完成计划文件的活动式未勾选项 | 🟢 完成 | 5 个早期 plan（TD-004/005/006/007/015）顶部补交付历史段，154 行 `- [ ]` → `- [x]`，与 TD-021 收口 TD-016/017/018/019 模式一致。 | `docs/engineering/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项` / [PR #44](https://github.com/MarkDanile/MetaEduBase/pull/44) |
| 2026-06-05 | TD-021 收口已完成计划文件和候选区状态同步漏洞 | 🟢 完成 | 收口 TD-016/017/018/019 历史 plan 未勾选项；补强候选区、最近完成和已完成 plan 的提交前硬检查，并登记 TD-022。 | `docs/engineering/technical-debt.md#td-021-收口已完成计划文件和候选区状态同步漏洞` |
| 2026-06-05 | TD-019 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 | 🟢 完成 | 把 polling 派生从调用方下沉到 query hook 的 `refetchInterval: (query) => ...` 函数形式，从 `query.state.data` 派生；避开 setup 阶段 TDZ，行为完全不变。 | `docs/engineering/technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误` / [PR #42](https://github.com/MarkDanile/MetaEduBase/pull/42) |
