# REQ-033 P2 链路真 vector 价值评估 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

脚本新增 `_render_req033_section`（retrieval 层价值分析 + 指标 A/B），不改主链路。基于真 LLM 数据出评估报告 + 价值判定 + 链路调整建议。

## Slice 1 — retrieval 层价值分析章节

**文件**：`scripts/validate_req024_p2_real_validation.py`（修改）

**改动**：

1. **新增** `_render_req033_section(runs, grouped) -> str`:
   - 表 1：graph_edge 通道有效性（per sample：edge 召回 / 进 fusion / 进 packed）
   - 表 2：跨文档 grounding（edge evidence 文件 vs 其他通道文件）
   - 表 3：packed 重排度（baseline ∩ weighted overlap）
   - 指标 A：graph_edge 关联补足率 = `count(weighted.edge_packed > 0) / total`
   - 指标 B：跨 section 完整性 = `distinct section_path(weighted) - distinct section_path(baseline)` per sample
   - 价值判定（按 spec §5.3 框架）
2. **`_render_report`** 触发 REQ-033 章节（REQ-028 group 存在时）

**验收**：`py_compile` + `ruff` 通过。

## Slice 2 — dry-run

标准 dry-run，exit 0。

## Slice 3 — 真 LLM 重跑 + 价值判定

**命令**：复用 threshold 0.35 真 LLM 重跑（REQ-032 数据已含 retrieval 字段，可重跑出新报告含 REQ-033 章节）。

**验收**：
- exit 0
- 指标 A / B 计算正确
- 价值判定 + 结论 + 建议

## Slice 4 — 评估报告 + 文档收口 + Git 闭环

**文件改动**：
- `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md`（新增，评估报告）
- `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md` — Status + Delivery Record
- `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` — AC-5 根因归档 + 最终状态
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-033 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-033 状态
- `docs/01-product-planning/04-backlog.md` — REQ-033 状态 + 后续需求
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行索引

**Git 闭环**：commit + push + PR + squash merge + delete branch。

**验收**：`gh pr view <PR>` state=MERGED；`scripts/check-engineering-docs` 通过。

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`

## Follow-up (Out of Scope)

- 若建议调整链路：登记 REQ-034 评估 graph_edge RRF 权重 / 策略调整影响面
- 重跑 REQ-026/027/029 真 LLM 报告
- TD-032 脚本拆分
