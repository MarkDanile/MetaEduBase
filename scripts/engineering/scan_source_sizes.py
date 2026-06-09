"""Source file size scanner for TD-032 baseline management.

Replaces the manual ``rg --files -0 | xargs -0 wc -l | sort -nr | head 40``
pipeline with a reproducible Python script that:

- Scans ``packages/``, ``scripts/``, ``tests/`` for source files.
- Excludes ``.venv/``, ``uploads/``, ``node_modules/``, ``dist/``,
  ``__pycache__/``, ``.git/``.
- Outputs a sorted file list by line count.
- Supports ``--json`` (machine-readable), ``--diff`` (compare with last
  baseline), ``--threshold`` (filter by minimum lines), ``--refresh``
  (update ``td-032-source-file-sizes.md`` line-count columns and append
  scan history).

See DOC-042 / ``docs/03-engineering-governance/technical-debt.md#doc-042``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
    ".css": "CSS",
    ".scss": "CSS",
}

SCAN_DIRS: tuple[str, ...] = ("packages", "scripts", "tests")

EXCLUDE_DIRS: frozenset[str] = frozenset(
    {".venv", "uploads", "node_modules", "dist", "__pycache__", ".git"}
)

BASELINE_REL = (
    "docs/03-engineering-governance/02-baselines/source-sizes-baseline.json"
)

SIZES_MD_REL = (
    "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md"
)

HARD_LIMIT = 1000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileInfo:
    """One source file with its line count and language."""

    path: str
    lines: int
    language: str


@dataclass
class DiffEntry:
    """Difference between current scan and baseline for one file."""

    path: str
    baseline_lines: int | None = None
    current_lines: int | None = None
    kind: str = ""  # "new", "removed", "changed"


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _should_exclude(parts: tuple[str, ...]) -> bool:
    return any(part in EXCLUDE_DIRS for part in parts)


def scan_source_files(root: Path) -> list[FileInfo]:
    """Walk *root* and return source files sorted by line count desc."""
    entries: list[FileInfo] = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if _should_exclude(p.relative_to(root).parts):
                continue
            ext = p.suffix.lower()
            lang = SOURCE_EXTENSIONS.get(ext)
            if lang is None:
                continue
            try:
                line_count = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            entries.append(
                FileInfo(path=p.relative_to(root).as_posix(), lines=line_count, language=lang)
            )
    entries.sort(key=lambda f: (-f.lines, f.path))
    return entries


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------


def load_baseline(path: Path) -> dict[str, int]:
    """Load a baseline JSON file; return ``{rel_path: line_count}``."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["path"]: entry["lines"] for entry in data}


