# REQ-029 P2 RAG 弱召回样例 v3 residual 阈值模式报告 (real LLM)

## 环境

- Generated At: `2026-06-18T22:45:49.882001+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要理解 Python 函数的参数，可以从三个维度入手：**参数的形式、参数的传递机制、以及默认参数的特殊规则**。参考证据正好揭示了其中最容易被忽视的“坑”，学透这一点就能建立起正确的参数心智模型。

---

### 1. 分清参数的种类 |
| Q1_python_func_param | query_understanding | llm | 0.85 | ["parameter", "参数传递", "形式参数", "实际参数"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要理解 Python 函数的参数，尤其是初学者最容易困惑的默认参数，关键在于建立**“变量指向对象”**的思维。最好的切入点，就是吃透默认参数的一个经典“陷阱”。

我们可以从以下几点层层递进，帮你建立清晰的理解：

### 1. 核心陷阱 |
| Q1_python_func_param | graph_edge | llm | 0.85 | ["parameter", "参数传递"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 根据你提供的学习材料，对于 Python 函数的参数，可以从两个最核心且初学者容易踩坑的特性入手来理解：**默认参数的“记忆”陷阱** 和 **可变参数的灵活使用**。结合原文证据，我为你梳理出清晰的认知框架。

---

### 1. 默 |
| Q1_python_func_param | weighted_rrf | llm | 0.85 | ["parameter", "参数传递"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，关键在于抓住**默认参数的陷阱**与**不变对象**的设计原则，再扩展到**可变参数**的灵活性。下面用教学化的结构帮你理清要点。

## 1. 默认参数为什么是“坑”？
Python 在**定义函数**时就 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源 |
| Q2_course_quality | query_understanding | llm | 0.75 | ["教学设计", "课程安排", "教学计划", "评估"] | {"vector": 8, "keyword": 16} | 8 | 8 | 基于你提供的材料，该教学安排整体上是**合理且符合职业教育规范的**，主要体现在目标设置、内容组织和质量保障三个维度。具体分析如下：

**1. 教学目标维度合理，体现“三维目标”完整性**
该教学安排严格遵循了职业教育项目化教学的理念，每 |
| Q2_course_quality | graph_edge | llm | 0.65 | ["教学设计", "课程安排", "教学计划", "教学评价", "合理性标准"] | {"vector": 5, "keyword": 10} | 5 | 8 | 好的，我们来分析一下这份教案的教学安排是否合理。

基于你提供的参考证据，这份《新能源汽车驱动电机检修——驱动电机拆装与检测》教案的教学安排是比较合理的，它充分体现了职业教育的特色。

具体分析如下：

**1. 教学模式体现了“理实一体” |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["课程安排", "教学设计", "合理性评估", "教学计划"] | {"vector": 1, "keyword": 2} | 1 | 3 | 好的，我们基于提供的参考证据，从几个关键维度来判断这份教学安排是否合理。

目前看来，该教学安排在部分设计上是合理的，但由于缺乏核心信息，无法做出全面判断。

**1. 毕业标准方面（合理）**
-   **明确性与弹性**：证据 [1]  |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.9 | ["配置模板", "设置模板", "用户手册", "操作指南", "文档"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["template配置", "模板设置", "文档模板", "配置指南"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。提供的参考证据涉及校内实训室条件、专业师资队伍、教学质量管理和Python错误处理与调试，未检索到与“模板配置”相关的文档资料。 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["配置模板", "模板设置", "使用文档", "说明文档"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。提供的参考证据全部围绕 Python 的文档测试（`doctest`）展开，没有涉及“模板配置”的相关资料。 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。

当前提供的参考证据均与《水环境监测技术》课程相关，包括该课程的编制说明、教学内容及教学目标 [1][2]。证据中未包含任何关于“电子信息专业课程”的信息。

如果您需要查询相关课程信息，请提供具体的课程名称或相关的参 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。所提供的参考证据均围绕《水环境监测》课程，未涉及电子信息专业课程相关内容。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `646` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要理解 Python 函数的参数，可以从三个维度入手：**参数的形式、参数的传递机制、以及默认参数的特殊规则**。参考证据正好揭示了其中最容易被忽视的“坑”，学透这一点就能建立起正确的参数心智模型。\n\n---\n\n### 1. 分清参数的种类\n\n函数定义时，参数主要有以下几种形式：\n\n- **必选参数**：调用时按顺序传入，数量必须一致。\n- **默认参数**：形如 `def add_end(L=[])`，调用时可省略，此时使用定义时设置"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要理解 Python 函数的参数，尤其是初学者最容易困惑的默认参数，关键在于建立**“变量指向对象”**的思维。最好的切入点，就是吃透默认参数的一个经典“陷阱”。\n\n我们可以从以下几点层层递进，帮你建立清晰的理解：\n\n### 1. 核心陷阱：默认参数“只被计算一次”\n\n很多初学者会像这样定义一个函数：\n```python\ndef add_end(L=[]):\n    L.append('END')\n    return L\n```\n\n首"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "根据你提供的学习材料，对于 Python 函数的参数，可以从两个最核心且初学者容易踩坑的特性入手来理解：**默认参数的“记忆”陷阱** 和 **可变参数的灵活使用**。结合原文证据，我为你梳理出清晰的认知框架。\n\n---\n\n### 1. 默认参数：为什么不能直接写 `[]` 或 `{}`？\n\n这是参数理解中最重要的一点。很多新手会定义一个带有空列表默认参数的函数，例如：\n\n```python\ndef add_end(L=[]):\n   "}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，关键在于抓住**默认参数的陷阱**与**不变对象**的设计原则，再扩展到**可变参数**的灵活性。下面用教学化的结构帮你理清要点。\n\n## 1. 默认参数为什么是“坑”？\nPython 在**定义函数**时就会计算默认参数的值，并让参数变量指向那个对象。如果默认值是一个可变对象（如列表 `[]`），后续调用中对该对象的修改就会被“记住”。\n\n### 示例（陷阱演示）\n```python\ndef add_e"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "未找到足够参考来源"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 16}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "gr...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.20 | 0.80 | 0.80 | 0.40 | +0.20 | +0.25 | 中性 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.60 | 0.00 | 0.00 | 0.00 | -0.60 | -1.00 | 退化 | 1 |
| Q3_default_param_pitfall | REQ-026 | 0.80 | 0.60 | 1.00 | 0.80 | +0.00 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.20 | 0.00 | 0.80 | 0.80 | +0.60 | +0.75 | 正向 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 0.00 | 0.80 | 1.00 | 0.00 | +0.00 | +0.00 | 中性 | 1 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.20 | 0.40 | 0.20 | 0.40 | +0.20 | +0.25 | 中性 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.80 | 0.80 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 1.00 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

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
| Q1_decorator_concept | baseline_rule_no_edge | 0.20 | 0.20 | 0.29 | 0.00 | 装饰器 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 0.60 | 0.60 | 0.57 | 0.60 | 装饰器,函数,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q2_generator_iterator_relationship | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q2_generator_iterator_relationship | graph_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q2_generator_iterator_relationship | weighted_rrf | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 0.80 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.20 | 0.40 | 0.38 | 0.00 | 先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.80 | 0.88 | 0.20 | 环境监测,培养目标,职业能力,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q6_python_closure | query_understanding | 0.60 | 0.80 | 0.88 | 0.60 | 闭包,装饰器,函数,引用 |
| Q6_python_closure | graph_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q6_python_closure | weighted_rrf | 0.80 | 1.00 | 1.00 | 0.80 | 闭包,装饰器,函数,内部,引用 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.80 | 0.80 | 0.80 | 0.80 | 化学检验工,水环境监测工,大气环境监测工,环境噪声 |
| Q8_training_program_occupation | query_understanding | 0.80 | 0.80 | 0.80 | 0.80 | 化学检验工,水环境监测工,大气环境监测工,环境噪声 |
| Q8_training_program_occupation | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 化学检验工,水环境监测工,大气环境监测工,环境噪声,室内环境 |
| Q8_training_program_occupation | weighted_rrf | 1.00 | 1.00 | 1.00 | 1.00 | 化学检验工,水环境监测工,大气环境监测工,环境噪声,室内环境 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q10_python_advanced_synthesis | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,列表生成式,yield,for |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |

### REQ-028 per-sample summary (semantic metric)

| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |
|--------|--------------|--------------|-------|----------------|-------------|----------------|
| Q1_decorator_concept | 0.20 | 0.60 | +0.40 | +0.50 | 正向 | 1 |
| Q2_generator_iterator_relationship | 0.00 | 1.00 | +1.00 | +1.00 | 正向 | 1 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | 0.60 | 0.40 | -0.20 | -0.50 | 退化 | 0 |
| Q5_course_target_summary | 0.60 | 0.80 | +0.20 | +0.50 | 正向 | 0 |
| Q6_python_closure | 0.00 | 1.00 | +1.00 | +1.00 | 正向 | 1 |
| Q7_kg_occupation_to_skill | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.80 | 1.00 | +0.20 | +1.00 | 正向 | 0 |
| Q9_course_standard_syllabus | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `9` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `5` 样例达标

