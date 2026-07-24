# Agent Platform AI Delivery Routing Matrix

本矩阵约束 P3 企业 Agent 平台后续任务由哪类编码 Harness / 基础模型承担。它只描述“谁来实现代码”，不参与 MetaEduBase 生产环境的模型路由、`RuntimeProfile` 或 `ModelGrant`。

## Model Profiles

| Profile | 推荐组合 | 默认用途 | 边界 |
|---------|----------|----------|------|
| `S-XH` | Codex + GPT-5.6 Sol，`xhigh` | 架构、分布式状态、安全、审批和关键契约 | `max` 只用于最终对抗性审查，不作为日常默认 |
| `S-H` | Codex + GPT-5.6 Sol，`high` | 复杂实现、跨模块调试和关键 Review | 精确 model id 和 effort 在任务开工时再次核实 |
| `S-M` | Codex + GPT-5.6 Sol，`medium` | 普通全栈切片和中等风险 Review | 不用于单独裁决安全、迁移或分布式状态 |
| `G-M` | Claude Code + GLM-5.2，`max` | 长程复杂实现和独立反例审查 | 公开榜单只决定初始分配，不替代仓库测试 |
| `G-H` | Claude Code + GLM-5.2，`high` | 边界清楚的后端、前端和测试切片 | 不用于单独裁决极高复杂度契约 |
| `K-T` | Claude Code + Kimi K3，thinking enabled | 前端、交互、应用层编排和研究工作流 | 必须记录实际返回 model id；不虚构 `high` / `max` 档位 |

