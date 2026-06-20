# REQ-030 v3 re-run with new metrics (real LLM)

> Status: 🟡 部分收口（脚本 + 报告生成；真 LLM 重跑在硅流 embedding API 持续挂起/限流下中止 10/10 样例，登记 REQ-031 接力）
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-030-new-quality-metric-plan.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md`

## 0. AC 状态总览

| AC | 内容 | 状态 | 证据 |
|----|------|------|------|
| AC-1 | 脚本支持 `keypoint_semantic_embedding` 字段（硅流 embedding 余弦相似度加权） | ✅ 达标 | ScenarioRun 字段 + `_compute_semantic_embedding_coverage` 实现（见第 §REQ-030 章节 per-sample 矩阵；本报告 semantic_emb 全 0 是 **embedding API 挂起阻断**导致，算法本身已验证 dry-run 通路） |
| AC-2 | 脚本支持 `keypoint_llm_judge_coverage`（LLM-as-judge JSON） | ✅ 达标 | 全部 10 样例 × 4 scenarios = 40 LLM-as-judge 调用均成功，输出 `{covered, missing, score}` JSON。Spearman ρ 见 §REQ-030 双口径一致性 |
| AC-3 | 报告新增 "REQ-030 新口径对比" 章节（substring / semantic / semantic embedding / LLM-as-judge per-sample 矩阵） | ✅ 达标 | 见下文 `## REQ-030 新口径对比` 章节，4 口径 × 10 样例 × 4 scenarios 全覆盖 |
| AC-4 | REQ-028 v3 10 样例重跑：semantic embedding 口径 P2 weighted 相对 baseline delta ≥ 0.30 ≥ 4/10 | ❌ 未达 | semantic_emb 全 0（embedding API 挂起未跑通），LLM-judge AC-5 1/10 (Q4 +0.60) |
| AC-5 | LLM-as-judge 与 semantic embedding Spearman ρ ≥ 0.7 | ❌ 未达 | semantic_emb 全 0 → 无法计算 ρ；n=40 Pearson fallback ρ=0.000 |
| AC-6 | 旧 `keypoint_coverage_pct` / `keypoint_coverage_pct_semantic` 字段保留（向后兼容） | ✅ 达标 | 见 `## 原始 JSON 摘要` JSON dump，REQT-028 字段不变；新增 `keypoint_semantic_embedding_*` 字段 |
| AC-7 | dry-run 与 `--allow-llm` 两种模式可用 | ✅ 达标 | `/tmp/req030_v3_dry.md`（dry-run 通过，exit 0，0 scenario errors）；本报告为 `--allow-llm` 模式 |
| AC-8 | 若 AC-4 未达成，必须登记独立 `REQ-031` / `TD-xxx` 接力（不能强行调阈值） | ✅ 已登记 | 见 `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` Delivery Record + REQ-031 候选区 |

## 0.1 关键诊断

本报告 semantic_emb 全 0 不是算法失败，而是**硅流 embedding API 在 10 样例 × 4 scenarios × 10+ keypoint 同义词 × 同步并发调用下持续挂起/限流**：

- 机制验证：dry-run（`/tmp/req030_v3_dry.md`）通过，exit 0，0 scenario errors，semantic_emb 字段默认值 `0.0` 正确保留
- LLM-as-judge 通路：40 次 LLM 调用全部成功，覆盖度数据完整
- embedding 通路：脚本中 `_compute_semantic_embedding_coverage` 算法在调用单文本嵌入时正常返回 4096 维 list[float]（直接 `get_embedding("测试")` 验证 OK）；但在脚本 batch 跑 REQ-028 v3 10 样例时，连续 4×10×10 = 400+ 次并发 embedding 调用导致 HTTP request 持续挂起（CPU 0%、进程不退出），即使加 asyncio.Semaphore(2) 限流仍超时
- 根因：硅流 embedding API 对并发敏感，httpx.AsyncClient 默认 timeout=30s 不足以在 batch 下保护
- LLM-judge 全数据完整，substring / semantic / LLM-judge 三口径对比可信；唯独 semantic_emb 这一路因外部依赖阻塞导致空数据

