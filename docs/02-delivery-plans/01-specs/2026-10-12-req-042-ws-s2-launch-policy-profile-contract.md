# REQ-042 WS-S2 phase-B：launch policy 消费面 + V1 最小 execution profile 契约（contract freeze 候选）

> Status: 🟣 Contract Proposal（本 PR 合并后视为 phase-B 契约冻结；评审期发现冲突以本文修订为准，不静默改写）
> Created: 2026-10-12
> Owner Requirement: [REQ-042](../../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md)（整体仍 ⚫ Candidate，本 spec 不代表 REQ-042 进入 Ready / Planned / Done）
> 上级计划：[WS-S2 / WS-S3 contract-shaping 计划](../02-plans/2026-09-09-req-042-ws-s2-ws-s3-contract-shaping.md) §WS-S2 phase-B（第三版裁决：REQ-043 完整 spec 与 REQ-047 Extended 三组 spec 均非本 phase 硬门禁）
> 前置契约：[WS-S2 phase-A 公共 submit API 契约](2026-10-12-req-042-ws-s2-public-submit-api-contract.md)（🟢 已冻结，PR #642）
> 明确排除：REQ-043 Runtime 语义（RuntimeProfileResolver / RuntimeSessionBinding / conformance / Tool Gateway）、REQ-047 Extended 三组契约与持久化 schema、phase-C backend route 与真实 PG tests、phase-D/E、WS-S3 全部

## 0. 边界声明

- 本 spec 只冻结 **launch policy 的消费面**与 **V1 最小 execution profile**：即「服务端在 dispatch 前必须构造哪些不可变输入、取值从哪里来、谁来校验、校验失败的对外语义」。它描述契约，**不声称任何公共端点已实现**——公共 `POST /turns` route 仍不存在（归 phase-C）。
- 本 spec **不定义、不实现** RuntimeProfileResolver 的选择算法、RuntimeSessionBinding 生命周期、Runtime conformance、Tool Gateway 运行时语义（均归 REQ-043）；**不定义** ToolGrant / Approval / Artifact / Evidence 契约或其持久化 schema（归 REQ-047 Extended）。
- 「消费面」含义：phase-C 实装 route 时服务端构造 `TurnLaunchSpecV1` 所必须遵守的字段级契约。RuntimeProfileResolver 未来由 REQ-043 实现时，其输出必须满足本消费面；本 spec 不要求 Resolver 存在。
- 未确定事项在 §4 逐项明示为「未冻结」，不以「不依赖 Extended 全集」为由省略必要语义。

## 1. 消费字段表（`TurnLaunchSpecV1` 逐字段）

事实源：`packages/server-python/app/shared/schemas/agent_integration.py:65`（`TurnLaunchSpecV1`，frozen + extra-forbid，docstring 原文 "Server-selected immutable execution inputs"）。全部字段 **server-selected**：客户端提交任一字段即 422（phase-A §4 已冻结）。

| 字段 | 类型 | 必填 | 来源（服务端选择责任） | 不可变边界 / 验证时点 |
|------|------|------|------------------------|------------------------|
| `agent_definition_version_id` | UUID | 是 | 必须等于客户端请求的 `agent_definition_version_id`（一致性校验在 `bridge.py` submit_turn 内既有，不一致 raise `WorkspaceIntegrationConflictError`，不得静默改写客户端选择） | 构造时；进入 outbox 后不可变 |
| `runtime_profile_id` | UUID | 是 | launch policy 按 tenant + definition 选定 profile（V1 唯一可选 profile 见 §2）；profile 必须 enabled（既有 `require_enabled_runtime_profile`，repository.py:167） | 构造时；profile 后续 disable 不回改已发出 launch |
| `runtime_binding_id` | UUID \| None | 否 | V1 恒为 `None`（compatibility 路径无 session binding；binding 语义归 REQ-043） | 构造时 |
| `runtime_capability_snapshot` | RuntimeCapabilitySnapshotV1 | 是 | 必须等于所选 profile 登记的 capability digest 对应快照（既有校验：snapshot 的 `runtime_kind` / `adapter_key` 与 profile 身份不一致 raise `CatalogConflictError`，execution_identity_service.py:105-110） | 构造时逐字段相等；快照随 launch 进 outbox 后不可变 |
| `run_config_snapshot` | RunConfigSnapshotV1 | 是 | 见 §2.3 逐项取值表；`budget` 子字段必须与顶层 `budget_snapshot` 逐字相等（schema 内建校验） | 构造时；内建校验失败即构造失败（fail-closed） |
| `context_snapshot_ref` / `context_snapshot_digest` / `context_snapshot_classification` | str / 64-hex / 枚举 \| None | 否 | V1 恒为全 `None`（schema 内建 all-null-or-all-present 校验）；context snapshot 语义归后续阶段 | 构造时；三字段要么全空要么全有 |
| `budget_snapshot` | RunBudgetSnapshotV1 | 是 | V1 取值见 §2.3；不得由客户端选项放大 | 构造时 |
| `parent_run_id` | UUID \| None | 否 | V1 恒为 `None`（root turn；子 Run 语义不在 WS-S2） | 构造时 |

