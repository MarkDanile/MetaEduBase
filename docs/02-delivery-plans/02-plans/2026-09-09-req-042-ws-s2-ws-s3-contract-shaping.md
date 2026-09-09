# REQ-042 WS-S2 / WS-S3 Contract-Shaping 报告（Phase 0）

> **Status**: 🟣 Shaping — Phase 0 audit + slicing plan（pure-spec / pure-docs，**不实现业务代码**）
> **Base**: `9fda8ae166c8ee924f986908fabb08d24bffe705`（main HEAD，PR #620 governance correction 已合入）
> **Requirement**: [REQ-042](../../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md)（status ⚫ Candidate）
> **Plan basis**: [REQ-041/047 Conversation/Run Durable Core 联合 plan](../../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md)（W1/E0/E1/B1/A1/D1/R1-S1..S6/C1 已合并）
> **作者任务卡**: TASK-REQ-042-WS-S2-CONTRACT-SHAPING（仅 docs/ + current-work.md，无业务代码改动）

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

### 4.2 WS-S2 切片（5 个 mini-slice）

> 前提：所有 WS-S2 mini-slice 依赖 WS-S1 + REQ-041 Durable Core（已合并）+ REQ-047 Durable Core（已合并）。无新后端契约需要落库。
> 边界：**不接 Runtime** / **不发 SSE** / **不实现 cancel** / **使用短轮询**（≤ 30s，长 poll by GET Run）。

| WS-S2 mini-slice | 目标 | 输入 | 输出 | 前置 | 完成标准（不冒充 production enable） |
|------------------|------|------|------|------|--------------------------------------|
| **WS-S2.A** Submit-Turn Endpoint Wire-up | 把现有 `/turns` POST endpoint（已在 REQ-041 W1 + B1 bridge 中实现 backend）前端消费层接好 | backend 已实：`POST /agent-workspace/conversations/{id}/turns`（[REQ-041 W1 plan](2026-07-24-req-041-047-conversation-run-contract-plan.md) Slice B1 §交付） | `service/turns.ts`：submitTurn(conversationId, content, idempotencyKey) → returns `{ runId, messageId, queueSeq }`；store 层加 `submitTurnInFlight` ref + guard（archive/restore/delete 相同模式） | WS-S1 完成；REQ-041 B1 PR #485 已合；REQ-047 E1 PR #483 已合 | unit tests：双击 guard（[c.f. workspace.spec.ts race GUARD 测试模式](../../../packages/web/src/stores/workspace.spec.ts)）+ 409 transparent 抛出 + 幂等键去重；**不发 SSE**；**不发按钮改 enabled**；仍保持 disabled，仅添加 service 层 wire-up |
| **WS-S2.B** Run Query Polling Loop（短轮询） | 实现"已启动 Run 后短轮询 GET Run 直到终态" | backend 已实：`GET /agent-runs/{id}`（WS-S1 已有）+ `cancel intent`（A1 PR #487） | `service/runs.ts`：pollRunUntilTerminal(runId, { maxDurationMs: 30_000, intervalMs: 1_000 }) | WS-S2.A 完成；WS-S1 store `getRun` 已有 | unit tests：interval / timeout 边界；终态判定用 `TERMINAL_RUN_STATUSES`；cancel intent 不在此 slice 实现（仅 poll） |
| **WS-S2.C** Composer Send Button ENABLED（受限） | 打开"已存档/已删除"以外状态会话的发送按钮 | WS-S2.A + WS-S2.B 完成 + Composer 当前已 `:disabled="true"` | 修改 `:disabled="false"` for state ∈ {active}；aria-disabled 同步；title 改"发送" | WS-S2.A + WS-S2.B 完成 | **必须保留**：state=archived / state=deleted 时仍 disabled（业务约束）；不接 SSE；不接 cancel；不接 Runtime；不发按钮替换 disabled placeholder |
| **WS-S2.D** Mock Submit-Turn E2E (Playwright) | 给 WS-S2.A/B/C 一个浏览器可观察的 mock 闭环 | 服务端真实 + 服务端 mock 拦截（page.route 模式） | playwright test：点发送 → 看到 message 出现在 timeline → run 状态从 queued → completed 变化 | WS-S2.A/B/C 完成 + 已开 setupWorkspaceE2E | e2e：mock 拦截 `POST /turns` 返回 201 + `GET /agent-runs/{id}` 返回 queued→running→completed 三态；timeout 30s 内完成；**模拟 fail-closed**：mock 409 / mock 422 也能正确显示 |
| **WS-S2.E** Manual Acceptance & Spec Completion | 真实 PG + 真实 user submit-turn（手动测试，不进 CI） | 全部 WS-S2.A-D 完成 + 真实 backend | 手动验收报告：9 项用户场景（如 WS-S1 9 项 + 新 submit 1 项 = 10 项） | WS-S2.A-D 完成 | 手动验收 pass + PR body「WS-S2.A-B-C-D-E 全部完成；真实 PG 后端 + frontend submit-turn poll 闭环 + 9 项手动验收 pass；保留 P2/P3 已知限制」 |

