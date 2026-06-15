# BUG-006: 资源库展示与抽取 3 类残留问题（前端字段名 / pdf_parser section / TD-067 nested 回归）

Status: 🔵 Ready
Priority: P1
Milestone: P1 RAG 治理 / 资源库 UX
Source: 2026-06-15 用户重新上传 `01-人才培养方案环境监测技术专业.pdf` 后审查发现（用户 + Claude Code 真 PG 复测）

## 背景

worker 重启后（commit `56f2ad3` 之后）用户重新上传文件，6 步流水线全部 success；今日合并的 BUG-005 / TD-054 R2/R3 / TD-067 大部分修复**真实生效**：

✅ 已修复（worker 跑最新代码后）
- `files.doc_type='人才培养方案'` / `template_id` 已填充（BUG-005 PR #285）
- `offset_overlaps: 0/28 (0.00%)`（TD-054 R3 PR #290）
- 知识图谱前端可见（58 节点 + 154 边，53/58 关联到 chunk）
- 模板 `curriculum_system` 39 门课程正确抽取（TD-067 PR #287 在 array[object] 单层 children 上生效）
- 模板 `basic_info` 5 字段全部填充

❌ 仍残留 3 类问题（本任务范围）

### 1. 前端模板抽取页面渲染英文 key 而非中文 label

页面展示 `major_name: 环境监测技术`、`degree: -`、`training_level: 中职` 等，应展示 `专业名称: 环境监测技术`。后端 `structured_data.template` 用 key 作为 JSON 字段（设计如此 —— 持久化用 stable key），前端应当查 `templates.fields[].label` 把 key 翻译成中文。

### 2. `pdf_parser` 不识别中文一二三...章节标题 → `structured_data.sections` 只有 1 个空 section

真 PG 复测：`structured_data.sections` 长度 = 1，第一个 section 的 `title=''` / `path=''`。但文档原文有清晰的中文标题：「一、专业名称与代码」「二、入学要求」「三、修业年限」「四、职业面向」「五、培养目标与培养规格」「六、课程设置」「七、学时安排」「八、教学进程总体安排」「九、教学进度安排」等。

下游影响：
- `document_chunks.section_title / section_path = '' AND ''`（28/28）—— TD-053 fallback 修过 path 但**前提是 sections 至少有 title**，本场景 sections 本身就是 1 个空 section
- AI Chat 溯源 / Resource Library 章节面包屑无法工作

**根因定位**：问题在 `packages/server-python/app/shared/parsing/pdf_parser.py`（不是 `chunker.py` / `chunk_document.py`）。pdf_parser 的章节识别正则只匹配 markdown `## ` 等英文 heading，没匹配中文「一、二、三、（一）（二）」等编号标题模式。

### 3. TD-067 在 `nested array[object with multi children]` / `table multi-col` / `object with multi children` 上未真正命中

真 PG 复测：`teaching_plan: '-'` / `practice_links: '-'` / `graduation_requirements: '-'` / `degree_requirements: { 4 字段全 - }`。

但 `curriculum_system: array[object with single child course]` 正常抽取出 39 门课程。

**TD-067 的 fewshot examples 在 `array[object[children]]` 单 child 上有效，在以下 schema 上失效**：
- `array[object[children with NESTED children]]`（teaching_plan 学期→课时表，2 层嵌套）
- `table[multi columns]`（practice_links 实践环节表，4 列）
- `object[multi children]`（degree_requirements 4 字段对象）
- `text` / `array[strings]`（graduation_requirements）

PR #287 的 `build_few_shot_examples` 已对前 3 类 emit examples（[test_extract_template_few_shot_examples.py](../../../packages/server-python/tests/contexts/document/test_extract_template_few_shot_examples.py)），但 LLM **依然返 `-`**——说明：fewshot 示例已注入 prompt，但 LLM 对这些复杂 schema 的抽取仍失败。可能原因：
- prompt 中 fewshot 位置 / 上下文长度不当（`chunks_text[:6000]` 截断把示例挤掉）
- LLM 模型本身对中文嵌套 schema 抽取能力不足（即使有示例）
- schema 描述层级太深（teaching_plan: array→object→object→text 4 层）需更明确的引导
- table 类型的 fewshot 示例与实际页面布局不匹配（实际是横版课时表，example 是纵版）

## 复现路径

### 复现 #1（前端字段名）

1. 上传任意有模板匹配的文件到 Resource Library
2. 等 6 步流水线 success
3. 文件详情 → 模板抽取 tab
4. 字段名应是中文 label（专业名称），实际是英文 key（major_name）

### 复现 #2（pdf_parser section）

```sql
SELECT
  jsonb_array_length(coalesce(structured_data->'sections', '[]'::jsonb)) AS section_count,
  structured_data->'sections'->0->>'title' AS first_section_title,
  structured_data->'sections'->0->>'path' AS first_section_path
FROM metaedu.files
WHERE id = '<file_id>';
-- 期望（多 section 文档）: section_count >= 5 + 第 1 个 title 非空
-- 实际: section_count = 1, first_section_title = '', first_section_path = ''
```

### 复现 #3（TD-067 nested 回归）

