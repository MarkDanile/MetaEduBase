"""占位 / 验证声明族：`check_delivery_placeholders` / `check_validation_claims`."""

from __future__ import annotations

import re
from pathlib import Path

from ._common import Issue, iter_doc_files, read_lines


DELIVERY_PLACEHOLDER_RE = re.compile(
    r"(即将入|待提交|提交后更新|以最终回复为准|待最终确认)"
)
NORMATIVE_PLACEHOLDER_RE = re.compile(r"(不得|禁止|不能|不要|例如|示例|占位)")
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


def check_delivery_placeholders(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        for line_no, line in enumerate(read_lines(path), start=1):
            if not DELIVERY_PLACEHOLDER_RE.search(line):
                continue
            if NORMATIVE_PLACEHOLDER_RE.search(line):
                continue
            issues.append(
                Issue(
                    path,
                    line_no,
                    "delivery-placeholder",
                    "交付事实源中残留提交或最终回复占位。",
                    "回填真实 PR / commit / 验证结果，或删除过期占位。",
                )
            )
    return issues


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
