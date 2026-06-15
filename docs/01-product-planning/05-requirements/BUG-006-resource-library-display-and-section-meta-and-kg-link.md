# BUG-006: 资源库展示与切片溯源 3 类问题（结构化抽取字段名 / chunk section_path / KG 文件归属）

Status: 🔵 Ready
Priority: P1
Milestone: P1 RAG 治理 / 资源库 UX
Source: 2026-06-15 用户重新上传 `01-人才培养方案环境监测技术专业.pdf` 后审查发现（用户提供 + Claude Code 真 PG 复测）

## 背景

worker 重启后（commit `56f2ad3` 之后）用户重新上传文件，6 步流水线全部 success（doc_type / template_id / offset_overlaps 等指标已修），但仍发现 3 类残留问题：

### 1. 结构化抽取页面字段名是英文 key 而非中文 label

页面渲染 `major_name: 环境监测技术`、`degree: -`、`training_level: 中职` 等，应展示 `专业名称: 环境监测技术`。Field 模型已定义 `label`（如"专业名称"）和 `key`（如"major_name"），DB `templates.fields` 也有 label，但前端 `FieldCard` / 模板抽取展示组件直接渲染 key 作为字段名。

### 2. `document_chunks.section_title` / `section_path` 100% 空

真 PG 复测：28/28 chunks 的 `section_title='' AND section_path=''`。结构化解析正确产生了 sections（dev 库 `structured_data.sections` 数组非空）但 `chunk_document` task 写入 chunks 时未传递 section title / path。这是 TD-053 的衍生 bug——TD-053 修了 fallback 路径补 section_path，但**主路径** `chunk_by_structure` 在生产数据上仍空。

### 3. 知识图谱页面没显示 + `knowledge_nodes.source_file_id = 0`

真 PG 复测：`knowledge_nodes total=145`（dev 库历史数据）但 `knowledge_nodes WHERE source_file_id = <new_file>` = 0。`extract_knowledge_graph` task 成功执行（document_tasks status=success）但抽出的节点未绑定到本次上传的 file_id，导致前端按文件查 KG 永远是空。

## 复现路径

### 复现 #1（前端字段名）

1. 上传任意有模板匹配的文件（如人才培养方案）到 Resource Library。
2. 等 6 步流水线 success。
3. 打开文件详情 → 模板抽取 tab。
4. 观察字段名：应该是中文（专业名称、入学要求 等），实际是英文（major_name、enrollment_object 等）。

### 复现 #2（chunk section_path）

```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE section_path IS NULL OR section_path = '') AS sp_empty,
  COUNT(*) FILTER (WHERE section_title IS NULL OR section_title = '') AS st_empty
FROM metaedu.document_chunks
WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
AND file_id = '<new_file_id>';
-- 期望: sp_empty / st_empty 远低于 total（多 section 文档应有大部分 section_path 非空）
-- 实际: sp_empty = st_empty = total（100% 空）
```

### 复现 #3（KG 文件归属）

```sql
-- 上传文件后 extract_kg success
SELECT COUNT(*) FROM metaedu.knowledge_nodes
WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
AND source_file_id = '<new_file_id>';
-- 期望: > 0（应有抽出的实体绑定到此文件）
-- 实际: 0（所有节点 source_file_id 都是其他历史文件或 NULL）
```

前端 KG 页面按 `source_file_id` 过滤显示节点 → 永远空白。

## 期望行为

1. **字段名**：模板抽取展示组件渲染 `field.label` 而非 `field.key`；保留 `key` 作为内部 anchor。
2. **chunk section_path**：当 `structured_data.sections` 非空时，`chunk_document` 主路径必须把每个 chunk 关联回其所属 section 的 title + path（不是只 fallback 路径才补）。
3. **KG 节点归属**：`extract_knowledge_graph` 把抽出的每个节点的 `source_file_id` 设置为当前 file_id（已抽出 `source_chunk_id` 的节点应自动 derive `source_file_id` from chunk）。

## 怀疑点

1. **#1 前端字段名**：`packages/web/src/components/...FieldCard*.vue` 或资源库详情页模板抽取 tab 渲染处用了 `{{ field.key }}` 而非 `{{ field.label }}`。
2. **#2 chunk section_path**：`packages/server-python/app/contexts/document/application/tasks/chunk_document.py` 主路径调 `chunk_by_structure(parsed)` 但没有把 `parsed.sections` 的 title/path 传递；或 `chunker.py` 创建 Chunk 时只设 `section_title=section.title, section_path=section.path` 但 `section.title/path` 本身在 PDF parser 里就是空。
3. **#3 KG file 归属**：`extract_knowledge_graph._do` 创建 `KnowledgeNode` 时未传 `source_file_id`；或传了但 alembic schema 该字段是 nullable，没有 NOT NULL 约束兜底。

## 完成标准

- 上传任一有模板匹配的文件后，**前端**模板抽取页面字段名全部展示为中文 label（不再有英文 key）。
- 上传任一多 section 文档（如人才培养方案）后，真 PG 查询 `section_path_empty / total ≤ 30%`（少量首章节、未识别标题等可空）。
- 上传任一可抽出 KG 实体的文档后，真 PG 查询 `knowledge_nodes WHERE source_file_id = <file_id>` ≥ 5（具体阈值按文档类型）。
- mock pytest 锁回归（前端：`FieldCard.spec.ts` 加 label-not-key 用例；后端：`test_chunk_document.py` 加 section propagation 用例 + `test_extract_kg.py` 加 source_file_id 用例）。

## 验证方式

- `pnpm test web -- FieldCard` 用例覆盖 label-vs-key 渲染。
- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_chunk_document.py tests/contexts/document/test_extract_kg.py -v`。
- 真 PG dev 库重新上传 1 个文件后跑 3 个 SQL（上方"复现路径"）确认 3 类指标达成。
- `scripts/ai/evidence_coverage_report.py` 复跑后 `node_source_chunk` 应非零。
- `ruff check app/ tests/` clean / `git diff --check` clean / `scripts/check-engineering-docs` exit 0。

## 不在范围

- chunk_quality_report `offset_overlaps` 0%（已由 TD-054 R3 PR #290 修复）。
- `files.doc_type` / `template_id` 回写（已由 BUG-005 PR #285 修复）。
- 模板嵌套字段返 `-`（已由 TD-067 PR #287 修复）。
- TD-053 fallback 路径补 path 逻辑（已合 PR #235）。
- 任何 alembic schema 改动（KG `source_file_id` 列已存在，本 BUG 只修代码不改 schema）。

## 关联

- BUG-005（doc_type 回写，已 Done）
- TD-053（fallback section_path 已修，本 BUG 修主路径）
- TD-054 R2/R3（chunker offset，已 Done）
- TD-067（few-shot 示例，已 Done）
- REQ-010（P1 RAG 证据治理，本 BUG 是 evidence_coverage 后续 follow-up）
