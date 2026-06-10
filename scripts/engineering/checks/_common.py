"""Shared dataclasses, constants, regexes, and small parse helpers.

集中放 cross-check 公共符号。所有聚焦模块从此处 import；本模块**不**引用任何
聚焦模块，避免循环。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DOC_GLOBS: tuple[str, ...] = (
    "docs/*.md",
    "docs/03-engineering-governance/*.md",
    "docs/03-engineering-governance/02-baselines/*.md",
    "docs/03-engineering-governance/03-matrices/*.md",
    "docs/03-engineering-governance/04-retrospectives/*.md",
    "docs/03-engineering-governance/01-rules/*.md",
    "docs/01-product-planning/*.md",
    "docs/01-product-planning/*/*.md",
    "docs/02-delivery-plans/01-specs/*.md",
    "docs/02-delivery-plans/02-plans/*.md",
)

CURRENT_WORK_RECENT_LIMIT = 20
CURRENT_WORK_RECENT_SUMMARY_LIMIT = 220
LEGACY_DOC_ROOT_NAMES: tuple[str, ...] = (
    "engineering",
    "specs",
    "plans",
    "product",
    "superpowers",
)
TASK_ID_RE = re.compile(r"\b(?:REQ|TD|DOC|BUG|APP)-\d{3}\b")
# REQ-NNN (parent) and REQ-NNN-K (child subtask) are distinct task ids.
# DOC-056: prior `\bREQ-\d{3}\b` matched `REQ-002` inside `REQ-002-3`,
# causing `check_req_status_consistency` to merge parent/child statuses.
# The trailing `(?![-\d])` prevents backtracking into a parent prefix
# while still allowing whitespace / `.md` / end-of-string after the id.
REQ_ID_RE = re.compile(r"\bREQ-\d{3}(?:-\d+)?(?![-\d])")
FOLLOWUP_ID_RE = re.compile(r"\b(?:REQ|TD)-\d{3}-FOLLOWUP\b")
LEGACY_FOLLOWUP_REFS: frozenset[tuple[str, str]] = frozenset(
    {
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-006-llm-model-fallback.md", "TD-006-FOLLOWUP"),
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-007-databaseview-vue-query.md", "TD-007-FOLLOWUP"),
        ("docs/03-engineering-governance/technical-debt.md", "TD-002-FOLLOWUP"),
        ("docs/03-engineering-governance/work-log.md", "TD-002-FOLLOWUP"),
    }
)
BACKLOG_DONE_TYPES: frozenset[str] = frozenset({"REQ", "DOC", "BUG", "APP"})
SCRIPTED_GATE_CANDIDATES: frozenset[str] = frozenset(
    {
        "`current-work.md` 最近完成最多 20 行",
        "`current-work.md` 下一批候选最多 3 行，且不允许 `🟢 完成`",
        "已完成任务不得残留 `未运行`、`待提交`、`以最终回复为准` 等占位",
        "禁止把 `REQ-xxx-FOLLOWUP` / `TD-xxx-FOLLOWUP` 作为长期任务编号",
        "`Done` 任务在 Backlog / current-work / work-log 之间有最小索引闭环",
        "旧 docs 路径残留检查",
        "Markdown 相对链接存在性检查",
        "AGENTS.md / CLAUDE.md 与 IDE 兼容入口同步检查",
        "源码文件超过 1000 行硬限制检查",
    }
)

KNOWN_ISSUES: tuple[tuple[str, str, str], ...] = ()

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class Issue:
    path: Path
    line: int
    code: str
    message: str
    suggestion: str


@dataclass(frozen=True)
class DebtDetail:
    line: int
    status: str | None
    body: list[tuple[int, str]]


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


def split_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def iter_doc_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(root.glob(pattern))
    return sorted(path for path in files if path.is_file())


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
