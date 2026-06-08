"""`check_entry_sync`: `AGENTS.md` / `CLAUDE.md` 与 IDE 兼容入口同步检查。"""

from __future__ import annotations

from pathlib import Path

from ._common import Issue, read_lines


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
