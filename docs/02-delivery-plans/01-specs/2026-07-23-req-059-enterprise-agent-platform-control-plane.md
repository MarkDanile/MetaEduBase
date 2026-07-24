# REQ-059 Spec: 企业级可控 Agent 平台源码研究与控制面契约

> **Status**: 🟢 Done
> **Requirement**: `docs/01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md`
> **Related**: REQ-041 / REQ-042 / REQ-043 / REQ-047 / REQ-060 / REQ-061 / TD-085
> **Research baseline**: 2026-07-24
> **Purpose**: 冻结架构边界、统一命名和实施顺序；本 spec 不代表对应代码已经落地

---

## 1. 结论先行

MetaEduBase 的目标不是再增加一个“会循环调用工具的 RAG 服务”，而是建设一套类似 Codex 的企业 Agent Harness：

- 产品级 Conversation、Message、AgentRun、RunEvent、Approval、Artifact、Evidence 和 Memory 由 MetaEduBase 持久化并治理。
- 新 Agent Workspace 的每次输入统一进入 `AgentTurnLoopRuntime`；模型可以零工具回答，也可以自主选择 RAG、Query、MCP、Skill 和业务工具。
- 旧 Direct RAG、确定性 SkillRunner、Pi Agent Loop 和 ACP 外部 Agent 都不拥有企业产品事实源；前两者只作为兼容入口或确定性 Workflow 保留。
- Pi 最适合作为首个 Native Agent Runtime 内核，但其源码明确不提供企业权限、MCP、审批、计划模式或沙箱边界。
- ACP 适合做南向 Runtime 协议和能力协商，不适合作为业务编排、产品会话或企业权限事实源。
- OpenClaw 最值得借鉴 Runtime Port、Session Actor、Event Ledger、Approval 和 Task Recovery；不能继承其单 Operator 信任域。
- Nuwax/NuwaClaw 最值得借鉴 ACP Session/Permission 的产品适配；其内存状态、默认 yolo、沙箱降级和 load 失败回退不能进入生产默认值。
- Open Design 最值得借鉴 Runtime Agent Definition、Conversation/Runtime Session 分离、Run Event、Tool Token 和 Agent Workspace 产品模式；它仍是 local-first 单用户产品，不是企业控制面。
- Codex 开源源码最值得借鉴 Thread/Turn/Item、App Server、ThreadManager、Session/TurnContext、ToolRouter/ToolRegistry、Rollout/State DB、Permission/Sandbox 和 Skill/MCP 的分层；未公开的桌面服务端实现不得猜测。

推荐采用“源码级 SDK 集成 + 独立部署单元”，而不是“页面集成”或“整体 fork”：

```text
MetaEduBase Web
  -> MetaEduBase API / SSE
      -> Agent Control Plane (Python + PostgreSQL)
          -> AgentTurnLoopRuntime
              -> Agent Runtime Worker (Node.js, pinned Pi SDK)
              -> ACP / LangGraph / self-hosted adapters
          -> Direct RAG / Skill compatibility adapters
          -> Tool Gateway -> existing RAG / MCP / SkillRunner / QueryService
```

## 2. 证据规则与源码快照

### 2.1 事实优先级

本次结论按以下顺序裁决冲突：

1. 固定 commit 的实际源码与测试。
2. 同 commit 的仓库文档和协议说明。
3. README、架构图和发布说明。
4. 飞书专家解读、文章和二手案例。
5. 无法回溯数据集与评测方法的宣传数字不进入验收基线。

### 2.2 研究快照

