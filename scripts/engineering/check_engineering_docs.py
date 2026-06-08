#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DOC_GLOBS = (
    "docs/*.md",
    "docs/03-engineering-governance/*.md",
    "docs/03-engineering-governance/03-retrospectives/*.md",
    "docs/03-engineering-governance/01-rules/*.md",
    "docs/01-product-planning/*.md",
    "docs/01-product-planning/*/*.md",
    "docs/02-delivery-plans/01-specs/*.md",
    "docs/02-delivery-plans/02-plans/*.md",
)

CURRENT_WORK_RECENT_SUMMARY_LIMIT = 220
LEGACY_DOC_ROOT_NAMES = ("engineering", "specs", "plans", "product", "superpowers")
TASK_ID_RE = re.compile(r"\b(?:REQ|TD|DOC|BUG|APP)-\d{3}\b")
REQ_ID_RE = re.compile(r"\bREQ-\d{3}\b")
PRODUCT_STATUS_ICON_RE = re.compile(r"^[⚪⚫🔵🟡🔴🟣🟢]\s+")
PRODUCT_STATUS_NAMES = frozenset(
    {
        "Idea",
        "Candidate",
        "Shaping",
        "Ready",
        "Planned",
        "Doing",
        "Blocked",
        "Done",
        "Dropped",
        "Future",
    }
)
DELIVERY_PLACEHOLDER_RE = re.compile(
    r"(即将入|待提交|提交后更新|以最终回复为准|待最终确认)"
)
NORMATIVE_PLACEHOLDER_RE = re.compile(r"(不得|禁止|不能|不要|例如|示例|占位)")
FOLLOWUP_ID_RE = re.compile(r"\b(?:REQ|TD)-\d{3}-FOLLOWUP\b")
LEGACY_FOLLOWUP_REFS = frozenset(
    {
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-006-llm-model-fallback.md", "TD-006-FOLLOWUP"),
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-007-databaseview-vue-query.md", "TD-007-FOLLOWUP"),
        ("docs/03-engineering-governance/technical-debt.md", "TD-002-FOLLOWUP"),
        ("docs/03-engineering-governance/work-log.md", "TD-002-FOLLOWUP"),
    }
)
BACKLOG_DONE_TYPES = frozenset({"REQ", "DOC", "BUG", "APP"})
SCRIPTED_GATE_CANDIDATES = frozenset(
    {
        "`current-work.md` 最近完成最多 5 行",
        "`current-work.md` 下一批候选最多 3 行，且不允许 `🟢 完成`",
        "已完成任务不得残留 `未运行`、`待提交`、`以最终回复为准` 等占位",
        "禁止把 `REQ-xxx-FOLLOWUP` / `TD-xxx-FOLLOWUP` 作为长期任务编号",
        "`Done` 任务在 Backlog / current-work / work-log 之间有最小索引闭环",
        "旧 docs 路径残留检查",
        "Markdown 相对链接存在性检查",
        "AGENTS.md / CLAUDE.md 与 IDE 兼容入口同步检查",
    }
)

KNOWN_ISSUES = (
    (
        "docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md",
        "markdown-link",
        "TD-023",
    ),
    (
        "docs/02-delivery-plans/01-specs/2026-06-05-td-020-provider-resolver-factory.md",
        "validation-claim",
        "TD-023",
    ),
    (
        "docs/02-delivery-plans/02-plans/2026-06-05-td-020-provider-resolver-factory-plan.md",
        "validation-claim",
        "TD-023",
    ),
    ("docs/03-engineering-governance/technical-debt.md", "validation-claim", "TD-023"),
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


def split_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def check_current_work(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    issues: list[Issue] = []

    for title in ("当前进行中", "下一批候选任务", "最近完成"):
        count = sum(1 for line in lines if line.strip() == f"## {title}")
        if count > 1:
            issues.append(
                Issue(
                    path,
                    1,
                    "current-work",
                    f"“{title}”区域不得重复。",
                    "合并重复区域，current-work.md 只保留一个对应标题。",
                )
            )

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
        for line_no, row in recent:
            cells = split_table_row(row)
            if len(cells) < 5:
                continue
            summary = cells[3]
            if len(summary) > CURRENT_WORK_RECENT_SUMMARY_LIMIT:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "current-work",
                        "最近完成摘要过长。",
                        "current-work.md 只保留短摘要；详细交付事实归档到 work-log、技术债总账或 PR。",
                    )
                )

    return issues


