# 产品需求文档：MetaEduBase 智能文档处理管道

> 日期: 2026-05-18（全面技术实现版）
> 状态: 已上线验证
> 范围: 资源库文档处理 + 数据库模块 + 知识图谱构建

---

## 1. 产品概述

MetaEduBase 智能文档处理管道将非结构化文档（PDF/DOCX）和结构化数据（Excel）转化为可检索、可推理的知识。用户上传文档后，系统自动完成解析、语义切片、向量化、全文索引、结构化抽取、知识图谱构建，全部异步后台执行，用户实时感知处理进度。

**两个入口：**
- **资源库**：上传 PDF/DOCX，系统解析文档结构、切片、向量化、抽取模板和知识图谱
- **数据库**：上传 Excel，系统解析行列数据、向量化，并构建跨表知识图谱

---

## 2. 技术架构总览

```
用户上传 PDF/DOCX/Excel
         ↓
    文件存储（本地磁盘 / MinIO）
         ↓
    写入元数据（files/datasets 表，status=uploaded）
         ↓
    派发 Celery 异步任务（Redis Broker）
         ↓
    ┌─────────────────────────────────────────┐
    │         资源库文档处理管道                │
    │  parse → chunk → embed → index_tsv     │
    │  → extract_template → extract_kg        │
    └─────────────────────────────────────────┘
         ↓
    更新状态（status=processed）
         ↓
    前端轮询感知（3秒间隔）
```

**核心技术栈：**
- 异步队列：Celery 5 + Redis（Broker: redis://localhost:6379/1）
- 向量数据库：PostgreSQL 16 + pgvector（1536 维，HNSW 索引）
- 全文搜索：PostgreSQL tsvector（simple 分词器）
- LLM：MiniMax-M2（通义千问兼容 API）/ DeepSeek / Qwen
- Embedding：MiniMax emboir（内置）/ SiliconFlow Qwen/Qwen3-Embedding-8B
- PDF 解析：PyMuPDF（fitz）
- DOCX 解析：python-docx
- Excel 解析：openpyxl

---

## 3. 完整数据处理管道

### 3.1 管道 1：资源库 — 文档上传

```
用户上传 PDF/DOCX
    ↓
[Step 0] 保存文件 → files 表（status=uploaded）→ 派发 parse_document
    ↓
[Step 1] parse_document — 文档解析
    ↓
[Step 2] chunk_document — 结构感知切片
    ↓
[Step 3] embed_chunks — 向量化
    ↓  并行
[Step 3b] index_tsvector — 全文索引
    ↓
[Step 4] extract_template — 模板抽取（MiniMax-M2）
    ↓
[Step 5] extract_knowledge_graph — 知识图谱抽取（MiniMax-M2）
    ↓
files.status = processed
```

### 3.2 管道 2：数据库 — Excel 导入

```
用户上传 Excel
    ↓
[Step 0] 保存文件 → datasets 表（status=uploaded）→ 派发 ds_parse
    ↓
[Step 1] ds_parse — Excel 解析（openpyxl）
    ↓
[Step 2] ds_embed — 向量化
    ↓
datasets.status = processed, kg_status = pending
    ↓
[Step 3] 所有数据集处理完成后 → ds_extract_kg（跨数据集知识图谱）
    ↓
datasets.kg_status = done
```

---

## 4. 各环节技术实现详解

### 4.1 文档解析（parse_document）

**技术选型：**
- PDF：`PyMuPDF`（fitz）— 轻量、高性能、跨平台
- DOCX：`python-docx`

**PDF 解析算法（PyMuPDF）：**

```
1. 打开 PDF，获取所有页面
2. 遍历每个页面的 block（文本块）
3. 对每行文本：
   - 提取最大字体（max_font_size）和粗体标记
   - 字体大小 → 标题级别映射：
     22pt+  → 一级标题（H1）
     18pt+  → 二级标题（H2）
     15pt+  → 三级标题（H3）
     13pt+  → 四级标题（H4）
   - 字体 ≥13pt + 粗体 + 长度 <200字符 → 识别为标题
4. 标题之间的文本归入当前章节
5. 章节编号自动生成（如 "3.2.1"）：
   - 维护每个级别的计数器
   - _build_path(): 按级别顺序拼接 → "3.2.1"
6. 无明显标题的文档：降级为整页文本模式
7. 输出：
   - sections: List[DocumentSection(title, level, content, page, path)]
   - full_text: 所有章节拼接的完整文本
```

