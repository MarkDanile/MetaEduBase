# REQ-061: Agent 记忆与上下文治理

> Status: ⚫ Candidate
> Priority: P1
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Memory / Context / Privacy / Retrieval
> Created: 2026-07-23
> Source: Codex 式多轮任务体验与教育/园区敏感信息治理目标
> Parent: REQ-059
> Related: REQ-041 / REQ-043 / REQ-047
> Architecture Spec: [REQ-059 源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)

## Problem

聊天记录、Runtime Session、上下文压缩、用户偏好、业务长期记忆和企业知识库是不同的数据生命周期。若统一塞进 prompt 或向量库，既无法可靠删除和解释来源，也容易让学生画像、企业风险、合同和审批信息跨会话或跨租户泄漏。

## Memory Layers

| 层级 | 内容 | 默认生命周期 |
|------|------|--------------|
| Working Context | 当前 Run 的消息、计划、工具结果摘要 | Run 内 |
| Conversation Summary | 压缩后的会话历史与未完成事项 | Conversation |
| Episodic Memory | 用户明确保存的任务经验、偏好和结论 | tenant/user/agent + TTL |
| Semantic Memory | 经治理抽取的稳定事实 | 有来源、版本、有效期 |
| Enterprise Knowledge | 文档、结构化数据和图谱 | 现有 Knowledge/Data 上下文，不等同个人记忆 |

## Scope

- 定义 `MemoryItem` 的 tenant、subject/user、agent、scope、type、content/ref、provenance、confidence、created_by、expires_at 和 deletion 状态。
- 上下文组装器按策略选择消息、摘要、记忆、RAG 证据和工具结果，并记录选择 trace。
- 自动抽取默认关闭或按场景白名单；教育画像、企业风险、合同和审批信息进入长期记忆前必须经过明确策略。
- 支持查看、纠正、删除、过期和重新抽取；删除后不再被上下文组装命中。
- Compaction 与长期记忆分离：压缩 Session 不自动产生跨会话事实。
- OpenClaw Markdown memory、Pi Session compaction、Open Design global/project memory 和 Codex 本地 memory 只作为实现样本；进入企业长期记忆前必须转换为受 tenant/user/agent/purpose/provenance/TTL 治理的 `MemoryItem`。

## Acceptance

- AC-1：tenant/user/agent/scope 任一边界不匹配时，MemoryItem 不可检索和注入。
- AC-2：每条长期记忆具备来源、创建方式、有效期和删除入口；无来源模型结论不能升级为稳定事实。
- AC-3：上下文组装输出可审计 trace，但不记录原始 Chain-of-Thought。
- AC-4：敏感类别支持 deny、manual-confirm、TTL 和 purpose binding 策略。
- AC-5：Conversation 删除、用户数据删除和租户注销具有明确记忆清理/保留规则。
- AC-6：记忆召回效果、错误注入率、过期命中和 Token 成本进入评测基线。
- AC-7：更换 Pi/ACP Runtime 后长期记忆仍由 MetaEduBase 管理，不依赖 Runtime 私有 Session 文件。

## Non-goals

- 不把全部聊天记录向量化后称为长期记忆。
- 不自动保存所有学生、企业和合同信息。
- 不允许模型自行决定绕过 tenant、purpose 或人工确认策略。
- 不替换现有知识库和结构化数据事实源。

## Dependencies / Next Step

- 依赖 REQ-041 Conversation/Message、REQ-047 RunEvent/Evidence 和 REQ-043 Context/Runtime contract。
- 首个 spec 必须先选择一个低敏感场景验证，再扩展教育画像和企业业务数据。
