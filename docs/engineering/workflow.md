# 跨 AI 开发工作流

本规范用于统一 Codex、Claude Code、superpower、EveryInc/compound-engineering-plugin 以及其他 AI IDE 或插件的协作方式。工具可以不同，但任务入口、规范目录、计划来源、验证和状态更新必须一致。

## 核心原则

- 仓库文档是事实源，插件是执行工具。
- 任务状态统一维护在 `docs/engineering/current-work.md`。
- 任务状态更新必须使用 `状态：颜色 状态名` 格式；颜色图例见 `docs/engineering/current-work.md`。
- `docs/engineering/current-work.md` 是活文档。实现、验证或 Git 阶段变化后，执行者必须同步任务卡片。
- 新任务的长期需求文档统一放在 `docs/specs/*`，实施计划统一放在 `docs/plans/*`。
- `docs/superpowers/*` 只作为历史目录或插件兼容输出目录，不作为新任务默认事实源。
- 开发前必须明确本次任务卡片、相关计划、相关约束和验收标准。
- 常见任务模式的开工条件、必读文档和完成标准见 `docs/engineering/task-modes.md`。
- 开发中遵循计划，但如果发现计划与代码事实冲突，应先停下来更新计划或向用户确认。
- 开发后必须运行与改动范围匹配的验证，并更新任务进度状态。

## 开发前检查

每次开发任务开始前，执行者必须：

1. 阅读 `docs/engineering/current-work.md`，确认本次任务卡片。
2. 按任务卡片链接读取相关文档：
   - 功能需求优先读取对应 `docs/specs/*`。
   - 实施步骤优先读取对应 `docs/plans/*`。
   - 历史任务或兼容输出可读取 `docs/superpowers/specs/*`、`docs/superpowers/plans/*` 或用户指定的插件计划。
   - 技术债读取 `docs/engineering/technical-debt.md`。
   - 架构边界读取 `ARCHITECTURE.md` 的相关章节。
   - API、DTO、前后端类型或 shared schema 变更读取 `docs/engineering/rules/contracts.md`。
3. 和用户确认本次执行范围、完成标准和验证方式。
4. 将任务状态更新为 `进行中`，并记录最近接手工具和当前执行模式。

很小的即时修复或纯问答可以不新增任务卡片，但执行者仍应在最终回复中说明验证结果。只要任务涉及跨文件修改、计划接力、状态交接或后续继续开发，就必须登记到当前工作台。

## 计划来源优先级

当多个计划或文档同时存在时，按以下顺序处理：

1. 用户在当前对话中明确指定的计划或文档。
2. `docs/engineering/current-work.md` 中任务卡片链接的 Plan。
3. 对应 `docs/plans/*` 中的实施计划。
4. 对应 `docs/specs/*` 中的需求和设计。
5. 历史或兼容目录中的 `docs/superpowers/plans/*`、`docs/superpowers/specs/*`。
6. `ARCHITECTURE.md` 中的长期架构约束。

如果文档之间冲突，不要静默选择。先指出冲突，并请用户确认以哪份为准。

## 开发中规则

- 只实现本次任务卡片和计划中要求的内容。
- 不做无关重构，不清理与当前任务无关的历史问题。
- 如果发现新的技术债，只记录到 `docs/engineering/technical-debt.md`，不要顺手修复，除非它阻塞当前任务。
- 如果计划需要调整，先更新任务卡片的 `交接备注` 或相关 plan，再继续执行。

## 开发后收尾

每次开发任务结束前，执行者必须：

1. 运行与改动范围匹配的验证：
   - 前端改动至少运行 `pnpm --filter @metaedu/web typecheck`，必要时运行 build。
   - 后端改动优先运行相关 pytest；如果依赖数据库或环境不可用，记录失败原因。
   - 文档-only 改动至少检查链接、编号和任务状态。
   - 具体验证矩阵以 `docs/engineering/rules/quality-gates.md` 为准。
2. 更新 `docs/engineering/current-work.md`：
   - 更新状态。
   - 更新已完成、未完成和下一步。
   - 更新验证状态。
   - 记录最近接手工具。
3. 做一次最终声明回查：
   - 状态字段是否与实际一致。
   - 验证结果是否来自真实命令输出。
   - 测试是否覆盖完成标准中的所有等价入口。
   - 如果验证命令失败，是否写清失败项并绑定已有或新增的 `TD-xxx`。
4. 如果完成技术债任务，同步更新 `docs/engineering/technical-debt.md` 的状态和备注。
5. 如果用户要求提交代码，必须先阅读 `docs/engineering/rules/git-workflow.md`，再按 `docs/engineering/rules/git-workflow.md#完整交付闭环` 推进提交、push、PR、合并 `main` 和合并后确认。
6. 在最终回复中说明改动、验证结果、Git 交付阶段和未完成事项。

提交完成不等于合并完成。执行者必须明确当前停留在“已本地提交”“已 push”“已创建 PR”还是“已合并到 `main`”。如果用户没有要求完整 Git 流程，默认不要推送或合并；如果用户要求“走完整流程”，则默认推进到合并 `main`，遇到 PR 检查、Review、权限或冲突阻塞时再停下并说明原因。

## 插件使用规则

- superpower、compound-engineering-plugin 或其他插件生成的 spec/plan 可以作为任务卡片的 `Spec` 或 `Plan` 链接，但必须登记到 `docs/engineering/current-work.md`。
- 插件生成的计划不是最终事实源；最终任务状态、当前进展、验证结果和下一步必须以 `docs/engineering/current-work.md` 为准。
- 新任务如果使用 superpower 生成到 `docs/superpowers/*`，进入开发前必须在任务卡片中明确标记为兼容来源；长期维护时优先迁入或镜像到 `docs/specs/*` / `docs/plans/*`。
- 新任务如果使用 compound-engineering-plugin 生成到插件自己的目录，也必须在任务卡片中登记，并优先沉淀为 `docs/specs/*` / `docs/plans/*`。
- 如果插件维护自己的任务状态，也要在收尾时同步回当前工作台。
- 不同 AI IDE 接手时，以当前工作台为入口，而不是依赖某个插件的内部上下文。
- `.claude/rules`、Codex 私有规则目录或其他工具私有规则目录只能作为跳转入口；共享规则事实源统一维护在 `docs/engineering/rules/`。

## Superpower 兼容规则

使用 superpower 时，允许它继续读取或生成 `docs/superpowers/*` 下的历史文档，但执行者必须遵守以下规则：

1. 开工前先读 `docs/engineering/current-work.md`，不要直接从 superpower 的 plan 开始做。
2. 如果 superpower 生成了新 spec/plan，先把链接写入任务卡片的 `Spec` / `Plan` 字段。
3. 如果该任务会长期维护，优先把新文档放到或迁入 `docs/specs/*` / `docs/plans/*`。
4. 执行完成后，同步任务状态、验证结果和下一步到 `docs/engineering/current-work.md`。
5. 如果 superpower plan 中的要求与 `docs/engineering/rules/*` 冲突，以工程规则为准，并在继续前向用户说明冲突。
