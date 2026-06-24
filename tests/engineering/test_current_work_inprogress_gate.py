"""`当前进行中` 形状门禁回归锁。

`check_current_work` 扩展：无活跃任务时只允许单句，防止 agent 把已完成任务
的摘要段落整段塞进「当前进行中」（事实应归「最近完成」区）。活跃态用表格
或 `### TASK` 卡片时不触发单句约束。
"""

from __future__ import annotations

from pathlib import Path

import textwrap

from tests.engineering.test_check_engineering_docs import make_minimal_docs, run_checker


def test_fails_when_in_progress_polluted_with_paragraph(tmp_path: Path) -> None:
    """「当前进行中」无活跃任务时被完成摘要段落污染 → 报门禁失败。"""
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        textwrap.dedent(
            """
            # 当前开发工作台

            ## 当前进行中

            当前无活跃任务。BUG-012 已完成。BUG-011 已完成。这是一段不该出现的完成摘要段落，
            把多个已完成任务的事实塞进了当前进行中区，违反 workbench.md 单句约束。

            ## 下一批候选任务

            | 任务 | 状态 | 优先级 | 领域 | 下一步 |
            |------|------|--------|------|--------|
            | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

            ## 最近完成

            | 日期 | 任务 | 状态 | 摘要 | 事实源 |
            |------|------|------|------|--------|
            | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "当前进行中" in result.stderr
    assert "只保留一句" in result.stderr


def test_passes_when_in_progress_uses_active_table(tmp_path: Path) -> None:
    """「当前进行中」用活跃任务表格（非单句）时不报污染门禁。

    锁定：活跃态可用表格列出任务，不应被「无活跃任务只保留单句」规则误伤。
    """
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        textwrap.dedent(
            """
            # 当前开发工作台

            ## 当前进行中

            | 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 |
            |------|------|--------|------|----------|--------|
            | REQ-002 父任务 | 🔵 Ready | P2 | Docs | 待子任务链 | 等子任务 |

            ## 下一批候选任务

            | 任务 | 状态 | 优先级 | 领域 | 下一步 |
            |------|------|--------|------|--------|
            | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

            ## 最近完成

            | 日期 | 任务 | 状态 | 摘要 | 事实源 |
            |------|------|------|------|--------|
            | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert "只保留一句" not in result.stderr, result.stderr