schema 级不变量（既有，phase-C 不得削弱）：frozen + extra-forbid；`run_config_snapshot.budget == budget_snapshot`；整体 canonical JSON ≤ 24 KiB（`MAX_INLINE_INTEGRATION_BYTES`）。

## 2. V1 最小 execution profile

### 2.1 命名事实核对（不凭名称假设两个实现）

「compatibility execution」与「system.direct_rag.v1」是**同一条 compatibility 路径**的不同侧面，代码中只有一个实现（`composition/direct_rag_compatibility.py`）：

| 侧面 | 实际值（代码事实） | 位置 |
|------|---------------------|------|
| Agent definition | `definition_key = "system.direct_rag"`，`version = 1`（注意：代码中并无字面字符串 `system.direct_rag.v1`，该写法是 definition_key + version 的组合读法） | execution_identity_service.py:22-23 |
| Runtime profile | `profile_key = "compat.direct_rag.v1"`，`runtime_kind = "compatibility"`，`adapter_key = "direct_rag"` | execution_identity_service.py:24, 64-79 |
| policy_version | `"compat.direct_rag.v1"` | execution_identity_service.py:25 |

### 2.2 capability 快照（V1 唯一取值）

`DIRECT_RAG_CAPABILITIES`（execution_identity_service.py:27-37）：`runtime_kind="compatibility"`、`adapter_key="direct_rag"`，`resume / steer / native_tools / tool_calls / input_requests / approvals / event_ack` 全 `False`。domain 与 integration schema 双形式逐字段同构（domain/snapshots.py:25 与 agent_integration.py:22）。

### 2.3 V1 run config 与 budget（compatibility 路径现事实）

| 字段 | V1 取值 | 位置 |
|------|---------|------|
| `model_profile_key` | `None` | direct_rag_compatibility.py:174 |
| `autonomy_level` | `0` | direct_rag_compatibility.py:175 |
| `policy_version` | `"compat.direct_rag.v1"` | direct_rag_compatibility.py:176 |
| `tool_keys` | `()` | direct_rag_compatibility.py:177 |
| `budget.max_steps` | `2` | direct_rag_compatibility.py:117-124 |
| `budget.max_wall_seconds` | `300` | 同上 |
| `budget.max_tokens` | `100_000` | 同上 |
| `budget.max_cost_micros` | `2_000_000` | 同上 |
| `budget.max_tool_calls` | `1` | 同上 |
| `budget.max_retries` | `0` | 同上 |

### 2.4 phase-B 冻结的 V1 profile 语义

- 公共 submit API（phase-C 实装）的 V1 launch policy：**服务端只允许构造 compatibility 路径的 launch**；`runtime_profile_id` 解析目标恒为 tenant 内 `compat.direct_rag.v1` profile（不存在或 disabled → 拒绝，见 §3）。
- 客户端请求的 `agent_definition_version_id` 必须存在于本 tenant 且对应 enabled profile 可服务；V1 期不要求支持多 definition 市场语义，未授权/不可服务 → §3 错误语义。
- 上述是**消费面**冻结：将来 REQ-043 引入 RuntimeProfileResolver 后，多 profile 选择由其负责，但其输出必须满足本表与 §1 的不变量。

## 3. capability gate 消费面（fail-closed）

### 3.1 现状事实（如实）

- 公共错误码 `capability_denied` 在代码中**尚不存在**（全仓 grep 零命中）；phase-A §10 错误码表中的 `403 capability_denied` 是已冻结的**公共契约语义**，其提交期实装归 phase-C。
- 执行侧已存在 fail-closed capability 强制（与提交期 403 属不同阶段）：`run_coordinator.py:406-408` 在 Run 启动时拒绝 `tool_calls` / `input_requests` / `approvals` 任一为真的 capability 快照（`UnsupportedRunCapabilitiesError`，"E1 only accepts compatibility/read-only capability snapshots"）。
- 既有可复用校验：`require_enabled_runtime_profile`（profile disabled → `RuntimeProfileDisabledError`，repository.py:167）、capability 快照与 profile 身份一致性校验（`CatalogConflictError`）、definition **publish 时** digest 一致性 / 冲突检测（identity repository）。
- 按 `agent_definition_version_id` 查询存在性的方法**当前不存在**；§3.2-1 的「未知 → 422」判定须由 phase-C 新增查询实装，本 spec 不声称已有该查询。

### 3.2 phase-B 冻结的判定要求

dispatch 前（与 phase-A §8 durable 边界同一事务内）必须依次满足，任一不满足即拒绝（fail-closed，不降级放行）：

