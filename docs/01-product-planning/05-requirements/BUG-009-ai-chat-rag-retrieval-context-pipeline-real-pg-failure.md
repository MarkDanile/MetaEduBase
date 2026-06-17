# BUG-009: AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt

Status: 🟢 Done
Priority: P0
Milestone: P2
Source: REQ-015 真实 dev DB 验收
Related: REQ-012 / REQ-013 / REQ-014 / REQ-015 / BUG-003 / P2-SEARCH / P2-RRF

## Delivery Record

| Date | What | Details |
|------|------|---------|
| 2026-06-17 | Retrieval pipeline fix + prompt-before-LLM validation | 修复共享 `AsyncSession` 并发召回、RRF rank 分数被旧绝对阈值清空、keyword / vector fallback 只在 tsvector 为空时才补 lexical 候选、邻居目录块未识别等问题。真实 dev DB 截停验收：`fusion_topN[1]` 为 chunk 54 `数据类型和变量`，packed context 含“能够直接处理的数据类型有以下几种”、浮点数与布尔值；`PROMPT_HAS_BASIC_TYPES=True`。LLM provider resolver 当前选 `deepseek / deepseek-v4-pro`，无业务内容 `OK` 连通性测试通过。 |
| 2026-06-17 | Full external ask validation authorized by user | 用户明确授权将本次 dev DB 检索切片和 prompt context 发送给 `DeepSeek / deepseek-v4-pro` 做 BUG-009 真实 ask 验收。临时启动当前分支后端 `127.0.0.1:8012`，登录 + `POST /api/v1/ai/chat/evidence` 均返回 HTTP 200。回答不再出现“未找到足够参考来源”，包含整数 `int`、浮点数 `float`、字符串 `str`、布尔值 `bool`、空值 `None`，并带 `[1]` / `[2]` 引用；`sources=11`，`document_sources[0]` 为 `Python教程-廖雪峰-2025-06-16.pdf`。 |
| 2026-06-17 | PR merged | [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) 已 squash merge，merge commit `4d78667`。 |

## Problem

REQ-015 已把 `ContextPacker`、`RRFFusion` 和 diagnostics 接入生产 AI Chat 默认路径，但真实 dev DB 截停验收发现：资料库中存在可回答“python 的基本数据类型有哪些？”的正文 chunk，生产编排在进入 LLM 前仍没有把这些 chunk 放入 prompt。

这会导致页面继续回答“未找到足够参考来源”，即使文档原文已经入库、chunk / embedding / tsvector / section metadata 都存在。

## Evidence

真实 dev DB 样例：

- Python 教程文件：`358bd704-d223-4228-8935-3a6e1b3e699f`
- 状态：`processed`
- chunk：875 / embedding：875 / tsvector：875 / section_title：875 / section_path：875 / char offsets：875
- KG：31 nodes，其中 30 个已有 `source_chunk_id`

数据库中可回答问题的正文 chunk 已存在：

- chunk 54：`数据类型和变量`，包含“在Python中，能够直接处理的数据类型有以下几种：整数...”
- chunk 55：包含“浮点数...字符串...”
- chunk 61：包含“布尔值...True / False...”
- chunk 64：包含“列表、字典等多种数据类型...”

REQ-015 不外发 LLM 的 prompt 前截停验收结论：

- `CompositeChunkRetriever` 并发使用同一个 SQLAlchemy `AsyncSession`，真实 DB 下报 `concurrent operations are not permitted`，chunk retriever 失败。
- RRF 默认分数约 `0.03`，但 `AIChatService.min_evidence_score` 仍为 `0.3`，导致 fused evidence 被全部过滤。
- 顺序检索对照中，keyword fallback 可返回结果，但排序优先命中目录 / 简介 chunk；chunk 54 / 55 / 61 未进入 top 8。
- `ContextPacker` 只能围绕错误命中扩展，最终 `PROMPT_HAS_BASIC_TYPES=False`。

