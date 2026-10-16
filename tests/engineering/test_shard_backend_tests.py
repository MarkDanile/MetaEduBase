"""TD-107 P2-1：shard_backend_tests.py 的 durations 基线契约回归测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "shard_backend_tests.py"

TEST_FILES = [
    "tests/test_a.py",
    "tests/test_b.py",
    "tests/contexts/test_c.py",
    "tests/contexts/test_d.py",
]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path, files: list[str] | None = None) -> Path:
    repo = tmp_path / "pkg"
    (repo / "tests" / "contexts").mkdir(parents=True)
    for rel in files or TEST_FILES:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def test_x():\n    pass\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "--all")
    _git(
        repo,
        "-c",
        "user.name=CI Test",
        "-c",
        "user.email=ci-test@example.invalid",
        "commit",
        "-m",
        "tests",
    )
    return repo


def _run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_baseline(tmp_path: Path, payload: object | str) -> Path:
    path = tmp_path / "backend-durations.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _shards(repo: Path, durations: Path | None, tmp_path: Path) -> tuple[list[str], list[str]]:
    outputs = []
    for shard in ("1", "2"):
        out = tmp_path / f"shard{shard}.list"
        args = ["--shard", shard, "--repo-root", repo, "--output", out]
        if durations is not None:
            args += ["--durations", durations]
        result = _run(*args)
        assert result.returncode == 0, result.stderr
        outputs.append(out.read_text().split())
    return outputs[0], outputs[1]


def test_cold_start_equal_weights_logged(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    out = tmp_path / "shard1.list"
    result = _run("--shard", "1", "--repo-root", repo, "--output", out)
    assert result.returncode == 0, result.stderr
    assert "source=none" in result.stdout
    assert f"files={len(TEST_FILES)}" in result.stdout
    assert "weighted=0" in result.stdout
    assert f"defaulted={len(TEST_FILES)}" in result.stdout
    assert "default-weight=1.0" in result.stdout
    # 冷启动逐条说明每个文件用默认权重
    assert result.stdout.count("durations-baseline-default:") >= len(TEST_FILES)


def test_baseline_hit_reports_source_and_counts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    baseline = _write_baseline(
        tmp_path,
        {"version": 1, "files": {"tests/test_a.py": 5.0, "tests/test_b.py": 2.0}},
    )
    out = tmp_path / "shard1.list"
    result = _run(
        "--shard", "1", "--repo-root", repo, "--output", out,
        "--durations", baseline, "--baseline-source", "run:123 sha256:abc",
    )
    assert result.returncode == 0, result.stderr
    assert "source=run:123 sha256:abc" in result.stdout
    assert "weighted=2" in result.stdout
    assert "defaulted=2" in result.stdout


def test_new_test_gets_explicit_default_weight(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    baseline = _write_baseline(
        tmp_path, {"version": 1, "files": {"tests/test_a.py": 5.0}}
    )
    out = tmp_path / "shard1.list"
    result = _run("--shard", "1", "--repo-root", repo, "--output", out, "--durations", baseline)
    assert result.returncode == 0, result.stderr
    # 新增测试（基线缺失）逐条点名 + 显式默认权重
    assert "durations-baseline-default: tests/test_b.py (weight 1.0)" in result.stdout
    assert "durations-baseline-default: tests/contexts/test_c.py (weight 1.0)" in result.stdout


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        json.dumps({"version": 2, "files": {"tests/test_a.py": 1.0}}),
        json.dumps({"version": 1, "files": {}}),
        json.dumps({"version": 1, "files": "nope"}),
        json.dumps({"version": 1, "files": {"tests/test_a.py": -1.0}}),
        json.dumps({"version": 1, "files": {"tests/test_a.py": "fast"}}),
        '{"version": 1, "files": {"tests/test_a.py": NaN}}',
    ],
    ids=[
        "invalid-json",
        "wrong-version",
        "empty-files",
        "files-not-object",
        "negative-weight",
        "non-numeric-weight",
        "nan-weight",
    ],
)
def test_corrupt_baseline_fails_loudly_never_cold_start(
    tmp_path: Path, payload: str
) -> None:
    repo = _make_repo(tmp_path)
    baseline = _write_baseline(tmp_path, payload)
    out = tmp_path / "shard1.list"
    result = _run("--shard", "1", "--repo-root", repo, "--output", out, "--durations", baseline)
    assert result.returncode == 2
    assert "unusable" in result.stderr
    # 不得伪装成冷启动：输出文件不生成，stdout 无 cold-start 痕迹
    assert not out.exists()
    assert "source=none" not in result.stdout


def test_baseline_never_changes_collection(tmp_path: Path) -> None:
    """历史基线只影响分配：幽灵 key 被忽略，union 恒等于 git ls-files 全集。"""
    repo = _make_repo(tmp_path)
    baseline = _write_baseline(
        tmp_path,
        {
            "version": 1,
            "files": {
                "tests/test_a.py": 9.0,
                "tests/test_ghost_deleted.py": 99.0,
            },
        },
    )
    s1, s2 = _shards(repo, baseline, tmp_path)
    all_out = tmp_path / "all.list"
    result = _run("--all", "--repo-root", repo, "--output", all_out)
    assert result.returncode == 0
    serial = all_out.read_text().split()
    assert sorted(s1 + s2) == serial == sorted(TEST_FILES)
    assert not set(s1) & set(s2)


def test_nonuniform_weights_change_partition(tmp_path: Path) -> None:
    """权重必须真实参与分片：等权与悬殊权重产生不同分配。"""
    repo = _make_repo(tmp_path)
    # sorted 顺序: contexts/test_c, contexts/test_d, test_a, test_b
    eq1, eq2 = _shards(repo, None, tmp_path)
    assert eq1 == ["tests/contexts/test_c.py", "tests/test_a.py"]
    assert eq2 == ["tests/contexts/test_d.py", "tests/test_b.py"]

    heavy = _write_baseline(
        tmp_path, {"version": 1, "files": {"tests/contexts/test_c.py": 100.0}}
    )
    h1, h2 = _shards(repo, heavy, tmp_path)
    assert h1 == ["tests/contexts/test_c.py"]
    assert h2 == ["tests/contexts/test_d.py", "tests/test_a.py", "tests/test_b.py"]
    assert (h1, h2) != (eq1, eq2)


def test_partition_deterministic(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    baseline = _write_baseline(
        tmp_path,
        {"version": 1, "files": {"tests/test_a.py": 3.0, "tests/test_b.py": 0.25}},
    )
    first = _shards(repo, baseline, tmp_path)
    second = _shards(repo, baseline, tmp_path)
    assert first == second


def test_validate_durations_mode(tmp_path: Path) -> None:
    baseline = _write_baseline(
        tmp_path, {"version": 1, "files": {"tests/test_a.py": 1.5}}
    )
    ok = _run("--validate-durations", baseline)
    assert ok.returncode == 0
    assert "sha256=" in ok.stdout
    assert "files=1" in ok.stdout
    assert "total-seconds=1.5" in ok.stdout

    bad = _write_baseline(tmp_path, json.dumps({"version": 1, "files": {}}))
    result = _run("--validate-durations", bad)
    assert result.returncode == 2
    assert "unusable" in result.stderr
