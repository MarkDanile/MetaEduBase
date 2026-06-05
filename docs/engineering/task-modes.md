# Task Modes — 任务模式检查表

本文件用于把常见工作接入同一套流程。无论使用 plan-do、superpower、compound-engineering-plugin、Codex、Claude Code 或人工开发，都先从 `docs/engineering/current-work.md` 建立或确认任务卡片。

## 类型与领域

任务卡片使用两层分类，避免为每个组合都创建新流程。

类型：
- `功能`
- `修复`
- `技术债`
- `重构`
- `调研`
- `基础设施`
- `数据迁移`
- `发布`
- `文档`

领域：
- `Frontend`
- `Backend`
- `API`
- `Data Integrity`
- `Security`
- `Testing`
- `Delivery`
- `AI`
- `Docs`

安全问题作为高优先级领域处理，不单独成为任务模式；它可以出现在 Bug 修复、技术债修复、新需求开发、数据迁移或发布任务中。

## 通用入口

每次进入开发前确认：

1. 任务卡片已登记到 `docs/engineering/current-work.md`，或当前任务足够小且不需要交接。
2. 任务卡片包含本次范围、相关文档、完成标准和验证方式。
3. 当前执行模式已标记为 `plan-do`、`superpower`、`compound-engineering` 或 `manual`。
4. 如果使用插件生成 spec/plan，规范副本已迁移或镜像到 `docs/specs/*` / `docs/plans/*`，插件原始输出已登记到任务卡片的 `插件输出` 字段。
5. 开发完成后必须更新任务状态、验证结果和下一步。

## 通用收尾回查

每次进入提交、PR 或声明任务完成前，执行者必须做一次最终回查：

1. `docs/engineering/current-work.md` 的状态、进展、下一步和验证状态是否与实际一致。
2. `当前进行中`、`下一批候选任务`、`最近完成` 三个区域是否同步，已完成任务是否仍残留过期下一步。
3. `下一批候选任务` 是否只包含 1 到 3 个未完成候选，且无 `🟢 完成` 行。
4. `最近完成` 是否不超过 5 行；超出窗口的完成任务是否已进入 `docs/engineering/work-log.md` 或对应事实源。
5. 如果任务需要长期追踪，是否已更新 `docs/engineering/work-log.md` 一行式索引。
6. 验证结论是否来自真实命令输出；退出码非 0 的命令不得写“通过”。
7. 如果本次改动影响多个等价入口、对象类型、状态流或端点，是否已用覆盖矩阵确认测试或验收范围。
8. 如果声明“零业务逻辑变更”“仅格式化”或“仅 lint 修复”，是否已按质量门禁规则排查行为变化信号。
9. PR 范围是否只包含本任务相关文件；无关资产删除、生成物清理或其他人工改动是否已拆分，或经用户确认并在 PR 中单独说明。
10. 已完成任务对应的 plan/spec 是否已收口为历史事实，且不再残留活动式 `- [ ]` 收尾项。
11. 完整 Git 闭环后，仓库文档中是否已清除 PR、完成日期和 merge commit 占位；已有占位或任务总账明确要求时才回填，默认以 PR 作为交付事实源。
12. 如果仍有历史失败，是否绑定到已有或新增的 `TD-xxx`。
13. PR 描述、最终回复和任务卡片里的声明是否一致。

这一步必须发生在验证完成后、`git add` 前。不要在验证前提前把任务写成完成状态。

## 标准启动语

用户不需要记住完整流程。后续可以使用短句启动任务，执行者必须自动映射到本文件对应模式，并按 `docs/engineering/current-work.md` 登记或更新任务卡片。

## 默认模式路由

用户不必指定 `plan-do`、`superpower` 或其他插件模式。除非用户明确指定模式，执行者必须根据任务特征自动选择：

