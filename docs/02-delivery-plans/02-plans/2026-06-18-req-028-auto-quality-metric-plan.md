# REQ-028 P2 弱召回自动质量比较口径改造 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-auto-quality-metric.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

扩展 `validate_req024_p2_real_validation.py` 支持三口径覆盖度（substring / semantic / llm_judge），复用 REQ-027 样例集（10 条）跑双口径报告。不修改 AIChatService / RRF / ContextPacker 主链路。

## Slice 1 — 脚本核心改造

**目标**：脚本支持 Keypoint dataclass + 三口径覆盖度计算 + 向后兼容。

**文件：**

- `scripts/validate_req024_p2_real_validation.py`（修改）

**改动：**

1. 新增 `Keypoint` dataclass：
   ```python
   @dataclass
   class Keypoint:
       term: str
       synonyms: list[str] = field(default_factory=list)
       weight: float = 1.0
   ```

2. 新增 `_parse_keypoint(kp: Any) -> Keypoint`:
   - 字符串 → `Keypoint(term=kp)`
   - 字典 → `Keypoint(term=kp["term"], synonyms=kp.get("synonyms", []), weight=kp.get("weight", 1.0))`

3. 改造 `Question.expected_keypoints: list[Keypoint]`（或保留 `list[str]` + 内部转换）

4. 改造 `_load_questions` 解析 `expected_keypoints` 元素：
   ```python
   raw_keypoints = item.get("expected_keypoints", []) or []
   keypoints = [_parse_keypoint(kp) for kp in raw_keypoints if kp]
   ```

5. **保留** `_compute_keypoint_coverage`（旧 substring 行为不变）

6. **新增** `_compute_semantic_coverage(answer_preview, sources_titles, keypoints: list[Keypoint]) -> dict`:
   ```python
   def _compute_semantic_coverage(answer_preview, sources_titles, keypoints):
       if not keypoints:
           return {"hit_count": 0, "total": 0, "coverage_pct": 0.0, "weight_pct": 0.0, "hit_terms": []}
       haystack = ((answer_preview or "") + "\n" + "\n".join(sources_titles or [])).lower()
       hit_terms = []
       total_weight = 0.0
       hit_weight = 0.0
       for kp in keypoints:
           total_weight += kp.weight
           candidates = [kp.term] + list(kp.synonyms or [])
           if any(c.lower() in haystack for c in candidates if c):
               hit_terms.append(kp.term)
               hit_weight += kp.weight
       total = len(keypoints)
       coverage_pct = (len(hit_terms) / total) if total else 0.0
       weight_pct = (hit_weight / total_weight) if total_weight else 0.0
       return {
           "hit_count": len(hit_terms),
           "total": total,
           "coverage_pct": round(coverage_pct, 4),
           "weight_pct": round(weight_pct, 4),
           "hit_terms": hit_terms,
       }
   ```

7. **新增** `_compute_llm_judge_coverage(answer_preview, keypoints, llm_callable) -> dict | None`:
   - prompt: 「以下答案是否覆盖以下关键事实？列出命中与未命中项，输出 JSON {covered, missing, score}」
   - 解析 JSON 返回 `{coverage_pct, covered, missing}`
   - `llm_callable is None` 时返回 None

8. **ScenarioRun 扩展字段**:
   - `keypoint_coverage_pct_substring: float` (= 旧 `keypoint_coverage_pct`)
   - `keypoint_coverage_pct_semantic: float`
   - `keypoint_weight_pct_semantic: float`
   - `keypoint_llm_judge_pct: float | None`
   - `keypoint_hit_list_substring: list[str]`
   - `keypoint_hit_list_semantic: list[str]`

9. **报告渲染** 新增章节 `## REQ-028 三口径对比`:
   - per-sample 矩阵：substring / semantic / weight / llm_judge
   - 差异分析：semantic 显著高于 substring 的样例
   - 决策依据：P2 完整链路相对 baseline 的口径选择

**验收：**

- `python -m py_compile scripts/validate_req024_p2_real_validation.py` 通过
- 旧样例 (string `expected_keypoints`) 仍能跑通
- 新样例 (dict `expected_keypoints`) 跑出 semantic 字段

## Slice 2 — v3 样例集（keypoint 带 synonyms + weight）

**目标**：把 REQ-027 v2 5 条 + REQ-027 v1 5 条升级为 keypoint dict 格式，配 synonyms 与 weight。

**文件：**

- `scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json`（新建）

