# TD-032 切片 2 拆分 `check_engineering_docs.py`（>1000 行）— Spec

## 背景

`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 把
`scripts/engineering/check_engineering_docs.py`（1003 行）登记为「⚪ 待切片」。

它是 TD-032 切片 1（已合并，[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92) /
merge `3de4de5`）建立基线 + 原则之后，按 `docs/02-delivery-plans/02-plans/2026-06-08-td-032-large-source-files-plan.md#切片-2` 计划的第一个业务级拆分目标。

主文件实际职责盘点（基于当前 1003 行）：

| 段（行号） | 内容 | 行数 | 拆分去向 |
|------------|------|------|----------|
| 入口与 argv | `main` + `argparse`（`--root`）+ `print_issue` | 1003-1022（重构后） | 入口主文件 |
| 公共数据/常量 | `DOC_GLOBS`、7 个 `*_RE` 正则、`PRODUCT_STATUS_NAMES`、`LEGACY_FOLLOWUP_REFS`、`BACKLOG_DONE_TYPES`、`SCRIPTED_GATE_CANDIDATES`、`KNOWN_ISSUES`、4 个 limit/regex 常量 | 12-86 | `checks/_common.py` |
| dataclass | `Issue`、`DebtDetail` | 89-95、678-683 | `checks/_common.py` |
| 路径/读取/小工具 | `rel`、`is_known`、`read_lines`、`section`、`table_rows`、`split_table_row`、`iter_doc_files`、`normalize_link_target`、`should_skip_link` | 98-154、816-826、828-842、105-110 | `checks/_common.py` |
| 状态归一 / 产品规划状态 | `normalize_status`、`is_product_status`、`has_product_status_icon` | 288-309 | `checks/product_planning.py` |
| current-work 族 | `parse_current_work_completed_ids`、`check_current_work`、`check_recent_completed_work_log` | 156-248、251-285 | `checks/current_work.py` |
| product planning 族 | `check_product_planning_status_icons`、`collect_backlog_req_statuses`、`collect_requirement_file_statuses`、`collect_iteration_req_statuses`、`collect_milestone_req_statuses`、`collect_current_work_req_statuses`、`merge_status_maps`、`check_req_status_consistency` | 312-481 | `checks/product_planning.py` |
| task ID 卫生 | `check_followup_ids`、`collect_backlog_done_tasks`、`has_fact_source`、`check_backlog_done_index` | 504-566、524-541、544-547 | `checks/task_ids.py` |
| 入口同步 | `normalize_entry_lines`、`check_entry_sync` | 569-629 | `checks/entry_sync.py` |
| technical-debt 族 | `DETAIL_HEADING_RE`、`STATUS_LINE_RE`、`parse_debt_overview`、`parse_debt_details`、`delivery_record_lines`、`check_technical_debt`、`is_completed_plan`、`allowed_active_checkbox`、`check_completed_plans` | 674-813 | `checks/technical_debt.py` |
| 链接/路径 | `check_legacy_doc_roots`、`check_markdown_links`、`git_diff_work_log`、`check_work_log_append_only` | 632-671、816-906 | `checks/links_paths.py` |
| 占位/验证声明 | `check_delivery_placeholders`、`VALIDATION_CLAIM_RE`、`EVIDENCE_RE`、`has_validation_evidence`、`check_validation_claims` | 484-501、909-942 | `checks/placeholders_claims.py` |
| 脚本候选 | `check_scripted_gate_candidates` | 632-653 | `checks/gate_candidates.py` |
| 编排 | `run_checks` | 945-970 | 入口主文件 |

`tests/engineering/test_check_engineering_docs.py`（460 行）走 `subprocess` 黑盒跑
`scripts/engineering/check_engineering_docs.py --root <tmp>`，**不** import 任何内部符号。
这意味着 CLI 行为（退出码 0/1、stdout `engineering docs checks passed`、stderr 文案
片段）是 14 个测试唯一约束的事实源——任何拆分只要保持 CLI 行为零变化，测试就过。

## 目标

1. 把 1003 行的 `scripts/engineering/check_engineering_docs.py` 拆为「入口主文件 +
   9 个聚焦 `checks/*.py` 模块」，主文件目标 ≤300 行（编排 + 入口）。
2. **零业务行为变化**：所有 `check_*` 函数与采集器的语义、`KNOWN_ISSUES` allowlist 8 项、
   CLI 退出码与文案均保持 byte-identical。
