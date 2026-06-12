#!/usr/bin/env python3
"""Engineering docs gate — entrypoint.

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-2-check-engineering-docs-split.md`
拆分自原 1003 行单文件。实际 check 全部在 `scripts.engineering.checks.*` 子模块中，
本文件只负责 `argparse` / `run_checks` 编排 / 输出 / 退出码。

入口脚本 `scripts/check-engineering-docs`（17 行 `runpy.run_path`）保持不变。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.engineering.checks import KNOWN_CHECKS, Issue  # noqa: E402
from scripts.engineering.checks._common import is_known  # noqa: E402


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


def print_issue(issue: Issue, root: Path) -> None:
    from scripts.engineering.checks._common import rel

    sys.stderr.write(
        f"{rel(issue.path, root)}:{issue.line}: {issue.message}\n"
        f"  建议：{issue.suggestion}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check engineering docs gates.")
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    parser.add_argument(
        "--verify-pr-state",
        action="store_true",
        help=(
            "DOC-063: opt-in 启用 `gh pr view` 校验 PR 真实状态（慢速，~1s/次，"
            "可能超时）。默认走 `git rev-parse` 校验任务卡 mergeCommit 字段（< 5ms/次，零网络）。"
        ),
    )
    args = parser.parse_args(argv)

    if args.verify_pr_state:
        # 触发 task_card_claims 的 gh 路径（DOC-063 legacy）。
        import os
        os.environ["METAEDU_CHECK_VERIFY_PR_STATE"] = "1"

    root = Path(args.root).resolve()
    active, known = run_checks(root)

    for issue in active:
        print_issue(issue, root)
    if active:
        return 1

    if known:
        sys.stdout.write(
            f"engineering docs checks passed ({len(known)} known issue(s) allowlisted)\n"
        )
    else:
        sys.stdout.write("engineering docs checks passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