**DOCX 解析算法（python-docx）：**

```
1. 打开 DOCX，遍历所有段落（paragraphs）
2. 样式名 → 标题级别映射：
   "Heading 1" → H1
   "Heading 2" → H2
   ...
   "标题 1" → H1（兼容中文样式名）
   "标题 2" → H2
3. 非标题段落归入当前章节
4. 输出结构同 PDF
```

**代码位置：** `packages/server-python/app/shared/parsing/pdf_parser.py`
**代码位置：** `packages/server-python/app/shared/parsing/docx_parser.py`

---

### 4.2 结构感知切片（chunk_document）

**技术选型：** 自研语义切片算法（基于段落→句子→子句→字符的递归拆分）

**切片规则：**

| 参数 | 值 | 说明 |
|------|----|------|
| 目标切片大小 | 500 字符 | ≈ 300-500 tokens（中文） |
| 最小切片大小 | 80 字符 | 低于此值与前一片合并 |
| 切片上限 | 500 字符 | 超限在子句/句子边界递归拆分 |
| 边界优先级 | 段落 > 句子 > 逗号/顿号 > 字符 | 永远不在句子中间拆分 |

**算法流程：**

```
输入: ParsedDocument（sections: List[DocumentSection]）

For each section:
    1. 按 \n\n 拆分为段落（paragraphs）
    2. For each paragraph:
        a. 按句子边界（。！？?!）拆分为句子（sentences）
        b. For each sentence:
            - 如果能装入当前片（+1个换行符 ≤ 500字符）→ 合并
            - 如果装不下：
              · 若当前片 <100字符 且 新句子 >400字符 → 强制合并（防碎片化）
              · 否则 → 新建一片
    3. 对所有超限切片递归拆分：
        a. 先在句子边界拆
        b. 若单句仍超限，在逗号/顿号/分号处拆
        c. 若子句仍超限，按字符数硬拆（最后手段）
    4. 合并过小切片（<80字符）到前一片

输出: List[Chunk](content, section_title, section_path, char_start, char_end, index)
```

**中文语义边界处理：**
- 句子边界：`。！？`（中文）+ `?!`（英文）
- 子句边界：`，、；`（不在句子边界时使用）
- 段落边界：`\n\n`（最强语义边界）

**写入数据库：**
```sql
INSERT INTO metaedu.document_chunks
  (id, tenant_id, file_id, chunk_index, content, section_title, section_path, char_start, char_end)
VALUES (...)
```

**代码位置：** `packages/server-python/app/shared/parsing/chunker.py`

---

### 4.3 向量化（embed_chunks）

**技术选型：**

| 提供商 | 模型 | 向量维度 | 批量支持 | 备注 |
|--------|------|----------|----------|------|
| MiniMax | `emboir`（内置） | 1536 | 是（最大50条/请求） | 主用 |
| SiliconFlow | `Qwen/Qwen3-Embedding-8B` | 1536 | 是（batch API） | 备用 |

**API 端点：**
- MiniMax：`https://api.minimaxi.com/v1/embeddings`（OpenAI 兼容）
- SiliconFlow：`https://api.siliconflow.cn/v1/embeddings`

**批量策略：**

```
1. 查询所有未向量化的 chunks（embedding IS NULL）
2. 将 content 截断至 8192 字符（防止超出模型输入限制）
3. 优先调用 MiniMax batch embedding（50条/批）
   - 若失败（超时/429/5xx）→ 记录 warning
4. 若 MiniMax 无结果，fallback 到 SiliconFlow
   - SiliconFlow 支持更大批量
5. 若两提供商均失败 → 任务标记为 FAILED（不静默跳过）
6. 批量 UPDATE document_chunks SET embedding = :vec
```

**降级逻辑：**
- MiniMax 优先：API key 非空则优先调用
- SiliconFlow 兜底：MiniMax 失败后尝试
- 均失败：任务失败，可重试

**向量存储：**
```sql
ALTER TABLE metaedu.document_chunks ADD COLUMN embedding VECTOR(1536);

-- HNSW 索引（创建时指定）
CREATE INDEX ON metaedu.document_chunks USING hnsw (embedding vector_cosine_ops);
```

