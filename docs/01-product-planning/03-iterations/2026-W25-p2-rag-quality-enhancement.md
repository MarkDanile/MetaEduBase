# Iteration 2026-W25: P2 RAG 质量增强

Status: 🟡 Planned
Dates: 2026-W25
Goal: 在 REQ-012 多路 evidence 骨架之上，补齐召回后上下文组装、排序演进和真实问答 grounding，优先解决“资料库有正文但回答证据不足”的问题。

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|
| REQ-013 | REQ | 🟢 Done | RAG Context Packer 与回答 grounding 增强 | PR #305 已合并；命中 chunk 后按相邻 chunk / 同 section 组装 prompt。真实 PG 样例与最终 grounding 验收转入 REQ-014。 |
| BUG-007 | BUG | 🔵 Ready | pdf_parser sections path 错乱 | 修复 section path 计算，降低后续 section expansion 依赖坏 metadata 的风险。 |
| REQ-014 | REQ | 🟡 Doing | RAG 真实 PG 样例、数据回填与回答 grounding 验收 | spec + plan + 一次性验收脚本 `scripts/validate_real_pg_rag.py` 已就位；下个会话跑真 PG 5 子命令生成报告；不修 BUG-006/007 实现 |

## Out of Scope

- 不在本迭代引入 Elasticsearch、Milvus、Neo4j 或完整 GraphRAG 框架。
- 不把 P2 所有 RAG 能力一次性做完；每次只推进有明确样例和验收的切片。
- 不把里程碑 open item 直接当开发任务；必须映射到 REQ / BUG / TD / DOC 后再进入工作台。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| REQ-012 后仍出现“只拿目录证据”的回答 | 当前缺口集中在 fusion 后的上下文包装，不是单纯增加召回通道 | REQ-013 |
| section metadata 近期仍有 path 错乱问题 | Context Packer 首版必须有 chunk_index fallback，不能强依赖 section_path | BUG-007 / REQ-013 |
| REQ-013 / BUG-007 合并后仍缺真实 PG 样例 backfill | 当前需要把机制测试推进到真实样例和最终回答验收 | REQ-014 |
| P2 已有 PostgreSQL tsvector 基础 | 当前先用既有 PostgreSQL 能力提升质量，不急于换 ES / Milvus / Neo4j | P2-SEARCH / REQ-013；P2-RRF 仍留在里程碑 Open Items，待真实瓶颈明确后再映射稳定任务编号 |
