"""DOC-059: 任务卡完成 → PR 真实存在兜底校验。

按 [technical-debt.md#doc-059](../../../../docs/03-engineering-governance/technical-debt.md#doc-059)
任务卡约束：

- 任务卡 L2071 原计划走 `gh pr list --state merged --search <ID>` 路径
  （49+ 次串行 gh，DOC-063 已重构成 git plumbing fast path）。
- DOC-059 收口时调整实现为 git log 兜底：DOC-060 已用
  `check_merge_commit_in_git_history` 覆盖『任务卡写明 PR 编号 + mergeCommit』
  维度；本模块只补『任务卡 🟢 完成但任务卡里既没写 PR 编号、也没写 Merge Commit
  字段』的兜底维度。
- 实现在 `_common.check_task_completion_pr_consistency_fallback` 通用函数 +
  本模块 `check` 入口。

与 DOC-060 (`check_task_card_stale_completion`) 互补：
- DOC-060 校验"任务卡写明的 PR 编号 / Merge Commit 字段"在 git history 真实存在；
- DOC-059 兜底扫"任务卡完成但未写 PR 字段"——本模块运行后会在 DOC-060 跳过
  的卡上报 1 个 issue，由两层门禁独立报警。
"""

from __future__ import annotations

from pathlib import Path

from ._common import Issue, check_task_completion_pr_consistency_fallback


def check(root: Path) -> list[Issue]:
    """DOC-059 入口：扫 3 份工程治理事实源的 🟢 完成 任务卡，git log 兜底校验。

    调用 `_common.check_task_completion_pr_consistency_fallback` 拆 3 份文档
    路径后批量调用。返回合并的 issue 列表。
    """
    return check_task_completion_pr_consistency_fallback(
        root / "docs/03-engineering-governance/technical-debt.md",
        root / "docs/03-engineering-governance/work-log.md",
        root / "docs/03-engineering-governance/current-work.md",
        repo_root=root,
    )


__all__ = ["check", "Issue"]