3. 入口脚本 `scripts/check-engineering-docs`（仅 17 行 `runpy.run_path`）**不**改。
4. 现有 14 个 `tests/engineering/test_check_engineering_docs.py` 测试用例 100% 通过。
5. `scripts/check-engineering-docs` 在仓库内继续返回 0 / 失败摘要与现状一致（baseline
   行为零变化）。

## 范围

### In scope

- 新建 `scripts/engineering/__init__.py`（空包）。
- 新建 `scripts/engineering/checks/__init__.py`：从 9 个聚焦模块 re-export 所有 `check_*` 函数，
  并暴露 `KNOWN_CHECKS: list[Callable[[Path], list[Issue]]]` 供入口聚合。
- 新建 9 个聚焦模块（每文件 30~150 行）：
  - `scripts/engineering/checks/_common.py` — `Issue` / `DebtDetail` dataclass、`rel` /
    `is_known` / `read_lines` / `section` / `table_rows` / `split_table_row` /
    `iter_doc_files` / `normalize_link_target` / `should_skip_link`、6 个公共常量
    （`DOC_GLOBS`、`LEGACY_DOC_ROOT_NAMES`、`LEGACY_FOLLOWUP_REFS`、`BACKLOG_DONE_TYPES`、
    `SCRIPTED_GATE_CANDIDATES`、`KNOWN_ISSUES`）、3 个 `*_RE`（`TASK_ID_RE` /
    `REQ_ID_RE` / `FOLLOWUP_ID_RE` / `LINK_RE`）。
  - `scripts/engineering/checks/current_work.py` — 3 个函数
    `check_current_work` / `check_recent_completed_work_log` / `parse_current_work_completed_ids`。
  - `scripts/engineering/checks/product_planning.py` — `normalize_status` / `is_product_status` /
    `has_product_status_icon` / `check_product_planning_status_icons` / 5 个
    `collect_*_req_statuses` / `merge_status_maps` / `check_req_status_consistency` /
    `PRODUCT_STATUS_ICON_RE` / `PRODUCT_STATUS_NAMES`。
  - `scripts/engineering/checks/task_ids.py` — `check_followup_ids` /
    `check_backlog_done_index` / `collect_backlog_done_tasks` / `has_fact_source`。
  - `scripts/engineering/checks/entry_sync.py` — `check_entry_sync` / `normalize_entry_lines`。
  - `scripts/engineering/checks/technical_debt.py` — `check_technical_debt` /
    `check_completed_plans` / `parse_debt_overview` / `parse_debt_details` /
    `delivery_record_lines` / `is_completed_plan` / `allowed_active_checkbox` /
    `DebtDetail` 复用 + `DETAIL_HEADING_RE` / `STATUS_LINE_RE`。
    （`DebtDetail` 在 `_common.py` 与本模块都被引用——只在 `_common.py` 声明一次，
    `technical_debt.py` import 使用。）
  - `scripts/engineering/checks/links_paths.py` — `check_legacy_doc_roots` /
    `check_markdown_links` / `check_work_log_append_only` / `git_diff_work_log`。
  - `scripts/engineering/checks/placeholders_claims.py` — `check_delivery_placeholders` /
    `check_validation_claims` / `has_validation_evidence` / `DELIVERY_PLACEHOLDER_RE` /
    `NORMATIVE_PLACEHOLDER_RE` / `VALIDATION_CLAIM_RE` / `EVIDENCE_RE`。
  - `scripts/engineering/checks/gate_candidates.py` — `check_scripted_gate_candidates`。
- 精简 `scripts/engineering/check_engineering_docs.py`：
  - 保留：`main` / `argparse` / `run_checks` / `print_issue` / `if __name__ == "__main__"`。
  - 删除：所有 `check_*` / `collect_*` / 工具函数与本地常量（迁到上述模块）。
  - 入口主文件目标 ≤300 行。
- 不动 `scripts/check-engineering-docs`（兼容入口，仅 17 行 `runpy.run_path`）。
- 不动 `tests/engineering/test_check_engineering_docs.py`（测试本身就是行为基线，
  不能为拆分而改测试）。
- 不动任何 docs。

### Out of scope

- 不在本次拆分中**修改**任何 check 的语义、文案、`KNOWN_ISSUES` 列表、退出码、
  stdout/stderr 输出格式。
