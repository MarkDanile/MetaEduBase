from __future__ import annotations

from pathlib import Path

from tests.engineering.test_check_engineering_docs import (
    make_minimal_docs,
    run_checker,
    write,
)


def test_fails_when_draft_id_is_used_as_backlog_primary_key(
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
        | DRAFT-20260613-2238-A7K9 | DOC | ⚫ Candidate | P2 | P3 | 临时任务 | 归并正式编号 |  |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "draft-task-id" in result.stderr or "临时编号" in result.stderr
    assert "DRAFT-20260613-2238-A7K9" in result.stderr


def test_allows_draft_id_as_origin_text_after_formal_id(
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
        | DOC-001 | DOC | ⚫ Candidate | P2 | P3 | 正式任务 | Origin: DRAFT-20260613-2238-A7K9 |  |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
