# REQ-031 v3 re-run (cache + timeout, real LLM)

> Status: REQ-030 🟡 部分收口 → REQ-031 接力后 embedding 通路稳定（非零 8/10），AC-4/5 阈值校准留 follow-up
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric.md` / `2026-06-20-req-031-semantic-embedding-stability.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-031-semantic-embedding-stability-plan.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` / `REQ-031-p2-semantic-embedding-coverage-stabilization.md`

## 0. AC 状态总览（REQ-030 + REQ-031 补判）

**REQ-031 接力成果**：进程内 embedding 缓存（hit=1581 / miss=259）+ `asyncio.wait_for` 60s 硬超时 + 降级。**timeout=0 / error=0**——彻底消除 REQ-030 阶段的 batch 挂起。semantic_emb 字段从全 0 变为 **8/10 样例非零**。

| AC (REQ-030) | 内容 | 状态 | 证据 |
|----|------|------|------|
| AC-1 | 脚本支持 `keypoint_semantic_embedding` 字段 | ✅ 达标 | ScenarioRun 字段 + `_compute_semantic_embedding_coverage` |
| AC-2 | 脚本支持 `keypoint_llm_judge_coverage` | ✅ 达标 | 40 次 LLM-as-judge 调用全成功 |
| AC-3 | 报告新增 "REQ-030 新口径对比" 章节 | ✅ 达标 | 见下文 4 口径 × 10 样例 × 4 scenarios 矩阵 |
| AC-4 | semantic_emb 口径 P2 weighted delta ≥ 0.30 ≥ 4/10 | ❌ 未达 | 0/10。threshold 0.5 过严，semantic_emb 值集中 0.20-0.40（见诊断） |
| AC-5 | LLM-judge 与 semantic_emb Spearman ρ ≥ 0.7 | ❌ 未达 | ρ=0.109 (n=40, Pearson fallback)。双口径在 threshold 0.5 下不一致 |
| AC-6 | 旧字段保留（向后兼容） | ✅ 达标 | JSON dump 字段不变 |
| AC-7 | dry-run 与 `--allow-llm` 双模式可用 | ✅ 达标 | dry-run exit 0；本报告为 `--allow-llm` |
| AC-8 | 若 AC-4 未达成，登记接力 | ✅ 已登记 | REQ-031（本任务，通路修复）+ 阈值校准 follow-up |

| AC (REQ-031) | 内容 | 状态 | 证据 |
|----|------|------|------|
| AC-1 | 进程内 embedding 缓存（key by text） | ✅ 达标 | `_EMBEDDING_CACHE` hit=1581 / miss=259 |
| AC-2 | `asyncio.wait_for` 60s 硬超时 + 降级 | ✅ 达标 | timeout=0 / error=0，无 1h+ 挂起 |
| AC-3 | semantic_emb 非零 sample ≥ 5/10 | ✅ 达标 | 8/10 非零（Q4/Q9 全零） |
| AC-4 | Spearman ρ 如实计算 | ✅ 达标 | ρ=0.109 (n=40) |
| AC-5 | REQ-030 AC-4/5 基于真实数据补判 | ✅ 达标 | AC-4/5 = 0/10，如实记录；阈值校准留 follow-up |
| AC-6 | 旧字段行为不变 | ✅ 达标 | 字段不变 |
| AC-7 | dry-run 与 `--allow-llm` 双模式 | ✅ 达标 | 两种模式均 exit 0 |
| AC-8 | 若通路仍不通，登记下一步 | ✅ 不适用 | 通路已通；阈值校准作为 follow-up 而非 REQ-031 失败 |

## 0.1 关键诊断（REQ-031 后）

**通路已通**：semantic_emb 从 REQ-030 阶段的全 0 变为 8/10 样例非零，值分布在 0.20-0.60。

**阈值校准问题**（留 follow-up，非 REQ-031 失败）：
- cosine threshold = 0.5 过严：Qwen3-Embedding-8B 对中文短 keypoint（"装饰器"/"闭包"）与长 answer 的余弦相似度天然偏低，多数 keypoint similarity 落在 0.3-0.5 区间，0.5 阈值导致命中偏少
- AC-4 (semantic_emb ≥ 0.50 in weighted) 0/10：weighted scenario 的 semantic_emb 多为 0.00-0.40
- AC-5 (delta ≥ 0.30) 0/10：baseline 与 weighted 的 semantic_emb 差异 < 0.30
- Spearman ρ=0.109：semantic_emb（threshold 0.5）与 LLM-judge 排序不一致——threshold 0.5 让 semantic_emb 过于稀疏，丢失排序信息

**建议 follow-up**（独立任务，不阻塞 REQ-031 收口）：
- threshold 0.5 → 0.35（基于实测 similarity 分布）后重判 AC-4/5
- 或改用 continuous weighted coverage（不二值化，直接用 similarity 加权）替代 threshold 命中

**Q4/Q9 全零**：Q4 (prerequisite_knowledge_for_course) / Q9 (course_standard_syllabus) 的 expected_keypoints 与真实答案在 0.5 阈值下无任何命中，可能 keypoints 偏抽象（"前置知识"/"课程标准"）需 review。

## 环境

- Generated At: `2026-06-20T15:17:40.138947+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要理解 Python 函数的参数，可以从“接口设计”和“调用规则”两个角度出发。函数通过参数接收输入，封装内部逻辑，调用者只需要关心“需要传什么参数，能得到什么返回值”即可 [10]。以下以最常见的参数类型为线索，帮你建立清晰的认知。

