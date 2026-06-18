# REQ-028 Spec: P2 弱召回自动质量比较口径改造

> Status: 🟣 Shaping
> Created: 2026-06-18
> Source: REQ-027 follow-up
> Requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-18-req-028-auto-quality-metric-plan.md`

## 1. Problem Statement

REQ-027 真 PG + `--allow-llm` 报告（10 样例）质量层结论 `1/10` (10%)。诊断：Q8 weighted_rrf baseline coverage 已 0.80 → **数据其实够**；问题在自动覆盖度口径（子串匹配 + 真实 LLM 长答案同义改写）。

具体反例：
- `Q1_decorator_concept expected_keypoints=["装饰器","函数","wrapper","语法糖","@"]` → LLM 用 "内部函数 / 包装器 / 被装饰的函数" 替换 "wrapper / 函数" → 子串只命中 1/5（"函数"）。
- `Q6_python_closure expected_keypoints=["闭包","装饰器","函数","内部","引用"]` → LLM 答案用 "嵌套函数 / 外层引用" → 子串全 0。
- `Q2_generator_iterator` → LLM 答案含 "yield / 迭代 / for 循环 / 生成器函数" 完整内容 → 子串只命中 2/5。

仅靠子串匹配无法识别同义改写，导致 P2 链路质量被系统性低估。

## 2. Goal

把子串匹配升级为**多维度覆盖度口径**，使 P2 能力评估更接近真实语义命中。

## 3. Non-Goals

- 不重写 RRF / ContextPacker / AIChatService / PgEdgeRetriever 主链路。
- 不替换 expected_keypoints 数据结构；只在样例 JSON 增加可选 `synonyms` / `weight` 字段。
- 不把 LLM-as-judge 作为唯一验收依据。
- 不修复 TD-068（vector embedding 为空）。
- 不调整 graph_edge 权重（REQ-017 范围）。

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 样例 JSON 支持 `expected_keypoints` 元素为 `{term, synonyms?, weight?}` 对象或字符串（向后兼容） | JSON 解析兼容 + 报告展示 |
| AC-2 | 脚本输出三口径：`keypoint_coverage_pct_substring` / `_semantic` / `_llm_judge` | ScenarioRun 字段 |
| AC-3 | 报告同时展示三种口径矩阵和差异分析 | 新报告章节 |
| AC-4 | REQ-027 10 样例重跑双口径：semantic 覆盖度 ≥ 0.50 样例数 ≥ 5/10 | 新报告验证 |
| AC-5 | REQ-027 10 样例重跑双口径：P2 完整链路相对 baseline semantic 覆盖度提升 ≥ 30% 样例数 ≥ 3/10 | 新报告验证 |
| AC-6 | LLM-as-judge 调用需 `--allow-llm` 才会跑；dry-run 模式 LLM-as-judge 字段为 `null` | CLI 行为 |
| AC-7 | 若 AC-5 未达成，必须登记独立 `REQ-029` 或 `TD-xxx` 接力 | 候选区登记 |
| AC-8 | 旧 `keypoint_coverage_pct` 字段保留（= substring 口径），保证 REQ-026/027 报告不变 | 旧报告复跑一致 |

## 5. Architecture

### 5.1 样例 JSON schema 升级

旧格式（向后兼容）：
```json
"expected_keypoints": ["闭包", "装饰器", "函数", "内部", "引用"]
```

新格式（推荐）：
```json
"expected_keypoints": [
  {"term": "闭包", "synonyms": ["嵌套函数", "closure", "外层引用"], "weight": 1.0},
  {"term": "装饰器", "synonyms": ["decorator", "@", "包装器"], "weight": 1.0},
  {"term": "函数", "synonyms": ["function", "def", "方法"], "weight": 0.5}
]
```

字段语义：
- `term` (str, 必填): 关键词原形
- `synonyms` (list[str], 可选): 同义词列表，匹配任一同义词视为命中
- `weight` (float, 默认 1.0): 关键事实分项权重；核心词 1.0，修饰词 / 同义泛指 0.5
- semantic coverage = sum(命中 keypoint 的 weight) / sum(全部 keypoint 的 weight)

### 5.2 三口径计算

| 口径 | 算法 | 用途 |
|------|------|------|
| substring | 子串包含（旧） | 历史基线，向后兼容 |
| semantic | 关键词 + synonyms 集合 ∩ 答案文本；按 weight 加权 | 主验收口径 |
| llm_judge | 调用 LLM：「以下答案是否覆盖以下关键事实？列出命中与未命中」 | secondary signal |

### 5.3 脚本改造

`scripts/validate_req024_p2_real_validation.py` 改造：

1. **新增** `_parse_keypoint(kp: Any) -> Keypoint`:
   - 字符串 → Keypoint(term=kp, synonyms=[], weight=1.0)
   - 字典 → Keypoint(term=kp["term"], synonyms=kp.get("synonyms", []), weight=kp.get("weight", 1.0))

2. **新增** dataclass `Keypoint`:
   ```python
   @dataclass
   class Keypoint:
       term: str
       synonyms: list[str]
       weight: float
   ```

3. **改造** `_load_questions`: 解析 `expected_keypoints` 为 `list[Keypoint]`

4. **改造** `_compute_keypoint_coverage` -> 重命名为 `_compute_substring_coverage`，保留旧行为

5. **新增** `_compute_semantic_coverage(answer_preview, sources_titles, keypoints: list[Keypoint]) -> tuple[float, list[str], float, list[str]]`:
   - 返回 (pct, hit_terms, weight_pct, hit_details)
   - 命中判定: haystack 包含 term 或任一 synonym（lowercase substring）
   - 权重计算: sum(weight for hit) / sum(weight for all)

6. **新增** `_compute_llm_judge_coverage(answer_preview, keypoints, llm_callable) -> tuple[float, list[str]]`:
   - 调 LLM 输出 JSON：`{"covered": [...], "missing": [...], "score": 0-1}`
   - 不调外部 LLM 时返回 (None, [])

7. **ScenarioRun 扩展字段**:
   - `keypoint_hit_count_semantic: int`
   - `keypoint_total_semantic: int`
   - `keypoint_coverage_pct_semantic: float`
   - `keypoint_weight_pct_semantic: float` (新：权重口径)
   - `keypoint_llm_judge_pct: float | None`
   - 旧字段保留不变

8. **报告渲染** 新增章节：
   - `## REQ-028 三口径对比`
   - per-sample 矩阵：substring / semantic / weight / llm_judge
   - 差异分析：哪些样例 semantic 显著高于 substring（同义改写命中）
   - 决策依据：P2 完整链路相对 baseline 的口径选择

