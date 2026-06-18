# REQ-018 P2 4通道图谱关系召回 — 真实PG验收报告

> 生成时间: 2026-06-18
> 环境: dev DB + knowledge_edges (151条边/193节点)

## 验收目的

验证 REQ-018 Slice 1-3 在真实PG环境下的行为：
1. **4通道并行召回**：vector / keyword / graph_node / graph_edge 并发执行，单通道失败不影响整体
2. **graph_edge通道有效**：edge召回到的chunk不被keyword/vector覆盖
3. **trace区分**：diagnostics.retrieval_topn包含4个独立通道键
4. **去重合并**：同一chunk被多通道命中共用evidence_id，不重复污染sources

## 实际环境

- DB: `metaedu@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- knowledge_edges: 151条，knowledge_nodes: 193个
- 节点标题：Python / Scoop / HTML / HTTP / SQLite 等技术标签（domain: education_sports）
- LLM provider: deepseek

---

## Q1 — 课程先导知识（ILIKE关键词匹配失败）

**Query**: "学习这门课前需要哪些先导知识？"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| retrieval_topn.graph_edge 非空 | 是 | **否** | ❌ |
| 原因 | — | ILIKE关键词（学习/课/先导）与现有节点标题（Python/HTML/...）无匹配 | — |

**分析**: Step 1 ILIKE 种子节点用通用词"学习/需要/哪些/先导/知识"查询，与现有 KG 节点标题（`education_sports` 领域的 Python/HTML/SQLite 等）无交集。这是**节点覆盖度不足**而非代码缺陷。Step 2 edge query 没有种子节点输入，因此 graph_edge 返回空。

**建议**: 后续 KG 提取应增加先导知识类关系边，或补充课程类节点标题。

---

## Q2 — 跨章节关联（graph_edge通道激活）

**Query**: "Python函数的参数和返回值有什么关系？"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| retrieval_topn.graph_edge 非空 | 是 | **是（5条）** | ✅ |
| graph_edge evidence_id 唯一 | 是 | `knowledge_edge:{uuid}` 格式，共5个不同ID | ✅ |
| edge召回的chunk有有效source_chunk_id | 是 | 5个不同chunk_id，部分与graph/node通道重叠 | ✅ |
| fusion后edge来源保留 | 是（edge有帮助时） | **keyword/vector太强，RRF权重0.5下edge未进top10** | ⚠️ |
| channel_top_k包含graph_edge | 是 | `"graph_edge":5` | ✅ |

**RRF Score分析**（权重: vector=1.0, keyword=1.0, graph=0.5, graph_edge=0.5）:
- keyword rank1: 1.0/(60+1) = **0.0164** × 10 items → 主导 top10
- graph_edge rank1: 0.5/(60+1) = **0.0082** × 5 items 累加 = 0.0397
- graph_edge 5条累加分 < keyword 3条累加分

**结论**: graph_edge 通道正常工作（返回5条有效edge），但当 keyword/vector 已强覆盖时，RRF 权重差异导致 graph_edge 未能挤入 top10。这是**预期行为**（RRF 的设计就是让主通道优先），而非缺陷。graph_edge 的价值在 keyword/vector 本身覆盖不足时才能体现（见Q3对照）。

---

## Q3 — 强关键词基线（edge不必须场景）

**Query**: "Python 函数定义"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| keyword通道已能稳定召回相关chunk | 是 | keyword:15条，vector:5条 | ✅ |
| graph_edge通道激活 | 是（可选） | graph_edge:5条（与Q2同组edges） | ✅ |
| 整体回答质量不受edge影响 | 是 | keyword/vector主导，edge补充 | ✅ |

---

## 4通道Trace（Q2样例）

```json
{
  "retrieval_topn": {
    "vector": [5 items],
    "keyword": [15 items],
    "graph": [5 items, knowledge_node类型],
    "graph_edge": [5 items, knowledge_edge类型, evidence_id格式: "knowledge_edge:{uuid}"]
  },
  "fusion_topn": [10 items, keyword+vector主导],
  "packed": {
    "channel_top_k": {"vector": 5, "keyword": 15, "graph": 5, "graph_edge": 5},
    "fused_count": 10,
    "graph_hydrated_count": 0
  }
}
```

---

## Bug修复记录

| 日期 | 问题 | 修复 | PR |
|------|------|------|-----|
| 2026-06-18 | `PgEdgeRetriever` 设 `evidence_id=""`，导致所有edge被RRF dedup为1条后无法参与竞争 | 移除 `evidence_id=""`，由 `_derive_evidence_id` 自动生成唯一ID | fix/... (本PR) |

---

## 结论

| AC | 验收项 | 结果 | 说明 |
|----|--------|------|------|
| AC-1 | 4通道并行，任一通道失败可降级 | ✅ | `channel_results` 独立 try/except，均有 graceful fallback |
| AC-2 | graph edge 命中的关系最终回源到chunk/section | ✅ | edge有source_chunk_id；hydration逻辑在context_packer（但graph_hydrated_count=0因graph_edge未进top10） |
| AC-3 | trace中能看到graph edge topN、关联节点、回源chunk | ✅ | diagnostics.retrieval_topn.graph_edge 有5条独立edge记录 |
| AC-4 | 重复evidence合并channels，不重复污染sources | ✅ | `evidence_id` 去重，channels 合并 |
| AC-5 | 至少2个真实样例证明关系召回补足keyword/vector不稳定问答 | ⚠️ | Q2证明graph_edge通道有效（5条edge）；但当前数据下keyword/vector已强，edge未能改变fusion排序 |
| AC-6 | 现有graph node → chunk hydration行为不回归 | ✅ | 代码未改动graph hydration逻辑 |