def parse_current_work_completed_ids(root: Path) -> list[tuple[str, int]]:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    _recent_start, recent_body = section(lines, "最近完成")
    completed: list[tuple[str, int]] = []
    for line_no, row in table_rows(recent_body):
        cells = split_table_row(row)
        if len(cells) < 3 or "完成" not in cells[2]:
            continue
        task_match = TASK_ID_RE.search(cells[1])
        if task_match:
            completed.append((task_match.group(0), line_no))
    return completed


def check_recent_completed_work_log(root: Path) -> list[Issue]:
    current_path = root / "docs/03-engineering-governance/current-work.md"
    work_log_path = root / "docs/03-engineering-governance/work-log.md"
    work_log_text = work_log_path.read_text(encoding="utf-8") if work_log_path.exists() else ""
    issues: list[Issue] = []

    for task_id, line_no in parse_current_work_completed_ids(root):
        if task_id in work_log_text:
            continue
        issues.append(
            Issue(
                current_path,
                line_no,
                "current-work-work-log",
                f"最近完成任务 {task_id} 缺少 work-log 索引。",
                "在 docs/03-engineering-governance/work-log.md 增加一行索引，或从最近完成移出。",
            )
        )

    return issues


def normalize_status(status: str) -> str:
    clean = re.sub(r"[⚪⚫🔵🟡🔴🟣🟢]", "", status).strip()
    mapping = {
        "待澄清": "Idea",
        "待计划": "Candidate",
        "候选": "Candidate",
        "就绪": "Ready",
        "进行中": "Doing",
        "待验证": "Doing",
        "阻塞": "Blocked",
        "完成": "Done",
        "已完成": "Done",
    }
    return mapping.get(clean, clean)


def is_product_status(status: str) -> bool:
    return normalize_status(status) in PRODUCT_STATUS_NAMES


def has_product_status_icon(status: str) -> bool:
    return bool(PRODUCT_STATUS_ICON_RE.match(status.strip()))


def check_product_planning_status_icons(root: Path) -> list[Issue]:
    product_root = root / "docs/01-product-planning"
    issues: list[Issue] = []

    for path in sorted(product_root.glob("**/*.md")):
        status_column: int | None = None
        for line_no, line in enumerate(read_lines(path), start=1):
            stripped = line.strip()

            status_line = re.match(r"^Status:\s*(.+)$", stripped)
            if status_line:
                status = status_line.group(1).strip()
                if status and is_product_status(status) and not has_product_status_icon(status):
                    issues.append(
                        Issue(
                            path,
                            line_no,
                            "product-status-icon",
                            "产品规划状态缺少颜色图标。",
                            "使用 `颜色 状态名` 格式，例如 `⚫ Candidate` 或 `🟢 Done`。",
                        )
                    )
                continue

            if not stripped.startswith("|"):
                status_column = None
                continue
            if set(stripped.replace("|", "").replace("-", "").replace(" ", "")) == set():
                continue

            cells = split_table_row(stripped)
            if "状态" in cells:
                status_column = cells.index("状态")
                continue
            if status_column is None or len(cells) <= status_column:
                continue

            status = cells[status_column].strip()
            if not status or status == "-":
                continue
            if is_product_status(status) and not has_product_status_icon(status):
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "product-status-icon",
                        "产品规划表格状态缺少颜色图标。",
                        "使用 `颜色 状态名` 格式，例如 `⚫ Candidate` 或 `🟢 Done`。",
                    )
                )

    return issues


def collect_backlog_req_statuses(root: Path) -> dict[str, list[tuple[Path, int, str]]]:
    path = root / "docs/01-product-planning/04-backlog.md"
    lines = read_lines(path)
    _start, body = section(lines, "Backlog")
    statuses: dict[str, list[tuple[Path, int, str]]] = {}
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 3 or not REQ_ID_RE.fullmatch(cells[0]):
            continue
        statuses.setdefault(cells[0], []).append((path, line_no, normalize_status(cells[2])))
    return statuses


def collect_requirement_file_statuses(root: Path) -> dict[str, list[tuple[Path, int, str]]]:
    statuses: dict[str, list[tuple[Path, int, str]]] = {}
    req_root = root / "docs/01-product-planning/05-requirements"
    for path in sorted(req_root.glob("REQ-*.md")):
        task_match = REQ_ID_RE.search(path.name)
        if not task_match:
            continue
        task_id = task_match.group(0)
        for line_no, line in enumerate(read_lines(path), start=1):
            match = re.match(r"^Status:\s*(.+)$", line.strip())
            if not match:
                continue
            statuses.setdefault(task_id, []).append(
                (path, line_no, normalize_status(match.group(1)))
            )
            break
    return statuses