### 5.4 数据流

```
validate_req024_p2_real_validation.py (改造)
    │
    ├─► 加载 samples (REQ-016/018/027 v1/v2)
    │       解析 expected_keypoints (string | dict)
    │
    ├─► 对每个 sample x scenario 跑 AIChatService
    │
    ├─► 计算三种覆盖度：
    │       ├─ substring (旧，向后兼容)
    │       ├─ semantic (新，主验收)
    │       └─ llm_judge (新，secondary signal，需 --allow-llm)
    │
    └─► 输出双口径报告
```

## 6. File Layout

```
scripts/
├── validate_req024_p2_real_validation.py                 # 改造
├── validate_real_pg_rag_req026_weak_recall.example.json  # 不修改（向后兼容验证）
├── validate_real_pg_rag_req027_weak_recall_v2.example.json  # 可选：升级 keypoints 为 dict 格式
├── run_req027_validation.py                              # 不修改
└── validate_real_pg_rag_req028_weak_recall_v3.example.json  # 新增：v3 样例（keypoint 带 synonyms + weight）

docs/02-delivery-plans/01-specs/
├── 2026-06-18-req-028-auto-quality-metric.md             # 本文件
└── 2026-06-18-req-028-rag-effect-comparison-v3-report.md  # 新增：v3 双口径报告

docs/02-delivery-plans/02-plans/
└── 2026-06-18-req-028-auto-quality-metric-plan.md        # 新增

docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md  # 已产出
docs/01-product-planning/02-milestones/02-growth-phase.md
docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md
docs/01-product-planning/04-backlog.md
docs/03-engineering-governance/current-work.md
docs/03-engineering-governance/work-log.md
```

## 7. Diagnostics Trace

复用 REQ-026 diagnostics：retrieval_topn / fusion_topn / packed_blocks / document_sources / final_answer_preview / vector_fallback_count。

ScenarioRun 新增字段：
```json
{
  "keypoint_coverage_pct_substring": 0.20,
  "keypoint_coverage_pct_semantic": 0.80,
  "keypoint_weight_pct_semantic": 0.85,
  "keypoint_llm_judge_pct": 0.60,
  "keypoint_hit_list_substring": ["函数"],
  "keypoint_hit_list_semantic": ["函数", "装饰器", "内部函数", "包装器"]
}
```

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | REQ-028 requirement + spec + plan + Keypoint dataclass + `_parse_keypoint` + `_compute_substring_coverage` / `_compute_semantic_coverage` | — |
| Slice 2 | `_compute_llm_judge_coverage` + ScenarioRun 扩展字段 + 报告新章节 | Slice 1 |
| Slice 3 | v3 样例集（keypoint 带 synonyms + weight，覆盖 Q1-Q10） | Slice 1 |
| Slice 4 | 真 PG dry-run v3 双口径报告 | Slice 2/3 |
| Slice 5 | 真 PG + `--allow-llm` v3 三口径报告 | Slice 4 |
| Slice 6 | 文档收口 + commit + push + PR | Slice 5 |

## 9. Risks

- **LLM-as-judge 速率 / 成本**：每样例 × 4 scenario × 3 rounds = 120 次 LLM 调用，可能撞限流。需 `--limit` 控制。
- **synonyms 校准**：新格式 keypoint 的 synonyms 必须在 dev DB 真实内容中校准，避免引入空泛同义词。
- **向后兼容破坏**：旧样例 JSON 字符串格式必须仍能解析；旧报告 substring 字段必须保留。
- **双口径决策规则**：当 semantic 与 substring 不一致时，必须明确决策依据（不能拍脑袋）。

## 10. References

- REQ-027 requirement: `docs/01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md`
- REQ-027 report v1: `docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v1-report.md`
- REQ-027 report v2: `docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md`
- REQ-027 样例集 v2: `scripts/validate_real_pg_rag_req027_weak_recall_v2.example.json`
- REQ-027 wrapper: `scripts/run_req027_validation.py`
- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`