# REQ-025 P2 graph_edge prompt impact validation report

## 环境

- Generated At: `2026-06-18T19:10:29.398337+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 理解 Python 函数的参数，关键是抓住“参数如何传递和如何被记住”这个核心。从参考证据来看，**默认参数** 和 **可变参数** 是两个最需要深入理解的类型，尤其是默认参数的“陷阱”对初学者非常重要。下面分步讲解。

---

### |
| Q1_python_func_param | query_understanding | llm | 0.85 | ["parameter", "参数传递", "函数定义"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要理解 Python 函数的参数，不妨从“接口契约”和“对象绑定”两个角度入手，把参数的类型、传递机制以及常见陷阱串成一条线。

## 1. 参数是函数的“使用说明书”
定义函数时，函数名、参数列表和返回值共同构成了函数的**接口**。调用 |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["parameter", "形参", "实参", "参数传递"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，关键在于把握**默认参数的赋值时机**和**参数对象的可变性**。下面以默认参数为例说明这个最佳理解方式，并结合证据里的典型陷阱与解决方案。

**1. 默认参数在函数定义时只被计算一次**  
默认参数的值 |
| Q1_python_func_param | weighted_rrf | llm | 0.9 | ["parameter", "参数传递", "形参", "实参"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，关键是抓住“参数传递机制”和“默认参数的行为”。根据提供的参考证据，下面从核心要点、典型陷阱和最佳实践三个方面帮你建立清晰的认识。

### 1. 核心认知：默认参数只在函数定义时计算一次
在 Python  |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。由于您未提供具体的教学材料内容，我无法进行分析判断。请附上您需要评估的材料，我将基于参考证据为您提供详细分析。 |
| Q2_course_quality | query_understanding | llm | 0.7 | ["教学计划", "课程安排", "教学评估", "材料审核", "教学质量"] | {"vector": 4, "keyword": 8} | 4 | 8 | 基于提供的参考证据，这份材料中的教学安排总体是合理的，主要体现在教学管理理念、质量监控体系和评价方式设计三个方面。具体分析如下：

**1. 教学管理兼具规范性与灵活性**
从教学管理的顶层设计来看，材料明确提出“教学管理要有一定的规范性和 |
| Q2_course_quality | graph_edge | llm | 0.93 | ["教学计划", "课程设计", "教学评估", "教学组织"] | {"vector": 2, "keyword": 4} | 2 | 6 | 根据您提供的参考证据，可以对该专业（环境监测相关方向）的教学安排进行多维度分析。整体来看，教学安排在**实训资源配置、评价体系设计和毕业要求衔接**等方面均体现出职业教育“教、学、做合一”的特点，安排较为合理。具体分析如下：

### 1. |
| Q2_course_quality | weighted_rrf | llm | 0.6 | ["教学设计", "课程安排", "教材评估", "教学计划评估"] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.9 | ["配置模板", "模板设置", "模板定制", "指南", "使用说明"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。提供的参考资料均为 Python 基础语法相关（文本编辑器、list与tuple等），未涉及模板配置内容。 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["模板配置", "配置模板", "模板设置", "文档资料"] | {} | 0 | 0 | 未找到足够参考来源 |
| Q3_template_doc | weighted_rrf | llm | 0.95 | ["模板设置", "配置模板", "使用手册", "帮助文档", "用户指南"] | {} | 0 | 0 | 未找到足够参考来源 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。提供的参考证据仅涉及“水环境监测”专业的课程编制与内容，没有关于“电子信息专业课程”的信息。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。根据提供的参考证据，内容均围绕《水环境监测》课程展开，未涉及电子信息专业相关信息，因此无法回答该问题。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `118` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "final_answer_preview": "理解 Python 函数的参数，关键是抓住“参数如何传递和如何被记住”这个核心。从参考证据来看，**默认参数** 和 **可变参数** 是两个最需要深入理解的类型，尤其是默认参数的“陷阱”对初学者非常重要。下面分步讲解。\n\n---\n\n### 1. 默认参数：为什么会出现“记忆效应”\n\n先看一个典型的“坑” [1]：\n\n```python\ndef add_end(L=[]):\n    L.append('END')\n    return "}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "final_answer_preview": "要理解 Python 函数的参数，不妨从“接口契约”和“对象绑定”两个角度入手，把参数的类型、传递机制以及常见陷阱串成一条线。\n\n## 1. 参数是函数的“使用说明书”\n定义函数时，函数名、参数列表和返回值共同构成了函数的**接口**。调用者只需要知道“该传哪些参数”、“会得到什么结果”，而不必关心内部的实现细节[3]。因此，参数的第一层理解就是：**让函数能够接收外部数据，实现逻辑复用**。\n\n## 2. 核心参数类型\nPython "}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "final_answer_preview": "理解 Python 函数的参数，关键在于把握**默认参数的赋值时机**和**参数对象的可变性**。下面以默认参数为例说明这个最佳理解方式，并结合证据里的典型陷阱与解决方案。\n\n**1. 默认参数在函数定义时只被计算一次**  \n默认参数的值不是在每次调用函数时重新生成的，而是在 `def` 语句执行时就被计算出来，并且该默认值是一个变量，指向一个具体对象。如果这个对象是可变的（如列表 `[]`），那么后续调用中对默认参数的修改会直接改变"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "final_answer_preview": "理解 Python 函数的参数，关键是抓住“参数传递机制”和“默认参数的行为”。根据提供的参考证据，下面从核心要点、典型陷阱和最佳实践三个方面帮你建立清晰的认识。\n\n### 1. 核心认知：默认参数只在函数定义时计算一次\n在 Python 中，**默认参数的值是在函数定义时被计算并保存的，而不是每次调用时重新计算**[1]。这意味着如果默认值指向一个**可变对象**（例如列表 `[]`），那么后续对它的修改会保留下来，导致看似“记忆”了"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "final_answer_preview": "未找到足够参考来源。由于您未提供具体的教学材料内容，我无法进行分析判断。请附上您需要评估的材料，我将基于参考证据为您提供详细分析。"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 4, "keyword": 8}, "vector_fallback_count": 4, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "final_answer_preview": "基于提供的参考证据，这份材料中的教学安排总体是合理的，主要体现在教学管理理念、质量监控体系和评价方式设计三个方面。具体分析如下：\n\n**1. 教学管理兼具规范性与灵活性**\n从教学管理的顶层设计来看，材料明确提出“教学管理要有一定的规范性和灵活性”，并能“合理调配教师、实训室和实训场地等教学资源”，这为课程实施创造了条件 [1][2]。这表明教学安排考虑到了职业教育对资源调配的需求，避免了刚性管理带来的僵化。\n\n**2. 构建了全过程的"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "graph_edge", "retrieval_counts": {"vector": 2, "keyword": 4}, "vector_fallback_count": 2, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "final_answer_preview": "根据您提供的参考证据，可以对该专业（环境监测相关方向）的教学安排进行多维度分析。整体来看，教学安排在**实训资源配置、评价体系设计和毕业要求衔接**等方面均体现出职业教育“教、学、做合一”的特点，安排较为合理。具体分析如下：\n\n### 1. 校内实训条件满足“理实一体”要求\n证据[1]显示，该专业配备了普通化学、仪器分析、环境监测、环境微生物等专用实训室，总面积超过790m²，并按照**标准班40人/班**配置了核心仪器设备。例如，环境"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "weighted_rrf", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_...
```