```sql
SELECT
  structured_data->'template'->>'teaching_plan' AS teaching_plan,
  structured_data->'template'->>'practice_links' AS practice_links,
  structured_data->'template'->>'graduation_requirements' AS graduation_requirements,
  structured_data->'template'->'degree_requirements' AS degree_requirements
FROM metaedu.files
WHERE id = '<file_id>' AND doc_type = '人才培养方案';
-- 期望: 4 个字段全部非 '-'（curriculum_system 都成功抽取了 39 门课）
-- 实际: 全部 '-' 或子字段全 '-'
```

## 期望行为

1. **前端字段名**：模板抽取 tab 渲染 `field.label`，保留 `field.key` 作为内部 anchor / DOM id
2. **pdf_parser section**：识别中文「一、二、三、（一）（二）」等编号标题；多章节文档 `structured_data.sections` 长度 ≥ 5；每个 section 至少 `title` 非空
3. **TD-067 nested**：`teaching_plan` / `practice_links` / `degree_requirements` / `graduation_requirements` 4 个字段在人才培养方案样本上至少 1 个抽取成功（其余记录 LLM 返 `-` 的原始响应供后续优化）

## 怀疑点

1. **#1 前端字段名**：`packages/web/src/components/.../FieldCard*.vue` 或 `FileTabsPanel.vue` 模板抽取展示组件渲染 `{{ field.key }}` 而非 `{{ field.label }}`（具体文件需 git grep 定位）
2. **#2 pdf_parser**：`pdf_parser.py` 的 section 识别正则只匹配 `^##\s+|^#\s+` 等英文 heading，没匹配中文编号 `^[一二三四五六七八九十]、` 或 `^（[一二三四五六七八九十]）` 模式
3. **#3 TD-067 nested**：
   - 检查 prompt 实际生成内容（`extract_template.py` 的 `prompt_template` 拼装位置 + `chunks_text[:6000]` 截断是否把 fewshot 挤掉）
   - 检查 LLM 真实返回（task log 应该 caplog 记录原始响应）
   - 抽样人工读 prompt 看 fewshot 示例是否对 nested schema 真的清晰
   - 考虑切换更强模型（如 GPT-4o → 当前可能用了较弱的本地模型）

## 完成标准

- 上传任一有模板匹配的多章节文件后：
  - 前端字段名展示中文 label（人工 review 前端 → 应至少 90% 字段名是中文，10% 容错给历史模板未填 label 的字段）
  - SQL 查询 `section_count >= 5` AND `first_section_title != ''`
  - SQL 查询人才培养方案 4 个嵌套字段中至少 1 个非 `-`
- 自动化测试：
  - 前端：`FieldCard.spec.ts` 加 `renders label not key` 用例
  - 后端：`tests/shared/test_pdf_parser.py` 加「中文一二三标题识别」用例（`test_chinese_chapter_heading_identified`）
  - 后端：`tests/contexts/document/test_extract_template_nested_recovery.py` 加「人才培养方案样本」mock 用例验证 prompt 含 fewshot 段（已有的 [test_extract_template_few_shot_examples.py](../../../packages/server-python/tests/contexts/document/test_extract_template_few_shot_examples.py) 已锁 helper，本任务锁端到端集成）

## 验证方式

- `pnpm test web -- FieldCard` 用例覆盖 label-vs-key 渲染
- `cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_pdf_parser.py tests/contexts/document/test_extract_template_nested_recovery.py -v`
- 真 PG dev 库重新上传 1 个人才培养方案 + 1 个教案后跑 3 个 SQL 确认 3 类指标改善
- `ruff check app/ tests/` clean / `git diff --check` clean / `scripts/check-engineering-docs` exit 0

## 不在范围

- KG 节点未绑文件（实测 58/58 已绑，worker 重启后自然修复）
- chunk_quality_report `offset_overlaps` 0%（已由 TD-054 R3 PR #290 修复，本次复测 0/28）
- `files.doc_type` / `template_id` 回写（已由 BUG-005 PR #285 修复）
- `curriculum_system` array[course] 单层抽取（已由 TD-067 PR #287 修复）
- 任何 alembic schema 改动
- 切换 LLM 模型（属运维决策，不在本 BUG 范围）

## 关联

- BUG-005（doc_type 回写，已 Done）
- TD-053（fallback section_path，已合 PR #235）
- TD-054 R2/R3（chunker offset，已 Done）
- TD-067（few-shot 示例，已 Done；本 BUG #3 是其 follow-up）
- REQ-010（P1 RAG 证据治理，本 BUG 是 evidence_coverage / 章节溯源 follow-up）

## 拆分建议（实现时）

3 类问题独立性强、修复路径不重叠，建议拆 3 个 PR 分别开发：

1. **PR-1（前端，最简）**：BUG-006 #1 字段名 label 渲染 + Vue 单测（≤ 50 行 vue 代码 + 30 行 test）
2. **PR-2（后端 pdf_parser）**：BUG-006 #2 中文章节标题识别 + 真 PG 复测验收
3. **PR-3（后端 prompt 调优 / 模型切换）**：BUG-006 #3 TD-067 nested 回归（先 spike 看 LLM 真实返回，再决定改 prompt 还是切模型）
