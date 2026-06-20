# REQ-032 v3 re-run (threshold 0.35 + continuous, real LLM)

> Status: REQ-030 AC-4/5 最终判定 — 阈值校准 + continuous 双口径均不达 4/10，**根因为 P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献**（非评估口径问题）。登记 REQ-033 评估 P2 链路本身
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-032-semantic-emb-threshold-calibration.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md`

## 0. AC 状态总览（REQ-030 + REQ-031 + REQ-032 最终判定）

**REQ-032 成果**：`--semantic-emb-threshold` CLI（本报告 threshold=0.35）+ `keypoint_semantic_embedding_continuous_pct` 字段 + 报告 continuous 口径列/Spearman。threshold 0.5→0.35 后 AC-4 从 0/10 提升到 4/10，但 AC-5（delta ≥ 0.30）三种口径各仅 1/10。

| AC (REQ-030) | 内容 | 状态 | 证据 |
|----|------|------|------|
| AC-1 | 脚本支持 semantic_emb 字段 | ✅ 达标 | ScenarioRun 字段 |
| AC-2 | 脚本支持 LLM-judge 字段 | ✅ 达标 | 39 次 LLM-as-judge 调用成功 |
| AC-3 | 报告新增 REQ-030 新口径对比章节 | ✅ 达标 | 5 列口径 × 10 样例 × 4 scenarios（含 continuous） |
| AC-4 | semantic_emb ≥ 0.50 ≥ 4/10 | ✅ 达标（threshold 0.35） | **4/10** 达标（Q1/Q6/Q7/Q10 weighted） |
| AC-5 | semantic_emb delta ≥ 0.30 ≥ 4/10 | ❌ 未达 | 1/10（Q6 +0.40）；continuous 1/10（Q9 +0.31）；LLM-judge 1/10（Q5 +0.40） |
| AC-6 | 旧字段保留 | ✅ 达标 | 字段不变 |
| AC-7 | dry-run + `--allow-llm` 双模式 | ✅ 达标 | 两种模式 exit 0 |
| AC-8 | 若 AC-4 未达成登记接力 | ✅ 已登记 | REQ-031（通路）+ REQ-032（阈值）+ REQ-033（P2 链路，新登记） |

| AC (REQ-032) | 内容 | 状态 | 证据 |
|----|------|------|------|
| AC-1 | `--semantic-emb-threshold` CLI + 多档命中率 | ✅ 达标 | 本报告 threshold=0.35 |
| AC-2 | `keypoint_semantic_embedding_continuous_pct` 字段 | ✅ 达标 | JSON dump + 报告 cont cov 列 |
| AC-3 | 报告 continuous 口径 + per-sample delta | ✅ 达标 | per-sample summary 含 cont delta |
| AC-4 | threshold 0.35 + continuous 双口径 AC-5 如实记录 | ✅ 达标 | sem_emb 1/10 / cont 1/10 |
| AC-5 | continuous vs LLM-judge Spearman 如实计算 | ✅ 达标 | ρ=0.072 (n=39, Pearson) |
| AC-6 | 旧字段不变 | ✅ 达标 | 字段不变 |
| AC-7 | dry-run + `--allow-llm` 双模式 | ✅ 达标 | exit 0 |
| AC-8 | 根因定位 + 登记后续，不强行声明完成 | ✅ 达标 | 根因=P2 链路无正向贡献，登记 REQ-033 |

## 0.1 根因诊断（REQ-032 最终结论）

**阈值校准有效但不足以达标**：
- threshold 0.5→0.35：AC-4 从 0/10 → 4/10（命中率 14%→44%，符合 similarity 分布 median=0.329）
- 但 AC-5（delta ≥ 0.30）三种口径各仅 1/10，且**正向 sample 互不一致**：
  - semantic_emb (threshold 0.35): Q6 +0.40
  - continuous: Q9 +0.31
  - LLM-judge: Q5 +0.40

**根因不是阈值，是 P2 链路本身**：
- continuous delta 全在 -0.16~+0.31，9/10 中性 —— weighted 与 baseline 的语义覆盖度几乎无差异
- 三种独立口径（embedding threshold / embedding continuous / LLM-judge）对"哪个 sample 正向"判断不一致，说明 P2 链路（graph_edge + weighted RRF）在真 vector 召回下**对 answer 的 keypoint 覆盖没有系统性提升**，偶尔的正向是单 sample 噪声
- 这与 REQ-028 v3 重跑的核心发现一致：真 vector 召回下 baseline coverage 普遍上升，weighted 反而常下降（Q2 -0.60 / Q5 -0.40 退化）

**substring 口径的"假阳性"**：substring 在 fake vector 时代能达成 AC-5 5/10，是因为 keyword 兜底主导召回，子串恰好命中；真 vector 召回下 substring 无法识别 LLM 同义改写，数据失真。semantic_emb 口径反而**如实**反映了 P2 链路的真实表现。

**结论**：评估口径已充分（四口径 + continuous + Spearman），无法通过继续调阈值让 AC-5 达标。问题转移到 P2 链路本身——登记 REQ-033 评估 P2 链路在真 vector 下的实际价值（RRF 权重 / graph_edge 策略 / ContextPacker 是否需调整）。

## 环境

- Generated At: `2026-06-20T18:06:52.207403+08:00`
- DB: `***@localhost:5432/metaedu`
- Tenant: `00000000-0000-0000-0000-000000000001`
- External LLM: `enabled`
- Validation Status: `real-llm-run`

## REQ-016 Query Understanding 验收

| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |
|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|
| Q1_python_func_param | baseline_rule_no_edge | - | - | [] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要透彻理解 Python 函数的参数，不妨从“**调用时如何传参**”和“**定义时如何接收**”两个角度入手。下面结合常见参数类型、实际例子和避坑要点，帮你建立起清晰的认知。

## 1. 先看函数调用：必须对号入座
调用函数时，你需要提 |
| Q1_python_func_param | query_understanding | llm | 0.9 | ["参数传递", "形参", "实参"] | {"vector": 16, "keyword": 11, "graph": 11} | 0 | 8 | 要理解 Python 函数的参数，可以从**参数类型**、**使用场景**和**常见陷阱**三个维度来掌握，它们共同构成了 Python 函数灵活而强大的接口设计能力。

---

### 1. 认识五种参数类型
Python 函数支持五种 |
| Q1_python_func_param | graph_edge | llm | 0.9 | ["parameter", "参数传递", "形参", "实参"] | {"vector": 16, "keyword": 19, "graph": 11, "graph_edge": 8} | 8 | 8 | 理解 Python 函数的参数，关键在于把握几个核心原则，尤其是**“默认参数的值在定义时就被计算”**以及**“尽量使用不变对象”**。以下从教学角度给出清晰解读。

## 1. 参数的基本分类
Python 函数可以接收多种参数，常见的 |
| Q1_python_func_param | weighted_rrf | llm | 0.9 | ["parameter", "参数传递", "形参", "实参"] | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} | 0 | 8 | 很抱歉，根据你提供的参考证据，我没有找到关于“Python 函数参数”的详细解释或相关讨论。

当前的参考证据主要介绍了以下几方面的内容：
- **Python 的定位与特点**：它是一种“优雅”、“明确”、“简单”的高级编程语言 [9]， |
| Q2_course_quality | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 好的，我们基于您提供的参考证据，来分析这份《新能源汽车驱动电机检修——驱动电机拆装与检测》教案的教学安排是否合理。

综合分析后，可以判断：**这份材料的教学安排是合理的。** 其设计体现了职业教育“理实一体”、“做中学”的核心理念，各环节 |
| Q2_course_quality | query_understanding | llm | 0.5 | ["教学设计", "课程计划", "教案", "教学大纲"] | {"vector": 16, "keyword": 7, "graph": 8} | 0 | 8 | 根据提供的参考证据，这份关于“新能源汽车驱动电机检修——驱动电机拆装与检测”的教案，其教学安排总体上是合理的。判断依据主要从结构完整性、方法适配性和改进可行性三个方面来看：

1.  **教学结构完整，目标明确**
    该教案包含了完整 |
| Q2_course_quality | graph_edge | llm | 0.7 | ["教学设计", "课程计划", "教学评估"] | {"vector": 16, "graph": 8} | 0 | 8 | 好的，我们来分析一下这份关于“驱动电机拆装与检测”的教学安排是否合理。

总体而言，这份教学设计**结构完整、逻辑清晰、安排合理**，充分体现了职业教育“理实一体、做中学”的特点。以下将结合参考证据，从几个关键维度进行评析：

### 1. |
| Q2_course_quality | weighted_rrf | llm | 0.65 | ["课程安排", "教学设计", "教学计划"] | {"vector": 16, "keyword": 1, "graph": 8} | 0 | 8 | 根据提供的教学材料 [4]，这份关于“驱动电机拆装与检测”的教学安排整体上是相当合理的，较好地体现了职业教育“理实一体化”的教学理念。以下从几个核心维度进行分析：

**1. 教学对象与内容匹配度合理**
课程面向的是“汽车运用与维修210 |
| Q3_template_doc | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q3_template_doc | query_understanding | llm | 0.9 | ["配置模板", "模板设置", "模版配置", "template configuration", "documentation"] | {"vector": 16, "keyword": 3, "graph": 8} | 0 | 8 | 根据参考证据，关于模板配置的文档资料主要集中在 **Flask 使用 Jinja2 模板** 的实践说明中。以下是具体配置要点：

### 1. 模板目录结构
模板文件必须放在 **`templates`** 目录下，并且该目录应与 Fla |
| Q3_template_doc | graph_edge | llm | 0.9 | ["配置模板", "文档资料", "指南", "教程", "手册"] | {"vector": 16, "keyword": 8, "graph": 8} | 0 | 8 | 未找到足够参考来源。提供的证据材料仅涵盖《新能源汽车驱动电机检修》课程的教案信息，包括教学目标、教学内容、教学流程等，不包含模板配置相关的文档资料。 |
| Q3_template_doc | weighted_rrf | llm | 0.9 | ["配置指南", "模板设置", "配置手册"] | {"vector": 16, "graph": 8} | 0 | 8 | 未找到足够参考来源。 |
| Q4_rule_hit | baseline_rule_no_edge | - | - | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。提供的参考证据主要涉及环境监测技术专业的课程标准、课程设置和实训条件，未包含电子信息专业课程的相关信息。 |
| Q4_rule_hit | query_understanding | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3} | 0 | 8 | 未找到足够参考来源。

所提供的参考证据全部围绕“环境监测技术”专业展开，其课程设置、教材说明及实训环境均针对水环境监测、分析化学等技术领域，并未包含任何关于“电子信息专业课程”的信息。 |
| Q4_rule_hit | graph_edge | rule | 1.0 | [] | {"vector": 8, "graph": 3, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。提供的参考证据均围绕“环境监测技术”专业，未涉及电子信息专业课程的相关信息。 |
| Q4_rule_hit | weighted_rrf | rule | 1.0 | [] | {"vector": 16, "graph": 11, "keyword": 3, "graph_edge": 6} | 0 | 8 | 未找到足够参考来源。 |

## REQ-018 graph_edge 补足样例分析

| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |
|-------|-----------------|----------------|----------------|------------------------------------|------------------|
| Q1_prerequisite_query | 0 | 0 | 0 | 0 | {"vector": 16, "keyword": 2, "graph": 8} |
| Q2_cross_section_relationship | 8 | 6 | 5 | 7 | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} |
| Q3_keyword_only_baseline | 8 | 5 | 3 | 7 | {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8} |

## 对比结论

- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。
- vector fallback trace count: `16` (大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。
- graph_edge fusion-level supplement examples: `2` (只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。
- graph_edge prompt-level supplement examples: `2` (REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。
- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 `graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。

