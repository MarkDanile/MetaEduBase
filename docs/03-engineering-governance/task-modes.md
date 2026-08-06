# Task Modes — 任务模式入口

本文件负责把用户启动语路由到正确流程。详细 Git、验证、工作台规则分别见 `01-rules/git-workflow.md`、`01-rules/quality-gates.md`、`01-rules/workbench.md`。

## 开工硬门禁

用户说 `按流程处理 XXX`、`开发 XXX`、`修复 XXX` 时，第一步不是实现，而是完成开工三连：

1. 读 `docs/03-engineering-governance/current-work.md`。
2. 若会修改文件，运行 `git status --short --branch`；在 `main` 时先建任务分支。
3. 按下方“任务入口解析门禁”定位事实源；需要改工作台或任务状态时，先读 `01-rules/workbench.md`。

完成三连前，不得直接读取目标任务详情并开始改代码。目标是避免跨 IDE / Windows 环境把“按流程”误解为“直接开干”。

## 任务入口解析门禁

| `XXX` 所在位置 | 执行动作 |
|----------------|----------|
| `current-work.md` | 按任务卡片执行；候选任务开工前先移入“当前进行中”。 |
| `technical-debt.md` | 以 `TD-xxx` 为事实源；进入实现前登记到工作台。 |
| `04-backlog.md` / `05-requirements/*` | `Idea` / `Candidate` / `Shaping` 只塑形；`Ready` 或已有 spec/plan 后再实现。 |
| Roadmap / Milestone / Iteration | 只是规划信号；先映射为 `REQ` / `TD` / `DOC` / `BUG`，再进工作台。 |
| 找不到稳定编号 | 先登记事实源，补证据、完成标准、验证方式；不得直接改业务代码。 |
| 多电脑 / 离线临时想法 | 可先用 `DRAFT-YYYYMMDD-HHMM-XXXX` 记录来源；进工作台或主表前必须归并为正式编号。 |

## 默认模式路由

| 任务特征 | 默认模式 | 交付要求 |
|----------|----------|----------|
| 小范围文案 / 样式 / 配置 | plan-do | 可不新建 spec/plan；需要交接时登记工作台。 |
| 明确 bug、回归、异常 | bug fix | 记录复现、期望、验证；优先补测试或手动验收。 |
| `TD-xxx` 或维护性治理 | technical-debt | 读技术债总账；高风险先补 spec/plan。 |
| 新想法、里程碑、需求池 | product planning | 进入 Backlog / Requirement，不直接开发。 |
| AI Chat / RAG / LLM NER / 图谱召回等效果型任务 | ai-effect validation | 必须声明最高已验证层级，不用低层证据冒充真实效果达成。 |
| 跨 3 个以上文件、新 API、新数据模型、复杂 UI | superpower / plan-do | 先产出 spec/plan，再实现。 |
| 架构方向、技术选型、未知成本 | spike | 输出取舍和下一步，不默认改主路径。 |
| 结构优化但行为不变 | refactor | 明确行为边界和验证方式。 |
| CI/CD、依赖、脚本、发布、迁移 | infrastructure / release | 明确环境、回滚、验证矩阵。 |

## 常见启动语

| 用户说法 | 必须动作 |
|----------|----------|
| `按流程处理 TD-xxx` | 开工三连；读技术债总账；确认完成标准和验证方式。 |
| `按流程修复这个 BUG` | 登记 / 更新 `BUG-xxx`；写复现路径、期望行为、验证方式。 |
| `按流程规划这个需求` | 更新 Backlog；必要时新建 Requirement；不直接实现。 |
| `按流程开发这个新需求` | 判断是否需要 spec/plan；复杂需求先塑形；完成实现、验证、commit、push 和 PR 创建后停止，报告 CI 状态并提示后续评审，不自动合并。 |
| `按流程提交` | 读 `git-workflow.md`；推进 commit / push / PR 后停止，不自动合并。 |
| `按流程评审 XXX` | 先确认当前 HEAD；高风险首轮按数据/状态、并发/故障、测试/运维/文档三个面并行审查并按根因族汇总；处理或登记 finding，完成正式评分并更新评分总账，重新验证后停止，保持 PR 未合并。 |
| `按流程合并` / `提交至合并` / `完整 Git 闭环` | 读 `git-workflow.md`；确认评审评分、当前 PR Head、阻塞 finding 和 required checks 后执行合并、文档收口与 clean check。 |
| `按流程复盘 XXX` | 区分实现问题、规则缺口、工具习惯、需求塑形不足；必要时登记 follow-up。 |
| `按流程复核 P1` / `收口当前迭代` | 对齐 Roadmap、Milestone、Iteration、Backlog、current-work、TD。 |
| `按流程规划 APP-xxx` | 更新 AI Applications 与 Backlog；进入 Requirement Shaping，不直接实现。 |
| `按流程登记这个想法/问题` | 分类入 `REQ` / `BUG` / `TD` / `DOC` / `OPS`；只登记不默认开发。 |
| `按并行模式处理 A 和 B` | 先做并行可行性评估；低耦合才并行。 |