- 不动 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`
  表里 `main.css` / 后端 / 前端超大文件（属于切片 3-4+ 范围）。
- 不动 `main.css`、`document/tasks.py`、`structured_data/tasks.py`、
  `DatabaseView.vue`、`TemplateModal.vue`（属于切片 3-4 范围）。
- 不动 `scripts/engineering/check_engineering_docs.py` 之外的工程脚本。
- 不引入新依赖。
- 不改 `pyproject.toml` / `setup.py` / `requirements*.txt`。

## 设计要点

### 1. 拆分粒度：按"检查族"对齐

按 `docs/03-engineering-governance/01-rules/coding-style.md#拆分层级-td-032` 中
「CSS / 工程脚本」行的指导「拆模块文件 + 入口聚合」，把当前 14 个 `check_*` 函数按
"检查族"归并到 9 个聚焦模块：

| 模块 | 主题 | 依赖的 `_common` 工具 |
|------|------|------------------------|
| `_common.py` | dataclass + 公共解析 + 公共常量 | — |
| `current_work.py` | current-work 状态机 | `Issue` / `section` / `table_rows` / `split_table_row` / `read_lines` |
| `product_planning.py` | 产品规划层状态 + 跨事实源一致性 | `Issue` / `rel` / `section` / `table_rows` / `split_table_row` / `read_lines` / `REQ_ID_RE` |
| `task_ids.py` | follow-up / backlog done 索引 | `Issue` / `rel` / `iter_doc_files` / `read_lines` / `FOLLOWUP_ID_RE` / `TASK_ID_RE` / `BACKLOG_DONE_TYPES` |
| `entry_sync.py` | 入口同步 | `Issue` / `read_lines` |
| `technical_debt.py` | 技术债总账一致性 | `Issue` / `section` / `table_rows` / `split_table_row` / `read_lines` / `DebtDetail` |
| `links_paths.py` | 链接 / 旧路径 / work-log append-only | `Issue` / `iter_doc_files` / `read_lines` / `rel` / `LINK_RE` / `LEGACY_DOC_ROOT_NAMES` |
| `placeholders_claims.py` | 交付占位 / 验证声明 | `Issue` / `iter_doc_files` / `read_lines` / `DELIVERY_PLACEHOLDER_RE` / `NORMATIVE_PLACEHOLDER_RE` / `VALIDATION_CLAIM_RE` / `EVIDENCE_RE` |
| `gate_candidates.py` | 脚本候选反查 | `Issue` / `section` / `table_rows` / `split_table_row` / `read_lines` / `SCRIPTED_GATE_CANDIDATES` |

### 2. 公共常量在 `_common.py` 集中

把以下常量迁到 `checks/_common.py`，每个聚焦模块按需 import：

```python
DOC_GLOBS: tuple[str, ...] = (...)
LEGACY_DOC_ROOT_NAMES: tuple[str, ...] = (...)
LEGACY_FOLLOWUP_REFS: frozenset[tuple[str, str]] = frozenset({...})
BACKLOG_DONE_TYPES: frozenset[str] = frozenset({...})
SCRIPTED_GATE_CANDIDATES: frozenset[str] = frozenset({...})
KNOWN_ISSUES: tuple[tuple[str, str, str], ...] = (...)

TASK_ID_RE: re.Pattern[str] = re.compile(...)
REQ_ID_RE: re.Pattern[str] = re.compile(...)
FOLLOWUP_ID_RE: re.Pattern[str] = re.compile(...)
LINK_RE: re.Pattern[str] = re.compile(...)
```

`KNOWN_ISSUES` 含 8 条元组 `(path, code, reason)`，**路径字符串原样保留**；
`is_known(issue, root)` 也迁到 `_common.py`，因为它需要访问 `KNOWN_ISSUES` + `rel`。

`Issue` / `DebtDetail` 在 `_common.py` 唯一声明；`technical_debt.py` 通过
`from ._common import DebtDetail` 复用。

### 3. `__init__.py` 作为注册表

`scripts/engineering/checks/__init__.py` 仅做 re-export 与注册：

