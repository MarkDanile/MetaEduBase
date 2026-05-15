# 子项目 A1 设计文档：资源库增强 + 文档处理管道 + 数据库模块

> 日期: 2026-05-15
> 状态: 已确认
> 范围: 子项目 A1 — 完整数据入库管道

## 1. 目标

构建从非结构化文档/结构化 Excel 到可检索知识的完整入库管道，验证"上传 → 解析 → 切片 → 向量化 → 知识图谱"端到端流程。资源库和数据库是两个独立的功能入口，处理管道不同。

## 2. 范围

| # | 功能 | 说明 |
|---|------|------|
| 1 | 资源库增强 | 文件夹树(ltree) + 标签系统 + 树形导航/上传/CRUD |
| 2 | 文档处理管道 | Celery 异步：PDF/DOCX 解析 → 结构感知切片 → 向量化(pgvector) + 全文索引(tsvector) + 模板抽取(JSONB) |
| 3 | 数据库模块 | 独立菜单，Excel 上传 → 解析 → 向量化 → LLM 抽取知识图谱。独立数据表和 API |
| 4 | 知识图谱构建 | LLM 从文档切片/Excel 抽取知识点和关系，写入 knowledge_nodes/edges，向量相似度去重 |
| 5 | 处理状态追踪 | 前端可查看文件处理进度/结果，支持手动刷新和失败重试 |

**不在范围内：**
- 文档类型模板配置系统（子项目 A2）
- 混合检索 RAG（子项目 B）
- Elasticsearch（后续阶段）

## 3. 数据模型

### 3.1 新建表

#### folders（文件夹树 — 资源库用）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| name | VARCHAR(200) | 文件夹名称 |
| parent_id | UUID FK→folders | nullable, 自引用 |
| path | VARCHAR(500) | ltree 物化路径 |
| sort_order | INTEGER | 同级排序 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

索引: `(tenant_id, parent_id)`, `(path)`

#### files（资源库文件表 — 替代 resources）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| folder_id | UUID FK→folders | 所属文件夹 |
| filename | VARCHAR(300) | 文件名 |
| file_type | VARCHAR(50) | pdf/docx |
| doc_type | VARCHAR(50) | nullable, 教案/授课计划/课程标准/... |
| file_size | INTEGER | nullable, 字节 |
| storage_key | VARCHAR(500) | nullable, 存储路径 |
| tags | TEXT[] | 标签数组 |
| status | VARCHAR(20) | uploaded/processing/processed/failed |
| structured_data | JSONB | nullable, 文档级模板抽取结果（教案/课程标准等） |
| uploaded_by | UUID FK→users | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

索引: `(tenant_id, folder_id)`, `(tenant_id, doc_type)`, `(tenant_id, status)`

#### document_chunks（文档切片 — 资源库用）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| file_id | UUID FK→files | 所属文件 |
| chunk_index | INTEGER | 切片序号（从 0 开始） |
| content | TEXT | 切片文本内容 |
| section_title | VARCHAR(200) | nullable, 所属章节标题 |
| section_path | VARCHAR(100) | nullable, 章节路径（如 "3.2"） |
| embedding | VECTOR(1536) | nullable, pgvector 向量 |
| content_tsvector | TSVECTOR | nullable, 全文索引 |
| char_start | INTEGER | nullable, 原文起始字符位置 |
| char_end | INTEGER | nullable, 原文结束字符位置 |
| created_at | TIMESTAMP | |

索引: `(tenant_id, file_id)`, `(embedding)` (HNSW), `(content_tsvector)` (GIN)

#### datasets（数据集表 — 数据库模块用）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| name | VARCHAR(300) | 数据表名称（如"学生信息表"、"成绩表"） |
| description | TEXT | nullable, 描述 |
| source_type | VARCHAR(30) | excel / api / database（MVP 只支持 excel） |
| storage_key | VARCHAR(500) | nullable, 原始文件存储路径 |
| file_size | INTEGER | nullable, 字节 |
| row_count | INTEGER | nullable, 行数 |
| column_count | INTEGER | nullable, 列数 |
| column_names | TEXT[] | nullable, 列名数组 |
| column_types | TEXT[] | nullable, 列类型推断（string/integer/float/date） |
| tags | TEXT[] | 标签数组 |
| status | VARCHAR(20) | uploaded/processing/processed/failed |
| kg_status | VARCHAR(20) | pending/processing/done/failed，数据库级知识图谱构建状态 |
| sort_order | INTEGER | 列表排序 |
| uploaded_by | UUID FK→users | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

索引: `(tenant_id, status)`, `(tenant_id, source_type)`

