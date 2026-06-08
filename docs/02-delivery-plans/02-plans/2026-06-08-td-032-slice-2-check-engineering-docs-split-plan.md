# TD-032 切片 2 拆分 `check_engineering_docs.py`（>1000 行）— Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-2-check-engineering-docs-split.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 卡片
- 当前执行模式: `plan-do`（单一职责、纯重构、行为零变化、跨 10 个文件已 spec 覆盖）
- 分支: `refactor/td-032-slice-2-check-engineering-docs`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 风险 2 提前验证：相对 import 在 `__main__` 模式下能否工作

- [ ] 临时建 `scripts/engineering/__init__.py`（空文件）+ `scripts/engineering/checks/__init__.py`（空）。
- [ ] 在主文件顶部临时加 `from .checks._common import KNOWN_ISSUES, Issue`，
      `from .checks import KNOWN_CHECKS`。
- [ ] 跑 `python scripts/engineering/check_engineering_docs.py --root /tmp` 验证：
      - 若退出码 0 / 1 正常 → 相对 import 方案可行，继续。
      - 若 `ImportError: attempted relative import with no known parent package` →
        改用 spec §风险 2 的回退：主文件顶部用
        `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))` +
        `from engineering.checks import KNOWN_CHECKS`（绝对 import）。
- [ ] 验证完撤销临时改动。

**验证点**：`python scripts/engineering/check_engineering_docs.py --root /tmp` 退出码 0
或 1，stderr/stdout 文本与 baseline 一致。

### 2. 建立 `checks/_common.py`

- [ ] 新建 `scripts/engineering/checks/_common.py`，迁入：
  - `from __future__ import annotations` / `import re` / `from dataclasses import dataclass` / `from pathlib import Path`。
  - `Issue` dataclass（行 89-95）。
  - `DebtDetail` dataclass（行 678-683）。
  - 公共常量：`DOC_GLOBS`、`LEGACY_DOC_ROOT_NAMES`、`LEGACY_FOLLOWUP_REFS`、
    `BACKLOG_DONE_TYPES`、`SCRIPTED_GATE_CANDIDATES`、`KNOWN_ISSUES`。
  - 公共正则：`TASK_ID_RE`、`REQ_ID_RE`、`FOLLOWUP_ID_RE`、`LINK_RE`。
  - 工具函数：`rel`、`is_known`、`read_lines`、`section`、`table_rows`、
    `split_table_row`、`iter_doc_files`、`normalize_link_target`、`should_skip_link`。
  - 每个 dataclass / 公共符号加 1 行 docstring 说明（与原行号无对应，纯新增）。

**验证点**：`python -c "from scripts.engineering.checks._common import Issue, KNOWN_ISSUES; print(len(KNOWN_ISSUES))"`
输出 8。

### 3. 建立 8 个聚焦模块

- [ ] `scripts/engineering/checks/current_work.py`：
  - `parse_current_work_completed_ids`（行 251-263）。
  - `check_current_work`（行 156-248）。
  - `check_recent_completed_work_log`（行 266-285）。
  - 常量 `CURRENT_WORK_RECENT_SUMMARY_LIMIT`（行 23）从主文件迁入。
- [ ] `scripts/engineering/checks/product_planning.py`：
  - `PRODUCT_STATUS_ICON_RE`（行 27）、`PRODUCT_STATUS_NAMES`（行 28-41）。
  - `normalize_status`（行 288-301）、`is_product_status`（行 304-305）、
    `has_product_status_icon`（行 308-309）。
  - `check_product_planning_status_icons`（行 312-363）。
  - 5 个 `collect_*_req_statuses`（行 366-439）。
  - `merge_status_maps`（行 442-449）。
  - `check_req_status_consistency`（行 452-481）。
- [ ] `scripts/engineering/checks/task_ids.py`：
  - `check_followup_ids`（行 504-521）。
  - `collect_backlog_done_tasks`（行 524-541）。
  - `has_fact_source`（行 544-547）。
  - `check_backlog_done_index`（行 550-566）。
