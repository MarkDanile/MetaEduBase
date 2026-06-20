# REQ-028 v3 re-run after TD-068+069 (real LLM)

> **Re-run note (2026-06-20)**: 本报告覆盖 REQ-028 v3 第一次报告（PR #360 `f624f49`）。重跑原因：
> 1. **TD-068 Slice 2 + TD-069 schema migration** 已 merge（PR #366 `ed77227`），dev DB `document_chunks.embedding` / `knowledge_nodes.embedding` 现在真实 `vector(4096)` 类型，pgvector `<=>` 操作符可用
> 2. `validate_req024_p2_real_validation.py` 真 PG dry-run `vector_fallback_count: 0`，retrieval_topn.vector 真命中
> 3. **关键发现**：本次重跑结论与 PR #360 报告**显著变化**——vector 真召回导致 baseline coverage 普遍上升（keyword 兜底不再占主导），但 weighted RRF coverage 反而下降，因为真召回的 chunks 不一定包含 expected keypoints。这是更诚实的诊断：**P2 长链在真实向量召回下的能力，需要新的口径（如语义匹配 / LLM-as-judge）评估**。
> 4. 本次重跑结论：AC-4 (semantic ≥ 0.50) **6/10**（vs PR #360 7/10），AC-5 residual **1/10**（vs PR #360 5/10）。详见下方"自动比较结论"。

## 环境

