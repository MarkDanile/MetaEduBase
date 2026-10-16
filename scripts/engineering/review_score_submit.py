"""Validate the atomic scope of a formal review-score submission.

The checker compares the final tree with the implementation baseline. It is
deliberately independent of GitHub so a score-only push can be verified in a
local hook or in CI without network access.

Row types: `Original`（每 PR 唯一，既有记录不可改/删/排）与 `Reassessment`
（DOC-082：正式评分后同 PR 再次发生返修时的追加复评；必须引用同 PR 上一条
评分行及其实现基线；拒绝孤立复评、跨 PR 引用与同实现基线重复入账；历史
分数不被覆盖，最新有效复评用于当前交付判断）。
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
DECLARED_BASE_LABEL_RE = re.compile(r"SCORE_BASE")
DECLARED_BASE_RE = re.compile(r"SCORE_BASE[^0-9a-f]{0,12}([0-9a-f]{7,40})", re.I)
PRIOR_BASE_LABEL_RE = re.compile(
    r"(?:implementation base|implementation head|实现基线|评分基线)"
    r"[^0-9a-f]{0,12}([0-9a-f]{7,40})",
    re.I,
)
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
    root: Path,
) -> None:
    cells = _table_cells(row)
    if len(cells) != 10:
        raise CheckFailure("the inserted score row must contain exactly 10 Score Log cells")
    if any(not cell for cell in cells):
        raise CheckFailure("the inserted score row must not contain empty Score Log cells")
    if cells[1] not in ("Original", "Reassessment"):
        raise CheckFailure(
            "the inserted score row must be typed `Original` or `Reassessment`"
        )
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
    prior_rows = [
        line
        for line in baseline.splitlines()
        if _targets_pr(_table_cells(line), pr_number)
    ]
    if cells[1] == "Original":
        # Original 每 PR 唯一：既有记录（Original、Reassessment 或 Backfilled）
        # 不可改、删、排，亦不得再追加第二条 Original。
        # 基线绑定保持既有宽松语义（行内含 --base 前缀 token 即可），向后兼容。
        baseline_tokens = {token.lower() for token in BASE_SHA_RE.findall(row)}
        if not any(base_oid.startswith(token) for token in baseline_tokens):
            raise CheckFailure(
                "the inserted score row does not contain the requested implementation "
                f"baseline {base_oid[:12]}"
            )
        if prior_rows:
            raise CheckFailure(
                f"review-score-log.md already contains a row for PR #{pr_number}"
            )
        return
    _validate_reassessment_row(
        row,
        baseline=baseline,
        prior_rows=prior_rows,
        pr_number=pr_number,
        base_oid=base_oid,
        root=root,
    )


def _tokens_match(left: str, right: str) -> bool:
    """两个 hex token 视为同一实现基线：相等或互为前缀（较短者长度 ≥ 7）。"""
    if left == right:
        return True
    short, long_ = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) >= 7 and long_.startswith(short)


def _formal_prior_rows(prior_rows: list[str]) -> list[str]:
    """同 PR 的正式评分行（Original / Reassessment）。

    Backfilled 是历史复盘补录，不得单独充当前序正式评分。
    """
    formal: list[str] = []
    for line in prior_rows:
        cells = _table_cells(line)
        if len(cells) >= 2 and cells[1] in ("Original", "Reassessment"):
            formal.append(line)
    return formal


def _recognize_row_baseline(row: str) -> str:
    """识别一条既有评分行自身的实现基线（明确规则，无任意 token 兜底）。

    顺序：先取 `SCORE_BASE` 标签后的 hex token（多个标签 token 必须一致）；
    若无标签 token，回退到 implementation base / implementation head /
    实现基线 / 评分基线 标签（同样必须唯一）。无法唯一识别即报错。
    """
    labeled = [token.lower() for token in DECLARED_BASE_RE.findall(row)]
    if len(set(labeled)) > 1:
        raise CheckFailure(
            "an existing score row has conflicting SCORE_BASE declarations; "
            "cannot identify its implementation baseline"
        )
    if labeled:
        return labeled[0]
    fallback = [token.lower() for token in PRIOR_BASE_LABEL_RE.findall(row)]
    if len(set(fallback)) > 1:
        raise CheckFailure(
            "an existing score row has multiple candidate implementation baselines; "
            "cannot uniquely identify one"
        )
    if fallback:
        return fallback[0]
    raise CheckFailure(
        "an existing score row has no recognizable implementation baseline label "
        "(SCORE_BASE / implementation base / 实现基线 / 评分基线)"
    )


def _resolve_declared_base(token: str, base_oid: str, root: Path) -> None:
    """声明基线必须与 --base 解析出的 commit 一致；短 SHA 仅当无前缀歧义。

    完整 40 位要求逐字相等；7–39 位短 SHA 要求既是 base_oid 前缀、又在仓库
    对象库中经 `git rev-parse --disambiguate` 唯一解析到 base_oid。
    """
    if len(token) == 40:
        if token != base_oid.lower():
            raise CheckFailure(
                "the declared SCORE_BASE does not match the --base commit "
                f"{base_oid[:12]} (declared {token[:12]}…)"
            )
        return
    if not base_oid.lower().startswith(token):
        raise CheckFailure(
            "the declared SCORE_BASE does not match the --base commit "
            f"{base_oid[:12]} (declared {token}…)"
        )
    matches = [
        line.strip() for line in _git(root, "rev-parse", f"--disambiguate={token}").splitlines() if line.strip()
    ]
    if len(matches) != 1 or matches[0].lower() != base_oid.lower():
        raise CheckFailure(
            f"the declared short SCORE_BASE `{token}` is ambiguous in this repository; "
            "use the full 40-char SHA"
        )


def _validate_reassessment_row(
    row: str,
    *,
    baseline: str,
    prior_rows: list[str],
    pr_number: str,
    base_oid: str,
    root: Path,
) -> None:
    """Reassessment 专属规则（Original 的所有共享保护在调用方已先行通过）。

    - 孤立复评拒绝：同 PR 必须已有正式评分行（Original 或 Reassessment；
      Backfilled 不得单独充当前序）。
    - 本次基线严格绑定：恰一个 `SCORE_BASE` 声明，且其值与 --base 解析出的
      commit 一致（短 SHA 仅当无歧义）；行内其他位置出现真实 SHA 不能替代
      该字段。
    - 前序引用精确绑定：复投行必须引用同 PR 最近一条正式评分行**自身的**
      实现基线（按 _recognize_row_baseline 的明确规则识别），匹配该行中
      的祖先引用或其他 SHA 不算数。
    - 同一实现基线重复入账拒绝：本次声明基线不得就是上一条行的基线。
    """
    formal = _formal_prior_rows(prior_rows)
    if not formal:
        raise CheckFailure(
            f"orphan reassessment: no prior formal (Original/Reassessment) score "
            f"row exists for PR #{pr_number}"
        )
    label_count = len(DECLARED_BASE_LABEL_RE.findall(row))
    if label_count != 1:
        raise CheckFailure(
            "the reassessment row must contain exactly one `SCORE_BASE` declaration "
            f"for the current baseline (found {label_count}); references to prior "
            "baselines must not use the `SCORE_BASE` label"
        )
    declared = [token.lower() for token in DECLARED_BASE_RE.findall(row)]
    if len(declared) != 1:
        raise CheckFailure(
            "the reassessment row's `SCORE_BASE` declaration must carry exactly one "
            "hex token"
        )
    declared_token = declared[0]
    _resolve_declared_base(declared_token, base_oid, root)
    previous_base = _recognize_row_baseline(formal[0])
    if _tokens_match(declared_token, previous_base):
        raise CheckFailure(
            f"implementation baseline {declared_token[:12]}… is already covered by the "
            f"previous score row for PR #{pr_number}"
        )
    reference_tokens = [
        token.lower()
        for token in BASE_SHA_RE.findall(row)
        if not _tokens_match(token.lower(), declared_token)
    ]
    if not any(_tokens_match(token, previous_base) for token in reference_tokens):
        raise CheckFailure(
            "the reassessment row must reference the previous formal score row's own "
            f"implementation baseline for PR #{pr_number} (matching an ancestor or "
            "unrelated SHA does not count)"
        )


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
        root=root,
    )
    return _table_cells(inserted_row)[1]


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
        row_type = validate(root, base=args.base, pr_number=args.pr)
    except (CheckFailure, UnicodeDecodeError) as exc:
        print(f"review-score-submit: {exc}", file=sys.stderr)
        return 1
    print(
        "review-score-submit: passed "
        f"(base {args.base}, PR #{args.pr}, one {row_type} row, Metrics unchanged)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
