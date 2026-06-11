# 跨 AI 开发工作流

本规范用于统一 Codex、Claude Code、superpower、EveryInc/compound-engineering-plugin 以及其他 AI IDE 或插件的协作方式。工具可以不同，但任务入口、规范目录、计划来源、验证和状态更新必须一致。

## 核心原则

- 仓库文档是事实源，插件是执行工具。
- 任务状态统一维护在 `docs/03-engineering-governance/current-work.md`。
- 任务状态更新必须使用 `状态：颜色 状态名` 格式；颜色图例见 `docs/03-engineering-governance/current-work.md`。
- 修改 `docs/03-engineering-governance/current-work.md` 或任务状态前，必须读取 `docs/03-engineering-governance/01-rules/workbench.md`。
- `docs/03-engineering-governance/current-work.md` 是活文档。实现、验证或 Git 阶段变化后，执行者必须同步任务卡片。
- `docs/03-engineering-governance/current-work.md` 是交接工作台，不是历史档案。完成任务超出保留窗口后，归档到对应事实源，并在 `docs/03-engineering-governance/work-log.md` 保留索引。
- `docs/03-engineering-governance/current-work.md` 的“最近完成”只保留短摘要；详细验证输出、行为变化、复盘和 PR 进入 `docs/03-engineering-governance/work-log.md`、对应总账、plan 或 PR。
- 最终回复不是事实源。完整 Git 闭环完成后，必须清除过期状态和交付占位；PR 链接优先作为交付事实源，merge commit 默认通过 PR 查询，只有文档占位或任务总账明确要求时才回填到仓库。
- 产品规划、里程碑、迭代和需求池统一放在 `docs/01-product-planning/*`；进入交付后的长期需求文档放在 `docs/02-delivery-plans/01-specs/*`，实施计划放在 `docs/02-delivery-plans/02-plans/*`。
- 规划层负责管理方向和需求池，不能替代交付层；进入开发后，spec / plan / 验证结果仍以交付层和工程治理层为准。
- `docs/90-compat-legacy/superpowers/*` 只作为历史目录或插件兼容输出目录，不作为新任务默认事实源。
- superpower、compound-engineering-plugin 或其他插件生成的 spec/plan 只可作为兼容输出；用于本次开发前，必须迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`，并在任务卡片中登记原始插件输出。
- 不能假设插件会自动遵守仓库新路径。生成前要在提示词中明确规范输出路径；生成后运行文档门禁，确认没有重新出现旧顶层文档入口。
- 开发前必须明确本次任务卡片、相关计划、相关约束和验收标准。
- 会修改仓库文件的任务，必须先确认当前不在 `main`；若在 `main`，先按 `docs/03-engineering-governance/01-rules/git-workflow.md#开发前分支门禁` 创建任务分支，再更新工作台、spec、plan 或代码。
- 常见任务模式的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。
- 用户未指定执行模式时，按 `docs/03-engineering-governance/task-modes.md#默认模式路由` 自动判断；复杂新需求默认优先走 superpower 生成 spec/plan，小改动默认走 plan-do。
- 代码探索和文本搜索可使用当前 AI IDE 可用工具；最终判断仍以代码事实、验证结果和仓库事实源记录为准。
- 开发中遵循计划，但如果发现计划与代码事实冲突，应先停下来更新计划或向用户确认。
- 开发后必须运行与改动范围匹配的验证，并更新任务进度状态。
- 复核、测试、PR review 或交接中发现的问题必须形成闭环：立即修复，或登记到对应任务总账；系统性问题进入 `docs/03-engineering-governance/04-retrospectives/*` 并转成 `REQ` / `BUG` / `TD` / `DOC` / `OPS`；不得只停留在最终回复、聊天记录或插件内部状态。

## 开发前检查

每次开发任务开始前，执行者必须：

1. 阅读 `docs/03-engineering-governance/current-work.md`，确认本次任务卡片；如果用户点名的任务不在工作台，先按 `docs/03-engineering-governance/task-modes.md#任务入口解析门禁` 定位事实源；如果需要更新工作台或任务状态，同时读取 `docs/03-engineering-governance/01-rules/workbench.md`。
2. 如果本次会修改仓库文件，用 `git status --short --branch` 确认已在语义化任务分支；若仍在 `main`，先切分支，再改任何文件。
3. 按任务卡片链接读取相关文档：
   - 功能需求优先读取对应 `docs/02-delivery-plans/01-specs/*`。
   - 未进入交付的新需求、里程碑或迭代安排读取 `docs/01-product-planning/*`。
   - 实施步骤优先读取对应 `docs/02-delivery-plans/02-plans/*`。
   - 历史任务或兼容输出可读取 `docs/90-compat-legacy/superpowers/specs/*`、`docs/90-compat-legacy/superpowers/plans/*` 或用户指定的插件计划。
   - 技术债读取 `docs/03-engineering-governance/technical-debt.md`。
   - 架构边界读取 `ARCHITECTURE.md` 的相关章节。
   - API、DTO、前后端类型或 shared schema 变更读取 `docs/03-engineering-governance/01-rules/contracts.md`。
