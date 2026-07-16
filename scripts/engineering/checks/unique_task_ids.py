"""`check_unique_task_ids`: cross-source uniqueness for BUG-/TD-/DOC-/REQ-/APP- ids.

DOC-077: 同一 ID 在所有 docs/*.md 文件中映射到多个不同 H1 核心标题时记
violation。

设计：
- 唯一的判定维度是「canonical 任务卡」（位于 `docs/01-product-planning/05-
  requirements/{ID}-*.md`）。每条任务 ID 必须只有 1 份 canonical 文件；多
  于 1 份即视为 ID 碰撞（这是历史 BUG-011 / BUG-013 复用同一编号的检测场景）。
- spec / plan / report 等子交付物属于单 ID 的子文档，不参与 ID 唯一性比对
  （它们的 H1 标题可能合法地包含 deliverable suffix、validation report 副
  标题等差异，不应误报）。
- canonical 文件 H1 抽取规则：从首个 `# <title>` 行匹配 task-id + 核心标题，
  去掉前缀 task-id 标识和尾部 deliverable suffix（如 `— Spec`），归一化后
  用于比较。同一 ID 的多份 canonical 必须共享同一核心标题，否则记 violation
  （防止 canonical 文件 ID 被改但 H1 没改 / 或反之）。

归一化：
1) 去掉前缀 task_id 标识（带或不带分隔符）。
2) 去掉尾部 deliverable suffix（"— Spec" / "— Plan" / "真实PG验收报告" 等）。
3) em-dash / dash / colon 归一化为同一分隔。
4) 多余空白压缩 + 末尾中英文标点归一化。
"""
from __future__ import annotations

import re
from pathlib import Path

from ._common import Issue, read_lines, rel


_TASK_ID_FROM_FILENAME_RE = re.compile(
    r"(?:BUG|TD|DOC|REQ|APP)-\d{3}(?:-[A-Za-z0-9]+)?"
)
_H1_TITLE_RE = re.compile(
    r"^#\s+((?:BUG|TD|DOC|REQ|APP)-\d{3}(?:-[A-Za-z0-9]+)?)\s*[—\-:：]\s*(.+?)\s*$"
)
_H1_BARE_RE = re.compile(
    r"^#\s+((?:BUG|TD|DOC|REQ|APP)-\d{3}(?:-[A-Za-z0-9]+)?)(?:\s|$)"
)

_DELIVERABLE_SUFFIX_TOKENS = (
    "— Spec",
    ": Spec",
    "— Spec.",
    ": Spec.",
    "— Plan",
    ": Plan",
    "— Implementation Plan",
    ": Implementation Plan",
    "Implementation Plan",
    "— 报告",
    ": 报告",
    "— 真实PG验收报告",
    ": 真实PG验收报告",
    "真实PG验收报告",
    "真实PG 验收报告",
    "— v3 Report",
    ": v3 Report",
    "— Re-run After TD-068+069",
    "— Plan",
    "— Spec",
    "— Report",
)

_CANONICAL_REQUIREMENTS_DIR = (
    "docs/01-product-planning/05-requirements"
)


def _strip_deliverable_suffix(title: str) -> str:
    """去掉标题尾部 deliverable suffix（"— Spec" / "— Plan" / "真实PG验收报告"）。"""
    t = title.strip()
    earliest = len(t)
    for suffix in _DELIVERABLE_SUFFIX_TOKENS:
        idx = t.find(suffix)
        if idx != -1 and idx < earliest:
            earliest = idx
    if earliest < len(t):
        t = t[:earliest]
    return t.strip()


def _normalize_core_title(title: str) -> str:
    """归一化 H1 标题用于跨文件比对。"""
    t = title.strip()
    t = re.sub(r"^#\s+", "", t)
    t = re.sub(
        r"^(?:BUG|TD|DOC|REQ|APP)-\d{3}(?:-[A-Za-z0-9]+)?\s*[—\-:：]?\s*",
        "",
        t,
    )
    t = _strip_deliverable_suffix(t)
    t = t.replace("—", "-").replace("–", "-")
    t = re.sub(r"\s*[—\-:：]\s*$", "", t)
    t = t.rstrip("。.;；:：!！?？")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _extract_ids_from_filename(path: Path) -> str | None:
    match = _TASK_ID_FROM_FILENAME_RE.search(path.name)
    return match.group(0) if match else None


def _extract_h1(lines: list[str]) -> tuple[str, str] | None:
    """Return (task_id, full_h1_text) from the first H1 in lines."""
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped.startswith("# "):
            continue
        m = _H1_TITLE_RE.match(stripped)
        if m:
            return m.group(1), stripped[2:].strip()
        m2 = _H1_BARE_RE.match(stripped)
        if m2:
            return m2.group(1), stripped[2:].strip()
    return None


def check_unique_task_ids(root: Path) -> list[Issue]:
    """DOC-077: canonical 任务卡文件中同一 ID 不得映射到多个不同核心 H1 标题。

    算法：
    1) 扫描 `docs/01-product-planning/05-requirements/*.md`（canonical）。
    2) 每份文件抽 (filename_id, title_id, normalized_core_title)。
    3) 同 ID 必须唯一；若 ≥2 份 canonical 共享同 ID，记 violation
       （DOC-077 期望：通过 alias 行 + 重命名保证每 ID 仅 1 份 canonical）。
    """
    canonical_dir = root / _CANONICAL_REQUIREMENTS_DIR
    if not canonical_dir.is_dir():
        return []

    issues: list[Issue] = []
    # id → {normalized_title → [paths]}
    id_to_titles: dict[str, dict[str, list[Path]]] = {}
    for path in sorted(canonical_dir.glob("*.md")):
        lines = read_lines(path)
        if not lines:
            continue
        h1 = _extract_h1(lines)
        task_id: str | None = None
        if h1 is not None:
            task_id = h1[0]
        if task_id is None:
            task_id = _extract_ids_from_filename(path)
            if task_id is None:
                continue
        normalized = (
            _normalize_core_title(h1[1]) if h1 is not None else task_id
        )
        if not normalized:
            continue
        id_to_titles.setdefault(task_id, {}).setdefault(normalized, []).append(
            path
        )

    for task_id, title_map in id_to_titles.items():
        # 1 份 canonical → 通过。
        if len(title_map) <= 1:
            continue
        # 多份 canonical → collision violation
        sorted_titles = sorted(title_map.items(), key=lambda kv: kv[0])
        titles_repr = " / ".join(
            f"「{title}」@ {rel(sorted(paths)[0], root)}"
            for title, paths in sorted_titles
        )
        first_path = sorted_titles[0][1][0]
        issues.append(
            Issue(
                path=first_path,
                line=1,
                code="unique-task-id-mismatch",
                message=(
                    f"任务编号 {task_id} 在 {rel(canonical_dir, root)}/ 下"
                    f"映射到多个不同核心 H1 标题：{titles_repr}。"
                    f"同 ID 必须指向同一任务（DOC-077）。"
                ),
                suggestion=(
                    "按创建时间保留首次占用（template-init / business-tests 等），"
                    "后创建项重命名（如 BUG-013 → BUG-014），"
                    "并在被重命名文件的 Status 段补 `> Alias: 历史 BUG-XXX` 标注旧引用。"
                ),
            )
        )
    return issues


__all__ = ["check_unique_task_ids"]