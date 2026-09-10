# REQ-042 WS-S2 / WS-S3 Contract-Shaping 报告（Phase 0）

> **Status**: 🟣 Shaping — Phase 0 audit + slicing plan（pure-spec / pure-docs，**不实现业务代码**）
> **Base**: `9fda8ae166c8ee924f986908fabb08d24bffe705`（main HEAD，PR #620 governance correction 已合入）
> **Requirement**: [REQ-042](../../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md)（status ⚫ Candidate）
> **Plan basis**: [REQ-041/047 Conversation/Run Durable Core 联合 plan](../../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md)（W1/E0/E1/B1/A1/D1/R1-S1..S6/C1 已合并）
> **作者任务卡**: TASK-REQ-042-WS-S2-CONTRACT-SHAPING（仅 docs/ + current-work.md，无业务代码改动）

## 0. 修订历史与本版裁决

| 版本 | commit | 事实状态 |
|------|--------|----------|
| 第一版 | `fe1ebce2` | 含多处事实错误（声称 `/turns` 已实 / `cancel body = {reason}` / SSE/cancel 后端未实 / 描述 WS-S2 mock-only + 真实 PG manual 矛盾 / REQ-017 typo） |
| 第一次纠偏 | `38164a8f` | 重写 §6.2 / §6.3 / §9.1 / §9.3；但 §4.2 / §4.3 / §7.1 / §10 / §11.2 仍残留第一版错误并与已纠正节矛盾（**三面独立只读复审判定不通过**） |
| 第二次纠偏（**本版**） | HEAD | 唯一产品路径 = WS-S2 real submit closure = **option B**；当前状态 = **BLOCKED**；§4 - §11 + §13 全文统一；删除所有 `option A 作为可立即开工的 WS-S2 implementation` 口径；option A 仅可作为公共 API 冻结后的 L1 mock contract experiment（非交付、非合并） |

**本版最终裁决**（与第一版 + 第一次纠偏并存过的 option A / option B 矛盾口径一致）：
- WS-S2 real submit closure 路径 = **option B**
- 当前状态 = **BLOCKED**（4 项硬门禁）
- WS-S2 不再有任何「可立即开工的 mini-slice」承诺
- WS-S2.A-E 重拆为**未来顺序**，全部 planning / 全部未启动
- WS-S2 frontend 任何 prototype 至多标记为 `non-deliverable / non-mergeable / L1 contract experiment`，不冒充 production submit
- Phase 0 仅完成审计 + 切片规划；WS-S2/WS-S3 implementation 均**未启动**

**历史错误引用（仅作修订说明保留，禁止在规范正文中出现）**：
- 第一版：错误声称 `POST /turns` 已实 + WS-S2 可立即开工 + L2 真实 PG dry-run for mock-only 等
- 第一次纠偏：仅修了 §6.2/§6.3/§9.1/§9.3 但保留 §4.2 错误 slice 表 + §4.3 错误 cancelRun(reason) + §7.1 L2 表 + §11.2 REQ-017 typo
- **本版**：上述残留全部纠正

## 1. 边界声明（先于一切内容）

本报告**仅做 Phase 0 审计 + 切片规划**，明确以下禁止项与本报告不构成开启任何实现的授权：

- ✗ **不实现 submit-turn** / 不开放发送按钮 / 不接 AgentTurnLoopRuntime / Pi / ACP / MCP Server
- ✗ **不实现 SSE/EventSource** / `after_seq` 重放 / cancel / stop / steer
- ✗ **不实现 Approval** / Tool / Artifact / Evidence / SkillRunner timeline / HumanInputRequest
- ✗ **不修改后端** / migration / schema / registry / CI / 门禁
- ✗ **不运行 `agent_erasure_backfill`** / 不修改 `erase_available` / 不触碰 `metaedu` 或 `metaedu_test`
- ✗ **不启动 REQ-043 / REQ-062 / REQ-063 / TD-085**
- ✗ **不把 REQ-042 翻 Done** / **不把 REQ-047 Extended 翻 Ready**
- ✗ **不处理 stale remote-tracking refs**
- ✗ **不修改 review-score-log.md 或 Metrics**

WS-S1 边界声明完整保留（PR #620 closeout + governance correction 已固化）：
- 真实 PG 正向 restore 仍不在 WS-S1 scope
- 普通新建会话缺少完整六-owner fence 时返回 409 是 fail-closed 设计意图
- AC-4 / AC-5 / AC-7 / AC-8 仍未完成

---

## 2. WS-S1 现状代码级盘点（真实路径，非声称）

### 2.1 路由 / Flag 门控（已落地）