**WS-S2 禁止**：
- ✗ 不接 SSE / EventSource
- ✗ 不接 `AgentTurnLoopRuntime`
- ✗ 不实现 cancel / stop / steer
- ✗ 不开放 Runtime Profile 切换
- ✗ 不修改 /turns endpoint contract（backend 已冻结）

### 4.3 WS-S3 切片（5 个 mini-slice）

> 前提：WS-S2 全部完成 + REQ-043 Runtime neutral adapter spec 已冻结（依赖 TD-085 依赖倒置切片完成）+ REQ-047 Extended Contracts（HumanInputRequest + ApprovalRequest + ToolCall + ToolGrant + Artifact + Evidence）已冻结。
> 边界：**接 SSE** / cancel / steer / 实时 RunEvent / 结构化 Tool / Approval / Artifact 面板。

| WS-S3 mini-slice | 目标 | 输入 | 输出 | 前置 | 完成标准 |
|------------------|------|------|------|------|----------|
| **WS-S3.A** SSE Event Stream Endpoint + Frontend Transport | 后端 SSE `GET /agent-runs/{id}/events?after_seq=N`；前端 `useRunEventStream(runId)` composable | REQ-043 AC-11「SSE 断开不推导 Run 成功，客户端可按 after_seq 重放并独立查询终态」+ REQ-047 AC-2「(tenant_id, run_id, seq) 唯一且 seq 单调递增；客户端可检测 gap 并按 after_seq 重放」 | backend：SSE endpoint；frontend：`composables/useRunEventStream.ts`（EventSource 包装，after_seq 自动续传，gap 检测 → trigger reload） | REQ-047 B1 + E1 已合并；WS-S2 完成 | unit tests：after_seq 重连；gap detection；abort；连接超时；同 run 多次切换不重复连接 |
| **WS-S3.B** RunEvent Timeline Component + Structured Renderers | 中栏 RunEvent 类型化渲染：plan_summary / phase / tool lifecycle / evidence / approval / input / artifact / retry / usage / error / terminal | REQ-047 RunEvent 类型 + Spec §RunEvent 字段 | `components/agent-workspace/RunEventTimeline.vue` + `components/agent-workspace/events/{Plan,Tool,Evidence,Approval,Input,Artifact,Error,Terminal}.vue`；按 `kind` 分发到不同子组件（结构化组件 ≠ 普通助手文本） | WS-S3.A 完成；REQ-047 AC-9（32 KiB 内联边界、classification 外置）已 merge | 每个事件类型单独 unit test；端到端 SSE e2e（mock event stream） |
| **WS-S3.C** Cancel / Stop / Steer intent + UI | RunDetailPane 加 cancel 按钮 + 显式 steer 输入框（活动 Run 强制终止 + 普通消息排队 → 下一 Run） | REQ-047 AC-1「Run 状态机覆盖 queued/starting/running/waiting_input/waiting_approval/resume_required/cancelling/completed/failed/cancelled/expired，非法迁移失败」+ REQ-043 AC-16/AC-17「cancel/timeout 遇到 executing/reconciling 写 Tool 时不得先落 Run 终态；先 reconcile，无法确认时 ToolCall=outcome_unknown 且 Run=resume_required」+ REQ-043 AC-18「resume_required -> starting 只能由同一 Binding/epoch 恢复成功触发」 | `service/runs.ts`：`cancelRun(runId, reason)` + `steerRun(runId, content, idempotencyKey)`；RunDetailPane 新增按钮 + 输入 | WS-S3.B 完成；REQ-047 E1/A1 state machine 已 merge；RuntimeSessionBinding 已 wired | 单元 + e2e：cancel 按钮 disabled for terminal states；steer 后产生 queued message；outcome_unknown 显示为 resume_required |
| **WS-S3.D** HumanInputRequest + ApprovalRequest UI（结构化组件） | 活动 Run 等待 input/approval 时显示结构化请求卡：HumanInputRequest 与 Approval 分离；过期不可重复提交；reviewer scope 显示 | REQ-047 AC-14「HumanInputRequest 与 ApprovalRequest 在状态、权限、响应和过期语义上完全分离」+ REQ-043 AC-5「审批 durable、first-answer-wins、带 revision/runtime epoch、过期时间和 reviewer scope」+ REQ-047 AC-4「审批进程重启后仍可查询和处理；重复或冲突回答有稳定幂等语义」 | HumanInputCard.vue + ApprovalCard.vue；response endpoint `POST /runs/{id}/input` + `POST /runs/{id}/approvals/{aid}/respond` | WS-S3.B 完成；REQ-047 Extended Contracts (HumanInput + Approval) 已 spec 冻结 + plan merge | 单元 + e2e：分离组件；过期原子取消未执行 ToolCall；revision bump 拒绝旧 revision |
| **WS-S3.E** Artifact / Evidence Timeline + Thinking Summary | RunEvent timeline 嵌入 Artifact 卡 + EvidenceItem 卡 + thinking summary 受控展示（不展示原始 CoT） | REQ-047 AC-5「Artifact 支持版本、来源 Run、创建者、tenant、确认/退回和归档；大文件不直接塞数据库 JSON」+ REQ-047 AC-6「Evidence 可回溯到 RAG source、MCP invocation、Query audit 或其他受治理来源，不接受模型自造引用」+ REQ-047 AC-11「事件和日志中不存在原始 Chain-of-Thought、长期凭证及未裁剪敏感 Tool Result」 | ArtifactCard.vue + EvidenceCard.vue + thinking-summary 渲染（仅 plan/phase/tool/evidence/usage/error 摘要） | WS-S3.B + WS-S3.D 完成；REQ-047 Artifact + Evidence 已 merge | 单元 + e2e：Artifact 版本链；Evidence 血缘；thinking summary 严格按 REQ-047 §Scope 边界渲染 |

