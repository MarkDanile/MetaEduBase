from __future__ import annotations

from pathlib import Path

from tests.engineering.test_check_engineering_docs import (
    init_git_repo,
    make_minimal_docs,
    run_checker,
    write,
)


def write_source_size_baseline(root: Path) -> None:
    write(
        root / "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md",
        """
        # TD-032 源码文件行数基线

        ## 文件清单

        ### >1000 行

        | 文件 | 行数 | 状态 | 例外 / 拆分说明 |
        |------|------|------|-----------------|
        """,
    )


def large_python_file() -> str:
    return "\n".join(["x = 1"] * 1001) + "\n"


def test_source_size_default_ignores_unchanged_large_file(tmp_path: Path) -> None:
    """Default check-engineering-docs is a fast gate: changed files only."""
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "packages" / "server-python" / "app" / "huge.py",
        large_python_file(),
    )
    write_source_size_baseline(tmp_path)
    init_git_repo(tmp_path)

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_source_size_default_flags_changed_large_file(tmp_path: Path) -> None:
    """Default mode still blocks new or modified large source files."""
    make_minimal_docs(tmp_path)
    write_source_size_baseline(tmp_path)
    init_git_repo(tmp_path)
    write(
        tmp_path / "packages" / "server-python" / "app" / "huge.py",
        large_python_file(),
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "huge.py" in result.stderr
    assert "超过 1000 行硬限制" in result.stderr


def test_source_size_full_flags_unchanged_large_file(tmp_path: Path) -> None:
    """--full keeps the dedicated full source-size audit behavior."""
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "packages" / "server-python" / "app" / "huge.py",
        large_python_file(),
    )
    write_source_size_baseline(tmp_path)
    init_git_repo(tmp_path)

    result = run_checker(tmp_path, extra_args=["--full"])

    assert result.returncode == 1
    assert "huge.py" in result.stderr
    assert "超过 1000 行硬限制" in result.stderr


def test_timing_flag_prints_check_breakdown(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)

    result = run_checker(tmp_path, extra_args=["--timing"])

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout
    assert "check_source_size_hard_limit" in result.stderr