说明：数据集概念类似 MySQL 数据表。每个 Excel 对应一张数据表，点开可预览行数据。知识图谱在数据库层面统一构建（见 4.2）。

#### dataset_rows（数据集行数据 — 数据库模块用）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| dataset_id | UUID FK→datasets | 所属数据集 |
| row_index | INTEGER | 行号（从 0 开始） |
| row_data | JSONB | 行数据，key 为列名 |
| created_at | TIMESTAMP | |

索引: `(tenant_id, dataset_id)`

#### document_tasks（处理任务 — 通用）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| file_id | UUID FK→files | nullable, 资源库文件 FK |
| dataset_id | UUID FK→datasets | nullable, 数据集 FK |
| task_type | VARCHAR(50) | 见 4.3 任务类型表 |
| status | VARCHAR(20) | pending/running/success/failed |
| progress | INTEGER | 0-100 百分比 |
| error_message | TEXT | nullable |
| started_at | TIMESTAMP | nullable |
| completed_at | TIMESTAMP | nullable |
| created_at | TIMESTAMP | |

索引: `(tenant_id, file_id)`, `(tenant_id, dataset_id)`, `(file_id, task_type)`, `(dataset_id, task_type)`

### 3.2 已有表变更

**knowledge_nodes 新增字段：**

| 列名 | 类型 | 说明 |
|------|------|------|
| source_chunk_id | UUID FK→document_chunks | nullable, 知识点来源切片（资源库） |
| source_file_id | UUID FK→files | nullable, 知识点来源文件（资源库，冗余加速查询） |
| source_dataset_id | UUID FK→datasets | nullable, 知识点来源数据集（数据库模块，冗余加速查询） |
| source_row_id | UUID FK→dataset_rows | nullable, 知识点来源行（数据库模块，细粒度溯源） |

**knowledge_edges 新增索引：**

- `(tenant_id, source_id, relation_type)` — 按关系类型查邻居
- `(tenant_id, target_id, relation_type)` — 反向查邻居
- `(tenant_id, relation_type)` — 按关系类型浏览

**knowledge_nodes 新增索引：**

- `(tenant_id, source_file_id)` — 按文件查所有知识点
- `(tenant_id, source_chunk_id)` — 按切片查知识点
- `(tenant_id, source_dataset_id)` — 按数据集查所有知识点
- `(tenant_id, source_row_id)` — 按行查知识点

### 3.3 resources 表处理

新建 files 表替代 resources 表。保留 resources 表不删除，新功能走 document 上下文。后续统一迁移后移除。

## 4. 处理管道

### 4.1 管道 1：资源库 — 文档上传

```
用户上传 PDF/DOCX → 选择文件夹 + 填写标签 + 选择文档类型(可选)
  ↓ 同步
保存文件到本地/MinIO → 写 files 表(status=uploaded) → 派发 Celery 任务 → 返回 file_id
  ↓ 异步（Celery Worker）
Step 1: 文档解析
  PDF → PyMuPDF 提取文本 + 标题层级
  DOCX → python-docx 提取文本 + 标题层级
  输出：结构化文档树（标题/段落/表格）
  ↓
Step 2: 结构感知切片
  按章节标题切分，保留 section_title + section_path
  单切片超 512 字时按段落二次切分，重叠 64 字
  输出：List[chunk] 写入 document_chunks 表
  ↓
Step 3: 三路并行
  3a. 向量化 — 批量调用 DashScope，chunk.content → embedding，UPDATE document_chunks
  3b. 全文索引 — PostgreSQL tsvector，chunk.content → to_tsvector('simple')
  3c. 模板抽取 — 按 doc_type 匹配硬编码模板（MVP: 教案），LLM structured output 抽取 → files.structured_data（文档级，非切片级）
  ↓
Step 4: 知识图谱抽取
  从切片中批量提取知识点和关系（LLM structured output）
  每个知识点做向量相似度去重（> 0.95 合并已有节点，只加新边）
  写入 knowledge_nodes + knowledge_edges
  设置 source_chunk_id / source_file_id
  ↓
files.status = processed
```

### 4.2 管道 2：数据库 — Excel 导入

**上传阶段（每个 Excel 独立处理）：**

```
用户上传 XLSX → 填写数据表名称 + 标签 + 描述
  ↓ 同步
保存文件到本地/MinIO → openpyxl 解析行列元数据 → 写 datasets 表(status=uploaded) → 派发 Celery 任务 → 返回 dataset_id
  ↓ 异步（Celery Worker）
Step 1: 解析 Excel 数据
  openpyxl 逐行解析 → 写入 dataset_rows（row_data = JSONB）
  更新 datasets.row_count / column_count / column_names / column_types
  ↓
Step 2: 向量化
  将每行数据拼装为结构化文本描述 → 生成 embedding
  写入 document_chunks（file_id=null, 关联 dataset_id 通过 metadata）
  ↓
datasets.status = processed
datasets.kg_status = pending
```

