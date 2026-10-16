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
        f"{score} | 优秀；P0/P1=0；评分基线 SCORE_BASE `{base[:8]}` | 无 | 无 | 无 | Fixture |\n"
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
            "优秀；P0/P1=0；评分基线 SCORE_BASE",
            "优秀；评分基线 SCORE_BASE",
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
            "must be typed `Original` or `Reassessment`",
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
# ---------------------------------------------------------------------------
# DOC-082：Reassessment（正式评分后返修的追加复评）
# ---------------------------------------------------------------------------


def reassessment_row(
    *, base: str, pr: str, prev_token: str, score: str = "95", declared: str | None = None
) -> str:
    """复投行：prev_token=上一条评分行的实现基线（不带 SCORE_BASE 标签的引用）；

    declared=本次 SCORE_BASE 标签声明的实现基线（默认 = --base 前缀）。
    """
    declared = declared or base[:8]
    return (
        f"| 2026-08-12 | Reassessment | DOC-082 rework recheck | "
        f"[#{pr}](https://example.test/{pr}) | {score} | "
        f"优秀；P0/P1=0；复评前序评分行（实现基线 `{prev_token}`）；"
        f"本次评分基线 SCORE_BASE `{declared}`；提交 HEAD `{base[:8]}` | 无 | 无 | 无 | Fixture |\n"
    )


def init_with_original(tmp_path: Path, pr: str = "123") -> tuple[Path, str, str]:
    """构造含一条 Original 评分行的仓库；返回 (root, 原评分基线, 新实现基线)。"""
    root, base0 = init_fixture(tmp_path)
    add_score_row(root, base0, pr=pr)
    commit(root, "original score for pr")
    return root, base0, git(root, "rev-parse", "HEAD")


def add_reassessment_row(
    root: Path, *, base: str, pr: str, prev_token: str, top: bool = True,
    declared: str | None = None,
) -> None:
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    if top:
        marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
        assert content.count(marker) == 1
        path.write_text(
            content.replace(
                marker,
                marker + reassessment_row(base=base, pr=pr, prev_token=prev_token, declared=declared),
                1,
            ),
            encoding="utf-8",
        )
    else:
        # 插入到既有数据行之后（仍在表内但不在表头下一行，违反位置规则）
        existing = "| 2026-08-01 | Original | DOC-001 Existing | [#1](https://example.test/1) | 90 | 优秀 | 无 | 无 | 无 | Fixture |\n"
        assert existing in content
        path.write_text(
            content.replace(
                existing,
                existing
                + reassessment_row(base=base, pr=pr, prev_token=prev_token, declared=declared),
                1,
            ),
            encoding="utf-8",
        )


def test_reassessment_accepted_after_original(tmp_path: Path) -> None:
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8])
    commit(root, "reassessment after rework")

    result = run_check(root, impl_head)

    assert result.returncode == 0, result.stderr
    assert "one Reassessment row" in result.stdout


def test_reassessment_rejected_without_prior_row(tmp_path: Path) -> None:
    root, base = init_fixture(tmp_path)
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
    path.write_text(
        content.replace(
            marker,
            marker + reassessment_row(base=base, pr="999", prev_token="deadbeef"),
            1,
        ),
        encoding="utf-8",
    )
    commit(root, "orphan reassessment")

    result = run_check(root, base, pr="999")

    assert result.returncode != 0
    assert "orphan reassessment" in result.stderr


def test_reassessment_rejected_without_previous_baseline_reference(tmp_path: Path) -> None:
    """跨 PR / 错误引用：复投行不含上一条同 PR 行的任何基线 token。"""
    root, _base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token="f" * 40)
    commit(root, "reassessment with wrong reference")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "must reference the previous formal score row's own" in result.stderr


def test_reassessment_rejects_declared_base_mismatching_head(tmp_path: Path) -> None:
    """声明 D 而行内其他位置包含真实 --base C：声明必须等于 --base，拒绝。"""
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(
        root, base=impl_head, pr="123", prev_token=base0[:8], declared="d" * 40
    )
    commit(root, "reassessment with wrong declared base")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "does not match the --base commit" in result.stderr


