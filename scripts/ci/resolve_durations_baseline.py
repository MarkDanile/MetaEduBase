#!/usr/bin/env python3
"""TD-107 P2-1：为两个 full hermetic shard 单点解析同一份历史 durations 基线。

在 backend job 内运行一次（唯一解析点），两个 shard 通过 job outputs 消费同一
(run_id, artifact_id, sha256)——shard 不得各自查询"最新"，避免跨 shard
TOCTOU 漂移。

候选顺序（确定性）：当前分支最新成功 CI run（最多 5 个），其后 main 最新成功
run（去重）。首个满足以下全部条件的 run 胜出：
    1. 含未过期的 backend-durations artifact；
    2. artifact 可下载；
    3. 内容通过 shard_backend_tests.py --validate-durations 严格校验。
全部不可用 → cold-start（等权回退），reason 逐条说明为何不可用——冷启动是
显式结论，不是下载失败的伪装。基线一旦选定（status=selected），下游下载或
校验失败由 shard 步骤硬性失败承担，不回退。

输出（--github-output 追加写入）：
    baseline_status=selected|cold-start
    baseline_reason=<单行说明>
    baseline_run_id / baseline_artifact_id / baseline_sha256（仅 selected）
选定时基线 JSON 位于 <workdir>/backend-durations.json，由调用方作为当前 run
artifact 重新发布供 shard 在同 run 内下载。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARD_SCRIPT = REPO_ROOT / "scripts" / "ci" / "shard_backend_tests.py"
ARTIFACT_NAME = "backend-durations"
BASELINE_FILENAME = "backend-durations.json"
CANDIDATE_LIMIT = 5
_REASON_LIMIT = 800


@dataclass(frozen=True)
class Resolution:
    status: str  # "selected" | "cold-start"
    reason: str
    run_id: str = ""
    artifact_id: str = ""
    sha256: str = ""


def _gh_json_real(args: list[str]) -> object:
    res = subprocess.run(["gh", *args], check=False, capture_output=True)
    if res.returncode != 0:
        detail = res.stderr.decode(errors="replace").strip()[:300] or "gh command failed"
        raise RuntimeError(detail)
    return json.loads(res.stdout)


def _gh_download_real(run_id: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["gh", "run", "download", run_id, "--name", ARTIFACT_NAME, "--dir", str(dest_dir)],
        check=False,
        capture_output=True,
    )
    if res.returncode != 0:
        detail = res.stderr.decode(errors="replace").strip()[:300] or "gh run download failed"
        raise RuntimeError(detail)
    path = dest_dir / BASELINE_FILENAME
    if not path.exists():
        raise RuntimeError(f"downloaded artifact missing {BASELINE_FILENAME}")
    return path


def _validate_real(path: Path) -> dict[str, str]:
    res = subprocess.run(
        [sys.executable, str(SHARD_SCRIPT), "--validate-durations", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        detail = res.stderr.strip()[:300] or "baseline validation failed"
        raise RuntimeError(detail)
    stats: dict[str, str] = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            stats[key.strip()] = value.strip()
    if "sha256" not in stats:
        raise RuntimeError("validator output missing sha256")
    return stats


def _one_line(text: str) -> str:
    return " ".join(text.split())[:_REASON_LIMIT]


def candidate_runs(
    repo: str,
    branch: str,
    *,
    gh_json: Callable[[list[str]], object] = _gh_json_real,
) -> list[tuple[str, str]]:
    """Same-branch successful runs first, then main's; dedup, newest first."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    branches = [branch] if branch == "main" else [branch, "main"]
    for br in branches:
        runs = gh_json(
            [
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                "ci.yml",
                "--branch",
                br,
                "--status",
                "success",
                "--limit",
                str(CANDIDATE_LIMIT),
                "--json",
                "databaseId",
            ]
        )
        if not isinstance(runs, list):
            raise RuntimeError(f"unexpected gh run list payload for branch {br!r}")
        for item in runs:
            rid = str(item.get("databaseId", ""))
            if rid and rid not in seen:
                seen.add(rid)
                out.append((rid, br))
    return out


def resolve(
    repo: str,
    branch: str,
    workdir: Path,
    *,
    gh_json: Callable[[list[str]], object] = _gh_json_real,
    gh_download: Callable[[str, Path], Path] = _gh_download_real,
    validate: Callable[[Path], dict[str, str]] = _validate_real,
    log: Callable[[str], None] = print,
) -> Resolution:
    try:
        candidates = candidate_runs(repo, branch, gh_json=gh_json)
    except (RuntimeError, json.JSONDecodeError) as exc:
        reason = f"candidate-query-failed: {exc}"
        log(f"durations baseline cold start: {reason}")
        return Resolution("cold-start", _one_line(reason))

    skipped: list[str] = []
    for run_id, br in candidates:
        try:
            data = gh_json(
                ["api", f"repos/{repo}/actions/runs/{run_id}/artifacts?name={ARTIFACT_NAME}"]
            )
            artifacts = data.get("artifacts", []) if isinstance(data, dict) else []
            artifact_id = next(
                (
                    str(a["id"])
                    for a in artifacts
                    if a.get("name") == ARTIFACT_NAME and not a.get("expired", True)
                ),
                None,
            )
        except (RuntimeError, json.JSONDecodeError) as exc:
            skipped.append(f"run {run_id}: artifact-query-failed: {exc}")
            continue
        if artifact_id is None:
            skipped.append(f"run {run_id} ({br}): no usable '{ARTIFACT_NAME}' artifact")
            continue
        try:
            path = gh_download(run_id, workdir)
        except RuntimeError as exc:
            skipped.append(f"run {run_id}: download-failed: {exc}")
            continue
        try:
            stats = validate(path)
        except RuntimeError as exc:
            skipped.append(f"run {run_id}: corrupt-baseline: {exc}")
            continue
        for entry in skipped:
            log(f"skipped candidate: {entry}")
        log(
            "durations baseline selected:"
            f" run={run_id} artifact={artifact_id}"
            f" sha256={stats['sha256']} files={stats.get('files', '?')}"
        )
        return Resolution("selected", "ok", run_id, artifact_id, stats["sha256"])

    if not candidates:
        reason = "no-candidate-run (no successful CI run on this branch or main yet)"
    else:
        reason = "no-usable-baseline: " + "; ".join(skipped)
    log(f"durations baseline cold start: {reason}")
    return Resolution("cold-start", _one_line(reason))


def main(
    argv: list[str] | None = None,
    *,
    gh_json: Callable[[list[str]], object] = _gh_json_real,
    gh_download: Callable[[str, Path], Path] = _gh_download_real,
    validate: Callable[[Path], dict[str, str]] = _validate_real,
    log: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--branch", required=True, help="current branch name")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args(argv)

    resolution = resolve(
        args.repo,
        args.branch,
        args.workdir,
        gh_json=gh_json,
        gh_download=gh_download,
        validate=validate,
        log=log,
    )

    lines = [
        f"baseline_status={resolution.status}",
        f"baseline_reason={resolution.reason}",
    ]
    if resolution.status == "selected":
        lines += [
            f"baseline_run_id={resolution.run_id}",
            f"baseline_artifact_id={resolution.artifact_id}",
            f"baseline_sha256={resolution.sha256}",
        ]
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    for line in lines:
        log(f"output: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
