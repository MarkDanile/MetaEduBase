# TD-070 Plan: vector 召回 query embedding 无超时兜底

> Status: 🟢 完成
> Created: 2026-06-21
> Spec: `docs/02-delivery-plans/01-specs/2026-06-21-td-070-vector-recall-timeout.md`

## 任务模式

技术债（TD-070）。小修，加超时 helper + 3 调用点改造 + 单测。

## 执行步骤

### Slice 1: helper + 调用点 + 单测

1. `embedding_service.py` 新增 `get_embedding_with_timeout(text, timeout=60.0)`（`asyncio.wait_for` + catch TimeoutError → None）。
2. `recall_service.py:32`：`get_embedding_vec(query)` → `get_embedding_with_timeout(query)`（更新 import alias）。
3. `pg_chunk_vector_retriever.py:58`：`get_embedding(embedding_text)` → `get_embedding_with_timeout(embedding_text)`。
4. `router.py:278`：`get_embedding(data.query)` → `get_embedding_with_timeout(data.query)`（:182 写入路径不动）。
5. 新增单测 `test_embedding_service_timeout.py`（或加到现有 embedding_service 测试）：
   - 成功路径：mock `get_embedding` 立即返回 → helper 透传
   - 超时路径：mock `get_embedding` sleep >timeout → helper 返回 None

### Slice 2: 验证

```bash
cd packages/server-python
ruff check app/contexts/knowledge/application/embedding_service.py \
  app/contexts/knowledge/application/recall_service.py \
  app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py \
  app/contexts/knowledge/interfaces/api/router.py \
  tests/contexts/knowledge/test_embedding_service.py
pytest tests/contexts/knowledge/test_embedding_service.py tests/contexts/ai/test_ai_chat_router_req015.py -q
scripts/check-engineering-docs
```

### Slice 3: 文档收口 + Git

- TD-070 ledger 详情 + overview 表行 + backlog 行
- current-work / work-log 同步
- commit + push + PR + squash merge + 删分支 + 同步 main

## 验证矩阵

| 项 | 命令 |
|----|------|
| 风格 | `ruff check` 4 改文件 + 测试 |
| 单测 | `pytest tests/contexts/knowledge/test_embedding_service.py -q` |
| 无回归 | `pytest tests/contexts/knowledge/test_embedding_service.py tests/contexts/ai/test_ai_chat_router_req015.py -q` |
| 门禁 | `scripts/check-engineering-docs` |

## 风险与回退

- 改动限定在 1 helper + 3 调用点 import + 1 单测；`get_embedding` 本身不动，batch/写入路径不受影响。
- 回退：revert 单 commit。
