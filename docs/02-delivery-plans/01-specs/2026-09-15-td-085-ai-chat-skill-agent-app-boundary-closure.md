# TD-085 Spec: AI Chat / Skill / Agent App 上下文边界收口

> **Status**: 🟣 Shaping（Phase 0 contract-first，仅规划与契约冻结；不进入 implementation）
> **Priority**: P1
> **Domain**: 后端 / Agent Platform / DDD / 可维护性
> **Source**: [REQ-059](../../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md) / 2026-07-23 源码复核 + 2026-09-15 TD-085 Phase 0 现场审计

## 0. base 事实与开篇约定

### 0.1 base SHA 与现状

- main HEAD：`448f4f6d27562bcd953bd911b27dfbf3eea9177f`（Phase 0 审计起点）
- TD-085 在 [technical-debt.md](../../03-engineering-governance/technical-debt.md) ⚫ 待办（P1）
- REQ-042 → TD-085 → REQ-043 仓库规划顺序（TD-085 是 REQ-043 的硬前置）
- WS-S2 option B 仍 BLOCKED、WS-S3 仍 BLOCKED（独立事实：PR #622 closeout 已 merge）

### 0.2 审计证据（code:line 真实存在）

#### A. 应用层 → interface/api 层反向导入（layer inversion）

事实源（git grep + line numbers）：