| 项 | 代码路径 | 状态 |
|----|---------|------|
| 路由 `name: "agent-workspace"` + path `/agent-workspace` | [packages/web/src/app/router.ts:109-113](../../../packages/web/src/app/router.ts#L109) | ✅ |
| meta `featureFlag: "agent_workspace"` + `permission: "nav.ai_work"` | [router.ts:112](../../../packages/web/src/app/router.ts#L112) | ✅ |
| flag runtime check `featureFlags[meta.featureFlag] !== true → /403` | [nav.ts:201](../../../packages/web/src/app/nav.ts#L201) + [router.ts:270-280](../../../packages/web/src/app/router.ts#L270) | ✅ |
| sidebar 通过 nav.ts `featureFlags.known` 投影 | [nav.ts:86-107](../../../packages/web/src/app/nav.ts#L86) | ✅ |

**结论**：路由层 WS-S1 完成；WS-S2 不需改路由层（仅需在 nav.spec 业务 leaf 中确认 workspace 入口）。

### 2.2 三栏 Shell + 移动端 Tab（已落地）

| 项 | 代码路径 | 状态 |
|----|---------|------|
| 三栏 desktop grid（`grid-template-columns: 300px minmax(0, 1fr) 340px`） | [AgentWorkspaceView.vue:18-35](../../../packages/web/src/views/agent-workspace/AgentWorkspaceView.vue#L18) + style | ✅ |
| 中间断点 768-1279px 收窄侧栏 | [AgentWorkspaceView.vue:148-153](../../../packages/web/src/views/agent-workspace/AgentWorkspaceView.vue#L148) | ✅ |
| 移动端 <768px 抽屉/Tab（v-show 三面板切换） | [AgentWorkspaceView.vue:4-17](../../../packages/web/src/views/agent-workspace/AgentWorkspaceView.vue#L4) + tabs handler L78-81 | ✅ |
| Playwright desktop 1280×800 + mobile Pixel 5 视口测试 | [e2e/workspace-{desktop,mobile,shared}.spec.ts](../../../packages/web/e2e/)（7 unique / 9 CI） | ✅ |

**结论**：AC-6 desktop/mobile 布局已交付。WS-S2 不需改 shell。

### 2.3 Conversation 生命周期（已落地 + 测试覆盖）

| 能力 | 代码路径 | 状态 |
|-----|---------|------|
| 列 / 搜索（≥2 字防抖）/ 切换 tab（active / archived） | ConversationListPane.vue + [workspace.ts:83-126](../../../packages/web/src/stores/workspace.ts#L83) | ✅ |
| 新建（幂等 POST） | [agentWorkspace.ts:237-242](../../../packages/web/src/services/agentWorkspace.ts#L237) | ✅ |
| 重命名 / 置顶 / 取消置顶 | [agentWorkspace.ts:258-279](../../../packages/web/src/services/agentWorkspace.ts#L258) + `togglePin` [workspace.ts:300](../../../packages/web/src/stores/workspace.ts#L300) | ✅ |
| 归档 / 恢复 / 软删除（带 If-Match CAS） | [agentWorkspace.ts:281-313](../../../packages/web/src/services/agentWorkspace.ts#L281) + in-flight guard `archiveInFlight/restoreInFlight/deleteInFlight` [workspace.ts:309-353](../../../packages/web/src/stores/workspace.ts#L309) | ✅ |
| 按钮 `:disabled="store.{archive,restore,rename,delete}InFlight"` | MessageTimelinePane.vue:48-74 | ✅ |

**结论**：AC-1 [不含 restore] / 完整生命周期 UI + 持久化层（real PG）已交付。

### 2.4 Conversation Durable Read（已落地 + race GUARD）

| 能力 | 代码路径 | 状态 |
|-----|---------|------|
| `selectedId` GUARD：rapid A→B 切换时丢弃迟到的 A 响应 | [workspace.ts:148-157](../../../packages/web/src/stores/workspace.ts#L148) + [L165-178](../../../packages/web/src/stores/workspace.ts#L165) + [L189-204](../../../packages/web/src/stores/workspace.ts#L189) | ✅ |
| `messagesLoadingOlder` 切换重置（避免旧会话 guard 误拒新会话 load-older） | [workspace.ts:138](../../../packages/web/src/stores/workspace.ts#L138) | ✅ |
| `before_seq` / `after_seq` keyset 分页 | [agentWorkspace.ts:318-332](../../../packages/web/src/services/agentWorkspace.ts#L318) | ✅ |
| 消息 parts 渲染（text / resource_ref / redacted / superseded） | MessageTimelinePane.vue:115-167 | ✅ |

**结论**：AC-2 读半边（持久化 + 切换重置 + keyset 分页）已交付。

### 2.5 Run 三态 + 410 event_history_expired mapping（已落地）

| 能力 | 代码路径 | 状态 |
|-----|---------|------|
| 11 值 Run.status（queued/starting/running/waiting_input/waiting_approval/resume_required/cancelling/completed/failed/cancelled/expired） | [agentWorkspace.ts:88-100](../../../packages/web/src/services/agentWorkspace.ts#L88) | ✅ |
| 3 态分类（success / 404-403 / 410 event_history_expired / 409 tombstone） | [workspace.ts:227-261](../../../packages/web/src/stores/workspace.ts#L227) | ✅ |
| 410 → `runUnavailable=true`（诚实空态，不冒充错误） | [workspace.ts:243-255](../../../packages/web/src/stores/workspace.ts#L243) | ✅ |
| `selectedRunId` GUARD（rapid 切换丢弃迟到响应） | [workspace.ts:236/240](../../../packages/web/src/stores/workspace.ts#L236) | ✅ |
| 默认派生（首屏自动选中最新带运行引用的 run） | [workspace.ts:264-278](../../../packages/web/src/stores/workspace.ts#L264) | ✅ |
| RunDetailPane 显示 status / queue_seq / event window / log completeness / output_publish_state / usage | [RunDetailPane.vue](../../../packages/web/src/views/agent-workspace/panes/RunDetailPane.vue) | ✅ |

**结论**：Run 三态 + 410 mapping 已交付（基于真实 PG，real backend）。

### 2.6 草稿持久化（已落地）

| 能力 | 代码路径 | 状态 |
|-----|---------|------|
| tenant + owner(JWT sub) + conversation 三维隔离 | [workspaceDraft.ts](../../../packages/web/src/stores/workspaceDraft.ts) | ✅ |
| localStorage 镜像键含 scope | workspaceDraft.ts `getDraft(id)` / `setDraft(id, text)` | ✅ |
| 切换会话自动装载该会话草稿 | [WorkspaceComposer.vue:46-52](../../../packages/web/src/views/agent-workspace/panes/WorkspaceComposer.vue#L46) | ✅ |
| 未登录静默降级（不抛错） | workspaceDraft.ts try/catch 包裹 localStorage | ✅ |

**结论**：草稿恢复 AC 已实现。

### 2.7 发送按钮 disabled（明确非提交态）

**关键发现**：

```vue
<!-- WorkspaceComposer.vue:13-21 -->
<button
  class="ui-btn ui-btn-primary"
  :disabled="true"
  aria-disabled="true"
  title="发送功能将在后续版本开放"
  data-testid="ws-send-btn"
>
  <SendHorizontal :size="14" aria-hidden="true" /> 发送
</button>
```

**事实核对**：
- `:disabled="true"` 硬编码（无 v-bind 动态）
- 无 `@click` handler
- 无 form submit
- placeholder 文字「发送将在后续版本开放」明确告知
- aria-disabled 正确

**结论**：WS-S1 不开放发送功能（明确非提交态，无虚假成功反馈）。

### 2.8 WS-S1 显式未实现能力（事实清单）

| 能力 | WS-S1 状态 | 证据 |
|-----|----------|------|
| `POST /turns` / submit-turn / `submit-turn` HTTP endpoint | ❌ 未实现 | grep 全仓库无 `/turns` 路径；agentWorkspace.ts 第 19-20 行 WS-S1 边界明文声明 `submit-turn` 严禁 |
| `AgentTurnLoopRuntime` / Pi / ACP / MCP Server | ❌ 未接入 | 不在前端 DTO 范围；RunDetailPane 仅读 `getRun`（[agentWorkspace.ts:335-340](../../../packages/web/src/services/agentWorkspace.ts#L335)） |
| SSE / `EventSource` / `useEventSource` | ❌ 未启用 | [auto-imports.d.ts:181](../../../packages/web/src/auto-imports.d.ts) 含类型定义但零调用 |
| `after_seq` 重放 | ❌ UI 无消费者 | service `listMessages` 支持 after_seq 查询参数，但前端 store 只用 `before_seq`（向前加载历史），无 after_seq 重放路径 |
| Run cancel / stop / steer | ❌ 无 UI / 无 service | 无 `cancelRun` / `stopRun` / `steerRun` service 方法；RunDetailPane 无对应按钮 |
| ApprovalRequest / HumanInputRequest | ❌ 无 UI / 无 service | RunDetailPane 仅展示 `pending_approval_count: number`（仅数字呈现），无审批卡 / 无审批 endpoint |
| ToolCall / ToolGrant / SkillRunner | ❌ 无 UI | RunDetailPane 无 tool lifecycle 面板 |
| Artifact / EvidenceItem | ❌ 无 UI | RunDetailPane 无 artifact / evidence 面板 |
| Plan summary / Current phase | ❌ 无 UI | RunDetailPane 无 plan 渲染 |
| Thinking summary | ❌ 无 UI | RunDetailPane 无 thinking 显示 |
| RunEvent 时间线 | ❌ 无 UI | RunDetailPane 无 sequence 化 RunEvent 列表 |
| 持久化 draft restore / session 重连 | ✅ 部分（draft localStorage only） | 不涉及 RunEvent 持久化重连 |

---

## 3. WS-S1 已交付与未交付矩阵（vs REQ-042 AC-1..AC-8）

| AC | 描述 | WS-S1 状态 | 证据 / 缺口 |
|----|------|----------|------------|
| **AC-1** | 创建/切换/搜索/置顶/归档/删除 + 草稿不丢 | ✅ 已交付（不含 restore） | Conversation 生命周期 + workspaceDraft 三维隔离 localStorage；restore 持久化路径已 wire-up（service + store），但**仅 mock UI contract**（409 fail-closed）；非真实 PG 正向验证 |
| **AC-2 读半边** | 刷新/重进 durable read | ✅ 已交付 | Conversation + Message 真实 PG（REQ-041 W1/B1/A1）→ 刷新页面经 `selectConversation(id)` 重读；recently 完成修复轮 race GUARD |
| **AC-2 运行中能力** | 停止 / 刷新后从最后 seq 恢复 / 不重复渲染 | ❌ 未交付 | 0% — 无 submit-turn、无 SSE、无 after_seq 重放、无 cancel/stop |
| **AC-3** | 工具/审批/产物/证据结构化组件 | ❌ 未交付 | RunDetailPane 仅显示 Run metadata；无 Tool / Approval / Artifact / Evidence 组件 |
| **AC-4** | 审批展示范围/风险/参数摘要/过期不可重复提交 | ❌ 未交付 | REQ-047 Extended Contracts（HumanInputRequest / ApprovalRequest / ReviewerScope）未冻结 |
| **AC-5** | 不展示原始 CoT；thinking summary 平台批准 | ❌ 未交付 | 无 thinking 渲染；REQ-047 AC-11 + REQ-043 平台批准 thinking 待补 |
| **AC-6** | desktop 1280×800 + Pixel 5 中间断点 + Playwright | ✅ 已交付 | 三栏 grid + 中间断点 + 移动端 Tab；7 unique / 10 CI Playwright |
| **AC-7** | Direct RAG / SkillRunner / Agent Runtime 统一时间线协议 | ❌ 未交付 | 仅在旧 `/ai/chat/evidence` 兼容路径（[ai-chat/AiChatView.vue:372](../../../packages/web/src/views/ai-chat/AiChatView.vue#L372)）；新 Workspace 未引入统一 RunEvent 协议 |
| **AC-8** | 用户离开页面 Run 继续 + 显式 steer | ❌ 未交付 | 无 background Run、无 steer 交互；活动 Run 中普通消息排队 → 下一 Run 行为未实现 |

### 矩阵汇总

| 状态 | AC 数 | AC 编号 |
|------|------|--------|
| ✅ 已交付 | 3/8 | AC-1 [不含 restore] / AC-2 读半边 / AC-6 |
| ❌ 未交付 | 5/8 | AC-2 运行中能力 / AC-3 / AC-4 / AC-5 / AC-7 / AC-8 |

---

## 4. WS-S2 / WS-S3 切片推荐

### 4.1 WS-S1 vs WS-S2 vs WS-S3 边界（核心建议）

**关键判断**：
- **WS-S2**：发送按钮 + 真实 submit-turn 入口（最小化打开）+ Run 启动 + 短暂轮询终态（**不含 SSE**）
- **WS-S3**：SSE 事件流 + after_seq 重连 + cancel/stop/steer + 实时 RunEvent 时间线

**为什么不 WS-S2 包含 SSE**：REQ-047 Durable Core 已合并（PR #582 + #485 + #487 + #489 + #596 + #598 + #600 + #602 + #604 + #606 + #610 + #612 + #614 → C1 = Durable Core 完成）。但 V1 product enable 路径仍要求「客户端只连接 MetaEduBase API/SSE」（REQ-043 AC-11）。如果 WS-S2 直接含 SSE，意味着 WS-S2 完成时即可 production-enable 第一批 Runtime Profile，这违反 REQ-041 / REQ-043 的 contract-first 纪律。

**建议拆分原则**（按 contract-first）：
1. **WS-S2**：contract = submit-turn → poll 终态（短轮询，长 ≤ 30s）。这个 contract 已在 REQ-041 AC-4「Message 写入具备幂等键和 durable dispatch」+ REQ-047 A1「owner-private GET Run + 持久化幂等 cancel intent + PostgreSQL ledger SSE replay/live polling」中预先冻结。WS-S2 只是把这两个 contract 的前端消费者打开，不开放 Runtime。
2. **WS-S3**：contract = SSE event stream + after_seq replay + cancel intent + steer intent。依赖 Runtime SessionBinding 已 wiring（[REQ-043 AC-1](../../01-product-planning/05-requirements/REQ-043-runtime-neutral-agentic-rag-orchestration.md)）+ RuntimeProfileResolver 已写（E0 已合并）+ Capability Gate 已落（D1 已合并）。

### 4.2 WS-S2 切片（未来顺序，全部未启动）

> **状态**：WS-S2 implementation **当前 BLOCKED**（见 §9.1）。本节列出**未来顺序**，全部为 **planning**，**不代表已启动**。
>
> **产品路径裁决**：WS-S2 real submit closure = option B。必须等公共契约 + server-selected launch policy + 最小 execution profile 全部冻结才能开工。
>
> **历史错误清除**：第一版错误声称 "POST /turns backend 已实" / "WS-S2 可立即开工" / "修改 `:disabled="false"`" / "mock POST /turns 返回 201" / "WS-S2.E 真实 PG manual 验收" —— 全部删除（残留仅在 §0 修订历史 + §12 中保留作 honest 记录）。

**WS-S2 未来顺序（5 个 phase，全部未启动）**：

| WS-S2 phase | 目标 | 输入 | 输出 | 前置依赖（**硬门禁**） | 当前状态 |
|-------------|------|------|------|---------------------|---------|
| **WS-S2 phase-A** 公共 submit API + DTO + error contract 冻结 | contract-first 冻结：路径 / method / 鉴权 / owner isolation / 幂等重放 / 冲突码 / 能力门控 | REQ-041 W1 + B1 + REQ-047 Durable Core 已存在；内部 `submit_turn()` 已有 application contract | `POST /api/v1/agent-workspace/conversations/{id}/turns` 公开 spec 文档；`SubmitTurnRequest` / `SubmitTurnResponse` DTO；4xx/5xx error code 表（403 / 404 / 409 revision_conflict / 422 / 429 / 500） | ① 公共契约评审流程定义 ② REQ-042 §Acceptance 拆解（AC-2 运行中部分 + AC-8 Run 继续部分） | 🟣 **未启动** |
| **WS-S2 phase-B** server-selected launch policy + 最小 execution profile 冻结 | 冻结 `RuntimeProfileResolver` 选 profile 字段 + capability gate 字段 + `TurnLaunchSpecV1` 服务端构造路径 + 最小 execution profile（compatibility execution / system.direct_rag.v1 等） | REQ-043 Spec + REQ-047 Extended Contracts 已冻结 | `RuntimeProfileResolver` contract + `TurnLaunchSpecV1` 构造 contract + minimal execution profile 列表 | ① WS-S2 phase-A ② REQ-043 Spec 冻结 ③ REQ-047 Extended Contracts 三组 spec 冻结 | 🟣 **未启动** |
| **WS-S2 phase-C** backend route + 真实 PG contract tests | 把 `submit_turn()` application 公开化为 `POST /turns` route（router 登记）+ WS-S2 backend slice；写真实 PG 端到端 contract tests | WS-S2 phase-A 冻结的 spec | backend route 实装 + 真实 PG 端到端 contract tests（不变量：幂等重放、revision conflict、owner isolation、能力门控 fail-closed、ConversationExecutionGuard 串行化） | ① WS-S2 phase-A ② WS-S2 phase-B | 🟣 **未启动** |
| **WS-S2 phase-D** frontend service/store + guarded Composer enable | 前端 service / store wire-up；在 state=active 且 WS-S2 phase-A/B/C 后端可用时打开按钮：state=archived / state=deleted 仍 disabled | WS-S2 phase-A 公开 spec + WS-S2 phase-C 后端 route | `service/turns.ts` + store `submitTurnInFlight` ref + guard；Composer 根据 state 与 capability gate 动态 enabled/disabled；按钮 `:disabled` v-bind 不再硬编码 | ① WS-S2 phase-C ② WS-S2 phase-D 须配合独立 frontend slice PR | 🟣 **未启动** |
| **WS-S2 phase-E** mock + 真实 PG e2e + 用户手动验收 | e2e 闭环：mock route + 真实 PG；用户手动验收 10 项 | WS-S2 phase-D frontend 已实 | e2e tests + 手动验收报告 | ① WS-S2 phase-D | 🟣 **未启动** |

**WS-S2 禁止（不变）**：
- ✗ 不接 SSE / EventSource（WS-S2 不涉及 SSE；SSE 归 WS-S3）
- ✗ 不接 `AgentTurnLoopRuntime`
- ✗ 不实现 cancel / stop / steer
- ✗ 不开放 Runtime Profile 切换
- ✗ 不声称 mock-only pre-wire 作为 "WS-S2 implementation 启动"（最多标记为非交付、非合并、L1 contract experiment）
- ✗ 不修改 `/turns` endpoint contract（**endpoint 不存在**，不是已冻结；WS-S2 phase-A 才是冻结）
- ✗ 不修改 `expectedRevision` body schema（后端 `CancelRunRequest` 已冻结 = `{expected_revision: int}`）
- ✗ 不把 cancelRun body 写成 `{reason}`（**错的**）

### 4.3 WS-S3 切片（未来顺序，全部未启动）

> **状态**：WS-S3 implementation **当前 BLOCKED**（见 §9.3）。本节列出**未来顺序**，全部为 **planning**，**不代表已启动**。
>
> **后端现状（事实源 `router.py:376 / :397`）**：后端 SSE + cancel endpoint **已实现**（不属于 WS-S3 新增 endpoint）。
> - `POST /api/v1/agent-runs/{run_id}/cancel` body 字段 `CancelRunRequest = {expected_revision: int = Field(ge=1)}`（**不是 `{reason}`**）
> - `GET /api/v1/agent-runs/{run_id}/events` 支持 `after_seq` query + `Last-Event-ID` header + heartbeat + `url_token_forbidden` 拒绝 URL token
>
> **WS-S3 真正缺的**：前端消费层 + 结构化 UI + 浏览器 SSE 鉴权 transport（**不是后端 endpoint**）。

| WS-S3 phase | 目标 | 输入 | 输出 | 前置依赖（**硬门禁**） | 当前状态 |
|-------------|------|------|------|---------------------|---------|
| **WS-S3 phase-A** 浏览器 SSE 鉴权 transport 冻结 | 在 `fetch()+ReadableStream` / polyfill / 独立 stream_token 契约 三选一 中 contract-first 冻结（**原生 EventSource 不能设 Authorization header；后端已拒绝 URL token**） | 后端 SSE 已实 + url_token_forbidden | 单一 transport 契约（建议 fetch+ReadableStream 优先：不引入额外依赖、不破坏 SSE 自动重连语义由调用方自实现） | ① Transport 选型 contract-first 评审 | 🟣 **未启动** |
| **WS-S3 phase-B** `cancelRun(runId, expectedRevision)` frontend wire-up + UI | 前端 service + 按钮 + revision bump 失败 toast（不开放按钮当 state 非 active） | 后端 cancel endpoint 已实 + WS-S3 phase-A transport 冻结（共用 transport） | `service/runs.ts:cancelRun(runId, expectedRevision)` + RunDetailPane cancel 按钮（state guard：active / cancelling / terminal 三态分别禁用/启用/隐藏） | ① WS-S3 phase-A | 🟣 **未启动** |
| **WS-S3 phase-C** RunEvent Timeline + Structured Renderers (Plan / Tool / Evidence / Approval / Input / Artifact / Error / Terminal) | 类型化 RunEvent 渲染（结构化组件 ≠ 普通助手文本）；32 KiB 内联 + classification 外置边界 | WS-S3 phase-A transport 冻结 + WS-S3 phase-B 消费层路径 | 8 个结构化子组件 + timeline 父组件 | ① WS-S3 phase-A ② WS-S3 phase-B | 🟣 **未启动** |
| **WS-S3 phase-D** `steerRun` / `respondHumanInput` / `respondApproval` frontend + UI | 活动 Run 等待时显示结构化请求卡（HumanInput 与 Approval 分离）；过期不可重复提交；reviewer scope 显示 | REQ-047 HumanInputRequest + ApprovalRequest spec 已冻结 + 公共 endpoint 已实 | 三类 service + 三类 UI 卡 | ① WS-S3 phase-A ② REQ-047 Extended Contracts (HumanInput + Approval) 已冻结 ③ REQ-043 RuntimeSessionBinding 已 wired | 🟣 **未启动** |
| **WS-S3 phase-E** Artifact / Evidence Timeline + Thinking Summary 受控展示 | Artifact 版本链 + Evidence 血缘 + thinking summary 仅 plan/phase/tool/evidence/usage/error 摘要（不展示原始 CoT） | REQ-047 Artifact + EvidenceItem spec 已冻结 + endpoint 已实 | ArtifactCard + EvidenceCard + thinking-summary 渲染器 | ① WS-S3 phase-D ② REQ-047 Extended (Artifact + Evidence) 已冻结 | 🟣 **未启动** |

**WS-S3 禁止（不变）**：
- ✗ 不修改后端 SSE/cancel endpoint contract（已冻结；body 字段 `expected_revision` 不变）
- ✗ 不实现 Tool Gateway / ToolGrant 后端（归 REQ-043 Tool Gateway 切片）
- ✗ 不实现 Runtime Plan 算法（归 REQ-043 Runtime 中立 Runtime）
- ✗ 不修改 RunEvent schema（依赖 REQ-047 已冻结）
- ✗ 把 `new EventSource(url)` 写成可实施默认方案（**原生 EventSource 不能设 Authorization header**；须用 phase-A 冻结的 transport）

### 4.4 切片依赖图

**重要前提**：WS-S2 + WS-S3 全部 phase **当前均未启动**；下图为**未来顺序依赖图**，不是已开工的并行项目。

```
WS-S1 完成 ✅
  │
  ├─ WS-S2 phase-A 公共 submit API spec 冻结
  │   └─ WS-S2 phase-B server-selected launch policy + 最小 execution profile 冻结
  │       └─ WS-S2 phase-C backend route + 真实 PG contract tests
  │           └─ WS-S2 phase-D frontend service/store + guarded Composer enable
  │               └─ WS-S2 phase-E mock + 真实 PG e2e + 用户手动验收
  │
  └─ WS-S2 不依赖 REQ-043 Runtime 接入；WS-S2 真实 PG submit-loop
      仅依赖公共契约 + RuntimeProfileResolver + 最小 execution profile

REQ-047 Durable Core 🟢 Done + REQ-047 Extended Contracts 🟣 Shaping
  ├─ WS-S3 phase-A 浏览器 SSE 鉴权 transport 冻结
  │   ├─ WS-S3 phase-B cancelRun(runId, expectedRevision) wire-up + UI
  │   └─ WS-S3 phase-C RunEvent Timeline + Structured Renderers
  │       ├─ WS-S3 phase-D steerRun + HumanInput + Approval UI
  │       │   └─ WS-S3 phase-E Artifact + Evidence + Thinking Summary
  │       └─ WS-S3 phase-E (parallel after phase-D)
  └─ (depends on REQ-047 Extended Contracts 3 组 spec + REQ-043 Tool Gateway + TD-085)
```

---

## 5. REQ-043 / REQ-047 依赖与阻塞条件

### 5.1 REQ-043（Runtime 中立的 Agentic RAG 与工具编排）状态：⚫ Candidate

**对 WS-S2/WS-S3 的影响**：

| REQ-043 能力 | WS-S2 依赖 | WS-S3 依赖 | 阻塞条件 |
|------------|----------|----------|----------|
| AgentTurnLoopRuntime (initialize/create/resume session/start turn/ACK/cancel/close) | 不依赖（WS-S2 只调 submit + poll） | **强依赖**（WS-S3.A/C 需要 Runtime event protocol + cancel intent） | REQ-043 Spec 须冻结 Runtime conformance suite；V1 Pi Worker spike（REQ-043 AC-6）跑通 |
| RuntimeSessionBinding + RuntimeProfileResolver | 不依赖 | **强依赖**（WS-S3 启动 Run 须指明 RuntimeProfile） | REQ-043 AC-1「同一 Conversation 可切换 RuntimeProfile」 |
| Tool Gateway / ToolGrant | 不依赖 | **强依赖**（WS-S3.D 审批涉及 ToolCall） | REQ-043 Spec §Tool Gateway 冻结 + V1 Worker spike 集成测试 |
| HTTP command API + SSE event stream | 不依赖（WS-S2 用短轮询） | **强依赖**（WS-S3.A） | REQ-043 AC-11 |
| Agentic RAG Loop / Plan / Evidence | 不依赖 | **强依赖**（WS-S3.B/E） | REQ-043 Spec §Agentic RAG Loop 冻结 + REQ-047 Artifact/Evidence 冻结 |

**WS-S2 阻塞**：
- ✗ 无 — WS-S2 不依赖 REQ-043

**WS-S3 阻塞**：
- ✓ 必须等 REQ-043 Spec 冻结（contract-first 后可开工）
- ✓ 必须等 TD-085 Boundary Closure 中阻塞 Runtime 接线的依赖倒置切片完成

### 5.2 REQ-047（Agent Run / Artifact / Approval Center）状态：🟣 Shaping（Durable Core 🟢 Done）

**对 WS-S2/WS-S3 的影响**：

| REQ-047 切片 | 已合并 | WS-S2 依赖 | WS-S3 依赖 |
|-------------|--------|----------|----------|
| W1 Workspace durable store | ✅ PR #479 | 必需 | 必需 |
| E0 Execution identity/Binding/Snapshot | ✅ PR #481 | 必需 | 必需 |
| E1 Execution durable core | ✅ PR #483 | 必需 | 必需 |
| B1 Bidirectional outbox/inbox + bridge | ✅ PR #485 | 必需 | 必需 |
| A1 owner-private GET Run + ledger SSE | ✅ PR #487 | 必需（GET Run 路径） | 必需 |
| D1 Compatibility adapter for `/ai/chat/evidence` | ✅ PR #489 | 不依赖（旧入口） | 不依赖 |
| R1-S1..S6 retention/purge/recovery | ✅ | 不依赖（WS-S1 已使用 410 mapping） | 必需（cancel/expire 涉及） |
| C1 Durable Core bounded integration | ✅ PR #614 | 必需 | 必需 |
| **HumanInputRequest + ApprovalRequest spec** | 🟣 未冻结 | 不依赖 | **WS-S3.D 强依赖** |
| **ToolCall + ToolGrant + Snapshot spec** | 🟣 未冻结 | 不依赖 | **WS-S3.B/D/E 强依赖** |
| **Artifact + EvidenceItem spec** | 🟣 未冻结 | 不依赖 | **WS-S3.B/E 强依赖** |

**WS-S2 阻塞**：
- ✓ 不依赖 REQ-047 Extended Contracts（Durable Core 已足够支撑 submit + poll）

**WS-S3 阻塞**：
- ✓ 必须等 REQ-047 Extended Contracts 三组 spec 冻结：HumanInputRequest + ApprovalRequest / ToolCall + ToolGrant + Snapshot / Artifact + EvidenceItem
- 三组 spec 冻结后，WS-S3.D / WS-S3.B / WS-S3.E 可并行

### 5.3 推荐的依赖倒置顺序（避免 V1 阻塞）

**关键事实校正**：REQ-047 Extended Contracts 不是 WS-S2 的硬依赖；WS-S2 仅依赖公共契约 + RuntimeProfileResolver + 最小 execution profile（这些可能间接引用 REQ-043 字段，但 REQ-047 Extended 三组 spec 不阻塞 WS-S2）。

| 依赖类别 | 内容 | 谁阻塞 |
|---------|------|-------|
| **WS-S2 硬门禁** | ① 公共 submit API spec 冻结（鉴权 / owner isolation / 幂等重放 / 冲突码 / 能力门控） ② server-selected launch policy 冻结 ③ 最小 execution profile 契约 ④ backend route + 真实 PG contract tests | ① ② ③ 是 contract-first 任务（独立 PR）；④ 是 backend slice（独立 PR） |
| **WS-S2 soft 依赖** | REQ-041 Durable Core（已合）/ REQ-047 Durable Core（已合）/ WS-S1（已合） | 全部已合，无阻塞 |
| **WS-S3 硬门禁** | ① 浏览器 SSE 鉴权 transport 冻结 ② REQ-047 Extended 三组 spec 冻结（HumanInput + Approval / ToolCall + ToolGrant + Snapshot / Artifact + Evidence） ③ REQ-043 Runtime conformance spec + Tool Gateway spec 冻结 ④ REQ-043 RuntimeSessionBinding + RuntimeProfileResolver 实装 ⑤ TD-085 依赖倒置切片 | ① contract-first 独立 PR；② ③ ④ ⑤ 都是 contract / refactor 类 PR |
| **WS-S3 soft 依赖** | REQ-047 Durable Core（已合） | 全部已合，无阻塞 |
| **历史错误校正** | 第一版 + 第一次纠偏 写 "WS-S2 立即可开工（无 spec blocker，仅依赖 Durable Core）"——**错的**。WS-S2 当前真实状态 = BLOCKED（4 项硬门禁） | 全文禁止再出现"WS-S2 可立即开工"表述 |

**建议顺序（contract-first）**：
```
1. WS-S2 phase-A 公共 submit API spec 冻结（contract-first PR）
2. WS-S2 phase-B server-selected launch policy + 最小 execution profile 冻结（contract-first PR；可能引用 REQ-043 字段，但 REQ-047 Extended 不阻塞此步）
3. WS-S2 phase-C backend route 实装 + 真实 PG contract tests（独立 backend slice PR）
4. WS-S2 phase-D frontend service/store + guarded Composer enable（独立 frontend slice PR）
5. WS-S2 phase-E mock + 真实 PG e2e + 用户手动验收
6. WS-S3 phase-A 浏览器 SSE 鉴权 transport 冻结
7. WS-S3 phase-B cancelRun wire-up
8. WS-S3 phase-C RunEvent Timeline + Renderers
9. WS-S3 phase-D + phase-E（依赖 REQ-047 Extended 三组 spec）
```

---

## 6. API / DTO / Event Protocol / State Machine / Persistence 边界

### 6.1 现有契约（WS-S1 已消费）

| 契约 | 事实源 | WS-S1 消费方式 |
|-----|--------|--------------|
| `ConversationDTO` 11 字段 | [agentWorkspace.ts:50-62](../../../packages/web/src/services/agentWorkspace.ts#L50) | 仅 GET / PATCH |
| `MessageDTO` + `MessagePartDTO` | [agentWorkspace.ts:64-87](../../../packages/web/src/services/agentWorkspace.ts#L64) | 仅 GET，分页 keyset |
| `AgentRunDTO` 28 字段 | [agentWorkspace.ts:104-138](../../../packages/web/src/services/agentWorkspace.ts#L104) | 仅 GET 终态事实 |
| `RunStatus` 11 值 | [agentWorkspace.ts:88-100](../../../packages/web/src/services/agentWorkspace.ts#L88) | 状态映射 + 410 三态分类 |
| `OutputPublishState` 5 值 | [agentWorkspace.ts:102](../../../packages/web/src/services/agentWorkspace.ts#L102) | RunDetailPane 显示 |
| HTTP error 语义 | [agentWorkspace.ts:189-220](../../../packages/web/src/services/agentWorkspace.ts#L189) `parseApiError` | 404-403 / 409 / 410 mapping |
| `TERMINAL_RUN_STATUSES` | [agentWorkspace.ts:144-148](../../../packages/web/src/services/agentWorkspace.ts#L144) | `completed/failed/cancelled/expired` |
| Restore 持久化 endpoint + `event_history_expired` 错误码 | [agentWorkspace.ts:293-303](../../../packages/web/src/services/agentWorkspace.ts#L293) + REQ-047 R1-S6 (410 event_history_expired) | 仅 mock UI contract；非真实 PG 验证 |

### 6.2 WS-S2 现状（事实纠偏后）

**关键事实（事实源 `packages/server-python/app/`）**：

1. **公开 `POST /agent-workspace/conversations/{id}/turns` 路由不存在**：
   - `packages/server-python/app/contexts/agent_workspace/interfaces/api/router.py` 仅注册 8 个 endpoint（`listConversations` / `createConversation` / `getConversation` / `patchConversation` / `pin / unpin / archive / restore / delete / messages`），**无 `/turns`**
   - `packages/server-python/app/contexts/agent_workspace/application/bridge.py:160` 有 `async def submit_turn(...)` — 这是 **internal application method**，被 `agent_control_plane.py:238` 与 `direct_rag_compatibility.py:207` 组件层调用，**不是 public API**
   - `test_workspace_api.py:277` `test_b1_registers_guarded_delete_but_keeps_submit_turn_route_closed` 与 `test_run_api.py:902` `test_a1_registers_run_routes_without_opening_workspace_submit_turn` 两测试明确断言 public `/turns` 路由保持关闭
   - REQ-041 AC-7「它不得消费新 Workspace submit-turn，新 Agent Workspace 的统一 Turn Loop 语义由 REQ-043 承接」

2. **后端 `submit_turn()` 已有 application contract**（仅 internal 使用，**禁止直接当公共 DTO**）：
   - `TurnCommand`（[dto.py:48-55](../../../packages/server-python/app/contexts/agent_workspace/application/dto.py)）：`client_message_id: UUID`, `parts: tuple[MessagePartInput, ...]`, `agent_definition_version_id: UUID`, `client_options: dict[str, Any]`
   - `TurnLaunchSpecV1`（[agent_integration.py:65+](../../../packages/server-python/app/shared/schemas/agent_integration.py)）：**server-selected immutable execution inputs** — `agent_definition_version_id`, `runtime_profile_id`, `runtime_binding_id`, `runtime_capability_snapshot`, `run_config_snapshot`, `context_snapshot_ref/digest/classification`, `budget_snapshot`
   - `SubmitTurnReceipt`（[bridge.py:64+](../../../packages/server-python/app/contexts/agent_workspace/application/bridge.py)）：`reserved: ReservedUserTurn`, `event_id: UUID`, `correlation_id: UUID`, `dispatch_state: TurnDispatchState`

3. **server-selected 字段不可由前端填**：
   - `runtime_profile_id` / `runtime_binding_id` / `runtime_capability_snapshot` / `run_config_snapshot` / `budget_snapshot` 全部由 server 端 RuntimeProfileResolver / Capability Gate 解析后选定
   - 前端即使 wire-up service 层也无法构造合法 TurnLaunchSpecV1（必须等待 server 端解析）
   - 在 REQ-043 RuntimeProfileResolver spec + REQ-047 Extended Contracts（ToolGrant / BudgetSnapshot 字段）冻结之前，前端不可自行补默认值

4. **dispatch 路径需要 Runtime**：
   - `submit_turn()` 走 composition Coordinator → RuntimeProfileResolver → Runtime（暂未接入）→ TerminalOutputReader
   - 没有可消费 dispatch 的 Runtime 时，Run 不会经 `queued → running → completed`
   - 「提交 + 轮询但不依赖 Runtime」方案不可行（composition 层会因 Runtime Profile 未安装 fail closed）

**结论**：WS-S2 真实提交闭环**被阻塞**，依赖以下全部完成：

| 依赖 | 阻塞原因 | 状态 |
|------|---------|------|
| **WS-S2 phase-A**：公共 submit API spec 冻结（鉴权 / owner isolation / 幂等重放 / 冲突码 / 能力门控） | 当前仅 internal application method；router 无 `/turns` | 🟣 未冻结 |
| **WS-S2 phase-B**：server-selected launch policy spec（RuntimeProfileResolver + Capability Gate 字段）+ 最小 execution profile 契约 | REQ-043 仍 ⚫ Candidate；REQ-047 Extended ToolGrant / BudgetSnapshot 字段未冻结 | 🟣 未冻结 |
| **WS-S2 phase-C**：backend route + 真实 PG contract tests | 依赖 phase-A + phase-B | 🟣 阻塞 |
| **WS-S2 phase-D**：frontend service/store + guarded Composer enable | 依赖 phase-C；按钮状态绑定 capability gate | 🟣 阻塞 |
| **WS-S2 phase-E**：mock + 真实 PG e2e + 用户手动验收 | 依赖 phase-D | 🟣 阻塞 |

**历史错误清除**：第一版 + 第一次纠偏 写 "WS-S2 仍可做的范围（option A：纯前端 mock 预接线）" 列表（含 service stub + Composer draft + pollRunUntilTerminal 等"可做"项）——**错的**。第一版 + 第一次纠偏 写 "WS-S2 DTO 草案（仅当前端 typed stub 形态）" ——**错的**：未冻结公共 API 时前端 typed stub 会冒充 server contract。

**当前文件唯一允许出现的 WS-S2 范围**：5 个 phase 全部 planning / 全部未启动。任何声称 "WS-S2 mini-slice 可执行" "WS-S2 frontend service 可 wire-up" "WS-S2 producer stub" "WS-S2 mock closed loop" 等表述均须删除。

### 6.3 WS-S3 现状（事实纠偏后）

**关键事实（事实源 `packages/server-python/app/contexts/agent_execution/interfaces/api/router.py`）**：

1. **`POST /agent-runs/{run_id}/cancel` 已实现**（[router.py:376](../../../packages/server-python/app/contexts/agent_execution/interfaces/api/router.py#L376)）：
   - `CancelRunRequest` body 字段（[router.py:50-53](../../../packages/server-python/app/contexts/agent_execution/interfaces/api/router.py#L50)）：
     ```python
     class CancelRunRequest(BaseModel):
         model_config = ConfigDict(extra="forbid")
         expected_revision: int = Field(ge=1)
     ```
   - **body 是 `{expected_revision: int}`，不是 `{reason: string}`**（用户原报 `{reason}` 错）

2. **`GET /agent-runs/{run_id}/events` SSE 已实现**（[router.py:397](../../../packages/server-python/app/contexts/agent_execution/interfaces/api/router.py#L397)）：
   - 支持 `after_seq` query param（`Annotated[int | None, Query(ge=0, le=_MAX_EVENT_SEQ)]`）
   - 支持 `Last-Event-ID` HTTP header
   - heartbeat interval（`_HEARTBEAT_INTERVAL_SECONDS` + `yield b": heartbeat\n\n"`）
   - 显式拒绝 URL token query params（`url_token_forbidden` 400 错误）
   - cursor 解析 `_resolve_after_seq(after_seq, last_event_id)` 同时校验两个来源一致

3. **WS-S3 真正缺的是「前端消费」与「结构化 UI」**（不是后端路由）：
   - WS-S1 frontend 仅消费 `GET /agent-runs/{id}` 终态事实（[agentWorkspace.ts:335-340](../../../packages/web/src/services/agentWorkspace.ts#L335)），**未消费 SSE event stream**
   - **RunEvent 类型化子组件不存在**：RunDetailPane 仅显示 metadata，无 PlanCard / ToolCard / EvidenceCard / ApprovalCard / InputCard / ArtifactCard / ErrorCard / TerminalCard 结构化渲染
   - **cancel/stop/steer UI 不存在**：WS-S1 未实现 `cancelRun` / `stopRun` / `steerRun` frontend service（grep 全仓库 service 仅 `getRun`，无 `cancelRun`/`steerRun`）
   - **Approval/HumanInput 卡组件不存在**：WS-S1 RunDetailPane 仅显示 `pending_approval_count: number`（仅数字呈现），无审批卡 / 人类输入卡

4. **WS-S3 浏览器 SSE 鉴权问题**（未在前端层解决）：
   - 后端 SSE endpoint 要求 Authorization Bearer（`_identity(current_user)` 依赖 `get_current_user`，与普通 endpoint 同样的鉴权）
   - **原生 `EventSource` 无法设置 `Authorization` header**；前端代码 `useEventSource` 仅类型定义（[auto-imports.d.ts:181](../../../packages/web/src/auto-imports.d.ts)），零调用
   - **后端拒绝 URL query token**（`url_token_forbidden`），所以 query token 方案被排除
   - **可行 transport**（contract-first 须冻结）：
     - (a) `fetch()` + ReadableStream 手动解析 SSE 帧（带 Authorization header）；缺点：失去 EventSource 自动重连，需自实现
     - (b) polyfill（如 `eventsource` npm 包 + 拦截 header） — 增加依赖
     - (c) 独立鉴权契约 — 例如短时 `stream_token` 走单独 endpoint
   - **未裁决前不得把 `new EventSource(url)` 写成可实施方案**

**WS-S3 仍需新增/冻结的 contract（前端消费层）**：

| 能力 | 状态 | 依赖 |
|------|------|------|
| `useRunEventStream(runId, { afterSeq, abortSignal })` composable | 🟣 未实现（前端无 SSE transport） | 浏览器 SSE 鉴权 transport 冻结（见上） |
| `pollRunUntilTerminal` 替代 / 辅助 | ✅ 已存在 `getRun` | 无 |
| `cancelRun(runId, expectedRevision)` | 🟣 后端已实 / 前端未消费 + UI 不存在 | 按钮 + DTO alignment |
| `steerRun(runId, content, idempotencyKey)` | ❌ 后端未实 + 前端 UI 不存在 | REQ-043 AC-16 + REQ-047 spec |
| `respondHumanInput(inputId, answer)` | ❌ 后端未实 + 前端 UI 不存在 | REQ-047 HumanInputRequest spec |
| `respondApproval(approvalId, option, idempotencyKey)` | ❌ 后端未实 + 前端 UI 不存在 | REQ-047 ApprovalRequest spec |
| `fetchArtifact(artifactId)` / `fetchEvidence(evidenceId)` | ❌ 后端未实 + 前端 UI 不存在 | REQ-047 Artifact/Evidence spec |

**RunEvent schema**（REQ-047 已冻结，事实源 [REQ-047 §Scope](../../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)）：
- 类型：phase / plan summary / tool lifecycle / evidence / input / approval / artifact / retry / usage / error / terminal
- `(tenant_id, run_id, seq)` 唯一且 seq 单调递增
- 32 KiB 内联边界 + classification 不高于 `internal`
- 大/二进制/敏感 payload 外置

### 6.4 状态机（WS-S2/WS-S3 新增意图）

```
[Active Run]
   │
   ├─ WS-S2.C: 普通 submit-turn → state=queued → POST /turns → Run 启动
   │
   ├─ WS-S3.C: cancel intent → state=cancelling → POST /cancel
   │     │
   │     ├─ outcome=succeeded → state=cancelled
   │     ├─ outcome=failed → state=cancelled
   │     └─ outcome_unknown → state=resume_required（不允许 → cancelled）
   │
   └─ WS-S3.C: steer intent → 普通消息在 queued state 排队到下一 Run
                 显式 steer → 注入当前 running Run（仅 Runtime 内）
```

### 6.5 持久化边界

| 数据 | WS-S2 | WS-S3 | 后端归属 |
|-----|-------|-------|---------|
| `TurnInput.message_id` | 必需（幂等键） | 必需 | REQ-041 Conversation/Message |
| `TurnInput.run_id` | 必需（poll target） | 必需 | REQ-047 AgentRun |
| `RunEvent` SSE hot-replay | 不需（用 GET Run 终态） | 必需（90 天默认） | REQ-047 RunEvent ledger |
| `ToolGrant` 256-bit 熵 opaque token | 不需 | WS-S3.D 必需 | REQ-043 Tool Gateway |
| `ApprovalRequest` revision / runtime_epoch | 不需 | WS-S3.D 必需 | REQ-047 ApprovalRequest |
| Compose draft localStorage | 必需（已有 workspaceDraft） | 沿用 | 前端仅 |
| Conversation restore 真值（6 owner fence） | 不需 | 不需 | REQ-047 R1-S6 已落；WS-S2/WS-S3 仅消费 |

---

## 7. 证据等级（fake Runtime vs 真实 Runtime vs 真实 PG）

**本 Phase 0 报告当前最高已验证层级**：

| 验证场景 | 最高层级 | 状态 |
|---------|---------|------|
| 静态代码审计 + 后端契约事实核对 | **L0** | ✅ 本报告 |
| 后端已有 endpoint 真实 PG 端到端（WS-S1 已消费 GET Run / 真实 PG / 真实会话） | **L2**（属历史 REQ-041/047 PR） | ✅ 既有证据，不属 WS-S2/WS-S3 |
| front-end wire-up 不依赖新 contract | L1 mock（仅在 contract-first PR 内） | 🟣 未启动 |
| 真实 PG submit-loop 端到端 | **L2** | 🟣 **必须等 WS-S2 phase-C/D/E 完成** |
| 真实 LLM 接入 | **L3** | 🟣 归 REQ-043 Pi Worker V1 spike |

### 7.1 各 Slice 的最高已验证层级（**当前所有 slice 均为 planning，最高已验证层级只能为 L0 静态审计**）

| Slice | 当前状态 | 未来验收门禁（**严禁冒充当前可做**） |
|------|---------|--------------------------------------|
| WS-S2 phase-A | 🟣 未启动 | 公共契约评审通过（L0 → L1 doc-review） |
| WS-S2 phase-B | 🟣 未启动 | server-selected launch policy spec 评审通过 |
| WS-S2 phase-C | 🟣 未启动 | backend route + 真实 PG contract tests pass（L2） |
| WS-S2 phase-D | 🟣 未启动 | frontend wire-up + unit tests + guarded Composer enable |
| WS-S2 phase-E | 🟣 未启动 | mock e2e + 真实 PG submit-loop + 用户手动验收 10 项（L2 真实 PG dry-run） |
| WS-S3 phase-A | 🟣 未启动 | 浏览器 SSE 鉴权 transport spec 评审 |
| WS-S3 phase-B | 🟣 未启动 | cancelRun wire-up + revision bump test |
| WS-S3 phase-C | 🟣 未启动 | 8 个结构化 RunEvent 子组件 + timeline 父组件 + SSE 消费 e2e |
| WS-S3 phase-D | 🟣 未启动 | HumanInput + Approval UI + revision bump |
| WS-S3 phase-E | 🟣 未启动 | Artifact + Evidence + Thinking Summary |

**关键声明**：
- **本 Phase 0 报告仅完成 L0 静态代码审计 + 未来切片规划**
- mock 可作为**已冻结公共契约的 e2e 工具**（contract-first PR 内部），**禁止作为 WS-S2 真实提交闭环的"已交付证据"**
- L1 mock / L2 真实 PG / L3 真实 LLM 只能写成**未来验收门禁**，**禁止冒充当前已通过**
- WS-S2 / WS-S3 收口时须按上表显式声明"达到 L2 真实 PG dry-run"或"L3 真实 LLM 接入"；当前报告无任何 L1+ 证据

**历史错误清除**：
- 第一版 + 第一次纠偏 写 "WS-S2.E = L2 真实 PG dry-run + 手动用户测试 10 项" ——**错的**，因为当前 WS-S2 phase A-E 全部未启动
- 第一次纠偏 "Mock 仅作 UI contract 验证；最高已验证层级为 L1 mock；WS-S2.E 手动验收为 L2 真实 PG dry-run" —— 错的：mock 可到 L1 是通用事实，但 WS-S2.E 写"已是 L2 真实 PG dry-run"是冒充未来状态
- 本版统一：本 Phase 0 报告最高 L0；未来 L1/L2/L3 验证门禁按上表登记
| **REQ-043 Runtime V1 enable** | **真实 Pi Worker + 真实 PG** | **L3 真实 LLM 接入** | **独立后续 REQ-043 PR；不在 WS-S3 范围** |

### 7.2 关键声明

- **WS-S2 完成 ≠ production enable**：submit-turn endpoint 开放 + 短轮询 GET Run 闭环仅证明「用户输入可触达 Run 启动」+ 「Run 终态可观察」。**真实 Runtime / 真实 LLM / 真实 Agentic RAG 行为不在 WS-S2 范围**。
- **WS-S3 完成 ≠ Runtime production enable**：SSE + cancel/steer + 结构化 Timeline 仅证明「UI 能消费 Runtime 事件流」。**Tool Gateway / RuntimeSessionBinding / RuntimeProfile adapter V1 enable 仍在 REQ-043 范围**。
- **最高已验证层级声明**：WS-S2/WS-S3 收口时显式声明「L2 真实 PG dry-run（手动验收）」；L3 真实 LLM 接入需独立 REQ-043 PR 收口后声明。

### 7.3 与现有 precedent 对齐

- REQ-041 D1（PR #489）已用 L2 真实 PG dry-run 收口，模式相同
- REQ-047 C1（PR #614）已用 L2 bounded integration 收口，模式相同
- 真实 LLM 接入（REQ-043 V1 Pi Worker）属于独立后续，本报告不预设其范围

---

## 8. 每个 Slice 的测试矩阵 + 手动验收路径

**重要前提**：所有测试矩阵描述的是**未来验收门禁**，**不是当前可执行的测试任务**。当 WS-S2/WS-S3 phase 实际启动时，按对应行实施；当前所有 phase 未启动，**不得写"测试已通过"或"已跑过"**。

### 8.1 WS-S2 未来测试矩阵（全部 🟣 未启动）

| Phase | unit (vitest) | e2e (Playwright) | 手动验收（仅 phase-E） | mutation harness |
|------|--------------|------------------|---------|------------------|
| phase-A 公共契约冻结 | **L1 doc-review**：评审纪要；非代码测试 | — | — | — |
| phase-B launch policy spec | **L1 doc-review** | — | — | — |
| phase-C backend route + 真实 PG contract tests | 集成测试：幂等重放 / revision conflict / owner isolation / capability gate fail-closed / ConversationExecutionGuard 串行化 | — | — | N/A |
| phase-D frontend wire-up | submitTurnInFlight guard；409 transparent 抛出；state guard（archived / deleted 仍 disabled） | 按钮 enabled 流 + 按钮 disabled 流（state guard） | — | N/A |
| phase-E e2e + 真实 PG dry-run | — | mock route（仅当公共契约冻结后） + 真实 PG e2e | 10 项用户场景：创建 → 输入 → 发送 → 看到 message → 看到 run 终态；归档后无法发送；删除后无法发送；非 archived 状态正常；网络错误 toast；超时 30s 提示 | — |

### 8.2 WS-S3 未来测试矩阵（全部 🟣 未启动）

| Phase | unit | e2e | 手动验收 | mutation |
|------|------|-----|---------|---------|
| phase-A SSE transport | useRunEventStream reconnection；gap detection；abort；connection timeout；multi-mount no duplicate connection | mock SSE 流 | — | N/A |
| phase-B cancelRun wire-up | revision bump 失败 toast；state guard；按钮 disabled for terminal states | mock cancel 流 | — | N/A |
| phase-C RunEvent timeline | 8 个结构化子组件（Plan / Tool / Evidence / Approval / Input / Artifact / Error / Terminal）独立渲染 | mock SSE → 事件类型分发 | — | N/A |
| phase-D HumanInput + Approval UI | 分离组件；revision bump 拒绝旧 revision；过期原子取消未执行 ToolCall | mock input/approval respond 流 | — | N/A |
| phase-E Artifact + Evidence + Thinking Summary | ArtifactCard 版本链；EvidenceCard 血缘；thinking summary 严格按 REQ-047 §Scope 边界 | mock artifact/evidence events | — | N/A |

### 8.3 手动验收路径（**仅 WS-S2 phase-E 适用**，当前未启动）

> **重要前提**：手动验收必须等 WS-S2 phase-A/B/C/D 全部完成 + phase-E mock e2e 全部 pass 之后才能开始；**当前**WS-S2 phase 全部未启动。

**假设 WS-S2 phase-E 启动时**（当前未启动）：

```
用户场景 1：active 会话提交 turn
  1. 进入 /agent-workspace?c=conv-1
  2. Composer 输入 "test"
  3. 点发送（按钮须按 state guard 启用）
  4. 看到 message 出现在 timeline
  5. 右栏自动派生 run（queued → running → completed）
  6. 看到 run status 终态事实（status / queue_seq / event window）

用户场景 2：archived 会话提交应被阻止
  1. 归档会话
  2. Composer 应 disabled（state=archived guard）
  ...
```

> 按钮在 option B 的 backend + execution 前置**全部通过前**始终 disabled（**不依赖 mock-only pre-wire**）。

---

## 9. 「可以开始实现」的门禁条件

### 9.1 WS-S2 真实提交闭环（**当前 BLOCKED**）

**事实纠偏后裁决：WS-S2 真实提交闭环被阻塞**（**唯一产品路径 = option B**），理由：

| 阻塞项 | 现状 | 启动所需 |
|--------|------|---------|
| WS-S2 phase-A 公共 submit API spec 冻结 | ❌ router 仅 8 个 endpoint（listConversations / createConversation / getConversation / patchConversation / pin / unpin / archive / restore / delete / messages），**无 `/turns`** | 独立 contract-first PR + 评审通过 |
| WS-S2 phase-A 双测试断言 | ❌ `test_b1_registers_guarded_delete_but_keeps_submit_turn_route_closed` + `test_a1_registers_run_routes_without_opening_workspace_submit_turn` 明确断言 `submit-turn` 路由保持关闭 | phase-A spec 冻结后 router 登记 + 测试改写 |
| `submit_turn()` 公开化（router 登记 + WS-S2 backend slice） | ❌ 当前 router 无 `/turns`；仅 internal application method 被 `bridge.py:160` / `agent_control_plane.py:238` / `direct_rag_compatibility.py:207` 调用 | ① WS-S2 phase-A spec 冻结 ② WS-S2 phase-B launch policy + execution profile 冻结 |
| `CancelRunRequest` body schema | ✅ 已冻结 = `{expected_revision: int = Field(ge=1)}`（**不是 `{reason}`**；不要写错） | n/a（已冻结） |
| `TurnCommand` / `TurnLaunchSpecV1` / `SubmitTurnReceipt` application DTO | ✅ 已冻结 application 内部 DTO，但**前端不可构造** TurnLaunchSpecV1（server-selected 字段） | n/a（已冻结 internal；公共 submit API DTO 须独立 contract-first） |
| RuntimeProfileResolver / server-selected launch policy | ❌ REQ-043 仍 ⚫ Candidate | 独立 REQ-043 Spec 冻结 PR |
| 最小 execution profile（compatibility execution）contract | ❌ REQ-047 Extended 🟣 Shaping | 独立 REQ-047 Extended Spec 冻结 PR |
| 真实 PG submit + Run 启动 + 终态可达 | ❌ 全部依赖以上 | phase-C backend slice 完成 |

**option A（mock-only pre-wire）合同裁决**：
- WS-S2 frontend prototype 至多标记为 `non-deliverable / non-mergeable / L1 contract experiment`
- **不得作为"WS-S2 implementation 启动"**
- 不得写入 option A "WS-S2.A 立即可开工" / "backend 已实 /turns endpoint"
- 按钮**保持 disabled**直到 phase-A/B/C/D 后端 + execution 前置**全部通过**

**WS-S2 启动门禁（option B 完整闭环，须全部满足才能启动 implementation）**：
- [ ] WS-S2 phase-A 公共 submit API spec 冻结（鉴权 / owner isolation / 幂等重放 / 冲突码 / 能力门控 / 真实 PG 端到端测试 spec）
- [ ] WS-S2 phase-A 公共 `/turns` backend slice（router 登记 + WS-S2 backend implementation；含 phase-A 测试改写）
- [ ] WS-S2 phase-B server-selected launch policy spec 冻结（RuntimeProfileResolver 字段 + capability gate 字段）
- [ ] WS-S2 phase-B 最小 execution profile contract（compatibility execution / system.direct_rag.v1 等）
- [ ] WS-S2 phase-C backend route + 真实 PG contract tests pass
- [ ] WS-S2 phase-D frontend slice PR（含按钮状态绑定 capability gate）
- [ ] WS-S2 phase-E mock + 真实 PG e2e + 用户手动验收
- [ ] 独立三面复审 + 评分 ≥ 80 + 必修 follow-up = 无
- [ ] **不要求** mock-only pre-wire 单独 slice（与历史 option A 路径断开）

**历史错误校正**：本报告之前 写"WS-S2 仍可做的范围（option A：纯前端 mock 预接线）" 表格（含 service stub + Composer draft + pollRunUntilTerminal + DTO 草案）——**全部删除**。任何"WS-S2 frontend service 可 wire-up" / "WS-S2 producer stub 可实现" / "WS-S2 mock closed loop" 表述均**禁止**出现。

**禁止声称口径**：
- ✗ 禁止说 "WS-S2 可立即开工"
- ✗ 禁止说 "WS-S2 当前已满足、可开工"
- ✗ 禁止说 "本 shaping 报告已合并"（**当前 PR #621 仍未合并**；仅是 Draft）

### 9.2 WS-S3 开功门禁（**当前 BLOCKED**）

| 阻塞 | 状态 | 预计解锁 |
|------|------|---------|
| WS-S3 phase-A 浏览器 SSE 鉴权 transport 冻结（fetch+ReadableStream / polyfill / 独立 stream_token 契约三选一） | 🟣 未冻结 | 独立 contract-first PR |
| REQ-043 Runtime conformance spec + Tool Gateway spec 冻结 | ⚫ Candidate | 独立后续 PR（不在本报告范围） |
| REQ-047 Extended Contracts 三组 spec 冻结（HumanInput/Approval + ToolCall/Grant/Snapshot + Artifact/Evidence） | 🟣 Shaping | 独立后续 PR（不在本报告范围） |
| TD-085 Boundary Closure 中阻塞 Runtime 接线的依赖倒置切片完成 | 待办 | 独立后续任务 |

### 9.3 WS-S3 启动前必备清单

- [ ] WS-S3 phase-A 浏览器 SSE 鉴权 transport 冻结（fetch+ReadableStream / polyfill / 独立 stream_token 契约三选一）
- [ ] WS-S3 phase-B `cancelRun(runId, expectedRevision)` frontend wire-up（仅 UI + service 层；后端 cancel endpoint 已实，仅缺 transport）
- [ ] **REQ-047** Extended Contracts contract-first 冻结（保留 `/HumanInputRequest` `/ApprovalRequest` `/ToolCall` `/ToolGrant` `/RuntimeCapabilitySnapshot` `/Artifact` `/EvidenceItem` 全字段）——**严禁 typo 为 REQ-017**
- [ ] REQ-043 Spec contract-first 冻结（含 Runtime conformance + Tool Gateway + RuntimeProfileResolver）
- [ ] TD-085 依赖倒置切片完成
- [ ] Pi Worker V1 spike（REQ-043 AC-6）跑通至少 1 个真实只读 RAG + MCP/Skill 场景
- [ ] ACP Spike（REQ-043 AC-7）跑通 session new/resume + cancel + permission round-trip
- [ ] 至少 1 个 Runtime Cell sandbox 网络默认拒绝 + allowlist 放行验证（REQ-043 AC-8）

### 9.4 WS-S2/WS-S3 启动前置条件澄清

**历史错误校正**：
- 第一版 + 第一次纠偏 写 "WS-S2 implementation 当前已满足、可立即开工"——**错的**
- 第一版 + 第一次纠偏 写 "本 shaping 报告已合并"——**错的**（PR #621 截至本版仍为 OPEN/Draft）
- 第一版 + 第一次纠偏 写 "WS-S2.A mock POST /turns 返回 201"——**错的**（/turns 不存在，front-end 不能 mock 不存在的 endpoint）
- 第一次纠偏 残留 §9.3 「REQ-017」 typo——本版已纠正为 **REQ-047**

**唯一产品路径 = WS-S2 real submit closure (option B)**：
- WS-S2 当前 = BLOCKED（4 项硬门禁）
- WS-S3 当前 = BLOCKED（4 项硬门禁）
- Phase 0 仅完成 L0 静态代码审计 + 切片规划；WS-S2/WS-S3 implementation 均**未启动**

### 9.4 WS-S2 启动后「可以收口 WS-S2」的判定

- [ ] WS-S2.A-D 全部 unit + e2e pass
- [ ] WS-S2.E 手动验收 10 项全部 pass（含真实 PG 端到端）
- [ ] `git diff --check` clean
- [ ] `scripts/check-engineering-docs --full` passed
- [ ] 三路 CI 全 SUCCESS
- [ ] review-score-log.md 新增一行 #WS-S2-XX Original
- [ ] Metrics byte-identical
- [ ] 评分 ≥ 80 且 必修 follow-up = 无

---

## 10. 禁止表述（不能把 mock / fake / UI wiring 表述成 production enable）

**本节为强制规范**：所有正在进行的 WS-S2 / WS-S3 相关文档（plan / spec / PR body / commit message）都必须遵守本节。

| 禁止表述 | 必须表述 |
|---------|---------|
| 「WS-S2 = production ready submit-turn」 | 「WS-S2 implementation 当前 BLOCKED；公共 `/turns` API 未冻结；server-selected launch policy 未冻结；真实 Runtime 接入不在 WS-S2 scope」 |
| 「WS-S2.A 立即可开工」 / 「WS-S2 当前已满足可开工」 | 「WS-S2 phase-A/B/C/D/E 全部未启动；必须等 4 项硬门禁全部完成才能启动」 |
| 「submit-turn backend 已实」 / 「WS-S2 backend 已实 /turns endpoint」 | 「公共 `POST /turns` **不存在**；当前仅 internal `submit_turn()` application method；router 仅 8 个 endpoint（无 `/turns`）」 |
| 「不修改 /turns endpoint contract（backend 已冻结）」 | 「endpoint 不存在，不是已冻结；WS-S2 phase-A 才是冻结」 |
| 「submit-turn enabled」 / 「修改 `:disabled="false"`」 | 「Composer `:disabled="true"` 硬编码；按钮在 option B 的 backend + execution 前置全部通过前**始终 disabled**」 |
| 「WS-S2 frontend consumer wiring complete」 / 「submitTurn service stub」 | 「未启动；任何 frontend service/store mock stub 至多标记为 `non-deliverable / non-mergeable / L1 contract experiment`」 |
| 「WS-S3 = production ready agent workspace」 | 「WS-S3 implementation 当前 BLOCKED；4 项硬门禁未启动」 |
| 「cancelRun(runId, reason)」 | 「cancelRun(runId, expectedRevision)」（`CancelRunRequest = {expected_revision: int = Field(ge=1)}`；**不是 `{reason}`**） |
| 「WS-S3.A 新增 SSE endpoint」 | 「后端 SSE + cancel endpoint **已实现**（`router.py:376 / :397`）；WS-S3.A 仅做前端 transport + 消费层」 |
| 「SSE streaming」 (without mocking) | 「真实 SSE endpoint 已实；前端 SSE transport 选型（fetch+ReadableStream / polyfill / stream_token）**未冻结**；原生 EventSource 不能设 Authorization header」 |
| 「Mock = 真实 PG」 / 「L2 真实 PG dry-run for WS-S2.E」 | 「Mock 仅作 UI contract 验证；本 Phase 0 报告**最高已验证层级仅为 L0 静态代码审计**；L1 mock / L2 真实 PG dry-run / L3 真实 LLM 接入只能写成**未来验收门禁**」 |
| 「REQ-042 Done」 | 「WS-S1/WS-S2/WS-S3 完成仅交付 AC 子集；REQ-042 整体 ⚫ Candidate」 |
| 「AgentTurnLoopRuntime 接入」 / 「Runtime 中立 Adapter 已实现」 | 「WS-S2/WS-S3 不接 Runtime；Runtime 中立 Adapter 归 REQ-043（⚫ Candidate，未冻结）」 |
| 「审批 / 工具 / 产物 / 证据 实现」 | 「WS-S3 仅前端结构化 UI 渲染；审批后端 / 工具后端 / 产物后端 / 证据后端归 REQ-047 Extended（🟣 Shaping，未冻结）」 |
| 「本 shaping 报告已合并」 / 「可立即开工」 | 「PR #621 截至本版仍为 OPEN/Draft；**未合并**；仅完成 L0 审计 + 切片规划；WS-S2/WS-S3 implementation **均未启动**」 |
| 「REQ-017」 typo | **REQ-047**（严禁 REQ-017） |

---

## 11. 现有 spec / plan 不足点与最小文档修改建议

### 11.1 发现的不足

| 不足点 | 位置 | 严重度 |
|--------|------|-------|
| REQ-042 无明确 WS-S1/WS-S2/WS-S3 切片边界 | REQ-042 §Acceptance | 中（已由本报告 + 候选 row 标注） |
| WS-S1 closeout 已固化「AC-1[不含 restore] / AC-2 读半边 / AC-6」但 REQ-042 §Acceptance 全文未拆分 | REQ-042:28-35 | 低（不影响本任务） |
| 现有 plan 2026-07-24-req-041-047-conversation-run-contract-plan.md 仅覆盖 REQ-041/047 Durable Core，未覆盖 REQ-042 UI Slices | plan | 低（不影响本任务） |
| REQ-043 Spec §Runtime conformance 尚未 contract-first 冻结 | REQ-043 + [REQ-059 architecture spec](../01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md) | 高（blocker for WS-S3） |
| REQ-047 Extended Contracts 三组 spec 尚未 contract-first 冻结 | REQ-047 | 高（blocker for WS-S3） |

### 11.2 最小文档修改建议（**本报告不执行修改**，仅登记建议）

> **本节已校对**：REQ-017 typo 已在本版全面纠正为 REQ-047。
> 历史残留排查：本文件中所有 "REQ-017" 出现位置（§0 修订历史表内 + §9.3 + §9.4 + §13 + §14）仅作为「第一版/第一次纠偏历史错误的客观记录」保留，**禁止在任何规范正文中继续使用 REQ-017**。

| 建议 | 范围 | 优先级 |
|------|------|-------|
| 在 REQ-042 §Acceptance 下追加「WS-S1/WS-S2/WS-S3 切片映射」子节 | docs/01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md | P2（独立 task） |
| **WS-S2 phase-A 公共 submit API contract-first 冻结**（独立 PR；含 WS-S2 backend slice router 登记 + 测试改写） | docs/02-delivery-plans/01-specs/ + 独立 backend PR | **P0**（option B 第一道硬门禁） |
| **WS-S2 phase-B server-selected launch policy + 最小 execution profile contract-first 冻结**（独立 PR） | docs/02-delivery-plans/01-specs/ | **P0**（option B 第二道硬门禁） |
| **WS-S3 phase-A 浏览器 SSE 鉴权 transport 冻结**（fetch+ReadableStream / polyfill / 独立 stream_token 契约三选一） | docs/02-delivery-plans/01-specs/ | **P0**（WS-S3 第一道硬门禁） |
| 修改 REQ-047 Extended Contracts spec 冻结（含 HumanInput/Approval + ToolCall/Grant/Snapshot + Artifact/Evidence 全字段） | docs/02-delivery-plans/01-specs/ + REQ-047 §Scope 扩展 | **P0**（WS-S3 第二道硬门禁） |
| 修改 REQ-043 Runtime conformance + Tool Gateway + RuntimeProfileResolver spec 冻结 | docs/02-delivery-plans/01-specs/ + REQ-059 architecture spec | **P0**（WS-S2 + WS-S3 第三道硬门禁） |
| **禁止**新增 plan「WS-S2 mock-only pre-wire 单独 slice」 / 「WS-S2 frontend service wire-up 单独 slice」 | docs/02-delivery-plans/02-plans/ | **禁止**（与本报告裁决冲突；mock-only 路径已断开） |

### 11.3 不建议扩大的范围

- ✗ 不建议本报告触发 REQ-042 §Acceptance 文本改动（用户明确禁止「自行扩大范围」）
- ✗ 不建议本报告触发新 fact-audit.md / plan / spec（仅作建议登记）
- ✗ 不建议本报告修改后端任何文件

---

## 12. 现状盘点与状态标记

- 本任务卡 TASK-REQ-042-WS-S2-CONTRACT-SHAPING = 🟡 进行中
- 本报告完成 = 现状盘点 + AC 矩阵 + 切片推荐 + 依赖矩阵 + 证据等级 + 测试矩阵 + 开功门禁 + 禁止表述 + 文档建议 全部已落
- 下一动作 = 本报告写入 git 并 commit（pure-docs）
- WS-S2 启动 = 等本任务 commit 后用户明确授权
- WS-S3 启动 = 等 REQ-043 spec 冻结 + REQ-047 Extended spec 冻结 + TD-085 完成

---

## 13. 边界保留（最终确认）

- ✅ 本报告**仅修改 docs/02-delivery-plans/02-plans/2026-09-09-req-042-ws-s2-ws-s3-contract-shaping.md**（1 个 pure-docs 新文件）+ docs/03-engineering-governance/current-work.md（active card 状态更新）
- ✗ **不实现 submit-turn** / SSE / after_seq / cancel / stop / steer
- ✗ **不接 AgentTurnLoopRuntime** / Pi / ACP / MCP Server
- ✗ **不实现 Approval / Tool / Artifact / Evidence / SkillRunner timeline / HumanInputRequest**
- ✗ **不修改后端** / migration / schema / registry / CI / 门禁
- ✗ **不运行 agent_erasure_backfill** / 不修改 erase_available / 不触碰 metaedu 或 metaedu_test
- ✗ **不启动 REQ-043 / REQ-062 / REQ-063 / TD-085**
- ✗ **不把 REQ-042 翻 Done** / **不把 REQ-047 Extended 翻 Ready**
- ✗ **不处理 stale remote-tracking refs**
- ✗ **不修改 review-score-log.md 或 Metrics**
- ✗ **不触碰 recover-claude-dropped-stash-td047 与 dangling commit 91fe0290**

---

## 14. 完成状态

- **TASK-REQ-042-WS-S2-CONTRACT-SHAPING** Phase 0 shaping 完成
- 等用户裁决：
  - 接受本报告 → 进入 WS-S2 实施（用户另行启动 TASK-REQ-042-WS-S2-IMPLEMENTATION）
  - 要求修改切片边界 → 本报告 follow-up 修订
  - 不接受 → 当前状态保持