4. 和用户确认本次执行范围、完成标准和验证方式。
5. 将任务状态更新为 `进行中`，并记录最近接手工具、当前执行模式和当前分支。
6. 如果任务来自 `docs/03-engineering-governance/current-work.md` 的“下一批候选任务”或外部事实源，开工前必须移动或登记到“当前进行中”，并保留候选来源、事实源链接和本轮验证计划。

很小的即时修复或纯问答可以不新增任务卡片，但执行者仍应在最终回复中说明验证结果。只要任务涉及跨文件修改、计划接力、状态交接或后续继续开发，就必须登记到当前工作台。

## 计划来源优先级

当多个计划或文档同时存在时，按以下顺序处理：

1. 用户在当前对话中明确指定的计划或文档。
2. `docs/03-engineering-governance/current-work.md` 中任务卡片链接的 Plan。
3. 对应 `docs/02-delivery-plans/02-plans/*` 中的实施计划。
4. 对应 `docs/02-delivery-plans/01-specs/*` 中的需求和设计。
5. 对应 `docs/01-product-planning/*` 中的 roadmap、iteration、backlog 或 requirement。
6. 历史或兼容目录中的 `docs/90-compat-legacy/superpowers/plans/*`、`docs/90-compat-legacy/superpowers/specs/*`。
7. `ARCHITECTURE.md` 中的长期架构约束。

如果文档之间冲突，不要静默选择。先指出冲突，并请用户确认以哪份为准。

## 开发中规则

- 只实现本次任务卡片和计划中要求的内容。
- 不做无关重构，不清理与当前任务无关的历史问题。
- 如果发现新的技术债，只记录到 `docs/03-engineering-governance/technical-debt.md`，不要顺手修复，除非它阻塞当前任务。
- 如果计划需要调整，先更新任务卡片的 `交接备注` 或相关 plan，再继续执行。
- 如果发现的是当前任务的后续遗留，优先在原任务备注中说明关系，并按 `docs/03-engineering-governance/task-modes.md#follow-up-分流` 建立新的稳定编号；需要近期接力时，再同步到 `current-work.md` 的“下一批候选任务”。
- 复核或验收发现的问题不得只写成 `TD-xxx-FOLLOWUP` 备注长期悬挂；如果需要后续执行，必须转为稳定编号任务，并补齐证据、完成标准和验证方式。

## 并行开发模式

并行开发只在用户明确触发时启用，例如“按并行模式处理 REQ-A 和 REQ-B”。默认仍是单任务闭环。

并行批次开工前，协调者必须先完成并行可行性评估：

- 列出每个任务的 agent、分支、推荐 worktree / clone、允许修改范围和禁止修改范围。
- 标明共享契约、共享 DTO / schema、共享 migration、共享页面和可能冲突文件。
- 规定合并顺序：先合 contract / 低风险 / 基础 PR，再合依赖 PR。
- 指定集成负责人，负责最终回填 `current-work.md`、Backlog、milestone、work-log 和 review-score-log。

并行开发期间，各 agent 应减少对全局事实源的高频修改：

- 过程状态优先写入各自 plan、PR body 或任务专属文档。
- `current-work.md` 可只记录一个并行批次入口，避免多个 agent 反复改同一区域。
- 如果必须修改全局文档，先确认不会覆盖其他 agent 的状态；合并前必须从最新 `main` 同步一次。

并行批次结束后，由集成负责人统一执行：

- 完整验证和跨 PR 行为回归检查。
- 当前工作台、Backlog、milestone、work-log 的状态收口。
- 任务评审评分、follow-up 分流和规则改进判断。

## 开发后收尾

每次开发任务结束前，执行者必须：

1. 运行与改动范围匹配的验证：
   - 前端改动至少运行 `pnpm --filter @metaedu/web typecheck`，必要时运行 build。
   - 后端改动优先运行相关 pytest；如果依赖数据库或环境不可用，记录失败原因。
   - 文档-only 改动至少检查链接、编号和任务状态。
   - 具体验证矩阵以 `docs/03-engineering-governance/01-rules/quality-gates.md` 为准。
