# REQ-TD069 (alias for spec/plan): P2 RAG Embedding Schema Vector Migration

> Status: 🟣 Shaping → Doing → Done (本任务将合并代码修复 + schema migration + data backfill + 报告字段更新)
> Created: 2026-06-19
> Source: TD-068 Slice 2 diagnosis → TD-069 注册
> Tech Debt: `docs/03-engineering-governance/technical-debt.md#td-069`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-19-td-069-embedding-column-vector-migration-plan.md`

## 1. Problem Statement

dev DB `document_chunks.embedding` / `knowledge_nodes.embedding` 两列当前 `text` 类型，pgvector 扩展已装但 `<=>` cosine 操作符要求 `vector` 类型。当前所有"vector 召回"实际都是 keyword 兜底。REQ-024/025/026/027/028/029 报告结论虽已用 REQ-028 三口径 + REQ-029 residual 阈值重新校准，但**真实向量召回能力**仍未验证。

## 2. Goal

- alembic 迁移：`document_chunks.embedding` / `knowledge_nodes.embedding` `text` → `vector(4096)`
- 1062 个 chunks embedding 字符串 → vector cast 保留
- 599 个 knowledge_nodes embedding backfill（写新迁移重跑 `extract_knowledge_graph`）
- 同步 merge TD-068 Slice 2 暂存代码修复（provider 多 fallback + retriever CAST）
- 验证 4 通道并行召回中 vector 通道真实命中
- 报告重跑留独立 PR

## 3. Non-Goals

- 不重跑 REQ-024/025/026/028/029 真 LLM 报告（独立 PR）
- 不修改 RRF / ContextPacker / AIChatService 主链路
- 不引入 Milvus / Qdrant 等新向量引擎
- 不修复 vector 数据本身（仅 schema 修复）

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | alembic 迁移生成：`document_chunks.embedding` / `knowledge_nodes.embedding` 改 `vector(4096)` | alembic upgrade head 成功 |
| AC-2 | 迁移后 1062 个 document_chunks embedding 数据 0 丢失 | `SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL` = 1062 |
| AC-3 | 599 个 knowledge_nodes embedding 100% 有数据 | `SELECT COUNT(*) FROM knowledge_nodes WHERE embedding IS NOT NULL` = 599 |
| AC-4 | `psql` 直接执行 `SELECT 1 - (embedding <=> '[...]'::vector) FROM metaedu.document_chunks LIMIT 1` 正常返回 | psql 验证 |
| AC-5 | `validate_req024_p2_real_validation.py` 真 PG dry-run：`vector_fallback_count` 维持 0；`retrieval_topn.vector` 真实命中 | 跑脚本 |
| AC-6 | TD-068 Slice 2 代码修复同步 merge：provider 多 fallback + retriever CAST | 同一 PR |
| AC-7 | 不影响现有 REQ-024/025/026/028/029 真 LLM 报告（字段保持兼容） | 字段对比 |

## 5. Architecture

### 5.1 schema 迁移设计

```python
# alembic/versions/030_embedding_columns_vector_4096.py
"""change embedding columns from text to vector(4096)

Revision ID: 030_embedding_vector
Revises: 005_add_knowledge_node_embedding
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # 1. document_chunks.embedding: text -> vector(4096) USING expression
    # (pgvector 支持 text → vector 的隐式 cast)
    op.execute("""
        ALTER TABLE metaedu.document_chunks
        ALTER COLUMN embedding TYPE vector(4096)
        USING embedding::vector(4096)
    """)

    # 2. knowledge_nodes.embedding: text -> vector(4096)
    # 但目前 599 行 100% NULL，需要先 backfill 再 alter type
    # backfill 由独立迁移 031 处理（先建立列结构 + 重跑 extract_knowledge_graph）
    op.execute("""
        ALTER TABLE metaedu.knowledge_nodes
        ALTER COLUMN embedding TYPE vector(4096)
        USING embedding::vector(4096)
    """)

def downgrade():
    op.execute("ALTER TABLE metaedu.document_chunks ALTER COLUMN embedding TYPE text USING embedding::text")
    op.execute("ALTER TABLE metaedu.knowledge_nodes ALTER COLUMN embedding TYPE text USING embedding::text")
```

**数据迁移安全**：pgvector `USING embedding::vector(N)` 在 NULL 值时也兼容；现存的 1062 chunks embedding 字符串（`[-0.011,0.002,...]`）正好是合法 vector 表示。

### 5.2 knowledge_nodes embedding backfill

需要新写 Celery 任务（或扩展 `extract_knowledge_graph`）：
1. 给 `extract_knowledge_graph` 加 embedding 字段填充（用 siliconflow `Qwen3-Embedding-8B`，4096 维）
2. 重跑已上传的 5 个 PDF 文件 → 599 节点全部 backfill

### 5.3 代码修复同步（来自 TD-068 Slice 2）

需要把暂存代码合入：
- `embedding_service.py`：多 provider fallback（qwen → siliconflow → minimax）
- `pg_chunk_vector_retriever.py`：`CAST(:vec AS vector)` 修复 SQLAlchemy 参数绑定
- 同样修复 `pg_graph_retriever.py`（同 schema 问题）

### 5.4 数据流

```
alembic upgrade head
    ↓
document_chunks.embedding: text → vector(4096) (1062 行数据保留)
    ↓
knowledge_nodes.embedding: text → vector(4096) (599 行 NULL → 仍 NULL，等待 backfill)
    ↓
extract_knowledge_graph 重跑 → 599 节点 embedding 填充
    ↓
pgvector <-> 操作符可用
    ↓
validate_req024_p2_real_validation.py 跑真实检索 → vector 通道真命中
```

## 6. File Layout

```
alembic/versions/
└── 030_embedding_columns_vector_4096.py         # 新增 schema 迁移

packages/server-python/app/contexts/knowledge/application/
└── embedding_service.py                          # 暂存修改同步 merge

packages/server-python/app/contexts/knowledge/infrastructure/retrievers/
├── pg_chunk_vector_retriever.py                  # 暂存 CAST(:vec AS vector)
└── pg_graph_retriever.py                         # 同步 CAST 修复

packages/server-python/app/contexts/document/application/tasks/
└── extract_knowledge_graph.py                    # 加 embedding 字段填充（如需要）

docs/03-engineering-governance/technical-debt.md
├── TD-068 status: 部分收口 → 完成
└── TD-069 status: Candidate → 完成（或者合并到 TD-068）
```

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | alembic 迁移 `030_embedding_columns_vector_4096.py` + upgrade + downgrade 测试 | — |
| Slice 2 | merge TD-068 Slice 2 暂存代码修复（embedding_service.py + pg_chunk_vector_retriever.py + pg_graph_retriever.py CAST） | Slice 1 |
| Slice 3 | backfill knowledge_nodes embedding（写 Celery 任务 + 重跑 599 节点） | Slice 1 |
| Slice 4 | 验证 4 通道 vector 真命中（`psql` + `validate_req024_p2_real_validation.py`） | Slice 2 + 3 |
| Slice 5 | TD-068 翻完成 + TD-069 翻完成 + 跨事实源同步 | Slice 4 |

## 8. Risks

- **alembic 迁移不可逆**：必须先用 dry-run 测试，确认 `USING expression` 在所有行（含 NULL）都兼容
- **backfill 成本**：5 PDF × 599 节点 = 2995 次硅流 embedding 调用（每次 ~30 秒）≈ 25 分钟，可能撞速率限制
- **provider 已配**：dev DB `.env` 有 `SILICONFLOW_API_KEY` 和 `MINIMAX_API_KEY`，但 TD-068 暂存代码需先 merge 才会用上
- **graph_node SQL 也需修**：`pg_graph_retriever.py` 同 schema 问题，需同步修
- **报告字段兼容性**：REQ-028 报告的 `vector_fallback_count` 字段语义变了（之前=keyword 兜底次数；现在=embedding provider 失败次数），需在 README 里说明

## 9. References

- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`
- TD-069: `docs/03-engineering-governance/technical-debt.md#td-069`
- REQ-018 / REQ-026 / REQ-029
- 005 migration: `alembic/versions/005_add_knowledge_node_embedding.py`
- `pg_chunk_vector_retriever.py` 当前 SQL