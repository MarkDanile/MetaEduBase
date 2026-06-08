# Task Modes — 任务模式入口

本文件用于把常见开发工作接入同一套流程。它关注的是“这类任务该怎么开工、该读什么、怎样算完成”，不是重复展开完整工作流。跨 AI IDE / 插件交接流程仍以 `docs/03-engineering-governance/workflow.md` 为主。

## 类型与领域

任务卡片继续使用“两层分类”：

### 类型

- `功能`
- `修复`
- `技术债`
- `重构`
- `调研`
- `基础设施`
- `数据迁移`
- `发布`
- `文档`

### 领域

- `Frontend`
- `Backend`
- `API`
- `Data Integrity`
- `Security`
- `Testing`
- `Delivery`
- `AI`
- `Docs`

安全问题作为高优先级领域处理，不单独成为任务模式。

## 通用入口

每次进入开发前，至少确认这 6 件事：

1. 任务卡片已登记到 `docs/03-engineering-governance/current-work.md`，或当前任务足够小且不需要交接。
2. 任务卡片包含本次范围、相关文档、完成标准和验证方式。
3. 只要会修改仓库文件，已按 `git-workflow.md#开发前分支门禁` 确认当前不在 `main`；这个检查早于更新工作台、spec、plan 或代码。
4. 当前执行模式已标记为 `plan-do`、`superpower`、`compound-engineering` 或 `manual`。
5. 如果插件生成了 spec / plan，规范副本已迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`。
6. 开发结束后会回写状态、验证结果和下一步。

## 通用收尾回查

每次进入提交、PR 或声明完成前，必须执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`。如果任务触发专项风险，再补读对应专项门禁：

- 覆盖多个等价入口、对象类型、状态流或端点：使用覆盖矩阵
- 声明“零业务逻辑变更”“仅 lint 修复”等：执行行为变化声明检查
- 涉及 composable、Vue Query、轮询或 mutation 刷新：执行前端请求生命周期等价矩阵
- 涉及 API / DTO / shared schema：读取 `docs/03-engineering-governance/01-rules/contracts.md`

这一步必须发生在验证完成后、`git add` 前。

## Follow-up 分流

复核、验收、测试失败或交接发现的问题，必须按问题性质建立稳定编号，不使用 `REQ-xxx-FOLLOWUP`、`TD-xxx-FOLLOWUP` 作为长期任务编号。

| 问题性质 | 任务类型 | 处理方式 |
|----------|----------|----------|
| 原需求验收缺口、验收口径过强、真实业务场景未闭环 | `REQ-xxx` | 新建或继续需求任务，并写 `Parent:` 指向来源需求 |
| 用户可见错误、回归、异常或线上 / 本地 bug | `BUG-xxx` | 记录复现路径、期望行为和验证方式 |
| 代码结构、测试基础设施、质量门禁、可维护性问题 | `TD-xxx` | 进入技术债总账，补证据、完成标准和验证方式 |
| 规则、文档、流程、事实源状态漂移或脚本门禁问题 | `DOC-xxx` | 进入工程治理记录，并优先补规则或自动检查 |

进入 `Ready` 或 `Done` 前，follow-up 必须有证据、完成标准和验证方式；否则只能保持待澄清或候选状态。

## 默认模式路由

用户不必显式说 `plan-do`、`superpower` 或其他模式。除非用户明确指定，否则按任务特征自动选择：