**WS-S3 禁止**：
- ✗ 不实现 Tool Gateway / ToolGrant 后端（归 REQ-043 Tool Gateway 切片）
- ✗ 不实现 Runtime Plan 算法（归 REQ-043 Runtime 中立 Runtime）
- ✗ 不修改 RunEvent schema（依赖 REQ-047 已冻结）

### 4.4 切片依赖图

```
WS-S1 完成 ✅
  ├─ WS-S2.A submit-turn wire-up
  │   ├─ WS-S2.B poll loop
  │   │   └─ WS-S2.C enable send button
  │   │       └─ WS-S2.D mock e2e
  │   │           └─ WS-S2.E manual acceptance
  └─ (independent) ────────────────────
                                          
REQ-047 Extended Contracts 🟣 Shaping
  ├─ WS-S3.A SSE transport
  │   ├─ WS-S3.B RunEvent timeline
  │   │   ├─ WS-S3.D HumanInput + Approval
  │   │   │   └─ WS-S3.E Artifact + Evidence
  │   │   └─ WS-S3.C cancel/stop/steer (parallel)
  │   │       └─ WS-S3.E Artifact + Evidence
  └─ (depends on REQ-043 Tool Gateway & Runtime Profile adapter — TD-085 依赖倒置切片)
```

**关键依赖**：
- WS-S3 整体依赖 REQ-043 Runtime 中立 Adapter spec 冻结 + TD-085 Boundary Closure 中会阻塞 Runtime 接线的依赖倒置切片完成
- WS-S3.D（HumanInput + Approval UI）依赖 REQ-047 Extended Contracts (HumanInputRequest + ApprovalRequest) 冻结
- WS-S3.E（Artifact + Evidence）依赖 REQ-047 Artifact + Evidence spec 冻结

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