1. definition 存在性：未知 `agent_definition_version_id` → 422（phase-A §10 `validation_error`，既有契约不变）。
2. 可服务性：definition 在本 tenant 无可服务的 enabled compatibility profile → 403 `capability_denied`（phase-A §10 既有冻结码，本 spec 不另造新码）。
3. 快照一致性：构造的 capability snapshot 与 profile 登记 digest 不一致 → 视为服务端缺陷，构造失败即提交失败（不返回 2xx；phase-C 映射为 500 `internal_error`）。
4. 授权：`parts` 引用 resource 未通过服务端访问校验 → 403 `resource_access_denied`（phase-A 既有契约，workspace 侧 `_authorize_resource_references` 已存在）。

### 3.3 与 phase-A 的对齐

本 spec 不新增、不修改任何错误码；phase-A §10 错误码表（401/403×2/404/409×2/422/429/500）原样适用。429 仍按 phase-A 注明：无既有中间件，实装归 phase-C。

## 4. 输入事实、消费要求与未确定事项

| 输入 | 现有事实 | 消费要求 | 外部依赖 / 未确定事项 |
|------|----------|----------|------------------------|
| profile | `compat.direct_rag.v1` 可由 `bootstrap_direct_rag` publish-or-get（enabled=True） | §1/§2 取值与 enabled 校验 | 多 profile 选择归 REQ-043（未冻结 Resolver 语义） |
| binding | V1 恒 `None`；`RuntimeBindingStatus` 五态（creating/active/resume_required/closed/invalid）已存在于 domain | 本 spec 不消费 binding | binding 生命周期归 REQ-043 |
| capability | 双形式快照 + digest 一致性校验已存在 | §3.2-3 一致性判定 | 更丰富能力矩阵归 REQ-043 |
| run-config | compatibility 路径常量构造（§2.3） | 内建校验不得削弱 | `model_profile_key` 取值域未冻结（V1 恒 None） |
| budget | `_DIRECT_RAG_BUDGET` 常量（§2.3） | 客户端选项不得放大 | 按 definition/tenant 差异化预算策略**未冻结**（后续 phase 或 REQ-043/047 Extended 决策） |
| context snapshot | 三字段恒 None | all-null-or-all-present 校验 | 产生者与存储归后续阶段，**未冻结** |
| ToolGrant / Approval / Artifact / Evidence | 不进入本消费面 | 不消费 | 归 REQ-047 Extended，**未冻结** |

## 5. phase-C 验收矩阵与非目标

### 5.1 phase-C 可据此实现与验证的验收矩阵（真实 PG contract tests 候选）

| # | 验收项 | 依据 |
|---|--------|------|
| B-1 | 合法提交 → 201 + receipt；构造的 launch 满足 §1 全部不变量（含 budget 双写一致、≤24KiB） | §1 |
| B-2 | 客户端提交任一 server-selected 字段 → 422 | phase-A §4 + §1 |
| B-3 | 请求 definition 与服务端构造不一致 → 构造失败不返回 2xx（服务端缺陷语义） | §1 行 1 |
| B-4 | definition 不可服务 / profile disabled → 403 `capability_denied` | §3.2-2 |
| B-5 | 未知 definition → 422 | §3.2-1 |
| B-6 | capability snapshot 与 profile digest 不一致 → 500 fail-closed | §3.2-3 |
| B-7 | resource 未授权 → 403 `resource_access_denied` | §3.2-4 |
| B-8 | V1 launch 恒 `runtime_binding_id=None`、context snapshot 三字段全 None、budget 取 §2.3 常量 | §2.3 / §2.4 |
| B-9 | 幂等重放返回原 receipt，不改变既有 Message / Run / outbox 结果（不约束 route 是否临时构造随后被丢弃的 launch 对象） | phase-A §5 |

> phase-A §5 的「同键不同 digest → `409 idempotency_conflict`」路径由 phase-A 契约承担，phase-C 验收时须一并覆盖；本 spec 不另定义 digest 或幂等规则。

### 5.2 非目标（本 spec 明确不交付）

- 不实现公共 `/turns` route、middleware、限流（归 phase-C）。
- 不定义 RuntimeProfileResolver / RuntimeSessionBinding / Runtime conformance / Tool Gateway（归 REQ-043）。
- 不定义 ToolGrant / Approval / Artifact / Evidence 契约或持久化 schema（归 REQ-047 Extended）。
- 不引入多 profile / 多 Runtime 选择，不开放 Runtime Profile 切换。
- 不做 frontend wire-up（归 phase-D），不接 SSE（归 WS-S3）。
- 不把 compatibility 路径写成「Runtime 已实现」；Run 从 queued 到终态的真实执行仍依赖后续 Runtime 接入。

## 6. 验证

本 PR 为 pure-docs 契约塑形，无业务代码 / 测试 / migration / CI 变更。验证以门禁与人工比对为准：`git diff --check`、`scripts/check-engineering-docs --full`、相对链接存在性、字段取值与代码逐点比对（§1/§2 表格逐项对应 `agent_integration.py` / `execution_identity_service.py` / `direct_rag_compatibility.py` 行号）。不声称端点已实现或 submit loop 可运行。
