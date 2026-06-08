from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINEERING_CHECKER = (
    REPO_ROOT / "scripts" / "engineering" / "check_engineering_docs.py"
)
SCRIPT_WRAPPER = REPO_ROOT / "scripts" / "check-engineering-docs"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def make_minimal_docs(root: Path) -> None:
    write(
        root / "docs/03-engineering-governance/current-work.md",
        """
        # 当前开发工作台

        ## 当前进行中

        当前无进行中任务。

        ## 下一批候选任务

        | 任务 | 状态 | 优先级 | 领域 | 下一步 |
        |------|------|--------|------|--------|
        | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

        ## 最近完成

        | 日期 | 任务 | 状态 | 摘要 | 事实源 |
        |------|------|------|------|--------|
        | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |
        """,
    )
    write(
        root / "docs/03-engineering-governance/work-log.md",
        """
        # 工程工作日志索引

        ## 索引

        | 日期 | 任务 | 类型 | PR 可选 | Merge Commit 可选 | 归档位置 |
        |------|------|------|----|-------------------|----------|
        | 2026-06-05 | DOC-001 示例完成 | 文档 |  |  | `docs/03-engineering-governance/current-work.md` |
        """,
    )
    write(
        root / "docs/03-engineering-governance/technical-debt.md",
        """
        # 技术债总账

        ## 任务总览

        | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
        |------|------|------|--------|------|--------|
        | TD-001 | 示例任务 | 🔵 就绪 | P2 | Docs | - |
        """,
    )
    write(
        root / "docs/02-delivery-plans/01-specs/example.md",
        """
        # Example Spec

        See [work log](../../03-engineering-governance/work-log.md).
        """,
    )
    write(
        root / "docs/02-delivery-plans/02-plans/example-plan.md",
        """
        # Example Plan

        > 状态：🔵 就绪

        - [ ] 未完成计划项。
        """,
    )
    write(
        root / "AGENTS.md",
        """
        # AGENTS.md

        本文件是跨 AI IDE 的仓库入口，只保留导航和开工顺序。规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。
        """,
    )
    write(
        root / "CLAUDE.md",
        """
        # CLAUDE.md

        本文件是 Claude Code 的仓库入口，只保留导航和开工顺序。规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。
        """,
    )


def run_checker(
    root: Path, checker: Path = ENGINEERING_CHECKER
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(checker), "--root", str(root)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_passes_minimal_valid_docs(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_scripts_wrapper_delegates_to_tools_checker(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)

    result = run_checker(tmp_path, SCRIPT_WRAPPER)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_fails_when_candidate_contains_completed_task(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        current_work.read_text(encoding="utf-8").replace("🔵 就绪", "🟢 完成", 1),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "候选区不得出现完成任务" in result.stderr
    assert "current-work.md" in result.stderr


def test_fails_when_recent_completed_exceeds_five_rows(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    rows = "\n".join(
        f"| 2026-06-05 | DOC-00{i} 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |"
        for i in range(1, 7)
    )
    current_work.write_text(
        textwrap.dedent(
            f"""
            # 当前开发工作台

            ## 当前进行中

            当前无进行中任务。

            ## 下一批候选任务

            | 任务 | 状态 | 优先级 | 领域 | 下一步 |
            |------|------|--------|------|--------|
            | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

            ## 最近完成

            | 日期 | 任务 | 状态 | 摘要 | 事实源 |
            |------|------|------|------|--------|
            {rows}
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "最近完成最多 5 行" in result.stderr


def test_fails_when_recent_completed_summary_is_too_long(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        current_work.read_text(encoding="utf-8").replace(
            "已完成。",
            "这是一段过长的最近完成摘要，" * 20,
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "最近完成摘要过长" in result.stderr


def test_fails_when_completed_plan_has_active_checkbox(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    plan = tmp_path / "docs/02-delivery-plans/02-plans/example-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace("状态：🔵 就绪", "状态：🟢 完成"),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "已完成 plan 不得残留活动式" in result.stderr


def test_fails_when_markdown_link_target_is_missing(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/broken.md",
        """
        # Broken

        See [missing](../../03-engineering-governance/missing.md).
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "Markdown 链接目标不存在" in result.stderr


def test_fails_when_work_log_index_row_is_deleted(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    work_log = tmp_path / "docs/03-engineering-governance/work-log.md"
    work_log.write_text(
        "\n".join(
            line
            for line in work_log.read_text(encoding="utf-8").splitlines()
            if "DOC-001 示例完成" not in line
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "work-log.md 默认只新增索引" in result.stderr


def test_fails_when_full_pytest_passed_claim_has_no_evidence(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/claim.md",
        """
        # Claim

        验证摘要：全量 pytest 152 passed。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "验证通过声明缺少可复核证据" in result.stderr


def test_fails_when_debt_overview_and_detail_status_diverge(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 示例任务 | 🟢 完成 | P2 | Docs | PR #1 |

            ## 任务详情

            ### TD-001: 示例任务

            状态：⚫ 待办

            **交付记录**
            - 未完成。
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "技术债总览和详情状态不一致" in result.stderr


def test_fails_when_completed_debt_detail_still_says_unfinished(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 示例任务 | 🟢 完成 | P2 | Docs | PR #1 |

            ## 任务详情

            ### TD-001: 示例任务

            状态：🟢 完成

            **交付记录**
            - 未完成。
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "完成任务的交付记录仍写未完成" in result.stderr


def test_fails_when_new_followup_id_is_used(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/followup.md",
        """
        # Followup

        后续任务：TD-999-FOLLOWUP。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "发现临时 follow-up 编号" in result.stderr


def test_fails_when_done_backlog_task_has_no_index_or_fact_source(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/01-product-planning/04-backlog.md",
        """
        # Product Backlog

        ## Backlog

        | ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
        |----|------|------|--------|--------|------|--------|----------|
        | DOC-999 | DOC | 🟢 Done | P2 | P3 | 示例完成任务 | 已完成 |  |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "缺少 work-log 或明确事实源" in result.stderr


def test_fails_when_agents_and_claude_entries_drift(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n额外入口规则正文。\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "AGENTS.md 与 CLAUDE.md 的导航内容不一致" in result.stderr


def test_fails_when_ide_rule_entry_contains_body_text(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / ".claude/rules/quality-gates.md",
        """
        # Quality Gates

        本文件仅作为 Claude Code 的兼容入口。

        共享规则事实源已迁移到：

        `docs/03-engineering-governance/01-rules/quality-gates.md`

        请以该文件为准，不要在 `.claude/rules/` 中维护第二份规则正文。

        ## 重复规则正文

        这里不应该复制完整规则。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "IDE 兼容规则入口过长" in result.stderr


def test_fails_when_implemented_gate_candidate_has_no_script_mapping(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/03-engineering-governance/01-rules/quality-gates.md",
        """
        # Quality Gates

        ## 脚本门禁候选清单

        | 候选门禁 | 当前状态 | 触发价值 |
        |----------|----------|----------|
        | 未登记的新脚本门禁 | 已实现 | 示例 |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "脚本门禁候选标为已实现" in result.stderr
