# TD-051 `document_chunks` 结构元数据、切片质量与既有数据重建 — Spec

> Spec 入口：TD-051（债务定义 2026-06-12）。本文件定义问题根因、现状快照与验收标准；实施 plan 另见 [`2026-06-12-td-051-document-chunks-metadata-governance-plan.md`](../02-plans/2026-06-12-td-051-document-chunks-metadata-governance-plan.md)。
> 任务卡：[`docs/03-engineering-governance/technical-debt.md#td-051`](../../03-engineering-governance/technical-debt.md#td-051-治理-document_chunks-结构元数据切片质量与既有数据重建)
> 前置背景：BUG-003 AI Chat 排查 / 2026-06-12 `document_chunks` 只读统计

## 1. 背景

TD-051 是 BUG-003 AI Chat 回答质量回归排查中发现的数据层根因。`document_chunks` 表的结构元数据（`section_path`、`section_title`、`char_start`、`char_end`）在入库时就已经不可信，导致 AI Chat 引用定位、neighbor expansion、KG 回源和文档详情高亮都缺稳定基础。只修召回 / prompt 不能解决根本问题。

## 2. 问题根因（事实锁死）

### 2.1 parse_document — sections 被丢弃

| 文件 | 行 | 行为 |
|------|-----|------|
| `pdf_parser.py` | 33–122 | `extract_pdf_text` 返回 `ParsedDocument(sections=[DocumentSection(title, level, content, page, path)], full_text=...)` — 原始 sections 含 path（如 "3.2"）和 page |
| `docx_parser.py` | 8–88 | 同上，`extract_docx_text` 返回完整 sections |
| `extract_template_prompts.py` | 28–30 | `_build_parsed_structured_data` 只保存 `{"full_text": str, "section_count": int}` — **sections 数组被丢弃** |

```python
# extract_template_prompts.py:28
def _build_parsed_structured_data(full_text: str, section_count: int) -> dict[str, object]:
    return {"full_text": full_text, "section_count": section_count}  # sections 丢失
```

### 2.2 chunk_document — 从残缺的 full_text 逆向猜 sections

| 文件 | 行 | 行为 |
|------|-----|------|
| `chunk.py` | 65–100 | 读取 `structured_data` 只得到 `full_text`，再从 `full_text` 里用正则 `r'\n(?=##\s)'` 拆分出 `DocumentSection` — 原始 path/page/level 全部丢失 |

原始 parser 已正确计算每个 section 的 path（`"3.2"`）、page（页码），但 chunk_document 重新从 markdown 文本猜，100% 的 `section_path` 空值由此产生。

### 2.3 chunker._enforce_size_limit — 拆分后偏移丢失

| 文件 | 行 | 行为 |
|------|-----|------|
| `chunker.py` | 178–198 | `_enforce_size_limit` 拆分 oversized chunk 时，新建 `Chunk(section_title=..., section_path=..., index=...)` — **没有传递 `char_start`/`char_end`，默认为 0** |

```python
# chunker.py:190–195
new_chunk = Chunk(
    content=sc,
    section_title=chunk.section_title,
    section_path=chunk.section_path,
    index=chunk.index,  # char_start / char_end 丢失
)
```

### 2.4 本机 `metaedu.document_chunks` 统计（tenant `default`，2026-06-12）

| 指标 | 值 |
|------|-----|
| 总 chunk 数 | 1551 |
| `section_path` 空 | 1551 / 1551（**100%**） |
| `section_title` 空 | 325 / 1551（约 **21%**） |
| `char_start` / `char_end` 为 null | 各 100 |
| `char_start = 0 AND char_end = 0` | 278 |
| orphan chunks（file_id 找不到 files.id） | 100 |
| 长度 < 100 字 | 121 条 |
| 长度 100–199 字 | 87 条 |
| 长度 200–349 字 | 221 条 |
| 长度 **350–499 字** | **822 条**（主体） |
| 长度 500–799 字 | 233 条 |
| 长度 800–1199 字 | 39 条 |
| 长度 ≥ 1200 字 | 28 条 |

## 3. 现状快照（2026-06-12 验证）

### 3.1 structured_data 写入路径

```
parse_document (task)
  → extract_pdf_text / extract_docx_text  → ParsedDocument(sections=[...], full_text="...")
  → _build_parsed_structured_data(full_text, section_count)  → {"full_text": "...", "section_count": N}
  → UPDATE metaedu.files SET structured_data = CAST(:data AS JSONB)
```

### 3.2 chunk_document 读取路径

```
chunk_document (task)
  → SELECT structured_data FROM metaedu.files
  → sd["full_text"]  → 字符串，无 sections
  → re-parse full_text by ## headings (regex)
  → chunk_by_structure(parsed)
  → DELETE + INSERT metaedu.document_chunks
```

### 3.3 关键文件影响范围

| 文件 | 变更类型 |
|------|----------|
| `app/contexts/document/application/tasks/extract_template_prompts.py` | 修改 `_build_parsed_structured_data`，新增 `sections` 字段 |
| `app/contexts/document/application/tasks/parse.py` | 传递完整 `parsed.sections` 到 structured_data |
| `app/contexts/document/application/tasks/chunk.py` | 从 structured_data 读取 sections 而非重新猜；计算 char_offset |
| `app/shared/parsing/chunker.py` | `_enforce_size_limit` 保留 `char_start`/`char_end` |
| `app/shared/parsing/pdf_parser.py` | `DocumentSection.path` 已正确计算（无需修改） |
| `app/shared/parsing/docx_parser.py` | 同上 |
| 数据重建脚本（新增） | 重复 parse → chunk → embed → tsvector → KG 回源 |

## 4. 验收标准

### AC-1：sections 保留

- `files.structured_data` 包含 `sections` 数组，每个元素含 `title`、`level`、`path`、`page`、`content`
- `chunk_document` 从 `structured_data["sections"]` 而非从 `full_text` 正则猜构建 `ParsedDocument.sections`

### AC-2：section_path / section_title 可信

- 新生成 chunk 的 `section_path` 不再全空
- 对无法归属章节的文档（无标题 PDF），fallback `section_path=""` + `section_title=""`
- `section_title` 空值率应接近真实无标题 section 比例（不再是 21% 假性空值）

### AC-3：char_start / char_end 准确

- 新生成 chunk 的 `char_start`/`char_end` 覆盖 chunk 内容，且单调递增
- `_enforce_size_limit` 拆分后，子 chunk 继承父 chunk 的内容范围并正确偏移

### AC-4：chunk 长度分布改善

- 推荐 chunk size 评估后，明确 `TARGET_CHUNK_CHARS` 取值（当前 500）
- 过长 chunk（≥1200）比例减少

### AC-5：历史数据可重建

- 提供可重复的重建入口，支持对已入库文件重跑 parse → chunk → embed → tsvector → KG 回源
- 重建前记录基线指标（空字段率、orphan chunks）；重建后对比改善

### AC-6：orphan chunks 清理

- 识别 100 条 orphan chunks（`file_id` 在 `files.id` 中不存在）
- 提供清理或隔离方案

### AC-7：与 BUG-003 协同

- TD-051 完成后，复测 "Python 的基本数据类型有哪些？" 回答质量（AI Chat evidence pipeline 依赖可信 chunk 元数据）