def test_reassessment_rejects_multiple_score_base_labels(tmp_path: Path) -> None:
    """恰一个 SCORE_BASE 声明：两个标签（即使其一指前序基线）即拒绝。"""
    root, base0, impl_head = init_with_original(tmp_path)
    row = reassessment_row(base=impl_head, pr="123", prev_token=base0[:8])
    row = row.replace(
        "复评前序评分行（实现基线",
        f"复评前序评分行（SCORE_BASE `{base0[:8]}`——实现基线",
        1,
    )
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
    path.write_text(content.replace(marker, marker + row, 1), encoding="utf-8")
    commit(root, "reassessment with two SCORE_BASE labels")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "exactly one `SCORE_BASE` declaration" in result.stderr


def test_reassessment_rejects_when_only_backfilled_prior(tmp_path: Path) -> None:
    """同 PR 仅有 Backfilled 行：不得单独充当前序正式评分，按孤立复评拒绝。"""
    root, base = init_fixture(tmp_path)
    path = root / SCORE_LOG
    content = path.read_text(encoding="utf-8")
    marker = "|------|------|------|----|------|------|----------------|------------|------------------|--------|\n"
    backfilled = (
        f"| 2026-08-05 | Backfilled | DOC-001 history | [#123](https://example.test/123) | "
        f"80 | 历史补录 | 无 | 无 | 无 | Fixture |\n"
    )
    path.write_text(content.replace(marker, marker + backfilled, 1), encoding="utf-8")
    commit(root, "add backfilled row")
    impl_head = git(root, "rev-parse", "HEAD")
    add_reassessment_row(root, base=impl_head, pr="123", prev_token="deadbeef")
    commit(root, "reassessment over backfilled-only history")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "orphan reassessment" in result.stderr


def test_reassessment_second_round_must_reference_immediate_predecessor(tmp_path: Path) -> None:
    """Original(A) → Reassessment(B) 后，第二次复评引用 A（跳过 B）：拒绝。"""
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8])
    commit(root, "first reassessment")
    impl_head2 = git(root, "rev-parse", "HEAD")
    # 错误：跨过 B 直接引用 A
    add_reassessment_row(root, base=impl_head2, pr="123", prev_token=base0[:8])
    commit(root, "second reassessment skipping immediate predecessor")

    result = run_check(root, impl_head2)

    assert result.returncode != 0
    assert "must reference the previous formal score row's own" in result.stderr


def test_reassessment_rejects_metrics_change(tmp_path: Path) -> None:
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8])
    path = root / SCORE_LOG
    path.write_text(
        path.read_text(encoding="utf-8").replace("已记录评审数 | 1", "已记录评审数 | 2"),
        encoding="utf-8",
    )
    commit(root, "reassessment with metrics change")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "Metrics Snapshot changed" in result.stderr


def test_reassessment_rejects_extra_file_in_net_diff(tmp_path: Path) -> None:
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8])
    (root / "current-work.md").write_text("scope drift\n", encoding="utf-8")
    commit(root, "reassessment with workbench change")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "only review-score-log.md" in result.stderr


def test_reassessment_must_be_first_row(tmp_path: Path) -> None:
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8], top=False)
    commit(root, "reassessment appended at table bottom")

    result = run_check(root, impl_head)

    assert result.returncode != 0
    assert "immediately below the Score Log header" in result.stderr


def test_reassessment_chains_over_previous_reassessment(tmp_path: Path) -> None:
    """第二次复评引用第一次复评的基线（链式），同样合法。"""
    root, base0, impl_head = init_with_original(tmp_path)
    add_reassessment_row(root, base=impl_head, pr="123", prev_token=base0[:8])
    commit(root, "first reassessment")
    impl_head2 = git(root, "rev-parse", "HEAD")
    add_reassessment_row(root, base=impl_head2, pr="123", prev_token=impl_head[:8])
    commit(root, "second reassessment")

    result = run_check(root, impl_head2)

    assert result.returncode == 0, result.stderr
    assert "one Reassessment row" in result.stdout
# ---------------------------------------------------------------------------
# DOC-082：_validate_reassessment_row 直接单元测试（绕过 SHA 因果限制）
# ---------------------------------------------------------------------------

import importlib.util
import sys as _sys

_SPEC = importlib.util.spec_from_file_location(
    "review_score_submit", REPO_ROOT / "scripts" / "engineering" / "review_score_submit.py"
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)


def _baseline_with_original(prev_base: str) -> str:
    return (
        "| 2026-08-11 | Original | DOC-080 | [#123](https://example.test/123) | 91 | "
        f"优秀；P0/P1=0；评分基线 SCORE_BASE `{prev_base}` | 无 | 无 | 无 | Fixture |\n"
    )


