from __future__ import annotations

from pathlib import Path

from tests.engineering.test_check_engineering_docs import (
    init_git_repo,
    make_minimal_docs,
    run_checker,
    write,
)


def _write_current_task(root: Path, task_row: str) -> None:
    write(
        root / "docs/03-engineering-governance/current-work.md",
        f"""
        # 当前开发工作台

        ## 当前进行中

        | 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
        |------|------|--------|------|----------|--------|------|
        {task_row}

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


def _change_gate_file(root: Path) -> None:
    gate_file = root / "scripts/engineering/checks/example_gate.py"
    write(gate_file, "VALUE = 1\n")
    init_git_repo(root)
    gate_file.write_text("VALUE = 2\n", encoding="utf-8")


def test_fails_when_non_gate_task_changes_gate_files(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    _write_current_task(
        tmp_path,
        "| REQ-999 示例业务任务 | 🟡 进行中 | P1 | Product | 正在开发业务功能 | 继续 | 未运行 |",
    )
    _change_gate_file(tmp_path)

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "本次变更修改了门禁脚本文件" in result.stderr


def test_allows_gate_file_changes_for_doc_gate_task(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    _write_current_task(
        tmp_path,
        "| DOC-073 门禁脚本防绕过与规则修改范围校验 | 🟡 进行中 | P1 | Governance / Quality Gates / Scripts | 正在修改门禁脚本 | 验证 | 未运行 |",
    )
    _change_gate_file(tmp_path)

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
