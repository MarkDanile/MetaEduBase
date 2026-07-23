#!/usr/bin/env python3
"""Run mypy and reject errors above the reviewed historical baseline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = SERVER_ROOT / "mypy-baseline.json"
ERROR_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::\d+)?: error: .* \[(?P<code>[^]]+)]$"
)


def parse_errors(output: str) -> tuple[Counter[str], list[str]]:
    counts: Counter[str] = Counter()
    fatal_lines: list[str] = []
    for line in output.splitlines():
        if ": error:" not in line:
            continue
        match = ERROR_RE.match(line)
        if match is None:
            fatal_lines.append(line)
            continue
        key = f"{match.group('path')}::{match.group('code')}"
        counts[key] += 1
    return counts, fatal_lines


def find_regressions(
    current: Counter[str], baseline: dict[str, int]
) -> dict[str, tuple[int, int]]:
    return {
        key: (baseline.get(key, 0), count)
        for key, count in current.items()
        if count > baseline.get(key, 0)
    }


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = payload.get("errors")
    if not isinstance(errors, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and value >= 0
        for key, value in errors.items()
    ):
        raise ValueError(f"Invalid mypy baseline: {path}")
    return errors


def write_baseline(path: Path, counts: Counter[str]) -> None:
    payload = {
        "version": 1,
        "description": (
            "Historical mypy errors keyed by relative path and error code. "
            "Counts may only stay equal or decrease."
        ),
        "errors": dict(sorted(counts.items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def run_mypy() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "app",
            "--no-pretty",
            "--show-error-codes",
            "--no-error-summary",
        ],
        cwd=SERVER_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Replace the baseline with the current reviewed mypy result.",
    )
    args = parser.parse_args()

    result = run_mypy()
    output = result.stdout + result.stderr
    current, fatal_lines = parse_errors(output)
    if fatal_lines or (result.returncode != 0 and not current):
        print(output, file=sys.stderr)
        print("mypy did not produce a parseable type-check result.", file=sys.stderr)
        return 2

    if args.write_baseline:
        write_baseline(BASELINE_PATH, current)
        print(f"Wrote {sum(current.values())} errors across {len(current)} baseline keys.")
        return 0

    baseline = load_baseline(BASELINE_PATH)
    regressions = find_regressions(current, baseline)
    if regressions:
        print("mypy baseline regression:", file=sys.stderr)
        for key, (allowed, actual) in sorted(regressions.items()):
            print(f"  {key}: allowed {allowed}, found {actual}", file=sys.stderr)
        return 1

    reductions = {
        key: (allowed, current.get(key, 0))
        for key, allowed in baseline.items()
        if current.get(key, 0) < allowed
    }
    print(
        f"mypy baseline passed: {sum(current.values())} historical errors "
        f"across {len(current)} keys; 0 regressions."
    )
    if reductions:
        print(f"Baseline can be reduced for {len(reductions)} key(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