| 任务特征 | 默认模式 | 文档要求 |
|----------|----------|----------|
| 单文件或小范围文案 / 样式 / 配置调整，风险低且验收清楚 | `plan-do` | 可不新建 spec/plan；需要交接时登记工作台 |
| 明确 bug、可复现错误、回归或线上异常 | `bug fix / TDD` | 登记 `BUG-xxx` 或当前任务卡片；优先补复现测试或手动验收步骤 |
| 已有 `TD-xxx` 或明确是技术债治理 | `technical-debt` | 读取并更新 `technical-debt.md`；必要时同步工作台 |
| 新想法、里程碑拆解、需求池整理或尚未塑形的新需求 | `product planning` | 先进入 `docs/01-product-planning/04-backlog.md` 或 `docs/01-product-planning/05-requirements/*`，暂不直接开发 |
| 跨 3 个以上文件、复杂 UI、新 API、新数据模型、权限 / 多租户 / 数据一致性变化 | `superpower` 优先 | 先产出或更新 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`，再进入开发 |
| 架构方向、方案选择、未知成本或需要比较路线 | `spike / 调研` | 先产出调研结论和推荐方案，不直接改业务代码 |
| 明确只改变结构、不改变行为 | `refactor` | 明确行为边界和验证方式 |
| 数据迁移、发布、CI/CD、依赖升级 | `infrastructure / release` | 明确目标环境、回滚方式和验证矩阵 |

如果自动判断不确定，只问 1 个澄清问题；否则直接按默认模式推进。

### 常见启动语

| 用户说法 | 执行者应理解为 | 必须动作 |
|----------|----------------|----------|
| `按流程处理 TD-xxx` | 技术债修复 | 读取 `current-work.md`、`technical-debt.md` 和相关规则；确认完成标准与验证方式 |
| `按流程修复这个 BUG: ...` | Bug 修复 | 登记或更新 `BUG-xxx`；明确复现步骤、期望行为和验证方式 |
| `按流程规划这个需求: ...` | 产品规划 / 需求塑形 | 登记或更新 `docs/01-product-planning/04-backlog.md`；必要时新建 `docs/01-product-planning/05-requirements/REQ-xxx.md` |
| `按流程开发这个新需求: ...` | 新需求开发 | 判断是否需要 spec/plan；需要时进入 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*` |
| `按流程重构 XXX` | 重构 | 明确行为边界和验证方式；不得混入新功能 |
| `按流程调研 XXX` | Spike / 调研 | 明确问题、时间盒和预期产出 |
| `按流程处理工具链/依赖/CI 问题: ...` | 基础设施 / 依赖 / 工具链 | 明确影响范围、兼容性风险和回滚方式 |
| `按流程处理数据迁移/发布: ...` | 数据迁移 / 发布 | 明确目标环境、数据影响、upgrade 路径和回滚方式 |

## 技术债修复

适用：处理 `docs/03-engineering-governance/technical-debt.md` 中的 `TD-xxx`。

必读：

- `docs/03-engineering-governance/current-work.md`
- `docs/03-engineering-governance/technical-debt.md`
- 相关领域规则
- 必要时读 `ARCHITECTURE.md`

执行原则：