def _unit_row(declared: str, ref_token: str) -> str:
    return (
        "| 2026-08-12 | Reassessment | DOC-082 | [#123](https://example.test/123) | 95 | "
        f"优秀；P0/P1=0；复评前序评分行（实现基线 `{ref_token}`）；"
        f"本次评分基线 SCORE_BASE `{declared}` | 无 | 无 | 无 | Fixture |"
    )


def _call(row, *, prior_rows, base_oid, disambiguate_lines=None, tmp_path):
    def fake_git(root, *args):
        if args[0] == "rev-parse" and args[1].startswith("--disambiguate="):
            lines = disambiguate_lines if disambiguate_lines is not None else [base_oid]
            return "\n".join(lines) + "\n"
        raise AssertionError(f"unexpected git call: {args}")

    original_git = _MOD._git
    _MOD._git = fake_git
    try:
        _MOD._validate_reassessment_row(
            row,
            baseline="\n".join(prior_rows),
            prior_rows=prior_rows,
            pr_number="123",
            base_oid=base_oid,
            root=tmp_path,
        )
    finally:
        _MOD._git = original_git


def test_unit_declared_equal_previous_base_rejected(tmp_path: Path) -> None:
    """同一实现基线重复入账：声明基线恰为上一条行自身基线 → 拒绝。"""
    # declared 与 --base 一致（前缀扩展为 40 位），与上一条行基线相同 → 重复基线
    base_oid = "a1b2c3d4e5f6" + "0" * 28
    prior = _baseline_with_original("a1b2c3d4e5f6")
    row = _unit_row(declared="a1b2c3d4e5f6" + "0" * 28, ref_token="a1b2c3d4e5f6")
    try:
        _call(row, prior_rows=[prior], base_oid=base_oid, tmp_path=tmp_path)
    except _MOD.CheckFailure as exc:
        assert "already covered by the previous score row" in str(exc)
    else:
        raise AssertionError("expected CheckFailure")


def test_unit_ambiguous_short_sha_rejected(tmp_path: Path) -> None:
    """短 SHA 前缀在对象库不唯一（如与 blob 撞前缀）→ 拒绝并要求完整 40 位。"""
    base_oid = "b" * 40
    prior = _baseline_with_original("a1b2c3d4e5f6")
    row = _unit_row(declared="bbbbbbb", ref_token="a1b2c3d4e5f6")
    try:
        _call(
            row,
            prior_rows=[prior],
            base_oid=base_oid,
            disambiguate_lines=[base_oid, "c" * 40],
            tmp_path=tmp_path,
        )
    except _MOD.CheckFailure as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("expected CheckFailure")


def test_unit_previous_row_with_unidentifiable_baseline_errors(tmp_path: Path) -> None:
    """前序行实现基线无法唯一识别 → 报错，不退回任意 token 相交。"""
    base_oid = "b" * 40
    # 前序行无任何可识别基线标签
    prior = (
        "| 2026-08-11 | Original | DOC-080 | [#123](https://example.test/123) | 91 | "
        "优秀；P0/P1=0 | 无 | 无 | 无 | Fixture |\n"
    )
    row = _unit_row(declared=base_oid, ref_token="a1b2c3d4e5f6")
    try:
        _call(row, prior_rows=[prior], base_oid=base_oid, tmp_path=tmp_path)
    except _MOD.CheckFailure as exc:
        assert "no recognizable implementation baseline label" in str(exc)
    else:
        raise AssertionError("expected CheckFailure")


def test_unit_reference_must_hit_previous_own_baseline_not_ancestor(tmp_path: Path) -> None:
    """引用前序行中的祖先/其他 SHA（非其自身基线）→ 拒绝。"""
    base_oid = "b" * 40
    # 前序行自身基线 a1b2c3…，但行内还提到祖先 91590551…
    prior = (
        "| 2026-08-11 | Original | DOC-080 | [#123](https://example.test/123) | 91 | "
        "优秀；P0/P1=0；评分基线 SCORE_BASE `a1b2c3d4e5f6`；"
        "merge 基线 origin/main `91590551c0cb` | 无 | 无 | 无 | Fixture |\n"
    )
    # 复评引用的是祖先 91590551… 而非前序自身基线
    row = _unit_row(declared=base_oid, ref_token="91590551c0cb")
    try:
        _call(row, prior_rows=[prior], base_oid=base_oid, tmp_path=tmp_path)
    except _MOD.CheckFailure as exc:
        assert "must reference the previous formal score row's own" in str(exc)
    else:
        raise AssertionError("expected CheckFailure")