**代码位置：** `packages/server-python/app/contexts/document/application/tasks.py` — `embed_chunks` 函数

---

### 4.4 全文索引（index_tsvector）

**技术选型：** PostgreSQL 内置 `to_tsvector('simple', content)`

**分词器：** `simple` — 按空格和标点分词，中文按字符切分

**为什么不用中文分词（jieba/pg_jieba）：**
- MVP 阶段使用 `simple` 分词已经够用
- `simple` 对中文支持：每个汉字作为独立 token，支持 `/` 前缀匹配
- 如 "AI 代理" → token: `ai`, `代`, `理`
- 前端搜索时用 `/.*代理.*/` 正则匹配

**更新方式：**
```sql
UPDATE metaedu.document_chunks
SET content_tsvector = to_tsvector('simple', content)
WHERE id = :cid
```

**全文检索示例：**
```sql
-- 检索包含"代理"的切片
SELECT * FROM metaedu.document_chunks
WHERE content_tsvector @@ to_tsquery('simple', '代理')
ORDER BY ts_rank(content_tsvector, to_tsquery('simple', '代理')) DESC;
```

---

### 4.5 结构化模板抽取（extract_template）

**技术选型：** MiniMax-M2（通义千问兼容 API）

**API：** `https://api.minimaxi.com/v1/chat/completions`
**模型：** `MiniMax-M2`（chat model，非 embedding）
**温度：** 0.1（低随机性，确保稳定 JSON 输出）

**抽取逻辑：**

```
1. 取文档前 10 个切片拼接（每个切片取前 500 字符）
   → 共约 5000 字符作为 LLM 上下文
2. 根据 doc_type 决定 prompt 模板：
   - 教案 → 教案专用字段
   - 其他 → 通用摘要字段
3. 发送中文 prompt（明确要求"只返回 JSON"）
4. 解析 LLM 输出：
   a. 先用正则去掉 MiniMax 思考标签：<thinking>...</thinking>
   b. 优先匹配 ```json ... ``` 代码块
   c. 否则找第一个 { 到最后一个 } 的内容
   d. json.loads() 解析
   e. 解析失败 → 返回空 dict {}
5. 合并到 files.structured_data.template 字段
   （保留已有的 full_text 和 section_count）
```

**Prompt（教案类文档）：**
```
请从以下教案内容中提取JSON格式的结构化信息，将所有字段翻译为中文，只返回JSON不要任何解释：
字段：course_name(课程名), chapter(章节), objectives[教学目标数组], key_points[重点数组], difficulties[难点数组], methods[教学方法数组], duration(课时)

内容：
{chunks_text[:6000]}
```

**Prompt（通用文档）：**
```
请对以下文档内容提取结构化摘要，将所有字段翻译为中文，只返回JSON不要任何解释：
字段：title(中文标题), summary(100字内中文摘要), sections[中文章节列表], key_points[中文关键要点], keywords[中文关键词最多5个]

内容：
{chunks_text[:6000]}
```

**输出字段（通用文档）：**
| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 文档中文标题 |
| summary | string | 100字内中文摘要 |
| sections | string[] | 主要章节列表（中文） |
| key_points | string[] | 关键要点数组（中文） |
| keywords | string[] | 关键词最多5个（中文） |

**存储：**
```sql
UPDATE metaedu.files
SET structured_data = CAST(:data AS JSONB)
WHERE id = :fid
-- structured_data 结构：{"template": {...}, "full_text": "...", "section_count": N}
```

**代码位置：** `packages/server-python/app/contexts/document/application/tasks.py` — `extract_template` 函数

---

### 4.6 知识图谱抽取（extract_knowledge_graph）

**技术选型：** MiniMax-M2（chat model）

**算法：**

```
1. 取文档前 20 个切片（每个 500 字符）
   → 每个切片显示：[章节标题] 内容前500字
2. 发送中文 prompt，要求：
   a. 实体名翻译成中文
   b. 只返回 JSON，不要任何解释
3. JSON 解析（同样去掉思考标签 + 代码块匹配）
4. 写入 knowledge_nodes（按 name 去重）
   - 计算 node_name 归一化（去空格、去引号）
   - 节点路径 = node_id[:8]
5. 写入 knowledge_edges（按 source/target/relation 去重）
   - relation 默认值："相关"
   - metadata 存储来源文件信息
```