```
1. REQ-047 Extended Contracts 三组 spec contract-first 冻结（blocker for WS-S3）
2. REQ-043 Runtime conformance + Tool Gateway spec 冻结（blocker for WS-S3）
3. TD-085 Boundary Closure 中阻塞 Runtime 接线的依赖倒置切片完成
4. WS-S2 立即可开工（无 spec blocker，仅依赖 Durable Core）
5. WS-S2 完成 → 真实浏览器手动验收 + 评分 → 才能进 WS-S3
6. WS-S3 按 A → B → C/D 并行 → E 顺序
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

### 6.2 WS-S2 新增契约（仅前端消费层，不动 backend）

| 新增 service 方法 | 路径 | 后端对应 |
|------------------|------|---------|
| `submitTurn(conversationId, content, idempotencyKey, draftAutoSave?)` | `POST /agent-workspace/conversations/{id}/turns` | 已在 REQ-041 W1 + B1 bridge 中实现 backend；前端未消费 |
| `pollRunUntilTerminal(runId, {maxDurationMs, intervalMs})` | `GET /agent-runs/{id}`（已存在） | 无新 contract |
| Composer 草稿自动保存 (`composerDraftStore`) | localStorage 镜像 | 无新 contract |
| RunStatusRevision 在 poll loop 中检测乐观并发变更 | `GET /agent-runs/{id}` 响应 `status_revision` 字段（已存在） | 无新 contract |

**WS-S2 DTO 扩展**（仅前端 typed，不动 backend）：
- `submitTurnRequest`: `{ content: string, idempotencyKey: string, draftAutoSave?: boolean }`
- `submitTurnResponse`: `{ runId: string, messageId: string, queueSeq: number, statusRevision: number }`
- `pollOptions`: `{ maxDurationMs?: number, intervalMs?: number }`

### 6.3 WS-S3 新增契约（contract-first 待 spec 冻结）

| 新增 service 方法 | 路径 | 依赖 |
|------------------|------|------|
| `useRunEventStream(runId, { afterSeq, abortSignal })` | SSE `GET /agent-runs/{id}/events?after_seq=N` | REQ-043 AC-11 + REQ-047 AC-2 |
| `cancelRun(runId, reason)` | `POST /agent-runs/{id}/cancel` | REQ-047 AC-1 |
| `steerRun(runId, content, idempotencyKey)` | `POST /agent-runs/{id}/steer` | REQ-043 AC-16 |
| `respondHumanInput(inputId, answer)` | `POST /runs/inputs/{id}/respond` | REQ-047 HumanInputRequest |
| `respondApproval(approvalId, option, idempotencyKey)` | `POST /runs/approvals/{id}/respond` | REQ-043 AC-5 + REQ-047 AC-14 |
| `fetchArtifact(artifactId)` + `fetchEvidence(evidenceId)` | `GET /artifacts/{id}` / `GET /evidence/{id}` | REQ-047 AC-5/AC-6 |

**WS-S3 RunEvent schema**（contract-first 须冻结）：
- `RunEvent` 类型：plan_summary / phase / tool_lifecycle / evidence / input / approval / artifact / retry / usage / error / terminal
- `(tenant_id, run_id, seq)` 唯一且 seq 单调递增（REQ-047 AC-2）
- 32 KiB 内联边界 + classification 不高于 `internal`（REQ-047 AC-9）

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

### 7.1 各 Slice 的最高已验证层级

| Slice | 验证环境 | 最高层级 | 备注 |
|------|---------|---------|------|
| WS-S2.A submit-turn wire-up | mock backend (page.route) | L1 mock | 不开放按钮；service + store unit tests |
| WS-S2.B poll loop | mock backend | L1 mock | 短轮询 interval / timeout 边界 unit tests |
| WS-S2.C enable send button | mock backend | L1 mock | e2e：mock 端到端 |
| WS-S2.D mock e2e | Playwright + mock | L1 mock | browser visible; mock covers success/409/422 |
| **WS-S2.E manual acceptance** | **真实 PG + 真实 backend** | **L2 真实 PG dry-run** | **手动用户测试 10 项**；不接 LLM |
| WS-S3.A SSE transport | mock SSE stream | L1 mock | EventSource + after_seq 重连 unit + e2e |
| WS-S3.B RunEvent timeline | mock SSE stream | L1 mock | 组件 unit tests |
| WS-S3.C cancel/stop/steer | mock backend | L1 mock | e2e：cancel + steer 流 |
| WS-S3.D HumanInput + Approval UI | mock backend | L1 mock | REQ-047 Extended 仍 Shaping，不连真实 backend |
| WS-S3.E Artifact + Evidence | mock backend | L1 mock | 同上 |
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

### 8.1 WS-S2 测试矩阵

| Slice | unit (vitest) | e2e (Playwright) | 手动验收 | mutation harness |
|------|--------------|------------------|---------|------------------|
| WS-S2.A | submitTurn double-click guard; 409 transparent; idempotencyKey dedup; store ref management | — | — | N/A（mock service） |
| WS-S2.B | pollRunUntilTerminal interval / timeout; TERMINAL_RUN_STATUSES detection; cancel 不实现 | — | — | N/A |
| WS-S2.C | Composer state=active → enabled; state=archived → disabled; state=deleted → disabled | — | — | N/A |
| WS-S2.D | — | mock POST /turns (201) → GET /agent-runs/{id} (queued→running→completed); mock POST /turns (409) → toast 错误 | — | N/A |
| WS-S2.E | — | — | 10 项用户场景：创建 → 输入 → 发送 → 看到 message → 看到 run 终态；归档后无法发送；删除后无法发送；非 archived 状态正常；网络错误 toast；超时 30s 提示 | — |

### 8.2 WS-S3 测试矩阵

| Slice | unit | e2e | 手动验收 | mutation |
|------|------|-----|---------|---------|
| WS-S3.A | useRunEventStream reconnection; gap detection; abort; connection timeout; multi-mount no duplicate connection | mock SSE event stream | — | N/A |
| WS-S3.B | PlanCard / ToolCard / EvidenceCard / ApprovalCard / InputCard / ArtifactCard / ErrorCard / TerminalCard 各自独立渲染 | mock SSE → 事件类型分发到子组件 | — | N/A |
| WS-S3.C | cancelRun button disabled for terminal; steerRun produces queued message; outcome_unknown → resume_required UI state | mock cancel flow; mock steer flow | — | N/A |
| WS-S3.D | HumanInputCard 与 ApprovalCard 分离; revision bump 拒绝旧 revision; 过期原子取消未执行 ToolCall | mock input/approval respond flows | — | N/A |
| WS-S3.E | ArtifactCard 版本链; EvidenceCard 血缘; thinking summary 严格按 REQ-047 §Scope 边界 | mock artifact/evidence events | — | N/A |

### 8.3 手动验收路径（WS-S2.E）

```
用户场景 1：active 会话提交 turn
  1. 进入 /agent-workspace?c=conv-1
  2. Composer 输入 "test"
  3. 点发送
  4. 看到 message 出现在 timeline
  5. 右栏自动派生 run（queued → running → completed）
  6. 看到 run status 终态事实（status / queue_seq / event window）