def collect_iteration_req_statuses(root: Path) -> dict[str, list[tuple[Path, int, str]]]:
    statuses: dict[str, list[tuple[Path, int, str]]] = {}
    iteration_root = root / "docs/01-product-planning/03-iterations"
    for path in sorted(iteration_root.glob("*.md")):
        for line_no, row in table_rows(list(enumerate(read_lines(path), start=1))):
            cells = split_table_row(row)
            if len(cells) < 3 or not REQ_ID_RE.fullmatch(cells[0]):
                continue
            statuses.setdefault(cells[0], []).append((path, line_no, normalize_status(cells[2])))
    return statuses


def collect_milestone_req_statuses(root: Path) -> dict[str, list[tuple[Path, int, str]]]:
    statuses: dict[str, list[tuple[Path, int, str]]] = {}
    milestone_root = root / "docs/01-product-planning/02-milestones"
    for path in sorted(milestone_root.glob("*.md")):
        for line_no, row in table_rows(list(enumerate(read_lines(path), start=1))):
            cells = split_table_row(row)
            if len(cells) < 2 or not REQ_ID_RE.fullmatch(cells[0]):
                continue
            statuses.setdefault(cells[0], []).append((path, line_no, normalize_status(cells[1])))
    return statuses


def collect_current_work_req_statuses(root: Path) -> dict[str, list[tuple[Path, int, str]]]:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    statuses: dict[str, list[tuple[Path, int, str]]] = {}
    for title in ("当前进行中", "下一批候选任务", "最近完成"):
        _start, body = section(lines, title)
        for line_no, row in table_rows(body):
            cells = split_table_row(row)
            if len(cells) < 2:
                continue
            task_match = REQ_ID_RE.search(cells[0] if title != "最近完成" else cells[1])
            if not task_match:
                continue
            status_cell = cells[1] if title != "最近完成" else cells[2]
            statuses.setdefault(task_match.group(0), []).append(
                (path, line_no, normalize_status(status_cell))
            )
    return statuses


def merge_status_maps(
    *maps: dict[str, list[tuple[Path, int, str]]],
) -> dict[str, list[tuple[Path, int, str]]]:
    merged: dict[str, list[tuple[Path, int, str]]] = {}
    for status_map in maps:
        for task_id, entries in status_map.items():
            merged.setdefault(task_id, []).extend(entries)
    return merged


def check_req_status_consistency(root: Path) -> list[Issue]:
    statuses = merge_status_maps(
        collect_backlog_req_statuses(root),
        collect_requirement_file_statuses(root),
        collect_iteration_req_statuses(root),
        collect_milestone_req_statuses(root),
        collect_current_work_req_statuses(root),
    )
    issues: list[Issue] = []

    for task_id, entries in sorted(statuses.items()):
        unique_statuses = {status for _path, _line_no, status in entries}
        if len(unique_statuses) <= 1:
            continue
        detail = ", ".join(
            f"{rel(path, root)}:{line_no}={status}"
            for path, line_no, status in entries
        )
        first_path, first_line, _first_status = entries[0]
        issues.append(
            Issue(
                first_path,
                first_line,
                "req-status-consistency",
                f"{task_id} 在产品规划层和工程工作台中的状态不一致：{detail}",
                "关闭或推进 REQ 任务时，同步 Backlog、Requirement、Iteration、Milestone 和 current-work。",
            )
        )

    return issues


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


def check_followup_ids(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        for line_no, line in enumerate(read_lines(path), start=1):
            for match in FOLLOWUP_ID_RE.finditer(line):
                task_id = match.group(0)
                if (rel(path, root), task_id) in LEGACY_FOLLOWUP_REFS:
                    continue
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "stable-task-id",
                        f"发现临时 follow-up 编号：{task_id}。",
                        "需要长期执行的 follow-up 应改为新的稳定编号，例如 REQ-007、TD-031 或 DOC-039。",
                    )
                )
    return issues


