# REQ-027 P2 RAG 弱召回样例 v1 复跑报告 (real LLM)

## 环境

- Generated At: `2026-06-18T20:46:47.598473+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 理解 Python 函数的参数，最好从“数据如何流入函数”这一角度入手，并特别关注**默认参数**的行为与设计原则。根据参考证据，你可以按以下顺序建立认知：

### 1. 明确参数的作用
参数是函数与外部世界交互的接口。你在调用函数时传入 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["形参", "实参", "参数传递", "parameter"] | {"vector": 8, "keyword": 19, "graph": 3} | 8 | 8 | 要深入理解 Python 函数的参数，关键是要抓住几个核心概念，尤其要警惕**默认参数的“坑”**。结合你手上的学习资料，我提取了三个最重要的理解维度：

---

### 1. 位置参数与默认参数 —— 搞懂“记忆”陷阱

函数参数最常见 |
| Q1_python_func_param | graph_edge | llm | 0.85 | ["parameter", "参数传递", "函数定义"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，关键是把握“定义”和“调用”两个视角，并认清不同类型参数的行为特点。下面从最基础的位置参数出发，再逐步深入到默认参数、可变参数，帮助你建立起清晰的认知。

### 1. 位置参数 — 最直接的“占位”方式
在 |
| Q1_python_func_param | weighted_rrf | llm | 0.87 | ["parameter", "参数传递", "形式参数"] | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} | 8 | 8 | 要理解 Python 函数的参数，最好的方式是把握几个核心概念：**位置参数、默认参数、可变参数**，尤其是默认参数的“陷阱”和正确用法。下面结合例子为你梳理。

## 1. 位置参数与默认参数
函数定义时可以给参数设置默认值，调用时如果没 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源 |
| Q2_course_quality | query_understanding | llm | 0.72 | ["课程安排", "教学设计", "教学计划", "教育评估"] | {"vector": 1, "keyword": 2} | 1 | 3 | 根据您提供的参考证据，目前无法直接判断“这份材料”的教学安排是否合理，因为您未上传具体的教学安排材料。现有证据仅展示了以下相关制度与要求，可作为判断教学安排合理性的通用框架：

1. **毕业要求**：学生需在3年内修满规定学分，完成军训、 |
| Q2_course_quality | graph_edge | llm | 0.75 | ["课程安排", "教学计划", "教学大纲", "教学评估", "课程设置评价"] | {"vector": 5, "keyword": 10} | 5 | 8 | 根据您提供的参考证据，可以判断这份关于《水环境监测》课程的教学材料，其教学安排在以下方面是合理的：

1.  **课程定位与结构设置合理**
    材料明确了该课程属于“专业技能课”[1]。在专业的课程结构中，“水环境监测”被列在“专业核 |
| Q2_course_quality | weighted_rrf | llm | 0.7 | ["教学设计", "课程计划", "教学评估"] | {} | 0 | 0 | 未找到足够参考来源。请提供待评估的教学材料或相关参考证据，以便我协助分析。 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {} | 0 | 0 | 未找到足够参考来源。请提供相关文档或资料片段，我将基于证据为您整理模板配置说明。 |
| Q3_template_doc | query_understanding | llm | 0.9 | ["模板设置", "配置模板", "文档模板", "配置指南"] | {} | 0 | 0 | 未找到足够参考来源 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["模板设置", "配置文件", "使用文档", "资料"] | {"vector": 8, "keyword": 16} | 8 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["模板设置", "配置模板", "template configuration", "使用手册", "用户指南"] | {"vector": 3, "keyword": 6} | 3 | 8 | 根据您提供的参考证据，为您整理了 Flask 中使用模板（以 Jinja2 为例）的配置要点与文档指引，具体如下：

---

### 1. 环境与安装
模板引擎 Jinja2 需要单独安装，Flask 默认支持它 [1]：
```bash |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。当前提供的参考证据全部围绕《水环境监测技术》课程与《环境监测技术》教材，仅涉及水环境监测领域的专业课程内容，并未包含“电子信息专业课程”的相关信息。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"graph": 3, "keyword": 3} | 0 | 5 | 未找到足够参考来源。您提供的参考证据均与「水环境监测」专业相关 [1][2]，未涉及电子信息专业的课程信息，无法据此回答该问题。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 6 | 未找到足够参考来源。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 2, "keyword": 4} |
| Q2_cross_section_relationship | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 4 | 1 | 7 | {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `233` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，最好从“数据如何流入函数”这一角度入手，并特别关注**默认参数**的行为与设计原则。根据参考证据，你可以按以下顺序建立认知：\n\n### 1. 明确参数的作用\n参数是函数与外部世界交互的接口。你在调用函数时传入的数据，会通过参数传递到函数内部进行处理。例如 `add_end([1,2,3])` 中的 `[1,2,3]` 就是传给参数 `L` 的实际值 [1]。\n\n### 2. 重点理解默认参数的“陷阱”与最"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要深入理解 Python 函数的参数，关键是要抓住几个核心概念，尤其要警惕**默认参数的“坑”**。结合你手上的学习资料，我提取了三个最重要的理解维度：\n\n---\n\n### 1. 位置参数与默认参数 —— 搞懂“记忆”陷阱\n\n函数参数最常见的用法是按位置传递，但当你为参数指定默认值时，就必须小心一个经典问题：**默认参数如果指向可变对象，会“记住”上一次被修改的状态**。\n\n资料中给出了一个很直观的例子 [1]：\n\n```python\n"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，关键是把握“定义”和“调用”两个视角，并认清不同类型参数的行为特点。下面从最基础的位置参数出发，再逐步深入到默认参数、可变参数，帮助你建立起清晰的认知。\n\n### 1. 位置参数 — 最直接的“占位”方式\n在定义函数时，把参数名按顺序写好，就形成了位置参数。调用时必须按相同的顺序传入对应的值。\n> **参考**：定义函数时把参数的名字和位置确定下来，函数的接口定义就完成了。比如 `def power(x)"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 8, "keyword": 19, "graph": 3, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 1, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，最好的方式是把握几个核心概念：**位置参数、默认参数、可变参数**，尤其是默认参数的“陷阱”和正确用法。下面结合例子为你梳理。\n\n## 1. 位置参数与默认参数\n函数定义时可以给参数设置默认值，调用时如果没传值就用默认值。  \n但**默认参数有一个大坑**：默认值在函数定义时就被计算一次，如果默认值是可变对象（如列表），后续调用会共享同一个对象。  \n参考[1]中的例子：\n```python\ndef a"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 0, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "未找到足够参考来源"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "query_understanding", "retrieval_counts": {"vector": 1, "keyword": 2}, "vector_fallback_count": 1, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "final_answer_preview": "根据您提供的参考证据，目前无法直接判断“这份材料”的教学安排是否合理，因为您未上传具体的教学安排材料。现有证据仅展示了以下相关制度与要求，可作为判断教学安排合理性的通用框架：\n\n1. **毕业要求**：学生需在3年内修满规定学分，完成军训、社会实践、校内实训、顶岗实习等环节，未通过者可补考，补考三门不合格则留级。同时，取得化学检验员（四级）或1+X水环境监测与治理（初级）证书可奖励学分[1]。\n2. **学习评价**：考试课成绩由期中3"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "graph_edge", "retrieval_counts": {"vector": 5, "keyword": 10}, "vector_fallback_count": 5, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 2, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "...
```

## REQ-026 弱召回样例关键事实覆盖度对比

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.00 | 0.80 | 0.40 | 0.60 | +0.60 | 正向 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 0.40 | 0.00 | 1.00 | 0.00 | -0.40 | 退化 | 1 |
| Q3_default_param_pitfall | REQ-026 | 0.60 | 0.80 | 0.60 | 0.80 | +0.20 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.60 | 0.20 | 0.00 | 0.60 | +0.00 | 中性 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | 中性 | 0 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `3` / `5`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `5`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `1` / `5`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `1` / `5`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。

