# REQ-030 P2 RAG 自动质量评估新口径设计 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

新增 `keypoint_semantic_embedding_coverage` 字段 + 启用 LLM-as-judge + REQ-028 v3 10 样例重跑。不修改 REQ-028 v3 历史报告字段（向后兼容）。

## Slice 1 — 脚本核心改造

**目标**：脚本支持 semantic embedding coverage 计算 + 报告新章节。

**文件**：`scripts/validate_req024_p2_real_validation.py`（修改）

**改动**：

1. **新增** `_compute_semantic_embedding_coverage(answer_preview, keypoints, embedding_callable) -> dict`:
   - 对每个 keypoint 计算 term + synonyms 的 embedding (复用 `get_embedding`)
   - 计算 answer embedding
   - 每个 keypoint 的相似度 = `max(cos(answer_emb, term_emb), cos(answer_emb, each_synonym_emb))`
   - 命中阈值 0.5（可参数化）
   - 覆盖率 = `sum(weight * (1 if sim > threshold else 0)) / sum(weight)`
   - 返回 `{coverage_pct, hit_terms, per_keypoint: [{term, similarity, hit}]}`

2. **ScenarioRun 扩展字段**:
   - `keypoint_semantic_embedding_pct: float`
   - `keypoint_semantic_embedding_hit_terms: list[str]`
   - `keypoint_llm_judge_pct: float | None` (已有，确保启用)
   - `keypoint_llm_judge_covered: list[str]`
   - `keypoint_llm_judge_missing: list[str]`

3. **CLI 参数** `--llm-judge` 可选开关（默认开启 dry-run 时关闭 LLM-as-judge）

4. **报告渲染** 新增章节 `## REQ-030 新口径对比`:
   - per-sample 矩阵：substring cov / semantic cov / semantic embedding cov / LLM-as-judge cov
   - 差异分析：semantic embedding 与 LLM-as-judge 的 Spearman 相关性
   - AC 判定：基于新 AC 阈值（semantic embedding delta ≥ 0.30）

**验收**：
- `python -m py_compile scripts/validate_req024_p2_real_validation.py` 通过
- 旧字段（`keypoint_coverage_pct` / `keypoint_coverage_pct_semantic`）保留
- 新字段默认值 `0.0` / `[]` / `None`

## Slice 2 — 真 PG dry-run v3 新口径

**目标**：dry-run 验证机制 + semantic embedding 字段可计算。

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/req030_v3_dry.md \
  --report-title "REQ-030 v3 dry-run (semantic embedding + LLM-as-judge)"
```

**验收**：
- exit 0
- 0 scenario errors
- semantic embedding 字段填入（非 0）
- LLM-as-judge 字段为 None（dry-run 模式）

## Slice 3 — `--allow-llm` 真 LLM 重跑 v3

**目标**：真 LLM 重跑，semantic embedding + LLM-as-judge 双口径生效。

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md \
  --json-out /tmp/req030_v3_real.json \
  --report-title "REQ-030 v3 re-run with new metrics (real LLM)" \
  --allow-llm
```

**验收**：
- exit 0
- semantic embedding coverage 与 substring coverage 显著不同
- LLM-as-judge coverage 报告完整
- Spearman rho ≥ 0.7 或如实记录
- AC-4 (semantic embedding delta ≥ 0.30): 至少 4/10 样例达标

## Slice 4 — 文档收口 + Git 闭环

**文件改动**：
- `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` — Status: Shaping → Done / 部分收口
- `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`（新增）
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-030 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-030 状态
- `docs/01-product-planning/04-backlog.md` — REQ-030 状态
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行索引

**Git 闭环**：
```bash
git add scripts/validate_req024_p2_real_validation.py \
        docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md \
        docs/02-delivery-plans/02-plans/2026-06-20-req-030-new-quality-metric-plan.md \
        docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md

git commit -m "feat(rag): REQ-030 new quality metrics (semantic embedding + LLM-as-judge) + v3 re-run"
git push origin feat/req-030-new-quality-metric
gh pr create --title "REQ-030 P2 RAG 新质量口径 (semantic embedding + LLM-as-judge)" --body "..."
gh pr merge --squash --delete-branch
```

**验收**：
- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- `scripts/check-engineering-docs` 通过

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py` (基线脚本，已有 `_compute_semantic_coverage` 和 `_compute_llm_judge_coverage_async`)
- `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md` (v3 重跑报告)
- `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json` (v3 样例)
- `packages/server-python/app/contexts/knowledge/application/embedding_service.py` (硅流 embedding 接入)

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 LLM 验收：`python scripts/validate_req024_p2_real_validation.py ... --allow-llm` 退出码 0

## Documentation Closure

完成后必须同步：

- `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` Status
- `docs/01-product-planning/02-milestones/02-growth-phase.md` REQ-030 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-030 状态
- `docs/01-product-planning/04-backlog.md` REQ-030 状态
- `docs/03-engineering-governance/current-work.md` 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` 一行索引

## Follow-up (Out of Scope)

- 重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR）
- 若 AC-4 未达成，登记 REQ-031 接力
- TD-032 脚本拆分（独立任务）