**Prompt：**
```
请从以下文本中提取知识实体和关系，将所有实体名称翻译为中文，只返回JSON不要任何解释：
{"entities": [{"name": "中文实体名", "type": "类型"}],
 "relations": [{"source": "中文实体1", "target": "中文实体2", "relation": "关系描述"}]}

文本：
{chunks_text[:6000]}
```

**节点写入：**
```sql
INSERT INTO metaedu.knowledge_nodes
  (id, tenant_id, title, description, domain, level, path, source_file_id, created_at, updated_at)
VALUES (:id, :tid, :title, '', 'education_sports', 'knowledge_point', :path, :fid, :now, :now)
```

**关系写入：**
```sql
INSERT INTO metaedu.knowledge_edges
  (id, tenant_id, source_id, target_id, relation_type, weight, metadata, created_at)
VALUES (:id, :tid, :src, :tgt, :rtype, 1.0, :meta, :now)
-- metadata: {"source_file_id": "..."}
```

**去重策略：**
- 节点名归一化后查重（strip空格、引号，大小写不敏感）
- 边去重：查 source_id + target_id + relation_type 唯一约束

**代码位置：** `packages/server-python/app/contexts/document/application/tasks.py` — `extract_knowledge_graph` 函数

---

### 4.7 跨数据集知识图谱（ds_build_cross_dataset_edges）

**技术选型：** 基于 FK 列名启发式检测（无 LLM，纯规则）

**算法：**

```
输入：当前租户下所有 status='processed' 的数据集

1. 对每个数据集，提取 column_names
2. 识别 FK 列（以 ID/Id/id 结尾，且非自身主键）：
   - "所属院系ID" → 引用"院系"
   - "学生ID" → 引用"学生"
3. 提取引用实体名：
   - 去掉前缀（所属、授课、关联、对应、相关）
   - 去掉后缀（ID、Id、id）
4. 匹配其他数据集的 entity_name（数据集名去掉"表/数据/信息"后缀）
5. 模糊匹配：ILIKE '%院系%'
6. 创建跨数据集边
```

**辅助函数：**
```python
def _extract_entity_name(dataset_name: str) -> str:
    """'院系表' → '院系', '学生信息表' → '学生'"""
    return dataset_name.rstrip("表").rstrip("数据").rstrip("信息")

def _extract_fk_reference(column_name: str, self_pk: str) -> str | None:
    """'所属院系ID' → '院系', '学生ID' → None(自身主键)"""
    if column_name == self_pk:
        return None
    for suffix in ("ID", "Id", "id"):
        if column_name.endswith(suffix):
            ref = column_name[:-len(suffix)]
            for prefix in ("所属", "授课", "关联", "对应", "相关"):
                if ref.startswith(prefix):
                    ref = ref[len(prefix):]
            return ref if ref else None
    return None
```

**触发条件：** 所有 `status='processed'` 的数据集 `kg_status` 均为 `done` 时，由最后一个 `ds_extract_kg` 成功后自动触发。

**代码位置：** `packages/server-python/app/contexts/structured_data/application/tasks.py` — `ds_build_cross_dataset_edges`

---

### 4.8 Excel 解析（ds_parse）

**技术选型：** `openpyxl`

**解析流程：**
```
1. openpyxl.load_workbook() 打开 Excel
2. 遍历所有 sheet，取第一个 sheet
3. 第一行为表头，以下各行为数据行
4. 推断列类型（string/integer/float/date）：
   - 全为数字 → integer/float
   - 匹配日期格式 → date
   - 否则 → string
5. 写入 dataset_rows 表：
   row_data = JSONB（如 {"姓名": "张三", "成绩": 95}）
6. 更新 datasets 表：
   - row_count, column_count
   - column_names[], column_types[]
```

**代码位置：** `packages/server-python/app/contexts/structured_data/application/tasks.py` — `ds_parse`

---

## 5. 管道稳定性设计

### 5.1 过期检测机制（Stale Detection）

**问题：** 用户多次点击"重新初始化"时，旧的管道任务可能在新任务完成后才到达，导致覆盖新结果。

**解决方案：** `files.updated_at` 作为管道版本标记

