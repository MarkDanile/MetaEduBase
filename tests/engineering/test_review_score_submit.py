from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check-review-score-submit"
SCORE_LOG = Path("docs/03-engineering-governance/04-retrospectives/review-score-log.md")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def write_score_log(root: Path) -> None:
    path = root / SCORE_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Review Score Log — 任务评审评分总账

## Score Log

| 日期 | 类型 | 任务 | PR | 总分 | 结论 | 必修 follow-up | 流程扣分点 | 规则 / 脚本改进 | 评审人 |
|------|------|------|----|------|------|----------------|------------|------------------|--------|
| 2026-08-01 | Original | DOC-001 Existing | [#1](https://example.test/1) | 90 | 优秀 | 无 | 无 | 无 | Fixture |

## Metrics Snapshot

| 指标 | 当前值 | 说明 |
|------|--------|------|
| 已记录评审数 | 1 | as of 2026-08-01; baseline fixture |
""",
        encoding="utf-8",
    )


def init_fixture(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    write_score_log(root)
    git(root, "add", ".")
    git(root, "commit", "-m", "initial score log")
    return root, git(root, "rev-parse", "HEAD")


def score_row(base: str, pr: str = "123", score: str = "91") -> str:
    return (
        f"| 2026-08-11 | Original | DOC-080 | [#{pr}](https://example.test/{pr}) | "
        f"{score} | 优秀；P0/P1=0；评分基线 HEAD `{base[:8]}` | 无 | 无 | 无 | Fixture |\n"
    )


def add_score_row(root: Path, base: str, *, pr: str = "123") -> None:
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
    assert content.count(marker) == 1
    path.write_text(content.replace(marker, marker + score_row(base, pr), 1), encoding="utf-8")


def commit(root: Path, message: str) -> None:
    git(root, "add", ".")
    git(root, "commit", "-m", message)


def run_check(root: Path, base: str, pr: str = "123") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CHECKER), "--root", str(root), "--base", base, "--pr", pr],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_score_submit_accepts_one_new_original_row(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    commit(root, "add score")

    result = run_check(root, base)

    assert result.returncode == 0, result.stderr
    assert "one Original row" in result.stdout


def test_score_submit_uses_final_net_diff_after_scope_correction(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    (root / "current-work.md").write_text("temporary scope drift\n", encoding="utf-8")
    commit(root, "score with temporary scope drift")
    (root / "current-work.md").unlink()
    commit(root, "restore scope")

    result = run_check(root, base)

    assert result.returncode == 0, result.stderr


def test_score_submit_rejects_extra_file_in_final_net_diff(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    (root / "current-work.md").write_text("scope drift\n", encoding="utf-8")
    commit(root, "score with workbench change")

    result = run_check(root, base)

    assert result.returncode != 0
    assert "only review-score-log.md" in result.stderr


def test_score_submit_rejects_metrics_change(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    path = root / SCORE_LOG
    path.write_text(
        path.read_text(encoding="utf-8").replace("已记录评审数 | 1", "已记录评审数 | 2"),
        encoding="utf-8",
    )
    commit(root, "score with metrics change")

    result = run_check(root, base)

    assert result.returncode != 0
    assert "Metrics Snapshot changed" in result.stderr


def test_score_submit_rejects_committed_metrics_change_hidden_by_worktree(
    tmp_path: Path,
) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    path = root / SCORE_LOG
    path.write_text(
        path.read_text(encoding="utf-8").replace("已记录评审数 | 1", "已记录评审数 | 2"),
        encoding="utf-8",
    )
    commit(root, "score with metrics change")
    path.write_text(
        path.read_text(encoding="utf-8").replace("已记录评审数 | 2", "已记录评审数 | 1"),
        encoding="utf-8",
    )

    result = run_check(root, base)

    assert result.returncode != 0
    assert "Metrics Snapshot changed" in result.stderr


def test_score_submit_rejects_two_new_rows(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base, pr="123")
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
    path.write_text(content.replace(marker, marker + score_row(base, pr="124"), 1), encoding="utf-8")
    commit(root, "add two scores")

    result = run_check(root, base)

    assert result.returncode != 0
    assert "exactly one inserted line" in result.stderr


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "优秀；P0/P1=0；评分基线 HEAD",
            "优秀；评分基线 HEAD",
            "cleared P0/P1 conclusion",
        ),
        (
            "P0/P1=0",
            "P0/P1=2",
            "cleared P0/P1 conclusion",
        ),
        (
            "P0/P1=0",
            "P0/P1=01",
            "cleared P0/P1 conclusion",
        ),
        (
            "| 无 | 无 | 无 | Fixture |",
            "| investigate later | 无 | 无 | Fixture |",
            "stable task id",
        ),
        (
            "| Fixture |",
            "| Fixture | Extra |",
            "exactly 10 Score Log cells",
        ),
        (
            "Original | DOC-080",
            "Backfilled | DOC-080",
            "must be typed `Original`",
        ),
        (
            "| 91 | 优秀",
            "| 101 | 优秀",
            "score from 0 to 100",
        ),
        (
            "| 无 | 无 | 无 | Fixture |",
            "| TD-080-FOLLOWUP | 无 | 无 | Fixture |",
            "stable task id",
        ),
        (
            "| 无 | 无 | 无 | Fixture |",
            "| TD-080X | 无 | 无 | Fixture |",
            "stable task id",
        ),
        (
            "| 无 | 无 | 无 | Fixture |",
            "|  | 无 | 无 | Fixture |",
            "must not contain empty",
        ),
    ],
)
def test_score_submit_rejects_incomplete_row_contract(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    path = root / SCORE_LOG
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )
    commit(root, "add invalid score row")

    result = run_check(root, base)

    assert result.returncode != 0
    assert expected in result.stderr


def test_score_submit_rejects_duplicate_pr_with_plain_text_baseline(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    path = root / SCORE_LOG
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "[#1](https://example.test/1)",
            "PR #1",
        ),
        encoding="utf-8",
    )
    commit(root, "normalize existing PR reference")
    baseline = git(root, "rev-parse", "HEAD")
    add_score_row(root, baseline, pr="1")
    commit(root, "add duplicate score")

    result = run_check(root, baseline, pr="1")

    assert result.returncode != 0
    assert "already contains a row for PR #1" in result.stderr


def test_score_submit_rejects_file_mode_change(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    git(root, "add", ".")
    git(root, "update-index", "--chmod=+x", str(SCORE_LOG))
    git(root, "commit", "-m", "add score with mode change")

    result = run_check(root, base)

    assert result.returncode != 0
    assert "file mode changed" in result.stderr


def test_score_submit_rejects_non_numeric_pr_argument(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, base)
    commit(root, "add score")

    result = run_check(root, base, pr="not-a-number")

    assert result.returncode != 0
    assert "positive numeric pull request number" in result.stderr


@pytest.mark.parametrize(
    ("row_pr", "requested_pr", "expected"),
    [
        ("999", "123", "does not target PR #123"),
        ("123", "123", "does not contain the requested implementation baseline"),
    ],
)
def test_score_submit_rejects_wrong_pr_or_baseline(
    tmp_path: Path, row_pr: str, requested_pr: str, expected: str
) -> None:
    root, base = init_fixture(tmp_path)
    add_score_row(root, "deadbeef", pr=row_pr)
    commit(root, "invalid score metadata")

    result = run_check(root, base, requested_pr)

    assert result.returncode != 0
    assert expected in result.stderr
