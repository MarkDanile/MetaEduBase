# REQ-017 P2 RRF / Weighted RRF 融合排序 — 真实PG验收报告

> 生成时间: 2026-06-18
> 环境: dev DB + knowledge_edges (151条边/193节点)

## 验收目的

验证 RRF / Weighted RRF 在 4 通道召回下的融合排序表现：
1. **AC-4**：正文 chunk 不被目录/简介系统性压低
2. **AC-5**：trace 可复盘每个 evidence 的通道来源和融合分数
3. **AC-7**：REQ-018 graph edge 通道接入后 RRF 正确处理第 4 通道并保留降级能力

---

## Q1 — 正文不被目录系统性压低（AC-4）

**Query**: "Python 函数定义"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| fusion top 中正文 chunk 排前 | 正文优先 | fusion top 10：chunk(index 1-5) > knowledge_node(6-10) | ✅ |
| keyword+vector 双通道 chunk 排名靠前 | 双通道增强 | chunk entries 均含 `['keyword','vector']` channels | ✅ |
| 目录/简介未系统性压制正文 | 正文 > node | 正文 chunk 主导 top 5，graph_node 补充 6-10 | ✅ |

**fusion_topn 详情**:
```
[1-5] chunk  ch=['keyword','vector']  ← 正文 chunk（keyword+vector 双通道）
[6-10] knowledge_node  ch=['graph','keyword']  ← KG 节点（补充）
```

---

## Q2 — trace 分数可解释（AC-5）

**Query**: "Python 函数的参数和返回值有什么关系？"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| retrieval_topn 含 4 通道 | vector/keyword/graph/graph_edge | ✅ | ✅ |
| fusion_topn 含排名依据 | 每个 item 有 channels + score | ✅ | ✅ |
| channel_top_k 可见各通道召回量 | `{"vector":5,"keyword":15,"graph":5,"graph_edge":5}` | ✅ | ✅ |

**diagnostics 结构**:
```json
{
  "retrieval_topn": {
    "vector": [5 items],
    "keyword": [15 items],
    "graph": [5 items, source_type=knowledge_node],
    "graph_edge": [5 items, source_type=knowledge_edge]
  },
  "fusion_topn": [10 items],
  "packed": {
    "channel_top_k": {"vector": 5, "keyword": 15, "graph": 5, "graph_edge": 5},
    "fused_count": 10
  }
}
```

---

## Q3 — graph_edge 第4通道融合（AC-7）

**Query**: "Python 函数的参数和返回值有什么关系？"

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| graph_edge 通道激活 | 5 条 edge items | ✅ | ✅ |
| graph_edge evidence_id 唯一 | `knowledge_edge:{uuid}` | ✅ | ✅ |
| edge items 经 RRF 参与排序 | 各通道权重 0.5 | ✅ | ✅ |
| keyword/vector 过强时 edge 未进 top10 | 预期行为 | ⚠️ | AC-7 通道存在，RRF 正常，未进 top10 因 keyword/vector 更强 |
| 单通道失败不影响整体 | 有 graceful fallback | ✅ | ✅ |

**RRF Score 分析**（权重: vector=1.0, keyword=1.0, graph=0.5, graph_edge=0.5）:
- keyword rank1: 1.0/(60+1) = **0.0164**（主导）
- graph_edge rank1: 0.5/(60+1) = **0.0082**（权重较低时难进 top10）

**结论**: graph_edge 通道正常工作（第4通道激活、evidence_id 唯一）。当前数据下 keyword/vector 已强，RRF 权重差异导致 graph_edge 未挤入 top10 是**预期行为**。

---

## AC 验收结论

| AC | 验收项 | 结果 |
|----|--------|------|
| AC-1 | RRF 作为默认 fusion 接入生产 | ✅ PR #325 已合并 |
| AC-2 | 同 chunk 多通道合并 channels | ✅ evidence_id 去重，channels 合并 |
| AC-3 | 单通道异常不影响整体 | ✅ 4 通道均有 graceful fallback |
| AC-4 | 正文 chunk 不被目录系统性压低 | ✅ 正文 chunk 主导 top5，node 补充 top6-10 |
| AC-5 | trace 可复盘通道来源和分数 | ✅ diagnostics 含 retrieval_topn + fusion_topn + channel_top_k |
| AC-6 | weighted RRF 权重可配置且影响排序 | ✅ channel_weights dict 传入 RRFFusion，有测试覆盖 |
| AC-7 | graph edge 第4通道接入并降级 | ✅ graph_edge 通道激活，4通道均参与 RRF，无单点故障 |