2. 按 `docs/03-engineering-governance/01-rules/workbench.md` 更新 `docs/03-engineering-governance/current-work.md`：
   - 更新状态。
   - 更新已完成、未完成和下一步。
   - 更新验证状态。
   - 记录最近接手工具。
3. 执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`。如果任务触发行为变化声明、覆盖矩阵、前端请求生命周期、API / DTO 契约或数据完整性风险，再读取对应专项规则。
4. 如果完成技术债任务，同步更新 `docs/03-engineering-governance/technical-debt.md` 的状态和备注。
5. 如果任务完成后需要长期追踪，在 `docs/03-engineering-governance/work-log.md` 增加或更新一行历史索引。
6. 如果任务进入 `current-work.md` 的“最近完成”，只保留一行短摘要和事实源链接；不要复制完整任务卡片。
7. 如果用户要求提交代码，必须先阅读 `docs/03-engineering-governance/01-rules/git-workflow.md`，再按 `docs/03-engineering-governance/01-rules/git-workflow.md#完整交付闭环` 推进提交、push、PR、合并 `main` 和合并后确认。
8. 完整 Git 闭环结束后，检查并清除交付占位；如果任务文档已有 PR、完成日期或 merge commit 占位，才回填对应字段。PR 本身是默认交付事实源，merge commit 默认可通过 PR 查询；只有文档占位、任务总账或审计要求明确需要时，才创建最小 backfill 提交或 PR。不得保留“以最终回复为准”“提交后更新”等占位。
9. 在最终回复中说明改动、验证结果、Git 交付阶段和未完成事项。

提交完成不等于合并完成。执行者必须明确当前停留在“已本地提交”“已 push”“已创建 PR”还是“已合并到 `main`”。如果用户没有要求完整 Git 流程，默认不要推送或合并；如果用户要求“走完整流程”，则默认推进到合并 `main`，遇到 PR 检查、Review、权限或冲突阻塞时再停下并说明原因。

## 插件使用规则

- superpower、compound-engineering-plugin 或其他插件生成的 spec/plan 必须登记到 `docs/03-engineering-governance/current-work.md` 的 `插件输出` 字段；任务卡片的 `Spec` / `Plan` 字段优先指向 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*` 中的规范副本。
- 插件生成的计划不是最终事实源；最终任务状态、当前进展、验证结果和下一步必须以 `docs/03-engineering-governance/current-work.md` 为准。
- 新任务如果使用 superpower 生成到 `docs/90-compat-legacy/superpowers/*`，进入开发前必须迁入或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`。任务卡片的 `Spec` / `Plan` 字段指向规范目录，原始插件产物写入 `插件输出` 字段。
- 新任务如果使用 compound-engineering-plugin 生成到插件自己的目录，也必须在任务卡片中登记，并在进入开发前迁入或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`。
- 只有一次性调研草稿或用户明确要求保留在插件目录时，可以暂不迁移；此时任务卡片必须写清“兼容来源”和不迁移原因，且最终事实仍需同步到当前工作台。
- 如果插件维护自己的任务状态，也要在收尾时同步回当前工作台。
- 不同 AI IDE 接手时，以当前工作台为入口，而不是依赖某个插件的内部上下文。
- `.claude/rules`、Codex 私有规则目录或其他工具私有规则目录只能作为跳转入口；共享规则事实源统一维护在 `docs/03-engineering-governance/01-rules/`。

## Superpower 兼容规则

使用 superpower 时，允许它继续读取或生成 `docs/90-compat-legacy/superpowers/*` 下的历史文档，但执行者必须遵守以下规则：

1. 开工前先读 `docs/03-engineering-governance/current-work.md`，不要直接从 superpower 的 plan 开始做。
2. 如果 superpower 生成了新 spec/plan，先迁入或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`，再把规范目录链接写入任务卡片的 `Spec` / `Plan` 字段。
3. 原始 `docs/90-compat-legacy/superpowers/*` 链接写入任务卡片的 `插件输出` 字段，便于追溯插件上下文。
4. 执行完成后，同步任务状态、验证结果和下一步到 `docs/03-engineering-governance/current-work.md`。
5. 如果 superpower plan 中的要求与 `docs/03-engineering-governance/01-rules/*` 冲突，以工程规则为准，并在继续前向用户说明冲突。
6. 如果 superpower 重新生成旧顶层输出目录，这是路径门禁失败信号；必须迁移或镜像到交付层，并删除旧入口后再继续开发或提交。