**知识图谱构建阶段（数据库级别，上传后自动触发）：**

```
Excel 解析+向量化完成后，自动触发
  ↓
收集当前租户下所有已处理的数据表（包括新上传的）
  ↓
Step 3: 数据库级知识图谱抽取
  将多张数据表的结构（列名、类型）和样本数据拼装为上下文
  LLM 理解表间关系（如"学生表.student_id → 成绩表.student_id"）
  LLM 从所有数据中提取知识点和跨表关系
  向量相似度去重（同管道 1 逻辑）
  写入 knowledge_nodes + knowledge_edges
  设置 source_dataset_id / source_row_id
  ↓
新数据集的 kg_status = done
```

关键设计：每上传一个 Excel 就自动触发知识图谱抽取，不需要手动操作。LLM 能看到所有数据表的结构和数据，识别跨表关系，构建出网状知识图谱。

### 4.3 任务状态流转

**资源库文件子任务（6 步）：**

| 序号 | task_type | 中文名称 | 说明 |
|------|-----------|----------|------|
| 1 | parse | 文档解析 | 解析 PDF/DOCX |
| 2 | chunk | 结构切片 | 按章节切分 |
| 3 | embed | 向量化 | 生成 embedding |
| 4 | index_tsv | 全文索引 | 生成 tsvector |
| 5 | extract_template | 模板抽取 | 按文档类型抽取结构化数据 |
| 6 | extract_kg | 知识图谱 | 抽取知识点和关系 |

**数据库数据集子任务（2 步 + 数据库级 1 步）：**

| 序号 | task_type | 中文名称 | 说明 | 作用域 |
|------|-----------|----------|------|--------|
| 1 | ds_parse | 数据解析 | 解析 Excel 行列数据 | 单数据集 |
| 2 | ds_embed | 向量化 | 生成 embedding | 单数据集 |
| 3 | ds_extract_kg | 知识图谱 | 跨数据集抽取知识点和关系 | 数据库级 |

状态：pending → running → success / failed

前端展示：
- 进度条：百分比 + 中文名称（如 "5% 文档解析"、"72% 向量化"）
- 手动刷新按钮：用户可立即查询最新状态，无需等待 3 秒轮询
- 轮询：详情页每 3 秒查询任务状态
- 失败重试：重新派发失败的任务
- 列表页：直接显示汇总状态

### 4.4 知识图谱去重策略

LLM 抽取知识点后，逐个对已有 knowledge_nodes 做向量相似度匹配：
- 相似度 > 0.95：复用已有节点，只添加新边（关系）
- 相似度 ≤ 0.95：新建节点

全校所有文档和数据集抽取的知识点汇聚成一张大网，同一知识点不管来自资源库文档还是数据库 Excel，都是同一个节点。

## 5. 业务上下文

### 5.1 document 上下文（新建 — 资源库）

```
app/contexts/document/
├── application/
│   ├── dto.py                    # FileCreateDTO, FolderCreateDTO, ChunkDTO, TaskDTO
│   ├── file_service.py           # 文件上传/管理逻辑
│   ├── folder_service.py         # 文件夹树 CRUD + 排序
│   ├── chunk_service.py          # 切片查询
│   ├── task_service.py           # 任务状态查询/重试
│   └── tasks.py                  # Celery 任务定义
│       ├── parse_document        # 文档解析
│       ├── chunk_document        # 结构切片
│       ├── embed_chunks          # 向量化
│       ├── index_tsvector        # 全文索引
│       ├── extract_template      # 模板抽取
│       └── extract_knowledge_graph  # 知识图谱抽取
├── domain/
│   └── entities.py               # 文件/文件夹/切片实体定义
├── infrastructure/
│   ├── models.py                 # FolderModel, FileModel, DocumentChunkModel, DocumentTaskModel
│   ├── file_repository.py        # FileRepository
│   ├── folder_repository.py      # FolderRepository
│   └── chunk_repository.py       # ChunkRepository
└── interfaces/api/
    ├── router.py                 # 文件夹/文件/切片 API
    └── task_router.py            # 任务状态 API
```

### 5.2 structured_data 上下文（新建 — 数据库模块）