```python
from __future__ import annotations
from collections.abc import Callable
from pathlib import Path

from ._common import Issue
from .current_work import check_current_work, check_recent_completed_work_log
from .entry_sync import check_entry_sync
from .gate_candidates import check_scripted_gate_candidates
from .links_paths import (
    check_legacy_doc_roots,
    check_markdown_links,
    check_work_log_append_only,
)
from .placeholders_claims import (
    check_delivery_placeholders,
    check_validation_claims,
)
from .product_planning import (
    check_product_planning_status_icons,
    check_req_status_consistency,
)
from .task_ids import check_backlog_done_index, check_followup_ids
from .technical_debt import check_completed_plans, check_technical_debt

KNOWN_CHECKS: tuple[Callable[[Path], list[Issue]], ...] = (
    check_legacy_doc_roots,
    check_current_work,
    check_recent_completed_work_log,
    check_req_status_consistency,
    check_product_planning_status_icons,
    check_followup_ids,
    check_backlog_done_index,
    check_entry_sync,
    check_technical_debt,
    check_completed_plans,
    check_markdown_links,
    check_work_log_append_only,
    check_delivery_placeholders,
    check_validation_claims,
    check_scripted_gate_candidates,
)

__all__ = ["KNOWN_CHECKS", "Issue"]
```

`KNOWN_CHECKS` 的顺序保持与现有 `run_checks` 中的 `issues.extend(...)` 一致，
确保 issue 报告顺序（隐式）和现状一致。`is_known(issue, root)` 不出现在注册表
中——它仍由 `run_checks` 编排逻辑调用，迁到入口主文件：

```python
from .checks import KNOWN_CHECKS, Issue
from .checks._common import KNOWN_ISSUES, is_known

def run_checks(root: Path) -> tuple[list[Issue], list[Issue]]:
    issues: list[Issue] = []
    for check in KNOWN_CHECKS:
        issues.extend(check(root))
    active: list[Issue] = []
    known: list[Issue] = []
    for issue in issues:
        if is_known(issue, root):
            known.append(issue)
        else:
            active.append(issue)
    return active, known
```

注意 `KNOWN_CHECKS` 中没有 `parse_current_work_completed_ids` /
`collect_backlog_req_statuses` 等私有采集器——它们是 `check_*` 函数的实现细节，
只在该聚焦模块内部使用，**不**对外暴露。`KNOWN_CHECKS` 共 15 个 check 函数，
与原 `run_checks` 中 `issues.extend(...)` 顺序一致：
`check_legacy_doc_roots` → `check_current_work` → `check_recent_completed_work_log` →
`check_req_status_consistency` → `check_product_planning_status_icons` →
`check_followup_ids` → `check_backlog_done_index` → `check_entry_sync` →
`check_technical_debt` → `check_completed_plans` → `check_markdown_links` →
`check_work_log_append_only` → `check_delivery_placeholders` →
`check_validation_claims` → `check_scripted_gate_candidates`。

### 4. 入口主文件瘦身目标

入口 `check_engineering_docs.py` 目标 ≤300 行；只保留：

1. `from __future__ import annotations`
2. `import argparse, sys` + `from pathlib import Path`
3. `from .checks import KNOWN_CHECKS, Issue`
4. `from .checks._common import is_known`
5. `def run_checks(...)`（≤15 行）
6. `def print_issue(...)`（≤10 行）
7. `def main(argv) -> int`（≤20 行：argparse + 调用 + 输出 known 数量）
8. `if __name__ == "__main__": raise SystemExit(main())`

预期 ≤70 行，加上空行 / 注释 / docstring / 类型注解在 100~150 行内。

## 完成标准

1. `scripts/engineering/check_engineering_docs.py` 行数 ≤300。
2. `scripts/engineering/checks/` 目录存在，9 个聚焦模块 + 1 个 `__init__.py` 全部就位。
3. `scripts/engineering/__init__.py` 存在（空包）。
4. 入口脚本 `scripts/check-engineering-docs` 内容**完全不变**（仍 17 行 `runpy.run_path`）。
5. `python scripts/engineering/check_engineering_docs.py --root .` 在仓库内退出码为 0，stdout
   包含 `engineering docs checks passed`（与现状一致；当前 main 上 0 active、0 known
   allowlist 命中；`KNOWN_ISSUES` 8 条作为历史 allowlist 保留但当前不触发）。
6. `pytest tests/engineering/test_check_engineering_docs.py -v` 16 个测试用例全部通过
   （baseline 实测 16 passed；spec 初稿写"14 个"是计数错误）。
7. `git diff --name-status` 仅包含：
   - `scripts/engineering/__init__.py`（A）
   - `scripts/engineering/check_engineering_docs.py`（M）
   - `scripts/engineering/checks/__init__.py`（A）
   - `scripts/engineering/checks/_common.py`（A）
   - `scripts/engineering/checks/current_work.py`（A）
   - `scripts/engineering/checks/product_planning.py`（A）
   - `scripts/engineering/checks/task_ids.py`（A）
   - `scripts/engineering/checks/entry_sync.py`（A）
   - `scripts/engineering/checks/technical_debt.py`（A）
   - `scripts/engineering/checks/links_paths.py`（A）
   - `scripts/engineering/checks/placeholders_claims.py`（A）
   - `scripts/engineering/checks/gate_candidates.py`（A）