| 任务特征 | 默认模式 | 文档要求 |
|----------|----------|----------|
| 单文件或小范围文案 / 样式 / 配置调整，风险低且验收清楚 | plan-do | 可不新建 spec/plan；需要交接时登记 `current-work.md` |
| 明确 bug、可复现错误、回归或线上异常 | bug fix / TDD | 登记 `BUG-xxx` 或当前任务卡片；优先补复现测试或手动验收步骤 |
| 已有 `TD-xxx` 或明确是技术债治理 | technical-debt | 读取并更新 `technical-debt.md`；必要时同步 `current-work.md` |
| 跨 3 个以上文件、复杂 UI 流程、新 API、新数据模型、权限 / 多租户 / 数据一致性变化 | superpower 优先 | 必须产出或更新 `docs/specs/*` 和 `docs/plans/*`，再进入开发 |
| 架构方向、方案选择、未知成本或需要比较多种路线 | spike / 调研 | 先产出调研结论、推荐方案和后续 plan，不直接改业务代码 |
| 明确只改变结构、不改变行为 | refactor | 明确行为边界和验证方式；不得混入新功能 |
| 数据迁移、发布、CI/CD、依赖升级 | infrastructure / release | 明确目标环境、回滚方式和验证矩阵 |

用户显式指定模式时，以用户指定为准，例如“用 superpower 规划”“不要写代码，只出 plan”“不用 superpower，直接小改”“只提交不合并”。如果自动判断不确定，执行者只问 1 个澄清问题；否则直接按默认模式推进。

大需求默认走 `superpower` 时，插件输出仍不是长期事实源：spec 必须迁移或镜像到 `docs/specs/*`，plan 必须迁移或镜像到 `docs/plans/*`，原始插件输出登记到任务卡片的 `插件输出` 字段。

| 用户说法 | 执行者应理解为 | 必须动作 |
|----------|----------------|----------|
| `按流程处理 TD-xxx` | 技术债修复 | 读取 `current-work.md`、`technical-debt.md` 和相关 rules；确认 `TD-xxx` 完成标准和验证方式 |
| `按流程修复这个 BUG: ...` | Bug 修复 | 登记或更新 `BUG-xxx`；明确复现步骤、期望行为和验证方式 |
| `按流程开发这个新需求: ...` | 新需求开发 | 判断是否需要 spec/plan；需要时使用 `docs/specs/*` 和 `docs/plans/*` |
| `按流程重构 XXX` | 重构 | 明确行为边界和验证方式；不得混入新功能 |
| `按流程调研 XXX` | Spike / 调研 | 明确要回答的问题、时间盒和预期产出 |
| `按流程处理工具链/依赖/CI 问题: ...` | 基础设施 / 依赖 / 工具链 | 明确影响范围、兼容性风险和回滚方式 |
| `按流程处理数据迁移/发布: ...` | 数据迁移 / 发布 | 明确目标环境、数据影响、upgrade 路径和回滚方式 |

如果用户只说“按流程处理这个问题”，执行者必须先判断任务类型和领域；判断不确定时，先用一句话说明不确定点并请用户确认。

用户也可以直接说需求本身，例如“给课程增加批量导入能力”。执行者必须先自动判断任务类型、领域和默认模式；如果判断为复杂新需求，应先进入 spec/plan，不要直接改代码。

如果用户明确指定插件，例如 superpower 或 compound-engineering-plugin，执行者仍必须以 `docs/engineering/current-work.md` 为入口，确认规范副本在 `docs/specs/*` / `docs/plans/*`，并把插件输出登记到任务卡片。

## 技术债修复

适用场景：处理 `docs/engineering/technical-debt.md` 中的 `TD-xxx`。

开工条件：
- 技术债状态为 `就绪`，或用户明确指定本次要处理该项。
- 任务包含证据、完成标准和验证方式。
- 当前工作台任务卡片引用对应 `TD-xxx`。

必读文档：
- `docs/engineering/current-work.md`
- `docs/engineering/technical-debt.md`
- 与领域相关的 `docs/engineering/rules/*`
- 如涉及架构边界，读取 `ARCHITECTURE.md` 相关章节。

