# REQ-027 P2 RAG 弱召回样例 v1+v2 报告 (real LLM)

## 环境

- Generated At: `2026-06-18T20:54:11.456887+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要真正理解 Python 函数的参数，建议你抓住两个最核心的概念：**默认参数**和**可变参数**，并且一定要在交互环境中亲手敲代码验证 [1][3]。下面结合教材内容，给你一个清晰的理解路径。

### 1. 默认参数的最大“坑”与正确 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["parameter", "函数参数", "形参", "实参", "参数传递"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 理解 Python 函数的参数，最好的方式是把它们看作**调用者和函数约定好的“数据入口”**，并按照“必选–可选–打包”的思路层层递进。下面从最基础的位置参数开始，逐步引入更灵活的参数类型。

### 1. 位置参数：最朴素的“按顺序传值 |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["parameter", "参数传递", "函数定义", "形式参数", "实际参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 对于 Python 函数参数的理解，可以把握一个核心：**参数是函数与调用者之间的“接口约定”**，不同种类的参数解决了不同场景下的传参需求。结合你提供的资料，可以从下面几个层次来建立清晰的认知。

---

### 1. 从“位置参数”开 |
| Q1_python_func_param | weighted_rrf | llm | 0.9 | ["parameter", "参数传递", "形参实参", "函数签名"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 要理解 Python 函数的参数，最关键是抓住 **“对象可变性”** 对默认参数的影响，并掌握可变参数的设计思路。结合上下文，可以从以下三个层面来理解。

### 1. 默认参数的本质与“陷阱”
在 Python 函数定义时，默认参数的值 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q2_course_quality | query_understanding | llm | 0.7 | ["教学计划", "课程设置", "教学评估"] | {"vector": 2, "keyword": 4} | 2 | 7 | 根据提供的参考证据，这份教学材料在教学安排上具有较高的合理性，主要体现在课程体系完整、评价机制科学和毕业要求明确三个方面。下面具体展开分析。

**1. 课程结构严谨，符合国家标准**
该专业的课程设置明确划分为公共基础课和专业技能课，且两 |
| Q2_course_quality | graph_edge | llm | 0.78 | ["课程安排", "教学设计", "教学计划", "教学质量"] | {"vector": 4, "keyword": 8} | 4 | 8 | 根据提供的参考证据，可以判断这份材料的教学安排是合理的。具体分析如下：

首先，在教学管理安排上，材料明确指出“本专业教学管理有一定的规范性和灵活性，能合理调配教师、实训室和实训场地等教学资源，为课程的实施创造条件” [2]，这直接回应了教 |
| Q2_course_quality | weighted_rrf | llm | 0.6 | ["教学设计", "课程安排", "合理性评价"] | {} | 0 | 0 | 未找到足够参考来源 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.8 | ["配置模板", "模板说明", "配置指南", "用户手册"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到专门针对“模板配置”的详细文档资料。参考证据主要介绍了在 Flask 中使用 Jinja2 模板的基本方式，并未描述模板引擎的配置参数（例如模板加载路径、环境设置、过滤器配置等）。相关内容可概括为：

- Flask 默认支持 Jin |
| Q3_template_doc | graph_edge | llm | 0.9 | ["配置模板", "模板设置", "参数模板", "文档"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["配置模板", "模板设置", "文档资料"] | {} | 0 | 0 | 未找到足够参考来源 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。

您询问的“电子信息专业课程”在提供的参考证据中并未出现。当前证据[1][2]全部围绕“水环境监测”课程，包括其课程标准、教材（《环境监测技术》）、教学项目（如水中物理/金属/非金属/有机物指标检测、水质自动监测等）、 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。提供的参考证据均围绕《水环境监测技术》课程，涉及环境监测专业的中职教学计划、教材及教学内容，未包含电子信息专业课程的相关信息。建议查询电子信息专业的课程标准或教学大纲获取准确内容。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `378` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要真正理解 Python 函数的参数，建议你抓住两个最核心的概念：**默认参数**和**可变参数**，并且一定要在交互环境中亲手敲代码验证 [1][3]。下面结合教材内容，给你一个清晰的理解路径。\n\n### 1. 默认参数的最大“坑”与正确用法\n默认参数是在函数**定义时**就被计算好的，而不是每次调用时才计算 [1]。当默认参数是一个可变对象（例如 `[]` 或 `{}`）时，这个对象会在多次调用之间被“记住”，导致意料之外的结果。\n"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，最好的方式是把它们看作**调用者和函数约定好的“数据入口”**，并按照“必选–可选–打包”的思路层层递进。下面从最基础的位置参数开始，逐步引入更灵活的参数类型。\n\n### 1. 位置参数：最朴素的“按顺序传值”\n位置参数就是按照定义时的顺序，依次传入对应位置的实参。  \n例如，`def power(x):` 中的 `x` 就是一个位置参数，调用时必须提供且只能提供一个值 [3]。  \n```python\n"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "对于 Python 函数参数的理解，可以把握一个核心：**参数是函数与调用者之间的“接口约定”**，不同种类的参数解决了不同场景下的传参需求。结合你提供的资料，可以从下面几个层次来建立清晰的认知。\n\n---\n\n### 1. 从“位置参数”开始，理解最基础的约定\n参数的第一种形态是**位置参数**，又称必选参数。调用函数时，必须按照定义时的位置和数量传入参数，否则会出错[3]。  \n例如一个计算平方的函数：\n```python\ndef p"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，最关键是抓住 **“对象可变性”** 对默认参数的影响，并掌握可变参数的设计思路。结合上下文，可以从以下三个层面来理解。\n\n### 1. 默认参数的本质与“陷阱”\n在 Python 函数定义时，默认参数的值**只计算一次**，后续调用会复用同一个对象。  \n如果默认值是一个**可变对象**（如 `[]`、`{}`），那么函数内部对该对象的修改会被“记住”，导致非预期的累积效果[1]。\n\n例如：\n```p"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "未找到足够参考来源。"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 2, "keyword": 4}, "vector_fallback_count": 2, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "根据提供的参考证据，这份教学材料在教学安排上具有较高的合理性，主要体现在课程体系完整、评价机制科学和毕业要求明确三个方面。下面具体展开分析。\n\n**1. 课程结构严谨，符合国家标准**\n该专业的课程设置明确划分为公共基础课和专业技能课，且两类课程均依据中等职业学校相应教学大纲开设，保证了教学内容和要求的规范性 [1]。公共基础课中，语文、数学、英语等课程不仅遵循大纲，还强调在职业模块中体现专业特色，实现了文化基础与专业需求的结合 [1]"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "graph_edge", "retrieval_counts": {"vector": 4, "keyword": 8}, "vector_fallback_count": 4, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "fi...
```

## REQ-026 弱召回样例关键事实覆盖度对比

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.20 | 0.80 | 0.60 | 0.80 | +0.60 | 正向 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.40 | 0.40 | 0.00 | 0.00 | -0.40 | 退化 | 1 |
| Q3_default_param_pitfall | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.00 | 0.20 | 0.00 | 0.00 | +0.00 | 中性 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.40 | +0.20 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | 中性 | 1 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.20 | 0.20 | 0.40 | 0.20 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.80 | 0.80 | 1.00 | 1.00 | +0.20 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 0.80 | 0.80 | 0.80 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `5` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `10`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `1` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `1` / `10`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。