- [packages/server-python/app/contexts/knowledge/application/ai_chat_service.py:565](../../../packages/server-python/app/contexts/knowledge/application/ai_chat_service.py#L565) — `from app.contexts.knowledge.interfaces.api.ai_router import _call_llm`
- [packages/server-python/app/contexts/knowledge/application/ai_chat_service.py:589](../../../packages/server-python/app/contexts/knowledge/application/ai_chat_service.py#L589) — 同导入（第二次调用）
- [packages/server-python/app/contexts/knowledge/application/hybrid_ner_service.py:93](../../../packages/server-python/app/contexts/knowledge/application/hybrid_ner_service.py#L93) — `from app.contexts.knowledge.interfaces.api.ai_router import (...)`
- [ai_chat_service.py:16](../../../packages/server-python/app/contexts/knowledge/application/ai_chat_service.py#L16) — 注释自认 "行为由 ai_router 单独保留（如有遗留调用方）。本 service 是 RAG 编排层"

事实判断：**真实边界倒置**（不是兼容适配）。应用层（`application/`）反向依赖本 context 的接口层（`interfaces/api/`）— 违反仓库文档 [architecture.md](../../03-engineering-governance/01-rules/architecture.md) "Router 只做认证、DTO、异常/响应映射；依赖装配进入清晰的 composition provider"。所谓"function-level lazy import 避免循环"是绕过编译器检查，不是架构正确性。

#### B. ai_chat_service.py 单文件 1015 行（> 1000 行硬边界）

- [ai_chat_service.py](../../../packages/server-python/app/contexts/knowledge/application/ai_chat_service.py) — `wc -l = 1015`
- 单一文件同时承担：NER、检索、Fusion、Context Packing、Prompt、LLM、内部问数 Tool Calling、Diagnostics
- 违反 [quality-gates.md](../../03-engineering-governance/01-rules/quality-gates.md) 文件规模硬限制（默认 500 行，新增 / 重构 1000 行）

事实判断：**真实违反硬限制**。

#### C. 通用 Skill 层被企业尽调反向塑形（domain boundary 混淆）

事实源：

- [skill_runner.py:103](../../../packages/server-python/app/contexts/skill_registry/application/skill_runner.py#L103) — `Real QCC tools (any \`qcc*\` server — company / risk / history / executive)`
- [skill_runner.py:110](../../../packages/server-python/app/contexts/skill_registry/application/skill_runner.py#L110) — `if server.startswith("qcc") and isinstance(subject, dict):`
- [skill_runner.py:407](../../../packages/server-python/app/contexts/skill_registry/application/skill_runner.py#L407) — `Run one \`internal_query\` step via the injectable query runner.`
- [skill_runner.py:411](../../../packages/server-python/app/contexts/skill_registry/application/skill_runner.py#L411) — `f"step '{step.id}' 是 internal_query,但 runner 未配置 query_runner"`
- [skill_runner.py:538](../../../packages/server-python/app/contexts/skill_registry/application/skill_runner.py#L538) — `你是企业尽调报告助手。严格按给定报告骨架填空：只填值、不更改结构；`
- `dd_query_runner.py`（历史路径 `skill_registry/application/dd_query_runner.py`；TD-085 Slice C 起迁至 [due_diligence/application/dd_query_runner.py](../../../packages/server-python/app/contexts/due_diligence/application/dd_query_runner.py)）— `wc -l = 258`（位于 skill_registry 上下文，命名、配置、主体解析均属于 due_diligence）
- `dd_query_runner.py:30-34`（历史路径 `skill_registry/application/`，Slice C 起迁至 `due_diligence/application/`）— `from app.contexts.mcp_registry.application.mcp_invocation_service import (...)` 和 `from app.contexts.structured_data.application.query_service import QueryService`（DD 借通用 Skill 与 QueryService 入口）
- 测试证据：`test_dd_query_runner.py`、`test_dd_internal_query_e2e.py`（历史位于 `tests/contexts/skill_registry/`，Slice C 起迁至 [tests/contexts/due_diligence/](../../../packages/server-python/tests/contexts/due_diligence/)）存在于 skill_registry 测试目录，证明 DD 测试覆盖归 Skill 上下文

事实判断：**真实 domain boundary 倒置**（DD 业务渗入通用 Skill 上下文 + 通过 compatibility adapter 维持兼容）。

#### D. agent_workspace ↔ agent_execution 双向 mutual 依赖（context boundary leak）

事实源：

- [direct_rag_compatibility.py:46-53](../../../packages/server-python/app/composition/direct_rag_compatibility.py#L46-L53) — `from app.contexts.agent_workspace.application.bridge import (...)` 和 `from app.contexts.agent_workspace.domain import (...)`（composition → workspace application，方向正常）
- [agent_workspace/.../workspace_transport_erasure_participant.py:241](../../../packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_transport_erasure_participant.py#L241) — `from app.contexts.agent_execution.domain.snapshots import snapshot_digest`（workspace ← execution domain = 违反 REQ-059 agent_workspace 与 agent_execution 互不依赖）
- [agent_execution/.../execution_erasure_participant.py:79-88](../../../packages/server-python/app/contexts/agent_execution/infrastructure/execution_erasure_participant.py#L79-L88) — `from app.contexts.agent_workspace.domain import (...)` 与 `from app.contexts.agent_workspace.infrastructure.erasure_repository import (...)` 与 `from app.contexts.agent_workspace.infrastructure.models import (...)`（execution ← workspace = 双向 leak）
- [agent_execution/application/compatibility_output_service.py:18](../../../packages/server-python/app/contexts/agent_execution/application/compatibility_output_service.py#L18) — `from app.contexts.agent_workspace.application.ports import TerminalOutput`（execution application ← workspace ports：合理 port 抽象，但暗示依赖 workspace domain 定义）
- [agent_execution/application/run_query_service.py:32](../../../packages/server-python/app/contexts/agent_execution/application/run_query_service.py#L32) — `from app.contexts.agent_workspace.application.ports import WorkspaceReadPort`（execution ← workspace ports：合理抽象但仍依赖 workspace application 层）

事实判断：**双向 mutual 依赖 + 双向 leak 真实存在**。两 context 通过 erasure participant 与 ports 形成循环依赖。REQ-059 规定二者应为独立 bounded context。

#### E. 上下文文件数量与测试分布

| 上下文 | .py 文件 | 测试文件 | 占比 |
|-------|----------|---------|------|
| agent_workspace | 23 | 6 | 26% |
| agent_execution | 29 | 12 | 41% |
| knowledge | 31 | 25 | 81% |
| skill_registry | 14 | 14 | 100% |
| due_diligence | 17 | 15 | 88% |
| ai_app | 12 | 5 | 42% |

事实判断：**skill_registry 测试覆盖 100%（含 DD 测试）= 进一步证实 DD 被反塑形到通用 Skill 层**。

### 0.3 哪些是真实倒置 vs 哪些是合理调用

- **真实倒置**（必须修复）：
  - `knowledge/application → knowledge/interfaces/api`（A）
  - `agent_workspace ↔ agent_execution mutual erasure participant + ports`（D）
  - `ai_chat_service.py 单文件 1015 行跨多职责`（B）
  - `skill_runner.py + dd_query_runner.py 携带 DD/QCC 业务`（C）

- **合理调用**（保留为 Port 抽象）：
  - `composition/direct_rag_compatibility → agent_workspace`（composition 可调用 context application）
  - `composition/agent_control_plane → agent_workspace + agent_execution`（composition 是合法编排层）
  - `agent_execution/application/compatibility_output_service → agent_workspace/application/ports`（仅 import port 接口，类型抽象，无循环）

## 1. 当前边界与问题定义

### 1.1 当前 owner 错位

| 关注点 | 实际 owner | 应当 owner | 倒置? |
|--------|---------|----------|--------|
| LLM HTTP 调用 | `knowledge/interfaces/api/ai_router.py`（被 application 层反向 import） | 应由 `runtime.llm_provider` 或新 `tool_gateway` 抽象拥有；application 层只调用 port | 是 |
| RAG 编排（含 NER + 检索 + Fusion + Context Packing + Prompt + Tool Calling） | 单一 `ai_chat_service.py` 1015 行 | 拆分：knowledge → retrieval；tool_gateway → tool orchestration；runtime → LLM | 是 |
| 企业尽调业务（QCC 调用、报告骨架、内部问数） | 通用 `skill_runner.py` 第 538 行 + `skill_registry/application/dd_query_runner.py` | 应由 `due_diligence` context 拥有 | 是 |
| Tool Calling 与"is internal_query"分支逻辑 | 通用 `skill_runner.py` 内部 | 应由 `tool_gateway` 抽象 + `due_diligence` 业务方调用 | 是 |
| Conversation 与 Message 归属 | `agent_workspace` | `agent_workspace`（正确） | 否 |
| Run / Event / AgentRun / TurnInput | `agent_execution` | `agent_execution`（正确） | 否 |
| agent_workspace ↔ agent_execution 跨边界调用 | 直接 domain + infrastructure import | 各自通过 port 抽象 | 是 |
| 两 context 互相 erasure participant 跨边界调用 | 直接相互 import | 各自通过 port + composition 协调 | 是 |

### 1.2 问题陈述

- 依赖方向：domain/application 指向 interface 和具体业务 adapter，违反 Router 轻量与上下文分层规则
- 职责模糊：Direct RAG、确定性 Skill 和未来 Agent Runtime 无法清晰组合
- 业务泄漏：企业尽调字段和 Prompt 泄漏进通用 Skill 层
- 一次性大重构风险高：必须以特征测试和 Port/Adapter 逐步迁移

### 1.3 与 REQ-059 / REQ-043 / REQ-047 Extended 关系

- REQ-059 规定 `agent_workspace` 与 `agent_execution` 应为独立 bounded context；当前 mutual import 违反
- REQ-043（Runtime Port / Tool Gateway）被 TD-085 阻塞：
  - LLM Port 必须先抽取（解开 ai_chat_service.py 反向依赖）
  - Skill 与 Agent Skill 语义必须先区分（解开 skill_runner.py 中 QCC 硬编码与 internal_query 分支）
- REQ-047 Extended（HumanInput/Approval/ToolCall/Grant/Snapshot/Artifact/Evidence）被 TD-085 影响：
  - TD-085 解开 agent_workspace 与 agent_execution 跨边界 mutual import 后，REQ-047 Extended 才能在两个独立 context 上分别定义 Input/Approval/Output/ToolCall 字段

### 1.4 与 WS-S2 / WS-S3 关系

- WS-S2 option B BLOCKED（4 项硬门禁：公共 submit API + server-selected launch policy + 最小 execution profile + 真实 PG submit-loop）
- WS-S3 BLOCKED（4 项硬门禁：浏览器 SSE 鉴权 transport + cancelRun/steerRun 前端 + REQ-047 Extended spec + REQ-043 Runtime conformance spec）
- TD-085 解开的是 LLM Port + 跨 context 边界，**不直接解锁** WS-S2 / WS-S3 任何一个门禁
- 真正解锁路径：WS-S2 → REQ-043 public `/turns` + launch policy；WS-S3 → REQ-047 Extended spec + REQ-043 Runtime conformance
- **TD-085 单独完成不意味着 WS-S2/WS-S3/REQ-043 已解除全部阻塞**（此为本任务必须避免的隐性误表述）

## 2. 目标依赖方向和所有权

### 2.1 期望 owner 重新分配

| 关注点 | 期望 owner | 期望依赖方向 |
|--------|----------|------------|
| LLM HTTP / 工具调用通用协议 | 新建 `tool_gateway`（或 `runtime` 子包） | application → tool_gateway（application → port → runtime） |
| NER / 检索 / Fusion | `knowledge`（保留） | composition → knowledge → retrieval port |
| Prompt 构造（含 Context Packing） | `runtime`（拆分自 ai_chat_service） | application → runtime port |
| Skills 调用编排 | `skill_registry`（仅通用 Schema 与 Router） | Router → skill_runner port（不再含业务硬编码） |
| DD 业务（QCC + 报告骨架 + internal_query） | `due_diligence`（回收） | due_diligence → skill port（外部调用 skill_runner） |
| agent_workspace 与 agent_execution | 各自独立 | 通过 composition 编排 |

### 2.2 依赖方向

```
tool_gateway (新) ← runtime ← composition
   ↓
knowledge → tool_gateway port → skill port → due_diligence (via compat adapter)

composition → agent_workspace (port)
composition → agent_execution (port)
agent_workspace ←X→ agent_execution（禁止 direct import，通过 composition 编排）
```

### 2.3 兼容性策略

迁移期间允许 **compatibility adapter**：

- `due_diligence` 业务调用 `skill_registry` 通过**单向** `due_diligence → skill_port` adapter
- `knowledge` 编排层调用 `tool_gateway` 通过**单向** `knowledge → tool_gateway_port` adapter
- 旧的 `direct_rag_compatibility.py` 可保留作为 compatibility adapter（composition 层），**不进入 application 层**

## 3. 允许与禁止的跨 context 调用

### 3.1 允许

- `composition/*` 可同时调用多个 context 的 port
- `application/<ctx_a>` 可调用同一 context 的 `application/<ctx_a>` 和 `infrastructure/<ctx_a>` 和 `domain/<ctx_a>`
- `application/<ctx_a>` 可调用 `application/<ctx_a>/ports` 定义抽象
- `interfaces/api/<ctx_a>` 仅依赖 `application/<ctx_a>` 与 `domain/<ctx_a>`（Router 规则）
- migration 期间：`due_diligence → skill_registry` 通过**单向** port adapter；不允许反向

### 3.2 禁止

- `application/<ctx_a>` → `interfaces/api/<ctx_a>`（layer inversion）
- `application/<ctx_a>` → `interfaces/api/<ctx_b>`（跨 context Router 调用）
- `domain/<ctx_a>` → `infrastructure/<ctx_b>`（跨 context 实现依赖）
- `application/<ctx_a>` → `domain/<ctx_b>`（跨 context domain 依赖）
- `erasure_participant` 跨 context domain import（必须通过 port 抽象或 composition）
- `ai_chat_service.py` 单文件 > 1000 行（必须按职责拆分）
- `skill_runner.py` 含 DD/QCC 业务硬编码（必须迁移至 due_diligence）

## 4. compatibility adapter 边界

允许的 compat adapter 形态：

- `composition/compat_*.py`：composition 层 compat adapter，可调用多个 context 的 port
- `application/<ctx_a>/compat_<ctx_b>.py`：单 context 内 compat adapter（仅 port 抽象，不直 import 业务）
- `infrastructure/<ctx_a>/port_<ctx_b>_adapter.py`：port 适配层（类型转换专用）

不允许的 compat adapter 形态：

- `application/<ctx_a>/<业务逻辑>`（混淆业务）
- `interfaces/api/<ctx_a>/compat_<ctx_b>`（router 路由只能 redirect）
- 跨 context 共享 mutable state 的 compat adapter

## 5. 行为保持要求和非目标

### 5.1 行为保持要求

迁移期间下列行为必须 1:1 保持：

- AI Chat RAG 对话（response 形状、token 计数、错误码）
- Skill 注册、加载、执行（router → skill_runner 路径）
- 企业尽调所有内部问数 + QCC 调用 + 报告骨架
- agent_workspace → agent_execution 的所有兼容性路径（dispatcher → RunCoordinator）
- erasure participant（迁移期间必须保留双向能力，否则 fence ledger 不完整）

### 5.2 非目标

- 不实现 REQ-043 RuntimeProfileResolver / Runtime conformance / 公共 `/turns` endpoint
- 不实现 REQ-047 Extended 的 HumanInput / Approval / ToolCall / Grant / Snapshot / Artifact / Evidence 字段
- 不启动 WS-S2 / WS-S3 / REQ-062 / REQ-063
- 不修改业务测试用例
- 不运行 agent_erasure_backfill
- 不修改 erase_available
- 不触碰 metaedu / metaedu_test / stale refs / 恢复分支 / dangling commit 91fe0290
- 不做整体重写（必须分 Slice，每个 Slice 可独立回滚）

## 6. 完成标准与验证方式

### 6.0 三态语义（readiness / slice acceptance / TD-085 completion）

为避免"启动条件"与"完成条件"语义倒置，本节明确区分三种状态：

| 状态 | 含义 | 触发 | 本 spec 章节 |
|------|------|------|------|
| **Readiness** | 4 项 OQ 全部裁决 + spec/plan 文档矛盾清除 + 工程门禁通过 | 本 PR（[PR #625](https://github.com/MarkDanile/MetaEduBase/pull/625) `docs/td085-boundary-closure-readiness`） | §6.0 + §11 |
| **Slice Acceptance** | 单个 slice 全部通过其"允许文件范围 + 测试 + 验证方式" | 后续 Slice A/B/C/D/E PR（独立可回滚） | §6.1 单项 + plan §1 |
| **TD-085 Completion** | Slice A-E 全部完成 + Slice E 综合验收 + 跨 context 零违规 + 文件规模门禁 pass | 最后一张 Slice E PR squash merge 入 main | §6.1 + plan §8 |

**重要区别**：

- **Readiness 解锁 ≠ TD-085 完成**。Readiness 仅解锁"可启动 Slice A"，不解决 A-E 的实现交付。
- **Slice Acceptance 解锁 ≠ TD-085 完成**。每个 slice 通过仅代表其交付达成，不解锁 TD-085。
- **TD-085 完成 ≠ REQ-043 / WS-S2 / WS-S3 已解除全部阻塞**（§6.3 进一步明确）。

### 6.1 完成标准

本节列出的"完成标准"按所属状态分组：

#### Readiness 标准（启动 Slice A 的硬条件）

1. 4 项 OQ 全部裁决并写入 spec §11（OQ-1/2/3/4 ADR-style）。
2. spec §6.0 / §8 / §9 文档矛盾清除（本 spec 已修订）。
3. plan §0 / §1 / §2 / §3 / §8 stale 表述、slice 依赖真伪、测试策略统一（本 plan 已修订）。
4. `scripts/check-engineering-docs --full` passed（commit `716b82b3` 后已验证）。

#### Slice Acceptance 标准（A-E 各 slice 独立达成）

| Slice | 标准 | 阻断 |
|-------|------|------|
| **A** | `rg "from app\.contexts\.knowledge\.interfaces\.api" packages/server-python/app/contexts/knowledge/application/` 返回 0 行 + LlmProvider port + OpenAIProvider adapter + 测试 pass + 文件规模门禁 pass | 任何测试失败 → 回滚 A → 不进入 B |
| **B** | `wc -l ai_chat_service.py ≤ 500` + Prompt/Tool/Diagnostics 各自文件 ≤ 500 行 + response 形状 byte-identical | 任一文件 > 500 行 → 回滚 → 重新设计边界 |
| **C** | `rg -i "qcc|dd|背调|enterprise_diligence" skill_runner.py` 业务专属分支零行 + dd_query_runner 迁移到 due_diligence + DD 测试路径同步迁移 + due_diligence→skill_registry 单向 port adapter ready | DD 业务测试失败 → 回滚 → 不进入 D |
| **D** | 双向 `rg` 仅基础设施兼容层返回 + FencedExecutionPort 复用 + WorkspaceSnapshotPort 新增（如缺）+ fence ledger 双边不变性测试 pass | 双向 import 残留 1 行 → 回滚 → 不进入 E |
| **E** | 所有 verifier 复跑 + 全量 hermetic 测试 pass + 跨 context dependency graph 零违规 | 任何失败 → 回滚上一个 slice |

#### TD-085 Completion 标准（Slice E 完成后达成）

A-E 全部完成 + Slice E 综合验收通过 + 跨 context 零违规 import + 文件规模门禁 `scan_source_sizes.py` pass。

### 6.2 验证方式

- `grep` 路径扫描：`rg` 证明跨 context 违规 import 归零
- 文件规模：`wc -l` + 仓库 `scan_source_sizes.py`
- hermetic 回归：`pytest` 全 pass
- `scripts/check-engineering-docs`：pass
- `git diff --check`：clean

### 6.3 TD-085 是否完成 ≠ REQ-043 / WS-S2 / WS-S3 已解除全部阻塞

完成 TD-085 **仅**意味着：

- `tool_gateway` 边界已抽离（Port 抽象 ready）
- LLM 调用由 application → ai_router 反向依赖 → application → runtime/tool_gateway port
- skill_runner 不再含业务硬编码（DD 业务回归 due_diligence）
- agent_workspace / agent_execution 互不依赖

TD-085 完成**不**意味着：

- REQ-043 Runtime conformance spec 已冻结
- WS-S2 / WS-S3 / REQ-043 已解除全部阻塞
- 任何 public `/turns` endpoint 已实现
- RuntimeProfileResolver 已实现

REQ-043 必须在 TD-085 完成后才能开始独立 shaping / implementation（仓库规划顺序：REQ-042 → TD-085 → REQ-043）。

## 7. 与现有 spec / plan 的关系

- 本 spec 不修改 REQ-059 架构约束
- 本 spec 不修改 REQ-042（已完成 main）
- 本 spec 不修改 REQ-043（仍 ⚫ Candidate；由本 spec 解锁后可启动 REQ-043 shaping）
- 本 spec 不修改 REQ-047 Extended（仍 🟣 Shaping；其 HumanInput/Approval/ToolCall 等字段依赖于 agent_workspace 与 agent_execution 互不依赖的边界）
- 本 spec 不修改 WS-S2 closeout 报告（PR #622 已 merge）
- 本 spec 与 TD-080 ~ TD-084 无重叠（已分别完成）

## 8. 开放问题（open questions）— readiness 阶段裁决结果

原 Phase 0 §8 中 4 项 OQ 已在 readiness 阶段裁决（见 §11 ADR），消除"§8 在 slices 中明确 / §9 在 readiness 明确"的循环门禁：

- **OQ-1**：`tool_gateway` 是新独立 bounded context 还是 `runtime` 子包？ → **裁决**：runtime 子包（`packages/server-python/app/runtime/`）。详见 §11.1。
- **OQ-2**：`ai_chat_service.py` 拆分后，编排逻辑归 `knowledge` 还是 `tool_gateway`？ → **裁决**：knowledge 保留 NER/检索/Fusion/Diagnostics；runtime 抽 LlmProvider port + OpenAIProvider adapter + prompt_builder + tool_orchestrator。详见 §11.2。
- **OQ-3**：`skill_runner.py` 的"is internal_query"分支是否 REQ-045 兼容要求强制保留？ → **裁决**：必须保留，但理由不是 REQ-045 而是 REQ-046 v2 业务方契约。详见 §11.3。
- **OQ-4**：`erasure participant` 的跨 context mutual import 在迁移期间是 port 抽象还是直接撤除？ → **裁决**：port 抽象保留双向能力，composition 协调 fence ledger 双边不变性。详见 §11.4。

## 9. Spec 完成标准 — 已升级为 readiness 标准

本 spec 进入 "可启动 Slice A" 状态（readiness）的条件（任一不满足则保持 ⚫ 待办）：

- [x] Phase 0 审计 evidence 列出每项关键事实 code:line（spec §0.2）
- [x] 上述 4 项 open question 状态明确（spec §11）
- [x] TD-085 在 technical-debt.md 中事实源 / 证据 / 完成标准 / 验证方式 / 4 项 OQ 决议链接 均已最小更新
- [x] 本 spec 与 REQ-059 不矛盾
- [x] 未越界修改 backend / tests / migration / schema / registry / CI / 门禁
- [x] 工程文档门禁 `scripts/check-engineering-docs --full` passed（commit `716b82b3` 后已验证）
- [x] 当前 PR 仍为 Draft（[PR #625](https://github.com/MarkDanile/MetaEduBase/pull/625) `docs/td085-boundary-closure-readiness`）

进入 readiness 后，**Slice A/B/C/D/E 的实现交付按 plan §1 各 slice 的"允许文件范围 + 测试 + 验证方式"独立执行**，不在本 spec 覆盖。每个 slice 完成后由对应 slice PR 单独评审；TD-085 完成 = Slice E PR squash merge 入 main（详见 §6.0 三态语义）。

## 10. 下游依赖

- **REQ-043**：TD-085 readiness 解锁后启动 REQ-043 shaping；REQ-043 在 TD-085 完成（slice 全部落地 + 测试通过 + 跨 context 零违规）后才能从 ⚫ Candidate 进入 🟣 Shaping → Ready → Implementation
- **REQ-047 Extended**：HumanInput/Approval/ToolCall 等字段依赖于 agent_workspace 与 agent_execution 的 port 抽象；TD-085 Slice D 完成后才能开始 REQ-047 Extended 的字段定义（必须等待 agent_workspace 与 agent_execution 边界稳定）
- **WS-S2 / WS-S3**：**不依赖** TD-085 直接完成（依赖 REQ-043 公共 `/turns`、server-selected launch policy、最小 execution profile、真实 PG submit-loop 端到端）

## 11. ADR（Architecture Decision Records）— 4 项 OQ 裁决

### 11.1 ADR-085-1：`runtime` 路径选择（OQ-1）

- **状态**：Accepted
- **日期**：2026-09-17
- **上下文**：spec Phase 0 §8 OQ-1 提问 `tool_gateway` 是新独立 bounded context 还是 `runtime` 子包？原 plan §1 Slice A 已硬编码 `runtime/application/llm_provider.py` + `runtime/infrastructure/openai_provider.py` 路径，但未明确"为何不建立独立 context"。
- **选项**：
  - **A**：建立独立 `tool_gateway` bounded context（`packages/server-python/app/contexts/tool_gateway/`）。被拒：违反 [architecture.md](../../03-engineering-governance/01-rules/architecture.md#何时更新-architecturemd) "新增 / 删除 / 重定义 bounded context 改变核心运行单元 / 主要集成关系" 硬约束；TD-085 readiness 阶段不建立新 context（避免一次性建立两个新 context 越界）。
  - **B（采纳）**：runtime 作为新增子包（`packages/server-python/app/runtime/`），未来稳定后再评估提升为独立 context。
- **决策**：B。
- **影响**：
  - Slice A 必须新增 `runtime/__init__.py` + `runtime/application/llm_provider.py`（port）+ `runtime/infrastructure/__init__.py` + `runtime/infrastructure/openai_provider.py`（adapter）。
  - Slice B 必须新增 `runtime/application/prompt_builder.py` + `runtime/application/tool_orchestrator.py`。
  - 与 plan §1 文件路径一致，无须修改 plan。
- **被拒方案代价**：A 选项若采纳，TD-085 readiness 必须额外同步 `ARCHITECTURE.md` 顶层架构映射（违反 readiness 阶段"不修改 ARCHITECTURE"硬约束）。

### 11.2 ADR-085-2：`ai_chat_service.py` 拆分后职责归属（OQ-2）

- **状态**：Accepted
- **日期**：2026-09-17
- **上下文**：spec Phase 0 §8 OQ-2 提问 `ai_chat_service.py` 拆分后编排逻辑归 `knowledge` 还是 `tool_gateway`？实际文件结构：`AIChatService` 单 class（行 112）+ 4 个 Pydantic DTO（行 55/61/68/82/98）+ 1015 行（> 1000 行硬边界）。
- **决策**：

| 职责 | 归属 | 文件路径 |
|------|------|---------|
| NER + 检索 + Fusion | `knowledge` 保留 | `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（拆分后剩余部分） |
| Prompt 构造（含 Context Packing） | `runtime` | `packages/server-python/app/runtime/application/prompt_builder.py` |
| LLM 调用 | `runtime` | `runtime/application/llm_provider.py`（port）+ `runtime/infrastructure/openai_provider.py`（adapter） |
| Tool Calling + Dispatch | `runtime` | `runtime/application/tool_orchestrator.py` |
| Diagnostics | `knowledge` | `packages/server-python/app/contexts/knowledge/application/ai_chat_diagnostics.py`（从原文件拆出） |
| Pydantic DTO（ChatRequest/Response/RetrievalTrace/PackedBlock） | `knowledge` 保留 | `packages/server-python/app/contexts/knowledge/application/ai_chat_dto.py`（按需拆出） |

- **影响**：
  - Slice B 完成后 `ai_chat_service.py` 行数 ≤ 500（hard cap）。
  - 与 plan §1 Slice B 拆分方向一致，仅在文件命名上新增 `prompt_builder.py` + `tool_orchestrator.py`（plan §1 已列名）+ `ai_chat_diagnostics.py`（plan §1 未列，本 ADR 补充）。
- **被拒方案**：
  - "全部归 knowledge"——违反 plan §1 Slice B "Prompt 构造 + Context Packing → 迁移至 runtime" 既定方向。
  - "全部归 tool_gateway"——超出 TD-085 scope，tool_gateway 是 REQ-043 范围。

### 11.3 ADR-085-3：`skill_runner.py` `internal_query` 契约保留（OQ-3）

- **状态**：Accepted
- **日期**：2026-09-17
- **上下文**：spec Phase 0 §8 OQ-3 提问 `skill_runner.py` 的"is internal_query"分支是否 REQ-045 兼容要求强制保留？原 spec §8 推测"基于历史 commit msg `Both are optional for REQ-045 backward compat`"。
- **证据收集**：
  - 注释行 144-148 真实文本：`SkillStepResult` 字段 `query_audit_id` points at the `query_audit_log` row for an `internal_query` step. **Both are optional for REQ-045 backward compat.**（"Both" 指 `invocation_audit_id` + `query_audit_id` 两个字段非必填，不是 `internal_query` 本身可选）
  - `internal_query` 实际契约来源 = **REQ-046 v2**：
    - `524d7a32 feat(dd): REQ-046 PR-3 SkillRunner v2 可审计编排 (#446)` 引入 `internal_query` step 类型
    - `ccd9b5d7 feat(dd): REQ-046 PR-5/Slice 4 园区招商背调 SKILL 模板 + internal_query step (#448)` 在 `park_investment_dd.yaml` 模板定义 3 个 `internal_query` step
    - `21309395 feat(dd): REQ-046 AC-8 真实企业端到端 — internal_query 真实链路修复 (#452)` 真实链路修复
  - `internal_query` 真实调用方：`packages/server-python/app/contexts/skill_registry/application/dd_query_runner.py`（258 行）+ `packages/server-python/app/contexts/skill_registry/templates/park_investment_dd.yaml`（3 个 internal_query step）
  - `internal_query` 真实测试：`tests/contexts/skill_registry/test_skill_runner_v2.py` + `test_dd_internal_query_e2e.py` + `test_dd_query_runner.py` + `test_park_investment_dd_template.py`（4 个测试文件覆盖）
- **决策**：`internal_query` **必须保留**，理由不是 REQ-045 兼容而是 REQ-046 v2 业务方契约。Slice C 实施时迁移 `dd_query_runner.py` + `park_investment_dd.yaml` + 4 个测试到 `due_diligence/`，迁移后 due_diligence 通过单向 port adapter 调用 skill_runner 的 `internal_query` 入口。
- **影响**：
  - Slice C 完成后 `skill_runner.py` 行 110/146/194/261/267/407/411 的 `internal_query` 分支**保留**为通用 Skills 入口能力；DD 业务通过 port 调用而非直接注入 `query_runner`。
  - `dd_query_runner.py` 仍是 `internal_query` 的 production 实现，但物理位置从 `skill_registry/application/` 迁移到 `due_diligence/application/`。
- **被拒方案**：
  - "internal_query 是 REQ-045 兼容要求强制保留"（原 spec §8 猜测）——错误归因。REQ-045 不要求 internal_query；REQ-046 才是契约来源。
  - "删除 internal_query"——破坏 REQ-046 v2 业务契约，违反 spec §5.1 行为保持要求。

### 11.4 ADR-085-4：erasure participant 双向依赖通过 composition 协调（OQ-4）

- **状态**：Accepted
- **日期**：2026-09-17
- **上下文**：spec Phase 0 §8 OQ-4 提问 erasure participant 跨 context mutual import 是 port 抽象还是直接撤除？原 plan §1 Slice D 假设"FencedExecutionPort 已存在，确认复用"。
- **证据收集**：
  - `FencedExecutionPort` **已存在**：`packages/server-python/app/composition/execution_fenced_port.py:53 class FencedExecutionPort`
  - 8 处调用方：`agent_control_plane.py:282/301/416/430/446/468/865/869`（composition 层调用）
  - `WorkspaceSnapshotPort` **不存在**（grep 无匹配，plan §1 Slice D 假设"如不存在则新增"验证为不存在）
  - `snapshot_digest` 签名：`packages/server-python/app/contexts/agent_execution/domain/snapshots.py:149 def snapshot_digest(snapshot: _FrozenSnapshot | Mapping[str, Any]) -> str`（纯函数无状态）
  - 当前双向 import 真实存在：
    - `agent_workspace/infrastructure/workspace_transport_erasure_participant.py:241 from app.contexts.agent_execution.domain.snapshots import snapshot_digest`（workspace ← execution domain）
    - `agent_execution/infrastructure/execution_erasure_participant.py:79-88 from app.contexts.agent_workspace.domain import (...)` 等多处（execution ← workspace）
- **决策**：**port 抽象保留双向能力**，composition 协调 fence ledger 双边不变性。具体：
  - **Slice D 必须**：
    - 复用 `FencedExecutionPort`（已存在于 composition 层），不重新建立
    - 新增 `WorkspaceSnapshotPort` 到 `packages/server-python/app/contexts/agent_workspace/application/ports.py`（plan 假设验证为不存在，本 ADR 确认新增）
    - 双向 erasure participant 改为通过 port + composition 协调；`snapshot_digest` 调用下沉到 `composition/runtime_snapshot.py` 作为共享 helper（**不通过 direct import，而是 composition 层工具调用**）
  - **Slice D 必须保持**：fence ledger 双边不变性（REQ-059 AC-3 + REQ-047 S6-15.5 路由表冻结项）
- **影响**：
  - Slice D 完成后 `agent_workspace` 不再直接 import `agent_execution.domain`；`agent_execution` 不再直接 import `agent_workspace.domain/infrastructure`。
  - 双向 erasure participant 能力通过 port 保持（不撤除），满足 fence ledger 双边不变性硬约束。
- **被拒方案**：
  - "直接撤除 erasure participant 双向能力"——违反 REQ-059 AC-3 fence ledger 双边不变性。
  - "snapshot_digest 通过 direct import 跨 context 共享"——绕过 ADR-085-1 runtime 子包路径，回退 layer inversion 旧问题。
