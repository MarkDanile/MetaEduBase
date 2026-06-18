# REQ-016 P2 LLM 混合 NER / Query Understanding — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md`

## Scope

本 plan 实现 REQ-016 LLM 混合 NER / Query Understanding，建立在 `RuleBasedNER` 和 `BUG-010` deterministic normalizer 基础之上。`HybridQueryUnderstandingService` 满足 `NERPipeline` Protocol，`AIChatService` 注入新 service 并在 diagnostics 中透出 query understanding trace。

## Slice 1 — Schema + Hybrid Service 骨架 + 触发策略 + Mock Tests

**目标：** `QueryUnderstandingResult` schema 稳定，`HybridQueryUnderstandingService` 骨架完成，触发策略实现，mock 测试覆盖所有 AC。

**文件：**

- `packages/server-python/app/contexts/knowledge/application/query_understanding.py`（新建）
  - `QueryUnderstandingResult(BaseModel)`：method / confidence / normalized_query / core_terms / expanded_terms / entities / filters / raw_llm_output / llm_model
  - `HybridQueryUnderstandingResult(BaseModel)`：ner / query_understanding / trigger_reason
  - `QUERY_UNDERSTANDING_PROMPT` system prompt 模板

- `packages/server-python/app/contexts/knowledge/application/hybrid_ner_service.py`（新建）
  - `HybridQueryUnderstandingService`：
    - `__init__` 接受 LLM provider（可注入，默认用 `ai_router._call_llm`）
    - `extract(query: str) -> HybridQueryUnderstandingResult`：
      1. 调用 `self._rule_ner.extract(query)` → `NERResult`
      2. 判断是否触发 LLM（见触发策略）
      3. 若触发，调用 `_call_llm` → 解析 JSON → 填充 `QueryUnderstandingResult`
      4. 返回 `HybridQueryUnderstandingResult`
    - 触发策略实现：
      - `NERResult` 非空 → method="rule"，不触发 LLM
      - `NERResult` 空 + query len > 15 → 触发 LLM
      - `NERResult` 空 + query len ≤ 15 → method="rule"，confidence=0.0
      - LLM 异常 → 降级 method="rule"，记录 error

- `packages/server-python/tests/contexts/ai/test_hybrid_ner_service.py`（新建）
  - `test_extract_rule_hit_does_not_call_llm`：规则命中 query 不触发 LLM
  - `test_extract_rule_miss_short_query_no_llm`：短 query 不触发 LLM
  - `test_extract_llm_called_on_rule_miss_long_query`：规则未命中长 query 触发 LLM
  - `test_extract_llm_failure_falls_back_to_rule`：LLM 失败降级
  - `test_extract_result_fields_populated`：输出字段完整性
  - `test_hybrid_service_satisfies_ner_pipeline_protocol`：满足 `NERPipeline` Protocol
  - `test_query_understanding_result_model_validation`：Pydantic validation

**验收：**
- `pytest tests/contexts/ai/test_hybrid_ner_service.py -v` 全部通过
- `ruff check app/contexts/knowledge/ --fix`
- `git diff --check`

## Slice 2 — 接入 AIChatService + Diagnostics 扩展

**目标：** `AIChatService` 注入 `HybridQueryUnderstandingService`，diagnostics 包含 query_understanding，真实 LLM 在 dev DB 验证。

**文件：**

- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
  - `AIChatService.__init__` 新增参数 `use_hybrid_ner: bool = True`（向后兼容）
  - 条件注入 `HybridQueryUnderstandingService` 或保留原有 `RuleBasedNER`
  - `chat()` 方法：使用 `HybridQueryUnderstandingResult` 填充 `diagnostics.query_understanding`
  - retrievers 仍使用 `HybridQueryUnderstandingResult.ner`（`NERResult`）—— 接口不变

- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
  - `_build_evidence_service()` 注入 `HybridQueryUnderstandingService`（当 `use_hybrid_ner=True`）

- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
  - `AIChatDiagnostics` 新增可选字段 `query_understanding: dict | None = None`

- `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py`
  - 新增测试：`test_chat_uses_hybrid_ner_when_enabled` / `test_diagnostics_contains_query_understanding`

**验收：**
- `pytest tests/contexts/knowledge/test_ai_chat_service.py -q` 全部通过
- dev DB 真实 query 验证：触发 LLM 的 query diagnostics 含完整 `query_understanding` 字段
- `ruff check app/contexts/knowledge/ --fix`

## Slice 3 — expanded_terms 流经 Retrievers

**目标：** `expanded_terms` 从 `HybridQueryUnderstandingResult` 流入 retrievers，增强召回。

**注意：** 需先确认现有 retrievers（`PgChunkVectorRetriever` / `PgChunkKeywordRetriever`）是否已支持 `NERResult` 携带的 terms 扩展。

**建议动作：**
- 检查 `PgChunkVectorRetriever.retrieve()` 和 `PgChunkKeywordRetriever.retrieve()` 是否使用 `ner_result.domains` / `ner_result.levels` 之外的 terms 字段
- 若 retrievers 已支持 `ner_result` 中的 `raw_entities` 作为扩展词，则本 slice 主要工作为：确保 `HybridQueryUnderstandingResult.ner.raw_entities` 包含 `expanded_terms`（拼接规则 entities + LLM entities）
- 若 retrievers 不支持，新增 `ner_result.expanded_terms` 字段（需修改 `NERResult` 或新建 `RetrievalTerms` dataclass）并更新 retrievers

**文件（若有修改）：**
- `packages/server-python/app/shared/domain/ner_pipeline.py` 或 retrievers 接口

**验收：**
- 用"函数参数"类 query（`expanded_terms` 包含 `parameter` / `参数传递`）验证 retrievers 召回结果包含相关 chunk

## Slice 4 — 真实 PG 样例回归 + 验证报告

**目标：** 3 类真实问法（Python 教程 / 课程能力 / 资源库）有可复现实验记录。

**建议动作：**
- 在 `scripts/validate_real_pg_rag.py` 或独立验收脚本中增加 3 个 query 的 query understanding trace 输出
- 3 个 query 分类：
  1. Python 教程类（"Python 函数的参数要怎么理解最好"）
  2. 课程能力类（"这门课的教学做得好不好？"）
  3. 资源库类（"查找模板配置相关的文档"）
- 验收报告填充到 `docs/02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner-report.md`

**文件：**
- `docs/02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner-report.md`（新建，placeholder）

**验收：**
- 3 个 query 均有完整 `query_understanding` trace 输出
- 回归测试或脚本可复现

## Files To Inspect First

- `packages/server-python/app/contexts/knowledge/application/ner_service.py`
- `packages/server-python/app/shared/domain/ner_pipeline.py`
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_keyword_retriever.py`
- `packages/server-python/tests/contexts/ai/test_rule_based_ner.py`
- `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py`

## Required Checks

- `cd packages/server-python && pytest tests/contexts/ai/test_hybrid_ner_service.py tests/contexts/knowledge/test_ai_chat_service.py -q`
- `ruff check app/contexts/knowledge/`
- `scripts/check-engineering-docs`
- `git diff --check`

## Documentation Closure

完成后必须同步：
- `docs/01-product-planning/04-backlog.md`：REQ-016 状态 🟡 Planned
- `docs/01-product-planning/05-requirements/REQ-016-...`：Delivery Record
- `docs/01-product-planning/02-milestones/02-growth-phase.md`：P2 open item 状态
- `docs/03-engineering-governance/current-work.md`：任务卡片
- `docs/03-engineering-governance/work-log.md`：一行式索引