## Follow-up 分流

| 问题性质 | 任务类型 | 事实源 |
|----------|----------|--------|
| 原需求验收缺口、真实业务场景未闭环 | `REQ-xxx` | Backlog / Requirement |
| 用户可见错误、回归、异常 | `BUG-xxx` | Requirement 或 Backlog |
| 代码结构、测试基础设施、可维护性 | `TD-xxx` | `technical-debt.md` |
| 规则、文档、流程、状态漂移、脚本门禁 | `DOC-xxx` | work-log、规则或脚本 |

不使用 `REQ-xxx-FOLLOWUP`、`TD-xxx-FOLLOWUP` 作为长期编号。进入 `Ready` / `Done` 前必须有证据、完成标准和验证方式。

## 效果型任务完成分层

AI Chat / RAG / LLM NER / 图谱召回等效果型任务，按最高已验证层级声明：代码接入 -> mock / fixture -> dry-run / 真实 PG -> 真实 LLM / 用户验收。低层证据不得冒充高层；阻塞时登记 follow-up。

## 模式完成标准

| 模式 | 完成标准 |
|------|----------|
| technical-debt | `TD-xxx` 完成标准满足；验证已执行或记录阻塞；工作台和总账同步。 |
| bug fix | 复现路径不再失败；自动化或手动验收通过；同类入口已检查。 |
| 新需求开发 | spec AC 满足或记录未完成项；plan 状态更新；必要文档同步。 |
| product planning | 有稳定编号、状态、优先级、下一步；长内容进入 requirement/spec/plan。 |
| refactor | 用户可见行为不变；相关验证通过；行为风险说明清楚。 |
| spike | 回答开工问题；给出推荐 / 不推荐方案和下一步。 |
| infrastructure / release | 受影响命令、迁移、发布或回滚路径可复现；风险记录清楚。 |

## 并行开发模式

默认不并行。用户明确触发时，开工前列出任务 ID、agent、分支、推荐 worktree / clone、允许修改范围、禁止修改范围、共享契约、预计冲突点、合并顺序和集成负责人。

以下情况默认不并行：同一大页面、同一 DTO / schema、同一 migration、同一核心抽象、同一全局事实源需要高频修改。并行期间少改 `current-work.md`；由集成者统一回填状态、评分和 follow-up。

## 禁止绕过门禁

当前任务因门禁失败时，禁止修改门禁脚本、`KNOWN_ISSUES`、忽略列表、检查阈值或 CI 配置来让本任务通过。若认为门禁本身错误，停止当前任务，单独登记 `DOC` / `TD`，独立 PR 处理。

## 通用收尾回查

提交、PR、合并或声明完成前，执行 `quality-gates.md#完成门禁`。触发专项风险时补读对应规则：API / DTO 读 `contracts.md`；数据一致性读 `data-integrity.md`；测试策略读 `testing.md`；Git 阶段读 `git-workflow.md`。

验证声明必须写命令、退出结果、范围、环境；不能把主观判断包装成“通过”。

`按流程开发`、`按流程评审`、`按流程合并` 是三个独立阶段，不因前一阶段完成而自动进入后一阶段。PR 创建或评分完成都不构成合并授权。
