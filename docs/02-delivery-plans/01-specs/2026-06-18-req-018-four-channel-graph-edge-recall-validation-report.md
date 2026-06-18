# REQ-018 P2 4通道图谱关系召回 — 真实PG验收报告

> 生成时间: 2026-06-18
> 依赖: REQ-015 PG 环境（dev DB + knowledge_edges 数据 + LLM provider）

## 环境

- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- LLM provider: `deepseek`（授权用户）

## 验收目的

验证 REQ-018 Slice 1-3 在真实PG环境下的行为：

1. **4通道并行召回**：vector / keyword / graph_node / graph_edge 并发执行，单通道失败不影响整体
2. **graph_edge通道有效**：edge召回到的chunk不被keyword/vector覆盖
3. **trace区分**：diagnostics.retrieval_topn包含4个独立通道键
4. **去重合并**：同一chunk被多通道命中共用evidence_id，不重复污染sources

## 验收问题

### Q1 — 课程先导知识（edge召回验证）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | 学习这门课前需要哪些先导知识？ | | |
| retrieval_topn.graph_edge 非空 | 是 | | |
| graph_edge项的source_type | knowledge_edge | | |
| graph_edge项有有效edge_id | 是 | | |
| edge召回的chunk不在keyword/topK | 是 | | |
| fusion后edge来源仍保留 | 是 | | |

### Q2 — 跨章节关联（edge补充召回验证）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | Python 函数的参数和返回值有什么关系？ | | |
| retrieval_topn.graph_edge 非空 | 是 | | |
| edge召回的chunk content包含"参数"或"返回" | 是 | | |
| 该chunk未被vector或keyword通道召回 | 是 | | |
| fusion后该chunk排名合理 | 是 | | |

### Q3 — 强关键词基线（edge不必须场景）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| query | Python 函数定义 | | |
| keyword通道已能稳定召回相关chunk | 是 | | |
| graph_edge通道可选（有则好） | 是 | | |
| 整体回答质量不受edge影响 | 是 | | |

## 4通道Trace样例

```json
{
  "retrieval_topn": {
    "vector": [...],
    "keyword": [...],
    "graph_node": [...],
    "graph_edge": [...]
  },
  "fusion_topn": [...],
  "packed_blocks": [...]
}
```

## 结论

- [ ] AC-1：4通道并行，任一通道失败可降级
- [ ] AC-2：graph edge通道命中的关系最终回源到chunk/section
- [ ] AC-3：trace中能看到graph edge topN、关联节点、回源chunk
- [ ] AC-4：重复evidence合并channels，不重复污染sources
- [ ] AC-5：至少2个真实样例证明关系召回补足keyword/vector不稳定问答
- [ ] AC-6：现有graph node → chunk hydration行为不回归
