# TD-050 `EvidenceItem` 缺 `source_chunk_id` 字段 / spec 与实现错位 — Plan（路线 A2）

> Plan 入口：TD-050（路线 A2，2026-06-11 用户拍板）。本文件是实施步骤的事实源；规格口径与候选路线对比在 [TD-050 spec](../01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md)。
> 任务卡：[`docs/03-engineering-governance/technical-debt.md#td-050`](../../03-engineering-governance/technical-debt.md#td-050-evidenceitem-缺-source_chunk_id-字段--spec-与实现错位)
> 工作台：[`docs/03-engineering-governance/current-work.md`](../../03-engineering-governance/current-work.md)（任务卡：TD-050 行，状态 `🟡 进行中`）
> 上一级：[REQ-010 实施 spec §3.1 AC-3](../01-specs/2026-06-10-req-010-rag-evidence-governance.md) + [REQ-010 实施 plan Step 3.1](../02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md)
> 后续接力：[REQ-012 RAG 多路召回与知识图谱证据链收口](../../01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md)（TD-050 是 REQ-012 启动的前置依赖）

## 1. 范围与硬约束

- **路线**：A2（用户 2026-06-11 拍板，详见 spec §4）。
- **业务代码改动 4 个文件**（全部在 `packages/server-python/` 内）。
- **新 pytest 2 条**（`tests/contexts/knowledge/` 目录下）。
- **REQ-010 实施 spec 同步 1 处**（L40 字段清单追加 + §3.1 末尾"AC-3 解读说明"）；**REQ-010 实施 plan 同步 1 处**（Step 3.4 同步注 + Follow-up 段新增 FU-F）。
- **0 schema 变更**（`knowledge_nodes.source_chunk_id` 列已存在，TD-046 backfill 后 74.95% → TD-047 升级后 81.91% 节点有值）。
- **0 业务逻辑变更**（不改 `SourceItem` 旧契约 / MCP tool / `RRFFusion` / `FrequencyFusion` / `MetadataFileRecallChannel`）。
- **不在 main 上直接 commit**（已在 `chore/td-050-evidence-item-source-chunk-id-pass-through` 分支）。
- **不在本 PR 引入 REQ-012 启动**（REQ-012 启动时把"TD-050 已收口"作为前置依赖，本任务仅闭合 TD-050）。
- **不在本 PR 重跑 backfill**（`source_chunk_id` 数据已就位；本任务只修数据通路；81.91% 覆盖率不变）。
- **pytest 走 mock 优先**（避免 dev 库 PG 依赖；如需 PG fixture，由 dev 库真跑承载；沿用 TD-046 / TD-047 模式）。

## 2. 切片（独立可提交 / 可回滚）

| Slice | 范围 | 文件数 | 提交 | 独立可回滚？ |
|-------|------|------|------|------|
| 1.0 | docs-only：spec L40 字段清单 + §3.1 AC-3 解读说明 + plan Step 3.4 同步注 + Follow-up FU-F | 2 | docs only | ✅ |
| 2.0 | 后端：3 处 SQL 加列 + `RecallResult` 加 2 字段 + `EvidenceItem` 加 1 字段 + `PgGraphRetriever` 改 2 处 + 新 pytest 2 条 | 5（业务） + 2（pytest） | feat(server) | ✅ |
| 3.0 | 跨事实源收口（technical-debt `🟢 完成` + current-work 移出 + work-log 索引 + backlog REQ-012 行同步） | 3-4 | docs only | ✅ |

> **依赖关系**：Slice 1.0 必须在 Slice 2.0 之前合并（spec 同步先行，避免代码与 spec 再漂）。Slice 3.0 在 Slice 2.0 PR 合并后立即执行（不留占位）。

## 3. 切片 1.0：docs-only 同步

> 目的：先把 spec 字段清单口径对齐，再动代码。

### Step 1.1 — REQ-010 实施 spec L40 字段清单追加 `source_chunk_id`

文件：`docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`

- L40 当前：`... / `score` / `channels` (list[str])`。
- 改为：`... / `score` / `channels` (list[str]) / `source_chunk_id` (uuid.UUID | None, node 类型时承载 knowledge_nodes.source_chunk_id，默认为 None)`。
- 不动 L42 / L51（其他段落引用字段时不引用 L40 字段清单字面量；如有 grep 出引用字面量，同步加 `source_chunk_id`）。

### Step 1.2 — REQ-010 实施 spec §3.1 末尾追加"AC-3 解读说明"

文件：同上

- 找到 §3.1 "范围" 段（包含 Frontend 列表之前），在最后一段后追加 1 个新小节"AC-3 解读说明"：

  ```markdown
  ### AC-3 解读说明（TD-050 收口时同步）

  - `EvidenceItem.source_chunk_id` 字段仅在 `source_type == "knowledge_node"` 时填充（与 `chunk_id` 同值）。
  - `source_type == "chunk"` / `"knowledge_edge"` / `"structured_field"` 时 `source_chunk_id` 必须为 `None`（不与"该 evidence 指向原文切片"的语义混淆）。
  - `source_chunk_id` **不**参与 `evidence_id` 派生（避免同一 chunk 被多条 knowledge_node 共享时 evidence_id 冲突）。
  - 与 `RecallResult.source_chunk_id` 字段一一对应；`RecallResult.source_file_id` 同样仅 node 类型时有意义。
  ```

### Step 1.3 — REQ-010 实施 plan Step 3.1 同步注 + §8 风险表加 1 行

文件：`docs/02-delivery-plans/02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md`

- Step 3.1 当前 L131 末尾追加：`（TD-050 收口时同步：PgGraphRetriever 同时写 chunk_id 与 source_chunk_id / file_id 与 source_file_id，详见 spec §3.1 末尾"AC-3 解读说明"）`。
- §8 风险表新增 1 行：

  | `source_chunk_id` 不参与 `evidence_id` 派生，否则同一 chunk 被多条 node 共享时冲突 | `_derive_evidence_id` 函数显式不引用 `source_chunk_id`；单元测试覆盖两条 node 共享同一 chunk 时 evidence_id 仍唯一 |

### Step 1.4 — 不动 `contracts.md`

按 [`docs/03-engineering-governance/01-rules/contracts.md` §"何时更新本文件"](../../03-engineering-governance/01-rules/contracts.md) L98-99 规则："如果只是某个具体接口增加了字段、某次任务补了 shared schema，通常不更新本文件"。`EvidenceItem` 加 `source_chunk_id` 是"具体接口加字段"范畴，不更新本文件。`EvidenceItem` 字段清单段以 REQ-010 实施 spec L40（已在 Step 1.1 同步）作为事实源；`contracts.md` 仅记录"长期契约治理规则"。

**本任务对 `contracts.md` 的 0 改动。**

### 验证（Slice 1.0）

- `python3 scripts/check-engineering-docs` → rc=0
- `git diff --check` → clean
- `rg -n "source_chunk_id" docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md` → 命中：L40 字面量 + §3.1 末尾段（≥ 4 行）
- `rg -n "source_chunk_id" docs/02-delivery-plans/02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md` → 命中：Step 3.4 注 + Follow-up FU-F 行

### 提交

```text
docs(rag): TD-050 slice 1 — EvidenceItem.source_chunk_id spec/plan/contracts sync
```

## 4. 切片 2.0：业务代码 + pytest

> 目的：把 spec / plan 描述的 3 层数据通路真正打通。

### Step 2.1 — 3 处 recall SQL 加列

文件：`packages/server-python/app/contexts/knowledge/application/recall_service.py`

- L36-44 `PgVectorRecallChannel.recall` SQL：
  - 当前：`SELECT n.id, n.title, n.description, n.domain, n.level, n.path, 1 - (n.embedding <=> :vec::vector) AS score`
  - 改为：`SELECT n.id, n.title, n.description, n.domain, n.level, n.path, n.source_file_id, n.source_chunk_id, 1 - (n.embedding <=> :vec::vector) AS score`
- L94-101 `PgKeywordRecallChannel.recall` SQL：同样加 `n.source_file_id, n.source_chunk_id`。
- L151-158 `PgMetadataRecallChannel.recall` SQL：同样加 `n.source_file_id, n.source_chunk_id`。

### Step 2.2 — 3 处 `RecallResult` 构造同步写入

文件：同上

- L47-58 `PgVectorRecallChannel`：3 处 `RecallResult(...)` 构造末尾加 `source_file_id=row["source_file_id"]` / `source_chunk_id=row["source_chunk_id"]`。
- L104-115 `PgKeywordRecallChannel`：同样加。
- L161-172 `PgMetadataRecallChannel`：同样加。

### Step 2.3 — `RecallResult` 加 2 字段

文件：`packages/server-python/app/shared/domain/recall_channel.py`

- L1 添加 `import uuid`（如未添加）。
- L11-19 `RecallResult` 字段末尾追加：
  ```python
  source_file_id: uuid.UUID | None = None
  source_chunk_id: uuid.UUID | None = None
  ```

### Step 2.4 — `EvidenceItem` 加 1 字段

文件：`packages/server-python/app/contexts/knowledge/domain/evidence.py`

- L70-80 `EvidenceItem` 字段在 `chunk_id` 之后追加：
  ```python
  source_chunk_id: uuid.UUID | None = None
  """
  TD-050: 仅在 source_type=="knowledge_node" 时填充；与 chunk_id 同值
  （chunk_id 承载该 node 的 source_chunk_id）。其他 source_type 时为 None。
  不参与 evidence_id 派生（详见 spec §3.1 末尾"AC-3 解读说明"）。
  """
  ```
- `_derive_evidence_id` 函数**不**加 `source_chunk_id` 参数（保持派生规则稳定）。
- `_ensure_evidence_id` 也不引用 `source_chunk_id`。

### Step 2.5 — `PgGraphRetriever` 改 2 处

文件：`packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`

- L51-71（vector channel evidence 构造）：
  - 当前：
    ```python
    EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=None,
        chunk_id=None,
        node_id=r.node_id,
        ...
    )
    ```
  - 改为：
    ```python
    EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=r.source_file_id,        # TD-050: 由 RecallResult 透传
        chunk_id=r.source_chunk_id,      # TD-050: 由 RecallResult 透传
        source_chunk_id=r.source_chunk_id,  # TD-050: 与 chunk_id 同值
        node_id=r.node_id,
        ...
    )
    ```
  - 注：用户拍板路线 A2 是"新增 `source_chunk_id` 字段"（spec §3.2 表述）。`source_file_id` **不**进 `EvidenceItem` model（与 L40 字段清单对齐），只在 `RecallResult` 与 `PgGraphRetriever` 内部用，最终写入 evidence `file_id`。
- L80-99（keyword channel evidence 构造）：同样改。
- 删除 L1-9 docstring 里的旧注释 `knowledge_nodes.source_file_id not surfaced in RecallResult; filled in Slice 5` 整段（`source_file_id` / `source_chunk_id` 已经在 Step 2.1-2.3 surfaced，旧注释变成历史占位）。

### Step 2.6 — 新 pytest：透传测试

新文件：`packages/server-python/tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py`

- 用 mock 注入 `PgVectorRecallChannel` / `PgKeywordRecallChannel`（fake `RecallResult` 含 `source_file_id` / `source_chunk_id`）。
- 调用 `PgGraphRetriever.retrieve(...)`。
- 断言返回的 `EvidenceItem(source_type="knowledge_node")`：
  - `file_id` == fake `source_file_id`
  - `chunk_id` == fake `source_chunk_id`
  - `source_chunk_id` == fake `source_chunk_id`（同值）
  - `node_id` == fake `node_id`
- 边界 fixture 1：`source_chunk_id=None`（file_only 节点）→ 返回 evidence `chunk_id=None` / `source_chunk_id=None`（不伪造）。
- 边界 fixture 2：fake 2 条 node 共享同一 chunk → 2 条 evidence 的 `source_chunk_id` 同值但 `evidence_id` 不同（`evidence_id` 派生只与 `node_id` 相关；`source_chunk_id` 不参与派生）。

### Step 2.7 — 新 pytest：字段访问测试

新文件：`packages/server-python/tests/contexts/knowledge/test_evidence_item_source_chunk_id.py`（或追加到现有 `tests/contexts/knowledge/test_evidence_item.py`，按现有文件分布决定）。

- `EvidenceItem(source_type="knowledge_node", node_id=..., source_chunk_id=...)` → 字段直接可读。
- `EvidenceItem(source_type="chunk", file_id=..., chunk_id=...)` → `source_chunk_id is None`。
- `EvidenceItem(source_type="knowledge_edge", edge_id=...)` → `source_chunk_id is None`。
- `EvidenceItem(source_type="structured_field", structured_path=...)` → `source_chunk_id is None`。
- 派生规则回归：2 条 `source_type="knowledge_node"` evidence 共享同一 `source_chunk_id` 但 `node_id` 不同 → `evidence_id` 不同（不冲突）。

### 验证（Slice 2.0）

- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py tests/contexts/knowledge/test_evidence_item_source_chunk_id.py -v` → 5+ passed（4 个透传 + 4 个字段访问 + 1 个派生回归 = 9 case 起步）
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q` → 60 passed，零回归
- `cd packages/server-python && .venv/bin/python -m pytest tests/ -q` → 326 passed + 1 skipped（TD-047 baseline + 2 个新 pytest）
- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` → rc=0（保留 8 个 TD-049 pre-existing；本债 0 新增）
- `python3 scripts/check-engineering-docs` → rc=0
- `git diff --check` → clean
- `rg -n "source_chunk_id" packages/server-python/app/` → 命中：3 处 SQL SELECT + 3 处 RecallResult 写入 + 2 处 PgGraphRetriever 构造 + 1 处 EvidenceItem model 字段 = 9 处新增
- `rg -n "filled in Slice 5" packages/server-python/app/` → 0 命中（已删除旧注释）

### 行为变化声明（按 `quality-gates.md#行为变化声明检查`）

| 类型 | 描述 |
|------|------|
| **可观察行为变化 1** | `POST /api/v1/ai/chat` 的 `sources`（`EvidenceItem[]`）在 node 类型 evidence 上同时含 `chunk_id` / `source_chunk_id`（同值）和 `file_id`（可能非空）；从 P1 `None` 变可能非空（数据驱动，dev 库 81.91% 节点有值）。 |
| **可观察行为变化 2** | 前端 AI Chat `AiChatView` 的 `[N]` chip 渲染：node 类型 evidence 现在可跳 `/resource/files/:fileId?chunk=:chunkId`（之前只跳 `KnowledgeBaseView` 节点详情）。 |
| **公共 API 变化** | `EvidenceItem` 字段定义新增 1 个可选字段 `source_chunk_id: uuid.UUID | None = None`（向后兼容，默认 None）。`RecallResult` 字段定义新增 2 个可选字段 `source_file_id` / `source_chunk_id`（向后兼容，默认 None）。`RecallChannel` Protocol 形参不变。 |
| **数据库 / migration** | 0 schema 变更。 |
| **不**改变 | `SourceItem` 旧契约 / MCP tool / `RRFFusion` 占位实现 / `FrequencyFusion` 行为 / 现有 326 passed pytest 集合。 |

### 提交

```text
feat(server): TD-050 slice 2 — pass source_chunk_id through recall graph to EvidenceItem
```

## 5. 切片 3.0：跨事实源收口

> 目的：把 TD-050 状态从 `🟡 进行中` → `🟢 完成`，跨 5 事实源同步。

### Step 3.1 — `technical-debt.md` 状态变更

文件：`docs/03-engineering-governance/technical-debt.md`

- L2392 状态行：`🔵 就绪` → `🟢 完成`。
- L2414 段落（"完成标准"）末尾追加交付记录段。
- L2443 段落（"交付记录"）补充：
  - 完成日期 2026-06-11（待 PR 合并后回填）
  - PR / merge commit（待 PR 合并后回填）
  - 验证摘要（plan 期目标态：基于 TD-047 baseline 326 + 1 skipped，加 2 个新 pytest 预期 328 + 1 skipped；knowledge/ai 60 零回归；ruff rc=0 保留 8 个 TD-049 pre-existing；check-engineering-docs rc=0；git diff --check clean。**实际命令与结果待 Slice 2.0 / 3.0 交付时执行后回填到本卡 `交付记录` 段**）
  - 行为变化声明（2 条）
  - 跨事实源收口（5 源）

### Step 3.2 — `current-work.md` 移出"当前进行中"

文件：`docs/03-engineering-governance/current-work.md`

- 当前进行中区 TD-050 行 → 删除（移到"最近完成"）。
- 下一批候选区：不动（REQ-012 候选更新时把"TD-050 已收口"作为前置依赖写进）。
- 最近完成区追加一行（与 TD-046 / TD-047 同行风格一致）。

### Step 3.3 — `work-log.md` 索引追加

文件：`docs/03-engineering-governance/work-log.md`

- 顶部索引表追加一行 `TD-050`。
- 详情段追加（保持与 TD-046 / TD-047 同一索引段），引用 PR / merge commit。

### Step 3.4 — `backlog.md` / `validation-phase.md` REQ-012 行同步（如适用）

文件：`docs/01-product-planning/04-backlog.md` + `docs/01-product-planning/02-milestones/01-validation-phase.md`

- REQ-012 行的"前置依赖"或"已知债"段补"TD-050 已收口"。

### 验证（Slice 3.0）

- `python3 scripts/check-engineering-docs` → rc=0
- `git diff --check` → clean
- `rg -n "TD-050" docs/03-engineering-governance/ docs/01-product-planning/` → 命中：technical-debt 详情 + current-work 最近完成 + work-log 索引 + backlog / validation-phase REQ-012 段

### 提交

```text
docs(governance): TD-050 closure — workbench / debt / work-log / backlog sync
```

## 6. 跨事实源状态同步表

| 事实源 | Slice 1.0 后 | Slice 2.0 后 | Slice 3.0 后 |
|--------|--------------|--------------|--------------|
| `docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md` | L40 / §3.1 同步 | — | — |
| `docs/02-delivery-plans/02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md` | Step 3.1 / §8 同步 | — | — |
| `docs/02-delivery-plans/01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md` | 不变 | 不变 | 不变 |
| `docs/02-delivery-plans/02-plans/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through-plan.md` | 不变 | 不变 | 不变 |
| `docs/03-engineering-governance/01-rules/contracts.md` | 不动（按 contracts.md §"何时更新本文件" L98-99 规则） | — | — |
| `packages/server-python/app/contexts/knowledge/application/recall_service.py` | — | 3 SQL + 3 RecallResult 写入 | — |
| `packages/server-python/app/shared/domain/recall_channel.py` | — | `RecallResult` 加 2 字段 | — |
| `packages/server-python/app/contexts/knowledge/domain/evidence.py` | — | `EvidenceItem` 加 1 字段 | — |
| `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py` | — | 2 处改 + 删旧注释 | — |
| `packages/server-python/tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py` | — | 新建 | — |
| `packages/server-python/tests/contexts/knowledge/test_evidence_item_source_chunk_id.py` | — | 新建（或追加到 test_evidence_item.py） | — |
| `docs/03-engineering-governance/technical-debt.md` | `🔵 就绪` | `🔵 就绪`（业务代码已合入，状态待 Slice 3.0 收口） | `🟢 完成` |
| `docs/03-engineering-governance/current-work.md` | "当前进行中" 行更新 | "当前进行中" 行更新（验证状态补） | 移出"当前进行中" + 进"最近完成" |
| `docs/03-engineering-governance/work-log.md` | — | — | 索引 + 详情 |
| `docs/01-product-planning/04-backlog.md` | — | — | REQ-012 行同步 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` | — | — | REQ-012 行同步（如有） |

## 7. PR 合并顺序与回滚策略

1. **PR-1（docs-only Slice 1.0）**：可独立合并；回滚：直接 revert。plan 期预期：合并后 `check-engineering-docs` 仍 rc=0（**实际验证待执行**）。
2. **PR-2（feat Slice 2.0）**：基于 PR-1 之后的 main 创建；回滚：revert；plan 期预期：与现有 326 passed 集合零冲突（**实际验证待执行**）。
3. **PR-3（docs-only Slice 3.0）**：基于 PR-2 之后的 main 创建；仅文档同步，回滚无业务影响。

合并方式：按 git-workflow "快速交付通道"，每 PR squash merge → 立即更新 `main...origin/main` 干净检查。

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `RecallResult` 加 2 字段破坏现有 `RecallChannel` 契约测试 | TD-030 ([PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139)) 收口后契约测试用 `set(sig.parameters)` 严格校验 Protocol 形参；本任务**不动 Protocol 形参**，只动 `RecallResult` 字段；契约测试不应破，跑全量验证 |
| 旧 326 passed 中有依赖 `RecallResult` 字段集的快照测试 / 序列化测试 | 检索：`rg -n "RecallResult\(" packages/server-python/tests/`，如有，加字段默认值即可不破（`None` 默认） |
| `EvidenceItem` 加 `source_chunk_id` 字段后，前端 / MCP 工具 JSON 序列化会带新字段 | 序列化是稳定的（pydantic 默认 dump all fields）；前端 `packages/web` 应**自动**支持（TS 类型从 codegen 走 / 后端 OpenAPI 同步）；CI 跑 `pnpm typecheck` + 后端 pytest 双重校验 |
| MCP tool 的 tool schema 需要更新（OpenAPI consumers） | 路线 A2 已为 MCP 工具稳定读 `source_chunk_id` 准备 schema；MCP 工具改造不在本 PR 范围（推迟到 REQ-012）；本任务仅闭合 EvidenceItem 字段暴露，不强制 MCP 工具迁移 |
| Slice 2.0 改动 4 个业务文件 + 新 pytest 2 条 = 单 PR 较大 | 风险评估：每个文件改动幅度 ≤ 5 行（recall SQL 加 2 列 / RecallResult 加 2 字段 / EvidenceItem 加 1 字段 / PgGraphRetriever 2 处改 4 行 / 删 1 段 docstring 注释 / 新 pytest 2 文件）；可一次合入 |
| dev 库 PG fixture 不便构造 | pytest 走 mock-based（与 TD-046 / TD-047 同模式）；dev 库真跑承载手工验收 |
| 路线 A2 增加 `source_chunk_id` 字段后，3 个未来 P2 / P3 Neo4j / GraphRAG adapter 也要同步填 | 适配器在 `retrievers/` 目录下，P2 / P3 启动时统一处理；本任务仅修 P1 `Pg*Retriever`；不预动 P2 / P3 adapter 占位实现 |
| 字段命名冲突风险：未来如果新 `source_type` 出现（如 "knowledge_graph"），"source_chunk_id" 语义可能再模糊 | AC-3 解读说明段已显式说明 "仅 `source_type=="knowledge_node"` 时填充"；`_derive_evidence_id` 显式不引用；后续新 source_type 由 P2 / P3 spec 同步加 |

## 9. 验证矩阵汇总

| 类别 | 命令 | 期望 | 切片 |
|------|------|------|------|
| 文档门禁 | `python3 scripts/check-engineering-docs` | rc=0 | 1.0 / 2.0 / 3.0 |
| 后端 ruff | `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` | rc=0（保留 TD-049 pre-existing） | 2.0 |
| 后端全量 pytest | `cd packages/server-python && .venv/bin/python -m pytest -q` | 326 + 2 = 328 passed + 1 skipped | 2.0 |
| 后端聚焦 pytest | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py tests/contexts/knowledge/test_evidence_item_source_chunk_id.py -v` | 9+ passed | 2.0 |
| 知识图谱 + AI Chat 回归 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q` | 60+2 = 62 passed | 2.0 |
| 跨事实源状态 | `rg -n "TD-050" docs/03-engineering-governance/ docs/01-product-planning/` | 命中：technical-debt 详情 + current-work 最近完成 + work-log 索引 + backlog REQ-012 段 | 3.0 |
| git diff 干净 | `git diff --check` | clean | 1.0 / 2.0 / 3.0 |
| 字段命中 | `rg -n "source_chunk_id" packages/server-python/app/` | ≥ 9 命中 | 2.0 |
| 旧注释清除 | `rg -n "filled in Slice 5" packages/server-python/app/` | 0 命中 | 2.0 |
| gh pr checks | `gh pr checks <PR#>` | no checks reported（PR 未配 CI；按 TD-046 / TD-020 模式明示） | 1.0 / 2.0 / 3.0 |
| dev 库真跑 | `python -m app.cli.backfill node-source-chunk --dry-run` | 不破（无 backfill 副作用） | 2.0 |

## 10. 接力项（出账）

- **REQ-012**：启动时 spec 把"TD-050 已收口"作为前置依赖；本任务不预动 REQ-012 spec / plan。
- **`SourceItem` deprecation window（TD-048）**：本任务不预动；与 TD-048 后续接力一致。
- **`SourceItem` ↔ `EvidenceItem` 双契约期间**：node 类型 evidence 现在 `file_id` / `chunk_id` 有值；老 `SourceItem` 字段仍按 TD-048 兼容；前端默认走 evidence 端点（REQ-010 Slice 7）。
- **TD-049**（E402 pre-existing）：与本任务独立，不预动；按 TD-049 任务卡独立 PR 收口。
- **P2 / P3 Neo4j / GraphRAG adapter 升级**：本任务 P1 `PgGraphRetriever` 透传到位；P2 / P3 adapter 启动时复用本任务的"双字段透传"模式。
