# Data Integrity — 数据完整性规范

## 1. 级联删除原则

删除主数据时，必须清理所有关联的子数据，防止孤儿数据产生。当前项目仍有部分清理逻辑写在 API router 中；新增或重构时应优先收敛到 application service 或 repository，避免重复 SQL。

### 删除执行顺序

```
1. 先删子表数据（chunks, rows, tasks）
2. 再删关联数据（knowledge_nodes, embeddings）
3. 最后删主数据（files, datasets）
```

### 各场景级联删除要求

| 删除场景 | 必须级联删除 |
|----------|------------|
| 删除 `files` 记录 | chunks, knowledge_edges(关联 file 派生节点), knowledge_nodes(source_file_id), document_tasks(file_id) |
| 删除 `datasets` 记录 | dataset_rows, document_chunks(file_id=dataset_id), knowledge_edges(关联 dataset 派生节点), knowledge_nodes(source_dataset_id), document_tasks(dataset_id) |
| 删除 `resources` | 仅软删除（is_deleted=true），不级联 |

### 实现要求

- 删除 `knowledge_nodes` 前，必须先删除引用这些节点的 `knowledge_edges`。
- 清理逻辑应封装成可复用函数，文件删除和重新初始化不得各写一套级联 SQL。
- 级联清理必须带 `tenant_id` 条件。
- 删除逻辑变更时，必须补充或更新回归测试，覆盖关联边/节点/任务清理。

---

## 2. 外键与索引

| 表 | 外键引用 | 清理策略 |
|----|----------|----------|
| `document_chunks` | file_id → files.id 或 datasets.id | 删除文件/数据集时清理 |
| `knowledge_nodes` | source_file_id, source_dataset_id, source_chunk_id, source_row_id | 删除源数据时清理 |
| `knowledge_edges` | source_id/target_id → knowledge_nodes.id | 删除节点前清理关联边 |
| `document_tasks` | file_id, dataset_id | 删除源数据时清理 |
| `dataset_rows` | dataset_id → datasets.id | 删除数据集时清理 |

---

## 3. 定期数据一致性检查

每次删除操作后，建议检查以下孤儿数据：

```sql
-- 检查 orphan chunks
SELECT COUNT(*) FROM metaedu.document_chunks dc
LEFT JOIN metaedu.files f ON dc.file_id = f.id
LEFT JOIN metaedu.datasets d ON dc.file_id = d.id
WHERE f.id IS NULL AND d.id IS NULL;

-- 检查 orphan knowledge_nodes
SELECT COUNT(*) FROM metaedu.knowledge_nodes kn
LEFT JOIN metaedu.files f ON kn.source_file_id = f.id
LEFT JOIN metaedu.datasets d ON kn.source_dataset_id = d.id
WHERE (kn.source_file_id IS NOT NULL AND f.id IS NULL)
  AND (kn.source_dataset_id IS NOT NULL AND d.id IS NULL);

-- 检查 orphan dataset_rows
SELECT COUNT(*) FROM metaedu.dataset_rows dr
LEFT JOIN metaedu.datasets d ON dr.dataset_id = d.id
WHERE d.id IS NULL;

-- 检查 orphan document_tasks
SELECT COUNT(*) FROM metaedu.document_tasks dt
LEFT JOIN metaedu.files f ON dt.file_id = f.id
LEFT JOIN metaedu.datasets d ON dt.dataset_id = d.id
WHERE (dt.file_id IS NOT NULL AND f.id IS NULL)
  AND (dt.dataset_id IS NOT NULL AND d.id IS NULL);
```

---

## 4. 软删除 vs 硬删除

| 场景 | 删除方式 | 说明 |
|------|----------|------|
| `resources` | 软删除 | 设置 `is_deleted=true`，保留审计记录 |
| `files` | 硬删除 | 级联删除所有关联数据 |
| `datasets` | 硬删除 | 级联删除所有关联数据 |
| `knowledge_nodes` | 硬删除 | 由上游触发（删除 source_file/dataset 时） |

---

## 5. 资源清理

删除文件/数据集时，如需清理存储文件：
```python
import os
from app.config import settings

# 删除物理文件
file_path = os.path.join(settings.upload_dir, storage_key)
if os.path.exists(file_path):
    os.remove(file_path)
```
