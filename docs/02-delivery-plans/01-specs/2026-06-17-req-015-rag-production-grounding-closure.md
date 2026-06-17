# REQ-015 RAG 生产链路 grounding 与真实验收收口 — Spec

Requirement: `docs/01-product-planning/05-requirements/REQ-015-rag-production-grounding-closure.md`
Status: 🟡 Doing

## Goal

把 REQ-013 / REQ-014 从“模块和脚本存在”推进到“生产 AI Chat 默认链路真实使用、可观测、可回归”。本 spec 只收口 P2 RAG grounding 的最小闭环，不引入新基础设施。

## Current Findings

| 问题 | 证据 | 风险 |
|------|------|------|
| 生产服务未注入 `ContextPacker` | `ai_router.py` 默认 service 没有 `context_packer` 参数 | 用户页面可能没有 neighbor / section expansion |
| 接口缺 diagnostics | `EvidenceChatResponse` 只有 `reply/sources/document_sources` | 无法判断召回、融合、prompt 哪一步失败 |
| 验收脚本契约漂移 | 脚本发 `question/top_k`、读 `answer/evidence` | 真 PG 验收跑不通或得出空结论 |
| RRF 未默认启用 | production 仍用 `SimpleFrequencyFusion` | P2-RRF 规划没有进入真实路径 |
| 真实样例缺失 | REQ-014 报告为空 | “Python 基本数据类型”质量无法证明 |

## Target Flow

```text
用户问题
  -> NER
  -> chunk vector / chunk keyword / graph / metadata
  -> RRF / weighted RRF
  -> graph source hydration
  -> ContextPacker: hit chunk + neighbor + section + graph source
  -> prompt with [N] evidence
  -> LLM
  -> reply + sources + document_sources + diagnostics
```

## Diagnostics Contract

`POST /api/v1/ai/chat/evidence` 保持原字段兼容，并新增：

```json
{
  "diagnostics": {
    "query": "...",
    "retrieval_topn": {
      "vector": [{ "index": 1, "evidence_id": "...", "title": "...", "score": 0.9 }],
      "keyword": [],
      "graph": []
    },
    "fusion_topn": [{ "index": 1, "evidence_id": "...", "channels": ["vector"] }],
    "packed_blocks": [
      {
        "evidence_index": 1,
        "chunk_ids": ["..."],
        "title": "...",
        "chars": 512,
        "content": "preview...",
        "expansion_type": "hit|neighbor|section|graph_source"
      }
    ],
    "prompt_preview": "参考证据...",
    "packed": {
      "fused_count": 3,
      "toc_blocks_count": 1,
      "graph_chunks_fetched": 1
    }
  }
}
```

Diagnostics 只用于开发验收和调试；前端可忽略，不破坏现有 UI。

## Acceptance Criteria

- AC-1：生产 endpoint 按请求构造 `AIChatService`，并注入 `ContextPacker(ChunkRepository(session), tenant_id)`。
- AC-2：默认融合实例为 `RRFFusion`，且 `RRFFusion(channel_weights=...)` 单测通过。
- AC-3：`AIChatService.chat()` 返回 diagnostics，包含 retrieval / fusion / packed / prompt preview。
- AC-4：`scripts/validate_real_pg_rag.py ask` 使用 `message/context_window` 请求，并读取 `reply/sources/document_sources/diagnostics`。
- AC-5：mock 回归样例证明“Python 基本数据类型”进入 prompt 的正文内容来自 packed context，不只是 `sources` shape。
- AC-6：graph evidence 带 `source_chunk_id` 时，diagnostics 的 packed block 包含 `graph_source` 或 chunk 内容。
- AC-7：section expansion 可按 `section_path` 拉取同章节 chunk，而不只依赖已加载邻居。
- AC-8：如果本地缺真实 PG / LLM key，只能把真 PG 样例记录为环境阻塞，不得写成通过。

## Compatibility

- `reply`、`sources`、`document_sources` 保持不变。
- `diagnostics` 为新增可选字段；旧前端忽略即可。
- 不改 DB schema。
