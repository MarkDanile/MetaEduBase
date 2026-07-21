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


def test_req_status_consistency_reads_prose_task_card(tmp_path: Path) -> None:
    """`req-status-consistency` 必须能解析「当前进行中」的散文式任务卡片。

    回归锁（REQ-045 塑形时发现）：`collect_current_work_req_statuses` 原先只
    用 `table_rows` 扫三个 section 的表格行，有两个叠加缺陷：
    (1) 不识别 `### REQ-XXX: ...` + `状态：...` 的散文式任务卡片，卡片状态
        根本没被采集；
    (2) 「下一批候选任务」表的 priority 格若含 `REQ-045` 引用（如
        `P0（主线，待 REQ-045）`），`REQ_ID_RE.search(cells[0])` 会把它当成
        任务 id，再把 cells[1]（任务名）当状态 —— `normalize_status` 对非
        状态文本 fail-open 原样返回，于是任务名被当成一个"状态"参与比对，
        报「状态不一致」假阳性。

    修复后：卡片 `状态：🔵 Ready` 被采集为 current-work 状态；任务名格不再
    被当状态；backlog / requirement / current-work 三方 Ready 一致 → 不报。
    """
    make_minimal_docs(tmp_path)
    (tmp_path / "docs/01-product-planning/05-requirements").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "docs/01-product-planning/05-requirements/REQ-045-x.md").write_text(
        "# REQ-045: 示例\n\nStatus: 🔵 Ready\n", encoding="utf-8"
    )
    (tmp_path / "docs/01-product-planning/04-backlog.md").write_text(
        textwrap.dedent(
            """
            # Product Backlog

            ## Backlog

            | ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
            |----|------|------|--------|--------|------|--------|----------|
            | REQ-045 | REQ | 🔵 Ready | P0 | P3 | 示例 | 实现 |  |
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "docs/03-engineering-governance/current-work.md").write_text(
        textwrap.dedent(
            """
            # 当前开发工作台

            ## 当前进行中

            ### REQ-045: 示例任务

            状态：🔵 Ready（塑形完成，待启动实现）
            类型：新平台能力

            ## 下一批候选任务

            | 优先级 | 任务 | 状态 | 建议下一步 |
            |--------|------|------|------------|
            | P0（主线，待 REQ-045） | REQ-046 下游任务 | ⚫ Candidate | 等上游。 |

            ## 最近完成

            | 日期 | 任务 | 状态 | 摘要 | 事实源 |
            |------|------|------|------|--------|
            | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert "状态不一致" not in result.stderr, result.stderr

