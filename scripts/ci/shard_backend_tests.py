#!/usr/bin/env python3
"""Shard backend pytest test files for parallel CI runs.

TD-107：full hermetic 模式将单一串行 job 改为两个并行分片。本脚本按
文件级 greedy LPT 均衡把收集到的 test 文件拆成两个互斥的清单，并保证
shard1 ∪ shard2 == serial_full。

TD-107 P2-1（durations 基线契约）：
    * 测试收集永远来自 git ls-files——基线只影响分配权重，绝不决定某个
      测试文件是否被收集。
    * 无 --durations（冷启动）：所有文件使用显式默认权重 DEFAULT_WEIGHT，
      日志逐条说明。
    * 有 --durations：文件必须通过严格格式校验（version、files 非空、
      权重为有限非负数）。已选定基线却损坏/不可读时退出码 2——绝不静默
      伪装成冷启动。
    * 基线中缺失的新测试文件使用显式默认权重 DEFAULT_WEIGHT 并逐条记录；
      基线中已不存在于收集集的 key 被忽略。
    * --validate-durations FILE：只校验并输出 sha256=/files=/total-seconds=
      统计，供基线解析与发布门禁复用同一实现。

用法：
    python3 scripts/ci/shard_backend_tests.py --shard 1 \\
        --repo-root packages/server-python \\
        --output shard1.list
    python3 scripts/ci/shard_backend_tests.py --all \\
        --repo-root packages/server-python \\
        --output serial_full.list
    python3 scripts/ci/shard_backend_tests.py --shard 1 \\
        --repo-root packages/server-python \\
        --durations backend-durations.json \\
        --baseline-source "run:123 sha256:abc..." \\
        --output shard1.list
    python3 scripts/ci/shard_backend_tests.py --validate-durations backend-durations.json

输入约定：
    * --shard {1,2}：输出该 shard 的文件清单。
    * --all：输出 serial_full 清单（shard1 ∪ shard2 应等于此）。
    * --validate-durations：校验基线文件并输出统计（不需要 --repo-root）。
    * --repo-root：pytest 工作目录（含 tests/ 的 Python 包根）。
    * --durations：已选定的历史 durations JSON（键 = 测试文件相对路径，
      值 = 累计秒数）。缺失的键回退 DEFAULT_WEIGHT。
    * --baseline-source：可选的基线身份描述（如 run id + sha256），
      仅用于日志，不参与计算。

输出：清单写入 --output，每行一个相对路径（用 LF）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path


DEFAULT_WEIGHT = 1.0
_BASELINE_SOURCE_CAP = 20


class BaselineError(ValueError):
    """Selected durations baseline is unusable (never silently ignored)."""


def _collect_test_files(repo_root: Path) -> list[str]:
    """List every collected test file via git ls-files (cheap, deterministic).

    Falls back to a directory walk if git is unavailable so the script is
    still usable for ad-hoc local runs.
    """
    tests_root = repo_root / "tests"
    if not tests_root.exists():
        return []
    # git ls-files is faster than walking and matches what CI sees on a clean
    # checkout. Use -- so filenames starting with '-' are not parsed as flags.
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "--",
                "tests",
            ],
            check=True,
            capture_output=True,
        )
    except Exception:
        return _walk_tests(repo_root)
    raw = result.stdout
    if isinstance(raw, bytes):
        items = [p.decode() for p in raw.split(b"\0") if p]
    else:
        items = [p for p in raw.split("\0") if p]
    out: list[str] = []
    for rel in items:
        if not rel.endswith(".py"):
            continue
        if "/test_" not in rel and not rel.startswith("tests/test_"):
            continue
        out.append(rel)
    return sorted(out)


def _walk_tests(repo_root: Path) -> list[str]:
    tests_root = repo_root / "tests"
    out: list[str] = []
    for p in tests_root.rglob("test_*.py"):
        if p.is_file():
            out.append(str(p.relative_to(repo_root)))
    return sorted(out)


def validate_durations_payload(data: object) -> dict[str, float]:
    """Validate a durations baseline payload; raise BaselineError on any defect."""
    if not isinstance(data, dict):
        raise BaselineError("baseline is not a JSON object")
    if data.get("version") != 1:
        raise BaselineError(f"unsupported baseline version: {data.get('version')!r}")
    files = data.get("files")
    if not isinstance(files, dict):
        raise BaselineError("baseline 'files' is not an object")
    if not files:
        raise BaselineError("baseline 'files' is empty")
    out: dict[str, float] = {}
    for key, value in files.items():
        if not isinstance(key, str) or not key:
            raise BaselineError("baseline file key must be a non-empty string")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BaselineError(f"weight for {key!r} is not numeric: {value!r}")
        weight = float(value)
        if not math.isfinite(weight) or weight < 0:
            raise BaselineError(f"weight for {key!r} must be finite and >= 0, got {value!r}")
        out[key] = weight
    return out


def _load_durations_strict(path: Path) -> dict[str, float]:
    """Load a SELECTED baseline. Any defect is a BaselineError, never a fallback."""
    if not path.exists():
        raise BaselineError(f"durations file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"durations file is not valid JSON: {exc}") from exc
    return validate_durations_payload(data)


def _balanced_partition(paths: list[str], weights: dict[str, float]) -> list[list[str]]:
    """Greedy LPT partition: walk paths in sorted order, append to lighter bin.

    Sorted input → deterministic output; this is critical for sharding to
    reach a stable allocation between runs.
    """
    bins: list[list[str]] = [[], []]
    loads: list[float] = [0.0, 0.0]
    for p in paths:
        w = weights.get(p, DEFAULT_WEIGHT)
        if loads[0] <= loads[1]:
            bins[0].append(p)
            loads[0] += w
        else:
            bins[1].append(p)
            loads[1] += w
    return bins


def _log_weight_provenance(
    files: list[str], weights: dict[str, float], source: str
) -> None:
    """Make weight provenance loud: hits, defaults (new tests), and source."""
    weighted = [p for p in files if p in weights]
    defaulted = [p for p in files if p not in weights]
    print(
        "durations-baseline:"
        f" source={source}"
        f" files={len(files)}"
        f" weighted={len(weighted)}"
        f" defaulted={len(defaulted)}"
        f" default-weight={DEFAULT_WEIGHT}"
    )
    for path in defaulted[:_BASELINE_SOURCE_CAP]:
        print(f"durations-baseline-default: {path} (weight {DEFAULT_WEIGHT})")
    if len(defaulted) > _BASELINE_SOURCE_CAP:
        print(f"durations-baseline-default: ... and {len(defaulted) - _BASELINE_SOURCE_CAP} more")


def _validate_mode(path: Path) -> int:
    try:
        weights = _load_durations_strict(path)
    except BaselineError as exc:
        print(f"error: selected durations baseline is unusable: {exc}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"sha256={digest}")
    print(f"files={len(weights)}")
    print(f"total-seconds={round(sum(weights.values()), 4)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shard", choices=["1", "2"], help="emit the chosen shard's list")
    mode.add_argument("--all", action="store_true", help="emit the serial_full list")
    mode.add_argument(
        "--validate-durations",
        type=Path,
        default=None,
        help="validate a durations baseline file and print sha256=/files= stats",
    )
    parser.add_argument("--repo-root", type=Path, help="path to package root containing tests/")
    parser.add_argument(
        "--durations",
        type=Path,
        default=None,
        help="selected durations JSON (key = file path, value = seconds)",
    )
    parser.add_argument(
        "--baseline-source",
        default=None,
        help="optional baseline identity (e.g. 'run:123 sha256:...'), log-only",
    )
    parser.add_argument("--output", type=Path, help="output list file path")
    args = parser.parse_args()

    if args.validate_durations is not None:
        return _validate_mode(args.validate_durations)

    if args.repo_root is None or args.output is None:
        parser.error("--repo-root and --output are required for --shard/--all")

    repo_root: Path = args.repo_root.resolve()
    if not repo_root.is_dir():
        print(f"repo root not a directory: {repo_root}", file=sys.stderr)
        return 2

    files = _collect_test_files(repo_root)
    if not files:
        # Empty list is a valid signal: emit and let CI fail downstream if that
        # is unexpected. We do not pretend there is content to shard.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8", newline="\n")
        return 0

    weights: dict[str, float] = {}
    if args.durations is not None:
        try:
            weights = _load_durations_strict(args.durations)
        except BaselineError as exc:
            # A selected-but-broken baseline must never masquerade as cold start.
            print(
                f"error: selected durations baseline is unusable: {exc}",
                file=sys.stderr,
            )
            return 2
        source = args.baseline_source or "unspecified"
    else:
        source = args.baseline_source or "none"
    _log_weight_provenance(files, weights, source)

    if args.all:
        lines = files
    else:
        bins = _balanced_partition(files, weights)
        idx = 0 if args.shard == "1" else 1
        lines = bins[idx]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