def collect_backlog_done_tasks(root: Path) -> list[tuple[Path, int, str, str, str]]:
    path = root / "docs/01-product-planning/04-backlog.md"
    lines = read_lines(path)
    _start, body = section(lines, "Backlog")
    tasks: list[tuple[Path, int, str, str, str]] = []
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 8:
            continue
        task_id, task_type, status = cells[0], cells[1], cells[2]
        if not TASK_ID_RE.fullmatch(task_id):
            continue
        if task_type not in BACKLOG_DONE_TYPES:
            continue
        if normalize_status(status) != "Done":
            continue
        tasks.append((path, line_no, task_id, task_type, cells[7]))
    return tasks


def has_fact_source(external: str) -> bool:
    return bool(external.strip()) and (
        "[" in external or "PR" in external or "http://" in external or "https://" in external
    )


def check_backlog_done_index(root: Path) -> list[Issue]:
    work_log_path = root / "docs/03-engineering-governance/work-log.md"
    work_log_text = work_log_path.read_text(encoding="utf-8") if work_log_path.exists() else ""
    issues: list[Issue] = []
    for path, line_no, task_id, _task_type, external in collect_backlog_done_tasks(root):
        if task_id in work_log_text or has_fact_source(external):
            continue
        issues.append(
            Issue(
                path,
                line_no,
                "backlog-done-index",
                f"Backlog 中已完成任务 {task_id} 缺少 work-log 或明确事实源。",
                "补充 docs/03-engineering-governance/work-log.md 索引，或在 Backlog External 列链接 PR/spec/plan/事实源。",
            )
        )
    return issues


def normalize_entry_lines(path: Path) -> list[str]:
    normalized: list[str] = []
    for line in read_lines(path):
        if line.strip() in {"# AGENTS.md", "# CLAUDE.md"}:
            normalized.append("# ENTRY.md")
        elif line.startswith("本文件是"):
            normalized.append(
                "本文件是 AI IDE 的仓库入口，只保留导航和开工顺序。"
                "规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。"
            )
        else:
            normalized.append(line)
    return normalized


def check_entry_sync(root: Path) -> list[Issue]:
    agents_path = root / "AGENTS.md"
    claude_path = root / "CLAUDE.md"
    issues: list[Issue] = []

    if normalize_entry_lines(agents_path) != normalize_entry_lines(claude_path):
        issues.append(
            Issue(
                claude_path,
                1,
                "entry-sync",
                "AGENTS.md 与 CLAUDE.md 的导航内容不一致。",
                "入口文件应只保留导航；除标题和适配说明外，开工顺序与规则索引保持同步。",
            )
        )

    for rules_dir in (root / ".claude/rules", root / ".trae/rules"):
        if not rules_dir.exists():
            continue
        for path in sorted(rules_dir.glob("*.md")):
            lines = read_lines(path)
            text = "\n".join(lines)
            if len(lines) > 12:
                issues.append(
                    Issue(
                        path,
                        1,
                        "entry-sync",
                        "IDE 兼容规则入口过长。",
                        "`.claude/rules` 和 `.trae/rules` 只保留事实源跳转，不复制规则正文。",
                    )
                )
                continue
            if "兼容入口" in text and "事实源" in text and "不要在" in text:
                continue
            issues.append(
                Issue(
                    path,
                    1,
                    "entry-sync",
                    "IDE 兼容规则入口缺少标准跳转说明。",
                    "使用兼容入口模板：说明事实源路径，并声明不要在 IDE 私有目录维护第二份规则正文。",
                )
            )

    return issues


