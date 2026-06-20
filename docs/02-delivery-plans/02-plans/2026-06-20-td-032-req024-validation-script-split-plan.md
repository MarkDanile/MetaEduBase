# TD-032 Slice 8 Plan: 拆分 `validate_req024_p2_real_validation.py`

> Status: 🟢 完成（PR #375）
> Created: 2026-06-20
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-td-032-req024-validation-script-split.md`

## 任务模式

技术债（TD-032 follow-up slice 8）。机械拆分，零业务逻辑变化。

## 执行步骤

### Slice 1: 包骨架 + models/loader/coverage

1. 建目录 `scripts/rag_validation/`。
2. `models.py`：迁常量（REPO_ROOT/SERVER_PYTHON/sys.path 注入/DEFAULT_* 路径/DEFAULT_TENANT_ID）+ 4 个 dataclass（Question/Keypoint/Scenario/ScenarioRun）。保留 `from __future__ import annotations`。
3. `loader.py`：迁 `_load_dotenv` / `_mask_db_url` / `_parse_keypoint` / `_load_questions`，import models。
4. `coverage.py`：迁 `_compute_keypoint_coverage` / `_compute_semantic_coverage` / `_EMB_SEMAPHORE` / `_EMBEDDING_CACHE` / `_EMB_STATS` / `_get_cached_embedding` / `_compute_semantic_embedding_coverage` / `_compute_llm_judge_coverage` / `_compute_llm_judge_coverage_async`，import models。

### Slice 2: runner/report/report_quality/report_chain/main + 薄入口

5. `runner.py`：迁 scenarios / `_fake_query_understanding_response` / `_build_service` / `_trace_chunk_ids` / `_run_question` / `_json_preview` / `_compact_run` / `_group_runs` / `_graph_edge_supplement_count` / `_compute_lift_metrics`，import models + coverage。
6. `report.py`：迁 `_render_report` + `_render_req026_section` + `_render_req028_section`，import models + runner + report_quality + report_chain。
7. `report_quality.py`：迁 `_render_req030_section`，import models + coverage（读 `_EMB_STATS`）+ runner。
8. `report_chain.py`：迁 `_render_req033_section` + `_render_req034_section` + 共享 helpers，import models + runner。
9. `main.py`：迁 `_run` / `_build_parser` / `main`，import models + loader + runner + report。
10. `__init__.py`：`from .main import main`。
11. `scripts/validate_req024_p2_real_validation.py` 改为薄入口（sys.path insert + `from rag_validation import main`）。

### Slice 3: 等价验证

12. `ruff check scripts/rag_validation/ scripts/validate_req024_p2_real_validation.py`。
13. 拆分前先存一份 dry-run 报告基线（已存 /tmp/req034/dryrun-report.md from REQ-034）。
14. 拆分后 dry-run 复跑同输入，diff 报告（忽略时间戳行）→ 须等价。
15. `wc -l scripts/rag_validation/*.py` 确认每文件 ≤500。
16. `scripts/scan-source-sizes --refresh` 刷新基线 + `--diff` 确认无意外差异。
17. `scripts/check-engineering-docs`。

### Slice 4: 文档收口 + Git

18. baseline `td-032-source-file-sizes.md` 回写：原条目 1955 → 「已拆分」+ 包模块清单行数。
19. TD-032 总账追加 slice 8 交付记录。
20. current-work / work-log 同步。
21. commit + push + PR + squash merge + 删分支 + 同步 main。

## 验证矩阵

| 项 | 命令 |
|----|------|
| 风格 | `ruff check scripts/rag_validation/ scripts/validate_req024_p2_real_validation.py` |
| 等价 | dry-run 前后报告 diff（忽略时间戳） |
| 规模 | `wc -l scripts/rag_validation/*.py`（每文件 ≤500） |
| 基线 | `scripts/scan-source-sizes --refresh` + `--diff` |
| 门禁 | `scripts/check-engineering-docs` |

## 风险与回退

- 全部改动限定在 `scripts/`（新增包 + 入口瘦身），不碰业务代码；回退即 revert。
- 等价验证若失败，定位为 import 顺序 / helper 迁移遗漏 / 模块全局重建，逐项修正后重验。
