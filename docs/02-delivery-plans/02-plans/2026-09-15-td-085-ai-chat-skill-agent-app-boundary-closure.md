# TD-085 Plan: AI Chat / Skill / Agent App 上下文边界收口

> **Status**: 🟣 Shaping（依赖 [TD-085 spec](../01-specs/2026-09-15-td-085-ai-chat-skill-agent-app-boundary-closure.md) 完成后可启动）
> **依赖顺序**: REQ-042 → **TD-085** → REQ-043
> **完成标准**: 见 spec §6（layer inversion / ai_chat_service 拆分 / skill_runner DD 解耦 / agent_workspace↔agent_execution mutual import 解除 / 测试覆盖行为保持 / 文件规模门禁）

## 0. base 事实

- main HEAD：`448f4f6d27562bcd953bd911b27dfbf3eea9177f`
- 起点 PR：TASK-TD-085-BOUNDARY-CLOSURE-SHAPING Phase 0 spec 已冻结
- 起点 commit：本 plan 与 spec 同一 Draft PR

## 1. 实现切片（slices）

按"边界倒置修复"+"职责清理"+"互不依赖强制"原则划分 5 个 slice，每个 slice 单独可独立回滚、可独立评审。每个 slice 完成后必须保留全部现有行为契约（不可借机重构业务逻辑）。

### Slice A：`ai_chat.py` 反向依赖修复与 LLM Port 抽离

**目标**：
- `knowledge/application/ai_chat_service.py:565, 589` 与 `hybrid_ner_service.py:93` 的 `from app.contexts.knowledge.interfaces.api.ai_router import ...` 反向 import 全部移除
- 抽离 `runtime.llm_provider.LlmProvider` port（abstract interface）+ `runtime.infrastructure.openai_provider.OpenAIProvider` adapter（具体实现）
- `interfaces/api/ai_router.py` 中保留 `_call_llm` 等具体 HTTP 实现，作为 OpenAIProvider 的瘦包装

**允许文件范围**：
- 新增 `packages/server-python/app/runtime/__init__.py` + `runtime/application/llm_provider.py`（port）
- 新增 `packages/server-python/app/runtime/infrastructure/__init__.py` + `runtime/infrastructure/openai_provider.py`（adapter）
- 修改 `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（替换 import + 函数体）
- 修改 `packages/server-python/app/contexts/knowledge/application/hybrid_ner_service.py`（替换 import + 函数体）
- 修改 `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（仅允许删除冗余分支，保留 Router HTTP 路由职责）

**不允许文件范围**：其他 context、tests、migration、schema、registry、CI、门禁