```
app/contexts/structured_data/
├── application/
│   ├── dto.py                    # DatasetCreateDTO, DatasetRowDTO, TaskDTO
│   ├── dataset_service.py        # 数据集上传/管理逻辑
│   └── tasks.py                  # Celery 任务定义
│       ├── parse_dataset         # Excel 解析 → dataset_rows
│       ├── embed_dataset         # 向量化
│       └── extract_knowledge_graph  # 知识图谱抽取
├── domain/
│   └── entities.py               # 数据集/行数据实体定义
├── infrastructure/
│   ├── models.py                 # DatasetModel, DatasetRowModel
│   └── dataset_repository.py     # DatasetRepository
└── interfaces/api/
    ├── router.py                 # 数据集 CRUD API
    └── task_router.py            # 任务状态 API
```

### 5.3 knowledge 上下文（已有，扩展）

- knowledge_nodes: 新增 source_chunk_id, source_file_id, source_dataset_id, source_row_id 字段
- knowledge_edges: 新增网状查询索引
- 知识点抽取逻辑分别放在 document 和 structured_data 上下文的 Celery 任务中（跨上下文调用 knowledge 的 Repository）

### 5.4 resource 上下文（保留，不删除）

现有 resources 表和 API 保持不动，新功能走 document 上下文。

## 6. API 端点

### 6.1 资源库 — 文件夹

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/folders` | 获取文件夹树 |
| POST | `/api/v1/document/folders` | 创建文件夹 |
| PATCH | `/api/v1/document/folders/{id}` | 修改文件夹（名称/排序/移动） |
| DELETE | `/api/v1/document/folders/{id}` | 删除文件夹（需确认。空文件夹直接删除；含文件的文件夹需二次确认，文件移至"未分类"根文件夹） |
| PATCH | `/api/v1/document/folders/{id}/move` | 移动文件夹（修改 parent_id + path） |

### 6.2 资源库 — 文件

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/files` | 列出文件（支持 folder_id/tag/status 过滤） |
| POST | `/api/v1/document/files/upload` | 上传文件（multipart + folder_id + tags + doc_type） |
| GET | `/api/v1/document/files/{id}` | 获取文件详情 |
| GET | `/api/v1/document/files/{id}/download` | 下载文件 |
| DELETE | `/api/v1/document/files/{id}` | 删除文件（需确认） |
| PATCH | `/api/v1/document/files/{id}` | 修改文件信息（标签/文档类型等） |

### 6.3 资源库 — 任务与切片

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/document/files/{id}/tasks` | 获取文件的所有任务状态 |
| POST | `/api/v1/document/files/{id}/retry` | 重试失败的任务 |
| GET | `/api/v1/document/files/{id}/chunks` | 获取文件的切片列表 |

### 6.4 数据库 — 数据集

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/structured-data/datasets` | 列出数据集（支持 tag/status 过滤） |
| POST | `/api/v1/structured-data/datasets/upload` | 上传 Excel（multipart + name + tags + description） |
| GET | `/api/v1/structured-data/datasets/{id}` | 获取数据集详情 |
| GET | `/api/v1/structured-data/datasets/{id}/rows` | 获取数据集行数据（分页） |
| DELETE | `/api/v1/structured-data/datasets/{id}` | 删除数据集（需确认） |
| PATCH | `/api/v1/structured-data/datasets/{id}` | 修改数据集信息（名称/标签/描述/排序） |

### 6.5 数据库 — 任务与知识图谱

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/structured-data/datasets/{id}/tasks` | 获取数据集的所有任务状态 |
| POST | `/api/v1/structured-data/datasets/{id}/retry` | 重试失败的任务 |
| POST | `/api/v1/structured-data/knowledge-graph/build` | 手动重新构建数据库级知识图谱（正常流程自动触发，此接口用于重试） |
| GET | `/api/v1/structured-data/knowledge-graph/status` | 获取数据库级知识图谱构建状态 |
| GET | `/api/v1/structured-data/knowledge-graph` | 获取数据库级知识图谱（节点+边） |

## 7. 前端设计

### 7.1 侧边栏导航更新

新增"数据库"菜单项，与"资源库"平行：

```
侧边栏：
  首页
  知识库
  资源库     ← 已有，增强
  数据库     ← 新增
  AI 问答
  技能编辑器
  系统管理
