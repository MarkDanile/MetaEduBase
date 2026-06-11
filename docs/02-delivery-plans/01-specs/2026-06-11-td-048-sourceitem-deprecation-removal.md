# TD-048 `SourceItem` 旧字段下个迭代删除（契约 deprecation 窗口）— Spec

> Spec 入口：TD-048（技术债事实源 [`docs/03-engineering-governance/technical-debt.md#td-048`](../../../03-engineering-governance/technical-debt.md#td-048-sourceitem-旧字段下个迭代删除契约-deprecation-窗口)）。本文件是 deprecation 收口的验收口径与边界的事实源；实施拆分见 [`2026-06-11-td-048-sourceitem-deprecation-removal-plan.md`](../02-plans/2026-06-11-td-048-sourceitem-deprecation-removal-plan.md)。
> 规划归属：REQ-010 P1 RAG 证据治理（[spec §3.1 AC-3](../01-specs/2026-06-10-req-010-rag-evidence-governance.md#ac-3)）。
> 前置依赖：REQ-010 Slice 3 / 7（EvidenceChatResponse + AiChatView 切到 `/ai/chat/evidence`）已完成；MCP `rag_query_evidence` 已切到 evidence 端点（commit `23a54b1` 自承）。
> 后续接力：TD-050（EvidenceItem 缺 `source_chunk_id` 字段）独立 PR。

## 背景

REQ-009 / REQ-010 Slice 3 决策：AI Chat 端点从 `/ai/chat`（返回 `SourceItem` / `ChatResponse`）升级到 `/ai/chat/evidence`（返回 `EvidenceItem` / `EvidenceChatResponse`），旧 `SourceItem` 字段保留向后兼容（deprecation 窗口）。本债定义"下个迭代删除"的具体范围与验收口径。

事实源漂移历史（2026-06-11 复核时发现）：commit `23a54b1 chore(rag): TD-048 remove SourceItem legacy contract` 在分支 `chore/td-048-remove-sourceitem-legacy-contract` 上但 `main` 未合；`current-work.md` 写"已完成"是事实源漂移。本 spec 由 [PR #196](https://github.com/MarkDanile/MetaEduBase/pull/196) 切片 1 触发，回退到真实状态后在分支 `chore/td-048-remove-sourceitem-legacy-contract-2` 上重新走完整收口。

## 目标

删除 `ai_router.py` 旧 `/ai/chat` 端点及其 `SourceItem` / `ChatResponse` / `_recall_to_source` / `@router.post('/chat')` handler；迁移剩余内部消费方（`test_ai_chat.py` / `test_ai_chat_rag_e2e.py` / `test_p1_demo.py` / REQ-006 矩阵）到 `/ai/chat/evidence` 端点和 `EvidenceItem` DTO。0 业务逻辑变化（仅契约收口）。

## 决策记录（2026-06-11）

- **Q1 — 业务消费方是否已切完？** 答：是。前端 `AiChatView`（REQ-010 Slice 3/7）、MCP `rag_query_evidence` 均已切到 `/ai/chat/evidence`；旧 `/ai/chat` 端点无业务消费方。
- **Q2 — 是否保留 deprecation 窗口？** 答：不保留。`SourceItem` / `ChatResponse` 无业务消费方，继续保留 = 双路径维护成本 + AI Chat 实现可能误用 node-shaped sources（`pg_graph_retriever_source_pass_through` 提示有此类风险）。
- **Q3 — 是否新建 spec/plan？** 答：是。按 `task-modes.md#技术债修复` "跨 3 个以上文件、涉及 API / Schema / 数据一致性 / 安全 / 前端行为的技术债，开工前应补充对应 spec / plan"。本债跨 5 文件（4 业务 + 1 矩阵）+ 涉及 API 契约。

## 范围

### 删除（4 处）

- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
  - `:73 class SourceItem(BaseModel): ...`（L73-80）
  - `:83 class ChatResponse(BaseModel): reply / sources: list[SourceItem]`（L83-85）
  - `:99-108 def _recall_to_source(r: RecallResult) -> SourceItem`
  - `:130-180 @router.post("/chat", response_model=ChatResponse) / async def ai_chat(...)` 旧端点 handler（含 `_run_channel` 旧分支、context_text 拼接、`vector_coro` / `keyword_coro` / `metadata_coro` 3 路调用）

### 迁移（3 测试 + 1 矩阵）

- `packages/server-python/tests/contexts/ai/test_ai_chat.py`：把 `test_chat_with_mock_llm` / `test_chat_no_evidence_returns_fallback` 等调用 `/ai/chat` 的用例迁到 `/ai/chat/evidence`；返回断言从 `SourceItem` 改为 `EvidenceItem`。
- `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py`：e2e 用例端点 + 字段迁移。
- `packages/server-python/tests/e2e/test_p1_demo.py`：P1 演示 e2e 端点迁移。
- `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`：curl 截图段 + sources 字段描述（`/ai/chat` → `/ai/chat/evidence`，`answer` → `reply`，`sources` 字段清单改为 `EvidenceItem`）。

### 保留（不删）

- `ai_router.py:88 class EvidenceChatResponse`（REQ-010 Slice 3 引入的 evidence 端点响应形态）：保留。
- `ai_router.py` 的 `/ai/chat/evidence` endpoint（`@router.post("/chat/evidence", response_model=EvidenceChatResponse)`）：保留。
- `_run_channel` 的 evidence 端点调用：保留。
- 任何 `EvidenceItem` 相关 DTO / 字段：保留。

## 数据模型 / 迁移

无 schema 变更。无 Alembic 迁移。

## 验收口径

### 必跑验证

- 切片 2 业务代码 PR 合并前：`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/ tests/e2e/test_p1_demo.py -q` 退出码 0（mock-based 路径可复现；集成测试若依赖 PG 由 REQ-006 接力）。
- 切片 2 业务代码 PR 合并前：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0（保留 8 个 TD-049 E402 pre-existing 兼容）。
- 切片 2 业务代码 PR 合并后（main 上）：`rg -n "SourceItem|class ChatResponse|_recall_to_source|@router.post\\('/chat'\\)" packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py` 0 命中。
- 切片 2 业务代码 PR 合并后：`rg -n "/ai/chat[^/]" packages/server-python/` 仅命中 `/ai/chat/evidence`，0 个独立 `/ai/chat` 端点。
- 切片 3 跨事实源收口：`rg -n "TD-048" docs/03-engineering-governance/{current-work,technical-debt,work-log}.md` 3 文件全部命中且状态一致（current-work 最近完成 / technical-debt 🟢 完成 / work-log 索引无 ⚠️ 标注）。

### 行为变化声明

- **可观察行为变化 1**：`/ai/chat` 端点被删除；任何仍调用旧端点的客户端会收到 404 / 405。已确认前端 + MCP 均已切，无业务消费方。
- **可观察行为变化 2**：`SourceItem` / `ChatResponse` 旧 DTO 消失；如有任何代码 / 测试 / 文档 import 这些 DTO 会在 `pytest` 收集阶段报 `ImportError`。
- **0 业务逻辑变化**：AI Chat 业务（多路召回 / 融合 / 引用编号 / EvidenceItem 透传）逻辑不变。

### 跨切片硬性约束

- 合并切片 2 前必须确认 `gh pr view` 显示 `mergeable=true` + `gh pr checks` 无阻塞。
- 遵循 `git-workflow.md#完整交付闭环` 的 squash merge + delete-branch + 后续 main 同步。
- 切片 2 完成后由切片 3 收口：workbench / debt / work-log / backlog 跨事实源同步。

## 风险与缓解

1. **测试覆盖盲区**：原 commit `23a54b1` 声称"319 passed + 1 skipped 零回归"，但本切片 2 重跑时沙箱可能不可达 PG。**缓解**：走 mock-based 路径（`tests/contexts/ai/` + `tests/e2e/test_p1_demo.py`），按 REQ-003 / REQ-007 经验明确"mock 路径全绿，依赖 PG 的集成测试在本地 PG 真跑或 CI 接力"。
2. **历史 PR 产物 spec/plan 覆盖**：REQ-010 spec / plan 中 23a54b1 改的 AC-1 端点 + 旧 SourceItem 字段描述由切片 3 收口；不在切片 2 改（避免与 PR #193 / #195 / #181 冲突）。**缓解**：切片 2 提交时 `git diff --name-status` 仅 5 个文件（4 业务 + 1 矩阵）。
3. **DOC-057 验证缺口遗留**：`current-work.md:38` TD-050 摘要缺可复核证据 pre-existing，已由 [PR #196](https://github.com/github.com/MarkDanile/MetaEduBase/pull/196) 入账 DOC-057，由独立 PR 收口，不在切片 2 范围。
4. **代码风格一致性**：新写测试如果用新风格（`async def` / `await`）需与既有测试一致；优先沿用 23a54b1 提供的版本（基线已对齐）。
5. **pytest 沙箱可达性**：沙箱是否可达 PG 决定 pytest 跑法。按 `quality-gates.md#已知门禁状态` "后端完整 pytest 依赖 `metaedu_test` 测试库；新环境运行 `./dev.sh init-test-db` 或 `cd packages/server-python && make init-test-db` 显式初始化"。如果沙箱无 PG，降级为"mock-based 路径全绿，集成测试在 CI / 接力 PR 验证"。

## 跨事实源同步（切片 3 收口范围）

- `current-work.md` "最近完成" 加回 TD-048 一行 + 收口"当前进行中"卡
- `technical-debt.md` 任务总览表 L145 + 任务详情 L2358 翻 🟢 完成 + 补 PR 链接 + merge commit
- `work-log.md` L21 索引行去掉 ⚠️ 标注 + 补 PR / merge commit 字段 + "段落归档"复盘段更新为"已完成"
- 候选区维持 1-3 个候选不变

## 关联事实源

- 任务卡：[`docs/03-engineering-governance/technical-debt.md#td-048`](../../../03-engineering-governance/technical-debt.md#td-048-sourceitem-旧字段下个迭代删除契约-deprecation-窗口)
- 复盘（漂移回退）：[`docs/03-engineering-governance/work-log.md#2026-06-11-td-048-事实源漂移回退`](../../../03-engineering-governance/work-log.md#2026-06-11-td-048-事实源漂移回退)
- 切片 1 PR：[#196](https://github.com/MarkDanile/MetaEduBase/pull/196) `ba7f441`
- 原始未合 commit：`23a54b1`（分支 `chore/td-048-remove-sourceitem-legacy-contract` 已删）作为切片 2 cherry-pick 来源
- 上游决策：REQ-009 / REQ-010 Slice 3（[`spec §3.1 AC-3`](../01-specs/2026-06-10-req-010-rag-evidence-governance.md#ac-3)）
