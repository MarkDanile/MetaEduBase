# RAG 真实 PG 验收报告 — 2026-06-17

## 环境
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- 时间: 2026-06-17T08:50:04.171858+08:00
- LLM provider: `deepseek`

## 1. 样例文件清单与回填状态

| file_id | label | before | after | 命令 | 退出码 |
|---------|-------|--------|-------|------|--------|
| `358bd704-d223-4228-8935-3a6e1b3e699f` | Python 教程 PDF | {"file": {"id": "358bd704-d223-4228-8935-3a6e1b3e699f", "status": "processed", "doc_type": "课程标准", "template_id": "6ac6e47a-8e29-43a9-add3-5a48e8e3df8d"}, "chunks": 875, "embeddings": 875, "tsvectors": 875, "section_titles": 875, "section_paths": 875, "char_offsets": 875, "kg_nodes": 31, "kg_chunk_resolved": 30, "kg_edges": 27} | {"file": {"id": "358bd704-d223-4228-8935-3a6e1b3e699f", "status": "processed", "doc_type": "课程标准", "template_id": "6ac6e47a-8e29-43a9-add3-5a48e8e3df8d"}, "chunks": 875, "embeddings": 875, "tsvectors": 875, "section_titles": 875, "section_paths": 875, "char_offsets": 875, "kg_nodes": 31, "kg_chunk_resolved": 30, "kg_edges": 27} | - | - |
| `93101825-eb59-442f-838b-3c3b9894051f` | 人才培养方案 PDF | {"file": {"id": "93101825-eb59-442f-838b-3c3b9894051f", "status": "processed", "doc_type": "人才培养方案", "template_id": "50070278-61f4-4fb0-af1f-2778691d913d"}, "chunks": 36, "embeddings": 36, "tsvectors": 36, "section_titles": 36, "section_paths": 36, "char_offsets": 36, "kg_nodes": 128, "kg_chunk_resolved": 123, "kg_edges": 130} | {"file": {"id": "93101825-eb59-442f-838b-3c3b9894051f", "status": "processed", "doc_type": "人才培养方案", "template_id": "50070278-61f4-4fb0-af1f-2778691d913d"}, "chunks": 36, "embeddings": 36, "tsvectors": 36, "section_titles": 36, "section_paths": 36, "char_offsets": 36, "kg_nodes": 128, "kg_chunk_resolved": 123, "kg_edges": 130} | - | - |
| `132a8cfd-d1d1-429e-9871-68aab82f5ec3` | 课程标准 / 教案 PDF | {"file": {"id": "132a8cfd-d1d1-429e-9871-68aab82f5ec3", "status": "processed", "doc_type": "课程标准", "template_id": "6ac6e47a-8e29-43a9-add3-5a48e8e3df8d"}, "chunks": 12, "embeddings": 12, "tsvectors": 12, "section_titles": 12, "section_paths": 12, "char_offsets": 12, "kg_nodes": 81, "kg_chunk_resolved": 68, "kg_edges": 44} | {"file": {"id": "132a8cfd-d1d1-429e-9871-68aab82f5ec3", "status": "processed", "doc_type": "课程标准", "template_id": "6ac6e47a-8e29-43a9-add3-5a48e8e3df8d"}, "chunks": 12, "embeddings": 12, "tsvectors": 12, "section_titles": 12, "section_paths": 12, "char_offsets": 12, "kg_nodes": 81, "kg_chunk_resolved": 68, "kg_edges": 44} | - | - |

## 2. Context Packer 问答验收

外部 LLM `ask` 本次未运行：真实调用会把 dev DB 文档切片和 prompt context 发送到第三方 LLM provider，需要用户显式批准后单独跑。