- 只修复该技术债定义的范围
- 发现新技术债时入账，不顺手扩范围
- 多个等价入口受影响时，补覆盖矩阵
- 低风险、单点技术债可直接以 TD 卡片为计划；跨 3 个以上文件、涉及 API / Schema / 数据一致性 / 安全 / 前端行为等高风险技术债，先补 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`，再进入实现

完成标准：

- `TD-xxx` 的完成标准满足
- 验证已执行或明确记录阻塞原因
- `current-work.md` 与 `technical-debt.md` 状态同步

## Bug 修复

适用：修复可复现错误、回归、异常或线上 / 本地问题。

必读：

- `docs/03-engineering-governance/current-work.md`
- 来源功能对应的 spec / plan（如有）
- 相关领域规则

执行原则：

- 优先补可复现测试；不适合自动化时记录手动验收步骤
- 修复范围只覆盖该 bug 和必要邻接代码
- 如果暴露系统性问题，新增技术债，不把大重构混入 bug fix

完成标准：

- 复现路径不再失败
- 自动化测试或手动验收通过
- 如影响同类端点或状态流，已确认等价路径

## 新需求开发

适用：新增功能、较大 UI / 流程改造、新 API、新数据模型或跨模块能力。

必读：

- `docs/03-engineering-governance/current-work.md`
- 如果需求来自路线图、迭代或需求池，读取对应 `docs/01-product-planning/*`
- 对应 `docs/02-delivery-plans/01-specs/*`
- 对应 `docs/02-delivery-plans/02-plans/*`
- 必要时读 `ARCHITECTURE.md`
- 涉及 API / DTO / shared schema 时读 `docs/03-engineering-governance/01-rules/contracts.md`

执行原则：

- 先完成核心路径，再扩展边界场景
- 新功能不得绕过认证、多租户、数据完整性和质量门禁规则
- 复杂需求先有 spec / plan，再进入实现
- 需求仍处于 `Idea` / `Candidate` / `Shaping` 时，不直接开发；先完成需求塑形并进入 `Ready`

完成标准：

- spec 验收标准满足，或明确记录未完成项
- plan 状态更新
- 相关验证按 `quality-gates.md` 执行
- 必要文档已同步

## 产品规划 / 需求塑形

适用：里程碑规划、迭代拆解、需求池整理、需求价值和边界尚未明确的工作。

必读：

- `docs/01-product-planning/README.md`
- `docs/01-product-planning/01-roadmap.md`
- `docs/01-product-planning/04-backlog.md`
- 必要时读 `ARCHITECTURE.md`

执行原则：

- 先记录清单和判断，不把所有细节塞进单个文档
- 只有值得塑形的需求才新建 `docs/01-product-planning/05-requirements/REQ-xxx.md`
- 已准备交付的复杂需求再迁入或镜像到 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`
- 外部项目管理系统编号写入 `External`，不替代仓库编号

完成标准：

- 需求或任务有稳定编号、状态、优先级和下一步
- 需要详细说明的条目已有 requirement、spec 或 plan 链接
- 不需要继续的条目标记为 `Dropped` 并说明原因

## 重构

适用：改善代码结构、拆分模块、抽取稳定单元、降低复杂度，但不改变用户可见行为。

必读：

- `docs/03-engineering-governance/current-work.md`
- 相关领域规则
- 如涉及模块边界，读 `ARCHITECTURE.md`

执行原则：

- 明确重构目标和不变的行为边界
- 不把新功能混入重构
- 不顺手清理与目标无关的历史问题
- 优先先抽稳定小单元，再做更大结构调整

完成标准：

- 用户可见行为不变
- 相关测试或手动验收前后通过
- 当前工作台记录重构范围、验证结果和未覆盖风险

### 前端请求生命周期重构

如果重构涉及 composable、Vue Query、请求 service、轮询、loading / error 状态或 mutation 后刷新，不能只依赖 lint、typecheck 和 build 判断行为不变。应按 `quality-gates.md` 中的前端请求生命周期等价矩阵逐项回查。

## Spike / 调研

适用：方案不确定、技术选型、风险验证、性能假设验证或插件 / 工具评估。

必读：

- `docs/03-engineering-governance/current-work.md`
- 已有 spec / plan 或架构约束
- 必要的第三方官方文档

执行原则：

- 明确要回答的问题、时间盒和停止条件
- 可做原型，但默认不直接进入主路径
- 结论必须说明取舍、风险和推荐下一步

完成标准：

- 回答了开工时的问题
- 输出推荐方案与不推荐方案理由
- 后续任务已登记或明确不继续

## 基础设施 / 依赖 / 工具链

适用：依赖升级、构建配置、lint / typecheck、CI、dev server、脚本、包管理、工作区卫生。

必读：

- `docs/03-engineering-governance/current-work.md`
- `docs/03-engineering-governance/01-rules/local-development.md`
- `docs/03-engineering-governance/01-rules/quality-gates.md`
- 必要时读 `docs/03-engineering-governance/01-rules/git-workflow.md`

执行原则：

- 优先让现有命令更可复现，不引入不必要的新工具
- 关注锁文件、兼容性和回滚成本
- 命令变化必须同步文档

完成标准：

- 受影响命令或门禁可运行，或明确记录阻塞原因
- 相关文档已更新
- 当前工作台记录验证命令和影响范围

## 数据迁移 / 发布

适用：数据库 schema 变更、数据修正、上线前准备、hotfix、回滚或发布后验证。

必读：

- `docs/03-engineering-governance/current-work.md`
- `docs/03-engineering-governance/01-rules/data-integrity.md`
- 必要时读 `docs/03-engineering-governance/01-rules/contracts.md`
- `docs/03-engineering-governance/01-rules/quality-gates.md`
- 必要时读 `ARCHITECTURE.md`

执行原则：

- 明确目标环境、数据影响和风险
- 明确 upgrade 路径；高风险变更补充 downgrade 或补救方案
- 涉及安全或数据一致性的任务，优先级高于体验和风格治理

完成标准：

- migration、发布步骤或回滚步骤可复现
- 数据一致性检查或相关验收通过
- 当前工作台记录执行结果、验证结果和剩余风险

## 试跑复盘

每次按某种模式走完整流程后，建议在任务卡片 `交接备注` 里记 3 件事：

- 哪一步顺畅
- 哪一步仍不清晰
- 是否需要补规则、拆规则或补示例
