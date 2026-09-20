# TD-085 Plan: AI Chat / Skill / Agent App 上下文边界收口

> **Status**: 🟣 Shaping（依赖 [TD-085 spec](../01-specs/2026-09-15-td-085-ai-chat-skill-agent-app-boundary-closure.md) readiness 完成；spec §11 4 项 ADR 已裁决）
> **依赖顺序**: REQ-042 → **TD-085** → REQ-043
> **完成标准**: 见 spec §6（layer inversion / ai_chat_service 拆分 / skill_runner DD 解耦 / agent_workspace↔agent_execution mutual import 解除 / 测试覆盖行为保持 / 文件规模门禁）；TD-085 完成 = Slice E 完成后达成；readiness 解锁 = spec §11 4 项 ADR 全部裁决后达成

## 0. base 事实

- main HEAD：`2d47999158ff31fc78ffdc13c7e0bd0e8fcc0dfa`（readiness 起点 base；PR #624 squash mergeCommit）
- TD-085 readiness PR：[PR #625](https://github.com/MarkDanile/MetaEduBase/pull/625) `docs/td085-boundary-closure-readiness`
- TD-085 Phase 0 shaping PR：[PR #624](https://github.com/MarkDanile/MetaEduBase/pull/624) `docs/td085-boundary-closure-shaping`（squash mergeCommit `2d479991`；Original 评分 98/100；5 文件 +648/-14）
- 起点 commit：本 plan 与 spec readiness 更新为同一 Draft PR
- 4 项 OQ 裁决：runtime 子包（OQ-1）/ knowledge 保留 NER-Fusion-Diagnostics / runtime 抽 Prompt-Tool-LLM（OQ-2）/ internal_query 是 REQ-046 v2 契约非 REQ-045 兼容（OQ-3）/ FencedExecutionPort 复用 + WorkspaceSnapshotPort 新增（OQ-4）

## 1. 实现切片（slices）

按"边界倒置修复"+"职责清理"+"互不依赖强制"原则划分 5 个 slice，每个 slice 单独可独立回滚、可独立评审。每个 slice 完成后必须保留全部现有行为契约（不可借机重构业务逻辑）。

### 1.1 真实依赖图（readiness 阶段裁决修正）

原 plan §1 各 Slice 标注"前置：Slice A 完成"，经 code:line 验证后修正为：

```
Slice A (LLM Port 抽离)
  ↓ (LlmProvider port 是 B 的真实依赖)
Slice B (ai_chat_service 拆分)

Slice C (skill_runner DD 解耦 + DD 业务回收)  → 独立（不依赖 A；D 不依赖 C）

Slice D (agent_workspace↔agent_execution mutual import 解除)  → 独立（不依赖 A/B/C；FencedExecutionPort 已存在）

Slice E (综合验证 + 进入 implementation-readiness)  → barrier（依赖 A-D 全部完成）
```

**裁决依据**：
- Slice C 不依赖 A：`skill_runner.py` 当前无 `llm_provider` / `LlmProvider` / `openai_provider` / `runtime.` 引用（grep 无匹配）
- Slice D 不依赖 A：`workspace_transport_erasure_participant.py` + `execution_erasure_participant.py` 均无 `llm_provider` / `LlmProvider` 引用（grep 无匹配）
- Slice C 与 D 相互独立：grep 无相互引用
- Slice E 是 barrier：依赖所有 slice 的 verifier 复跑

**修正影响**：Slice C / D 可与 A 并行实施（不同 PR 不同分支）；B 必须在 A 之后；E 在所有之后。

### 1.2 Slice A：`ai_chat.py` 反向依赖修复与 LLM Port 抽离

**状态**：🟢 已完成（2026-09-20，PR #627 squash mergeCommit `8fb60704` 入 main；Original 评分 95/100；application → interfaces/api 与 application → runtime.infrastructure 反向 import 双向 0 lines；23 runtime 测试 + 35 AI 回归全 pass；CI Backend / Backend iteration / Frontend / Engineering docs 全 SUCCESS）

**目标**：
- `knowledge/application/ai_chat_service.py:565, 589` 与 `hybrid_ner_service.py:93` 的 `from app.contexts.knowledge.interfaces.api.ai_router import ...` 反向 import 全部移除
- 抽离 `runtime.application.llm_provider.LlmProvider` port（abstract interface）+ `runtime.infrastructure.openai_provider.OpenAIProvider` adapter（具体实现）
- `interfaces/api/ai_router.py` 中保留 `_call_llm` 等具体 HTTP 实现，作为 OpenAIProvider 的瘦包装

**允许文件范围**：
- 新增 `packages/server-python/app/runtime/__init__.py` + `runtime/application/llm_provider.py`（port）
- 新增 `packages/server-python/app/runtime/infrastructure/__init__.py` + `runtime/infrastructure/openai_provider.py`（adapter）
- 修改 `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（替换 import + 函数体）
- 修改 `packages/server-python/app/contexts/knowledge/application/hybrid_ner_service.py`（替换 import + 函数体）
- 修改 `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（仅允许删除冗余分支，保留 Router HTTP 路由职责）

**不允许文件范围**：其他 context、tests（除 §3 允许新增）、migration、schema、registry、CI、门禁

**特征测试 / 单元测试**：见 §3 测试策略

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/ai/ tests/runtime/ -v` 全 pass
- `tests/contexts/knowledge/` 全部 hermetic 回归 pass

**风险 / 失败模式 / 停止条件**：
- 风险：行为破坏（response 形状 / token 计数 / 错误码差异）
- 失败模式：OpenAIProvider adapter HTTP 调用错误
- 停止条件：任何测试失败 → 回滚 Slice A → 不进入 Slice B

### 1.3 Slice B：ai_chat_service.py 单文件拆分（> 1000 行 → ≤ 500 行）

**前置**：Slice A 完成（依赖 LlmProvider port 抽离，B 复用 A 的 port）

**目标**：
- `wc -l packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` 从 1015 行降至 ≤ 500 行
- 拆分方向（spec ADR-085-2）：
  - NER + 检索 + Fusion + DTO + Diagnostics → 保留 `knowledge/application/`
  - Prompt 构造 + Context Packing → 迁移至 `runtime/application/prompt_builder.py`
  - LLM 调用 → 已由 Slice A 抽出 LlmProvider
  - Tool Calling → 迁移至 `runtime/application/tool_orchestrator.py`
  - Diagnostics → 拆分至 `knowledge/application/ai_chat_diagnostics.py`（spec ADR-085-2 补充）

**允许文件范围**：
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（拆分）
- 新增 `packages/server-python/app/runtime/application/prompt_builder.py`
- 新增 `packages/server-python/app/runtime/application/tool_orchestrator.py`
- 新增 `packages/server-python/app/contexts/knowledge/application/ai_chat_diagnostics.py`（spec ADR-085-2 补充）
- 新增对应测试文件（见 §3）

**不允许文件范围**：其他 context、已有测试用例、migration、schema、registry、CI、门禁

**集成测试 / 回归矩阵**：
- 全套 hermetic 测试 pass
- response 形状 byte-identical（前后对比 fixture）

**风险 / 失败模式 / 停止条件**：
- 风险：Service 边界划分遗漏导致 circular dependency
- 失败模式：拆分粒度不当导致单文件 < 50 行（违反最小粒度）
- 停止条件：拆分后任一文件 > 500 行 → 回滚并重新设计边界

### 1.4 Slice C：skill_runner.py DD/QCC 解耦 + DD 业务回收至 due_diligence

**前置**：**无**（spec readiness 阶段裁决：Slice C 独立，不依赖 A；与 D 可并行）

**目标**：
- `rg -i "qcc|dd|背调|enterprise_diligence" packages/server-python/app/contexts/skill_registry/application/skill_runner.py` 业务专属分支归零
- `skill_runner.py:103, 110, 407, 411, 538` 的 DD/QCC 硬编码全部迁移
- `skill_runner.py` 缩为通用 Skills Router/Runner（仅 Schema 与编排）
- `dd_query_runner.py` 从 `skill_registry/application/` 迁移至 `due_diligence/application/`
- DD 业务方（due_diligence）通过 port 调用 skill_registry 通用 Runner（单向）
- **保留** `internal_query` step 类型与 `SkillStepResult.query_audit_id` 字段（spec ADR-085-3：REQ-046 v2 契约非 REQ-045 兼容）
- `park_investment_dd.yaml` 模板 3 个 `internal_query` step 同步迁移至 due_diligence

**允许文件范围**：
- `packages/server-python/app/contexts/skill_registry/application/skill_runner.py`（缩减）
- `packages/server-python/app/contexts/skill_registry/application/dd_query_runner.py`（迁移）
- 新增 `packages/server-python/app/contexts/due_diligence/application/skill_caller.py`（DD 调用 skill_registry 的 port adapter）
- 新增 `packages/server-python/app/contexts/due_diligence/application/dd_query_runner.py`（迁移后位置）
- 迁移 `packages/server-python/app/contexts/skill_registry/templates/park_investment_dd.yaml` → `packages/server-python/app/contexts/due_diligence/templates/park_investment_dd.yaml`
- 修改 `packages/server-python/app/contexts/due_diligence/interfaces/api/dd_router.py`（仅修改 import 路径）
- 修改 `packages/server-python/app/contexts/skill_registry/interfaces/api/skill_registry_router.py`（仅修改 import 路径）

**不允许文件范围**：其他 context、已有测试用例（除 §3 允许迁移路径）、migration、schema、registry、CI、门禁

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/skill_registry/ tests/contexts/due_diligence/ -v` 全 pass
- response / QCC 调用 / 报告骨架 / internal_query 真实链路 行为保持

**风险 / 失败模式 / 停止条件**：
- 风险：DD 业务丢失（QCC 调用顺序 / internal_query 分支 / 报告骨架 / park_investment_dd.yaml 模板）
- 失败模式：迁移后 DD 业务调用路径错误
- 停止条件：DD 任何业务测试失败 → 回滚 → 不进入 Slice D

### 1.5 Slice D：agent_workspace ↔ agent_execution mutual import 解除

**前置**：**无**（spec readiness 阶段裁决：Slice D 独立，不依赖 A/B/C；FencedExecutionPort 已存在可直接复用）

**目标**：
- `agent_workspace/infrastructure/workspace_transport_erasure_participant.py:241` 的 `from app.contexts.agent_execution.domain.snapshots import snapshot_digest` 反向依赖移除（改用 port 接口或 composition 编排）
- `agent_execution/infrastructure/execution_erasure_participant.py:79-88` 的反向依赖同样移除
- erasure participant 双向能力**保留**（通过 port 抽象，spec ADR-085-4）
- fence ledger 双边不变性保持

**允许文件范围**：
- `packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_transport_erasure_participant.py`
- `packages/server-python/app/contexts/agent_execution/infrastructure/execution_erasure_participant.py`
- 新增 `packages/server-python/app/composition/runtime_snapshot.py`（spec ADR-085-4：`snapshot_digest` 调用下沉为 composition 共享 helper）
- 新增 `packages/server-python/app/contexts/agent_workspace/application/ports.py` 中新增 `WorkspaceSnapshotPort`（spec ADR-085-4：plan §1 假设验证为不存在）

**不允许文件范围**：其他 context、已有测试用例（除 §3 允许新增）、migration、schema、registry、CI、门禁

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/agent_workspace/ tests/contexts/agent_execution/ tests/composition/ -v` 全 pass
- fence ledger 双边不变性测试 pass

**风险 / 失败模式 / 停止条件**：
- 风险：erasure 双边丢失导致 fence ledger 不完整
- 失败模式：cycle dependency 残留
- 停止条件：双向 import 残留 1 行 → 回滚 → 不进入 Slice E

### 1.6 Slice E：综合验证与 entry into TD-085 Completion

**前置**：Slice A-D 全部完成（barrier）

**目标**：
- 复跑所有 verifier：
  - `rg "from app\.contexts\.knowledge\.interfaces\.api" packages/server-python/app/contexts/knowledge/application/` 返回 0 行
  - `wc -l packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` ≤ 500 行
  - `rg -i "qcc|dd|背调" packages/server-python/app/contexts/skill_registry/application/skill_runner.py` 业务专属分支归零
  - `rg "from app\.contexts\.agent_execution" packages/server-python/app/contexts/agent_workspace/` 仅基础设施兼容层
  - `rg "from app\.contexts\.agent_workspace" packages/server-python/app/contexts/agent_execution/` 同条件
- 测试覆盖行为保持：
  - `pytest packages/server-python/tests/contexts/ai/ tests/contexts/skill_registry/ tests/contexts/due_diligence/ tests/contexts/agent_workspace/ tests/contexts/agent_execution/ tests/runtime/ tests/composition/ -v` 全 pass
- 文件规模门禁：`scan_source_sizes.py` pass
- 跨 context 零违规 import

**特征测试 / 单元测试**：
- 不新增测试用例（按 spec 5.2 不增删测试要求）
- 复用全部现有 hermetic 回归测试

**集成测试 / 回归矩阵**：
- 全部现有测试 pass
- 跨 context dependency graph 用 `python -c "import ast; ..."` 或 `rg` 验证

**风险 / 失败模式 / 停止条件**：
- 风险：行为累积偏移
- 失败模式：综合验证脚本自身错误
- 停止条件：任何失败 → 回滚到上一个 slice → 重新评估

## 2. Slice 依赖顺序

见 §1.1 真实依赖图。每个 slice 必须独立可回滚（revert commit）；不强制 bundle release；Slice A/B/C/D 可并行分多个 PR 提交（不同分支），E 必须在所有之后。

## 3. 测试策略（readiness 阶段统一）

消除原 plan "禁止修改 tests" + "要求新增、迁移测试" 的矛盾，统一为以下规则：

| 行为 | 是否允许 | 触发场景 |
|------|---------|---------|
| **不修改**已有测试用例（断言/输入/期望值） | ✅ 强制禁止 | 所有 slice（行为保持硬约束） |
| **允许新增**单元测试 | ✅ 允许 | Slice A 新增 `tests/runtime/test_llm_provider.py`；Slice B 新增 `tests/runtime/test_prompt_builder.py` + `test_tool_orchestrator.py` |
| **允许新增**集成测试 | ✅ 允许 | Slice D 新增 `tests/composition/test_runtime_snapshot.py` |
| **允许迁移**测试文件路径 | ✅ 允许（仅限 Slice C） | `tests/contexts/skill_registry/test_dd_query_runner.py` → `tests/contexts/due_diligence/test_dd_query_runner.py`；`test_dd_internal_query_e2e.py` → `tests/contexts/due_diligence/` |
| **禁止新增**与已存在测试重复 / 反向覆盖 / 跳过现有断言的测试 | ✅ 强制禁止 | 所有 slice |

**全局不允许修改**：
- 所有已有测试用例的代码（断言 / 输入 / 期望值）
- 所有 migration / schema / registry / CI / 门禁 / ERASURE / RBAC
- `packages/server-python/app/main.py`（除非必须新增 import，pure router 注册）
- 任何其他无关 context

## 4. 测试矩阵（统一汇总）

| Slice | 单元（新增） | 集成（新增） | 回归（复用） | E2E | 性能 |
|------|------|------|------|-----|------|
| A | test_llm_provider.py | - | test_ai_chat.py + test_ai_chat_router_req015.py | - | response time 持平 |
| B | test_prompt_builder.py + test_tool_orchestrator.py | - | test_ai_chat.py + test_ai_chat_router_req015.py | - | response 形状 byte-identical |
| C | test_dd_skill_caller.py | - | test_dd_query_runner.py (迁移) + test_dd_internal_query_e2e.py (迁移) + test_park_investment_dd_template.py (迁移) + test_skill_runner_v2.py | - | QCC 调用延迟持平 |
| D | test_runtime_snapshot.py | - | 现有 agent_workspace + agent_execution 测试 | - | fence ledger 不变性 |
| E | 无新增 | 综合 verify | 全部现有 | - | - |

**所有 slice 不修改生产测试用例**。

## 5. 风险 / 失败模式 / 停止条件（统一汇总）

- 跨 slice 边界：响应形状 / token 计数 / 错误码差异 → 立即回滚到上一个 slice
- 行为保持测试套件：任何现有测试失败 → 立即回滚
- fence ledger 完整性：双向 import 残留 → 立即回滚 Slice D
- 文件规模门禁：任一文件 > 1000 行 → 立即回滚 Slice B

## 6. 哪个 slice 完成后才能开始 REQ-043

- **Slice E** 完成后（TD-085 综合验收通过 + TD-085 Completion 状态），可启动 REQ-043 shaping
- REQ-043 仍 ⚫ Candidate → 🟣 Shaping → Ready → Implementation 顺序不变
- **TD-085 单独完成不等于 REQ-043 / WS-S2 / WS-S3 已解除全部阻塞**（此为隐性误表述必须避免）
- REQ-047 Extended 的字段定义（HumanInput/Approval/ToolCall 等）依赖 agent_workspace ↔ agent_execution 边界稳定（Slice D 必须完成）

## 7. 不在 TD-085 范围

- 不实现 REQ-043 RuntimeProfileResolver / Runtime conformance / 公共 `/turns`
- 不实现 REQ-047 Extended 的 HumanInput / Approval / ToolCall / Grant / Snapshot / Artifact / Evidence 字段
- 不启动 WS-S2 / WS-S3 / REQ-062 / REQ-063
- 不修改业务测试用例（已确认，§3 测试策略统一表）
- 不运行 agent_erasure_backfill
- 不修改 erase_available
- 不触碰 metaedu / metaedu_test / stale refs / 恢复分支 / dangling commit 91fe0290
- 不 amend / rebase / force-push / reset

## 8. Plan 完成标准（重复清理后）

本 plan 进入 "TD-085 Completion" 状态：

- [x] Slice A 完成（PR #627 mergeCommit `8fb60704`，Original 95/100）+ 跨 context 零违规 import + 测试 pass + 文件规模门禁 pass
- [ ] Slice B 完成 + ai_chat_service ≤ 500 行
- [ ] Slice C 完成 + skill_runner 零业务硬编码 + DD 业务完整迁移至 due_diligence（含 park_investment_dd.yaml 模板 + 4 个测试迁移）
- [ ] Slice D 完成 + agent_workspace ↔ agent_execution mutual import 解除 + FencedExecutionPort 复用 + WorkspaceSnapshotPort 新增
- [ ] Slice E 完成 + 综合验证 + TD-085 Completion

每完成一个 slice = 该 slice 的「允许文件范围」+「测试」+「验证方式」全部通过。

slice 与 slice 之间不强制连续：可暂停、可分多个 PR 提交、每个 PR 独立评审。

> **重复清理说明**：原 §8 中"E 完成后才解锁 REQ-043"与 §6 重复；readiness 阶段统一在 §6 表达，§8 仅保留 slice 完成标准清单。

## 9. 关联依赖

- [TD-085 spec](../01-specs/2026-09-15-td-085-ai-chat-skill-agent-app-boundary-closure.md) §6.0 三态语义 + §11 4 项 ADR：本 plan §1.1 真实依赖图 + §3 测试策略 + §8 完成标准 的事实源
- [REQ-043](../../01-product-planning/05-requirements/REQ-043-runtime-neutral-agentic-rag-orchestration.md)：Slice E 完成后启动 shaping
- [REQ-047 Extended](../../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)：HumanInput/Approval 字段依赖 Slice D 边界稳定
- [REQ-059](../../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md)：本 plan 实施后 agent_workspace / agent_execution 满足 REQ-059 bounded context 约束
- [architecture.md](../../03-engineering-governance/01-rules/architecture.md)：本 plan 实施后与 Router / composition 规则完全对齐
