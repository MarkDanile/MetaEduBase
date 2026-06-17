# REQ-018 Spec: P2 4 通道并行召回与图谱关系召回

> Status: 🟣 Shaping
> Created: 2026-06-18
> Source: P2-RECALL-4 Open Item

## 1. Problem Statement

当前 AI Chat 生产链路有 3 个并行召回通道（chunk vector、chunk keyword、graph node），但 graph node 召回是**节点级召回**而非**关系级召回**。用户问"这门课需要哪些先导知识？"时，仅靠 keyword / vector 可能无法召回跨章节的先导知识。

需要在 `knowledge_edges` 上新增**图谱关系召回通道**，将"课程 A → 先导课程 B"这类跨节点关系转化为检索线索，最终仍回源到 chunk / section evidence。

## 2. Goal

建立 P2 4 通道并行召回架构，新增 `knowledge_edges` graph edge 召回通道，使 AI Chat 在关系推理类问答上获得更好的召回质量。

## 3. Architecture

### 3.1 通道定义

| 通道 | 实现 | source_type | 说明 |
|------|------|-------------|------|
| chunk_vector | `PgChunkVectorRetriever` | `chunk` | embedding 最近邻 |
| chunk_keyword | `PgChunkKeywordRetriever` | `chunk` | tsvector + ILIKE |
| graph_node | `PgGraphRetriever` | `knowledge_node` | knowledge_nodes 查询（已有） |
| **graph_edge（新增）** | `PgEdgeRetriever` | `knowledge_node` | knowledge_edges 关系查询 |

### 3.2 `PgEdgeRetriever` 召回路径

```
User Query
    │
    ├─► knowledge_nodes 查询（query 匹配 title/description）
    │       获取 top-k 节点 IDs
    │
    ├─► knowledge_edges：查这些节点的 source_id / target_id 关系
    │       获取相关节点 IDs（排除自身）
    │
    ├─► 回源到 source_chunk_id / source_file_id
    │       或相邻 chunk / section
    │
    └─► 返回 EvidenceItem(source_type="knowledge_node", channels=["graph_edge"])
```

### 3.3 `knowledge_edges` 表结构（已知）

```sql
knowledge_edges(
    id UUID PRIMARY KEY,
    tenant_id UUID FK,
    source_id UUID FK(knowledge_nodes.id),   -- Index: ix_ke_source
    target_id UUID FK(knowledge_nodes.id),   -- Index: ix_ke_target
    relation_type VARCHAR(50),
    weight FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at DATETIME
)
```

### 3.4 降级策略

- `PgEdgeRetriever` 内部 try/except：任一子查询失败返回空列表，不影响其他通道
- AI Chat 层面 `CompositeChunkRetriever`（3 通道）和独立 `graph_edge` 通道并行，channel-level degradation 已由 `CompositeChunkRetriever` 保证
- 4 通道全部失败时：返回空 evidence，走 fallback prompt

### 3.5 数据流

```
AIChatService.chat()
    │
    ├─► CompositeChunkRetriever (vector + keyword) → list[EvidenceItem(source_type=chunk)]
    │
    ├─► PgGraphRetriever (node) → list[EvidenceItem(source_type=knowledge_node)]
    │
    └─► PgEdgeRetriever (edge) → list[EvidenceItem(source_type=knowledge_node)]
                                          │
                                          │ channels=["graph_edge"]
                                          │ source_chunk_id / source_file_id from edge target
                                          ▼
                              EvidenceFusion (RRFFusion)
                                          │
                                          ▼
                              _hydrate_graph_chunks (已有)
                                          │
                                          ▼
                              ContextPacker (已有)
```

### 3.6 EvidenceItem 字段约定

| 字段 | 值 | 说明 |
|------|-----|------|
| `source_type` | `"knowledge_node"` | 保持与 graph_node 一致 |
| `channels` | `["graph_edge"]` | 与 vector/keyword/chunk/graph_node 区分 |
| `node_id` | edge.target_id 或 node.id | 节点 ID |
| `source_chunk_id` | node.source_chunk_id | 回源 chunk |
| `evidence_id` | `f"edge:{edge_id}"` | 可选的 edge ID |

## 4. File Layout

```
packages/server-python/app/contexts/knowledge/application/
├── recall_service.py                   # 修改：PgEdgeRecallChannel（查询 edges 的 channel）
└── retriever_edge.py                   # 新增：PgEdgeRetriever（4 通道之一）

packages/server-python/app/contexts/knowledge/infrastructure/retrievers/
├── pg_edge_retriever.py                 # 新增：PgEdgeRetriever 实现

packages/server-python/app/contexts/knowledge/application/ai_chat_service.py
                                              # 修改：_retrieve 并发 4 通道（已有基础设施）

packages/server-python/tests/contexts/knowledge/retrievers/
├── test_pg_edge_retriever.py            # 新增：PgEdgeRetriever tests
```

## 5. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 4 个召回通道并行执行，任一通道失败其他通道继续 | 单元测试（mock 各通道失败） |
| AC-2 | graph_edge 通道命中的 evidence 通过 `_hydrate_graph_chunks` 回源到 chunk / section | 集成测试 |
| AC-3 | trace 能区分 `graph_edge` / `graph_node` / `keyword` / `vector` 通道来源 | 单元测试 |
| AC-4 | 重复 `source_chunk_id` 与其他通道的 evidence 合并，channels 字段叠加 | 单元测试 |
| AC-5 | 至少 2 个真实样例（课程先导知识 / 跨章节关联）证明关系召回有效 | 真实 PG 验收 |
| AC-6 | 现有 graph_node → chunk hydration 行为不变 | 回归测试通过 |

## 6. Diagnostics Trace

`retrieval_topn` dict 的 channel 键新增 `graph_edge`：

```json
{
  "vector": [...],
  "keyword": [...],
  "graph_node": [...],
  "graph_edge": [
    {
      "evidence_id": "edge:uuid",
      "source_type": "knowledge_node",
      "title": "课程A",
      "channels": ["graph_edge"],
      "metadata": {
        "relation_type": "prerequisite",
        "edge_id": "uuid",
        "source_node_id": "uuid"
      }
    }
  ]
}
```

## 7. Non-Goals

- 不做完整 GraphRAG 社区发现
- 不引入 Neo4j 或图数据库
- 不在本任务内实现 RRF 权重配置（REQ-017 已承接）
- 不替代 `PgGraphRetriever` 的 node 通道，两者独立并行

## 8. Slice 划分建议

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `PgEdgeRecallChannel` + `PgEdgeRetriever` 骨架 + channel contract | — |
| Slice 2 | 接入 `ai_router._build_evidence_service()` + 4 通道并发 | Slice 1 |
| Slice 3 | 通道降级 + trace 区分 + 去重合并 | Slice 2 |
| Slice 4 | 真实 PG 样例验收（课程能力图谱 / Python 问答） | Slice 3 |
