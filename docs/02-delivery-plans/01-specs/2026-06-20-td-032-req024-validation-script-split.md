# TD-032 Slice 8: 拆分 `validate_req024_p2_real_validation.py`

> Status: 🟢 完成（PR #375 squash merge；dry-run render 路径 byte-identical 验证通过）
> Created: 2026-06-20
> Source: TD-032 follow-up（baseline 已登记 `validate_req024_p2_real_validation.py` 待拆分）
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-td-032-req024-validation-script-split-plan.md`

## 1. Problem Statement

`scripts/validate_req024_p2_real_validation.py` 在 TD-032 收口时（2026-06-08）为 1035 行，已在 [TD-032 行数基线](../../03-engineering-governance/02-baselines/td-032-source-file-sizes.md) 登记为 🟢 已登记（待拆分），并给出拆分方向：按 `load_questions` / `compute_*_coverage` / `render_report_section` / `argparse` 拆为 `validate_req024_p2_real_validation/` 包，目标单文件 ≤500 行。

此后 P2 RAG 质量评估长链（REQ-028→034）持续在此文件叠加：
- REQ-028 三口径 + v3 样例（+215 行 → 1035）
- REQ-030 semantic embedding coverage（+~180 行）
- REQ-031 embedding 缓存 + 超时（+~30 行）
- REQ-032 threshold CLI + continuous 口径（+~60 行）
- REQ-033 retrieval 层价值评估章节（+~175 行）
- REQ-034 weight sweep + 策略评估章节（+~286 行）

当前 **1955 行**，远超 coding-style.md「超过 1000 行的文件不得继续承载新职责」红线。`coding-style.md#文件规模与职责边界` 规定单文件默认 ≤500 行，>1000 不得继续堆叠新职责（除非本任务就是拆分它）。

## 2. Goal

将单文件 1955 行脚本按职责拆为 `scripts/rag_validation/` 包 + 薄入口，目标单文件 ≤500 行，**零业务逻辑变化**，CLI 契约与调用路径不变。

## 3. Non-Goals

- 不改任何评估逻辑、metric 计算、报告内容、CLI 参数语义
- 不重跑 REQ-026/027/028/030/033/034 真 LLM 报告
- 不引入新依赖
- 不拆 `scripts/run_req027_validation.py`（wrapper，仅引用脚本路径，不受影响）

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `scripts/validate_req024_p2_real_validation.py` 保留为薄入口（≤30 行），CLI 与调用路径不变 | 入口行数 + subprocess 调用 |
| AC-2 | 逻辑迁入 `scripts/rag_validation/` 包，每个模块 ≤500 行 | `wc -l` + `scripts/scan-source-sizes` |
| AC-3 | 调用契约不变：`python ../../scripts/validate_req024_p2_real_validation.py ...` 仍可跑（dry-run） | dry-run 复跑 |
| AC-4 | `scripts/run_req027_validation.py`（subprocess 引用脚本路径）不受影响 | 代码审查 + 路径未变 |
| AC-5 | 报告输出 byte-for-byte 等价（dry-run 同输入同输出） | dry-run 前后报告 diff |
| AC-6 | `ruff check` 通过；`scripts/check-engineering-docs` 通过 | 门禁 |
| AC-7 | baseline `td-032-source-file-sizes.md` 回写：原 1955 行条目改为「已拆分」+ 包模块清单 | baseline 更新 |

## 5. Architecture

### 5.1 包结构

```
scripts/rag_validation/
├── __init__.py          # re-export main
├── models.py            # 常量 + dataclass (Question/Keypoint/Scenario/ScenarioRun)
├── loader.py            # _load_dotenv / _mask_db_url / _parse_keypoint / _load_questions
├── coverage.py          # _compute_*_coverage + embedding cache + LLM-judge（含 _EMB_STATS/_EMB_SEMAPHORE/_EMBEDDING_CACHE 模块全局）
├── runner.py            # scenarios / _build_service / _run_question / _compact_run / _group_runs / _compute_lift_metrics / _graph_edge_supplement_count
├── report.py            # _render_report 编排 + _render_req026_section + _render_req028_section
├── report_quality.py    # _render_req030_section（读 coverage._EMB_STATS）
└── report_chain.py      # _render_req033_section + _render_req034_section + 共享 helpers (_distinct_packed_sections/_packed_chunk_ids/_edge_brings_new_doc/_req034_scenario_metrics)
```

`scripts/rag_validation/main.py`：`_run` / `_build_parser` / `main`。

入口 `scripts/validate_req024_p2_real_validation.py`（薄）：
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_validation import main
if __name__ == "__main__":
    sys.exit(main())
```

### 5.2 依赖图（无环）

- `models` ← (无依赖，含 REPO_ROOT/SERVER_PYTHON + sys.path 注入 server-python)
- `loader` ← models
- `coverage` ← models
- `runner` ← models, coverage
- `report` ← models, runner, report_quality, report_chain
- `report_quality` ← models, coverage（读 _EMB_STATS）, runner
- `report_chain` ← models, runner
- `main` ← models, loader, runner, report

### 5.3 调用契约保留

- 入口路径 `scripts/validate_req024_p2_real_validation.py` 不变 → `run_req027_validation.py` 的 `subprocess.call([..., str(SCRIPT), ...])` 不受影响。
- CLI 参数（`--req028-samples` / `--allow-llm` / `--lift-mode` / `--semantic-emb-threshold` 等）语义不变。
- 报告章节顺序与内容不变（dry-run 等价验证）。

## 6. Risks

- **模块全局状态**：`_EMB_STATS` / `_EMBEDDING_CACHE` / `_EMB_SEMAPHORE` 是进程级单例，必须在 `coverage.py` 定义且只在此处实例化一次。`report_quality` 只读 `_EMB_STATS`，不重建。→ 通过 import 单例保证。
- **import 环**：按 §5.2 依赖图无环；`report` 编排器单向 import `report_quality`/`report_chain`。
- **dry-run 等价**：拆分后 dry-run 报告须与拆分前 byte-for-byte 一致（除时间戳/路径无关字段）。若不一致则定位 import 顺序或 helper 迁移遗漏。
- **`from __future__ import annotations`**：每个模块保留，保证 `dict[str, float] | None` 等注解在旧运行时可用。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | 建 `rag_validation/` 包骨架 + 迁 models/loader/coverage | — |
| Slice 2 | 迁 runner + report + report_quality + report_chain + main + 薄入口 | Slice 1 |
| Slice 3 | dry-run 等价验证 + ruff + scan-source-sizes + check-engineering-docs | Slice 2 |
| Slice 4 | baseline 回写 + 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- TD-032 行数基线: `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`
- TD-032 总账: `docs/03-engineering-governance/technical-debt.md#td-032`
- coding-style 文件规模规则: `docs/03-engineering-governance/01-rules/coding-style.md#文件规模与职责边界`
- 先例（薄入口 + 包拆分）: PR #93 `scripts/engineering/check_engineering_docs.py` 1003 → 72 + `checks/` 包
