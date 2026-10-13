"""TD-107 P2-1：resolve_durations_baseline.py 单点解析契约回归测试。

通过注入 gh_json / gh_download / validate 假件验证解析决策；validate 默认走
真实 shard_backend_tests.py --validate-durations（子进程），保证集成保真。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "resolve_durations_baseline.py"
SPEC = importlib.util.spec_from_file_location("resolve_durations_baseline", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

VALID_PAYLOAD = json.dumps({"version": 1, "files": {"tests/test_a.py": 1.5}})
CORRUPT_PAYLOAD = "this is not json"


class FakeGh:
    """按调用顺序编排 gh 响应；记录所有查询以便断言。"""

    def __init__(self) -> None:
        self.branch_runs: dict[str, list[int]] = {}
        self.artifacts: dict[int, list[dict]] = {}
        self.downloads: dict[int, str] = {}  # run_id -> payload text; 缺失=下载失败
        self.queries: list[list[str]] = []

    def gh_json(self, args: list[str]) -> object:
        self.queries.append(args)
        if args[:2] == ["run", "list"]:
            branch = args[args.index("--branch") + 1]
            return [{"databaseId": rid} for rid in self.branch_runs.get(branch, [])]
        if args[0] == "api" and "artifacts?name=" in args[1]:
            run_id = int(args[1].split("/actions/runs/")[1].split("/")[0])
            return {"artifacts": self.artifacts.get(run_id, [])}
        raise AssertionError(f"unexpected gh args: {args}")

    def gh_download(self, run_id: str, dest_dir: Path) -> Path:
        """忠实模拟 gh run download：目标文件已存在时拒绝提取（file exists）。"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        payload = self.downloads.get(int(run_id))
        if payload is None:
            raise RuntimeError("HTTP 403: artifact expired or forbidden")
        path = dest_dir / "backend-durations.json"
        if path.exists():
            raise RuntimeError(
                'error extracting "backend-durations.json": file exists'
            )
        path.write_text(payload, encoding="utf-8")
        return path


def _artifact(artifact_id: int, expired: bool = False) -> dict:
    return {"id": artifact_id, "name": "backend-durations", "expired": expired}


def test_cold_start_when_no_candidate_runs(tmp_path: Path) -> None:
    fake = FakeGh()
    logs: list[str] = []
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=logs.append
    )
    assert res.status == "cold-start"
    assert "no-candidate-run" in res.reason
    assert any("cold start" in line for line in logs)


def test_selects_first_valid_candidate_and_pins_identity(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [111]
    fake.artifacts[111] = [_artifact(7)]
    fake.downloads[111] = VALID_PAYLOAD
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=lambda _: None
    )
    assert res.status == "selected"
    assert res.run_id == "111"
    assert res.artifact_id == "7"
    assert res.sha256 == hashlib.sha256(VALID_PAYLOAD.encode()).hexdigest()
    assert (tmp_path / "backend-durations.json").exists()


def test_corrupt_candidate_skipped_with_reason_then_next_selected(tmp_path: Path) -> None:
    """损坏候选被跳过且原因留痕；其残留文件不得阻塞后续候选（真实 gh 行为：
    目标已存在时拒绝提取——曾因共享目录导致后续候选全部伪 download-failed）。"""
    fake = FakeGh()
    fake.branch_runs["feature"] = [111, 222]
    fake.artifacts[111] = [_artifact(7)]
    fake.downloads[111] = CORRUPT_PAYLOAD
    fake.artifacts[222] = [_artifact(8)]
    fake.downloads[222] = VALID_PAYLOAD
    logs: list[str] = []
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=logs.append
    )
    assert res.status == "selected"
    assert res.run_id == "222"
    assert any("111" in line and "corrupt-baseline" in line for line in logs)


def test_download_failure_skipped_then_next_selected(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [111, 222]
    fake.artifacts[111] = [_artifact(7)]  # 无 downloads 项 → 403
    fake.artifacts[222] = [_artifact(8)]
    fake.downloads[222] = VALID_PAYLOAD
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=lambda _: None
    )
    assert res.status == "selected"
    assert res.run_id == "222"


def test_all_candidates_unusable_is_cold_start_with_distinct_reason(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [111, 222]
    fake.artifacts[111] = []  # 无 artifact
    fake.artifacts[222] = [_artifact(8)]
    fake.downloads[222] = CORRUPT_PAYLOAD
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=lambda _: None
    )
    assert res.status == "cold-start"
    assert "no-usable-baseline" in res.reason
    assert "111" in res.reason and "222" in res.reason
    # 与“无候选”是不同 reason，不与下载失败混淆
    assert "no-candidate-run" not in res.reason


def test_candidate_query_failure_is_explicit_cold_start_reason(tmp_path: Path) -> None:
    def boom(args: list[str]) -> object:
        raise RuntimeError("HTTP 403: Resource not accessible")

    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=boom, gh_download=FakeGh().gh_download, log=lambda _: None
    )
    assert res.status == "cold-start"
    assert "candidate-query-failed" in res.reason


def test_branch_first_then_main_with_dedup(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [1, 2]
    fake.branch_runs["main"] = [2, 3]
    attempts: list[str] = []

    def tracking_download(run_id: str, dest_dir: Path) -> Path:
        attempts.append(run_id)
        return fake.gh_download(run_id, dest_dir)

    for rid in (1, 2, 3):
        fake.artifacts[rid] = [_artifact(10 + rid)]
    fake.downloads[3] = VALID_PAYLOAD  # 只有 main 的 run 3 可用
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=tracking_download, log=lambda _: None
    )
    assert res.status == "selected"
    assert res.run_id == "3"
    # 顺序：当前分支 1, 2 → main 去重后只剩 3（run 2 不重复下载）
    assert attempts == ["1", "2", "3"]


def test_main_branch_queries_only_main(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["main"] = [5]
    fake.artifacts[5] = [_artifact(15)]
    fake.downloads[5] = VALID_PAYLOAD
    res = MODULE.resolve(
        "o/r", "main", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=lambda _: None
    )
    assert res.status == "selected"
    branches_queried = [q[q.index("--branch") + 1] for q in fake.queries if q[:2] == ["run", "list"]]
    assert branches_queried == ["main"]


def test_expired_artifact_not_selected(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [111]
    fake.artifacts[111] = [_artifact(7, expired=True)]
    res = MODULE.resolve(
        "o/r", "feature", tmp_path, gh_json=fake.gh_json, gh_download=fake.gh_download, log=lambda _: None
    )
    assert res.status == "cold-start"
    assert "no-usable-baseline" in res.reason


def test_main_writes_github_output(tmp_path: Path) -> None:
    fake = FakeGh()
    fake.branch_runs["feature"] = [111]
    fake.artifacts[111] = [_artifact(7)]
    fake.downloads[111] = VALID_PAYLOAD
    output = tmp_path / "gh-output"
    output.touch()
    rc = MODULE.main(
        ["--repo", "o/r", "--branch", "feature", "--workdir", str(tmp_path / "wd"),
         "--github-output", str(output)],
        gh_json=fake.gh_json,
        gh_download=fake.gh_download,
        log=lambda _: None,
    )
    assert rc == 0
    text = output.read_text()
    assert "baseline_status=selected" in text
    assert "baseline_run_id=111" in text
    assert "baseline_artifact_id=7" in text
    assert f"baseline_sha256={hashlib.sha256(VALID_PAYLOAD.encode()).hexdigest()}" in text
    # outputs 必须是单行 key=value（reason 不允许混入换行破坏 GITHUB_OUTPUT 协议）
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 5
    assert all("=" in line and line.count("\r") == 0 for line in lines)