**特征测试 / 单元测试**：
- 新增 `packages/server-python/tests/runtime/test_llm_provider.py`：验证 port 抽象与 OpenAIProvider adapter 一致性
- 复用 `tests/contexts/ai/test_ai_chat.py` + `tests/contexts/ai/test_ai_chat_router_req015.py` 验证行为保持
- `pytest tests/runtime/test_llm_provider.py tests/contexts/ai/ -v` 全 pass

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/ai/ tests/runtime/ -v` 全 pass
- `tests/contexts/knowledge/` 全部 hermetic 回归 pass

**风险 / 失败模式 / 停止条件**：
- 风险：行为破坏（response 形状 / token 计数 / 错误码差异）
- 失败模式：OpenAIProvider adapter HTTP 调用错误
- 停止条件：任何测试失败 → 回滚 Slice A → 不进入 Slice B

### Slice B：ai_chat_service.py 单文件拆分（> 1000 行 → ≤ 500 行）

**前置**：Slice A 完成

**目标**：
- `wc -l packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` 从 1015 行降至 ≤ 500 行
- 拆分方向：
  - NER + 检索 + Fusion → 保留 `knowledge/application/`（保持 context 内）
  - Prompt 构造 + Context Packing → 迁移至 `runtime/application/prompt_builder.py`
  - LLM 调用 → 已由 Slice A 抽出 LlmProvider
  - Tool Calling → 迁移至 `runtime/application/tool_orchestrator.py`
  - Diagnostics → 保留 `knowledge/application/`

**允许文件范围**：
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（拆分）
- 新增 `packages/server-python/app/runtime/application/prompt_builder.py`
- 新增 `packages/server-python/app/runtime/application/tool_orchestrator.py`
- 新增对应测试文件

**特征测试 / 单元测试**：
- 新增 `tests/runtime/test_prompt_builder.py`：验证 Prompt 构造单元
- 新增 `tests/runtime/test_tool_orchestrator.py`：验证 Tool orchestration
- 复用现有 AI Chat 测试验证行为保持

**集成测试 / 回归矩阵**：
- 全套 hermetic 测试 pass
- response 形状 byte-identical（前后对比 fixture）

**风险 / 失败模式 / 停止条件**：
- 风险：Service 边界划分遗漏导致 circular dependency
- 失败模式：拆分粒度不当导致单文件 < 50 行（违反最小粒度）
- 停止条件：拆分后任一文件 > 500 行 → 回滚并重新设计边界

### Slice C：skill_runner.py DD/QCC 解耦 + DD 业务回收至 due_diligence

**前置**：Slice A 完成（依赖 LLM port 抽象）

**目标**：
- `rg -i "qcc|dd|背调|enterprise_diligence" packages/server-python/app/contexts/skill_registry/application/skill_runner.py` 业务专属分支归零
- `skill_runner.py:103, 110, 407, 411, 538` 的 DD/QCC 硬编码全部迁移
- `skill_runner.py` 缩为通用 Skills Router/Runner（仅 Schema 与编排）
- `dd_query_runner.py` 从 `skill_registry/application/` 迁移至 `due_diligence/application/`
- DD 业务方（due_diligence）通过 port 调用 skill_registry 通用 Runner（单向）

**允许文件范围**：
- `packages/server-python/app/contexts/skill_registry/application/skill_runner.py`（缩减）
- `packages/server-python/app/contexts/skill_registry/application/dd_query_runner.py`（迁移）
- 新增 `packages/server-python/app/contexts/due_diligence/application/skill_caller.py`（DD 调用 skill_registry 的 port adapter）
- 新增 `packages/server-python/app/contexts/due_diligence/application/dd_query_runner.py`（迁移后位置）
- 修改 `packages/server-python/app/contexts/due_diligence/interfaces/api/dd_router.py`（仅修改 import 路径）
- 修改 `packages/server-python/app/contexts/skill_registry/interfaces/api/skill_registry_router.py`（仅修改 import 路径）

**不允许文件范围**：其他 context、tests、migration、schema、registry、CI、门禁

**特征测试 / 单元测试**：
- 修改 `tests/contexts/skill_registry/test_dd_query_runner.py` → 迁移至 `tests/contexts/due_diligence/test_dd_query_runner.py`（仅路径变更）
- 修改 `tests/contexts/skill_registry/test_dd_internal_query_e2e.py` → 迁移至 `tests/contexts/due_diligence/`
- 新增 `tests/contexts/due_diligence/test_dd_skill_caller.py`：验证 DD 通过 port 调用 skill_registry

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/skill_registry/ tests/contexts/due_diligence/ -v` 全 pass
- response / QCC 调用 / 报告骨架 行为保持

**风险 / 失败模式 / 停止条件**：
- 风险：DD 业务丢失（QCC 调用顺序 / internal_query 分支 / 报告骨架）
- 失败模式：迁移后 DD 业务调用路径错误
- 停止条件：DD 任何业务测试失败 → 回滚 → 不进入 Slice D

### Slice D：agent_workspace ↔ agent_execution mutual import 解除

**前置**：Slice A 完成（依赖 LlmProvider port 抽离）

