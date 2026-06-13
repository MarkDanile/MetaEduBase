"""Engineering docs check 注册表。

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-2-check-engineering-docs-split.md`
约定的顺序导出 15 个 `check_*` 函数 + `KNOWN_CHECKS` 元组。`KNOWN_CHECKS` 的顺序
与原 `run_checks` 中 `issues.extend(...)` 完全一致，避免 issue 报告顺序变化。
"""

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
from .source_sizes import check_source_size_hard_limit
from .task_card_claims import (
    check_task_card_stale_completion,
    check_task_card_stale_residual,
)
from .task_ids import check_backlog_done_index, check_followup_ids
from .task_order import check_task_pool_order
from .task_pr_consistency import check as check_task_pr_consistency
from .technical_debt import check_completed_plans, check_technical_debt


KNOWN_CHECKS: tuple[Callable[[Path], list[Issue]], ...] = (
    check_legacy_doc_roots,
    check_current_work,
    check_recent_completed_work_log,
    check_req_status_consistency,
    check_product_planning_status_icons,
    check_followup_ids,
    check_backlog_done_index,
    check_task_pool_order,
    check_entry_sync,
    check_technical_debt,
    check_completed_plans,
    check_markdown_links,
    check_work_log_append_only,
    check_delivery_placeholders,
    check_validation_claims,
    check_scripted_gate_candidates,
    check_source_size_hard_limit,
    # DOC-060: 任务卡 vs 代码 / 声明语义校验。DOC-059 偏 PR 兜底维度，
    # DOC-060 偏代码 / 声明维度，互补覆盖"任务卡 → 实际状态"强校验缺口。
    check_task_card_stale_completion,
    check_task_card_stale_residual,
    # DOC-059: 兜底扫『任务卡 🟢 完成但未写 PR 编号 / Merge Commit 字段』，
    # 用 `git log --grep <ID>` 路径。任务卡 L2071 原 `gh pr list --search`
    # 路径已被 DOC-060/063 改用 git plumbing 取代；DOC-059 调整实现为 git
    # log 兜底（DOC-060 显式 skip "无 PR 字段"卡、本债补这个口子）。
    check_task_pr_consistency,
)


__all__ = ["KNOWN_CHECKS", "Issue"]