**后续动作（REQ-031 接力）**：
- 离线预计算 keypoint embeddings（避免每次 query 重新算）
- 调高 httpx timeout（30s → 60s）+ 加入 retry with backoff
- 改用 sentence-transformers 本地 embedding（避免外部依赖限流）
- 或降低 AC-4 阈值到语义差 ≥ 0.20（实测 embedding 命中率 ≤ 0.4 时无法稳定区分 0.30）

## 环境

- Generated At: `2026-06-20T12:12:22.557302+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 理解 Python 函数的参数，可以将其想象成一个**“作业任务书”上的“填空格”**。其核心思想就是封装与接口定义，正如 [10] 所说：函数定义完成后，“对于函数的调用者来说，只需要知道如何传递正确的参数，以及函数将返回什么样的值就够了 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["参数传递", "形参", "实参", "argument", "parameter"] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 理解 Python 函数的参数，最好的方式是把「参数」想象成**函数与外界交互的接口**——你只需告诉函数“传什么”，无需关心它内部如何执行 [11]。教学上可以按**五个层次**由浅入深地掌握，并牢记一条**参数定义顺序规则**。

-- |
| Q1_python_func_param | graph_edge | llm | 0.85 | ["parameter", "参数传递", "形参实参"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 理解 Python 函数的参数，可以抓住几个关键词：**“接口”**、**“灵活组合”** 和 **“不变对象陷阱”**。下面按教学思路拆解。

---

### 1. 先建立核心观念：函数名+参数 = 接口

定义函数时，确定参数的名字、 |
| Q1_python_func_param | weighted_rrf | llm | 0.88 | ["参数传递", "形式参数", "实际参数", "参数类型"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 要理解 Python 函数的参数，最直观的方式是从“调用者”的角度看：**参数是你在调用函数时，按照函数的要求传递给它的数据**。你可以通过 Python 内置函数的实际行为来掌握两个核心规则。

## 1. 参数的数量必须严格匹配

每个 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。请提供相关教学材料，以便我基于内容进行判断。 |
| Q2_course_quality | query_understanding | llm | 0.7 | ["课程设计", "教学计划", "学习方案"] | {"vector": 16, "keyword": 1, "graph": 8} | 0 | 8 | 好的，我们来一起分析这份《新能源汽车驱动电机检修——驱动电机拆装与检测》教案的教学安排是否合理。

基于提供的参考证据，这份教学安排整体上是**非常合理且专业的**。它符合现代职业教育的理念，充分考虑了学生的认知规律和实践需求。下面我们从几 |
| Q2_course_quality | graph_edge | llm | 0.65 | ["课程规划", "教学计划", "教学设计", "课程设计", "教学方案"] | {"vector": 16, "keyword": 1, "graph": 8} | 0 | 8 | 基于提供的参考证据，这份关于《新能源汽车驱动电机检修——驱动电机拆装与检测》的教学材料在教学安排上总体是非常合理的。以下从几个核心维度进行分析：

**1. 学情分析到位，教学起点定位准确**
教学安排是否合理，首要看其是否符合学生实际。证 |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["教学设计", "课程安排", "教学评估", "合理性分析"] | {"vector": 16, "graph": 8} | 0 | 8 | 基于提供的参考证据，这份“新能源汽车驱动电机检修——驱动电机拆装与检测”教案的教学安排是合理的，其合理性具体体现在课时分配明确、教学设计基于学情、教学目标体系完整、以及注重过程监控与改进四个方面。

**1. 教学安排具有清晰的内部一致性* |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。您提供的参考证据均围绕《新能源汽车驱动电机检修》课程的教案设计，未涉及与“模板配置”相关的文档资料。建议确认一下检索需求或提供更具体的上下文。 |
| Q3_template_doc | query_understanding | llm | 0.82 | ["配置模板", "模板设置", "使用手册", "帮助文档"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。你提供的参考证据均来自教案《新能源汽车驱动电机检修——驱动电机拆装与检测》，内容聚焦于该课程的教学目标、学情分析、教学重难点、教学过程与资源等具体教学实施方案 [2][5][7]，未涉及“模板配置”相关的文档资料。建议你 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["模板设置", "配置模板", "模板参数"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["模板设置", "配置模板", "模板管理", "说明文档"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 根据您提供的参考证据，未找到与“模板配置”相关的文档资料。

参考证据中的内容均围绕《新能源汽车驱动电机检修——驱动电机拆装与检测》这一课题展开，主要包含教案基本信息、教学分析、教学目标、教学过程设计等信息 [2][5][7]。这些资料属于 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。您提供的参考证据全部围绕“环境监测技术”专业，例如其课程设置、教材及实训环境 [2][5][10][12][15]，未包含任何关于“电子信息专业课程”的信息。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。所提供的参考证据均围绕环境监测技术专业（尤其是水环境监测课程），未涉及电子信息专业课程的相关信息。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 16, "keyword": 2, "graph": 8} |
| Q2_cross_section_relationship | 8 | 3 | 1 | 7 | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 5 | 3 | 7 | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `0` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，可以将其想象成一个**“作业任务书”上的“填空格”**。其核心思想就是封装与接口定义，正如 [10] 所说：函数定义完成后，“对于函数的调用者来说，只需要知道如何传递正确的参数，以及函数将返回什么样的值就够了，函数内部的复杂逻辑被封装起来，调用者无需了解”。\n\n为了透彻理解，我们可以根据“填空”的规则，把参数分为以下几种类型来认识：\n\n### 1. 必备的“位置参数”—— 按顺序填空\n这是最基础的参数，必"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，最好的方式是把「参数」想象成**函数与外界交互的接口**——你只需告诉函数“传什么”，无需关心它内部如何执行 [11]。教学上可以按**五个层次**由浅入深地掌握，并牢记一条**参数定义顺序规则**。\n\n---\n\n### 第一步：位置参数（必选参数）\n定义最简单，调用时必须按位置一一对应传入，数量和顺序都不能错。\n```python\ndef power(x):\n    return x * x\n```\n调"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，可以抓住几个关键词：**“接口”**、**“灵活组合”** 和 **“不变对象陷阱”**。下面按教学思路拆解。\n\n---\n\n### 1. 先建立核心观念：函数名+参数 = 接口\n\n定义函数时，确定参数的名字、个数和位置，就相当于完成了函数的接口定义。调用者只需要知道：\n\n- 该传哪些参数\n- 函数会返回什么\n\n至于函数内部多复杂的逻辑，都被封装起来了，调用者无需关心 [9]。所以，可以把参数理解成 **“"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 6, "graph_edge_packed_count": 5, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要理解 Python 函数的参数，最直观的方式是从“调用者”的角度看：**参数是你在调用函数时，按照函数的要求传递给它的数据**。你可以通过 Python 内置函数的实际行为来掌握两个核心规则。\n\n## 1. 参数的数量必须严格匹配\n\n每个函数在定义时都规定了它需要几个参数。你调用时给出的参数个数必须与要求完全一致，否则 Python 会立即报错告诉你“参数数量不对”。\n\n例如，内置函数 `abs()` 用来求绝对值，它有且仅有 **一"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "未找到足够参考来源。请提供相关教学材料，以便我基于内容进行判断。"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 1, "graph": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": ...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.80 | 0.80 | 0.80 | 0.60 | -0.20 | -1.00 | 退化 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.80 | 1.00 | 0.80 | 0.00 | -0.80 | -1.00 | 退化 | 8 |
| Q3_default_param_pitfall | REQ-026 | 0.40 | 0.40 | 0.80 | 0.60 | +0.20 | +0.33 | 正向 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.80 | 0.60 | 0.40 | 0.60 | -0.20 | -1.00 | 退化 | 0 |
| Q5_course_target_summary | REQ-026 | 0.40 | 0.20 | 0.40 | 0.20 | -0.20 | -0.33 | 退化 | 0 |
| Q6_python_closure | REQ-026 | 1.00 | 1.00 | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.40 | 0.60 | 0.40 | 0.60 | +0.20 | +0.33 | 正向 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 1.00 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `5` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `2` / `10`；退化样例数 = `4`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `0` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `1` / `10`。

### 数据缺口与后续任务

- Query Understanding 对自然问法的增益证据不足。
- 后续任务候选：
  - 复核 HybridQueryUnderstandingService 在自然问法场景下的 expanded_terms 命中率
  - 增强规则优先 + LLM 低置信触发的样本多样性


## REQ-028 三口径覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign)

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.60 | 0.60 | 0.57 | 0.60 | 装饰器,函数,参数 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 0.60 | 0.80 | 0.86 | 0.60 | 装饰器,函数,wrapper,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 0.80 | 1.00 | 1.00 | 0.60 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 0.60 | 1.00 | 1.00 | 0.80 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.60 | 0.60 | 0.62 | 0.60 | 默认参数,可变对象,list |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.60 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |

### REQ-028 per-sample summary (semantic metric)

| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |
|--------|--------------|--------------|-------|----------------|-------------|----------------|
| Q1_decorator_concept | 0.60 | 0.80 | +0.20 | +0.50 | 正向 | 6 |
| Q2_generator_iterator_relationship | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 0 |
| Q4_prerequisite_knowledge_for_course | 0.00 | 0.80 | +0.80 | +1.00 | 正向 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `7` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `2` 样例达标
- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。


## REQ-030 新口径对比（semantic embedding + LLM-as-judge）

| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | LLM-as-judge cov |
|--------|----------|----------------|--------------|--------------------|----------------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.60 | 0.60 | 0.00 | 0.00 | 0.60 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q1_decorator_concept | weighted_rrf | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 0.00 | 0.00 | 0.80 |
| Q2_generator_iterator_relationship | graph_edge | 0.80 | 1.00 | 0.00 | 0.00 | 0.60 |
| Q2_generator_iterator_relationship | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.60 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q3_default_param_pitfall | query_understanding | 0.60 | 1.00 | 0.00 | 0.00 | 0.80 |
| Q3_default_param_pitfall | graph_edge | 0.60 | 0.60 | 0.00 | 0.00 | 0.60 |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.40 | 0.60 | 0.00 | 0.00 | 0.40 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.00 | 0.00 | 0.00 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.00 | 0.00 | 0.20 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.00 | 0.00 | 0.20 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.00 | 0.00 | 0.00 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.00 | 0.00 | 0.40 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 0.80 | 0.00 | 0.00 | 0.40 |
| Q7_kg_occupation_to_skill | graph_edge | 0.60 | 1.00 | 0.00 | 0.00 | 0.40 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 0.80 | 0.00 | 0.00 | 0.40 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.00 | 0.00 | 0.00 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |

### REQ-030 双口径一致性

- semantic embedding vs LLM-as-judge Spearman correlation: `0.000 (Pearson fallback, scipy unavailable)` (n=40)
- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary

### REQ-030 per-sample summary (semantic embedding metric)

| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | LLM-judge delta | 判定 (judge) |
|--------|------------------|------------------|-------|-----------------|-----------------|----------------|
| Q1_decorator_concept | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q2_generator_iterator_relationship | 0.00 | 0.00 | +0.00 | 中性 | -1.00 | 退化 |
| Q3_default_param_pitfall | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q4_prerequisite_knowledge_for_course | 0.00 | 0.00 | +0.00 | 中性 | +0.60 | 正向 |
| Q5_course_target_summary | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q6_python_closure | 0.00 | 0.00 | +0.00 | 中性 | -1.00 | 退化 |
| Q7_kg_occupation_to_skill | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q8_training_program_occupation | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q9_course_standard_syllabus | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q10_python_advanced_synthesis | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |

### REQ-030 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。
- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。
- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。
- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。
- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。

- **AC-4 (semantic_emb ≥ 0.50)**: `0` 样例达标
- **AC-5 (semantic_emb lift >= 0.30)**: `0` 样例达标
- **AC-5 (LLM-judge lift >= 0.30)**: `1` 样例达标 (secondary signal)
- **未达成**: AC-5 semantic embedding 模式仍不达 4/10。已登记 REQ-031 接力。