REQ-015 初次验收阶段未执行外部 LLM 调用：真实调用会把 dev DB 文档切片和 prompt context 发送到外部 LLM provider，需要用户显式批准后单独跑；修复后完整 ask 已在用户明确授权下通过。

修复后复测结论：

- 生产编排同款 service + 真实 dev DB + fake LLM 截停：不再出现共享 `AsyncSession` 并发查询错误。
- `RRFFusion` 默认路径保留 rank 分数 evidence，不再被 `min_evidence_score=0.3` 清空。
- keyword / vector fallback 采用 tsvector + lexical supplement 合并排序；“Python 的 基本数据类型有哪些？”top1 命中 chunk 54 `数据类型和变量`。
- packed context / prompt preview 包含“在Python中，能够直接处理的数据类型有以下几种”、浮点数、布尔值等正文证据。
- `document_sources` 按文档聚合，来源包含 `Python教程-廖雪峰-2025-06-16.pdf`。
- LLM provider 连通性用无业务内容 `OK` 测通；完整外部 `ask` 经用户明确授权后已跑通。

## Scope

- 修复生产 AI Chat 召回编排，不允许多个 coroutine 共享同一个 `AsyncSession` 并发查询。
- 让 RRF 默认路径不被旧的绝对分数阈值 `0.3` 清空；可选择跳过绝对阈值、改为 rank/topK 阈值，或为 RRF 定义独立归一化阈值。
- 调整 keyword / fallback 排序：
  - 正文 chunk、标题精确命中、section 命中升权。
  - 目录 / 简介 chunk 降权。
  - ILIKE fallback 不得只按 `chunk_index` 排序。
- 保证“python 的基本数据类型有哪些？”最终 packed context 包含数据类型正文 chunk，而不是只包含目录、简介或无内容知识节点。
- 保持 graph evidence 最终落回 chunk / section；无正文来源的 graph evidence 不得压过 chunk 正文证据。
- 补真实回归或可复现脚本断言，不只测 response shape。

## Non-Goals

- 不引入 Elasticsearch、Milvus、Neo4j 或完整 GraphRAG。
- 不在本任务重做 chunker、PDF parser 或数据重建；现有样例数据已足够复现问题。
- 不要求本任务一定跑外部 LLM；必须先证明 prompt 前 context 已正确。

## Acceptance

- AC-1：真实 dev DB 下调用生产编排或等价集成路径，不再出现同一 `AsyncSession` 并发查询错误。
- AC-2：RRF 默认路径至少保留有效 fused evidence；不会因 `min_evidence_score=0.3` 把 RRF 结果清空。
- AC-3：“python 的基本数据类型有哪些？”的 retrieval / fusion topN 包含 `数据类型和变量` 正文 chunk。
- AC-4：packed context / prompt preview 包含整数、浮点数、字符串、布尔值等正文证据。
- AC-5：目录 / 简介 chunk 不作为主证据排在正文 chunk 前面；如保留目录，只能作为低优先级辅助证据。
- AC-6：`document_sources` 仍按文档聚合，且来源文档包含 Python 教程。
- AC-7：新增或更新真实样例验收记录；若不跑外部 LLM，必须明确标注“截停在 prompt 前”。

## Validation

- 真实 dev DB + 后端服务 + dev JWT。
- 不外发 LLM 的 prompt 前截停验收：记录 query、各通道 topN、RRF topN、packed blocks、prompt preview。
- 无业务内容 LLM provider 连通性测试：`deepseek / deepseek-v4-pro` 返回 `OK`。
- 完整外部 `ask`：用户明确授权后已运行；HTTP 200，回答包含基本数据类型列表、引用和文档来源，不再兜底为“未找到足够参考来源”。
- 相关后端 pytest。
- `scripts/check-engineering-docs`
- `git diff --check`

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Current Work: `docs/03-engineering-governance/current-work.md`
- REQ-015 validation report: `docs/02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-validation-report.md`