**样例设计：**

| ID | keypoint | synonyms | weight | 校准依据 |
|----|----------|----------|--------|----------|
| Q1 装饰器 | 装饰器 | decorator, @, 包装器, wrapper | 1.0 | dev DB chunk 命中 "decorator" |
| Q1 装饰器 | 函数 | function, def, 方法 | 0.5 | 同义泛指 |
| Q1 装饰器 | wrapper | 包装器, 内部函数, 嵌套函数 | 1.0 | Q1 specific |
| Q1 装饰器 | 语法糖 | 简写, sugar | 0.5 | 修饰词 |
| Q1 装饰器 | @ | at符号 | 0.3 | 修饰词 |
| Q2 生成器迭代器 | 生成器 | generator, yield | 1.0 | dev DB chunk 命中 |
| Q2 生成器迭代器 | 迭代器 | iterator, iter, next | 1.0 | dev DB chunk 命中 |
| Q2 生成器迭代器 | 列表生成式 | list comprehension, [x for x in] | 1.0 | dev DB chunk 命中 |
| Q2 生成器迭代器 | yield | 返回, 返回值 | 0.5 | 修饰 |
| Q2 生成器迭代器 | for | 循环, 遍历 | 0.3 | 修饰 |
| ... (Q3-Q10 同样升级) |

**验收：**

- v3 JSON 合法
- 每个 keypoint 的 synonyms 至少 1 个元素（除纯修饰词）
- weight 分配合理：核心词 1.0、修饰词 ≤ 0.5

## Slice 3 — 真 PG dry-run v3 双口径

**目标**：v3 dry-run 报告生成。

**命令：**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python scripts/run_req027_validation.py --weak-recall-samples scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json --out docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md --report-title "REQ-028 P2 RAG 弱召回样例 v3 双口径报告 (dry-run)"
```

**验收：**

- v3 dry-run 报告包含三口径章节
- dry-run 模式下 LLM-as-judge 字段为 null

## Slice 4 — 真 PG + `--allow-llm` v3 三口径

**目标**：用户授权后跑真 LLM provider。

**命令：**

```bash
python scripts/run_req027_validation.py --weak-recall-samples scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json --out docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md --report-title "REQ-028 P2 RAG 弱召回样例 v3 双口径报告 (real LLM)" --allow-llm
```

**验收：**

- v3 real LLM 报告包含三口径字段
- semantic 覆盖度 ≥ 0.50 样例数 ≥ 5/10
- P2 完整链路相对 baseline semantic 覆盖度提升 ≥ 30% 样例数 ≥ 3/10

## Slice 5 — 文档收口 + Git 闭环

**文件改动：**

- `docs/01-product-planning/05-requirements/REQ-028-...md` — Status: 🟡 Doing → 🟢 Done / 🟡 部分收口
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-028 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-028 状态
- `docs/01-product-planning/04-backlog.md` — REQ-028 状态
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行式索引

**Git 闭环：**

```bash
git add scripts/validate_req024_p2_real_validation.py \
        scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json \
        docs/02-delivery-plans/01-specs/2026-06-18-req-028-auto-quality-metric.md \
        docs/02-delivery-plans/02-plans/2026-06-18-req-028-auto-quality-metric-plan.md \
        docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md \
        docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md

git commit -m "feat(rag): REQ-028 three-metric auto quality comparison (substring/semantic/llm_judge) + v3 report"
git push origin feat/req-028-auto-quality-metric
gh pr create --title "REQ-028 P2 弱召回自动质量比较口径改造 (三口径 + v3 报告)" --body "..."
gh pr merge --squash --delete-branch
```

**验收：**

- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- `scripts/check-engineering-docs` 通过
- v3 报告 AC-4/AC-5 达成

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（基线脚本）
- `scripts/validate_real_pg_rag_req027_weak_recall_v2.example.json`（v2 样例结构）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md`（v2 报告结构）

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 PG 验收：`python scripts/run_req027_validation.py --weak-recall-samples v3 ...` 退出码 0

## Documentation Closure

完成后必须同步：

- `docs/01-product-planning/05-requirements/REQ-028-...md` Status → 🟡 Doing / 🟢 Done
- `docs/01-product-planning/02-milestones/02-growth-phase.md` REQ-028 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-028 状态
- `docs/01-product-planning/04-backlog.md` REQ-028 状态
- `docs/03-engineering-governance/current-work.md` 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` 一行式索引