def check_scripted_gate_candidates(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/01-rules/quality-gates.md"
    lines = read_lines(path)
    _start, body = section(lines, "脚本门禁候选清单")
    issues: list[Issue] = []
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 2 or "已实现" not in cells[1]:
            continue
        candidate = cells[0]
        if candidate in SCRIPTED_GATE_CANDIDATES:
            continue
        issues.append(
            Issue(
                path,
                line_no,
                "scripted-gate-candidate",
                f"脚本门禁候选标为已实现，但脚本未登记反查：{candidate}",
                "要么补充对应脚本检查和 SCRIPTED_GATE_CANDIDATES 映射，要么把状态改为候选或部分实现。",
            )
        )
    return issues


def check_legacy_doc_roots(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for name in LEGACY_DOC_ROOT_NAMES:
        path = root / "docs" / name
        if not path.exists():
            continue
        issues.append(
            Issue(
                path,
                1,
                "legacy-doc-root",
                f"旧顶层文档目录仍存在：`docs/{name}`。",
                "迁移或镜像到编号目录；历史 superpower 输出只能保留在 90-compat-legacy 下。",
            )
        )
    return issues


DETAIL_HEADING_RE = re.compile(r"^### (TD-\d{3}):")
STATUS_LINE_RE = re.compile(r"^状态：(.+)$")


@dataclass(frozen=True)
class DebtDetail:
    line: int
    status: str | None
    body: list[tuple[int, str]]


def parse_debt_overview(lines: list[str]) -> dict[str, tuple[int, str]]:
    _start, body = section(lines, "任务总览")
    overview: dict[str, tuple[int, str]] = {}
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 3 or not re.fullmatch(r"TD-\d{3}", cells[0]):
            continue
        overview[cells[0]] = (line_no, cells[2])
    return overview


def parse_debt_details(lines: list[str]) -> dict[str, DebtDetail]:
    details: dict[str, DebtDetail] = {}
    headings: list[tuple[str, int]] = []
    for line_no, line in enumerate(lines, start=1):
        match = DETAIL_HEADING_RE.match(line)
        if match:
            headings.append((match.group(1), line_no))

    for index, (task_id, heading_line) in enumerate(headings):
        next_line = headings[index + 1][1] if index + 1 < len(headings) else len(lines) + 1
        body = [
            (line_no, lines[line_no - 1])
            for line_no in range(heading_line + 1, next_line)
        ]
        status: str | None = None
        for _line_no, line in body:
            status_match = STATUS_LINE_RE.match(line.strip())
            if status_match:
                status = status_match.group(1).strip()
                break
        details[task_id] = DebtDetail(heading_line, status, body)
    return details


def delivery_record_lines(detail: DebtDetail) -> list[tuple[int, str]]:
    record: list[tuple[int, str]] = []
    in_record = False
    for line_no, line in detail.body:
        stripped = line.strip()
        if stripped == "**交付记录**":
            in_record = True
            continue
        if in_record and stripped.startswith("**") and stripped.endswith("**"):
            break
        if in_record:
            record.append((line_no, line))
    return record


def check_technical_debt(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/technical-debt.md"
    lines = read_lines(path)
    issues: list[Issue] = []
    overview = parse_debt_overview(lines)
    details = parse_debt_details(lines)

    for task_id, (line_no, overview_status) in overview.items():
        detail = details.get(task_id)
        if detail is None or detail.status is None:
            continue
        if detail.status != overview_status:
            issues.append(
                Issue(
                    path,
                    line_no,
                    "technical-debt-status",
                    f"技术债总览和详情状态不一致：{task_id} 总览为 {overview_status}，详情为 {detail.status}。",
                    "同步任务总览表和对应任务详情的 `状态：` 字段。",
                )
            )

    for task_id, detail in details.items():
        if detail.status != "🟢 完成":
            continue
        record = delivery_record_lines(detail)
        if not record:
            issues.append(
                Issue(
                    path,
                    detail.line,
                    "technical-debt-delivery",
                    f"{task_id} 已完成但缺少交付记录。",
                    "补充完成日期、PR / commit 或验证摘要。",
                )
            )
            continue
        for line_no, line in record:
            if "未完成" in line:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "technical-debt-delivery",
                        f"{task_id} 完成任务的交付记录仍写未完成。",
                        "将交付记录回填为完成日期、PR / commit 和验证摘要。",
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
    for path in sorted((root / "docs/02-delivery-plans/02-plans").glob("*.md")):
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
            ["git", "diff", "--unified=0", "--", "docs/03-engineering-governance/work-log.md"],
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
    path = root / "docs/03-engineering-governance/work-log.md"
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
    issues.extend(check_legacy_doc_roots(root))
    issues.extend(check_current_work(root))
    issues.extend(check_recent_completed_work_log(root))
    issues.extend(check_req_status_consistency(root))
    issues.extend(check_product_planning_status_icons(root))
    issues.extend(check_followup_ids(root))
    issues.extend(check_backlog_done_index(root))
    issues.extend(check_entry_sync(root))
    issues.extend(check_technical_debt(root))
    issues.extend(check_completed_plans(root))
    issues.extend(check_markdown_links(root))
    issues.extend(check_work_log_append_only(root))
    issues.extend(check_delivery_placeholders(root))
    issues.extend(check_validation_claims(root))
    issues.extend(check_scripted_gate_candidates(root))

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