8. `scripts/check-engineering-docs` 不在本 PR diff 中。
9. 提交信息遵循 Conventional Commits：`refactor(engineering): split check_engineering_docs.py into focused check modules`。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选后端 Python 行：

```bash
# 行为基线（拆分前后必须一致）
python scripts/engineering/check_engineering_docs.py --root .
echo "exit=$?"

# 入口脚本兼容入口
scripts/check-engineering-docs
echo "exit=$?"

# 单元测试
.venv/bin/python -m pytest tests/engineering/test_check_engineering_docs.py -v
# 或在没有 venv 时
python -m pytest tests/engineering/test_check_engineering_docs.py -v

# 行数目标
wc -l scripts/engineering/check_engineering_docs.py scripts/engineering/checks/*.py
```

按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为纯重构（拆分模块），所有 14 个 `check_*` 函数与 `KNOWN_ISSUES` allowlist
> 行为零变化；CLI 退出码与 stdout/stderr 文本与拆分前 byte-equivalent。
> 当前 main 上 `KNOWN_ISSUES` 8 条 allowlist 全部不触发（实测 0 active / 0 known），
> 拆分后实测必须保持一致。

## 风险与后续

- **风险 1**：`KNOWN_CHECKS` 注册表顺序与 `run_checks` 中 `issues.extend(...)` 顺序
  不一致，导致 `Issue` 报告顺序与现状不同（虽然测试只看 stderr 文案是否命中，但
  后续手工人眼观察会感知）。缓解：注册表按现有顺序写，并在 PR 描述中明确
  `KNOWN_CHECKS` 与原 `run_checks` 的 `extend` 顺序一致。
- **风险 2**：`from ._common import ...` 相对 import 在 `python path/to/file.py` 直跑
  模式下会失败（需要 `python -m scripts.engineering.check_engineering_docs`）。
  缓解：现有入口脚本 `scripts/check-engineering-docs` 用 `runpy.run_path(TOOL,
  run_name="__main__")`，把主文件作为 `__main__` 跑；相对 import 在 `__main__`
  上下文下需通过 `package=True` 解析。**需要在 spec §5.2 验证阶段确认：
  `python scripts/engineering/check_engineering_docs.py --root .` 仍能退出码 0**；
  若相对 import 失败，回退方案是把入口从单文件移到 `scripts/engineering/__main__.py`，
  但这会改 `scripts/check-engineering-docs` 的 `TOOL` 路径——属于 §5.4 的禁止项，
  所以**回退方案不可接受**。更稳的写法是 `from scripts.engineering.checks import ...`，
  配合 `sys.path` 调整，或在 `check_engineering_docs.py` 顶部用
  `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` 显式注入。
  计划在 plan §实施步骤里把"相对 import 验证"作为第一步。
- **风险 3**：拆分后 `_common.py` 的 import 链形成循环（`technical_debt.py` 引用
  `_common.DebtDetail`；`_common` 不引用 `technical_debt`）。缓解：`_common.py` 只
  放 dataclass + 工具 + 公共常量 + 公共正则，**不**引用任何聚焦模块。
- **后续**：切片 3-4（`document/tasks.py` / `structured_data/tasks.py` /
  `DatabaseView.vue` / `TemplateModal.vue` 拆分）由各自独立 spec / plan 承载。
- **后续**：本次拆分为 `check_engineering_docs.py` 重构开了"主入口 ≤300 行 + 聚焦
  模块"的可复用模板；如果该模式被工程治理层认可，可由 `DOC-xxx` 任务把
  "工程脚本按检查族拆分"补到 `coding-style.md#拆分层级` 段，但本 PR 范围内不强制
  改 `coding-style.md`。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把 TD-032 任务卡的
「下一步」从「切片 2 单独 spec / plan」改为「切片 2 已合并；切片 3 待开工」；
`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 中
`check_engineering_docs.py` 状态从 `⚪ 待切片` 改为 `🟢 已拆分` 并写新行数；
`docs/03-engineering-governance/technical-debt.md#td-032` 备注追加「切片 2 已合并」；
`docs/03-engineering-governance/work-log.md` 加一行索引。