**目标**：
- `agent_workspace/infrastructure/workspace_transport_erasure_participant.py:241` 的 `from app.contexts.agent_execution.domain.snapshots import snapshot_digest` 反向依赖移除（改用 port 接口或 composition 编排）
- `agent_execution/infrastructure/execution_erasure_participant.py:79-88` 的反向依赖同样移除
- erasure participant 双向能力保持（通过 port 抽象）
- fence ledger 双边不变性保持

**允许文件范围**：
- `packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_transport_erasure_participant.py`
- `packages/server-python/app/contexts/agent_execution/infrastructure/execution_erasure_participant.py`
- 新增 `packages/server-python/app/composition/fenced_port.py`（如不存在；FencedExecutionPort 已存在，确认复用）
- 新增 `packages/server-python/app/contexts/agent_workspace/application/ports.py` 中新增 `WorkspaceSnapshotPort`（如不存在）

**不允许文件范围**：tests、migration、schema、registry、CI、门禁

**特征测试 / 单元测试**：
- 复用 `tests/contexts/agent_workspace/` 与 `tests/contexts/agent_execution/` 中现有 erasure participant 测试
- 新增 `tests/composition/test_fenced_port.py`（如 FencedExecutionPort 复用则跳过）

**集成测试 / 回归矩阵**：
- `pytest tests/contexts/agent_workspace/ tests/contexts/agent_execution/ tests/composition/ -v` 全 pass
- fence ledger 双边不变性测试 pass

**风险 / 失败模式 / 停止条件**：
- 风险：erasure 双边丢失导致 fence ledger 不完整
- 失败模式：cycle dependency 残留
- 停止条件：双向 import 残留 1 行 → 回滚 → 不进入 Slice E

### Slice E：综合验证与 entry into implementation-readiness

**前置**：Slice A-D 全部完成

**目标**：
- 复跑所有 verifier：
  - `rg "from app\.contexts\.knowledge\.interfaces\.api" packages/server-python/app/contexts/knowledge/application/` 返回 0 行
  - `wc -l packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` ≤ 500 行
  - `rg -i "qcc|dd|背调" packages/server-python/app/contexts/skill_registry/application/skill_runner.py` 业务专属分支归零
  - `rg "from app\.contexts\.agent_execution" packages/server-python/app/contexts/agent_workspace/` 仅基础设施兼容层
  - `rg "from app\.contexts\.agent_workspace" packages/server-python/app/contexts/agent_execution/` 同条件
- 测试覆盖行为保持：
  - `pytest packages/server-python/tests/contexts/ai/ tests/contexts/skill_registry/ tests/contexts/due_diligence/ tests/contexts/agent_workspace/ tests/contexts/agent_execution/ -v` 全 pass
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

```
Slice A (LLM Port 抽离)
  ↓
Slice B (ai_chat_service 拆分)
  ↓
Slice C (skill_runner DD 解耦 + DD 业务回收)
  ↓
Slice D (agent_workspace↔agent_execution mutual import 解除)
  ↓
Slice E (综合验证 + 进入 implementation-readiness)
```

每个 slice 必须独立可回滚（revert commit）；不强制 bundle release。

## 3. 允许文件范围（按 slice）

见每 slice §1 子节。

**全局不允许修改**：
- `packages/server-python/tests/` 已有测试用例（不增删测试用例）
- 所有 migration / schema / registry / CI / 门禁 / ERASURE / RBAC
- `packages/server-python/app/main.py`（除非必须新增 import，pure router 注册）
- 任何其他无关 context

## 4. 测试矩阵（统一汇总）

