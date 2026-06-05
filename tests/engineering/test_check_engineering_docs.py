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
        root / "docs/engineering/current-work.md",
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
        | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/engineering/work-log.md |
        """,
    )
    write(
        root / "docs/engineering/work-log.md",
        """
        # 工程工作日志索引

        ## 索引

        | 日期 | 任务 | 类型 | PR 可选 | Merge Commit 可选 | 归档位置 |
        |------|------|------|----|-------------------|----------|
        | 2026-06-05 | DOC-001 示例完成 | 文档 |  |  | `docs/engineering/current-work.md` |
        """,
    )
    write(
        root / "docs/engineering/technical-debt.md",
        """
        # 技术债总账

        ## 任务总览

        | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
        |------|------|------|--------|------|--------|
        | TD-001 | 示例任务 | 🔵 就绪 | P2 | Docs | - |
        """,
    )
    write(
        root / "docs/specs/example.md",
        """
        # Example Spec

        See [work log](../engineering/work-log.md).
        """,
    )
    write(
        root / "docs/plans/example-plan.md",
        """
        # Example Plan

        > 状态：🔵 就绪

        - [ ] 未完成计划项。
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
    current_work = tmp_path / "docs/engineering/current-work.md"
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
    current_work = tmp_path / "docs/engineering/current-work.md"
    rows = "\n".join(
        f"| 2026-06-05 | DOC-00{i} 示例完成 | 🟢 完成 | 已完成。 | docs/engineering/work-log.md |"
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


def test_fails_when_completed_plan_has_active_checkbox(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    plan = tmp_path / "docs/plans/example-plan.md"
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
        tmp_path / "docs/specs/broken.md",
        """
        # Broken

        See [missing](../engineering/missing.md).
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
    work_log = tmp_path / "docs/engineering/work-log.md"
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
        tmp_path / "docs/specs/claim.md",
        """
        # Claim

        验证摘要：全量 pytest 152 passed。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "验证通过声明缺少可复核证据" in result.stderr