def save_baseline(path: Path, entries: list[FileInfo]) -> None:
    """Write the baseline JSON (pretty-printed, one entry per line list)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(e) for e in entries]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def diff_baseline(
    current: list[FileInfo], baseline: dict[str, int]
) -> list[DiffEntry]:
    """Compare current scan against baseline."""
    current_map = {f.path: f.lines for f in current}
    diffs: list[DiffEntry] = []

    # New or changed files
    for f in current:
        if f.path not in baseline:
            diffs.append(DiffEntry(path=f.path, current_lines=f.lines, kind="new"))
        elif f.lines != baseline[f.path]:
            diffs.append(
                DiffEntry(
                    path=f.path,
                    baseline_lines=baseline[f.path],
                    current_lines=f.lines,
                    kind="changed",
                )
            )

    # Removed files
    for path, lines in baseline.items():
        if path not in current_map:
            diffs.append(DiffEntry(path=path, baseline_lines=lines, kind="removed"))

    diffs.sort(key=lambda d: (0 if d.kind == "new" else 1 if d.kind == "removed" else 2, d.path))
    return diffs


# ---------------------------------------------------------------------------
# Markdown refresh
# ---------------------------------------------------------------------------

# Pattern: | `path` | 123 | ... |
_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _line_count_col_index(header: str) -> int | None:
    """Find the column index for the line-count column in a Markdown table."""
    cells = [c.strip().lower() for c in header.strip().strip("|").split("|")]
    for idx, cell in enumerate(cells):
        if "行数" in cell or "lines" in cell:
            return idx
    return None


def refresh_sizes_md(md_path: Path, current: list[FileInfo]) -> None:
    """Update line-count columns in ``td-032-source-file-sizes.md``.

    Only touches the 2nd column (行数) of table rows whose 1st cell matches a
    known source file.  All other columns (status, exception/split notes) are
    left untouched.  Also appends a scan-history entry.
    """
    if not md_path.exists():
        return

    current_map = {f.path: f.lines for f in current}
    lines = md_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    in_table = False
    line_count_col: int | None = None

    for line in lines:
        stripped = line.strip()

        # Detect table start
        if stripped.startswith("|") and "文件" in stripped and "行数" in stripped:
            in_table = True
            line_count_col = _line_count_col_index(stripped)
            out.append(line)
            continue

        # End of table
        if in_table and not stripped.startswith("|"):
            in_table = False

        if in_table and line_count_col is not None and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Find file path in first cell (backtick-wrapped)
            m = _TABLE_ROW_RE.match(stripped)
            if m and len(cells) > line_count_col:
                file_path = m.group(1)
                if file_path in current_map:
                    # Replace line count cell
                    cells[line_count_col] = str(current_map[file_path])
                    out.append("| " + " | ".join(cells) + " |")
                    continue
            out.append(line)
            continue

        out.append(line)

    # Append scan history entry
    today = date.today().isoformat()
    history_marker = "## 扫描历史"
    history_idx = next((i for i, line in enumerate(out) if line.strip() == history_marker), None)
    if history_idx is not None:
        out.insert(
            history_idx + 1,
            f"- {today}：`scripts/scan-source-sizes --refresh` 自动刷新行数列。",
        )

    md_path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_text(entries: list[FileInfo], threshold: int = 0) -> str:
    """Human-readable table output."""
    filtered = [e for e in entries if e.lines >= threshold] if threshold else entries
    if not filtered:
        return "(no files match threshold)\n"
    width = max(len(f.path) for f in filtered)
    lines = [f"{'File':<{width}}  {'Lines':>6}  Language"]
    lines.append("-" * width + "  ------  --------")
    for f in filtered:
        lines.append(f"{f.path:<{width}}  {f.lines:>6}  {f.language}")
    return "\n".join(lines) + "\n"


def format_json(entries: list[FileInfo]) -> str:
    """JSON output."""
    return json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False) + "\n"


def format_diff(diffs: list[DiffEntry]) -> str:
    """Human-readable diff output."""
    if not diffs:
        return "(no differences from baseline)\n"
    lines: list[str] = []
    for d in diffs:
        if d.kind == "new":
            lines.append(f"+ {d.path}  ({d.current_lines} lines, NEW)")
        elif d.kind == "removed":
            lines.append(f"- {d.path}  (was {d.baseline_lines} lines, REMOVED)")
        elif d.kind == "changed":
            delta = (d.current_lines or 0) - (d.baseline_lines or 0)
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"~ {d.path}  ({d.baseline_lines} → {d.current_lines}, {sign}{delta})"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan source file sizes and manage TD-032 baseline."
    )
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Only show files with >= THRESHOLD lines (default: 0 = all).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Compare current scan against last baseline.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Update baseline JSON + refresh td-032-source-file-sizes.md line-count columns.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    entries = scan_source_files(root)

    # --- diff mode ---
    if args.diff:
        baseline_path = root / BASELINE_REL
        baseline = load_baseline(baseline_path)
        diffs = diff_baseline(entries, baseline)
        sys.stdout.write(format_diff(diffs))
        return 0

    # --- refresh mode ---
    if args.refresh:
        baseline_path = root / BASELINE_REL
        save_baseline(baseline_path, entries)
        md_path = root / SIZES_MD_REL
        refresh_sizes_md(md_path, entries)
        sys.stdout.write(f"Baseline saved to {baseline_path.relative_to(root)}\n")
        sys.stdout.write(f"Markdown refreshed: {md_path.relative_to(root)}\n")
        return 0

    # --- normal output ---
    if args.json_output:
        sys.stdout.write(format_json(entries))
    else:
        sys.stdout.write(format_text(entries, args.threshold))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