| Slice | 单元 | 集成 | 回归 | E2E | 性能 |
|------|------|------|------|-----|------|
| A | test_llm_provider.py | test_ai_chat.py | test_ai_chat_router_req015.py | - | response time 持平 |
| B | test_prompt_builder.py / test_tool_orchestrator.py | test_ai_chat.py | test_ai_chat_router_req015.py | - | response 形状 byte-identical |
| C | test_dd_query_runner.py (迁移路径) / test_dd_skill_caller.py | test_skill_runner_v2.py / test_dd_internal_query_e2e.py | test_skill_runner.py / test_skill_run_api.py | - | QCC 调用延迟持平 |
| D | 复用现有 erasure 测试 | test_fenced_port.py (新增) | 现有 agent_workspace + agent_execution 测试 | - | fence ledger 不变性 |
| E | 无新增 | 综合 verify | 全部现有 | - | - |

**所有 slice 不修改生产测试用例**。

## 5. 风险 / 失败模式 / 停止条件（统一汇总）

- 跨 slice 边界：响应形状 / token 计数 / 错误码差异 → 立即回滚到上一个 slice
- 行为保持测试套件：任何现有测试失败 → 立即回滚
- fence ledger 完整性：双向 import 残留 → 立即回滚 Slice D
- 文件规模门禁：任一文件 > 1000 行 → 立即回滚 Slice B

## 6. 哪个 slice 完成后才能开始 REQ-043

- **Slice E** 完成后（TD-085 综合验收通过 + implementation-readiness 状态），可启动 REQ-043 shaping
- REQ-043 仍 ⚫ Candidate → 🟣 Shaping → Ready → Implementation 顺序不变
- **TD-085 单独完成不等于 REQ-043 / WS-S2 / WS-S3 已解除全部阻塞**（此为隐性误表述必须避免）
- REQ-047 Extended 的字段定义（HumanInput/Approval/ToolCall 等）依赖 agent_workspace ↔ agent_execution 边界稳定（Slice D 必须完成）

## 7. 不在 TD-085 范围

- 不实现 REQ-043 RuntimeProfileResolver / Runtime conformance / 公共 `/turns`
- 不实现 REQ-047 Extended 的 HumanInput / Approval / ToolCall / Grant / Snapshot / Artifact / Evidence 字段
- 不启动 WS-S2 / WS-S3 / REQ-062 / REQ-063
- 不修改业务测试用例（已确认）
- 不运行 agent_erasure_backfill
- 不修改 erase_available
- 不触碰 metaedu / metaedu_test / stale refs / 恢复分支 / dangling commit 91fe0290
- 不 amend / rebase / force-push / reset

## 8. Plan 完成标准

本 plan 进入 "可实施 slicing" 状态：

- [ ] Slice A 完成 + 跨 context 零违规 import + 测试 pass + 文件规模门禁 pass
- [ ] Slice B 完成 + ai_chat_service ≤ 500 行
- [ ] Slice C 完成 + skill_runner 零业务硬编码 + DD 业务完整迁移至 due_diligence
- [ ] Slice D 完成 + agent_workspace ↔ agent_execution mutual import 解除
- [ ] Slice E 完成 + 综合验证 + implementation-readiness

每完成一个 slice = 该 slice 的「允许文件范围」+「测试」+「验证方式」全部通过。

slice 与 slice 之间不强制连续：可暂停、可分多个 PR 提交、每个 PR 独立评审。

## 9. 关联依赖

- [TD-085 spec](../01-specs/2026-09-15-td-085-ai-chat-skill-agent-app-boundary-closure.md) §6 完成标准：本 plan 是实现入口
- [REQ-043](../../01-product-planning/05-requirements/REQ-043-runtime-neutral-agentic-rag-orchestration.md)：Slice E 完成后启动 shaping
- [REQ-047 Extended](../../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)：HumanInput/Approval 字段依赖 Slice D 边界稳定
- [REQ-059](../../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md)：本 plan 实施后 agent_workspace / agent_execution 满足 REQ-059 bounded context 约束
- [architecture.md](../../03-engineering-governance/01-rules/architecture.md)：本 plan 实施后与 Router / composition 规则完全对齐
