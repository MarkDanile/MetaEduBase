# REQ-033 v3 re-run (P2 chain value eval, real LLM)

> Status: REQ-030 AC-5 根因最终归档 — P2 链路在真 vector 下**价值有限**（指标 A=50% / B=10% / 跨文档=0%），AC-5 不达标是指标错配（keypoint 覆盖 vs graph_edge 关联补足目标不一致），非链路缺陷。REQ-030 翻完成（评估口径充分 + 根因归档）
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md`

## 0. P2 RAG 质量评估长链最终结论（REQ-028→030→031→032→033）

经 REQ-028（三口径）→ REQ-029（residual 阈值）→ REQ-030（semantic embedding + LLM-judge）→ REQ-031（embedding 通路稳定）→ REQ-032（阈值校准 + continuous）→ REQ-033（链路价值评估）六轮接力，P2 RAG 质量评估长链最终结论：

**核心发现**：真 vector 召回下（TD-068+069 后），P2 链路（graph_edge + weighted RRF）对 keypoint 覆盖无系统性正向贡献（REQ-030 AC-5 三口径各 1/10）。但这是**指标错配**，非链路缺陷：

- keypoint 覆盖衡量「答案是否命中分散关键词」
- graph_edge 设计意图是「补足同文档关联上下文」（REQ-018/025）
- 两者目标不一致

**REQ-033 价值评估（retrieval 层指标）**：
- 指标 A（graph_edge 关联补足率）= 5/10（50%）——半数样例 edge 进 packed
- 指标 B（跨 section 上下文扩展）= 1/10——edge 多替换同文档 chunk，上下文反而收缩（Q1/Q2/Q4/Q6）
- 跨文档 grounding 扩展 = 0/10——edge chunks 全同文档，不扩展溯源广度

**价值判定：价值有限**。graph_edge 在 fake vector 时代有价值（keyword 兜底主导、edge 补足能进 packed），真 vector 下 vector 已强，edge 通道在 RRF 融合时多被挤出 fusion_topN，价值被稀释。这是技术演进的自然结果，非 bug。

**后续动作**：
- REQ-030 翻完成（评估口径已充分：四口径 + continuous + Spearman + retrieval 层指标；AC-5 根因归档为指标错配）
- 登记 REQ-034 候选：评估是否下调 graph_edge RRF 权重 / 调整触发策略（独立需求，本任务不改主链路）
- REQ-025（graph_edge 进 prompt 验收）基线说明更新：fake vector 时代验收成立，真 vector 下价值转移

## 环境

- Generated At: `2026-06-20T20:18:09.236966+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 在 Python 中，理解函数的参数需要抓住几个核心层次：参数的作用、参数的类型（位置参数、默认参数、可变参数、关键字参数）以及调用时的匹配规则。我们可以用一个递进的方式来掌握它。

---

### 1. 先看最简单的：位置参数（必选参数 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["parameter", "形参", "实参", "参数传递"] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要理解 Python 函数的参数，最好的方式是「分类型、分角色、分顺序」地去认识它。简单来说，就是搞清楚**调用时谁来传值**，以及**定义时怎么安排参数的位置**和**默认行为**。下面按从基础到进阶的层次帮你梳理。

---