| 项目（GitHub） | 固定快照 | 定位 |
|----------------|----------|------|
| [OpenClaw](https://github.com/openclaw/openclaw) | [`5e651d5`](https://github.com/openclaw/openclaw/tree/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9) | 个人 AI Assistant Gateway / Harness |
| [Pi](https://github.com/earendil-works/pi) | [`a5afc3f`](https://github.com/earendil-works/pi/tree/a5afc3f171e422e08a2ccc342827719f9952f38a) | Agent Loop SDK、Session 与 Coding Agent |
| [Nuwax Web](https://github.com/nuwax-ai/nuwax) | [`1278e30`](https://github.com/nuwax-ai/nuwax/tree/1278e30dc42fff2c741185775f7cade5bf01389e) | Agent 产品前端 |
| [NuwaClaw](https://github.com/nuwax-ai/nuwaclaw) | [`77bccef`](https://github.com/nuwax-ai/nuwaclaw/tree/77bccefe701a5a73895dced587fea0636c7216f6) | Electron Agent Client、ACP Engine 与权限交互 |
| [RCoder](https://github.com/nuwax-ai/rcoder) | [`2189eaf`](https://github.com/nuwax-ai/rcoder/tree/2189eaffc4d2a6b0bc92b988c859698b0377124b) | Rust Agent Runner、Session 与 Permission Manager |
| [Claude ACP Adapter](https://github.com/agentclientprotocol/claude-agent-acp) | [`3b72577`](https://github.com/agentclientprotocol/claude-agent-acp/tree/3b725779996a7c8b99b26ef3553abb915423037a) | ACP 到 Claude Agent SDK 的适配 |
| [Open Design](https://github.com/nexu-io/open-design) | [`506c290`](https://github.com/nexu-io/open-design/tree/506c2900b972e6f3a25cfe5fabd7041ec6d869ca) / `0.16.1` | Local-first Agent Workspace 与 Runtime Adapter |
| [Codex](https://github.com/openai/codex) | [`39a2438`](https://github.com/openai/codex/tree/39a2438d16514d0d6f88105d17b0f747994af487) | Coding Agent Core、App Server 与 Harness |
| [LangGraph](https://github.com/langchain-ai/langgraph) | [`31f90df`](https://github.com/langchain-ai/langgraph/tree/31f90df3e6b0268fa77fd2d118a917d420b84a68) | Durable graph execution、checkpoint 与 interrupt/resume |
| [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) | [`4a550ef`](https://github.com/MoonshotAI/kimi-cli/tree/4a550effdfcb29a25a5d325bf935296cc50cd417) | Agent Harness、ACP Server、Session、MCP 与 Approval |
| [LangChain](https://github.com/langchain-ai/langchain) | [`64f5ebf`](https://github.com/langchain-ai/langchain/tree/64f5ebf97101f4ce1bd9a150ba27281f957516a7) | Agent factory、middleware 与 provider/tool 组件 |
| [OpenCode](https://github.com/anomalyco/opencode) | [`743f641`](https://github.com/anomalyco/opencode/tree/743f6410f2e5002723fc5e893039ac49fbfe0de8) | Local-first Agent、Session Runtime 与 Workspace 产品实现 |

进入实施 Spike 前必须重新固定版本、许可证、Node/Python/Rust 运行要求和破坏性变更，不允许使用浮动 `latest`。

### 2.3 专家解读的可用范围

| 材料 | 可取之处 | 源码校正 |
|------|----------|----------|
| OpenClaw 解读 | 正确关注会话、记忆、工具、任务和 Gateway | “固定四层记忆”、视觉记忆和 `MRR@10=0.87` 未在本快照源码/官方文档找到；实际是 Markdown 记忆文件、搜索工具和可插拔后端 |
| Pi 解读 | Agent Loop、并行/串行工具、Hook、steer/follow-up、compaction 基本准确 | Pi README 明确默认继承宿主进程权限；Coding Agent README 明确无内建 MCP、sub-agent、permission popup、plan mode 和 todo |
| Nuwax 解读 | ACP 适配层、能力协商和 Intervention 交互值得参考 | Nuwax 主仓是前端，Runtime 分散在多个仓库；标准 Apache-2.0 无“商业使用需额外授权”条款；不能把 README 架构图视为单仓已交付能力 |
| Open Design 解读 | Agent Workspace、插件和设计任务闭环方向有价值 | 材料基于早期 `0.1.0 Draft`；当前 `0.16.1` 已有桌面应用、Plugin、Automation、Memory、MCP、ACP、Pi RPC、SQLite 与 Run Event |

### 2.4 后续 REQ 实施源码导航

本节是后续 Agent Platform 需求的源码导航事实源。开工时只把固定 commit 的源码和测试作为实现证据；若升级快照，必须在对应 spec/plan 记录新 commit、许可证复核、行为差异和回归命令。链接用于学习协议、状态机和产品模式，不代表允许复制许可证不兼容的代码，也不改变 MetaEduBase 对 Conversation、Run、Approval、Artifact、Evidence、Memory、权限和审计的所有权。

#### 2.4.1 Runtime、Loop 与 Session

| 能力主题 | 项目与固定源码路径 | 可借鉴 | 不可照搬 | MetaEduBase 承接任务 |
|----------|--------------------|--------|----------|---------------------|
| Runtime Port、事件流、恢复 | OpenClaw [`AcpRuntime`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/packages/acp-core/src/runtime/types.ts)、[`EventLedger`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/acp/event-ledger.ts)、[`TaskRegistry`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/tasks/task-registry.ts) | `events + terminal result`、单调 seq、完整性标记、任务恢复 | 单 Operator 信任域、本地 Gateway/主机权限 | REQ-043、REQ-047、REQ-049 |
| Native Agent Loop | Pi [`agent-loop.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/agent-loop.ts)、[`harness/types.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/harness/types.ts)、[`agent-session.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/coding-agent/src/core/agent-session.ts) | tool batch、steer/follow-up、stop hook、上下文变换、运行事件 | 宿主进程权限、Coding Agent UI、把私有 Session 当产品事实源 | REQ-043 Pi Worker / Runtime Adapter |
| Runtime 私有 Session | Pi [`session.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/harness/session/session.ts)、[`jsonl-repo.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/harness/session/jsonl-repo.ts)、[`session-manager.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/coding-agent/src/core/session-manager.ts) | append-only tree、branch、compaction、可替换存储 | JSONL 作为企业 Conversation/RunEvent 唯一存储 | REQ-041、REQ-043 |
| ACP Session 适配 | NuwaClaw [`acpSessionSetup.ts`](https://github.com/nuwax-ai/nuwaclaw/blob/77bccefe701a5a73895dced587fea0636c7216f6/crates/agent-electron-client/src/main/services/engines/acp/acpSessionSetup.ts)、Claude ACP Adapter [`acp-agent.ts`](https://github.com/agentclientprotocol/claude-agent-acp/blob/3b725779996a7c8b99b26ef3553abb915423037a/src/acp-agent.ts)、[`session-load.test.ts`](https://github.com/agentclientprotocol/claude-agent-acp/blob/3b725779996a7c8b99b26ef3553abb915423037a/src/tests/session-load.test.ts) | initialize/new/load/resume/prompt/cancel、能力与错误映射 | NuwaClaw 的 load 失败静默 new；Provider 专属权限模式进入通用契约 | REQ-043 ACP Adapter / conformance suite |
| Rust Runner 与 Session | RCoder [`session_manager.rs`](https://github.com/nuwax-ai/rcoder/blob/2189eaffc4d2a6b0bc92b988c859698b0377124b/crates/agent_abstraction/src/session/session_manager.rs)、[`acp_worker.rs`](https://github.com/nuwax-ai/rcoder/blob/2189eaffc4d2a6b0bc92b988c859698b0377124b/crates/agent_abstraction/src/session/acp_worker.rs)、[`agent_session_service.rs`](https://github.com/nuwax-ai/rcoder/blob/2189eaffc4d2a6b0bc92b988c859698b0377124b/crates/agent_runner/src/service/agent_session_service.rs) | Runner/Worker 分离、session registry、cancel/notify 边界 | 内存 registry/cache 作为 durable state；直接复用其容器部署假设 | REQ-043 Worker、Runtime Cell |
| 数据驱动 Runtime Definition | Open Design [`runtimes/types.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/types.ts)、[`runtimes/registry.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/registry.ts)、[`ACP session`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/agent-protocol/acp/session.ts)、[`Pi RPC session`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/agent-protocol/pi-rpc/session.ts) | RuntimeAgentDef、通用 detection/launch/invoke、ACP/Pi 双适配 | CLI 放权参数、自动 permission/confirm、进程内 Run Registry | REQ-043 RuntimeProfile / Adapter |
| Thread/Turn/Item Harness | Codex [`app-server/README.md`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/app-server/README.md)、[`thread_manager.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/thread_manager.rs)、[`session.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/session/session.rs)、[`turn_context.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/session/turn_context.rs) | start/resume/fork、turn start/steer/interrupt、Session 与 TurnContext 分层 | 未公开桌面服务端推断；本地 Coding Agent 权限替代企业 RBAC | REQ-041、REQ-042、REQ-043、REQ-047 |
| Durable Graph Runtime | LangGraph [`types.py`](https://github.com/langchain-ai/langgraph/blob/31f90df3e6b0268fa77fd2d118a917d420b84a68/libs/langgraph/langgraph/types.py)、[`pregel/_loop.py`](https://github.com/langchain-ai/langgraph/blob/31f90df3e6b0268fa77fd2d118a917d420b84a68/libs/langgraph/langgraph/pregel/_loop.py)、[`pregel/_retry.py`](https://github.com/langchain-ai/langgraph/blob/31f90df3e6b0268fa77fd2d118a917d420b84a68/libs/langgraph/langgraph/pregel/_retry.py) | `Command(resume=...)`、interrupt、superstep、retry policy | checkpoint 等同企业 RunEvent；通用 retry 自动覆盖写 Tool 的 unknown outcome | REQ-043 LangGraph Adapter、REQ-047 |
| Checkpoint 契约 | LangGraph [`checkpoint/base`](https://github.com/langchain-ai/langgraph/blob/31f90df3e6b0268fa77fd2d118a917d420b84a68/libs/checkpoint/langgraph/checkpoint/base/__init__.py)、[`test_put_writes.py`](https://github.com/langchain-ai/langgraph/blob/31f90df3e6b0268fa77fd2d118a917d420b84a68/libs/checkpoint-conformance/langgraph/checkpoint/conformance/spec/test_put_writes.py) | checkpoint/pending writes 接口与 conformance 测试思路 | 直接采用其存储 schema 或绕过 MetaEduBase Event Ledger | REQ-043 Adapter conformance suite |
| Python Agent + ACP Server | Kimi CLI [`acp/server.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/acp/server.py)、[`acp/session.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/acp/session.py)、[`session.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/session.py) | ACP capability、new/load/resume/list/model/cancel、历史 replay | 进程内 `sessions`、本地 wire/session 文件作为企业事实源 | REQ-043 ACP conformance / External Runtime |
| Local-first Agent Runtime | OpenCode [`runner/index.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/runner/index.ts)、[`run-coordinator.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/run-coordinator.ts)、[`event.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/event.ts)、[`store.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/store.ts) | Session runner、coordinator、event projection、input inbox | local/project ownership 与存储 schema 直接变成多租户控制面 | REQ-042、REQ-043 External Runtime |

#### 2.4.2 Tool、Skill、Approval、Sandbox 与 Workspace

| 能力主题 | 项目与固定源码路径 | 可借鉴 | 不可照搬 | MetaEduBase 承接任务 |
|----------|--------------------|--------|----------|---------------------|
| Tool 生命周期 | Codex [`tools/router.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/tools/router.rs)、[`tools/registry.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/tools/registry.rs)、[`mcp.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/mcp.rs) | model-visible spec、Registry/Router、hook 与 MCP 生命周期分离 | Runtime 直拿企业凭证或绕过 ToolGrant | REQ-043 ToolGateway / ToolRouter |
| Approval 状态 | OpenClaw [`approval-shared.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/gateway/server-methods/approval-shared.ts)、NuwaClaw [`approvalInterventionService.ts`](https://github.com/nuwax-ai/nuwaclaw/blob/77bccefe701a5a73895dced587fea0636c7216f6/crates/agent-electron-client/src/main/services/intervention/approvalInterventionService.ts)、RCoder [`permission_manager.rs`](https://github.com/nuwax-ai/rcoder/blob/2189eaffc4d2a6b0bc92b988c859698b0377124b/crates/agent_runner/src/service/permission_manager.rs) | revision、runtime epoch、option 白名单、first-answer-wins | NuwaClaw/RCoder 的进程内 pending Map；生产 `allow-always` | REQ-047、REQ-043 durable HITL |
| Permission 与 Sandbox | NuwaClaw [`permissionCoordinator.ts`](https://github.com/nuwax-ai/nuwaclaw/blob/77bccefe701a5a73895dced587fea0636c7216f6/crates/agent-electron-client/src/main/services/engines/acp/permission/permissionCoordinator.ts)、[`acpSandboxPolicy.ts`](https://github.com/nuwax-ai/nuwaclaw/blob/77bccefe701a5a73895dced587fea0636c7216f6/crates/agent-electron-client/src/main/services/engines/acp/sandbox/acpSandboxPolicy.ts)、Codex [`approvals.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/protocol/src/approvals.rs)、[`sandbox manager`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/sandboxing/src/manager.rs) | 宿主二次写路径校验、独立 permission protocol、平台 sandbox manager | `yolo`、network on、`degrade_to_off`、把 sandbox 当唯一授权层 | REQ-043 Sandbox / WorkspaceLease、REQ-047 |
| Run-scoped Tool Token | Open Design [`tool-tokens.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/tool-tokens.ts)、[`db.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/db.ts) | Run/Project/Endpoint/Operation/TTL/revoke 绑定；产品会话与 Runtime identity 分离 | 进程内 Token Registry；本地 SQLite schema 直接复制 | REQ-041、REQ-043 ToolGrant |
| Agent Hook、MCP 与审批 | Kimi CLI [`kimisoul.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/soul/kimisoul.py)、[`approval.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/soul/approval.py)、[`toolset.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/soul/toolset.py)、[`hooks/engine.py`](https://github.com/MoonshotAI/kimi-cli/blob/4a550effdfcb29a25a5d325bf935296cc50cd417/src/kimi_cli/hooks/engine.py) | steer queue、hook engine、MCP tool wrapper、工具前审批 | yolo/AFK/approve-for-session 直接映射企业生产策略 | REQ-043 Tool Adapter / Hook、REQ-047 |
| Agent Middleware 组件 | LangChain [`agents/factory.py`](https://github.com/langchain-ai/langchain/blob/64f5ebf97101f4ce1bd9a150ba27281f957516a7/libs/langchain_v1/langchain/agents/factory.py)、[`middleware/types.py`](https://github.com/langchain-ai/langchain/blob/64f5ebf97101f4ce1bd9a150ba27281f957516a7/libs/langchain_v1/langchain/agents/middleware/types.py)、[`human_in_the_loop.py`](https://github.com/langchain-ai/langchain/blob/64f5ebf97101f4ce1bd9a150ba27281f957516a7/libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py)、[`tool_retry.py`](https://github.com/langchain-ai/langchain/blob/64f5ebf97101f4ce1bd9a150ba27281f957516a7/libs/langchain_v1/langchain/agents/middleware/tool_retry.py) | middleware composition、tool selection/retry、HITL API 形态 | 把 middleware 当 durable Runtime/Approval；对不可逆写入做通用自动重试 | REQ-043 应用层组件评估，不是 V1 Runtime |
| Tool/Skill Registry | OpenCode [`tool/registry.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/tool/registry.ts)、[`skill/discovery.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/skill/discovery.ts)、[`permission.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/permission.ts) | 工具发现、Skill 惰性加载、permission rule 组织 | 替换现有 MCP/Skill Registry；Runtime 自行裁决 tenant 权限 | REQ-043、REQ-060、REQ-061 |
| Intervention UI | Nuwax [`useConversationStreamResume.ts`](https://github.com/nuwax-ai/nuwax/blob/1278e30dc42fff2c741185775f7cade5bf01389e/src/components/business-component/UnifiedChatSession/hooks/useConversationStreamResume.ts)、[`useAgentInterventionLayer.ts`](https://github.com/nuwax-ai/nuwax/blob/1278e30dc42fff2c741185775f7cade5bf01389e/src/components/business-component/AgentIntervention/hooks/useAgentInterventionLayer.ts)、[`AcpPermissionCard`](https://github.com/nuwax-ai/nuwax/blob/1278e30dc42fff2c741185775f7cade5bf01389e/src/components/business-component/AgentIntervention/AcpPermissionCard/index.tsx) | SSE 恢复、pending intervention 队列、revision/option 交互 | 前端本地状态作为审批事实源；直接嵌入 Nuwax 页面 | REQ-042、REQ-047 |
| Workspace 时间线与权限 Dock | OpenCode [`session timeline`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/app/src/pages/session/timeline/message-timeline.tsx)、[`session-permission-dock.tsx`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/app/src/pages/session/composer/session-permission-dock.tsx)、Open Design [`json-event-stream.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/json-event-stream.ts) | 时间线投影、inline permission、事件流观察面 | UI 直接消费 Runtime 私有事件；照搬单用户信息架构 | REQ-042、REQ-060 |
| Skill 与长期上下文 | Pi [`extensions/types.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/coding-agent/src/core/extensions/types.ts)、Codex [`core-skills/service.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core-skills/src/service.rs)、Open Design [`skills.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/skills.ts)、[`memory.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/memory.ts) | Extension/Skill 接口、惰性发现、Run 隔离复制、文件型记忆模式 | 把 Extension 等同 MCP；global/project 文件记忆替代 tenant/purpose 治理 | REQ-043、REQ-061 |
| Rollout 与可重放记录 | Codex [`rollout/recorder.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/rollout/src/recorder.rs)、Open Design [`runtimes/json-event-stream.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/json-event-stream.ts) | 顺序记录、resume、观察与调试 | rollout/JSONL 直接充当 PostgreSQL 企业事件账本 | REQ-047 RunEventLedger、REQ-043 Worker spool |

后续 Requirement/plan 至少应在 `AI Delivery Profile` 或“参考实现”段落引用本节中与任务直接相关的路径；不得为了“借鉴完整”而一次性复制多个上游的状态机。若源码行为与本 spec 冻结语义冲突，以本 spec 的企业所有权、失败语义和安全默认值为准，并把差异写入 Adapter conformance test。

## 3. RAG 1.0 到 4.0 的准确解释

“RAG 1.0 / 2.0 / 3.0 / 4.0”不是论文共同定义的标准版本号。可以保留为企业内部能力成熟度语言，但必须映射到可验证能力，不能把行业文章中的准确率数字当作项目基线。

| 内部阶段 | 论文/工程能力 | MetaEduBase 对应现状 | 主要缺口 |
|----------|---------------|----------------------|----------|
| 1.0 基础 RAG | chunk -> dense retrieval -> prompt generation；对应 RAG、DPR 基础范式 | 已跨过 | 召回偏差、上下文缺口、冲突与引用治理 |
| 2.0 Retrieval Optimization | query understanding/rewrite、hybrid retrieval、RRF、rerank、context packing | 已具备多路召回、RRF、图谱召回、context packing 和 diagnostics | 评测集、路由、跨工具任务与统一状态容器 |
| 3.0 Adaptive/Corrective RAG | 按查询复杂度路由、检索质量评估、重写与有限重试；Self-RAG、CRAG、Adaptive-RAG、RAPTOR、GraphRAG 分别解决不同子问题 | 局部能力存在，尚无统一 Run/事件/策略 | 不能把 GraphRAG 等同于完整 Agent；不能把所有请求都升级为多轮检索 |
| 4.0 Agentic RAG | Agent Loop 使用检索、数据、MCP、Skill 等工具，带计划、预算、审批、恢复和产物 | 目标态 | Harness、Tool Gateway、Runtime Port、持久化审批、沙箱、记忆治理和评测 |

基础参考：

- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [Dense Passage Retrieval](https://arxiv.org/abs/2004.04906)
- [Self-RAG](https://arxiv.org/abs/2310.11511)
- [Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884)
- [Adaptive-RAG](https://arxiv.org/abs/2403.14403)
- [RAPTOR](https://arxiv.org/abs/2401.18059)
- [From Local to Global: A Graph RAG Approach](https://arxiv.org/abs/2404.16130)

“60% -> 80% -> 85%”只有在固定问题集、答案标准、检索版本、模型版本和评分方法下才有意义。本项目必须重新建立教育和园区数据集，不采用该数字作为 AC。

## 4. 五个源码样本的结构性结论

### 4.1 OpenClaw：控制面和恢复机制参考

关键源码：

- [`packages/acp-core/src/runtime/types.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/packages/acp-core/src/runtime/types.ts)：`AcpRuntime`、`AcpRuntimeTurn`、事件流与独立 terminal result。
- [`src/acp/event-ledger.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/acp/event-ledger.ts)：单调 `seq`、完整性标记、SQLite/内存 Event Ledger 和重放。
- [`src/gateway/server-methods/approval-shared.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/gateway/server-methods/approval-shared.ts)：持久化审批、revision/runtime epoch、first-answer-wins。
- [`src/tasks/task-registry.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/tasks/task-registry.ts)：Task Registry、恢复、阻塞和取消意图。

直接借鉴：

- Runtime Handle 和 Runtime Session 分离。
- `startTurn -> events + result`，终态不依赖流中的最后一帧。
- 同 Session 可变操作使用 actor queue 串行化。
- Event Ledger 记录重放完整性，事件被裁剪后必须标记 incomplete。
- Approval 是持久化状态机，不是一个等待中的 Promise。

拒绝继承：

- OpenClaw 安全文档明确默认面向一个可信 Operator，不是 hostile multi-tenant isolation。
- 不能把其 Gateway、主机权限或本地记忆目录直接作为共享企业服务边界。

### 4.2 Pi：首个 Native Agent Runtime 内核

关键源码：

- [`packages/agent/src/agent-loop.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/agent-loop.ts)：统一 Agent Loop、工具批次、steering、follow-up、stop hook。
- [`packages/agent/src/types.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/types.ts)：AgentContext、AgentEvent、Tool 与 Loop 配置。
- [`packages/agent/src/harness/types.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/harness/types.ts)：Harness Hook 和 Session 抽象。
- [`packages/agent/src/harness/session/session.ts`](https://github.com/earendil-works/pi/blob/a5afc3f171e422e08a2ccc342827719f9952f38a/packages/agent/src/harness/session/session.ts)：append-only tree、branch、compaction 和可替换 `SessionStorage`。

直接借鉴：

- 一个统一 Loop 驱动模型、工具结果和后续 turn，不单独制造 `Planner`、`Executor`、`Evaluator` 三套状态机。
- `transformContext`、`prepareNextTurn`、before/after tool hook、`shouldStopAfterTurn` 是企业策略的接入点。
- SessionStorage/SessionRepo 可适配到自有存储，但 Pi Session 仍只作为 Runtime 私有状态。

必须外围实现：

- tenant/identity/RBAC/ABAC、凭证、MCP Gateway、Approval、Sandbox、Audit、Budget、Artifact、长期记忆。
- Pi README 明确默认拥有启动进程的文件、进程、网络和凭证权限；不能在 Backend API 进程内直接运行。

### 4.3 Nuwax/NuwaClaw：ACP 产品适配样本

关键源码：

- `UnifiedAgentService -> AcpEngine` 和 per-project Engine Registry。
- `acpSessionSetup.ts` 实现 memory/load/new 的 Session 解析。
- `permissionCoordinator.ts` 实现规则、strict write guard 和 ask/yolo 决策。
- `approvalInterventionService.ts` 实现 option 白名单、revision 和 first-answer-wins 的交互状态。
- `acpSandboxPolicy.ts` 把全局沙箱策略映射到 ACP 进程配置。

直接借鉴：

- ACP `initialize/new/load/resume/prompt/cancel` 的能力协商和事件映射。
- Permission Request 转为产品 Intervention，再把用户选择映射回 ACP。
- Session 恢复时抑制历史 SSE 重复渲染。
- strict write guard 对写路径做宿主侧二次校验。

生产禁用项：

- `ApprovalInterventionService.pending` 是进程内 `Map`，进程重启后 pending 审批消失。
- `PermissionManager.pending/session_state/recent_resolutions` 和 Engine/Session Registry 主要是内存状态。
- `getEffectiveMode()` 缺省返回 `yolo`。
- `loadSession` 失败或 Runtime 不支持 load 时，`acpSessionSetup.ts` 会创建新 Session；企业产品必须返回显式 `resume_failed`，防止历史丢失或串会话。
- 沙箱配置默认 `networkEnabled: true`、`fallback: degrade_to_off`；策略解析异常会无沙箱继续运行。企业生产必须 network deny by default 且 fail closed。

Claude ACP Adapter 本身对不存在 Session 返回 `resourceNotFound`，因此“静默新建”是 NuwaClaw 产品适配层选择，不是 ACP 的必然语义。

### 4.4 Open Design 0.16.1：Workspace 和 Adapter 产品模式参考

关键源码：

- [`apps/daemon/src/runtimes/types.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/types.ts)：`RuntimeAgentDef` 数据规范。
- [`apps/daemon/src/runtimes/registry.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/runtimes/registry.ts)：Generic Engine 的 detection/launch/invoke/stream parsing。
- [`apps/daemon/src/agent-protocol/acp/session.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/agent-protocol/acp/session.ts)：ACP Session。
- [`apps/daemon/src/agent-protocol/pi-rpc/session.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/agent-protocol/pi-rpc/session.ts)：Pi RPC 和 Session Resume。
- [`apps/daemon/src/tool-tokens.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/tool-tokens.ts)：Run-scoped Tool Token、endpoint/operation allowlist、TTL 和 revoke。
- [`apps/daemon/src/db.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/db.ts)：Conversation、Message 与 Runtime Session identity 分离。

直接借鉴：

- Adapter 使用数据定义和通用 Engine，避免每个 CLI 重写完整编排器。
- 产品 Conversation 与 Runtime Session 分离，并保存 model/cwd/last_message_id 等恢复身份。
- Skill 每 Run 复制到隔离工作目录，避免修改源 Skill。
- SSE 支持 `Last-Event-ID`；Run Event 写 JSONL 供观察。
- Tool Token 绑定 Run、Project、Endpoint、Operation、TTL 和撤销。
- Workspace 以对话、运行过程、Artifact 为核心，而不是营销式 Chat 页面。

生产禁用项：

- Run Registry、Tool Token Registry 仍是进程内 Map；JSONL/状态不能完整恢复运行。
- ACP permission request 自动选择 session/always/once 中的允许项。
- Pi extension confirm 自动回答 `{confirmed: true}`。
- 多个 CLI 使用 `--allow-all-tools` 或 `--dangerously-skip-permissions` 等 headless 放权。
- Memory 是 global/project 文件存储，无 tenant/user/agent/purpose 企业治理。

### 4.5 Codex：目标 Harness 的公开源码校准

关键源码：

- [`codex-rs/app-server/README.md`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/app-server/README.md)：公开协议定义 Thread、Turn、Item，支持 start/resume/fork、turn start/steer/interrupt、流式 item 和 terminal turn。
- [`codex-rs/core/src/thread_manager.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/thread_manager.rs)：ThreadManager 和 loaded thread 生命周期。
- [`codex-rs/core/src/session/session.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/session/session.rs)：Session 核心状态与服务。
- [`codex-rs/core/src/session/turn_context.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/session/turn_context.rs)：每 Turn 不可变/派生执行上下文。
- [`codex-rs/core/src/tools/router.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/tools/router.rs)：ToolRouter 构建 model-visible specs 和 dispatch。
- [`codex-rs/core/src/tools/registry.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/tools/registry.rs)：ToolRegistry、CoreToolRuntime、Hook 和 lifecycle。
- [`codex-rs/rollout/src/recorder.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/rollout/src/recorder.rs)：RolloutRecorder、resume 和历史列表。
- `codex-rs/protocol`：Op/Event、Approval、Sandbox 与网络权限协议。

对 MetaEduBase 的核心启示：

- “像 Codex”首先是 Thread/Turn/Item 和 App Server/Harness，不是先做一个 Planner 类。
- 计划是 Turn 中的结构化 Item/Event，工具调用是 ToolRouter/Registry 生命周期，权限是独立协议。
- Session 与 TurnContext 分离，允许同一 Thread 在不同 Turn 使用不同模型、权限和工作区快照。
- Rollout、State DB 与 loaded Thread 是不同层；持久化事实不能等同于内存句柄。
- Codex 的本地开发权限模型不能直接替代教育/园区多租户策略；企业层仍由 MetaEduBase 持有。

## 5. 源码能力对比矩阵

| 维度 | OpenClaw | Pi | Nuwax/NuwaClaw | Open Design | Codex | MetaEduBase 采用 |
|------|----------|----|-----------------|-------------|-------|------------------|
| 核心定位 | Assistant Gateway/Harness | Agent Loop SDK | 产品 + ACP Client | Local Agent Workspace | Coding Agent Harness | 企业 Control Plane + Agent Apps |
| Loop | 外部 Runtime | 强 | 外部 ACP Engine | 多 CLI/ACP/Pi | 强 | Pi 首期，Runtime 可替换 |
| 产品会话 | 有，偏个人 | Runtime Session | App/ACP Session | Conversation + agent session | Thread/Turn/Item | Conversation/Message + AgentRun/Event |
| Runtime Port | `AcpRuntime` | SDK API | `AcpEngine` | `RuntimeAgentDef`/Generic Engine | App Server/Core | `AgentTurnLoopRuntime` |
| 事件恢复 | SQLite Event Ledger | Session tree，不是企业 event log | SSE 与 replay 抑制 | JSONL + SSE | Rollout + protocol event | PostgreSQL `RunEventLedger` + SSE |
| MCP/Tool | 强 | 核心无 MCP | ACP 注入 | MCP/connector/tool token | ToolRouter/Registry + MCP | 统一 `ToolGateway` |
| Skill | 文件/插件 | Extension/README | 产品能力 | 每 Run 隔离复制 | Skill service | 区分 deterministic Skill 与 Agent Skill |
| Approval | durable 设计强 | 无内建 | 交互好、状态主要在内存 | 自动批准风险 | 独立 approval protocol | PG 持久化、first-answer-wins |
| Sandbox | 有但非多租户边界 | 需外围 | 可降级关闭 | 多 Runtime 默认放权风险 | 显式 FS/network policy | fail closed、network deny、workspace lease |
| Memory | Markdown + 可插拔检索 | compaction/session | 自动抽取倾向 | global/project 文件 | 独立 memory subsystem | tenant/user/agent/purpose 治理 |
| 多租户 | 否 | 否 | 未形成共享企业边界 | 否 | 本地/产品自身边界 | MetaEduBase 强制拥有 |
| 集成结论 | 参考设计 | 固定 SDK 版本接入 | 参考 ACP Adapter | 参考产品和 Adapter | 参考公开 Harness | 不整体 fork 任一项目 |

## 6. MetaEduBase 当前源码事实

当前项目已经拥有可复用能力，不应重建：

- `knowledge/application/ai_chat_service.py`：多路召回、Fusion、Context Packing、Prompt、LLM 和一次 `query_internal_data` Tool Calling。
- `structured_data/application/query_service.py`：受权限、语义模型和审计治理的智能问数。
- `mcp_registry`：tenant 级 MCP Registry、凭证引用、SSRF 防护、调用与审计。
- `skill_registry/application/skill_runner.py`：确定性 SOP 执行器。
- `due_diligence`：首个 Agent App 和真实业务回归样例。

当前结构风险：

- `AIChatService` 已到 1015 行，同时持有 Retrieval、Prompt、LLM 和 Tool Calling；不能继续把 Agent Loop 塞入该类。
- `AIChatService._call_llm*` 从 application 反向导入 API Router，LLM Port 尚未抽离。
- `SkillRunner` 和 `dd_query_runner` 混入企业背调 Prompt、QCC 参数映射和 evidence 逻辑，通用能力被第一个业务场景反向塑形。
- 还没有产品级 Conversation/Message、AgentRun/RunEvent、Approval/Artifact、Runtime Binding 和 Tool Grant。

因此不能“新增一个 `agent` context + Planner/Executor/Evaluator，然后顺手拆 AIChatService”。正确做法是先冻结控制面契约，再以特征测试渐进迁移现有链路。

## 7. 目标术语与代码命名

### 7.1 产品术语映射

| MetaEduBase 术语 | Codex 对照 | 说明 |
|------------------|------------|------|
| `Conversation` | Thread | 产品级长期会话，面向普通业务用户 |
| `Message` | User/Agent Message Item | 用户可见消息，不承载所有运行对象 |
| `AgentRun` | Turn | 一次请求到 terminal result 的运行 |
| `RunEvent` | Item/Event | 阶段、计划摘要、工具、审批、产物、usage 和错误 |
| `RuntimeSessionBinding` | loaded Session/runtime state | 产品 Conversation 到 Runtime 私有 Session 的可丢失绑定 |
| `TurnInput` | Turn input | 不可变输入快照，引用用户 Message、附件和 `queued/steer` 交付方式 |
| `HumanInputRequest` | user input request | Runtime 需要补充信息时的持久化请求，不等同高风险 Approval |
| `AgentDefinitionVersion` / `RuntimeProfile` | Agent config/runtime selection | 版本化 Agent 能力和 Runtime 绑定；切换 Runtime 时创建新 Binding |
| `RuntimeCapabilitySnapshot` / `RunConfigSnapshot` / `ContextSnapshot` | TurnContext snapshot | 固化本 Run 的 Runtime 能力、预算、模型、工具和上下文选择 |
| `ModelGrant` | run-scoped model access | 授权本 Run 使用指定模型能力，不包含 Provider 长期凭证 |
| `Artifact` / `EvidenceItem` | generated item/tool result 的业务扩展 | 报告、表格、草稿和可追溯证据 |

不直接把后端实体命名为 Thread/Turn，是因为 MetaEduBase 已面向教育和园区业务，`Conversation/AgentRun` 语义更清晰；通过映射保留 Codex 架构经验。

### 7.2 不采用三个通用类

`Planner / Executor / Evaluator` 可用于解释能力，不建议直接成为三个核心服务：

- Pi 源码使用统一 Agent Loop，没有三个独立持久化状态机。
- 计划应是 `RunPlan` 数据或 `plan_summary` 事件，不是另一个会话事实源。
- 工具执行应进入 `ToolRouter/ToolGateway`，不由通用 Executor 绕过策略。
- 评估拆为可验证策略：`EvidencePolicy`、`BudgetPolicy`、`StopPolicy`；模型自反思仍留在 Runtime Loop。

建议应用服务命名：

| 名称 | 职责 | 源码依据 |
|------|------|----------|
| `RunCoordinator` | 创建 Run、解析 Runtime Profile、持久化 binding、接收事件、处理终态/取消 | OpenClaw Runtime Manager、Codex Thread/Turn lifecycle |
| `RuntimeProfileResolver` | 按 `AgentDefinitionVersion` 和租户策略解析 Runtime/模型/工具配置，不判断问题简单或复杂 | Open Design Runtime Agent Definition、Codex TurnContext |
| `AgentTurnLoopRuntime` | Runtime 中立的 create/resume/start turn/steer/cancel/close contract | Pi Agent Loop、OpenClaw `AcpRuntime`、Codex App Server |
| `RuntimeRegistry` | 按 runtime id/capability 选择 Adapter | OpenDesign Registry、OpenClaw Runtime Registry |
| `ToolRouter` | 生成本 Run 模型可见工具集合 | Codex `ToolRouter` |
| `ToolGateway` | Tool Grant 校验、策略、调用、审计和结果裁剪 | Codex ToolRegistry、Open Design Tool Token |
| `ContextAssembler` | 组装 Message、Summary、Memory、RAG Evidence 和 Tool Result | Pi `transformContext`、Codex TurnContext |
| `RunEventLedger` | 分配 seq、持久化、重放和完整性 | OpenClaw Event Ledger |
| `ApprovalService` | durable approval、幂等、revision/epoch、过期 | OpenClaw Approval |
| `EvidencePolicy` | 覆盖度、冲突、来源和停止/重试判定 | CRAG/Self-RAG 的企业可验证部分 |
| `BudgetPolicy` / `StopPolicy` | step/token/time/cost/tool retry 上限 | Pi stop hook、Agent Harness 通用约束 |

### 7.3 目标目录草案

目录只在对应 Requirement 进入 Ready 后创建；当前用于冻结命名和依赖方向：

```text
packages/server-python/app/contexts/
├── agent_workspace/
│   ├── application/
│   │   └── conversation_service.py
│   ├── domain/
│   │   ├── conversation.py
│   │   └── message.py
│   ├── infrastructure/
│   └── interfaces/api/
├── agent_execution/
│   ├── application/
│   │   ├── run_coordinator.py
│   │   ├── runtime_profile_resolver.py
│   │   ├── context_assembler.py
│   │   └── tool_gateway.py
│   ├── domain/
│   │   ├── agent_run.py
│   │   ├── run_event.py
│   │   ├── agent_definition_version.py
│   │   ├── runtime_profile.py
│   │   ├── runtime_session_binding.py
│   │   ├── turn_input.py
│   │   ├── human_input_request.py
│   │   ├── tool_call.py
│   │   ├── tool_grant.py
│   │   ├── model_grant.py
│   │   ├── approval_request.py
│   │   ├── artifact.py
│   │   ├── evidence_item.py
│   │   ├── snapshots.py
│   │   └── ports/
│   │       ├── agent_turn_loop_runtime.py
│   │       └── run_event_ledger.py
│   ├── infrastructure/
│   │   ├── runtimes/
│   │   │   ├── compatibility_runtime.py
│   │   │   └── remote_agent_runtime.py
│   │   └── persistence/
│   └── interfaces/api/
└── agent_memory/                         # REQ-061 进入 Ready 后
    ├── application/context_memory_service.py
    ├── domain/memory_item.py
    └── infrastructure/

packages/agent-runtime-worker/            # REQ-043 Pi Spike 验证后
├── src/runtime/runtime-server.ts
├── src/runtime/runtime-registry.ts
├── src/runtime/pi-runtime-adapter.ts
├── src/runtime/acp-runtime-adapter.ts
├── src/session/runtime-session-registry.ts
├── src/events/runtime-event-spool.ts
├── src/events/runtime-event-mapper.ts
└── src/tools/tool-gateway-client.ts
```

`runtime-session-registry` 只能缓存 live handle；`RuntimeSessionBinding` 必须先写 PostgreSQL。Worker 使用本地 SQLite spool 保留未 ACK 事件，但它仍不是企业事实源。Worker 重启后 live handle 可丢失，控制面必须把 Run 恢复为 `resume_required / failed`，不能假装仍在运行。

## 8. 目标运行流程

```mermaid
flowchart TD
    U["用户输入"] --> API["Agent Workspace API"]
    API --> CM["Conversation / Message"]
    CM --> RC["RunCoordinator"]
    RC --> RP["RuntimeProfileResolver"]
    RP --> AR["AgentTurnLoopRuntime"]
    AR --> PI["PiRuntimeAdapter (V1 default)"]
    AR --> ACP["ACP / future adapters"]
    PI --> TG
    ACP --> TG
    TG --> K["Knowledge Search / Graph Recall"]
    TG --> Q["QueryService"]
    TG --> M["MCPInvocationService"]
    TG --> S["SkillRunner"]
    PI --> SP["SQLite event spool"]
    ACP --> SP
    SP -->|"runtime_seq stream"| RC
    RC --> EL["RunEventLedger"]
    EL -->|"ACK through runtime_seq"| SP
    TG --> EL
    EL --> PG[("PostgreSQL")]
    PG --> SSE["SSE after_seq replay"]
    SSE --> API
    TG --> AP["ApprovalService"]
    AP --> PG
```

### 8.1 Turn Entry 与 Runtime Binding

新 Agent Workspace 不使用外部“问题复杂度分类器”决定是否进入 Agent Loop：

1. `AgentDefinitionVersion` 固定 Agent 指令、可发现能力和默认 `RuntimeProfile`。
2. `RuntimeProfileResolver` 只解析租户允许的 Runtime、模型、工具、预算和自主等级，不判断用户问题简单或复杂。
3. Pi 是 V1 默认 `AgentTurnLoopRuntime`；模型输出最终文本且没有 ToolCall 时，本 Turn 零工具结束。
4. 需要知识、数据或行动时，模型在同一 Loop 内选择授权 Tool；Policy 可以隐藏或拒绝不允许的 Tool，但不替模型做语义规划。
5. 切换 Runtime/Profile 创建新 `RuntimeSessionBinding`；产品 Conversation、Message、Run 和 Artifact 保持不变，不迁移 Runtime 私有 checkpoint。

旧 `/ai/chat/evidence` 和确定性 Agent App Workflow 可继续使用 compatibility adapter，逐步写入统一 Conversation/RunEvent；这不构成新 Workspace 的旁路语义。

### 8.2 Agent Loop

V1 Agent Turn 由 Pi Agent Loop 驱动：

- 模型根据系统指令和可见 Tool Specs 产生计划摘要和工具调用。
- Tool 调用全部回到 MetaEduBase Tool Gateway。
- `EvidencePolicy` 把缺失、冲突和来源不足转为结构化 Tool Result/next-turn context。
- `BudgetPolicy` 与 `StopPolicy` 通过 Pi Hook/stop hook 限制循环。
- 最终回答和结构化 Artifact 由 RunCoordinator 收口，不能由 Worker 直接写业务表。
- 活动 Run 中的新消息默认持久化为下一 Run 的 queued `TurnInput`；只有用户显式 steer 时才注入当前 Session actor queue。
- Runtime 追问生成 `HumanInputRequest` 并进入 `waiting_input`；高风险行动生成 `ApprovalRequest` 并进入 `waiting_approval`，二者不能复用同一状态或响应 API。

## 9. 核心契约

### 9.1 AgentTurnLoopRuntime

最小语义以 OpenClaw `AcpRuntime`、Codex App Server 和 ACP 能力交集为基线：

```text
initialize() -> RuntimeCapabilities
create_session(input) -> RuntimeSessionHandle
resume_session(binding) -> RuntimeSessionHandle | ResumeError
start_turn(handle, TurnInput) -> RuntimeRun(events, terminal_result)
stream_events(handle, after_runtime_seq)
ack_events(handle, through_runtime_seq)
get_status(handle)
set_mode(handle, mode)
set_config_option(handle, key, value)
respond_input(handle, input_response)
respond_approval(handle, approval_response)
steer_turn(handle, TurnInput)
cancel_run(handle, reason)
close_session(handle, discard_persistent_state)
```

硬语义：

- `events` 和 `terminal_result` 分离。
- `resume_session` 失败返回稳定错误，不得自动 `create_session`。
- 一个 Runtime Session 同时最多一个可变 Turn；steer/follow-up 进入 Session actor queue。
- 每次调用携带 `tenant_id / conversation_id / run_id / runtime_epoch`，Adapter 不信任 Worker 内存映射。
- Worker 先将事件写入本地 SQLite spool 再发送；Control Plane 以 `(binding, epoch, runtime_seq)` 幂等持久化并分配 `RunEvent.seq`，提交成功后才 ACK。

### 9.2 AgentRun 与 RunEvent

`AgentRun` 是终态事实源：

```text
queued -> starting -> running
running -> waiting_input|waiting_approval|resume_required|cancelling
waiting_input|waiting_approval -> running|cancelling|expired
resume_required -> starting|failed|cancelled
queued|starting|running|waiting_input|waiting_approval|cancelling
  -> completed|failed|cancelled|expired
```

状态迁移硬条件：

- `resume_required -> starting` 只能由同一 `RuntimeSessionBinding`、预期 runtime epoch 的 `resume_session` 成功触发；恢复失败保持 `resume_required` 并记录稳定错误。创建新 Binding 必须创建新 Run，不能借 `starting` 静默续跑旧 Run。
- cancel/timeout 先阻止新 ToolCall 并进入 `cancelling`。存在 `executing/reconciling` 写 Tool 时不得落 `cancelled/expired`；必须先 reconcile 为 succeeded/failed，或把 ToolCall 置为 `outcome_unknown`、Run 置为 `resume_required`。
- `outcome_unknown` 是未解决、非终态 ToolCall 状态。只允许经 Provider 对账或具名人工裁决转为 `succeeded/failed`；存在任何 `outcome_unknown` 时，Run 不得进入 completed/failed/cancelled/expired。
- Approval 过期时，对应 `waiting_approval` ToolCall 原子转为 `cancelled`、释放预算和 Grant；Run 才能继续转为 expired/cancelled。Run 进入任一终态前不得残留非终态 ToolCall/HumanInputRequest/ApprovalRequest。

`RunEvent` 最小字段：

```text
tenant_id, conversation_id, run_id, seq, event_id,
type, occurred_at, visibility, payload_ref|payload,
runtime_id, runtime_epoch, causation_id, correlation_id
runtime_binding_id, runtime_seq, runtime_event_id
```

建议事件族：

```text
run.started / phase.changed / plan.summary
tool.started / tool.progress / tool.completed / tool.failed
evidence.added / evidence.conflict
approval.requested / approval.resolved / approval.expired
input.requested / input.resolved
artifact.created / artifact.updated
usage.updated / retry.scheduled / error.reported
run.resume_required / tool.outcome_unknown
runtime.terminal_observed
run.completed / run.failed / run.cancelled / run.expired
```

原始 Chain-of-Thought 不进入 `RunEvent`；UI 只显示 `plan.summary`、phase、tool lifecycle、证据、审批、usage 和错误摘要。

Worker 的终态通知只映射为 `runtime.terminal_observed`。RunCoordinator 读取独立 `terminal_result` 后，在同一事务中 CAS `AgentRun` 终态并追加唯一 canonical `run.completed/failed/cancelled/expired` 事件。相同重复结果幂等忽略；事件与 terminal result 或后续 terminal result 冲突时不覆盖既有终态，记录双方 digest，并以 `runtime_terminal_mismatch` 失败/告警处理，禁止静默选择“成功”。

### 9.3 Tool Gateway 与 Tool Grant

Tool Gateway 是唯一企业调用入口：

```text
Runtime ToolCall
  -> prepare(arguments digest, risk, idempotency/reconcile capability)
  -> approval(if required, exact ToolCall + arguments digest)
  -> reserve(ToolGrant + budget)
  -> execute(adapter)
  -> reconcile(provider idempotency key / status / business audit)
  -> settle or release budget
  -> resume with model-facing ToolResult
```

`ToolGrant` 必须是短期、Run-scoped、可撤销凭证，至少绑定：

- tenant、actor、agent、run、runtime epoch。
- tool id/version、允许 operation、参数约束和风险等级。
- TTL、最大调用数、预算和 purpose。

Runtime Worker 不获得 MCP secret、数据库连接或租户长期 Token。

写 Tool 的 `ToolCall` 状态至少覆盖 `prepared / waiting_approval / reserved / executing / reconciling / succeeded / failed / outcome_unknown / cancelled`。其中只有 `succeeded/failed/cancelled` 是终态；`outcome_unknown` 必须保持可对账。执行请求必须携带稳定 idempotency key；Worker 或网络在 execute 后丢失时先 reconcile。无法证明成功或失败时进入 `outcome_unknown`，暂停 Run 并交由人工/对账流程处理，禁止自动重放。没有幂等键或可靠对账能力的写 Tool 只能作为 L2 Draft/Action Proposal 暴露。

### 9.4 Approval

审批不是 Runtime UI Promise。`ApprovalRequest` 至少持久化：

- tenant/run/tool_call/runtime_epoch/revision。
- risk、参数摘要、option 白名单、reviewer scope。
- pending/resolved/rejected/expired/cancelled/superseded。
- expires_at、resolved_by、resolved_at 和 response digest。

并发规则：first-answer-wins；相同响应幂等成功，不同响应稳定冲突。服务重启后仍可查询和处理；Runtime 已丢失时审批只能终结为 superseded/cancelled，不能执行旧 Tool Call。

V1 审批精确绑定一次 `ToolCall`、参数摘要、revision 和 runtime epoch，不支持持久化 `allow-always`。审批通过后重新签发匹配批准参数的新 Grant；参数变化必须重新 prepare/approval。

审批拒绝、过期、取消或 superseded 时，尚未执行的 ToolCall 必须原子转为 `cancelled` 并释放 Grant/预算；已经进入 executing/reconciling 的 ToolCall 不受审批状态回滚，必须完成 reconcile 或进入 `outcome_unknown`。

### 9.5 Run Snapshots 与配置

- `RuntimeCapabilitySnapshot` 固化 create/resume 时协商到的 Runtime 能力。
- `RunConfigSnapshot` 固化 `AgentDefinitionVersion`、`RuntimeProfile`、模型、预算、自主等级、Policy 版本和工具集合。
- `ContextSnapshot` 记录选入本 Run 的 Message、Summary、Memory、Evidence 和 Tool Result 引用，不复制敏感正文。
- `ModelGrant` 是 Run-scoped、可撤销的模型访问授权；Worker 只获得短期调用能力，不获得 Provider 长期凭证。
- Run 创建后配置变更只影响下一 Run；审计和恢复使用当前 Run 的不可变 Snapshot。

### 9.6 Compatibility Run Adapter

旧 Direct RAG/Skill 路径通过 `CompatibilityRunAdapter` 写入统一 Run/Event，而不是伪造有私有 Session 的 Agent Runtime：

- RunCoordinator 在调用前创建 AgentRun，并为本次无状态调用生成 adapter invocation id/runtime epoch；`RuntimeSessionBinding` 可为空。
- Adapter 把旧服务的开始、来源、diagnostics、产物、错误和返回值映射为同一 RunEvent/terminal contract；canonical 终态仍只由 RunCoordinator 提交。
- 无原生 Session 的 compatibility path 不声明 resume/steer 能力；进程中断后明确失败，不静默重跑产生重复回答或业务副作用。
- Compatibility adapter 只服务旧入口和迁移期验收，不接受新 Agent Workspace 输入，也不得成长为第二套 Tool Gateway。

### 9.7 Sandbox 与 Workspace

生产默认：

- Worker 与 FastAPI API 分进程/容器；Pi 不在 API 进程内执行。
- 每 Run 或每受控 Session 使用 `WorkspaceLease`，只挂载允许目录。
- 文件系统默认 read-only，写目录 allowlist；网络默认 deny，按域名/IP/协议 allowlist。
- sandbox unavailable、policy parse error、mount failure 和 network policy failure 全部 fail closed。
- 高风险租户或写任务使用独立 Runtime Cell；只读低风险任务可共享 Worker 池。
- Tool Gateway 再做宿主侧策略，Sandbox 不是唯一授权层。

### 9.8 Memory 与 Context

必须区分：

- Working Context：当前 Run 的消息、Tool Result、计划摘要。
- Conversation Summary：压缩历史，不等同长期事实。
- Episodic/Semantic Memory：有 tenant/user/agent/purpose/provenance/TTL 的长期记忆。
- Enterprise Knowledge：现有知识库、结构化数据和图谱，不叫个人记忆。

Pi compaction、OpenClaw Markdown memory、Open Design global/project memory 和 Codex 本地 memory 都只能提供实现参考，不能直接成为企业记忆库。

## 10. 集成与部署决策

### 10.1 Pi

选择：源码级 SDK 集成，部署为独立 Node Runtime Worker。

- 在自有 `packages/agent-runtime-worker` 中固定 `@earendil-works/pi-agent-core` 等具体版本和 lockfile。
- `AgentDefinitionVersion` 通过 `RuntimeProfile` 默认绑定 `PiRuntimeAdapter`；后续更换 Adapter 不修改 Conversation/Run 事实源。
- 通过自有 `PiRuntimeAdapter` 使用 Agent Loop、SessionStorage 和 Hook；Pi 私有 Session 只由 `RuntimeSessionBinding` 引用。
- Worker 使用本地 SQLite event spool；未收到 Control Plane ACK 的 `runtime_seq` 事件在重连后重发。
- 开发期可以 monorepo package 运行；生产构建为独立容器镜像，由 MetaEduBase 控制版本和回滚。
- V1 交付 Docker Compose 部署单元，同时保持 health check、配置、存储和网络边界可迁移到 Kubernetes。
- 不整体 fork Pi；只有上游 bug 无法扩展且补丁已尝试 upstream 时才维护最小 patch。
- 不嵌入 Pi 页面，不让浏览器连接 Pi RPC。

### 10.2 ACP

选择：作为南向 Runtime 协议，优先与 Pi Worker 使用同一远程 Runtime Port 对接控制面。

- ACP Adapter 负责 capability negotiation、session new/load/resume、prompt/steer、cancel、permission 和 event mapping。
- MetaEduBase Approval/Tool Gateway/Sandbox Policy 包裹 ACP，不信任 Agent 自报权限。
- `session/load` 的 `resourceNotFound`、capability missing 和 cwd/model mismatch 都是显式错误。

### 10.3 OpenClaw、Nuwax、Open Design、Codex

- 不作为 MetaEduBase 页面或主后端整体嵌入。
- 采用其协议、状态机和产品模式，保持许可证引用和源码证据。
- Codex/Claude Code/OpenCode 等未来可作为 ACP External Runtime，仍不拥有 MetaEduBase Conversation、Approval 和 Artifact。

## 11. 分阶段落地与现实工期

以下工期假设为 4-6 人稳定团队：2-3 后端/Runtime、1-2 前端、1 QA/平台兼任；不含采购审批和外部数据接入等待。

| 阶段 | 建议工期 | 交付 | 依赖/门禁 |
|------|----------|------|-----------|
| 0. Contract Freeze | 1-2 周 | 本 spec、Context Map、Runtime/RunEvent/ToolGrant schema、APP-005/009 首批 Rubric、APP-012/030 共享采集边界和 APP-016 研究边界 | REQ-059 Architecture Gate 已完成 |
| 1. Durable Control Plane | 2-3 周 | REQ-041 Conversation/Message；REQ-047 Run/Event/Approval/Artifact 最小表与 API；旧 Direct RAG/Skill compatibility path | 不接 Pi；先证明刷新/重连/终态 |
| 2. Workspace & Navigation | 2-3 周 | REQ-042 三栏 Workspace；REQ-060 单一导航/permission source | Playwright desktop/mobile + RBAC matrix |
| 3. Boundary Closure & Tool Gateway | 2-4 周 | TD-085 分 Slice；LLM Port；Direct RAG 收缩；AgentTurnLoopRuntime/RuntimeProfile/ToolRouter/ToolGateway/ToolGrant contract | 现有 RAG/问数/Skill/DD 回归全绿 |
| 4. Pi Read-only Pilot | 3-4 周 | Node Worker、PiRuntimeAdapter、SQLite spool/ACK；先跑 APP-005 只读对照，再以 APP-009 跑真实资产 + 授权外部交通/配套数据的多方案选址 | sandbox fail closed；无真实 secret 下发；不替换 APP-005 生产 SkillRunner；外部数据经 REQ-063 |
| 5. Controlled Action | 4-6 周 | durable HITL、workspace lease、network allowlist、L3 写语义、REQ-062/APP-012 闭环，再复用到 APP-030 | crash/reconcile/unknown、重启恢复、跨租户攻击测试 |
| 6. Runtime Expansion | 2-4 周 | ACP 与 LangGraph Adapter，复用同一 conformance suite | capability/new/resume/steer/cancel/permission/event mapping 全通过 |
| 7. Memory & Active Work | 4-6 周 | REQ-061 Memory Governance、REQ-049 schedule/event trigger、APP-016、评测与运营面板 | 敏感记忆策略、删除/纠正、成本基线 |

可演示 V1 约 8-12 周；满足企业生产治理的 V1 约 16-24 周。任何“2-4 周完成超级智能体”的计划通常只覆盖 Agent Loop 演示，不覆盖多租户、恢复、审批、沙箱、审计和评测。

### 11.1 对原四阶段方案的调整

| 原方案 | 调整 |
|--------|------|
| A. 先建 Planner/Executor/Evaluator Agent Core，并拆 AIChatService | 先做 Contract/RunEvent；TD-085 单独拆依赖倒置；Pi 提供统一 Loop，不新建三个通用类 |
| B. 再做记忆 + 路由 | 新 Workspace 不做外部问题复杂度路由；先冻结 Runtime Profile/Binding 和 Tool Policy，长期记忆延后，Conversation/Run 持久化不能延后 |
| C. 再接 MCP/Skill | MCP/Skill 已交付；当前工作是 Tool Gateway 包装和授权，不是重建 Registry |
| D. 最后产品化控制台 | 会话、Run、审批和事件 UI 是 Harness 的早期验收面，不应等 Loop 完成后补 |

### 11.2 AI Delivery Profile

后续每个交付 plan 必须记录复杂度、风险面、主 Harness/model/effort、允许下放范围、第二评审模型、人工门禁和验证命令。初始任务分工、推理强度和双模型评审规则以 [Agent Platform AI Delivery Routing Matrix](../../03-engineering-governance/03-matrices/agent-platform-ai-delivery-routing.md) 为事实源。该矩阵只管理编码交付责任，不参与产品运行时的 `RuntimeProfile` 或 `ModelGrant`。

## 12. 首批企业场景

企业 360 背调是第一个产业园区 AI 应用和 P3 首个平台化样板，但不作为平台基础能力或唯一验收场景。园区近期主线固定为 APP-005 -> APP-009 -> APP-012 -> APP-030 -> APP-016；APP-011 并入 APP-016，APP-022 并入 APP-012，教育样例随后验证跨行业复用。

建议园区五应用验收场景：

| 场景 | 执行方式 | 验证重点 |
|------|----------|----------|
| 园区第一号：APP-005 企业 360 背调 | deterministic SkillRunner 生产基线 + Agent Runtime 只读对照 | 接入统一 Conversation/Run/Approval/Artifact/Workspace；保持制审分离、报告/证据和 MCP 审计，不用 Agent 路径直接替换生产编排 |
| 园区第二号：APP-009 AI 载体选址 | Agent Runtime + QueryService + REQ-063 External Data | 真实资产库存、企业硬约束、授权地图/交通数据、多方案权衡、来源时效和人工选择；不自动锁定房源 |
| 园区第三号：APP-012 招商动态报表 | REQ-062 Campaign Workflow + Agent 辅助 | 统计要求解析、系统覆盖判断、动态表单审核发布、多人填报、数据快照、汇总报告和常态模板 |
| 园区第四号：APP-030 会展招商 | REQ-062 Campaign Workflow + Conversation Capture | 历史模板复用、本次字段版本、百人级受众、表单/对话登记、主体去重、进度和领导汇总 |
| 园区第五号：APP-016 产业研究辅助平台 | Research Agent + Skill + REQ-063 External Data + Artifact | 研究计划、授权来源、产业链/企业分析、假设与事实分离、证据化报告和招商指导；吸收 APP-011 |

高风险写操作首期不让自由 Agent 无审批执行。具备幂等键与可靠对账的 Tool 可在确定性 Policy 校验和精确审批后按 L3 执行；其余 Tool 只生成草稿或 Action Proposal。

## 13. 自主等级

| 等级 | 行为 | 默认场景 |
|------|------|----------|
| L0 Observe | Direct RAG/只读查询，只回答与引用 | FAQ、制度问答 |
| L1 Recommend | 多步只读 Agent，输出建议和 Artifact | 备课、经营分析 |
| L2 Draft | 生成工单、通知、方案草稿，不提交外部系统 | 政策申报材料、运营方案 |
| L3 Approve-to-Act | 每次高风险动作经持久化审批 | 工单创建、数据更新 |
| L4 Bounded Auto | 仅 allowlisted Workflow、预算和撤销范围内自动执行 | 成熟的定时报告/提醒 |

L4 不是“yolo”。它必须是明确业务范围、确定性前后置校验、可撤销动作和审计齐备后的策略结果。

## 14. 评测与上线门禁

### 14.1 效果指标

- Zero-tool/tool decision quality：应直接回答时不滥用工具，需要事实源时不跳过检索或问数。
- Tool exposure policy accuracy：按 AgentDefinition/tenant/purpose 生成的可见工具集合是否正确。
- Task success：按场景验收 Rubric 完成任务的比例。
- Groundedness 与 evidence coverage：关键结论是否有受治理证据。
- Contradiction handling：证据冲突是否显式呈现和升级。
- Tool selection/argument accuracy、Tool failure recovery、human intervention rate。
- Memory precision、错误注入率、过期命中率和删除后残留率。

### 14.2 运行指标

- 各 RuntimeProfile / AgentDefinition 的 P50/P95 首 token、总时长和排队时间。
- 每 Run step/tool/retry/token/cost。
- resume success、event gap、duplicate event、terminal mismatch。
- spool pending/ACK lag、runtime seq duplicate/gap、approval pending/expired/conflict、sandbox denied、policy denied。
- write reconcile success、`outcome_unknown`、人工对账时长和禁止盲重试命中数。

### 14.3 故障与安全门禁

- Worker 进程在 running/waiting_approval 时被 kill，控制面状态可恢复或显式失败。
- 对 `prepare / approval / reserve / execute / reconcile / settle` 每个边界注入崩溃；execute 后无法判定结果时必须进入 `outcome_unknown`。
- Worker spool 在 ACK 丢失、重复发送和重启后仍可重放；Control Plane 不产生重复 `RunEvent` 或重复终态。
- SSE 断线后从 `after_seq` 重放，无重复终态和事件缺口静默。
- ACP `session/load` 不存在/损坏时不创建新 Session。
- Sandbox/网络策略不可用时拒绝启动 Run。
- tenant A 的 Conversation、Run、Tool Grant、Approval、Artifact、Memory 对 tenant B 全部不可见且不可调用。
- Runtime 伪造 tenant/run/tool id、重放过期 grant、绕过 Gateway 均失败。

## 15. 冻结决策与待决项

### 15.1 已冻结

- MetaEduBase 是企业控制面和数据事实源。
- 前端只连接 MetaEduBase API/SSE，不页面集成外部 Agent。
- Pi 固定版本 SDK + Node Worker/Sidecar，不整体 fork。
- ACP 是南向 Runtime 协议，不是业务编排引擎。
- 新 Agent Workspace 输入统一进入 `AgentTurnLoopRuntime`；旧 Direct RAG/Skill 和确定性 Workflow 保持兼容边界。
- 不保存或展示原始 Chain-of-Thought。
- Approval、Tool Grant、RunEvent 和 Runtime Binding 必须持久化或可重建；内存 Map 不是事实源。
- `session/load` 失败不得静默创建新 Session；Sandbox 不得 fail open。

### 15.2 Architecture Gate 冻结决策

2026-07-23 按源码研究、当前代码边界和企业部署约束冻结以下 V1 默认值。后续 Requirement 可以在不改变产品事实源和 Port 语义的前提下优化实现；改变本表中的所有权、失败语义或安全默认值属于破坏性架构变更，必须回到 REQ-059 重新评审。

| ID | 决策 | V1 冻结值 | 后续触发条件 |
|----|------|-----------|--------------|
| AG-1 | Control Plane -> Worker 传输 | 内部 HTTP/JSON command API + SSE event stream；终态独立查询；生产使用服务身份和 mTLS/等价双向认证 | 只有真实压测证明 HTTP/SSE 无法满足吞吐、背压或双向流要求时，才在 `AgentTurnLoopRuntime` 后评估 gRPC |
| AG-2 | Runtime 隔离 | L0/L1 只读任务可使用共享 Worker 池；写操作、敏感租户、不可信 ACP、自定义文件/网络能力进入独立 Runtime Cell | 根据真实资源争用、合规等级和 P95 排队时间调整 Cell 粒度，不降低 fail-closed 默认值 |
| AG-3 | RunEvent 存储 | 可公开/内部 JSON payload `<= 32 KiB` 才内联 PostgreSQL；更大、二进制或敏感内容外置对象存储，仅保留 ref/digest/size/classification | 真实事件体积分布证明阈值不合理时按迁移 spec 调整，不允许直接增大数据库行而无基线 |
| AG-4 | ToolGrant | 服务端生成 256-bit opaque token，只存服务端摘要；默认 TTL 5 分钟、最大 15 分钟；写操作单次使用；预算由控制面 reserve、按 execute/reconcile 结果 settle/release | 只有 Gateway 压测证明在线校验成为瓶颈时才评估签名 token，且仍需即时撤销通道 |
| AG-5 | 首批 Pilot | APP-005 保持 SkillRunner 生产基线并做只读 Agent 对照；APP-009 是首个新 Agent Pilot；其余园区应用使用各自 Requirement 验收 | 外部来源未授权时 APP-009 明确 Blocked，不用 mock/dry-run 冒充真实 Pilot 通过 |
| AG-6 | bounded context | 首个实现 Slice 同时建立 `agent_workspace` 与 `agent_execution` 两个契约边界；`agent_memory` 后置 | 代码和迁移真正引入上下文时更新 `ARCHITECTURE.md`，不先创建通用 `agent` context |
| AG-7 | Turn Loop 与 Runtime 绑定 | 新 Agent Workspace 输入统一进入 `AgentTurnLoopRuntime`；Pi 为 V1 默认 RuntimeProfile；切换 Runtime 新建 Binding，不迁移私有 checkpoint | 只有产品决定恢复外部问题复杂度路由时回到 REQ-059 评审；旧 AI Chat/Workflow 兼容不触发变更 |
| AG-8 | Worker 事件与写操作恢复 | Worker SQLite spool + runtime_seq + Control Plane ACK；写操作按 prepare/approval/reserve/execute/reconcile/settle，未知结果 `outcome_unknown` 且禁止盲重试 | 只有 Provider 提供更强原子提交/对账协议时才可简化，不得弱化未知结果语义 |

#### AG-1：HTTP/SSE 传输契约

- Control Plane 通过幂等 HTTP/JSON command 创建/恢复 Session、启动/取消 Run、响应审批和关闭 Session。
- Worker 通过 SSE 暴露按 `after_runtime_seq` 恢复的事件流；Control Plane 将事件规范化后写入 `RunEventLedger`，再通过 command API ACK `through_runtime_seq`；浏览器不直接连接 Worker。
- 每个 command 必须携带 `tenant_id / conversation_id / run_id / runtime_epoch / idempotency_key`；Worker 不把连接存活等同于 Run 存活。
- `events` 与 `terminal_result` 保持分离；SSE 结束、网络断开或 Worker 重启都不能推导 Run 已成功。
- 首期不采用裸 NDJSON 双向 RPC；审批、cancel、steer/follow-up 统一走 command API，事件统一走 SSE，避免两套重放语义。

#### AG-2：Runtime Cell 分级

共享 Worker 池只允许同时满足以下条件的任务：

- RuntimeProfile、自主等级和 Tool Policy 均判定为只读 L0/L1 模式。
- 文件系统只读或仅使用独立临时目录，网络访问仅经 allowlist/Tool Gateway。
- 不含业务写 Tool、租户长期凭证、自定义可执行代码或未受信 ACP Runtime。
- 每个 Run 有独立 WorkspaceLease、并发/CPU/内存/时间预算和 runtime epoch。

出现任一条件时进入独立 Runtime Cell：

- 任何业务写操作、文件持久化写入或高风险审批后执行。
- tenant policy、数据分类或监管要求需要专属故障域。
- 外部 ACP/自定义 Runtime 无法证明与平台相同的沙箱边界。
- 自定义 Tool/Skill 需要额外网络、文件或进程能力。

敏感租户默认 per-tenant Cell；一次性高风险任务可以 per-run Cell。Sandbox、挂载或网络策略不可用时拒绝启动，不降级到共享池。

#### AG-3：RunEvent payload、保留与归档

- PostgreSQL `RunEvent` 内联 payload 必须是已裁剪 JSON、大小 `<= 32 KiB`，且 classification 不高于 `internal`。
- 超过阈值、二进制、原始 Tool Result、文档正文以及 `confidential/restricted` 内容写对象存储；事件只保存 `payload_ref / sha256 / byte_size / content_type / classification / expires_at` 和安全摘要。
- 默认保留：RunEvent 热重放 90 天；Run 终态、Approval 决策、ToolCall 审计和 payload digest 365 天；Artifact/Evidence 按业务与租户保留策略执行。租户策略可以延长，但不能绕过法定或安全删除要求。
- 热重放期后，客户端只能读取已归档摘要和 Artifact/Evidence，不承诺逐 token/tool-progress 回放。
- 原始 Chain-of-Thought、密钥、数据库连接、长期 Token 和未裁剪敏感响应不进入 RunEvent 或日志。
- `(tenant_id, run_id, seq)` 必须唯一；外置失败时不得先提交指向不存在对象的事件。

#### AG-4：ToolGrant 与预算结算

- ToolGrant token 使用 CSPRNG 生成至少 256 bit 熵的 opaque value，只在签发时返回 Runtime；数据库保存 keyed digest/token hint，不保存明文。
- Grant 绑定 `tenant / actor / agent / run / runtime_epoch / tool_id+version / operation / resource constraints / purpose / risk / approval_revision / expires_at / max_calls / budget`。
- 默认 TTL 5 分钟，绝对上限 15 分钟；写操作 `max_calls=1`。只读 Grant 也必须有调用次数和成本上限，不签发 Conversation 级长期 Grant。
- Run terminal、cancel、runtime epoch 变化、审批过期/撤销、策略版本失效或预算耗尽时立即撤销；重放旧 token 稳定返回拒绝。
- 预算采用 `reserve -> execute -> reconcile -> settle/release`：Control Plane 在调用前原子预留，Gateway 按真实 usage 和对账结果结算；Worker 自报 token/cost 只做观测，不是计费事实源。
- 审批通过后签发匹配批准参数摘要的新 Grant，不扩大原 Grant 权限，不允许 Runtime 修改已批准参数后复用。

#### AG-5：首批 Pilot Rubric

| Pilot | 数据与执行方式 | 必须通过的安全/正确性门槛 | 质量与运营基线 |
|-------|--------------|---------------------------|----------------|
| APP-005 企业 360 背调 | 使用已有授权企业样例、真实 QCC/内部数据/QueryService；生产仍走 deterministic SkillRunner，Agent 只读对照 | 跨租户/越权调用 0；关键事实 100% 有 Evidence；制审分离和人工确认点 100% 保留；Agent 不写 DdTask/DdReport | 对比 schema 完整度、Evidence coverage、工具失败、人工干预、P50/P95、token/cost，不预设无数据依据的“准确率提升” |
| APP-009 AI 载体选址 | 一份真实企业需求、一个真实资产 Catalog、至少一个经 REQ-063 授权的地图/交通来源；只读 Agent Runtime | 推荐方案硬约束违反 0；外部关键指标 100% 带来源/时间/坐标与距离口径；至少 3 套方案；不自动锁房或写资产系统 | 记录可行方案率、排序稳定性、证据覆盖、工具失败、人工改权重次数、P50/P95、token/cost |

真实授权样例不足时，只能完成 contract/fixture 安全测试并标记 Pilot Blocked。首个真实样例用于建立基线，不发布无法回溯数据集和评分方法的聚合准确率。进入规模化生产前，由 APP Requirement 用代表性数据集另行冻结业务阈值。

APP-012/030 共用 REQ-062 的 Campaign/Form/Submission Rubric；APP-016 共用 REQ-063 的来源和研究证据 Rubric，不复制到首个 Runtime Gate。

#### AG-6：上下文所有权

首个实现 Slice 联合冻结、分开创建两个 bounded context：

| 上下文 | 拥有对象 | 禁止拥有 |
|--------|----------|----------|
| `agent_workspace` | Conversation、Message、会话命名/置顶/归档/删除/搜索和用户可见消息生命周期 | Runtime live handle、ToolGrant、Approval 状态机、业务报告字段 |
| `agent_execution` | AgentDefinitionVersion、RuntimeProfile、AgentRun、RunEvent、RuntimeSessionBinding、TurnInput、HumanInputRequest、ToolCall、ToolGrant、ModelGrant、ApprovalRequest、Artifact、EvidenceItem、运行 Snapshot 和执行策略 Port | Conversation 生命周期、长期 Memory、企业背调/选址/报表/研究领域状态 |
| `agent_memory`（后置） | MemoryItem、摘要/记忆治理和 Context 选择记录 | Conversation/Run 事实源、企业知识库本体 |

- REQ-041 与 REQ-047 在同一 contract-first 设计中确认 ID、删除/保留和终态关系，但按上下文分别实现与迁移。
- 两个上下文只通过 application port、稳定 ID 和显式 DTO 交互，不共享 ORM model/repository。
- `agent_execution` 必须先支持 DirectRagRuntime/SkillRuntime compatibility path，不等待 Pi Worker 才可验收。
- `ARCHITECTURE.md` 只在代码、迁移和运行单元真实落地时更新；本 Architecture Gate 仍是目标设计，不虚构现状。

#### AG-7：Turn Loop 入口与 Runtime 绑定

- 新 Agent Workspace 的每个用户输入先持久化 Message/TurnInput，再创建后台 AgentRun 并进入 `AgentTurnLoopRuntime`。
- Pi 是 V1 默认 RuntimeProfile；模型可以零 ToolCall 直接结束，也可以在同一 Loop 内调用受治理工具。
- 活动 Run 的普通新消息默认 queued 为下一 Run；用户显式 steer 才进入当前 Session actor queue。
- Runtime 追问使用 `HumanInputRequest`，高风险行动使用 `ApprovalRequest`；二者状态、权限和响应 API 分离。
- 更换 Runtime/Profile 创建新 `RuntimeSessionBinding`；不迁移 Pi、ACP、LangGraph 或其他 Runtime 的私有 checkpoint。
- 旧 `/ai/chat/evidence` 和确定性 Workflow 作为兼容入口保留，但不得被描述为新 Workspace 的复杂度旁路。

#### AG-8：Worker Event Spool 与写操作恢复

- Worker 先把事件写入本地 SQLite spool，再按单调 `runtime_seq` 发送；Control Plane 以 `(binding, epoch, runtime_seq)` 幂等落 PostgreSQL 后 ACK。
- PostgreSQL `RunEvent` 是唯一企业事件事实源；spool 只负责进程间至少一次投递，不承担租户查询、审计或长期保留。
- 写 Tool 固定按 `prepare -> approval -> reserve -> execute -> reconcile -> settle -> resume` 推进，审批精确绑定 ToolCall 和参数摘要。
- execute 后进程或网络失败时必须先按 provider idempotency key、状态接口或业务审计 reconcile；无法判定时进入 `outcome_unknown`，暂停 Run 且禁止盲重试。
- 无幂等键或可靠对账能力的写 Tool 只能暴露为 L2 Draft/Action Proposal。V1 不支持生产 `allow-always`。

### 15.3 完成后仍需外部输入

以下内容不改变 Architecture Gate，可作为独立 Requirement 的真实验收前置：

- APP-009 的企业需求样例、资产 Catalog 和地图/交通数据授权，由 REQ-063 source Spike 跟踪。
- APP-012 的首份统计要求、填报角色和输出格式，由 REQ-062 跟踪。
- APP-030 的真实展会、受邀招商人员和历史模板，由 APP-030 后续 Requirement 跟踪。
- APP-016 的真实产业研究课题、研究范式和授权来源，由 APP-016 后续 Requirement 与 REQ-063 跟踪。
- 上述输入缺失会阻塞对应 Pilot 的真实验收，不回退 REQ-059 的控制面架构决策，也不得用 mock 宣称业务 Pilot 完成。

## 16. 明确不做

- 不把旧 AI Chat 端点或确定性业务 Workflow 强制迁入 Agent Loop；新 Agent Workspace 统一 Turn Loop 是已冻结目标。
- 不用 GraphRAG 替代 Runtime/控制面；GraphRAG 只是可选 Retrieval Tool。
- 不让 Pi/ACP Session 取代 Conversation/Message。
- 不让 Runtime 直接调用租户数据库、MCP secret 或业务写 API。
- 不使用 `allow-all-tools`、`dangerously-skip-permissions`、默认 yolo、自动 confirm 或 sandbox degrade-to-off 作为生产配置。
- 不把企业背调字段、QCC 参数或报告 schema 写入平台通用实体。
- 不在本架构文档更新 `ARCHITECTURE.md` 并声称新上下文已落地；代码和迁移开始后再更新长期架构事实源。