```
1. reinitialize 操作：
   a. files.status → 'uploaded'（repo.update 会更新 updated_at）
   b. 读取新的 updated_at → 作为 pipeline_version
   c. 派发 parse_document.delay(file_id, tenant_id, pipeline_version)

2. 每个管道任务入口（embed_chunks 等）：
   a. SELECT updated_at FROM metaedu.files WHERE id = :fid
   b. 归一化比较：updated_at.replace('T', ' ').split('.')[0] == pipeline_version
   c. 不匹配 → 标记任务为 failed，退出（不继续写数据）

3. 关键：管道任务不修改 files.updated_at
   - parse_document、index_tsvector、extract_template 均不更新
   - 只有 reinitialize 才会改变 updated_at
```

**归一化函数：**
```python
def _pipeline_version_key(ts: str | None) -> str:
    """Python: '2026-05-18T15:10:13.072166' → PostgreSQL: '2026-05-18 15:10:13'"""
    if not ts:
        return ""
    return ts.replace("T", " ").split(".")[0]
```

**适用任务：** `parse_document`、`chunk_document`、`embed_chunks`、`index_tsvector`
**不适用（幂等）：** `extract_template`、`extract_knowledge_graph`（管道末端，最多重复执行不影响正确性）

### 5.2 任务状态表（document_tasks）

| task_type | 中文名 | 进度定义 |
|-----------|--------|----------|
| parse | 文档解析 | 固定 100% |
| chunk | 结构切片 | 固定 100% |
| embed | 向量化 | 0%→100%（无中间进度） |
| index_tsv | 全文索引 | 0%→100% |
| extract_template | 模板抽取 | 0%→100% |
| extract_kg | 知识图谱 | 0%→100% |

**状态流转：** `pending` → `running` → `success` / `failed`

---

## 6. 数据库模型

### 6.1 新建表

#### folders（文件夹树）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| name | VARCHAR(200) | 文件夹名 |
| parent_id | UUID FK→folders | 父文件夹（nullable） |
| path | VARCHAR(500) | ltree 物化路径 |
| sort_order | INTEGER | 同级排序 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### files（资源库文件）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| folder_id | UUID FK→folders | 所属文件夹（nullable） |
| filename | VARCHAR(300) | 文件名 |
| file_type | VARCHAR(50) | pdf/docx/xlsx |
| doc_type | VARCHAR(50) | 教案/授课计划/课程标准/... |
| file_size | INTEGER | 字节 |
| storage_key | VARCHAR(500) | 存储路径 |
| tags | TEXT[] | 标签数组 |
| status | VARCHAR(20) | uploaded/processing/processed/failed |
| structured_data | JSONB | 模板抽取结果 |
| uploaded_by | UUID FK→users | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | 管道版本标记 |

#### document_chunks（文档切片）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| file_id | UUID FK→files | 所属文件 |
| chunk_index | INTEGER | 切片序号（从 0） |
| content | TEXT | 切片文本 |
| section_title | VARCHAR(200) | 所属章节标题 |
| section_path | VARCHAR(100) | 章节路径（如"3.2.1"） |
| embedding | VECTOR(1536) | pgvector 向量（nullable） |
| content_tsvector | TSVECTOR | 全文索引（nullable） |
| char_start | INTEGER | 原文起始字符 |
| char_end | INTEGER | 原文结束字符 |
| created_at | TIMESTAMP | |

**索引：**
```sql
CREATE INDEX idx_chunks_embedding ON metaedu.document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsvector ON metaedu.document_chunks USING gin (content_tsvector);
CREATE INDEX idx_chunks_file ON metaedu.document_chunks (tenant_id, file_id);
```

#### datasets（数据集）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| name | VARCHAR(300) | 数据表名称 |
| description | TEXT | 描述 |
| source_type | VARCHAR(30) | excel（MVP） |
| storage_key | VARCHAR(500) | 存储路径 |
| file_size | INTEGER | 字节 |
| row_count | INTEGER | 行数 |
| column_count | INTEGER | 列数 |
| column_names | TEXT[] | 列名数组 |
| column_types | TEXT[] | 列类型数组 |
| tags | TEXT[] | 标签 |
| status | VARCHAR(20) | uploaded/processing/processed/failed |
| kg_status | VARCHAR(20) | pending/processing/done/failed |
| sort_order | INTEGER | 排序 |
| uploaded_by | UUID FK→users | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### dataset_rows（数据集行数据）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| dataset_id | UUID FK→datasets | 所属数据集 |
| row_index | INTEGER | 行号 |
| row_data | JSONB | 行数据（key=列名） |
| created_at | TIMESTAMP | |

