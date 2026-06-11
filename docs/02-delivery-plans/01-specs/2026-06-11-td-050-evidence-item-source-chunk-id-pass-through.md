# TD-050 `EvidenceItem` 缺 `source_chunk_id` 字段 / spec 与实现错位 — Spec

> Spec 入口：TD-050（债务定义补全 2026-06-11）。本文件是债项定义、3 条候选路线对比与推荐路线的事实源；实施 plan 待用户拍板路线后另起文件。
> 任务卡：[`docs/03-engineering-governance/technical-debt.md#td-050`](../../03-engineering-governance/technical-debt.md#td-050-evidenceitem-缺-source_chunk_id-字段--spec-与实现错位)
> 上一级需求：[`REQ-010` spec AC-3](../../01-product-planning/05-requirements/REQ-010-p1-rag-evidence-governance.md) + [REQ-010 实施 spec §3.1](../01-specs/2026-06-10-req-010-rag-evidence-governance.md) + [REQ-010 实施 plan Step 3.1](../02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md)
> 后续接力：[`REQ-012 RAG 多路召回与知识图谱证据链收口`](../../01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md)（TD-050 是 REQ-012 启动的前置依赖）

## 1. 背景

REQ-010 P1 收口时（2026-06-10，8 Slice）把"AI Chat 多路召回统一为 `EvidenceItem`"作为 RAG 证据治理的核心契约。P1 阶段字段清单（REQ-010 实施 spec §3.1 L40）声明 `EvidenceItem` 包含 14 个字段，**不**含 `source_chunk_id`；但同 spec §3.1 AC-3（L100）文字要求 node 类型 evidence 同时含 `node_id` + `source_chunk_id`。

TD-048 收口时 user 把这一不一致点登记为 TD-050（措辞为"`EvidenceItem` 缺 `source_chunk_id` 字段"），但债务细节未补全。本 spec 负责：

1. 把 3 层数据断链（SQL → `RecallResult` → `PgGraphRetriever`）的事实锁死。
2. 列出 3 条候选路线（推荐路线 A1），并明确验收口径。
3. 等用户拍板后，进入 plan 阶段细化。

## 2. 现状快照（事实锁死）

> 本节所有行号 / 文件路径在 2026-06-11 验证；任何变更需重新核对。

### 2.1 数据层 — 列已存在且有数据

- `knowledge_nodes.source_chunk_id` 列 [`app/contexts/knowledge/infrastructure/models.py:38`](../../../packages/server-python/app/contexts/knowledge/infrastructure/models.py) 已存在（UUID FK → `document_chunks`，nullable）。
- `knowledge_nodes.source_file_id` 列同上文件同一 model，已存在。
- TD-046 ([PR #187](https://github.com/MarkDanile/MetaEduBase/pull/187)) 跑 `node-source-chunk` backfill 后覆盖率 74.95%（754 / 1006 节点非 file_only）。
- TD-047 ([PR #192](https://github.com/MarkDanile/MetaEduBase/pull/192)) 升级 ILIKE → `plainto_tsquery('chinese_zh', ...)` 后覆盖率 81.91%（824 / 1006 节点非 file_only；剩 182 file_only 属 REQ-012 embedding 召回范围）。

### 2.2 召回 SQL — 3 个 channel 全部未 SELECT 溯源列

| Channel | 文件 / 行 | SELECT 列 | 缺 |
|---------|-----------|----------|-----|
| `PgVectorRecallChannel` | [`app/contexts/knowledge/application/recall_service.py:36-44`](../../../packages/server-python/app/contexts/knowledge/application/recall_service.py) | `n.id, n.title, n.description, n.domain, n.level, n.path, 1 - (n.embedding <=> :vec::vector) AS score` | `n.source_file_id`, `n.source_chunk_id` |
| `PgKeywordRecallChannel` | `recall_service.py:94-101` | `n.id, n.title, n.description, n.domain, n.level, n.path` | `n.source_file_id`, `n.source_chunk_id` |
| `PgMetadataRecallChannel` | `recall_service.py:151-158` | `n.id, n.title, n.description, n.domain, n.level, n.path` | `n.source_file_id`, `n.source_chunk_id` |

### 2.3 契约层 — `RecallResult` 没有溯源字段

[`app/shared/domain/recall_channel.py:11-19`](../../../packages/server-python/app/shared/domain/recall_channel.py)：

```python
class RecallResult(BaseModel):
    node_id: str
    title: str
    description: str | None = None
    domain: str | None = None
    level: str | None = None
    score: float | None = None
    channel: str = ""
    path: str | None = None
```

**无** `source_file_id` / `source_chunk_id` 字段。

### 2.4 模型层 — `EvidenceItem` 没有 `source_chunk_id` 字段

[`app/contexts/knowledge/domain/evidence.py:61-80`](../../../packages/server-python/app/contexts/knowledge/domain/evidence.py) 14 字段清单与 REQ-010 实施 spec L40 完全一致；**无** `source_chunk_id` 字段。

### 2.5 编排层 — `PgGraphRetriever` 显式 `file_id=None, chunk_id=None`

[`app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py:51-71` / `80-99`](../../../packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py) 两处构造 `EvidenceItem(source_type="knowledge_node", file_id=None, chunk_id=None, ...)`；代码注释自承 `knowledge_nodes.source_file_id not surfaced in RecallResult; filled in Slice 5`，但 Slice 5（KG 抽取按 chunk 切片）实际只写了"插入时记 `source_chunk_id`"（plan Step 5.2），并未改 `RecallResult` / `PgGraphRetriever` 把该字段透传给 `EvidenceItem`。

### 2.6 现状后果

- node 类型 evidence 的 `file_id` / `chunk_id` 在 P1 阶段**始终为 `None`**。
- 前端 AI Chat `[1] / [2]` 引用在 evidence card 渲染时无法拼出 `/resource/files/:fileId?chunk=:chunkId`（[REQ-010 AC-5](../../01-product-planning/05-requirements/REQ-010-p1-rag-evidence-governance.md) 依赖 `chunk_id` + `file_id`）—— 当前 P1 实际行为：node 类型引用回退到 `KnowledgeBaseView` 节点详情（来自 [REQ-010 Slice 7 PR #181](https://github.com/MarkDanile/MetaEduBase/pull/181) 的 [N] chip 降级路径），不跳文件详情。
- 整个 P1 RAG 链路在 node 维度上 **缺最后一公里溯源**，直接挂住 REQ-012 启动（REQ-012 需要把"node → chunk 原文 → embedding 召回"打通，本债不闭合则第一步就是缺的）。

## 3. 候选路线对比

### 3.1 路线 A1（推荐）：`chunk_id` 字段透传 source_chunk_id

**核心改动**（4 处）：

1. **3 个 recall SQL** 各加 `n.source_file_id, n.source_chunk_id`（recurrence-friendly，列已存在）。
2. **`RecallResult`** 新增 `source_file_id: uuid.UUID | None = None` + `source_chunk_id: uuid.UUID | None = None`（保留 `node_id` 等 8 个旧字段；`RecallChannel` Protocol 不动）。
3. **`PgGraphRetriever.retrieve`** 把 `file_id=r.source_file_id, chunk_id=r.source_chunk_id`（`r` 是 `RecallResult`）。
4. **新 pytest** `tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py`：构造 1 个 file + 1 个 chunk + 1 个 knowledge_node（带 `source_chunk_id`），调用 `PgGraphRetriever.retrieve`，验证返回的 `EvidenceItem(source_type="knowledge_node")` 含 `file_id=file_id` / `chunk_id=chunk_id`。

**Spec 调整**：

- REQ-010 实施 spec L40 字段清单**不动**。
- REQ-010 实施 spec L100 AC-3 文字**不动**。
- 在 REQ-010 实施 spec §3.1 末尾或 plan Step 3.1 显式加一行"AC-3 解读说明"：`node 类型 EvidenceItem 用 chunk_id 字段承载 knowledge_nodes.source_chunk_id；file_id 字段承载 knowledge_nodes.source_file_id`（避免再次漂）。

**优点**：

- 改动面小：3 处 SQL + 1 个 model + 1 处 retriever + 1 个新 pytest。
- 零 schema 变更；零 OpenAPI 变更。
- 与 plan Step 3.1 原意（"evidence 的 `chunk_id` 承载 source_chunk_id"）一致。
- 与 REQ-010 Slice 7 前端 [N] chip 降级路径不冲突（chunk 类型 evidence 行为不变；node 类型 evidence 现在能补上 file_id / chunk_id）。

**缺点**：

- `EvidenceItem` 字段语义仍依赖 type discriminator（"node 类型的 `chunk_id` 实际是 source_chunk_id"）—— 如果未来新增第四种 `source_type`，"chunk_id 是否承载 source"会再模糊。
- 第三方消费方（如 MCP tool）直接读 `EvidenceItem.chunk_id` 时需 type-switch；AC-3 文字"node 类型含 `node_id` + `source_chunk_id`"在 schema 层无法直接 grep 出"有 `source_chunk_id` 字段"（需要按 type 判读）。

### 3.2 路线 A2：`EvidenceItem` 新增 `source_chunk_id` 字段

**核心改动**（5 处）：

1-3. 同 A1（3 处 SQL + `RecallResult` 新增字段）。
4. **`EvidenceItem`** 新增 `source_chunk_id: uuid.UUID | None = None` 字段。
5. **`PgGraphRetriever.retrieve`** 同时写 `chunk_id=r.source_chunk_id` 和 `source_chunk_id=r.source_chunk_id`（node 类型时双写；chunk 类型时 `source_chunk_id=None`）。
6. **新 pytest** ×2：① A1 的透传测试；② `EvidenceItem` 字段访问测试（`node` 类型时 `source_chunk_id == chunk_id`）。

**Spec 调整**：

- REQ-010 实施 spec L40 字段清单**追加** `source_chunk_id: uuid.UUID | None = None`。
- REQ-010 实施 spec L100 AC-3 文字**保留**（"node 类型含 `node_id` + `source_chunk_id`" 现在字面成立）。
- 计划解读说明同 A1。

**优点**：

- AC-3 文字字面成立，不再有"字段清单 vs AC 文字"漂移。
- 第三方消费方直接读 `source_chunk_id` 不必 type-switch。
- P2 / P3 替换为 Neo4j / GraphRAG 时，`source_chunk_id` 是稳定字段名（schema 不变）。

**缺点**：

- `EvidenceItem` 增加 1 个字段，**对 node 类型是冗余**（与 `chunk_id` 同值）。
- 改动面比 A1 略大（多 1 处 model + 多 1 处 retriever 写入 + 多 1 个 pytest）。
- 需要在 `_derive_evidence_id` 中明确：`source_chunk_id` 不参与 evidence_id 派生（避免同一 chunk 被两条 node 共享时 evidence_id 冲突）—— 这是 spec / 代码层需要的新约束。

### 3.3 路线 B（不推荐）：只做 spec 校正

**核心改动**：

- REQ-010 实施 spec §3.1 末尾加"AC-3 解读说明"（同 A1），字面把"`source_chunk_id` 字段"解读为"`chunk_id` 字段承载 source_chunk_id"。
- 不改任何业务代码。

**优点**：

- 0 业务代码改动；风险最低。

**缺点**：

- **不解决** 2.2-2.5 描述的 3 层数据断链：node 类型 evidence 的 `file_id` / `chunk_id` 仍然始终为 `None`。
- 前端 [N] chip 仍走"KnowledgeBaseView 节点详情"降级路径，无法跳文件详情。
- REQ-012 启动时第一步仍缺数据；债未实际闭合。
- 与"按流程处理 TD-050"语义不符（用户登记时意图是"代码缺字段"，不是"spec 漂"）。

## 4. 推荐路线

**用户拍板：路线 A2**。理由（按用户决策时点 2026-06-11 补充）：

1. **AC-3 文字字面成立**："node 类型含 `node_id` + `source_chunk_id`" 在 schema 层直接可 grep 出 `source_chunk_id` 字段，不再依赖"type discriminator + 字段复用" 的隐式约定。
2. **第三方消费方（特别是 MCP tool）可稳定读 `source_chunk_id`**：不需 type-switch；P2 / P3 替换为 Neo4j / GraphRAG 时字段名保持稳定。
3. **冗余可接受**：`chunk_id` 与 `source_chunk_id` 在 node 类型时同值；通过 pydantic model 派生一致性约束（`source_chunk_id` 不参与 `evidence_id` 派生；写入 PgGraphRetriever 时同时填两个字段，read 时 type-switch 选其一）。
4. **与 REQ-012 启动更衔接**：REQ-012 需要把 node → chunk 原文 → embedding 召回打通，稳定的 `source_chunk_id` 字段名能直接被 REQ-012 adapter 消费，不必解释"`chunk_id` 字段在 node 类型下语义为何"。
5. **多 1 个 pytest 覆盖成本可接受**：与 A1 相比多 1 个字段访问测试 + 多 1 处 model 字段 + 多 1 处 retriever 写入；总改动从 6 个文件升到 8 个文件。
6. **A1 路径不作为兜底**：本次 PR 显式选 A2，不预留"未来再升级到 A2"的口子；P2 / P3 升级到 Neo4j / GraphRAG 时 `source_chunk_id` 是稳定契约。

## 5. 验收口径（按路线补全）

### 5.1 路线 A1

#### 5.1.1 文档同步

- REQ-010 实施 spec [`docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`](../01-specs/2026-06-10-req-010-rag-evidence-governance.md) §3.1 末尾追加「AC-3 解读说明」段落（≥ 3 行）：明确 `node` 类型 `EvidenceItem` 的 `chunk_id` 字段承载 `knowledge_nodes.source_chunk_id`，`file_id` 字段承载 `knowledge_nodes.source_file_id`；`source_chunk_id` **不**作为 `EvidenceItem` 独立字段暴露。
- REQ-010 实施 plan Step 3.1 同步加注该解读（避免后续 AI IDE 按"AC-3 字面含 `source_chunk_id` 字段"重蹈漂移）。
- `docs/03-engineering-governance/technical-debt.md` TD-050 任务卡状态 `⚫ 待办` → `🔵 就绪`（路线拍板 + 完成标准 / 验证方式齐全）。
- `docs/03-engineering-governance/current-work.md` 任务卡验证状态更新（路线 + commit / PR）。
- `docs/03-engineering-governance/work-log.md` 追加一行索引（与 TD-046 / TD-047 同一索引段）。

#### 5.1.2 业务代码改动（6 个文件）

1. `app/contexts/knowledge/application/recall_service.py` —— `PgVectorRecallChannel.recall` SQL L36-44 加 `n.source_file_id, n.source_chunk_id`。
2. `app/contexts/knowledge/application/recall_service.py` —— `PgKeywordRecallChannel.recall` SQL L94-101 同样加。
3. `app/contexts/knowledge/application/recall_service.py` —— `PgMetadataRecallChannel.recall` SQL L151-158 同样加。
4. `app/contexts/knowledge/application/recall_service.py` —— 3 处 `RecallResult(...)` 构造各加 `source_file_id=row["source_file_id"]` / `source_chunk_id=row["source_chunk_id"]`。
5. `app/shared/domain/recall_channel.py` —— `RecallResult` 加 `source_file_id: uuid.UUID | None = None` + `source_chunk_id: uuid.UUID | None = None` 字段。
6. `app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py` —— 两处 `EvidenceItem(source_type="knowledge_node", file_id=None, chunk_id=None, ...)` 改为 `file_id=r.source_file_id, chunk_id=r.source_chunk_id`；移除旧注释 `knowledge_nodes.source_file_id not surfaced in RecallResult; filled in Slice 5`（因为本 PR 把它 surfaced 了）。

#### 5.1.3 新 pytest

- `tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py`：构造 1 个 file + 1 个 chunk + 1 个 knowledge_node（带 `source_chunk_id` 和 `source_file_id` 都已写入），调用 `PgGraphRetriever.retrieve(query, ner, tid, session, top_k=1)`，断言返回的 `EvidenceItem.source_type == "knowledge_node"` 且 `file_id == file_id` 且 `chunk_id == chunk_id`。
- 边界：若 `source_chunk_id IS NULL`（file_only 节点），返回的 evidence `chunk_id` 也必须为 `None`（与数据层一致，不伪造）。
- 若 P1 阶段 dev 库不方便构造 fixture，用 mock / 假 `RecallResult` 注入到 `PgGraphRetriever` 内部 `PgVectorRecallChannel` / `PgKeywordRecallChannel` 实例（避免起 PG）。

#### 5.1.4 验证矩阵

| 验证 | 命令 | 期望 |
|------|------|------|
| 后端全量 pytest | `cd packages/server-python && .venv/bin/python -m pytest -q` | 326 passed + 1 skipped，零回归（TD-047 baseline） |
| 新 pytest | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/knowledge/test_pg_graph_retriever_source_pass_through.py -v` | 1+ passed（具体条数 plan 时定） |
| 知识图谱 + AI Chat 回归 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q` | 60 passed，零回归（TD-030 baseline） |
| ruff | `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` | rc=0（保留 8 个 TD-049 pre-existing 兼容记录，本债范围内 0 新增） |
| check-engineering-docs | `scripts/check-engineering-docs` | rc=0 |
| git diff | `git diff --check` | clean |
| 行数扫描 | `rg -n "source_chunk_id" packages/server-python/app/` | 命中：3 处 SQL SELECT + 3 处 RecallResult 写入 + 2 处 PgGraphRetriever 构造 + 1 处 model = 9 处新增（外加 1 个新 pytest 文件） |
| 行为变化声明 | 检查项 | node 类型 evidence 的 `file_id` / `chunk_id` 从 `None` 变为可能非空（数据驱动，74.95%~81.91% 节点有值）；chunk / structured_field / knowledge_edge 类型 evidence 行为不变 |

#### 5.1.5 行为变化声明（按 `quality-gates.md#行为变化声明检查`）

- **可观察行为变化 1**：`POST /api/v1/ai/chat` 的 `sources`（`EvidenceItem[]`）在 node 类型 evidence 上，`file_id` / `chunk_id` 从恒为 `None` 变为按数据情况填充（dev 库 P1 阶段 81.91% 节点有值）。
- **可观察行为变化 2**：前端 AI Chat `AiChatView` 的 `[N]` chip 渲染：node 类型 evidence 现在可以跳到 `/resource/files/:fileId?chunk=:chunkId`（之前只跳 `KnowledgeBaseView` 节点详情）。
- **公共 API 变化**：`EvidenceItem` 字段定义不变（用户可见契约稳定）。`RecallResult` 内部加 2 个可选字段，但 `RecallChannel` Protocol 形参不变（契约测试不破）。
- **数据库 / migration**：0 schema 变更。
- **不**改变 `SourceItem` 旧契约 / MCP tool / `RRFFusion` 占位实现 / `FrequencyFusion` 行为。

#### 5.1.6 接力项

- 闭合后 `current-work.md` 移出"当前进行中"、进"最近完成"。
- 跨事实源同步（5 事实源）：`technical-debt` / `current-work` / `work-log` / `backlog`（REQ-012 行同步） / `validation-phase`。
- REQ-012 启动时 spec 把"TD-047 + TD-050 已收口"作为前置依赖。

### 5.2 路线 A2

在 5.1 基础上追加：

- 业务代码改动增加 2 个文件：`app/contexts/knowledge/domain/evidence.py`（加字段）+ `app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`（同时写 `chunk_id` 与 `source_chunk_id`）。
- 文档同步额外改 REQ-010 实施 spec L40 字段清单（追加 `source_chunk_id`）。
- 新 pytest 多 1 条（字段访问测试）。
- 行为变化声明 1 强化：node 类型 evidence 现在同时含 `chunk_id` 和 `source_chunk_id`（同值）；`EvidenceItem(source_type="chunk")` 时 `source_chunk_id=None`。

### 5.3 路线 B（不推荐）

仅文档同步（REQ-010 实施 spec §3.1 末尾"AC-3 解读说明" + plan Step 3.1 同步注）。**0 业务代码改动 / 0 pytest 改动**。验证矩阵：仅 `check-engineering-docs` + `git diff --check`，不跑后端 pytest / ruff。

## 6. 路线拍板前的硬约束

- 0 业务代码改动（除路线 A1 / A2 明确列出的 6 / 8 个文件外）。
- 不改 P1 RAG 数据基线（`node_source_chunk` 74.95% → 81.91% 已是 TD-047 收口时锁定事实，本债不再跑 backfill）。
- 不动 `RRFFusion` / `FrequencyFusion` / `MetadataFileRecallChannel` / `SourceItem` deprecation（TD-048 范围）。
- 不在 main 上直接 commit。

## 7. 与既有事实源的对齐

- [`docs/03-engineering-governance/01-rules/contracts.md`](../../03-engineering-governance/01-rules/contracts.md)：P1 不动 `EvidenceItem` 用户可见契约（路线 A1）；路线 A2 改 `EvidenceItem` schema 需更新 `contracts.md` 的 `EvidenceItem` 字段清单段。
- [`docs/03-engineering-governance/01-rules/architecture.md`](../../03-engineering-governance/01-rules/architecture.md)：adapter 边界 4 个接口（`ChunkRetriever` / `GraphRetriever` / `MetadataFilter` / `EvidenceFusion`）不动。
- [`docs/03-engineering-governance/01-rules/testing.md`](../../03-engineering-governance/01-rules/testing.md)：新 pytest 走 `tests/contexts/knowledge/` 已有风格（mock-based 优先；dev 库 PG 验证次选）。
- [`docs/03-engineering-governance/01-rules/quality-gates.md`](../../03-engineering-governance/01-rules/quality-gates.md)：行为变化声明检查 + 验证矩阵按本 spec §5.1.4 / §5.1.5 执行。
- [`docs/03-engineering-governance/01-rules/git-workflow.md`](../../03-engineering-governance/01-rules/git-workflow.md)：分支 `chore/td-050-evidence-item-source-chunk-id-pass-through`（已建，2026-06-11）；合并按"快速交付通道"执行。
- [`docs/03-engineering-governance/technical-debt.md`](../../03-engineering-governance/technical-debt.md) TD-050 任务卡：状态变更与本 spec 同步。

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `RecallResult` 加 2 字段破坏现有 `RecallChannel` 契约测试 | TD-030 ([PR #139](https://github.com/MarkDanile/MetaEduBase/pull/139)) 收口后契约测试用 `set(sig.parameters)` 严格校验 Protocol 形参；本债**不动 Protocol 形参**，只动 `RecallResult` 字段；契约测试不应破，跑全量验证 |
| 旧 319+ passed 中有依赖 `RecallResult` 字段集的快照测试 / 序列化测试 | 检索：`rg -n "RecallResult\(" packages/server-python/tests/`，如有，加字段默认值即可不破（`None` 默认） |
| 路线 A1 实施后，前端 `AiChatView` 仍 type-switch 处理 `chunk_id` 为 `None` 情况 | dev 库 + e2e 跑 P1 样例（与 TD-046 同基线）；如有 "chunk_id 仍 None" 降级路径报错，再回到路线 A2 |
| 路线 A2 增加 `source_chunk_id` 字段后，第三方消费方 / MCP 工具用 `EvidenceItem.model_dump()` 序列化会带新字段 | 序列化是稳定的（pydantic 默认 dump all fields）；MCP 工具 schema 需更新；按 plan 阶段同步检查 |
| 路线 B 仅文档改动不闭合债 | 明确"债未实际闭合"作为路线 B 的输出，在 work-log / 验证摘要里写明"债务定义已澄清；数据断链留给后续债" |
| 用户不拍板 | 默认按 A1 推进；用户评审 PR 时若要求 A2 / B，按评审意见调整；不动本 spec 推荐路线结论（spec 是事实源） |