- [ ] `scripts/engineering/checks/entry_sync.py`：
  - `normalize_entry_lines`（行 569-581）。
  - `check_entry_sync`（行 584-629）。
- [ ] `scripts/engineering/checks/technical_debt.py`：
  - `DETAIL_HEADING_RE`（行 674）、`STATUS_LINE_RE`（行 675）。
  - `parse_debt_overview`（行 685-693）。
  - `parse_debt_details`（行 696-717）。
  - `delivery_record_lines`（行 720-732）。
  - `check_technical_debt`（行 735-784）。
  - `is_completed_plan`（行 787-788）。
  - `allowed_active_checkbox`（行 791-793）。
  - `check_completed_plans`（行 796-813）。
  - `from ._common import DebtDetail`。
- [ ] `scripts/engineering/checks/links_paths.py`：
  - `check_legacy_doc_roots`（行 656-671）。
  - `check_markdown_links`（行 845-868）。
  - `git_diff_work_log`（行 871-884）。
  - `check_work_log_append_only`（行 887-906）。
- [ ] `scripts/engineering/checks/placeholders_claims.py`：
  - `DELIVERY_PLACEHOLDER_RE`（行 42-44）、`NORMATIVE_PLACEHOLDER_RE`（行 45）。
  - `check_delivery_placeholders`（行 484-501）。
  - `VALIDATION_CLAIM_RE`（行 909-912）、`EVIDENCE_RE`（行 913-916）。
  - `has_validation_evidence`（行 919-921）。
  - `check_validation_claims`（行 924-942）。
- [ ] `scripts/engineering/checks/gate_candidates.py`：
  - `check_scripted_gate_candidates`（行 632-653）。

每个聚焦模块顶部都有 `from __future__ import annotations` 与必要的 `from ._common import ...`。
**不在**聚焦模块内 import 任何其他聚焦模块——避免循环。

**验证点**：每个模块 `python -c "import sys; sys.path.insert(0, 'scripts/engineering'); import checks.current_work"` 不抛 ImportError。

### 4. 注册 `checks/__init__.py`

- [ ] 写 `scripts/engineering/checks/__init__.py`，按 spec §3 的内容从 8 个聚焦模块
      re-export 所有 15 个 `check_*` 函数，并定义 `KNOWN_CHECKS: tuple[Callable, ...]`
      保持与原 `run_checks` 中 `issues.extend(...)` 一致顺序。
- [ ] `__all__ = ["KNOWN_CHECKS", "Issue"]`。

**验证点**：`python -c "from scripts.engineering.checks import KNOWN_CHECKS; print(len(KNOWN_CHECKS))"` 输出 15。

### 5. 瘦身入口主文件

- [ ] 重写 `scripts/engineering/check_engineering_docs.py`：
  - 保留：`from __future__ import annotations`、`import argparse` / `import sys` /
    `from pathlib import Path`。
  - 保留：`if __name__ == "__main__": raise SystemExit(main())`。
  - 保留：`main` / `argparse` / `print_issue` / `run_checks`。
  - 删除：所有 check_* / collect_* / parse_* / normalize_* / has_* / is_* 工具函数 + 公共常量。
  - 顶部加 `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))` 一次，
    然后 `from engineering.checks import KNOWN_CHECKS, Issue` + `from engineering.checks._common import is_known`。
  - 入口主文件目标 ≤150 行。
- [ ] 跑 `python scripts/engineering/check_engineering_docs.py --root .`：
  - 退出码 0，stdout `engineering docs checks passed`（与 main baseline 一致）。
  - 若失败，逐模块对照 `KNOWN_CHECKS` 顺序与原 `issues.extend` 顺序。

**验证点**：`wc -l scripts/engineering/check_engineering_docs.py` ≤150。

### 6. 验证全量

