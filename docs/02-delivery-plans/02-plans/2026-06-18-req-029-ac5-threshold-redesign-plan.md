# REQ-029 P2 弱召回 AC-5 阈值重设计 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-redesign.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-029-p2-ac5-threshold-redesign.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

扩展 `validate_req024_p2_real_validation.py` 支持 AC-5 阈值重设计（residual ratio 公式），用 REQ-028 v3 样例（10 条）跑真 LLM 报告。不修改 AIChatService / RRF / ContextPacker 主链路。

## Slice 1 — 脚本核心改造

**目标**：脚本支持 `absolute` / `residual` 两种 lift 模式，参数化阈值。

**文件：**

- `scripts/validate_req024_p2_real_validation.py`（修改）

**改动：**

1. **新增** `_compute_lift_metrics(baseline: float, weighted: float, mode: str = "residual") -> dict`:
   - `absolute` 模式: `delta = weighted - baseline`；verdict 按 ±0.30 判定
   - `residual` 模式: `residual_ratio = (weighted - baseline) / (1 - baseline)`，clamp 到 [-1, 1]；verdict 按 ±0.30 判定
   - 边界: baseline=1.0 → ratio=0；baseline=0.0 → ratio=1.0 if weighted>0 else 0.0

2. **ScenarioRun 扩展字段**:
   - `semantic_lift_delta: float = 0.0`
   - `semantic_lift_residual_ratio: float | None = None`
   - `semantic_lift_verdict: str = "中性"`

3. **`_run_question`** 填充新字段（mode 来自 args）。

4. **CLI 参数** `--lift-mode`: choices=`['residual', 'absolute']`，default='residual'

5. **`_render_req026_section` / `_render_req028_section`** 用 `_compute_lift_metrics(scenario, mode=args.lift_mode)` 判定 verdict。

6. **REQ-028 报告新增章节**「REQ-029 阈值重设计」：
   - per-sample 对比表：absolute verdict vs residual verdict
   - 总结：residual 模式正向样例数 ≥ 4/10 标记 ✅
   - 若未达成，显式记录"已登记 REQ-030"

**验收：**

- `python -m py_compile scripts/validate_req024_p2_real_validation.py` 通过
- `python scripts/validate_req024_p2_real_validation.py --help` 含 `--lift-mode`
- `--lift-mode absolute` 报告字段与 REQ-028 v3 一致
- `--lift-mode residual` 报告新增 verdict 字段

## Slice 2 — 真 PG + `--allow-llm` residual 模式报告

**目标**：residual 模式真 LLM 报告生成。

**命令：**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python scripts/validate_req024_p2_real_validation.py \
  --req028-samples scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples scripts/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-residual-report.md \
  --json-out /tmp/req029_residual.json \
  --report-title "REQ-029 P2 RAG 弱召回样例 v3 residual 阈值模式报告 (real LLM)" \
  --lift-mode residual \
  --allow-llm
```

**验收：**

- 报告 `External LLM: enabled` / `Validation Status: real-llm-run`
- residual 模式 AC-5 达标样例数 ≥ 4/10
- 报告含「REQ-029 阈值重设计」章节（absolute vs residual 对比）

## Slice 3 — 文档收口 + Git 闭环

**文件改动：**

- `docs/01-product-planning/05-requirements/REQ-029-...md` — Status: 🟡 进行中 → 🟢 Done / 🟡 部分收口
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-029 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-029 状态
- `docs/01-product-planning/04-backlog.md` — REQ-029 状态
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行式索引

**Git 闭环：**

```bash
git add scripts/validate_req024_p2_real_validation.py \
        docs/02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-redesign.md \
        docs/02-delivery-plans/02-plans/2026-06-18-req-029-ac5-threshold-redesign-plan.md \
        docs/02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-residual-report.md \
        docs/01-product-planning/05-requirements/REQ-029-...md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md

git commit -m "feat(rag): REQ-029 AC-5 threshold redesign (residual ratio mode) + v3 report"
git push origin feat/req-029-ac5-threshold-redesign
gh pr create --title "REQ-029 P2 弱召回 AC-5 阈值重设计 (residual ratio)" --body "..."
gh pr merge --squash --delete-branch
```

**验收：**

- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- `scripts/check-engineering-docs` 通过

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（基线脚本）
- `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`（v3 报告对照）

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 PG + LLM 验收：`python scripts/validate_req024_p2_real_validation.py ... --lift-mode residual --allow-llm` 退出码 0

## Documentation Closure

完成后必须同步：

- `docs/01-product-planning/05-requirements/REQ-029-...md` Status → 🟢 Done
- `docs/01-product-planning/02-milestones/02-growth-phase.md` REQ-029 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` REQ-029 状态
- `docs/01-product-planning/04-backlog.md` REQ-029 状态
- `docs/03-engineering-governance/current-work.md` 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` 一行式索引