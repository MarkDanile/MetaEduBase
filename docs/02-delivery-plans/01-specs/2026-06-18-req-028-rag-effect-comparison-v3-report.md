# REQ-028 P2 RAG 弱召回样例 v3 三口径报告 (real LLM)

## 环境

- Generated At: `2026-06-18T21:52:31.859316+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要真正理解 Python 函数的参数，光记住语法是不够的，关键是抓住两个容易踩坑但非常实用的特性：**默认参数的行为**和**可变参数**的概念。结合廖雪峰教程中的讲解，我帮你梳理一下。

---

### 1. 默认参数 —— 别让函数“ |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["参数传递", "形参", "实参", "函数定义"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要深入理解 Python 函数的参数，可以试着从“背靠背”的两个角度来拆解：一是函数**定义者**的视角，二是函数**调用者**的视角。

这个理解框架的核心，是把函数接口看作一份明确的“约定”[3]。

### 1. 先定规则：从定义者的 |
| Q1_python_func_param | graph_edge | llm | 0.85 | ["参数传递", "形参实参", "函数定义"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，最好的方式是**先认清参数的几种类型，再抓住默认参数的陷阱与解决方案**，最后用接口的视角去体会封装与灵活调用。下面结合实例帮你逐步梳理。

### 1. 先看整体：参数决定了函数的面貌
在 Python 中 |
| Q1_python_func_param | weighted_rrf | llm | 0.85 | ["parameter", "参数传递", "形参实参"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，最关键的是抓住两点：**参数是如何传递的**，以及**默认参数在什么时候求值**。很多初学者觉得参数“记住了”上次的值，其实根源就在这里。

下面结合具体例子说明，所有结论都有来源支撑。

### 1. 默认 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q2_course_quality | query_understanding | llm | 0.7 | ["课程安排", "教学计划", "教学设计", "教学评估"] | {"vector": 1, "keyword": 2} | 1 | 3 | 根据您提供的参考证据，我无法直接判断“这份材料”的教学安排是否合理。

要做出判断，需要提供“这份材料”的具体内容，但您的问题中没有附带需评估的教育计划或教学安排文本。现有参考证据仅提供了毕业要求、学习评价和调课审批表等信息，这些属于评价合 |
| Q2_course_quality | graph_edge | llm | 0.78 | ["教学计划", "课程安排", "教学设计", "教学大纲", "教学组织"] | {"vector": 6, "keyword": 12} | 6 | 8 | 根据您提供的参考证据，这份材料的教学安排在理念和结构上是**基本合理**的，主要体现在以下三个方面：

1.  **课程定位与标准明确**
    *   该《水环境监测》课程被明确划定为“专业技能课”，而非公共基础课 [1]。这一分类符合 |
| Q2_course_quality | weighted_rrf | llm | 0.72 | ["课程设计", "教学计划", "教学方案", "教学评价", "合理性评估"] | {"vector": 5, "keyword": 10} | 5 | 8 | 根据提供的参考证据，可以判断这份名为《新能源汽车驱动电机检修——驱动电机拆装与检测》的材料，其教学安排是合理的。该安排符合职业教育“以能力为本位、理实一体化”的核心理念，具体体现在以下几个方面：

1.  **课程模式与教学方法符合标准** |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.92 | ["模板设置", "配置模板", "帮助文档", "技术文档", "用户手册"] | {"vector": 1, "keyword": 2} | 1 | 4 | 未找到足够参考来源。您提供的参考证据主要涉及“手动变速器油液检查”、“检修作业准备”及“技能考核标准”等内容，其中未包含任何与“模板配置”相关的文档信息。 |
| Q3_template_doc | graph_edge | llm | 0.78 | ["模板设置", "配置模板", "模板文档", "使用指南"] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | weighted_rrf | llm | 0.8 | ["模板设置", "配置模板", "模板管理", "文档模板"] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。提供的参考证据均围绕“水环境监测”课程的教学计划、教材和教学目标，未涉及电子信息专业课程的相关信息。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `621` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要真正理解 Python 函数的参数，光记住语法是不够的，关键是抓住两个容易踩坑但非常实用的特性：**默认参数的行为**和**可变参数**的概念。结合廖雪峰教程中的讲解，我帮你梳理一下。\n\n---\n\n### 1. 默认参数 —— 别让函数“记住”不该记的东西\n\n默认参数允许我们给函数参数设一个初始值，调用时如果不传该参数就自动使用默认值。但这里有一个“最大的坑”[1]。看下面的例子：\n\n```python\ndef add_end(L=["}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要深入理解 Python 函数的参数，可以试着从“背靠背”的两个角度来拆解：一是函数**定义者**的视角，二是函数**调用者**的视角。\n\n这个理解框架的核心，是把函数接口看作一份明确的“约定”[3]。\n\n### 1. 先定规则：从定义者的视角理解\n\n你作为函数的创建者，需要决定这个函数怎么被使用。Python 提供了灵活的工具，从简单到复杂，可以按需组合。\n\n-   **最基础的“位置参数”**\n    这是最直接的规则：调用时传参的"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，最好的方式是**先认清参数的几种类型，再抓住默认参数的陷阱与解决方案**，最后用接口的视角去体会封装与灵活调用。下面结合实例帮你逐步梳理。\n\n### 1. 先看整体：参数决定了函数的面貌\n在 Python 中定义函数时，我们会把参数的名字和位置确定下来，函数的接口就完成了。调用者只需知道怎么传参、会返回什么，内部细节完全被封装起来 [3]。  \n根据需求，参数可以分为：**必选参数（位置参数）、默认参数、"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，最关键的是抓住两点：**参数是如何传递的**，以及**默认参数在什么时候求值**。很多初学者觉得参数“记住了”上次的值，其实根源就在这里。\n\n下面结合具体例子说明，所有结论都有来源支撑。\n\n### 1. 默认参数的值在函数**定义**时就被确定了\n\n这是最容易产生困惑的地方。看一个经典的反面例子 [1]：\n\n```python\ndef add_end(L=[]):\n    L.append('END')\n"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "未找到足够参考来源。"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 1, "keyword": 2}, "vector_fallback_count": 1, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_ed...
```

## REQ-026 弱召回样例关键事实覆盖度对比

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.00 | 1.00 | 0.80 | 0.80 | +0.80 | 正向 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.40 | 0.00 | 0.00 | 0.00 | -0.40 | 退化 | 1 |
| Q3_default_param_pitfall | REQ-026 | 0.80 | 0.60 | 0.80 | 0.60 | -0.20 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.40 | 0.00 | 0.20 | 0.40 | +0.00 | 中性 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 0.00 | 0.40 | 0.60 | 0.60 | +0.60 | 正向 | 1 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.40 | 0.20 | 0.20 | 0.20 | -0.20 | 中性 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.80 | 0.80 | 1.00 | 1.00 | +0.20 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 0.80 | 0.80 | 0.80 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `5` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `2` / `10`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `2` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `2` / `10`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。


## REQ-028 三口径覆盖度对比

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q1_decorator_concept | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 装饰器,函数,语法糖,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 0.60 | 0.60 | 0.75 | 0.60 | 生成器,迭代器,yield |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 0.40 | 0.40 | 0.50 | 0.00 | 生成器,迭代器 |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.00 | 生成器,迭代器 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.62 | 0.40 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q6_python_closure | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.80 | 0.80 | 0.80 | 0.80 | 化学检验工,水环境监测工,大气环境监测工,环境噪声 |
| Q8_training_program_occupation | query_understanding | 0.80 | 0.80 | 0.80 | 0.80 | 化学检验工,水环境监测工,大气环境监测工,环境噪声 |
| Q8_training_program_occupation | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 化学检验工,水环境监测工,大气环境监测工,环境噪声,室内环境 |
| Q8_training_program_occupation | weighted_rrf | 1.00 | 1.00 | 1.00 | 1.00 | 化学检验工,水环境监测工,大气环境监测工,环境噪声,室内环境 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |

### REQ-028 per-sample summary (semantic metric)

| Sample | baseline sem | weighted sem | delta | 判定 (sem) | edge_in_packed |
|--------|--------------|--------------|-------|-------------|----------------|
| Q1_decorator_concept | 0.00 | 0.80 | +0.80 | 正向 | 1 |
| Q2_generator_iterator_relationship | 0.60 | 0.40 | -0.20 | 中性 | 1 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | 0.80 | 0.00 | -0.80 | 退化 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | 中性 | 0 |
| Q6_python_closure | 0.00 | 0.00 | +0.00 | 中性 | 1 |
| Q7_kg_occupation_to_skill | 0.80 | 0.80 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.80 | 1.00 | +0.20 | 中性 | 0 |
| Q9_course_standard_syllabus | 0.80 | 0.80 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 0.80 | +0.00 | 中性 | 1 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `7` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift ≥ 30%)**: `1` 样例达标