#### document_tasks（处理任务）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID | 租户隔离 |
| file_id | UUID FK→files | nullable |
| dataset_id | UUID FK→datasets | nullable |
| task_type | VARCHAR(50) | 任务类型 |
| status | VARCHAR(20) | pending/running/success/failed |
| progress | INTEGER | 0-100 |
| error_message | TEXT | nullable |
| started_at | TIMESTAMP | nullable |
| completed_at | TIMESTAMP | nullable |
| created_at | TIMESTAMP | |

### 6.2 已有表扩展

#### knowledge_nodes 新增字段

| 列名 | 类型 | 说明 |
|------|------|------|
| source_file_id | UUID FK→files | 资源库来源（nullable） |
| source_dataset_id | UUID FK→datasets | 数据库来源（nullable） |
| source_chunk_id | UUID FK→document_chunks | 切片来源（nullable） |
| source_row_id | UUID FK→dataset_rows | 行来源（nullable） |

#### knowledge_nodes 新增索引

```sql
CREATE INDEX idx_nodes_source_file ON metaedu.knowledge_nodes (tenant_id, source_file_id);
CREATE INDEX idx_nodes_source_dataset ON metaedu.knowledge_nodes (tenant_id, source_dataset_id);
CREATE INDEX idx_nodes_source_chunk ON metaedu.knowledge_nodes (tenant_id, source_chunk_id);
```

#### knowledge_edges 新增索引

```sql
CREATE INDEX idx_edges_source ON metaedu.knowledge_edges (tenant_id, source_id);
CREATE INDEX idx_edges_target ON metaedu.knowledge_nodes (tenant_id, target_id);
```

---

## 7. API 端点

### 7.1 资源库 — 文件夹

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/folders` | 获取文件夹树 |
| POST | `/api/v1/document/folders` | 创建文件夹 |
| PATCH | `/api/v1/document/folders/{id}` | 修改文件夹 |
| DELETE | `/api/v1/document/folders/{id}` | 删除文件夹（需为空） |
| PATCH | `/api/v1/document/folders/{id}/move` | 移动文件夹 |

### 7.2 资源库 — 文件

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/files` | 列出文件（支持 folder_id/tag/status 过滤） |
| POST | `/api/v1/document/files/upload` | 上传文件（multipart） |
| GET | `/api/v1/document/files/{id}` | 获取文件详情（含 structured_data） |
| DELETE | `/api/v1/document/files/{id}` | 删除文件（级联删除 chunks/知识节点/任务） |
| PATCH | `/api/v1/document/files/{id}` | 修改文件（标签/文档类型/文件夹） |
| POST | `/api/v1/document/files/{id}/reinitialize` | 重新初始化（清空重建管道） |

### 7.3 资源库 — 任务与切片

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/files/{id}/tasks` | 获取文件的所有任务状态 |
| POST | `/api/v1/document/files/{id}/retry` | 重试失败的任务 |
| GET | `/api/v1/document/files/{id}/chunks` | 获取文件切片列表 |

### 7.4 数据库 — 数据集

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/structured-data/datasets` | 列出数据集 |
| POST | `/api/v1/structured-data/datasets/upload` | 上传 Excel |
| GET | `/api/v1/structured-data/datasets/{id}` | 获取数据集详情 |
| GET | `/api/v1/structured-data/datasets/{id}/rows` | 获取行数据（分页） |
| DELETE | `/api/v1/structured-data/datasets/{id}` | 删除数据集 |
| PATCH | `/api/v1/structured-data/datasets/{id}` | 修改数据集 |
| POST | `/api/v1/structured-data/datasets/{id}/reinitialize` | 重新初始化 |