执行原则：
- 只修复该技术债定义的范围。
- 发现新技术债时记录到总账，不顺手扩大范围，除非它阻塞当前任务。
- 完成后将技术债状态更新为 `完成`，并记录完成日期、验证结果和相关提交。

完成标准：
- `TD-xxx` 的完成标准全部满足。
- 验证方式已执行或记录无法执行的具体原因。
- 如果技术债影响多个等价入口，已用覆盖矩阵确认没有遗漏路径。
- `current-work.md` 和 `technical-debt.md` 状态同步。

## Bug 修复

适用场景：修复可复现的错误、异常、回归或线上/本地问题。

开工条件：
- 有明确复现步骤、失败现象或错误日志。
- 可以定义期望行为。
- 当前工作台使用 `BUG-xxx` 编号登记。

必读文档：
- `docs/engineering/current-work.md`
- 相关 spec/plan，如果该 bug 来源于某个功能。
- 相关领域规则，例如安全、数据完整性、契约或测试规范。

执行原则：
- 优先写或补充能复现 bug 的测试；如果不适合自动化测试，记录手动验收步骤。
- 修复范围只覆盖该 bug 和必要的邻接代码。
- 如果 bug 暴露系统性问题，再新增技术债，不把大重构混入 bug fix。

完成标准：
- 复现步骤不再失败。
- 相关自动化测试或手动验收通过。
- 如果 bug 修复影响同类端点或状态流，已用覆盖矩阵确认等价路径。
- 当前工作台记录修复摘要、验证命令和剩余风险。

## 新需求开发

适用场景：新增功能、较大 UI/流程改造、新 API、新数据模型或跨模块能力。

开工条件：
- 小需求可以 plan-do，但必须明确范围、完成标准和验证方式。
- 跨 3 个以上文件、Schema/API 变更、新端点或复杂 UI 流程，必须有 spec/plan。
- 长期 spec 默认放 `docs/specs/*`，长期 plan 默认放 `docs/plans/*`。

必读文档：
- `docs/engineering/current-work.md`
- 对应 `docs/specs/*`
- 对应 `docs/plans/*`
- `ARCHITECTURE.md` 相关章节
- 涉及 API/DTO/shared schema 时读取 `docs/engineering/rules/contracts.md`

执行原则：
- 先完成核心路径，再扩展边界场景。
- 新功能不得绕过现有设计系统、认证、多租户、数据完整性和质量门禁规则。
- 如果插件生成计划，执行后仍以当前工作台状态为准。

完成标准：
- spec 中的验收标准全部满足，或明确记录未完成项。
- plan 中的任务状态已更新。
- 相关验证按 `docs/engineering/rules/quality-gates.md` 执行。
- 必要文档已同步，尤其是 API、Schema、运行命令和质量门禁变化。

## 重构

适用场景：改善代码结构、拆分模块、抽取稳定单元、降低复杂度，但不改变用户可见行为。

开工条件：
- 明确说明重构目标和不改变的行为边界。
- 有可对比的验证方式，优先使用现有测试。
- 如果重构来源于技术债，任务卡片引用对应 `TD-xxx`。

必读文档：
- `docs/engineering/current-work.md`
- 相关领域规则，例如编码风格、契约、数据完整性或测试规范。
- 如果涉及模块边界，读取 `ARCHITECTURE.md` 相关章节。

执行原则：
- 不把新功能混入重构。
- 不顺手清理与目标无关的历史问题。
- 优先先抽稳定小单元，再处理更大结构调整。

完成标准：
- 用户可见行为不变。
- 相关测试或手动验收前后通过。
- 当前工作台记录重构范围、验证结果和未覆盖风险。

### 前端请求生命周期重构

当重构涉及 composable、Vue Query、请求 service、轮询、loading / error 状态或 mutation 后刷新时，不能只依赖 lint、typecheck 和 build 判断行为不变。开工前必须列出行为等价矩阵，并在收尾时逐项回查。