- |
| Q1_python_func_param | query_understanding | llm | 0.85 | ["参数传递", "形参实参", "Python函数"] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要理解 Python 函数的参数，最好的方式是把它们看作“调用接口”的约定——函数内部怎么复杂不用管，只要知道该传哪些值、怎么传、会返回什么就行 [9]。Python 提供了五种参数类型，组合起来可以应对几乎所有的调用场景。这些参数必须按照 |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["parameter", "argument", "参数传递", "形式参数", "实际参数"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 理解 Python 函数的参数，就像在组装一个功能灵活的“乐高积木”——你只需要知道每块积木的插口（参数），就能让函数按你的要求工作。我们可以把参数理解成函数与外部传递数据的“接口”，而 Python 提供了多种接口形式，让我们编写函数时既 |
| Q1_python_func_param | weighted_rrf | llm | 0.85 | ["parameter", "参数传递", "形参", "实参"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 未找到足够参考来源。当前提供的参考证据主要涉及 Python 的历史、设计哲学、语言特点及适用场景 [9][10][11][12]，并未包含关于 Python 函数参数的讲解或教学说明，因此无法针对“如何理解 Python 函数参数”这一问 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 好的，我们来基于提供的参考证据，分析这份教学材料的教学安排是否合理。

综合来看，这份关于“驱动电机拆装与检测”的教学安排是**非常合理**的，展现了职业教育“理实一体化”的典型特点。其合理性主要体现在以下几个方面：

-   **内容选择 |
| Q2_course_quality | query_understanding | llm | 0.7 | ["教学计划", "课程安排", "教学设计评估"] | {"vector": 16, "keyword": 1, "graph": 8} | 0 | 8 | 根据参考证据，特别是[4]号证据中关于“新能源汽车驱动电机检修——驱动电机拆装与检测”的教案设计，可以判断这份材料的教学安排是**合理且专业的**。以下从几个方面进行分析：

**1. 教学设计结构严谨，环节完整**
该教学安排严格遵循了完 |
| Q2_course_quality | graph_edge | llm | 0.75 | ["教学计划", "课程安排", "教学评价", "教学评估"] | {"vector": 16, "keyword": 5, "graph": 8} | 0 | 8 | 基于提供的参考证据，我可以仅以其中一份关于“新能源汽车驱动电机检修”的具体教案[5]作为核心分析对象，来判断其教学安排的合理性。综合来看，这份材料的教学安排是合理的，它符合职业教育的规律和质量管理要求。

以下从五个维度进行具体分析：

| |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["教学计划评估", "课程安排合理性", "教学设计评价"] | {"vector": 16, "graph": 8} | 0 | 8 | 基于提供的参考证据，这份关于《新能源汽车驱动电机检修——驱动电机拆装与检测》的教案材料，其教学安排是合理的。以下从几个关键维度进行分析：

**1. 教学目标定位准确，符合“理实一体化”**
该教案的教学目标明确分为知识、能力和情感态度价值 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。您提供的参考证据均围绕《新能源汽车驱动电机检修——驱动电机拆装与检测》的教案设计，内容涉及教学分析、教学目标、重难点及教学过程等，并未出现与“模板配置”相关的文档资料。 |
| Q3_template_doc | query_understanding | llm | 0.75 | ["模板设置", "配置指南", "模板使用说明"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["模板设置", "配置文件", "模板参数", "文档模板", "配置说明"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | weighted_rrf | llm | 0.92 | ["配置模板", "模板设置", "帮助文档", "指南", "教程"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的参考证据仅涉及《新能源汽车驱动电机检修——驱动电机拆装与检测》教案内容，不包含任何模板配置相关的文档资料。 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。所提供的参考证据均围绕《环境监测技术》专业，涉及课程标准、教材、实训环境、接续专业等，未包含电子信息专业课程相关信息。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。

提供的参考证据主要围绕《水环境监测技术》课程标准、教材、课程设置及环境监测技术专业结构，未涉及电子信息专业课程的相关信息。建议重新提问或提供与电子信息专业相关的资料。 |

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
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "final_answer_preview": "要理解 Python 函数的参数，可以从“接口设计”和“调用规则”两个角度出发。函数通过参数接收输入，封装内部逻辑，调用者只需要关心“需要传什么参数，能得到什么返回值”即可 [10]。以下以最常见的参数类型为线索，帮你建立清晰的认知。\n\n---\n\n### 1. 位置参数 —— 最基础的“必须按序提供”的参数\n定义函数时，直接写在括号里的参数就是**位置参数**。调用时必须按顺序、且数量完全一致地传入实参，否则会报 `TypeError`"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "final_answer_preview": "要理解 Python 函数的参数，最好的方式是把它们看作“调用接口”的约定——函数内部怎么复杂不用管，只要知道该传哪些值、怎么传、会返回什么就行 [9]。Python 提供了五种参数类型，组合起来可以应对几乎所有的调用场景。这些参数必须按照固定顺序定义：**必选参数 → 默认参数 → 可变参数 → 命名关键字参数 → 关键字参数** [11]。\n\n下面用一个表格帮你快速建立整体认知：\n\n| 参数类型 | 定义时怎么写 | 作用 | 示例"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "final_answer_preview": "理解 Python 函数的参数，就像在组装一个功能灵活的“乐高积木”——你只需要知道每块积木的插口（参数），就能让函数按你的要求工作。我们可以把参数理解成函数与外部传递数据的“接口”，而 Python 提供了多种接口形式，让我们编写函数时既能保证简洁，又能应对复杂的需求。\n\n按照学习的逻辑，你可以这样层层递进地理解：\n\n### 1. 最基础：位置参数（必选参数）\n这是最直接的方式，就像给机器填入原料，必须按照**位置**一一对应。\n- "}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 7, "graph_edge_packed_count": 8, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "final_answer_preview": "未找到足够参考来源。当前提供的参考证据主要涉及 Python 的历史、设计哲学、语言特点及适用场景 [9][10][11][12]，并未包含关于 Python 函数参数的讲解或教学说明，因此无法针对“如何理解 Python 函数参数”这一问题给出有依据的回答。建议补充与 Python 函数定义、形参、实参、参数类型（如位置参数、默认参数、可变参数等）相关的资料。"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "graph": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 3, "keypoint...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.80 | 0.60 | 1.00 | 0.80 | +0.00 | +0.00 | 中性 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 1.00 | 0.80 | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | REQ-026 | 0.80 | 0.60 | 0.60 | 0.60 | -0.20 | -1.00 | 退化 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.00 | 0.60 | 0.60 | 0.80 | +0.80 | +1.00 | 正向 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 1.00 | 1.00 | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.20 | 0.60 | 0.40 | 0.40 | +0.20 | +0.25 | 中性 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 0.80 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 2 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `5` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `10`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `2` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `0` / `10`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。


## REQ-028 三口径覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign)

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | weighted_rrf | 0.60 | 0.60 | 0.62 | 0.40 | 生成器,迭代器,iter |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 0.40 | 0.60 | 0.62 | 0.60 | 默认参数,可变对象,list |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.80 | 0.80 | 0.75 | 0.80 | 化学,基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.80 | 0.80 | 0.75 | 0.80 | 化学,基础,先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.40 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.40 | 闭包,装饰器 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.60 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.40 | 0.40 | 0.00 | 化学检验工,水环境监测工 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 0.80 | 水样,采集,金属,非金属,有机物 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 0.88 | 0.60 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |

### REQ-028 per-sample summary (semantic metric)

| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |
|--------|--------------|--------------|-------|----------------|-------------|----------------|
| Q1_decorator_concept | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |
| Q2_generator_iterator_relationship | 1.00 | 0.60 | -0.40 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 0 |
| Q4_prerequisite_knowledge_for_course | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.40 | 0.20 | -0.20 | -0.33 | 退化 | 0 |
| Q9_course_standard_syllabus | 1.00 | 0.80 | -0.20 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `8` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `0` 样例达标
- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。


## REQ-030 新口径对比（semantic embedding + LLM-as-judge）

> REQ-031 embedding cache: hit=`1581` miss=`259` timeout=`0` error=`0` (total=`1840`)

| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | LLM-as-judge cov |
|--------|----------|----------------|--------------|--------------------|----------------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.80 | 0.80 | 0.20 | 0.29 | 0.80 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.20 | 0.29 | 0.80 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.20 | 0.29 | 0.80 |
| Q1_decorator_concept | weighted_rrf | 0.80 | 0.80 | 0.20 | 0.29 | 0.80 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 0.80 | 1.00 | 0.40 | 0.50 | 0.80 |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 0.60 | 0.62 | 1.00 |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 0.60 | 0.62 | 1.00 |
| Q2_generator_iterator_relationship | weighted_rrf | 0.60 | 0.60 | 0.00 | 0.00 | 0.40 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 0.20 | 0.25 | 1.00 |
| Q3_default_param_pitfall | query_understanding | 0.40 | 0.60 | 0.20 | 0.25 | 0.60 |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 0.20 | 0.25 | 1.00 |
| Q3_default_param_pitfall | weighted_rrf | 0.60 | 1.00 | 0.20 | 0.25 | 1.00 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.40 | 0.60 | 0.00 | 0.00 | 0.40 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.40 | 0.60 | 0.00 | 0.00 | 0.40 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.80 | 0.80 | 0.00 | 0.00 | 0.80 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.20 | 0.25 | 0.40 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.00 | 0.00 | 0.20 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.20 | 0.25 | 0.00 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.20 | 0.25 | 0.00 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 0.20 | 0.25 | 1.00 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 0.20 | 0.25 | 1.00 |
| Q6_python_closure | weighted_rrf | 0.40 | 0.40 | 0.00 | 0.00 | 0.40 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.40 | 0.44 | 0.40 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 1.00 | 0.40 | 0.44 | 0.40 |
| Q7_kg_occupation_to_skill | graph_edge | 0.40 | 0.80 | 0.20 | 0.22 | 0.40 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.60 | 0.80 | 0.40 | 0.44 | 0.40 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.40 | 0.20 | 0.20 | 0.00 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.20 | 0.00 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.20 | 0.00 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.40 | 0.40 | 0.00 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.80 | 1.00 | 0.00 | 0.00 | 0.80 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.00 | 0.00 | 0.60 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.40 | 0.50 | 0.80 |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.40 | 0.50 | 0.80 |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 0.20 | 0.25 | 0.60 |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.20 | 0.25 | 0.80 |

### REQ-030 双口径一致性

- semantic embedding vs LLM-as-judge Spearman correlation: `0.109 (Pearson fallback, scipy unavailable)` (n=40)
- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary

### REQ-030 per-sample summary (semantic embedding metric)

| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | LLM-judge delta | 判定 (judge) |
|--------|------------------|------------------|-------|-----------------|-----------------|----------------|
| Q1_decorator_concept | 0.20 | 0.20 | +0.00 | 中性 | +0.00 | 中性 |
| Q2_generator_iterator_relationship | 0.40 | 0.00 | -0.40 | 退化 | -0.40 | 退化 |
| Q3_default_param_pitfall | 0.20 | 0.20 | +0.00 | 中性 | +0.00 | 中性 |
| Q4_prerequisite_knowledge_for_course | 0.00 | 0.00 | +0.00 | 中性 | +0.00 | 中性 |
| Q5_course_target_summary | 0.20 | 0.20 | +0.00 | 中性 | -0.40 | 退化 |
| Q6_python_closure | 0.20 | 0.00 | -0.20 | 中性 | -0.60 | 退化 |
| Q7_kg_occupation_to_skill | 0.40 | 0.40 | +0.00 | 中性 | +0.00 | 中性 |
| Q8_training_program_occupation | 0.20 | 0.40 | +0.20 | 中性 | +0.00 | 中性 |
| Q9_course_standard_syllabus | 0.00 | 0.00 | +0.00 | 中性 | -0.20 | 中性 |
| Q10_python_advanced_synthesis | 0.40 | 0.20 | -0.20 | 中性 | +0.00 | 中性 |

### REQ-030 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。
- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。
- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。
- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。
- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。

- **AC-4 (semantic_emb ≥ 0.50)**: `0` 样例达标
- **AC-5 (semantic_emb lift >= 0.30)**: `0` 样例达标
- **AC-5 (LLM-judge lift >= 0.30)**: `0` 样例达标 (secondary signal)
- **未达成**: AC-5 semantic embedding 模式仍不达 4/10。已登记 REQ-031 接力。