用户场景 2：archived 会话提交应被阻止
  1. 归档会话
  2. Composer 应 disabled
  ...
```

---

## 9. 「可以开始实现」的门禁条件

### 9.1 WS-S2 开功门禁（**当前已满足，可开工**）

- ✅ WS-S1 完成（PR #618 merge + governance correction PR #620 merge）
- ✅ REQ-041 Durable Core 完成（🟢 Done）
- ✅ REQ-047 Durable Core 完成（C1 PR #614 merge）
- ✅ `/turns` endpoint backend 已实现（REQ-041 W1 + B1 bridge）
- ✅ GET Run endpoint 已存在（WS-S1 已消费）
- ✅ active card 登记（本任务 commit 1）
- ✅ 本 Phase 0 shaping 报告合并（spec/plan 完成）

### 9.2 WS-S3 开功门禁（**当前阻塞**）

| 阻塞 | 状态 | 预计解锁 |
|------|------|---------|
| REQ-043 Runtime conformance spec 冻结 | ⚫ Candidate | 独立后续 PR（不在本报告范围） |
| REQ-047 Extended Contracts 三组 spec 冻结（HumanInput/Approval + ToolCall/Grant/Snapshot + Artifact/Evidence） | 🟣 Shaping | 独立后续 PR（不在本报告范围） |
| TD-085 Boundary Closure 中阻塞 Runtime 接线的依赖倒置切片完成 | 待办 | 独立后续任务 |

### 9.3 WS-S3 启动前必备清单

- [ ] REQ-043 Spec contract-first 冻结（含 Runtime conformance + Tool Gateway + RuntimeProfileResolver）
- [ ] REQ-017 Extended Contracts contract-first 冻结（保留 `/HumanInputRequest` `/ApprovalRequest` `/ToolCall` `/ToolGrant` `/RuntimeCapabilitySnapshot` `/Artifact` `/EvidenceItem` 全字段）
- [ ] TD-085 依赖倒置切片完成
- [ ] Pi Worker V1 spike（REQ-043 AC-6）跑通至少 1 个真实只读 RAG + MCP/Skill 场景
- [ ] ACP Spike（REQ-043 AC-7）跑通 session new/resume + cancel + permission round-trip
- [ ] 至少 1 个 Runtime Cell sandbox 网络默认拒绝 + allowlist 放行验证（REQ-043 AC-8）

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

| 禁止表述 | 必须表述 |
|---------|---------|
| 「WS-S2 = production ready submit-turn」 | 「WS-S2 = submit-turn endpoint frontend consumer wiring complete（mock-only validation）；真实 Runtime / 真实 LLM / 真实 Agentic RAG 不在 WS-S2 scope」 |
| 「WS-S3 = production ready agent workspace」 | 「WS-S3 = SSE event stream + cancel/steer + 结构化 Timeline frontend consumer complete（mock-only validation）；Tool Gateway / RuntimeProfile adapter V1 enable 仍归 REQ-043」 |
| 「submit-turn enabled」 | 「Composer `:disabled` 在 WS-S2.C 才有条件打开；WS-S2.A/B 仅 service + store wire-up，按钮仍 disabled」 |
| 「SSE streaming」 (without mocking) | 「mock SSE event stream + 真实 SSE endpoint spec 待 REQ-047 Extended merge 后实现」 |
| 「Mock = 真实 PG」 | 「Mock 仅作 UI contract 验证；最高已验证层级为 L1 mock；WS-S2.E 手动验收为 L2 真实 PG dry-run」 |
| 「REQ-042 Done」 | 「WS-S1/WS-S2/WS-S3 完成仅交付 AC 子集；REQ-042 整体 ⚫ Candidate」 |
| 「AgentTurnLoopRuntime 接入」 | 「WS-S2/WS-S3 不接 Runtime；Runtime 中立 Adapter 归 REQ-043」 |
| 「审批 / 工具 / 产物 / 证据 实现」 | 「WS-S3 仅实现结构化 UI 渲染；审批后端 / 工具后端 / 产物后端 / 证据后端归 REQ-047 Extended」 |

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

| 建议 | 范围 | 优先级 |
|------|------|-------|
| 在 REQ-042 §Acceptance 下追加「WS-S1/WS-S2/WS-S3 切片映射」子节 | docs/01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md | P2（独立 task） |
| 新增 plan `2026-09-09-req-042-ws-s2-submit-poll-implementation-plan.md`（WS-S2 五 mini-slice 实施边界 + 完成标准 + 不允许交叉内容） | docs/02-delivery-plans/02-plans/ | P2（WS-S2 启动前 commit） |
| 新增 plan `2026-09-09-req-042-ws-s3-sse-cancel-timeline-implementation-plan.md`（WS-S3 五 mini-slice） | docs/02-delivery-plans/02-plans/ | P3（WS-S3 启动前 commit；先决条件见 §9.3） |
| 新增 spec `2026-09-09-req-042-ws-s2-ws-s3-runtime-event-contract-spec.md`（SSE/after_seq/cancel/steer contract-first） | docs/02-delivery-plans/01-specs/ | P3（WS-S3 启动前） |

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