矩阵至少覆盖：
- 请求参数、query/body/formData 字段和默认值。
- query `enabled` 条件、tab lazy-load、页面进入时是否预取。
- 轮询开始、暂停、停止和组件卸载清理条件。
- mutation 成功后的 cache invalidation、选中项刷新和列表刷新。
- loading、disabled、toast、错误文案和重试入口。
- DTO 形态和 adapter；不得用 `unknown as SomeDTO` 掩盖后端响应与前端展示类型不一致。

如果某一项刻意改变，必须在任务卡片、plan 或 PR 中写成可观察行为变化，并补充对应验证。

## Spike / 调研

适用场景：方案不确定、技术选型、风险验证、性能假设验证或插件/工具评估。

开工条件：
- 明确要回答的问题。
- 明确时间盒或停止条件。
- 明确预期产出是结论、方案、原型还是后续任务。

必读文档：
- `docs/engineering/current-work.md`
- 已有 spec/plan 或架构约束。
- 如涉及第三方工具或插件，读取对应官方文档或仓库说明。

执行原则：
- 调研可以产生原型，但原型代码默认不进入主路径，除非用户确认。
- 结论必须说明取舍、风险和推荐下一步。
- 如果发现可执行任务，转化为 `FEAT-xxx`、`BUG-xxx` 或 `TD-xxx`。

完成标准：
- 回答了开工时的问题。
- 输出推荐方案和不推荐方案的理由。
- 后续任务已登记或明确不需要继续。

## 基础设施 / 依赖 / 工具链

适用场景：依赖升级、构建配置、lint/typecheck、CI、dev server、脚本、包管理、工作区卫生。

开工条件：
- 明确影响范围：本地开发、CI、生产构建、测试或发布。
- 明确回滚方式或兼容性风险。
- 如果来源于技术债，任务卡片引用对应 `TD-xxx`。

必读文档：
- `docs/engineering/current-work.md`
- `docs/engineering/rules/local-development.md`
- `docs/engineering/rules/quality-gates.md`
- `docs/engineering/rules/git-workflow.md`，如果影响提交或 PR 流程。

执行原则：
- 优先让现有命令更可复现，不引入不必要的新工具。
- 依赖升级要关注锁文件、peer dependency、构建兼容性和回滚成本。
- 命令变化必须同步文档。

完成标准：
- 受影响的本地命令或质量门禁可运行，或记录明确阻塞原因。
- 相关文档已更新。
- 当前工作台记录验证命令和影响范围。

## 数据迁移 / 发布

适用场景：数据库 schema 变更、数据修正、上线前准备、hotfix、回滚或发布后验证。

开工条件：
- 明确目标环境：本地、测试、生产或回滚路径。
- 明确数据影响范围和风险。
- 涉及 schema 变更时有 migration plan。

必读文档：
- `docs/engineering/current-work.md`
- `docs/engineering/rules/data-integrity.md`
- `docs/engineering/rules/contracts.md`，如果影响 API/DTO/shared schema。
- `docs/engineering/rules/quality-gates.md`
- `ARCHITECTURE.md` 相关 schema 或部署章节。

执行原则：
- 数据迁移必须考虑 upgrade 路径；高风险变更还要说明 downgrade 或补救路径。
- 发布或 hotfix 必须记录验证、风险和回滚方式。
- 涉及安全或数据一致性的任务，优先级高于体验和风格治理。

完成标准：
- migration、发布步骤或回滚步骤可复现。
- 数据一致性检查或相关验收通过。
- 当前工作台记录执行结果、验证结果和剩余风险。

## 试跑复盘

每次按某种模式走完整流程后，建议在 `current-work.md` 的任务卡片 `交接备注` 中记录：

- 哪一步顺畅。
- 哪一步仍不清晰。
- 哪个文档被频繁查阅。
- 是否需要把规则拆小、合并或补充示例。
