# REQ-032 P2 semantic_emb 阈值校准与 continuous 口径 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-032-semantic-emb-threshold-calibration.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

`--semantic-emb-threshold` CLI + `keypoint_semantic_embedding_continuous_pct` 字段 + 报告增强（threshold 敏感性 + continuous delta + Spearman）。基于预诊断如实记录 AC-4/5 不达标根因。

## Slice 1 — CLI + continuous 字段 + 报告

**文件**：`scripts/validate_req024_p2_real_validation.py`（修改）

**改动**：

1. **CLI** `--semantic-emb-threshold`（float，默认 0.5），透传到 `_run_question` → `_compute_semantic_embedding_coverage`
2. **ScenarioRun** 新增 `keypoint_semantic_embedding_continuous_pct: float = 0.0`
3. **`_compute_semantic_embedding_coverage`** 返回值新增 `continuous_pct`（加权平均 similarity，不二值化）
4. **`_compact_run`** JSON dump 补 `keypoint_semantic_embedding_continuous_pct`
5. **报告** REQ-030 章节：
   - per-sample 矩阵增 `cont cov` 列
   - per-sample summary 增 continuous delta + verdict
   - 新增 "threshold 敏感性" 段（0.50/0.45/0.40/0.35 命中率，从缓存 per_keypoint 重算）
   - Spearman 增 continuous vs LLM-judge

**验收**：`py_compile` + `ruff` 通过；旧字段不变。

## Slice 2 — dry-run

**命令**：标准 dry-run，exit 0，0 scenario errors。

## Slice 3 — `--allow-llm` 真 LLM 重跑 + AC 补判

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md \
  --json-out /tmp/req032_real.json \
  --report-title "REQ-032 v3 re-run (threshold calibration + continuous, real LLM)" \
  --allow-llm --semantic-emb-threshold 0.35
```

**验收**：
- exit 0，无挂起
- threshold 0.35 + continuous 双口径 AC-5 如实记录（预判 0/10）
- continuous vs LLM-judge Spearman 如实记录（预判负相关）
- 根因诊断：P2 链路无正向贡献 vs 阈值 vs keypoint 标注

## Slice 4 — 文档收口 + Git 闭环

**文件改动**：
- `docs/01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md` — Status + Delivery Record
- `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md` — 覆盖式重跑 + AC 补判 + 根因
- `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` — AC-4/5 最终判定
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-030/032 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-032 状态
- `docs/01-product-planning/04-backlog.md` — REQ-032 状态 + 后续任务
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行索引

**Git 闭环**：commit + push + PR + squash merge + delete branch。

**验收**：`gh pr view <PR>` state=MERGED；`scripts/check-engineering-docs` 通过。

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 LLM 验收：`--allow-llm` exit 0

## Follow-up (Out of Scope)

- 若根因是 P2 链路：登记 REQ-033 评估 P2 链路在真 vector 下的实际价值（RRF 权重 / graph_edge 策略）
- 若根因是 keypoint 标注：review Q4/Q9 keypoints
- 重跑 REQ-026/027/029 真 LLM 报告（独立 PR）
- TD-032 脚本拆分