- [ ] `scripts/check-engineering-docs`（兼容入口）输出 `engineering docs checks passed`，退出码 0（当前 main baseline：0 active / 0 known allowlist 命中）。
- [ ] `python -m pytest tests/engineering/test_check_engineering_docs.py -v` 16 个测试用例全部通过（baseline 实测 16 passed；spec 初稿 14 是计数错误）。
- [ ] `git diff --name-status` 仅 12 个文件（spec §5.7 列表）；无业务代码改动。
- [ ] `wc -l` 各文件：
  - `scripts/engineering/check_engineering_docs.py` ≤150
  - 9 个聚焦模块每个 30~150 行
  - `checks/_common.py` ≤200 行（dataclass + 9 个工具 + 6 个公共常量 + 4 个正则）
- [ ] 行为变化声明：纯重构；`KNOWN_ISSUES` 8 条 allowlist 仍保留，当前 main baseline 0 active / 0 known。

### 7. Git 闭环

- [ ] 同步 `docs/03-engineering-governance/current-work.md` 任务卡（TD-032 切片 2 收口）。
- [ ] 暂存相关文件（`git add scripts/engineering/`，不暂存未跟踪垃圾）。
- [ ] 提交：`refactor(engineering): split check_engineering_docs.py into focused check modules`。
- [ ] push：`git push -u origin refactor/td-032-slice-2-check-engineering-docs`。
- [ ] PR：`gh pr create --title "refactor(engineering): TD-032 slice 2 — split check_engineering_docs.py" --body "..."`，
      body 含 Summary / Scope / Validation / Risks / Docs。
- [ ] `gh pr view --json state,mergeable,reviewDecision` 确认 `MERGEABLE`；`gh pr checks` 查
      CI（按现状 PR 未配置 CI；本仓库 gate 走本地 `scripts/check-engineering-docs` + pytest）。
- [ ] squash merge：`gh pr merge --squash --delete-branch`。
- [ ] 合并后回写：
  - `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：`check_engineering_docs.py`
    状态 `⚪ 待切片` → `🟢 已拆分` + 新行数（实测）+ 拆出去向。
  - `docs/03-engineering-governance/technical-debt.md#td-032`：备注追加「切片 2 已合并」+ PR 链接。
  - `docs/03-engineering-governance/work-log.md`：新增 1 行索引。
  - `docs/03-engineering-governance/current-work.md`：TD-032 任务卡「下一步」改为「切片 3 单独 spec / plan」。
  - 上述 docs-only 回写可以合并到 1 个原子 backfill commit（参考切片 1 的 `86a61bd`）。

## 任务拆分（按 plan-do 步骤）

1. 风险 2 提前验证（5 分钟）
2. `_common.py` + 8 个聚焦模块（按"由小到大"顺序，避免循环 import 风险）
3. `__init__.py` 注册表
4. 入口主文件瘦身
5. 14 个测试全过 + 仓库内 `scripts/check-engineering-docs` 行为零变化
6. 走完整 Git 流程
7. 合并后回写 4 处 docs

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 相对 import 在 `__main__` 模式下失败 | 实施步骤 §1 提前验证；失败时按 spec §风险 2 回退（绝对 import + sys.path 注入） |
| `KNOWN_CHECKS` 顺序与原 `run_checks` 中 `issues.extend(...)` 顺序不一致 | spec §3 明列顺序；实施步骤 §5 验证 baseline 行为时若发现顺序差异立即调整 |
| 拆分后 dataclass 引用循环（`_common` 引用 `technical_debt`，`technical_debt` 引用 `_common`） | 严格：`_common.py` 不 import 任何聚焦模块；`DebtDetail` 在 `_common.py` 唯一声明，`technical_debt.py` 反向 import |
| 测试意外失败（虽然行为零变化） | pytest 14 个测试只走 `subprocess` 黑盒，**不**直接 import 任何符号；行为零变化时测试必过 |
| 仓库 docs 状态在拆分过程中被门禁误报为"已实现"差异 | 实施步骤 §5-§6 多次跑 `scripts/check-engineering-docs`，确认输出文案与 baseline 字节级一致 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0，输出文案与 baseline 字节级一致。
- [ ] `pytest tests/engineering/test_check_engineering_docs.py` 14/14 通过。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件。
- [ ] `git diff --name-status` 只包含本任务 12 个文件；无业务代码、无生成物。
