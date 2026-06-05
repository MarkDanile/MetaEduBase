#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DOC_GLOBS = (
    "docs/engineering/*.md",
    "docs/engineering/rules/*.md",
    "docs/specs/*.md",
    "docs/plans/*.md",
)

KNOWN_ISSUES = (
    (
        "docs/plans/2026-06-05-td-020-provider-resolver-factory-plan.md",
        "markdown-link",
        "TD-023",
    ),
    (
        "docs/specs/2026-06-05-td-020-provider-resolver-factory.md",
        "validation-claim",
        "TD-023",
    ),
    (
        "docs/plans/2026-06-05-td-020-provider-resolver-factory-plan.md",
        "validation-claim",
        "TD-023",
    ),
    ("docs/engineering/technical-debt.md", "validation-claim", "TD-023"),
)


@dataclass(frozen=True)
class Issue:
    path: Path
    line: int
    code: str
    message: str
    suggestion: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_known(issue: Issue, root: Path) -> bool:
    issue_path = rel(issue.path, root)
    return any(
        issue_path == known_path and issue.code == known_code
        for known_path, known_code, _reason in KNOWN_ISSUES
    )


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def section(lines: list[str], title: str) -> tuple[int, list[tuple[int, str]]]:
    start = -1
    for index, line in enumerate(lines, start=1):
        if line.strip() == f"## {title}":
            start = index
            break
    if start == -1:
        return -1, []

    body: list[tuple[int, str]] = []
    for index, line in enumerate(lines[start:], start=start + 1):
        if line.startswith("## "):
            break
        body.append((index, line))
    return start, body


def table_rows(body: list[tuple[int, str]]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for line_no, line in body:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(" ", "")) == set():
            continue
        if "任务 | 状态" in stripped or "日期 | 任务" in stripped:
            continue
        if "暂无" in stripped:
            continue
        rows.append((line_no, stripped))
    return rows


def check_current_work(root: Path) -> list[Issue]:
    path = root / "docs/engineering/current-work.md"
    lines = read_lines(path)
    issues: list[Issue] = []

    candidate_start, candidate_body = section(lines, "下一批候选任务")
    if candidate_start == -1:
        issues.append(
            Issue(
                path,
                1,
                "current-work",
                "缺少“下一批候选任务”区域。",
                "恢复 current-work.md 的近期候选任务区域。",
            )
        )
    else:
        candidates = table_rows(candidate_body)
        if len(candidates) > 3:
            issues.append(
                Issue(
                    path,
                    candidates[3][0],
                    "current-work",
                    "下一批候选任务最多 3 行。",
                    "只保留 1 到 3 个近期未完成候选，完整 backlog 回到事实源。",
                )
            )
        for line_no, row in candidates:
            if "🟢 完成" in row:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "current-work",
                        "候选区不得出现完成任务。",
                        "已完成任务应进入“最近完成”或 work-log，不留在候选区。",
                    )
                )

    recent_start, recent_body = section(lines, "最近完成")
    if recent_start == -1:
        issues.append(
            Issue(
                path,
                1,
                "current-work",
                "缺少“最近完成”区域。",
                "恢复 current-work.md 的最近完成摘要区域。",
            )
        )
    else:
        recent = table_rows(recent_body)
        if len(recent) > 5:
            issues.append(
                Issue(
                    path,
                    recent[5][0],
                    "current-work",
                    "最近完成最多 5 行。",
                    "最旧完成项应归档到 work-log 或对应事实源。",
                )
            )

    return issues


def is_completed_plan(text: str) -> bool:
    return "状态：🟢 完成" in text or "交付历史" in text and "合并到 `main`" in text


def allowed_active_checkbox(line: str) -> bool:
    lowered = line.lower()
    return "out of scope" in lowered or "td-" in lowered or "后续" in line


def check_completed_plans(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted((root / "docs/plans").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not is_completed_plan(text):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^\s*-\s\[\s\]", line) and not allowed_active_checkbox(line):
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "completed-plan-checkbox",
                        "已完成 plan 不得残留活动式 `- [ ]`。",
                        "改为历史记录 / `- [x]`，或绑定后续任务编号并标明 out of scope。",
                    )
                )
    return issues


LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def normalize_link_target(raw: str) -> str:
    target = raw.strip()
    if " " in target and not target.startswith("<"):
        target = target.split(" ", 1)[0]
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.split("#", 1)[0]


def should_skip_link(target: str) -> bool:
    return (
        not target
        or target.startswith("#")
        or target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
    )


def iter_doc_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(root.glob(pattern))
    return sorted(path for path in files if path.is_file())


def check_markdown_links(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        for line_no, line in enumerate(read_lines(path), start=1):
            for match in LINK_RE.finditer(line):
                target = normalize_link_target(match.group(1))
                if should_skip_link(target):
                    continue
                target_path = (
                    root / target.lstrip("/")
                    if target.startswith("/")
                    else path.parent / target
                ).resolve()
                if not target_path.exists():
                    issues.append(
                        Issue(
                            path,
                            line_no,
                            "markdown-link",
                            f"Markdown 链接目标不存在：{target}",
                            "修正相对路径，或将历史兼容链接迁入明确白名单。",
                        )
                    )
    return issues


def git_diff_work_log(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--unified=0", "--", "docs/engineering/work-log.md"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    if result.returncode not in (0, 1):
        return ""
    return result.stdout


def check_work_log_append_only(root: Path) -> list[Issue]:
    path = root / "docs/engineering/work-log.md"
    diff = git_diff_work_log(root)
    issues: list[Issue] = []
    for diff_line in diff.splitlines():
        if not diff_line.startswith("-|"):
            continue
        if "任务" in diff_line and "类型" in diff_line:
            continue
        if re.search(r"\b(?:TD|DOC|BUG)-\d{3}\b", diff_line):
            issues.append(
                Issue(
                    path,
                    1,
                    "work-log-append-only",
                    "work-log.md 默认只新增索引，不应无说明删除或替换已有任务行。",
                    "恢复被删除的索引；若必须删除，在任务文档或提交说明中写清原因。",
                )
            )
    return issues


VALIDATION_CLAIM_RE = re.compile(
    r"(全量\s+pytest\s+\d+\s+passed|(?:pytest|tests|ruff)[^。\n]*\bpassed\b)",
    re.IGNORECASE,
)
EVIDENCE_RE = re.compile(
    r"(Command:|Result:|Environment:|CI|PR checks|gh pr checks|退出码\s*0|`[^`]*(pytest|ruff)[^`]*`)",
    re.IGNORECASE,
)


def has_validation_evidence(lines: list[str], index: int) -> bool:
    window = "\n".join(lines[max(0, index - 2) : min(len(lines), index + 3)])
    return bool(EVIDENCE_RE.search(window))


def check_validation_claims(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        lines = read_lines(path)
        for index, line in enumerate(lines):
            if not VALIDATION_CLAIM_RE.search(line):
                continue
            if has_validation_evidence(lines, index):
                continue
            issues.append(
                Issue(
                    path,
                    index + 1,
                    "validation-claim",
                    "验证通过声明缺少可复核证据。",
                    "补充 Command / Result / Environment / CI 证据，或改写为未运行/当前环境不可运行。",
                )
            )
    return issues


def run_checks(root: Path) -> tuple[list[Issue], list[Issue]]:
    issues: list[Issue] = []
    issues.extend(check_current_work(root))
    issues.extend(check_completed_plans(root))
    issues.extend(check_markdown_links(root))
    issues.extend(check_work_log_append_only(root))
    issues.extend(check_validation_claims(root))

    active: list[Issue] = []
    known: list[Issue] = []
    for issue in issues:
        if is_known(issue, root):
            known.append(issue)
        else:
            active.append(issue)
    return active, known


def print_issue(issue: Issue, root: Path) -> None:
    sys.stderr.write(
        f"{rel(issue.path, root)}:{issue.line}: {issue.message}\n"
        f"  建议：{issue.suggestion}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check engineering docs gates.")
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    args = parser.parse_args(argv)

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