- Generated At: `2026-06-20T09:10:43.915924+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 在 Python 中，理解函数的参数可以围绕两个视角展开：**站在调用者角度，知道怎么传参、传什么**；**站在定义者角度，知道如何设计灵活的函数接口**。下面结合参考证据，分层讲解。

---

## 一、先明白“调用函数”的基本规矩
调 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["parameter", "参数传递", "函数定义", "参数使用"] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要理解 Python 函数的参数，可以从“接口封装”的角度入手：**参数是函数与外部交流的唯一入口，定义了调用时需要提供哪些信息**。函数内部的具体实现被隐藏，调用者只需知道传什么参数、能得到什么返回值就行了[4]。下面分层讲解，帮你建立清 |
| Q1_python_func_param | graph_edge | llm | 0.85 | ["parameter", "参数传递", "Python函数定义"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 要理解 Python 函数的参数，可以从“定义方”和“调用方”两个视角来把握，并结合参数的不同类型，逐步建立清晰、可用的认识。

## 1. 先建立“接口”思维
函数就像一个有“输入”和“输出”的黑盒。定义函数时我们规定好参数的名字、数量和 |
| Q1_python_func_param | weighted_rrf | llm | 0.85 | ["函数参数", "参数传递", "形参与实参"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 理解 Python 函数的参数，可以从“接口设计”和“参数类型”两个角度入手，这样既好懂又实用。

### 1. 把参数理解为函数的“接口”
调用函数时，只要知道该传什么参数、会返回什么值就够了，无需关心内部的复杂逻辑 [4]。这就是封装的 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 基于您提供的参考证据，这份关于“新能源汽车驱动电机检修——驱动电机拆装与检测”的教学安排是**合理且结构完整的**。以下从多个维度进行分析：

**1. 教学设计系统全面，逻辑清晰**
证据[4]显示，教学分析从内容、学情、目标到重难点形成 |
| Q2_course_quality | query_understanding | llm | 0.78 | ["课程安排", "教学设计", "教学评估"] | {"vector": 16, "graph": 8} | 0 | 8 | 基于提供的参考证据，可以判断这份关于《新能源汽车驱动电机检修——驱动电机拆装与检测》的教学安排是**合理**的。以下从多个维度进行分析：

---

### 1. 教学内容的组织符合岗位能力需求
教案明确将内容划分为“驱动电机结构认识、拆装 |
| Q2_course_quality | graph_edge | llm | 0.75 | ["课程安排", "教学设计", "教学评价", "教学计划"] | {"vector": 16, "keyword": 5, "graph": 8} | 0 | 8 | 基于提供的参考证据，现从职业教育教学管理的核心维度进行分析：

**结论：该材料的教学安排总体上是合理的，体现了职业教育“能力本位、质量监控、资源保障”的特色。**

具体分析如下：

**1. 课程内容与岗位能力匹配度高（职业能力导向）* |
| Q2_course_quality | weighted_rrf | llm | 0.7 | ["教学设计", "教学计划", "课程安排", "评估"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 根据提供的证据材料，我们可以从教学目标的完整性、教学内容的逻辑性以及教学保障的支撑性三个维度来分析教学安排的合理性。

### 1. 教学目标明确，层次清晰
从多个任务材料来看，教学安排设置了明确且结构化的教学目标框架，通常包含认知、技能和 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的参考证据均围绕《新能源汽车驱动电机检修——驱动电机拆装与检测》课程的教学设计，包含教学目标、教学重点难点、教学资源、教学过程等内容，未涉及“模板配置”相关文档资料。 |
| Q3_template_doc | query_understanding | llm | 0.95 | ["模板设置", "配置模板", "操作指南", "使用文档"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的参考证据主要涉及“新能源汽车驱动电机检修——驱动电机拆装与检测”课程的教学设计，未包含与“模板配置”相关的文档资料。 |
| Q3_template_doc | graph_edge | llm | 0.9 | ["template configuration", "模板设置", "配置模板"] | {"vector": 16, "keyword": 3, "graph": 8} | 0 | 8 | 根据您提供的参考证据，暂未找到专门以“模板配置”为标题的独立文档，但其中包含了 Flask 框架下模板使用的完整基础资料，可以用来回答模板配置的相关问题。以下按教学场景整理关键内容，并标注对应出处。

---

### 1. 模板引擎的选择 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["模板设置", "配置模板", "模板指南", "模板说明"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 基于提供的参考证据，与“模板配置”相关的文档资料主要集中在 Web 开发中模板技术的使用方式上，尤其是 Flask 框架配合 Jinja2 模板引擎的配置与基础用法。以下是整理出的关键信息：

### 1. 模板技术的背景与 MVC 模型
 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。提供的参考证据全部围绕“环境监测技术”专业，涉及课程标准、教材、课程设置和实训环境等内容[2][5][10][15]，而学生问题指向“电子信息专业课程”，两者不相关，故无法基于现有证据作答。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。所提供的参考证据均围绕“环境监测技术”专业，包含水环境监测、空气监测等课程内容，未涉及电子信息专业的相关信息。 |

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
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "在 Python 中，理解函数的参数可以围绕两个视角展开：**站在调用者角度，知道怎么传参、传什么**；**站在定义者角度，知道如何设计灵活的函数接口**。下面结合参考证据，分层讲解。\n\n---\n\n## 一、先明白“调用函数”的基本规矩\n调用函数时，参数的数量和类型必须匹配。如果数量不对，会报错；类型不兼容，也会报错。\n\n> 调用函数的时候，如果传入的参数数量不对，会报 `TypeError` 的错误，并且 Python 会明确地告诉你"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要理解 Python 函数的参数，可以从“接口封装”的角度入手：**参数是函数与外部交流的唯一入口，定义了调用时需要提供哪些信息**。函数内部的具体实现被隐藏，调用者只需知道传什么参数、能得到什么返回值就行了[4]。下面分层讲解，帮你建立清晰的认知。\n\n---\n\n### 1. 位置参数 —— 最基础的“必填项”\n定义函数时写下的普通参数就是位置参数，调用时必须严格按位置、有且仅有一个地传入对应的值[4]。\n\n例如，定义一个计算平方的函数"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "要理解 Python 函数的参数，可以从“定义方”和“调用方”两个视角来把握，并结合参数的不同类型，逐步建立清晰、可用的认识。\n\n## 1. 先建立“接口”思维\n函数就像一个有“输入”和“输出”的黑盒。定义函数时我们规定好参数的名字、数量和可能的默认值，这就构成了函数的“接口”[4]。调用的人只需要知道：**传入什么参数，会返回什么值**，而不需要关心函数内部的实现细节[4]。\n\n## 2. 掌握最基本的参数类型\n### 2.1 位置参"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 4, "graph_edge_packed_count": 3, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "理解 Python 函数的参数，可以从“接口设计”和“参数类型”两个角度入手，这样既好懂又实用。\n\n### 1. 把参数理解为函数的“接口”\n调用函数时，只要知道该传什么参数、会返回什么值就够了，无需关心内部的复杂逻辑 [4]。这就是封装的好处——参数就是你和函数打交道的“合同”。\n\n### 2. 由“死板”到“灵活”认识参数类型\nPython 的参数设计从最简单的位置参数开始，逐步增加灵活性，你可以按这个顺序掌握：\n\n- **位置参数"}, {"question_group": "REQ-016", "question_id": "Q2_course_quality", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "graph": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 3, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "final_answer_preview": "基于您提供的参考证据，这份关于“新能源汽车驱动电机检修——驱动电机拆装与检测”的教学安排是**合理且结构完整的**。以下从多个维度进行分析：\n\n**1. 教学设计系统全面，逻辑清晰**\n证据[4]显示，教学分析从内容、学情、目标到重难点形成了完整闭环。内容分析明确了驱动电机作为新能源汽车“三大核心部件之一”的重要性，并划分了五个教学模块 [4]。学情分析充分考虑了学生“动手能力较强”但“对驱动电机精密结构了解不足”的特点，为教学策略的制"}, {"question...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.80 | 0.40 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 1.00 | 1.00 | 0.80 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | REQ-026 | 0.80 | 0.60 | 0.60 | 0.60 | -0.20 | -1.00 | 退化 | 0 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.20 | 0.40 | 0.00 | 0.40 | +0.20 | +0.25 | 中性 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.40 | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 1.00 | 1.00 | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.40 | 0.20 | 0.40 | 0.40 | +0.00 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 1.00 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `4` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `0` / `10`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `0` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `0` / `10`。

### 数据缺口与后续任务

- 当前 dev DB 数据集未能构造足够的弱召回样例来证明 P2 完整链路相对 baseline 提升 >= 30%。
- 后续任务候选：
  - `TD-068`: query embedding 为空导致 vector 通道降级为 keyword fallback（已登记，需修）
  - 新增 `REQ-027` (待登记): 增加 P2 弱召回知识覆盖 — 课程标准 / Python 高级特性 / 跨课程先导关系
- Query Understanding 对自然问法的增益证据不足。
- 后续任务候选：
  - 复核 HybridQueryUnderstandingService 在自然问法场景下的 expanded_terms 命中率
  - 增强规则优先 + LLM 低置信触发的样本多样性


## REQ-028 三口径覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign)

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.40 | 0.60 | 0.71 | 0.60 | 装饰器,函数,wrapper |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 0.40 | 0.40 | 0.43 | 0.40 | 装饰器,函数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.40 | 生成器,迭代器 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.20 | 0.40 | 0.38 | 0.20 | 先导,前置 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.40 | 闭包,装饰器 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.40 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.40 | 0.40 | 0.00 | 化学检验工,水环境监测工 |
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
| Q1_decorator_concept | 0.60 | 0.40 | -0.20 | -0.50 | 退化 | 1 |
| Q2_generator_iterator_relationship | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | 0.60 | 0.80 | +0.20 | +0.50 | 正向 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | 1.00 | 0.80 | -0.20 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.20 | 0.40 | +0.20 | +0.25 | 中性 | 0 |
| Q9_course_standard_syllabus | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `6` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `1` 样例达标
- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。

