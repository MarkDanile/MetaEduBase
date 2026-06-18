# REQ-026 P2 RAG 弱召回样例集与效果比较报告 (real LLM)

## 环境

- Generated At: `2026-06-18T19:27:54.754864+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要理解 Python 函数的参数，可以从“参数是什么”和“几种常见参数类型的特点与陷阱”入手，再结合代码实例来体会。下面以教学的方式为你拆解。

### 1. 先知道参数的基本作用
函数就像一台机器，参数就是你喂给机器的原材料。定义函数时写 |
| Q1_python_func_param | query_understanding | llm | 0.85 | ["参数定义", "形参", "实参"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要理解 Python 函数的参数，关键在于把握它的**分类、顺序和易错点**。结合参考材料，我们可以把最常见的理解路径梳理成三层，一层层掌握，就会非常清晰。

### 1. 先认识参数都有哪些“角色”
Python 里函数参数可以分成下面几 |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["参数传递", "形式参数", "实际参数", "argument", "parameter"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 要理解 Python 函数的参数，可以从“**调用**”和“**定义**”两个角度来把握，关键是弄清楚**参数个数、参数类型、默认值**和**可变参数**这几个核心概念。下面结合具体例子来梳理。

### 1. 先看怎样正确调用函数——参数 |
| Q1_python_func_param | weighted_rrf | llm | 0.9 | ["参数传递", "函数定义", "parameter", "argument"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，可以围绕“如何让函数更灵活、更健壮”这条主线来学习。结合参考内容，建议从以下几个层面逐步深入：

### 1. 函数的“契约”：参数个数与类型
函数定义时声明的参数，就是调用时必须遵守的基本约定。如果传入的参 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源 |
| Q2_course_quality | query_understanding | llm | 0.75 | ["教学设计", "课程安排", "教学评估", "教学计划"] | {"vector": 1, "keyword": 2} | 1 | 3 | 根据您提供的材料，这份教学安排从结构上看是**基本合理且严谨的**。主要体现在以下两个方面：

1.  **毕业要求明确，导向清晰**
    材料明确了毕业需满足的“修满学分”、“完成军训、顶岗实习”等一揽子教学活动 [1]。特别是提出了 |
| Q2_course_quality | graph_edge | llm | 0.6 | ["教学计划", "课程设计", "评估", "审核", "教学设计"] | {"vector": 8, "keyword": 16} | 8 | 8 | 根据您提供的材料，结合职业教育课程设计的核心要素，可以从**目标设定、内容支撑、过程管理与师资保障**四个维度来判断这份教学安排的合理性。总体来看，这份材料体现的教学安排是**相对合理且规范的**。

具体分析如下：

**1. 目标设定清 |
| Q2_course_quality | weighted_rrf | llm | 0.75 | ["课程规划", "教学设计", "教学计划合理性"] | {} | 0 | 0 | 未找到足够参考来源。请提供具体的教学材料（如课程大纲、教案或教学活动设计），以便我根据已有知识库中与职业教育相关的参考证据进行判断。 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.9 | ["配置文档", "模板设置", "模板指南"] | {} | 0 | 0 | 未找到足够参考来源。 |
| Q3_template_doc | graph_edge | llm | 0.88 | ["配置文件", "模板设置", "技术手册", "使用指南", "配置说明"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["模板设置", "配置模板", "template configuration"] | {"vector": 3, "keyword": 6} | 3 | 8 | 根据提供的参考证据，以下是关于模板配置的文档资料摘要：

### 模板引擎与配置
- **默认模板引擎**：[1] 指出 Flask 默认支持的模板是 **Jinja2**，需先通过 `pip install jinja2` 安装。
- * |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。您提供的“参考证据”[2][9] 全部是关于《水环境监测》课程的教学大纲、授课计划与教学内容，与“电子信息专业课程”无关，因此我无法为您提供该问题的相关信息。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `236` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，可以从“参数是什么”和“几种常见参数类型的特点与陷阱”入手，再结合代码实例来体会。下面以教学的方式为你拆解。\n\n### 1. 先知道参数的基本作用\n函数就像一台机器，参数就是你喂给机器的原材料。定义函数时写在小括号里的变量叫 **形参**，调用时实际传给函数的值叫 **实参**。例如：\n```python\ndef greet(name):      # name 是形参\n    print('Hello"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，关键在于把握它的**分类、顺序和易错点**。结合参考材料，我们可以把最常见的理解路径梳理成三层，一层层掌握，就会非常清晰。\n\n### 1. 先认识参数都有哪些“角色”\nPython 里函数参数可以分成下面几种，它们各有用途 [2]：\n- **必选参数**：调用时必须按位置传入。\n- **默认参数**：定义时给一个默认值，调用时可以不传。\n- **可变参数** (`*args`)：可以接收任意个位置参数，"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，可以从“**调用**”和“**定义**”两个角度来把握，关键是弄清楚**参数个数、参数类型、默认值**和**可变参数**这几个核心概念。下面结合具体例子来梳理。\n\n### 1. 先看怎样正确调用函数——参数必须“对上号”\n调用函数时，必须遵守函数定义的**参数个数**和**参数类型**要求，否则 Python 会报错。\n\n- **参数个数要一致**  \n  像求绝对值的函数 `abs()`，它只接受 *"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，可以围绕“如何让函数更灵活、更健壮”这条主线来学习。结合参考内容，建议从以下几个层面逐步深入：\n\n### 1. 函数的“契约”：参数个数与类型\n函数定义时声明的参数，就是调用时必须遵守的基本约定。如果传入的参数数量不对，Python 会明确报错 `TypeError`，并提示缺少或给出过多的参数 [3]。如果参数类型不被函数支持（比如给 `abs()` 传入字符串），同样会报 `TypeError` 并给"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "未找到足够参考来源"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 1, "keyword": 2}, "vector_fallback_count": 1, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "根据您提供的材料，这份教学安排从结构上看是**基本合理且严谨的**。主要体现在以下两个方面：\n\n1.  **毕业要求明确，导向清晰**\n    材料明确了毕业需满足的“修满学分”、“完成军训、顶岗实习”等一揽子教学活动 [1]。特别是提出了“未修满学分需补考，三门不合格进行留级”的刚性要求，并设置了“化学检验员（四级）”等证书可“奖励学分”的激励机制 [1]。这种将职业技能鉴定与学业考核相结合的设计，为学生的学习和教师的教学安排提供了清"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 16}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 3, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_...
```

## REQ-026 弱召回样例关键事实覆盖度对比

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.00 | 1.00 | 0.80 | 0.80 | +0.80 | 正向 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.40 | 0.00 | 1.00 | 0.60 | +0.20 | 中性 | 1 |
| Q3_default_param_pitfall | REQ-026 | 0.60 | 0.80 | 0.60 | 0.60 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.60 | 0.00 | 0.40 | 0.00 | -0.60 | 退化 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.40 | 0.40 | +0.20 | 中性 | 0 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `3` / `5`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `5`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `1` / `5`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `1` / `5`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。

