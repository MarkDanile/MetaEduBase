"""Validate the atomic scope of a formal review-score submission.

The checker compares the final tree with the implementation baseline. It is
deliberately independent of GitHub so a score-only push can be verified in a
local hook or in CI without network access.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SCORE_LOG = "docs/03-engineering-governance/04-retrospectives/review-score-log.md"
BASE_SHA_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{7,40})(?![0-9a-f])", re.I)
FOLLOW_UP_RE = re.compile(r"\b(?:REQ|BUG|TD|DOC)-\d{3}\b(?!-)")
P0_P1_CLEAR_RE = re.compile(
    r"(?:P0\s*/\s*P1\s*=\s*0\b|P0\s*=\s*0\b\s*/\s*P1\s*=\s*0\b|P0\s*/\s*P1\s*(?:已)?清零)"
)


class CheckFailure(Exception):
    """A user-facing score submission validation failure."""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CheckFailure(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _read_baseline(root: Path, base: str) -> tuple[str, str]:
    base_oid = _git(root, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    content = _git(root, "show", f"{base_oid}:{SCORE_LOG}")
    return base_oid, content


def _table_cells(line: str) -> list[str]:
    body = line.rstrip("\r\n")
    if not body.lstrip().startswith("|") or not body.rstrip().endswith("|"):
        return []
    return [cell.strip() for cell in body.split("|")[1:-1]]


def _targets_pr(cells: list[str], pr_number: str) -> bool:
    return len(cells) >= 4 and bool(
        re.search(rf"(?:\[#|PR\s*#){re.escape(pr_number)}(?:\]|\b)", cells[3])
    )


def _single_inserted_line(before: list[str], after: list[str]) -> tuple[int, str]:
    candidates: list[tuple[int, str]] = []
    for index in range(len(after)):
        if after[:index] == before[:index] and after[index + 1 :] == before[index:]:
            candidates.append((index, after[index]))
    if len(candidates) != 1:
        raise CheckFailure(
            "review-score-log.md must be the baseline plus exactly one inserted line; "
            f"detected {len(candidates)} possible insertions"
        )
    return candidates[0]


def _score_table_first_row(lines: list[str]) -> int:
    try:
        score_heading = next(
            index for index, line in enumerate(lines) if line.strip() == "## Score Log"
        )
    except StopIteration as exc:
        raise CheckFailure("review-score-log.md is missing the `## Score Log` section") from exc

    for index in range(score_heading + 1, len(lines)):
        if lines[index].lstrip().startswith("|------"):
            return index + 1
        if lines[index].startswith("## "):
            break
    raise CheckFailure("Score Log table header is missing its separator row")


def _validate_inserted_row(
    row: str,
    *,
    pr_number: str,
    base_oid: str,
    baseline: str,
) -> None:
    cells = _table_cells(row)
    if len(cells) != 10:
        raise CheckFailure("the inserted score row must contain exactly 10 Score Log cells")
    if any(not cell for cell in cells):
        raise CheckFailure("the inserted score row must not contain empty Score Log cells")
    if cells[1] != "Original":
        raise CheckFailure("the inserted score row must be typed `Original`")
    if not _targets_pr(cells, pr_number):
        raise CheckFailure(f"the inserted score row does not target PR #{pr_number}")
    if not re.fullmatch(r"\d{1,3}", cells[4]) or not 0 <= int(cells[4]) <= 100:
        raise CheckFailure("the inserted score row must contain a score from 0 to 100")
    if not P0_P1_CLEAR_RE.search(cells[5]):
        raise CheckFailure("the inserted score row must include a cleared P0/P1 conclusion")
    if cells[6] != "无" and not FOLLOW_UP_RE.search(cells[6]):
        raise CheckFailure(
            "the inserted score row follow-up must be `无` or contain a stable task id"
        )
    if not re.search(r"(?:基线|baseline)", row, re.I):
        raise CheckFailure("the inserted score row must identify its implementation baseline")
    baseline_tokens = {token.lower() for token in BASE_SHA_RE.findall(row)}
    if not any(base_oid.startswith(token) for token in baseline_tokens):
        raise CheckFailure(
            "the inserted score row does not contain the requested implementation baseline "
            f"{base_oid[:12]}"
        )
    if any(_targets_pr(_table_cells(line), pr_number) for line in baseline.splitlines()):
        raise CheckFailure(f"review-score-log.md already contains a row for PR #{pr_number}")


def validate(root: Path, *, base: str, pr_number: str) -> None:
    """Validate a final score-only tree against an implementation baseline."""
    if not re.fullmatch(r"[1-9]\d*", pr_number):
        raise CheckFailure("--pr must be a positive numeric pull request number")
    base_oid, baseline = _read_baseline(root, base)
    current = _git(root, "show", f"HEAD:{SCORE_LOG}")

    changed = _git(root, "diff", "--name-status", "--no-renames", f"{base_oid}..HEAD", "--")
    changed_lines = [line for line in changed.splitlines() if line.strip()]
    if changed_lines != [f"M\t{SCORE_LOG}"]:
        raise CheckFailure(
            "final score submission may change only review-score-log.md; "
            f"detected: {changed_lines or ['no changes']}"
        )
    mode_changes = _git(
        root,
        "diff",
        "--summary",
        f"{base_oid}..HEAD",
        "--",
        SCORE_LOG,
    )
    if mode_changes.strip():
        raise CheckFailure("review-score-log.md file mode changed during the score submission")

    baseline_metrics = baseline.split("\n## Metrics Snapshot", 1)
    current_metrics = current.split("\n## Metrics Snapshot", 1)
    if len(baseline_metrics) != 2 or len(current_metrics) != 2:
        raise CheckFailure("review-score-log.md must contain `## Metrics Snapshot`")
    if baseline_metrics[1] != current_metrics[1]:
        raise CheckFailure("Metrics Snapshot changed during the formal score submission")

    before_lines = baseline.splitlines(keepends=True)
    after_lines = current.splitlines(keepends=True)
    insertion_index, inserted_row = _single_inserted_line(before_lines, after_lines)
    if insertion_index != _score_table_first_row(after_lines):
        raise CheckFailure("the new score row must be immediately below the Score Log header")
    _validate_inserted_row(
        inserted_row,
        pr_number=pr_number,
        base_oid=base_oid,
        baseline=baseline,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a baseline-scoped formal review-score submission."
    )
    parser.add_argument("--base", required=True, help="Implementation baseline commit/ref.")
    parser.add_argument("--pr", required=True, help="Current pull request number.")
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        validate(root, base=args.base, pr_number=args.pr)
    except (CheckFailure, UnicodeDecodeError) as exc:
        print(f"review-score-submit: {exc}", file=sys.stderr)
        return 1
    print(
        "review-score-submit: passed "
        f"(base {args.base}, PR #{args.pr}, one Original row, Metrics unchanged)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