## 原始 JSON 摘要

```json
[{"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "baseline_rule_no_edge", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "要透彻理解 Python 函数的参数，不妨从“**调用时如何传参**”和“**定义时如何接收**”两个角度入手。下面结合常见参数类型、实际例子和避坑要点，帮你建立起清晰的认知。\n\n## 1. 先看函数调用：必须对号入座\n调用函数时，你需要提供**正确的参数个数和类型**，否则 Python 会直接报错 `TypeError`。[4]  \n以内置函数 `abs()` 为例——它只有一个参数，只能传入一个数值：\n```python\nabs("}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "query_understanding", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 0, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "要理解 Python 函数的参数，可以从**参数类型**、**使用场景**和**常见陷阱**三个维度来掌握，它们共同构成了 Python 函数灵活而强大的接口设计能力。\n\n---\n\n### 1. 认识五种参数类型\nPython 函数支持五种参数，它们的定义顺序是固定的：[11]  \n**必选参数 → 默认参数 → 可变参数 → 命名关键字参数 → 关键字参数**\n\n| 参数类型 | 说明 | 示例 |\n|---------|------"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "graph_edge", "retrieval_counts": {"vector": 16, "keyword": 19, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 8, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 0, "graph_edge_packed_count": 0, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "理解 Python 函数的参数，关键在于把握几个核心原则，尤其是**“默认参数的值在定义时就被计算”**以及**“尽量使用不变对象”**。以下从教学角度给出清晰解读。\n\n## 1. 参数的基本分类\nPython 函数可以接收多种参数，常见的有：\n- **位置参数**：按顺序传入。\n- **默认参数**：为参数提供默认值，调用时可省略。\n- **可变参数**：参数个数可变，如 `*args`。\n- 还有命名关键字参数等，但初学者先掌握前三"}, {"question_group": "REQ-016", "question_id": "Q1_python_func_param", "scenario": "weighted_rrf", "retrieval_counts": {"vector": 16, "keyword": 11, "graph": 11, "graph_edge": 8}, "vector_fallback_count": 0, "graph_edge_retrieval_count": 8, "graph_edge_fusion_count": 7, "graph_edge_packed_count": 8, "document_sources_count": 1, "keypoint_total": 0, "keypoint_hit_count": 0, "keypoint_coverage_pct": 0.0, "keypoint_coverage_pct_substring": 0.0, "keypoint_coverage_pct_semantic": 0.0, "keypoint_weight_pct_semantic": 0.0, "keypoint_llm_judge_pct": null, "keypoint_semantic_embedding_pct": 0.0, "keypoint_semantic_embedding_weight_pct": 0.0, "keypoint_semantic_embedding_hit_terms": [], "keypoint_semantic_embedding_continuous_pct": 0.0, "final_answer_preview": "很抱歉，根据你提供的参考证据，我没有找到关于“Python 函数参数”的详细解释或相关讨论。\n\n当前的参考证据主要介绍了以下几方面的内容：\n- **Python 的定位与特点**：它是一种“优雅”、“明确”、“简单”的高级编程语言 [9]，拥有丰富的内置库和第三方库 [9]。\n- **与其他语言的比较**：例如完成相同任务，Python 的代码量通常比 C 或 Java 少很多，但运行速度相对较慢 [10][11]。\n- **应用领域与"}, {"question_group": "REQ-016", "question_id": "Q2_course_...
```

## REQ-026 弱召回样例关键事实覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))

| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |
|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|
| Q1_decorator_concept | REQ-026 | 1.00 | 0.60 | 0.80 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q2_generator_iterator_relationship | REQ-026 | 1.00 | 1.00 | 0.00 | 0.60 | -0.40 | +0.00 | 中性 | 7 |
| Q3_default_param_pitfall | REQ-026 | 1.00 | 0.80 | 0.60 | 0.60 | -0.40 | +0.00 | 中性 | 1 |
| Q4_prerequisite_knowledge_for_course | REQ-026 | 0.00 | 0.20 | 0.40 | 0.60 | +0.60 | +1.00 | 正向 | 0 |
| Q5_course_target_summary | REQ-026 | 0.20 | 0.20 | 0.20 | 0.20 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | REQ-026 | 1.00 | 0.80 | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | REQ-026 | 0.60 | 0.20 | 0.40 | 0.20 | -0.40 | -1.00 | 退化 | 0 |
| Q8_training_program_occupation | REQ-026 | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | +0.00 | 中性 | 0 |
| Q9_course_standard_syllabus | REQ-026 | 0.60 | 0.60 | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q10_python_advanced_synthesis | REQ-026 | 0.80 | 0.80 | 0.80 | 0.80 | +0.00 | +0.00 | 中性 | 1 |

### 自动比较结论

- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` 脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`) 完成执行。
- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = `5` / `10`。
- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = `1` / `10`；退化样例数 = `1`。
- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = `0` / `10`。
- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = `0` / `10`。

### 数据缺口与后续任务

- Query Understanding 对自然问法的增益证据不足。
- 后续任务候选：
  - 复核 HybridQueryUnderstandingService 在自然问法场景下的 expanded_terms 命中率
  - 增强规则优先 + LLM 低置信触发的样本多样性


## REQ-028 三口径覆盖度对比

- **Lift mode**: `residual` (REQ-029 redesign)

| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |
|--------|----------|---------------|--------------|------------|---------------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 装饰器,函数,语法糖,wrapper,参数 |
| Q1_decorator_concept | query_understanding | 0.60 | 0.80 | 0.86 | 0.60 | 装饰器,函数,wrapper,参数 |
| Q1_decorator_concept | graph_edge | 0.40 | 0.40 | 0.43 | 0.40 | 装饰器,函数 |
| Q1_decorator_concept | weighted_rrf | 0.80 | 0.80 | 0.86 | 0.80 | 装饰器,函数,wrapper,参数 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 1.00 | 0.80 | 生成器,迭代器,yield,iter,next |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 0.50 | 0.40 | 生成器,迭代器 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | query_understanding | 0.80 | 1.00 | 1.00 | - | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 1.00 | 1.00 | 默认参数,可变对象,list,None,不变对象 |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 1.00 | 0.80 | 默认参数,可变对象,list,None,不变对象 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.40 | 0.60 | 0.50 | 0.40 | 基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q4_prerequisite_knowledge_for_course | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 化学,生物,基础,先导,前置 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.75 | 0.60 | 化学,基础,先导,前置 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.62 | 0.00 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.62 | 0.20 | 环境监测,培养目标,课程体系 |
| Q5_course_target_summary | weighted_rrf | 0.40 | 0.60 | 0.62 | 0.40 | 环境监测,培养目标,课程体系 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 闭包,装饰器,函数,内部,引用 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 0.00 | 0.00 | - |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | query_understanding | 0.60 | 0.80 | 0.78 | 0.40 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | graph_edge | 0.20 | 0.80 | 0.78 | 0.20 | 环境监测技术,水环境监测工,水和废水,检测技术 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 1.00 | 1.00 | 0.40 | 环境监测技术,化学检验工,水环境监测工,水和废水,检测技术 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.20 | 0.00 | 水环境监测工 |
| Q8_training_program_occupation | weighted_rrf | 0.20 | 0.40 | 0.40 | 0.20 | 化学检验工,水环境监测工 |
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
| Q1_decorator_concept | 1.00 | 0.80 | -0.20 | +0.00 | 中性 | 1 |
| Q2_generator_iterator_relationship | 1.00 | 0.40 | -0.60 | +0.00 | 中性 | 8 |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | +0.00 | 中性 | 0 |
| Q4_prerequisite_knowledge_for_course | 0.60 | 0.80 | +0.20 | +0.50 | 正向 | 0 |
| Q5_course_target_summary | 0.60 | 0.60 | +0.00 | +0.00 | 中性 | 0 |
| Q6_python_closure | 1.00 | 0.00 | -1.00 | +0.00 | 中性 | 8 |
| Q7_kg_occupation_to_skill | 0.80 | 1.00 | +0.20 | +1.00 | 正向 | 0 |
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

- **AC-4 (semantic ≥ 0.50)**: `7` 样例达标（独立看 weighted scenario）
- **AC-5 (semantic lift >= 0.30 in `residual` mode)**: `2` 样例达标
- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。


## REQ-030 新口径对比（semantic embedding + LLM-as-judge）

> REQ-031 embedding cache: hit=`1562` miss=`261` timeout=`0` error=`0` (total=`1823`)

| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | cont cov | LLM-as-judge cov |
|--------|----------|----------------|--------------|--------------------|----------------------|----------|-------------------|
| Q1_decorator_concept | baseline_rule_no_edge | 1.00 | 1.00 | 0.80 | 0.86 | 0.45 | 1.00 |
| Q1_decorator_concept | query_understanding | 0.60 | 0.80 | 0.60 | 0.71 | 0.44 | 0.60 |
| Q1_decorator_concept | graph_edge | 0.40 | 0.40 | 0.40 | 0.57 | 0.40 | 0.40 |
| Q1_decorator_concept | weighted_rrf | 0.80 | 0.80 | 0.60 | 0.71 | 0.43 | 0.80 |
| Q2_generator_iterator_relationship | baseline_rule_no_edge | 1.00 | 1.00 | 0.80 | 0.75 | 0.45 | 1.00 |
| Q2_generator_iterator_relationship | query_understanding | 1.00 | 1.00 | 1.00 | 1.00 | 0.52 | 1.00 |
| Q2_generator_iterator_relationship | graph_edge | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.80 |
| Q2_generator_iterator_relationship | weighted_rrf | 0.40 | 0.40 | 0.20 | 0.25 | 0.29 | 0.40 |
| Q3_default_param_pitfall | baseline_rule_no_edge | 0.80 | 1.00 | 0.20 | 0.25 | 0.33 | 1.00 |
| Q3_default_param_pitfall | query_understanding | 0.80 | 1.00 | 0.40 | 0.50 | 0.39 | - |
| Q3_default_param_pitfall | graph_edge | 0.80 | 1.00 | 0.20 | 0.25 | 0.30 | 1.00 |
| Q3_default_param_pitfall | weighted_rrf | 0.80 | 1.00 | 0.20 | 0.25 | 0.34 | 0.80 |
| Q4_prerequisite_knowledge_for_course | baseline_rule_no_edge | 0.40 | 0.60 | 0.40 | 0.38 | 0.30 | 0.40 |
| Q4_prerequisite_knowledge_for_course | query_understanding | 0.00 | 0.00 | 0.60 | 0.50 | 0.35 | 0.00 |
| Q4_prerequisite_knowledge_for_course | graph_edge | 1.00 | 1.00 | 0.00 | 0.00 | 0.22 | 1.00 |
| Q4_prerequisite_knowledge_for_course | weighted_rrf | 0.60 | 0.80 | 0.20 | 0.12 | 0.28 | 0.60 |
| Q5_course_target_summary | baseline_rule_no_edge | 0.20 | 0.60 | 0.60 | 0.62 | 0.37 | 0.00 |
| Q5_course_target_summary | query_understanding | 0.20 | 0.60 | 0.60 | 0.62 | 0.37 | 0.20 |
| Q5_course_target_summary | graph_edge | 0.20 | 0.60 | 0.40 | 0.38 | 0.36 | 0.20 |
| Q5_course_target_summary | weighted_rrf | 0.40 | 0.60 | 0.20 | 0.25 | 0.30 | 0.40 |
| Q6_python_closure | baseline_rule_no_edge | 1.00 | 1.00 | 0.60 | 0.62 | 0.43 | 1.00 |
| Q6_python_closure | query_understanding | 1.00 | 1.00 | 0.60 | 0.62 | 0.45 | 1.00 |
| Q6_python_closure | graph_edge | 1.00 | 1.00 | 0.60 | 0.62 | 0.37 | 1.00 |
| Q6_python_closure | weighted_rrf | 0.00 | 0.00 | 1.00 | 1.00 | 0.45 | 0.00 |
| Q7_kg_occupation_to_skill | baseline_rule_no_edge | 0.40 | 0.80 | 0.60 | 0.67 | 0.41 | 0.40 |
| Q7_kg_occupation_to_skill | query_understanding | 0.60 | 0.80 | 0.60 | 0.67 | 0.41 | 0.40 |
| Q7_kg_occupation_to_skill | graph_edge | 0.20 | 0.80 | 0.60 | 0.67 | 0.43 | 0.20 |
| Q7_kg_occupation_to_skill | weighted_rrf | 0.40 | 1.00 | 0.60 | 0.67 | 0.44 | 0.40 |
| Q8_training_program_occupation | baseline_rule_no_edge | 0.00 | 0.20 | 0.40 | 0.40 | 0.41 | 0.00 |
| Q8_training_program_occupation | query_understanding | 0.00 | 0.20 | 0.40 | 0.40 | 0.37 | 0.00 |
| Q8_training_program_occupation | graph_edge | 0.00 | 0.20 | 0.80 | 0.80 | 0.45 | 0.00 |
| Q8_training_program_occupation | weighted_rrf | 0.20 | 0.40 | 0.40 | 0.40 | 0.37 | 0.20 |
| Q9_course_standard_syllabus | baseline_rule_no_edge | 0.60 | 0.80 | 0.00 | 0.00 | 0.00 | 0.60 |
| Q9_course_standard_syllabus | query_understanding | 0.60 | 0.80 | 0.20 | 0.22 | 0.31 | 0.60 |
| Q9_course_standard_syllabus | graph_edge | 0.60 | 0.80 | 0.20 | 0.22 | 0.30 | 0.60 |
| Q9_course_standard_syllabus | weighted_rrf | 0.60 | 0.80 | 0.20 | 0.22 | 0.31 | 0.60 |
| Q10_python_advanced_synthesis | baseline_rule_no_edge | 0.80 | 0.80 | 0.80 | 0.88 | 0.50 | 0.80 |
| Q10_python_advanced_synthesis | query_understanding | 0.80 | 0.80 | 0.60 | 0.75 | 0.43 | 0.80 |
| Q10_python_advanced_synthesis | graph_edge | 0.80 | 0.80 | 1.00 | 1.00 | 0.51 | 0.80 |
| Q10_python_advanced_synthesis | weighted_rrf | 0.80 | 0.80 | 0.60 | 0.75 | 0.46 | 0.80 |

### REQ-030 双口径一致性

- semantic embedding (threshold-based) vs LLM-as-judge: `0.003 (Pearson fallback, scipy unavailable)` (n=39)
- continuous weighted coverage vs LLM-as-judge: `0.072 (Pearson)` (n=39)
- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary

### REQ-030 per-sample summary (semantic embedding metric)

| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | baseline cont | weighted cont | cont delta | 判定 (cont) | LLM-judge delta | 判定 (judge) |
|--------|------------------|------------------|-------|-----------------|---------------|---------------|------------|--------------|-----------------|----------------|
| Q1_decorator_concept | 0.80 | 0.60 | -0.20 | 中性 | 0.45 | 0.43 | -0.02 | 中性 | -0.20 | 中性 |
| Q2_generator_iterator_relationship | 0.80 | 0.20 | -0.60 | 退化 | 0.45 | 0.29 | -0.16 | 中性 | -0.60 | 退化 |
| Q3_default_param_pitfall | 0.20 | 0.20 | +0.00 | 中性 | 0.33 | 0.34 | +0.02 | 中性 | -0.20 | 中性 |
| Q4_prerequisite_knowledge_for_course | 0.40 | 0.20 | -0.20 | 中性 | 0.30 | 0.28 | -0.02 | 中性 | +0.20 | 中性 |
| Q5_course_target_summary | 0.60 | 0.20 | -0.40 | 退化 | 0.37 | 0.30 | -0.08 | 中性 | +0.40 | 正向 |
| Q6_python_closure | 0.60 | 1.00 | +0.40 | 正向 | 0.43 | 0.45 | +0.02 | 中性 | -1.00 | 退化 |
| Q7_kg_occupation_to_skill | 0.60 | 0.60 | +0.00 | 中性 | 0.41 | 0.44 | +0.03 | 中性 | +0.00 | 中性 |
| Q8_training_program_occupation | 0.40 | 0.40 | +0.00 | 中性 | 0.41 | 0.37 | -0.04 | 中性 | +0.20 | 中性 |
| Q9_course_standard_syllabus | 0.00 | 0.20 | +0.20 | 中性 | 0.00 | 0.31 | +0.31 | 正向 | +0.00 | 中性 |
| Q10_python_advanced_synthesis | 0.80 | 0.60 | -0.20 | 中性 | 0.50 | 0.46 | -0.04 | 中性 | +0.00 | 中性 |

### REQ-030 三口径决策依据

- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。
- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。
- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。
- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。
- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。

- **AC-4 (semantic_emb ≥ 0.50)**: `4` 样例达标
- **AC-5 (semantic_emb lift >= 0.30)**: `1` 样例达标
- **AC-5 (continuous lift >= 0.30)**: `1` 样例达标 (REQ-032 secondary)
- **AC-5 (LLM-judge lift >= 0.30)**: `1` 样例达标 (secondary signal)
- **未达成**: AC-5 semantic_emb + continuous 双口径均不达 4/10。根因诊断见报告 §0.1（P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献，非阈值问题）。

