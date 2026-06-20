# TD-069 dev DB Embedding Column Vector Migration — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-19-td-069-embedding-column-vector-migration.md`
> Tech Debt: `docs/03-engineering-governance/technical-debt.md#td-069`
> Base: TD-068 Slice 2 diagnosis (`docs/td-068-slice2-diagnosis-td069-handoff` branch)

## Scope

alembic schema 迁移 `text` → `vector(4096)` + 同步 merge TD-068 Slice 2 暂存代码修复 + knowledge_nodes embedding backfill。报告重跑留独立 PR。

## Slice 1 — Alembic Schema Migration

**目标**：dev DB `document_chunks.embedding` / `knowledge_nodes.embedding` `text` → `vector(4096)`。

**文件**：`alembic/versions/030_embedding_columns_vector_4096.py`（新增）

**核心 SQL**：
```sql
-- document_chunks: 1062 行已有数据，USING expression 保留
ALTER TABLE metaedu.document_chunks
ALTER COLUMN embedding TYPE vector(4096)
USING embedding::vector(4096);

-- knowledge_nodes: 599 行 NULL，USING expression 兼容 NULL
ALTER TABLE metaedu.knowledge_nodes
ALTER COLUMN embedding TYPE vector(4096)
USING embedding::vector(4096);
```

**验证**：
- `alembic upgrade head` 成功
- `alembic downgrade -1` 成功（保留数据）
- `psql` 验证两列类型 + 数据未丢失

## Slice 2 — Merge TD-068 Slice 2 Code Fixes

**目标**：把 `docs/td-068-slice2-diagnosis-td069-handoff` branch 上的暂存代码同步合入。

**文件**：
- `packages/server-python/app/contexts/knowledge/application/embedding_service.py`
  - 多 provider fallback (qwen → siliconflow → minimax)
  - `EMBEDDING_DIM` 从 1536 改 4096（dev DB 实际维度）
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`
  - SQL cast `::vector` 改 `CAST(:vec AS vector)`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`
  - 同 schema 问题同步修

**验证**：
- `python -m py_compile` 通过
- `get_embedding('Python 函数')` 真实返回 4096 维
- `validate_req024_p2_real_validation.py` 跑通（不再报 `text <=> vector`）

## Slice 3 — Knowledge Nodes Embedding Backfill

**目标**：599 个 knowledge_nodes embedding 100% NULL → 100% siliconflow 8B 4096 维。

**方案**：
- 扩展 `extract_knowledge_graph` Celery 任务：抽出节点 title + description → 硅流 embedding → UPDATE
- 或新写 `backfill_knowledge_node_embeddings.py` 一次性脚本（推荐，更易审计）
- 重跑 5 个已上传 PDF：`files` 表中 file_id 列表 + 触发 `extract_knowledge_graph` Celery 任务

**验证**：
- `SELECT COUNT(*) FROM metaedu.knowledge_nodes WHERE embedding IS NOT NULL` = 599

## Slice 4 — Validation

**目标**：验证 4 通道并行召回中 vector 通道真实命中。

**验证命令**：
```bash
# 1. psql 直接验证 pgvector 操作符
psql -c "SELECT 1 - (embedding <=> '[...]'::vector) FROM metaedu.document_chunks LIMIT 1;"

# 2. 跑真 PG dry-run
python scripts/validate_req024_p2_real_validation.py \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/td069_validation.md

# 3. 验证 vector_fallback_count = 0 + retrieval_topn.vector 真命中
```

## Slice 5 — Doc Sync + TD-068/TD-069 翻完成

**目标**：跨事实源同步，TD-068 翻完成，TD-069 翻完成。

**改动**：
- `technical-debt.md`：TD-068 status 🟡 → 🟢；TD-069 status ⚫ → 🟢
- `current-work.md`：TD-068 卡片更新（PR # + merge commit）
- `work-log.md`：TD-068 / TD-069 加一行索引
- `backlog.md`：移除 / 状态更新
- `iteration/2026-W25-p2-rag-quality-enhancement.md`：TD-068 / TD-069 更新
- `milestone/02-growth-phase.md`：TD-068 / TD-069 更新

## Files To Inspect First

- `alembic/versions/005_add_knowledge_node_embedding.py`（参考列类型定义）
- `alembic/versions/004_add_chunk_vectors.py`（参考 pgvector 迁移写法）
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`
- `packages/server-python/app/contexts/knowledge/application/embedding_service.py`
- `docs/03-engineering-governance/technical-debt.md#td-068`（TD-068 Slice 2 详情）

## Required Checks

- `alembic upgrade head` 成功
- `alembic downgrade -1` 成功
- `psql` 验证列类型和数据
- `python -m py_compile` 全部脚本通过
- `scripts/check-engineering-docs` 通过
- `git diff --check` 干净

## Documentation Closure

完成后必须同步：

- `docs/03-engineering-governance/technical-debt.md`：TD-068 / TD-069 状态
- `docs/03-engineering-governance/current-work.md`：TD-068 / TD-069 卡片
- `docs/03-engineering-governance/work-log.md`：一行索引
- `docs/01-product-planning/04-backlog.md`：移除 / 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`：更新
- `docs/01-product-planning/02-milestones/02-growth-phase.md`：更新

## Follow-up (Out of Scope)

- 重跑 REQ-024 / REQ-025 / REQ-026 / REQ-028 / REQ-029 真 LLM 报告（独立 PR，因为涉及 LLM 调用和长跑验证）
- TD-032 `validate_req024_p2_real_validation.py` 拆分（独立任务）