本次改为执行“不外发 LLM”的 prompt 前截停验收，覆盖真实 dev DB、后端服务、dev JWT、生产编排同款组件：

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 样例数据是否足够 | ✅ | Python 教程文件 `358bd704-d223-4228-8935-3a6e1b3e699f` 已 processed；875 chunks / 875 embeddings / 875 tsvectors / 875 section paths。 |
| 正文 chunk 是否存在 | ✅ | chunk 54 / 55 / 61 / 64 覆盖“整数 / 浮点数 / 字符串 / 布尔值 / 列表 / 字典”等正文。 |
| 生产并发检索是否稳定 | ❌ | `CompositeChunkRetriever` 真实 DB 下共享同一个 SQLAlchemy `AsyncSession` 并发查询，报 `concurrent operations are not permitted`，chunk retriever 失败。 |
| RRF 后 evidence 是否保留 | ❌ | RRF 分数约 `0.03`，仍被旧的 `min_evidence_score=0.3` 过滤，fused evidence 被清空。 |
| 顺序检索对照是否命中正文 | ❌ | keyword fallback 返回目录 / 简介优先，正文 chunk 54 / 55 / 61 未进入 top 8。 |
| packed context 是否包含基本类型正文 | ❌ | 对照验收输出 `PROMPT_HAS_BASIC_TYPES=False`；ContextPacker 只能围绕目录 / 简介 / 无关 chunk 扩展。 |

结论：当前失败发生在 LLM 之前，不是“模型不聪明”。真实数据可用，但生产检索编排、RRF 阈值和 fallback 排序仍会让 prompt 缺正文证据；已登记 [BUG-009](../../01-product-planning/05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md)。

## 3. BUG-007 真 PG reparse 复测

| file_id | label | section_count | empty_path | abnormal_path | chinese_title | 结论 |
|---------|-------|---------------|------------|---------------|---------------|------|
| `358bd704-d223-4228-8935-3a6e1b3e699f` | Python 教程 PDF | 875 | 0 | 0 | 704 | ✅ |
| `93101825-eb59-442f-838b-3c3b9894051f` | 人才培养方案 PDF | 36 | 0 | 0 | 36 | ✅ |
| `132a8cfd-d1d1-429e-9871-68aab82f5ec3` | 课程标准 / 教案 PDF | 12 | 0 | 0 | 12 | ✅ |

## 4. BUG-006 五子项真 PG 复测

| sub_id | title | verification | conclusion | notes |
|--------|-------|--------------|------------|-------|
| #1 | 模板字段名 label（递归 children + keyPath） | templates 取最新 1 个 `人才培养方案`，递归断言 fields / children / items / columns label 非空（顶层 7 字段） | ✅ |  |
| #2 | pdf_parser 中文章节正则（fallback） | 复用 bug007 子命令的 chinese_title_count 统计 | 见 bug007 章节 |  |
| #3 | 嵌套 schema 描述 + few-shot 前移 + 截断扩展 | 直接调用 build_fields_desc，断言嵌套子字段递归出现 | ✅ | outer(外层)[object型，含子字段：  inner(内层)[string型]] |
| #4 | KG > 50 节点 kg-bundle | 最大 nodes file `fc5c6690-10f9-4045-8ed3-6c6788ebbe39` (135 节点); HTTP 200 | ✅ |  |
| #5 | 文件详情页返回按钮 (router.replace + type=button) | 手动 dev 浏览器验收；脚本仅记录提示 | 手动 | 需在 dev 前端手测：FileDetailView goBack 后 URL 不残留错乱 query |

## 5. 失败归因与新登记

| 现象 | 归因 | 新 REQ / BUG / TD |
|------|------|-------------------|
| “python 的基本数据类型有哪些？”真实样例仍无法在 prompt 前拿到正文 chunk | 生产检索编排共享 `AsyncSession` 并发失败；RRF 分数被旧绝对阈值清空；keyword fallback 目录 / 简介优先 | [BUG-009](../../01-product-planning/05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md) |
| 外部 LLM 真实 `ask` 未执行 | 会把 dev DB 文档切片和 prompt context 发送到第三方 LLM provider，需要用户显式批准 | 暂不新增任务；修 BUG-009 后按需人工批准重跑 |

## 6. AC 收口

| AC | 状态 | 证据 |
|----|------|------|
| AC-1 | ✅ | 见报告对应章节 |
| AC-2 | ❌（prompt 前截停失败） | 见报告第 2 节 |
| AC-3 | ⏳（外部 LLM 未授权运行） | 见报告第 2 节 |
| AC-4 | ✅ | 见报告对应章节 |
| AC-5 | ⏳（含手动或复用 bug007 子项） | 见报告对应章节 |
| AC-6 | ✅（已归因并登记 BUG-009） | 见报告第 5 节 |
| AC-7 | ⏳（由 PR 阶段同步验证） | 见报告对应章节 |
| AC-8 | ⏳（由 PR 阶段门禁验证） | 见报告对应章节 |