### 7.5 数据库 — 任务与知识图谱

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/structured-data/datasets/{id}/tasks` | 获取数据集任务状态 |
| POST | `/api/v1/structured-data/datasets/{id}/retry` | 重试失败任务 |
| GET | `/api/v1/structured-data/knowledge-graph` | 获取数据库级知识图谱（全部节点+边） |
| POST | `/api/v1/structured-data/knowledge-graph/rebuild` | 重建整个知识图谱（危险操作） |
| GET | `/api/v1/structured-data/knowledge-graph/status` | KG 构建状态 |

---

## 8. 前端实现

### 8.1 文件详情页 — 处理流水线展示

**组件结构：**
```
FileDetailView.vue
├── PageHeader（文件名、类型、大小、标签）
├── 流水线状态栏（6步横向进度）
│   ├── parse（文档解析）
│   ├── chunk（结构切片）
│   ├── embed（向量化）
│   ├── index_tsv（全文索引）
│   ├── extract_template（模板抽取）
│   └── extract_kg（知识图谱）
├── Tab 区域
│   ├── 结构化抽取（templateData → structured_data.template）
│   ├── 切片列表（chunks → document_chunks）
│   └── 知识图谱（kgNodes + kgEdges → knowledge_nodes/edges）
```

### 8.2 自动轮询机制

**轮询逻辑（3秒间隔）：**
```javascript
// startPolling() — onMounted 时调用
setInterval(async () => {
  await loadTasks();     // 每次都刷新任务状态
  if (!polling.value) {  // 无 running/pending 任务时
    stopPolling();
    await loadFile();    // 刷新 structured_data
    await loadChunks();   // 刷新切片向量化状态
    await loadKg();       // 刷新知识图谱
  }
}, 3000);
```

**polling computed：** `tasks.value.some(t => t.status === "running" || t.status === "pending")`

**手动刷新按钮：** 调用 `refreshAll()`，同时刷新 `loadFile()` + `loadTasks()` + 当前 Tab 数据

### 8.3 重新初始化（Reinitialize）

**后端流程：**
```
1. 验证 status != 'processing'（防止并发）
2. DELETE document_chunks（文件所有切片）
3. DELETE knowledge_nodes（source_file_id = fid）
4. DELETE knowledge_edges（source_id IN nodes）
5. DELETE document_tasks（file_id = fid）
6. files.status → 'uploaded'（触发 updated_at 更新）
7. 读取新的 updated_at 作为 pipeline_version
8. 派发 parse_document.delay(file_id, tenant_id, pipeline_version)
```

---

## 9. 技术依赖清单

| 依赖 | 版本 | 用途 |
|------|------|------|
| Celery | 5.x | 异步任务队列 |
| Redis | 7.x | Celery Broker + Result Backend |
| PostgreSQL | 16.x | 主数据库 + pgvector + tsvector |
| PyMuPDF (fitz) | 最新 | PDF 文本和标题提取 |
| python-docx | 最新 | DOCX 文本和标题提取 |
| openpyxl | 最新 | Excel 行列解析 |
| httpx | 最新 | 异步 HTTP 客户端（LLM/Embedding API 调用） |
| MiniMax API | — | LLM（MiniMax-M2）+ Embedding（emboir） |
| SiliconFlow API | — | Embedding 备用（Qwen/Qwen3-Embedding-8B） |

---

## 10. 性能基准（参考）

| 操作 | 预计耗时（10MB PDF） | 说明 |
|------|---------------------|------|
| PDF 解析 | 1-3s | PyMuPDF 文本提取 |
| 切片（100片） | <1s | 本地算法 |
| 向量化（SiliconFlow） | 5-15s | 取决于 Embedding API 响应速度 |
| tsvector 索引 | <1s | PostgreSQL 批量 UPDATE |
| 模板抽取（MiniMax-M2） | 10-20s | 含 LLM API 延迟 |
| 知识图谱（MiniMax-M2） | 10-30s | 含 LLM API 延迟 |

---

## 11. 已知限制与未来优化

| 限制 | 当前处理 | 未来优化方向 |
|------|----------|--------------|
| 中文分词 | `simple` tokenizer（字符级） | 接入 pg_jieba 或 elasticsearch |
| Embedding 批量大小 | MiniMax 50条/批 | 调优 batch_size 参数 |
| 表格/PDF 图片 | 未处理 | PyMuPDF 支持图片提取，需单独处理 |
| 跨语言知识图谱 | 中文 prompt → 翻译抽取 | 保留英日韩等原文实体 |
| 文档类型模板 | 教案硬编码 | 子项目 A2：可配置 schema |
| RAG 问答 | 未实现 | 子项目 B：混合检索 RAG |

---

## 12. 文档历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-15 | 初稿设计 | 设计文档完成 |
| 2026-05-18 | 全面实现版 | 补充所有技术实现细节：解析算法、切片规则、Embedding 策略、过期检测机制、前端轮询逻辑、跨数据集边算法 |
