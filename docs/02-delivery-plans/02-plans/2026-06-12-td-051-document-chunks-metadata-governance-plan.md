# TD-051 `document_chunks` 结构元数据、切片质量与既有数据重建 — Plan

> Plan 入口：TD-051 Spec [`2026-06-12-td-051-document-chunks-metadata-governance.md`](../01-specs/2026-06-12-td-051-document-chunks-metadata-governance.md)
> 任务卡：[`docs/03-engineering-governance/technical-debt.md#td-051`](../../03-engineering-governance/technical-debt.md#td-051-治理-document_chunks-结构元数据切片质量与既有数据重建)

## 目标

修复 `document_chunks` 的结构元数据（`section_path`、`section_title`、`char_start`、`char_end`）在入库时就已损坏的问题，并提供历史数据重建入口。

## 实施顺序

### Slice 1（PR-1）：保留 sections 到 structured_data

**目标**：`files.structured_data` 包含 `sections` 数组，而非只存 `full_text + section_count`。

**变更文件**：
- `app/contexts/document/application/tasks/extract_template_prompts.py`
  - `_build_parsed_structured_data(full_text, section_count)` → `_build_parsed_structured_data(full_text, section_count, sections)`
  - 返回值增加 `sections: list[dict]` 字段（每个 dict 含 `title`, `level`, `path`, `page`, `content`）
- `app/contexts/document/application/tasks/parse.py`
  - 第 104–108 行：将 `parsed.sections` 序列化传入 `_build_parsed_structured_data`

**向后兼容**：旧的 `structured_data` 无 `sections` 字段，chunk 阶段走 regex fallback。

**验证**：
- 新上传 PDF/DOCX 后，`SELECT structured_data FROM metaedu.files WHERE id = :fid` 包含 `sections` 数组
- `SELECT jsonb_typeof(structured_data->'sections') FROM metaedu.files` 应返回 `array`

---

### Slice 2（PR-2）：chunk_document 使用真实 sections 而非 regex 猜测

**目标**：`chunk_document` 从 `structured_data["sections"]` 构建 `ParsedDocument.sections`，不再从 `full_text` 正则猜。

**变更文件**：
- `app/contexts/document/application/tasks/chunk.py`
  - 第 58–65 行：优先读 `structured_data.get("sections")`，如果存在则直接反序列化为 `list[DocumentSection]`
  - 如果 `sections` 不存在，保留现有 regex fallback（向后兼容旧数据）
  - `char_offset` 计算逻辑：遍历 `ParsedDocument.sections`，累加 `section.content` 长度 + 1（换行符），为每个 section 内的 chunk 提供基础偏移
  - 每个 section 内第一个 chunk 的 `char_start` = 该 section 在 `full_text` 中的实际起始偏移

**关键逻辑**（chunk.py 新增）：
```python
# 优先使用 structured_data 中的 sections
raw_sections = sd.get("sections", [])
if raw_sections:
    from app.shared.parsing.pdf_parser import DocumentSection
    sections = [
        DocumentSection(
            title=s.get("title", ""),
            level=s.get("level", 0),
            content=s.get("content", ""),
            page=s.get("page", 0),
            path=s.get("path", ""),
        )
        for s in raw_sections
    ]
else:
    # fallback: 从 full_text regex 猜（现有逻辑）
    sections = _reconstruct_sections_from_full_text(full_text)
```

**验证**：
- 新切片后，`SELECT section_path FROM metaedu.document_chunks WHERE file_id = :fid` 不再全部为空
- `SELECT section_title FROM metaedu.document_chunks` 空值率接近真实无标题比例

---

### Slice 3（PR-3）：修复 _enforce_size_limit 的 char_start/char_end

**目标**：oversized chunk 拆分后，子 chunk 继承正确的 `char_start`/`char_end` 偏移。

**变更文件**：
- `app/shared/parsing/chunker.py`
  - `_enforce_size_limit`：拆分时计算子 chunk 在原始文本中的实际偏移
  - 需要传入 chunk 的 `char_start`（chunk 内容在原始 full_text 中的起始位置）
  - `_split_oversized_chunk` 返回时附带每段的偏移信息

**验证**：
- 对已知长度的超大 section 触发强制拆分，`SELECT char_start, char_end FROM metaedu.document_chunks` 验证单调递增且覆盖正确内容
- 新增 `tests/shared/parsing/test_chunker.py` 单元测试：
  - `_enforce_size_limit` 后子 chunk 的 `char_start`/`char_end` 连续
  - `char_end - char_start == len(content)` 恒成立

---

### Slice 4（PR-4）：chunk size 策略评估 + 参数明确化

**目标**：评估当前 chunk 长度分布（350–499 字为主），明确 `TARGET_CHUNK_CHARS` 推荐值及边界参数。

**分析内容**：
- 当前 `TARGET_CHUNK_CHARS = 500`，`CHUNK_HEADROOM = 80`，`MIN_SENTENCES_KEPT = 1`
- 822 条 350–499 字 chunk 是否合理？
- 是否引入 `MIN_CHUNK_CHARS`（当前隐式 80）？
- 是否引入 parent-child chunk 或 neighbor expansion？

**结论记录**：
- 如果维持现状，在 `chunker.py` 注释中明确说明推荐理由
- 如果调整，在 spec 中记录新参数值
- neighbor expansion / parent-child 作为 P2 任务登记，不在本 TD 范围内

**验证**：
- 调整参数后，本机 PG 重新跑一片样本，对比前后长度分布

---

### Slice 5（PR-5）：历史数据重建入口

**目标**：提供可重复命令，对已入库文件重跑 parse → chunk → embed → tsvector → KG 回源。

**方案**：扩展现有的 reinitialize pipeline。

在 `app/contexts/document/application/tasks/` 下新增 `rebuild_chunks.py` Celery task 或 management command：

```python
@shared_task(name="rebuild_document_chunks")
def rebuild_document_chunks(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    """重新解析并切片指定文件的 document_chunks。

    不触发 embed 和后续步骤（由 embed_chunks 链式触发）。
    适用于：TD-051 修复后对历史数据的全量重建。
    """
```

或者扩展 `chunk.py` 的 `pipeline_version` 机制，使 reinitialize 能按新策略重跑。

**验证**：
- 选一个已知 chunk 质量差的 file_id，重跑 rebuild 后对比前后 `section_path`/`char_start`/`char_end`
- orphan chunks 清理：识别 + DELETE 或标记

---

### Slice 6（PR-6）：orphan chunks 清理

**目标**：清理 100 条 orphan chunks（`file_id` 在 `files.id` 中不存在）。

**方案**：
```sql
DELETE FROM metaedu.document_chunks
WHERE file_id NOT IN (SELECT id FROM metaedu.files);
```

在 `rebuild_chunks.py` 或单独 SQL 脚本中执行。

**验证**：
- 执行后 `SELECT COUNT(*) FROM metaedu.document_chunks WHERE file_id NOT IN (SELECT id FROM metaedu.files)` = 0

---

### Slice 7（PR-7）：后端 pytest 扩展

**目标**：新增 chunk 相关单元测试，防止回归。

**新增测试文件**：`tests/shared/parsing/test_chunker.py`

测试用例：
- `test_chunk_sections_preserve_path`：section path 正确传递到 Chunk
- `test_enforce_size_limit_preserves_offsets`：oversized split 后 char_start/char_end 连续
- `test_char_offset_monotonic`：chunk char_start单调递增
- `test_chunk_covers_content`：chunk.char_end - chunk.char_start == len(chunk.content)

---

## 验证矩阵

| 验收标准 | 验证方式 |
|----------|----------|
| AC-1 sections 保留 | 新建文件后 `SELECT structured_data->'sections' IS NOT NULL` |
| AC-2 section_path 不全空 | 新切片后 `SELECT COUNT(*) FROM document_chunks WHERE section_path = ''` / total < 10% |
| AC-3 char_offset 准确 | `_enforce_size_limit` 测试 + 手动验证 3 个 chunk |
| AC-4 chunk 长度分布 | 重建前后长度分布对比 |
| AC-5 历史数据可重建 | 选 1 个文件重跑，观察 section_path 非空 |
| AC-6 orphan chunks 清理 | SQL 查询孤儿数为 0 |
| AC-7 BUG-003 协同 | 复测 "Python 的基本数据类型有哪些？" |

## 当前状态

- 状态：⚫ 待计划（Spec 已完成）
- 分支：`refactor/td-051-document-chunks-metadata`
