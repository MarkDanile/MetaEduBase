# REQ-028 v3 Report Re-run After TD-068+069 — Plan

> Spec: implicit (REQ-028 既有 spec 不变)
> Requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
> Base report: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md` (PR #360)

## Scope

重跑 REQ-028 v3 真 LLM 报告。TD-068 + TD-069 修复后 vector 通道从"keyword 兜底"变为"真语义召回"，报告里 `vector_fallback_count: 0`（已确认）+ `retrieval_topn.vector: 16`（已确认）+ `retrieval_topn` channels 顺序有变化。

**仅重跑 v3**（10 样例，三口径 + residual 阈值），v1 / v2 不重跑（v1 已被 v2 取代，v2 的 1/10 数据已通过 v3 的 10 样例覆盖）。

## Slice 1 — Dry-run 重跑验证脚本能跑通

**目标**：在 TD-069 修复后，validate_req024_p2_real_validation.py 真 PG dry-run 能完整跑通（之前因 vector 不可用会报 `text <=> vector` 错误）。

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/req028_v3_dry.md \
  --report-title "REQ-028 v3 re-run after TD-068+069 (dry-run)"
```

**验收**：
- exit 0
- 0 scenario errors
- `vector_fallback_count: 0`
- `retrieval_topn.vector` 真命中

## Slice 2 — 真 LLM 重跑（需用户授权 `--allow-llm`）

**目标**：跑真 LLM provider（deepseek），重生成答案。

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md \
  --json-out /tmp/req028_v3_real.json \
  --report-title "REQ-028 v3 re-run after TD-068+069 (real LLM)" \
  --allow-llm
```

**验收**：
- exit 0
- `External LLM: enabled` / `Validation Status: real-llm-run`
- 三口径章节完整
- residual 模式 AC-5 仍 ≥ 4/10 样例达标（Q8 0.80→1.00 +0.20 在新 vector 通道下可能变 → 0.20→0.80 etc.）

## Slice 3 — 文档同步

**改动**：
- `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md` 覆盖重跑结果
- `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md` Delivery Record 加一行
- `docs/03-engineering-governance/technical-debt.md`（如 AC-5 改变影响 TD-068 状态）
- `docs/03-engineering-governance/current-work.md` 最近完成区

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（基线脚本）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`（v3 报告对照）
- `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`（验收口径）

## Required Checks

- `scripts/check-engineering-docs` 通过
- `git diff --check` 干净
- 真 LLM 验收 exit 0
- 三口径字段完整 (substring / semantic / weight / llm_judge)
- residual 模式 AC-5 仍达标或如实记录退化

## Follow-up (Out of Scope)

- 重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR，因为涉及 4 份报告 + LLM 调用成本）
- TD-068 Slice 2 报告重跑（如果本报告能证明 vector 通道改变长链结论，可让 TD-068 翻完成）