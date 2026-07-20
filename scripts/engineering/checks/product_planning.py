"""Product planning 层状态族：状态归一 + 5 个 `collect_*_req_statuses` + 一致性 check。

跨 `Backlog` / `Requirement` / `Iteration` / `Milestone` / `current-work` 五个事实源
聚合 REQ 状态，发现不一致时报警。
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import (
    Issue,
    REQ_ID_RE,
    read_lines,
    rel,
    section,
    split_table_row,
    table_rows,
)


PRODUCT_STATUS_ICON_RE = re.compile(r"^[⚪⚫🔵🟡🔴🟣🟢]\s+")
PRODUCT_STATUS_NAMES: frozenset[str] = frozenset(
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


def normalize_status(status: str) -> str:
    clean = re.sub(r"[⚪⚫🔵🟡🔴🟣🟢]", "", status).strip()
    # Strip parenthetical annotations like "进行中（并行 Agent A）" → "进行中"
    clean = re.sub(r"[（(][^）)]*[）)]", "", clean).strip()
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

    # 1) 「当前进行中」也接受散文式任务卡片（`### REQ-XXX: ...` + 后续 `状态：...`
    #    行）。原实现只用 table_rows 扫表格，完全不识别这种卡片，导致活跃任务的
    #    current-work 状态漏采，进而触发 req-status-consistency 假阳性。
    _start, in_progress = section(lines, "当前进行中")
    card_id: str | None = None
    for line_no, line in in_progress:
        header = re.match(r"^###\s+(REQ-\d{3}(?:-\d+)?)\s*[:：]", line.strip())
        if header:
            card_id = header.group(1)
            continue
        if card_id is None:
            continue
        status_match = re.match(r"^状态[:：]\s*(.+)$", line.strip())
        if status_match:
            normalized = normalize_status(status_match.group(1))
            if is_product_status(normalized):
                statuses.setdefault(card_id, []).append((path, line_no, normalized))
            card_id = None

    # 2) 三个 section 的表格行。状态格必须解析为合法产品状态，否则跳过——
    #    防止把任务名格（normalize_status 对自由文本 fail-open 原样返回）误当状态。
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
            normalized = normalize_status(status_cell)
            if not is_product_status(normalized):
                continue
            statuses.setdefault(task_match.group(0), []).append(
                (path, line_no, normalized)
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
