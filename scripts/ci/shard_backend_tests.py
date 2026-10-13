#!/usr/bin/env python3
"""Shard backend pytest test files for parallel CI runs.

TD-107：full hermetic 模式将单一串行 job 改为两个并行分片。本脚本按
文件级 greedy 均衡把收集到的 test 文件拆成两个互斥的清单，并保证
shard1 ∪ shard2 == serial_full。基线 durations 缺失时回退为文件计数
1.0（保证可重现起点，避免首次运行无数据）。

新文件不需要手写登记；按 git ls-files 收集 tests/ 树下的所有 test_*.py，
自然包含新增测试。

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
        --output shard1.list

输入约定：
    * --shard {1,2}：输出该 shard 的文件清单。
    * --all：输出 serial_full 清单（shard1 ∪ shard2 应等于此）。
    * --repo-root：pytest 工作目录（含 tests/ 的 Python 包根）。
    * --durations：可选 JSON 文件，键 = 测试文件相对路径，值 = 累计秒数。
      缺文件 / 缺键则回退为 1.0。

输出：清单写入 --output，每行一个相对路径（用 LF）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
        result = __import__("subprocess").run(
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


def _load_durations(path: Path | None) -> dict[str, float]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}


def _balanced_partition(paths: list[str], weights: dict[str, float]) -> list[list[str]]:
    """Greedy LPT partition: walk paths in sorted order, append to lighter bin.

    Sorted input → deterministic output; this is critical for sharding to
    reach a stable allocation between runs.
    """
    bins: list[list[str]] = [[], []]
    loads: list[float] = [0.0, 0.0]
    for p in paths:
        w = weights.get(p, 1.0)
        if loads[0] <= loads[1]:
            bins[0].append(p)
            loads[0] += w
        else:
            bins[1].append(p)
            loads[1] += w
    return bins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shard", choices=["1", "2"], help="emit the chosen shard's list")
    mode.add_argument("--all", action="store_true", help="emit the serial_full list")
    parser.add_argument("--repo-root", type=Path, required=True, help="path to package root containing tests/")
    parser.add_argument(
        "--durations",
        type=Path,
        default=None,
        help="optional durations JSON (key = file path, value = seconds)",
    )
    parser.add_argument("--output", type=Path, required=True, help="output list file path")
    args = parser.parse_args()

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

    weights = _load_durations(args.durations)

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