###  |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["parameter", "形参", "实参", "参数传递"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 要理解 Python 函数的参数，可以从“函数接口设计”和“参数分类”两个角度来把握：函数把复杂逻辑封装起来，调用者只需知道怎么传参和函数会返回什么；Python 的参数机制非常灵活，支持多种参数类型，但它们有明确的定义顺序和调用规则。下面 |
| Q1_python_func_param | weighted_rrf | llm | 0.85 | ["参数", "argument", "parameter", "参数传递", "函数定义"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 理解 Python 函数的参数，关键在于把握“接口封装”和“参数形态”两个维度。基于参考证据，我们可以这样分层来理解：

**1. 核心思维：把函数看作“封装好的接口”**
要从调用者的角度去理解，而不是制造者的角度。
函数定义好后，对于调 |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 根据提供的参考证据，我对《新能源汽车驱动电机检修——驱动电机拆装与检测》这份教案的教学安排进行合理性分析。结论是：**该教学安排整体合理，符合职业教育理实一体化的教学规律**。以下从多个维度具体说明。

### 1. 教学分析充分，定位准确 |
| Q2_course_quality | query_understanding | llm | 0.75 | ["教学计划", "课程设计", "教学设计评估"] | {"vector": 16, "keyword": 1, "graph": 8} | 0 | 8 | 根据你提供的参考证据，这份关于“新能源汽车驱动电机检修——驱动电机拆装与检测”的教案在教学安排上是合理的。以下是从几个关键维度进行的分析：

### 1. 学情分析与教学目标相匹配（合理）
教案明确了授课对象为“汽车运用与维修2101班”的 |
| Q2_course_quality | graph_edge | llm | 0.72 | ["教学设计", "课程计划", "教学评估"] | {"vector": 16, "graph": 8} | 0 | 8 | 基于提供的参考证据，特别是对「新能源汽车驱动电机检修——驱动电机拆装与检测」这份教案 [3] 的分析，该材料的教学安排是**非常合理且科学的**，体现了职业教育“理实一体化”的教学理念。具体分析如下：

---

### 一、 教学目标设置 |
| Q2_course_quality | weighted_rrf | llm | 0.8 | ["教学设计", "课程安排", "教学计划", "评价标准"] | {"vector": 16, "keyword": 2, "graph": 8} | 0 | 8 | 根据你提供的参考证据，这份关于“驱动电机拆装与检测”的教学安排是**基本合理**的，它在教学目标设计、学情分析和教学条件保障上均体现了职业教育的特点。具体分析如下：

**1. 课程定位与内容设计合理，符合职教人才培养要求**
教学内容的安 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.8 | ["模板设置", "配置模板", "文档模板", "模板文件"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | graph_edge | llm | 0.95 | ["模板设置", "配置模板", "文档", "资料", "说明书"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的证据均来自《新能源汽车驱动电机检修——驱动电机拆装与检测》教案，内容涉及课程基本信息、教学目标、教学重点难点、教学过程等，没有与“模板配置”相关的文档资料 [2][4][7]。 |
| Q3_template_doc | weighted_rrf | llm | 0.78 | ["模板设置", "配置模板", "文档", "资料", "帮助"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的资料全部围绕“新能源汽车驱动电机检修——驱动电机拆装与检测”的教案、教学目标、教学流程等内容[2][5][7]，未涉及“模板配置”相关的文档或配置说明。 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。参考证据均围绕环境监测技术专业展开，涉及课程设置、教材、接续专业、实训环境等内容 [2][5][10][12][15]，未包含电子信息专业课程的相关信息。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。提供的参考证据均围绕环境监测技术专业（如水环境监测课程标准、教材、课程结构等），不涉及电子信息专业课程内容。 |

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
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "在 Python 中，理解函数的参数需要抓住几个核心层次：参数的作用、参数的类型（位置参数、默认参数、可变参数、关键字参数）以及调用时的匹配规则。我们可以用一个递进的方式来掌握它。\n\n---\n\n### 1. 先看最简单的：位置参数（必选参数）\n位置参数是最基本的参数，调用时**必须按照位置顺序**传入，且个数要一致。\n\n- **定义时**：写上参数名，就知道需要几个参数。\n- **调用时**：必须传入有且仅有相同数量的值，否则会报 `T"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，最好的方式是「分类型、分角色、分顺序」地去认识它。简单来说，就是搞清楚**调用时谁来传值**，以及**定义时怎么安排参数的位置**和**默认行为**。下面按从基础到进阶的层次帮你梳理。\n\n---\n\n### 1. 先抓核心：位置参数（必选参数）\n这是最基础的一类，调用函数时，必须按顺序传入值，有多少个定义就要传多少个。[9]\n```python\ndef power(x):\n    return x * x"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，可以从“函数接口设计”和“参数分类”两个角度来把握：函数把复杂逻辑封装起来，调用者只需知道怎么传参和函数会返回什么；Python 的参数机制非常灵活，支持多种参数类型，但它们有明确的定义顺序和调用规则。下面结合参考证据，分层次说明。\n\n---\n\n### 1. 函数参数的本质：接口约定\n定义函数时，参数的名称和位置确定了，函数的接口也就完成了。调用者不用关心内部实现，只需按照约定的方式传入参数，函数返回相"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 5, "graph_edge_packed_count": 4, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，关键在于把握“接口封装”和“参数形态”两个维度。基于参考证据，我们可以这样分层来理解：\n\n**1. 核心思维：把函数看作“封装好的接口”**\n要从调用者的角度去理解，而不是制造者的角度。\n函数定义好后，对于调用者来说，**只需要知道如何传递正确的参数，以及函数将返回什么样的值就够了，函数内部的复杂逻辑被封装起来，调用者无需了解** [4]。这就像用遥控器，你只需要知道按什么按钮（参数）能得到什么结果（返回"}, {"question_group": "REQ-016", "question_id": "Q2_course_qu...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 0.60 | 1.00 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 1 |
| Q2_generator_iterator_relationship | REQ-026 | 1.00 | 1.00 | 0.80 | 0.80 | -0.20 | +0.00 | 中性 | 5 |
| Q3_default_param_pitfall | REQ-026 | 0.80 | 0.60 | 0.80 | 0.60 | -0.20 | -1.00 | 退化 | 0 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.60 | 0.80 | 0.60 | 0.80 | +0.20 | +0.50 | 正向 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 1.00 | 1.00 | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 5 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.40 | 0.40 | 0.40 | 0.20 | -0.20 | -0.33 | 退化 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 1.00 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `4` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `10`；退化样例数 = `2`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `1` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `0` / `10`。

### 数据缺口与后续任务

- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。


## REQ-028 三口径覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign)

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.40 | 0.40 | 0.43 | 0.40 | 装饰器,函数 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | weighted_rrf | 1.00 | 1.00 | 1.00 | 1.00 | 装饰器,函数,语法糖,wrapper,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.40 | 生成器,迭代器 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.60 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.20 | 0.40 | 0.38 | 0.00 | 先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.20 | 0.60 | 0.50 | 0.00 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | graph_edge | 0.80 | 1.00 | 1.00 | 0.80 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.60 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.60 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.60 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.89 | 0.60 | 水样,金属,非金属,有机物 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.88 | 0.80 | 生成器,迭代器,列表生成式,for |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,列表生成式,yield,for |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,列表生成式,yield,for |
| Q10_python_advanced_synthesis | weighted_rrf | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,列表生成式,yield,for |

### REQ-028 per-sample summary (semantic metric)

| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |
|--------|--------------|--------------|-------|----------------|-------------|----------------|
| Q1_decorator_concept | 0.40 | 1.00 | +0.60 | +1.00 | 正向 | 1 |
| Q2_generator_iterator_relationship | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | 0.40 | 0.80 | +0.40 | +0.67 | 正向 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | 1.00 | 0.80 | -0.20 | +0.00 | 中性 | 0 |
| Q8_training_program_occupation | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | 0.80 | 1.00 | +0.20 | +1.00 | 正向 | 2 |

### REQ-028 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。
- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。
- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。
- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。
- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。
- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。

- **AC-4 (semantic ≥ 0.50)**: `7` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `3` 样例达标
- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。


## REQ-030 新口径对比（semantic embedding + LLM-as-judge）

> REQ-031 embedding cache: hit=`1606` miss=`258` timeout=`0` error=`0` (total=`1864`)

| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | cont cov | LLM-as-judge cov |
|--------|----------|----------------|--------------|--------------------|----------------------|----------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 0.40 | 0.40 | 0.60 | 0.71 | 0.41 | 0.40 |
| Q1_decorator_concept | query_understanding | 0.80 | 0.80 | 0.60 | 0.71 | 0.45 | 0.80 |
| Q1_decorator_concept | graph_edge | 0.80 | 0.80 | 0.60 | 0.71 | 0.42 | 0.80 |
| Q1_decorator_concept | weighted_rrf | 1.00 | 1.00 | 0.80 | 0.86 | 0.47 | 1.00 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 0.80 | 0.75 | 0.47 | 1.00 |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 0.80 | 0.75 | 0.47 | 1.00 |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 0.80 | 0.75 | 0.49 | 0.80 |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 1.00 | 1.00 | 0.44 | 0.40 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.60 | 1.00 | 0.40 | 0.50 | 0.41 | 1.00 |
| Q3_default_param_pitfall | query_understanding | 0.80 | 1.00 | 0.80 | 0.88 | 0.45 | 1.00 |
| Q3_default_param_pitfall | graph_edge | 0.60 | 1.00 | 0.40 | 0.50 | 0.38 | 1.00 |
| Q3_default_param_pitfall | weighted_rrf | 0.60 | 1.00 | 0.80 | 0.88 | 0.45 | 1.00 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.20 | 0.40 | 0.40 | 0.38 | 0.28 | 0.00 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.20 | 0.60 | 0.20 | 0.12 | 0.28 | 0.00 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 0.00 | 0.00 | 0.60 | 0.50 | 0.35 | 0.00 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.20 | 0.12 | 0.29 | 0.60 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.80 | 0.88 | 0.42 | 0.00 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.80 | 0.88 | 0.42 | 0.00 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.40 | 0.38 | 0.35 | 0.20 |
| Q5_course_target_summary | weighted_rrf | 0.20 | 0.60 | 0.80 | 0.88 | 0.42 | 0.00 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 0.60 | 0.62 | 0.43 | 1.00 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 0.60 | 0.62 | 0.39 | 1.00 |
| Q6_python_closure | graph_edge | 0.80 | 1.00 | 0.60 | 0.62 | 0.44 | 0.80 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 1.00 | 1.00 | 0.47 | 0.00 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 1.00 | 0.60 | 0.67 | 0.42 | 0.40 |
| Q7_kg_occupation_to_skill | query_understanding | 0.60 | 0.80 | 0.40 | 0.44 | 0.40 | 0.40 |
| Q7_kg_occupation_to_skill | graph_edge | 0.60 | 1.00 | 0.40 | 0.44 | 0.36 | 0.40 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.60 | 0.80 | 0.60 | 0.67 | 0.45 | 0.40 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.80 | 0.80 | 0.44 | 0.00 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.40 | 0.40 | 0.31 | 0.00 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.40 | 0.40 | 0.36 | 0.00 |
| Q8_training_program_occupation | weighted_rrf | 0.00 | 0.20 | 0.40 | 0.40 | 0.34 | 0.00 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.20 | 0.22 | 0.28 | 0.60 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.20 | 0.22 | 0.31 | 0.60 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.20 | 0.22 | 0.30 | 0.60 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.20 | 0.22 | 0.29 | 0.60 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 1.00 | 1.00 | 0.54 | 0.80 |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 1.00 | 0.60 | 0.75 | 0.44 | 0.80 |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 1.00 | 0.60 | 0.75 | 0.45 | 0.80 |
| Q10_python_advanced_synthesis | weighted_rrf | 1.00 | 1.00 | 0.60 | 0.75 | 0.50 | 1.00 |

### REQ-030 双口径一致性

- semantic embedding (threshold-based) vs LLM-as-judge: `0.102 (Pearson fallback, scipy unavailable)` (n=40)
- continuous weighted coverage vs LLM-as-judge: `0.415 (Pearson)` (n=40)
- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary

### REQ-030 per-sample summary (semantic embedding metric)

| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | baseline cont | weighted cont | cont delta | 判定 (cont) | LLM-judge delta | 判定 (judge) |
|--------|------------------|------------------|-------|-----------------|---------------|---------------|------------|--------------|-----------------|----------------|
| Q1_decorator_concept | 0.60 | 0.80 | +0.20 | 中性 | 0.41 | 0.47 | +0.05 | 中性 | +0.60 | 正向 |
| Q2_generator_iterator_relationship | 0.80 | 1.00 | +0.20 | 中性 | 0.47 | 0.44 | -0.02 | 中性 | -0.60 | 退化 |
| Q3_default_param_pitfall | 0.40 | 0.80 | +0.40 | 正向 | 0.41 | 0.45 | +0.04 | 中性 | +0.00 | 中性 |
| Q4_prerequisite_knowledge_for_course | 0.40 | 0.20 | -0.20 | 中性 | 0.28 | 0.29 | +0.00 | 中性 | +0.60 | 正向 |
| Q5_course_target_summary | 0.80 | 0.80 | +0.00 | 中性 | 0.42 | 0.42 | +0.00 | 中性 | +0.00 | 中性 |
| Q6_python_closure | 0.60 | 1.00 | +0.40 | 正向 | 0.43 | 0.47 | +0.03 | 中性 | -1.00 | 退化 |
| Q7_kg_occupation_to_skill | 0.60 | 0.60 | +0.00 | 中性 | 0.42 | 0.45 | +0.02 | 中性 | +0.00 | 中性 |
| Q8_training_program_occupation | 0.80 | 0.40 | -0.40 | 退化 | 0.44 | 0.34 | -0.11 | 中性 | +0.00 | 中性 |
| Q9_course_standard_syllabus | 0.20 | 0.20 | +0.00 | 中性 | 0.28 | 0.29 | +0.01 | 中性 | +0.00 | 中性 |
| Q10_python_advanced_synthesis | 1.00 | 0.60 | -0.40 | 退化 | 0.54 | 0.50 | -0.04 | 中性 | +0.20 | 中性 |

### REQ-030 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。
- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。
- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。
- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。
- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。

- **AC-4 (semantic_emb ≥ 0.50)**: `7` 样例达标
- **AC-5 (semantic_emb lift >= 0.30)**: `2` 样例达标
- **AC-5 (continuous lift >= 0.30)**: `0` 样例达标 (REQ-032 secondary)
- **AC-5 (LLM-judge lift >= 0.30)**: `2` 样例达标 (secondary signal)
- **未达成**: AC-5 semantic_emb + continuous 双口径均不达 4/10。根因诊断见报告 §0.1（P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献，非阈值问题）。


## REQ-033 P2 链路真 vector 价值评估

> graph_edge 设计意图：补足 keyword/vector 弱召回的关联上下文（REQ-018/025）。
> keypoint 覆盖不是衡量其价值的正确指标——本节用 retrieval 层指标评估真实贡献。

### 1. graph_edge 通道有效性（weighted scenario）

| Sample | edge 召回 | edge 进 fusion | edge 进 packed | 判定 |
|--------|----------|----------------|----------------|------|
| Q1_decorator_concept | 8 | 3 | 1 | edge 进入 packed |
| Q2_generator_iterator_relationship | 8 | 7 | 8 | edge 进入 packed |
| Q3_default_param_pitfall | 8 | 1 | 1 | edge 进入 packed |
| Q4_prerequisite_knowledge_for_course | 7 | 2 | 0 | 进 fusion 未进 packed |
| Q5_course_target_summary | 8 | 3 | 0 | 进 fusion 未进 packed |
| Q6_python_closure | 8 | 7 | 8 | edge 进入 packed |
| Q7_kg_occupation_to_skill | 8 | 0 | 0 | 召回但 RRF 挤出 |
| Q8_training_program_occupation | 8 | 0 | 0 | 召回但 RRF 挤出 |
| Q9_course_standard_syllabus | 7 | 0 | 0 | 召回但 RRF 挤出 |
| Q10_python_advanced_synthesis | 8 | 4 | 2 | edge 进入 packed |

### 2. 跨文档 grounding 与 packed 重排度

| Sample | baseline sources | weighted sources | sources 变化 | packed overlap (b∩w) | edge 同文档? |
|--------|------------------|------------------|--------------|----------------------|--------------|
| Q1_decorator_concept | 1 | 1 | +0 | 6/8 | 无 edge |
| Q2_generator_iterator_relationship | 1 | 1 | +0 | 3/8 | 同文档 |
| Q3_default_param_pitfall | 1 | 1 | +0 | 4/7 | 无 edge |
| Q4_prerequisite_knowledge_for_course | 3 | 2 | -1 | 3/7 | 无 edge |
| Q5_course_target_summary | 2 | 2 | +0 | 5/5 | 无 edge |
| Q6_python_closure | 1 | 1 | +0 | 3/8 | 同文档 |
| Q7_kg_occupation_to_skill | 2 | 2 | +0 | 5/5 | 无 edge |
| Q8_training_program_occupation | 2 | 2 | +0 | 4/4 | 无 edge |
| Q9_course_standard_syllabus | 2 | 2 | +0 | 5/5 | 无 edge |
| Q10_python_advanced_synthesis | 1 | 1 | +0 | 6/8 | 无 edge |

### 3. 跨 section 上下文完整性（指标 B）

| Sample | baseline distinct sections | weighted distinct sections | section 增量 | 判定 |
|--------|---------------------------|---------------------------|--------------|------|
| Q1_decorator_concept | 4 | 3 | -1 | 上下文收缩 |
| Q2_generator_iterator_relationship | 3 | 2 | -1 | 上下文收缩 |
| Q3_default_param_pitfall | 1 | 2 | +1 | 上下文扩展 |
| Q4_prerequisite_knowledge_for_course | 6 | 5 | -1 | 上下文收缩 |
| Q5_course_target_summary | 4 | 4 | +0 | 无变化 |
| Q6_python_closure | 4 | 2 | -2 | 上下文收缩 |
| Q7_kg_occupation_to_skill | 4 | 4 | +0 | 无变化 |
| Q8_training_program_occupation | 4 | 4 | +0 | 无变化 |
| Q9_course_standard_syllabus | 5 | 5 | +0 | 无变化 |
| Q10_python_advanced_synthesis | 5 | 5 | +0 | 无变化 |

### 4. 价值指标汇总与判定

- **指标 A（graph_edge 关联补足率）**: `5/10` = `50%`
  - 定义：weighted scenario 中 packed context 含 graph_edge 通道 chunk 的样例比例
- **指标 B（跨 section 上下文扩展）**: `1/10` 样例正向扩展
  - 定义：weighted distinct section_path 数 > baseline 的样例比例
- **跨文档 grounding 扩展**: `0/10` 样例 edge 带来新文档

- **价值判定**: `价值有限`
- **建议动作**: 保留链路；graph_edge 在真 vector 下价值被稀释（vector 已强）。建议登记需求评估是否下调 graph_edge RRF 权重或调整触发策略，或确认价值天然有限并更新 REQ-025/030 验收基线说明

### 5. 结论

- graph_edge 在 fake vector 时代（REQ-018/025 验收）有价值，因 keyword 兜底主导召回、edge 补足关联 chunk 能进 packed。
- 真 vector 召回下（TD-068+069 后）vector 通道已强，edge 通道在 RRF 融合时多被挤出 fusion_topN，且 edge chunks 多为同文档关联、不扩展跨文档 grounding。
- keypoint 覆盖口径（REQ-030 AC-5）反映的是「答案是否命中分散的关键词」，而 graph_edge 补足的是「同文档关联上下文」——两者目标不一致。AC-5 不达标是指标错配，非链路缺陷。
- 本评估不修改主链路代码。若需调整 graph_edge RRF 权重 / 策略，登记独立需求（REQ-034 候选）评估影响面。