```

### 7.2 资源库主界面

- 布局：Master-Detail，左侧文件夹树 + 右侧文件列表
- 文件夹树：
  - 点击切换文件夹，右侧显示该文件夹下的文件
  - 支持新建/重命名/删除/移动排序
  - 删除需 ConfirmDialog 确认
  - 底部标签筛选区，点击标签跨文件夹筛选
- 文件列表：
  - 表格展示：文件名、文档类型、标签、状态、大小、上传时间
  - 拖拽上传区 + 上传按钮
  - 上传时选择文件夹 + 填写标签 + 选择文档类型
  - 文件名可点击 → 进入文件详情页
  - 操作菜单（⋯）：下载/查看详情/重试处理/删除

### 7.3 资源库 — 文件详情页

- 顶栏：文件名、类型、大小、上传人、标签、下载/删除按钮
- 处理状态流水线：6 步横向进度条（文档解析 → 结构切片 → 向量化 → 全文索引 → 模板抽取 → 知识图谱），每步显示完成/进行中/失败图标 + 统计数量
- 进度显示：百分比 + 中文名称进度条（如 "5% 文档解析"）
- 手动刷新按钮：点击立即查询最新状态
- 三个 Tab：
  - **结构化抽取**：按文档类型模板展示抽取结果（如教案的课题/目标/重难点/过程），数据来自 files.structured_data
  - **切片列表**：所有切片按章节排列，显示向量化状态、section_path、字数
  - **知识图谱**：从本文档抽取的知识点列表和三元组关系

### 7.4 数据库主界面

- 布局：类似 MySQL 数据库管理工具，左侧数据表列表 + 右侧内容区
- 数据表列表：
  - 列出所有数据集（数据表），显示名称、行数、状态
  - 点击数据表 → 右侧显示该表的数据预览
  - 支持新增（上传 Excel 或手动新建空表）、修改（双击重命名/⋯菜单改描述标签）、删除（ConfirmDialog 确认，级联删除行数据+切片+知识点/边）、移动排序（拖拽或上移/下移）
  - 顶部"构建知识图谱"状态指示（自动触发，非手动）
  - 上传按钮 → 上传 Excel 创建新数据表
- 右侧内容区（选中某张表时）：
  - 顶栏：数据表名称、列数/行数、标签、删除按钮
  - 处理状态流水线：3 步横向进度条（数据解析 → 向量化 → 知识图谱），百分比+中文名称，手动刷新按钮（与资源库文件详情页体验一致）
  - 两个 Tab：
    - **数据预览**：表格展示 dataset_rows（分页），显示列名和行数据
    - **知识图谱（本表）**：从本数据表抽取的知识点和三元组关系

### 7.5 数据库 — 知识图谱总览

- 入口：左侧数据表列表底部的"知识图谱"区域
- 数据库级别统一展示所有数据表的关联知识图谱
- 顶部：知识图谱构建状态（自动触发，上传后自动执行）
- 展示所有从数据库数据抽取的知识点和三元组关系
- 可按数据表筛选（哪些知识点来自哪张表）
- 跨表关系高亮标注来源表

两个视角的关系：
- **单表知识图谱**（右侧 Tab）：只看当前选中表贡献的知识点和关系
- **总览知识图谱**（左侧底部入口）：看所有数据表关联的完整知识图谱网

### 7.6 复用现有组件

PageHeader、EmptyState、ConfirmDialog、LoadingSpinner、ToastContainer、useToast

### 7.7 中文状态映射

**资源库：**

| task_type | 中文名称 |
|-----------|----------|
| parse | 文档解析 |
| chunk | 结构切片 |
| embed | 向量化 |
| index_tsv | 全文索引 |
| extract_template | 模板抽取 |
| extract_kg | 知识图谱 |

**数据库：**

| task_type | 中文名称 |
|-----------|----------|
| ds_parse | 数据解析 |
| ds_embed | 向量化 |
| ds_extract_kg | 知识图谱 |

## 8. 子项目划分（完整）

| 子项目 | 范围 | 状态 |
|--------|------|------|
| A1 | 资源库增强 + 文档处理管道 + 数据库模块 + 知识图谱构建 + 任务追踪 | **本次实施** |
| A2 | 文档类型模板系统（可配置 schema + LLM 辅助初始化 + 管理界面） | 后续 |
| B | 混合检索 RAG（NER + 多通道召回 + RRF 融合 + LLM 问答 + 溯源） | 后续 |

## 9. 依赖项

| 依赖 | 用途 | 状态 |
|------|------|------|
| Celery + Redis | 异步任务队列 | 已有框架，需实现具体任务 |
| PyMuPDF (fitz) | PDF 解析 | 新增 |
| python-docx | DOCX 解析 | 新增 |
| openpyxl | XLSX 解析 | 新增 |
| pgvector | 向量存储 | 已有 |
| tsvector | 全文索引 | PostgreSQL 内置，需启用 simple 分词 |
| DashScope API | Embedding 生成 | 已有 |
| LLM API | 模板抽取 + 知识点抽取 | 已有（MiniMax/DeepSeek/Qwen） |