GLM-5.2 能力基线来自官方 [`zai-org/GLM-5@436efa0`](https://github.com/zai-org/GLM-5/tree/436efa09bc868a6922e307624189e7018406beb9)。Kimi 的工具、ACP 和 thinking 能力基线来自官方 [`MoonshotAI/kimi-cli@4a550ef`](https://github.com/MoonshotAI/kimi-cli/tree/4a550effdfcb29a25a5d325bf935296cc50cd417)；K3 通过 Provider 动态模型列表接入时必须再次确认实际 model id。GPT-5.6 Sol 使用前按 [OpenAI model guidance](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6) 核实当前 id、effort 和工具协议。

## Complexity

| 等级 | 判定 |
|------|------|
| 低 | 机械文档、局部测试或单文件无行为调整 |
| 中 | 单 bounded context、无关键迁移、无高风险写入，失败可直接回滚 |
| 高 | 跨上下文、API/迁移、流式 UI、外部集成或明显回归面 |
| 极高 | 分布式状态、租户权限、审批、并发、不可逆写入、故障恢复或敏感数据治理 |

涉及 L3 写操作、`outcome_unknown`、跨租户授权或运行恢复时，复杂度自动为“极高”，不得因代码量少而降级。

## Delivery Assignments

| 顺序 | 任务 | 复杂度 | 推荐执行 | 可独立下放范围 |
|------|------|--------|----------|----------------|
| 0 | REQ-059 架构事实源 | 高 | `S-XH` 主修，`G-M` 反例审查 | 不允许整项独立定案；人工冻结所有权、失败语义和命名 |
| 1 | REQ-041 Conversation/Message | 高 | `S-H` 主导，`G-M` 实现明确切片 | API、Repository、普通测试可下放；删除/保留、幂等和迁移联合评审 |
| 2 | REQ-047 Run/Event/Approval/Artifact | 极高 | `S-XH` 主导，`G-M` 独立状态机审查 | 不允许单模型独立完成 |
| 2P | REQ-060 菜单与权限导航 | 中 | `K-T` 或 `G-H` 主实现，`S-M` Review | 可独立实现；人工检查 RBAC、深链和移动端 |
| 2A | REQ-062 核心契约塑形 | 极高 | `S-XH` 主修，完成后 `G-M` 只读反例审查 | 表单组件可后续下放；版本、Submission、权限和快照契约不可下放 |
| 2A | REQ-063 来源与授权 Spike | 高 | `G-M/K-T` 调研，`S-H` 安全收口 | 来源调研可下放；许可、SSRF、网络和提示注入策略需人工签字 |
| 3 | REQ-042 Agent Workspace | 高 | `K-T` 负责 UI，`S-H` 负责 Event Store/SSE 恢复 | 展示组件可独立；事件去重、审批交互和断线恢复不可单独放权 |
| 4 | TD-085 边界收口 | 高 | `S-H` 或 `G-M` 按 Slice 实施 | 可按 LLM Port、Direct RAG、DD 逻辑迁移分派；禁止整项一次重构 |
| 5 | REQ-043 Runtime Port/Tool Gateway | 极高 | `S-XH` 主导，`G-M` 反例与并发测试 | Adapter 壳和 DTO 可下放；授权、预算、写语义不可下放 |
| 6 | Pi Worker 与事件 ACK | 极高 | `S-XH/S-H` 主导，`G-M` 故障审查 | Pi API 封装可分派；spool、恢复、取消和未知结果不可独立完成 |
| 6A | APP-005 只读 Agent 对照 | 高 | `G-M` 主实现，`S-H` Review | 可作为 GLM 首个完整应用切片；禁止写入背调业务状态 |
| 6B | APP-009 AI 载体选址 | 高 | `G-M` 或 `K-T` 应用层，`S-H` 约束/证据审查 | UI、方案展示、需求抽取可下放；硬约束和来源口径确定性验证 |
| 7 | Durable HITL、Sandbox、L3 | 极高 | `S-XH` 主导，`G-M` 安全反审 | 不允许单模型独立完成；人工安全负责人签字 |
| 7A | REQ-062 实现与 APP-012 | 极高/高 | `S-XH` 核心，`G-M` 后端，`K-T` 表单 UI | UI、报表模板和解析可下放；发布、版本和多人权限不可单独放权 |
| 8 | APP-030 会展招商 | 高 | `K-T` 对话/移动端，`G-M` 后端，`S-H` Review | REQ-062 契约稳定后可按前后端切片下放 |
| 9 | ACP Adapter | 高 | `S-H` 或 `G-M`，另一模型做协议审查 | 契约冻结后可独立实现 Adapter；权限裁决仍归控制面 |
| 9P | LangGraph Adapter | 高 | `G-M` 或 `S-H` | 通过同一 Runtime conformance suite 后可独立实施 |
| 10 | REQ-061 Memory Governance | 极高 | `S-XH` 主导，`G-M` 隐私反审 | 检索实现可下放；敏感分类、删除、TTL、purpose binding 不可下放 |
| 11 | REQ-049 主动任务与事件触发 | 极高 | `S-XH` 主导，`G-M` 并发审查 | 调度 UI 可下放；重复触发、租约、审批和写操作不可下放 |
| 12 | APP-016 产业研究平台 | 极高 | `S-H` 平台层，`K-T/G-M` 研究工作流 | 研究计划、报告和 UI 可下放；证据规则由领域专家验收 |

## Assignment Rules

- 新模型可按官方定位和公开基准直接取得初始任务，不设置长期晋级期；开工前仍必须验证仓库读取、受控写入、终端、测试和 model id。
- 极高复杂度任务采用“主实现模型 + 第二模型只读反例审查 + 人工签字”。实现模型不得自审后直接合并。
- 不同模型不得同时修改同一状态机、迁移或公共契约。第二模型在主实现结束后进入只读 Review。
- 每个 PR 记录实际 Harness、model id、effort、验收结果、P0/P1 Review 缺陷、返工次数、CI 尝试和交付耗时，用项目内证据修正本矩阵。
- K3 无法确认实际 model id 或工具调用能力时，回退到 `G-H/G-M`，不得以 Provider 别名冒充 K3。
