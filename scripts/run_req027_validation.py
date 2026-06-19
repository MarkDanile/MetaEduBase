#!/usr/bin/env python3
"""REQ-027 P2 weak recall wrapper — load v1 + v2 samples, run two rounds.

Round 1: REQ-026 v1 samples (复跑) — baseline for cross-round comparison.
Round 2: REQ-027 v2 samples (新增 5 条) — verify expanded sample set.

Outputs two Markdown reports into docs/02-delivery-plans/01-specs/.
By default dry-run; pass --allow-llm to call the configured LLM provider.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_req024_p2_real_validation.py"
V1_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req026_weak_recall.example.json"
)
V2_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req027_weak_recall_v2.example.json"
)
SPECS = REPO_ROOT / "docs" / "02-delivery-plans" / "01-specs"

V1_REPORT = SPECS / "2026-06-18-req-027-rag-effect-comparison-v1-report.md"
V2_REPORT = SPECS / "2026-06-18-req-027-rag-effect-comparison-v2-report.md"


def _run_round(
    samples_path: Path,
    out_path: Path,
    *,
    allow_llm: bool,
    title: str,
) -> int:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--weak-recall-samples",
        str(samples_path),
        "--out",
        str(out_path),
        "--report-title",
        title,
    ]
    if allow_llm:
        cmd.append("--allow-llm")
    print(f"running: {' '.join(cmd)}")
    return subprocess.call(cmd)


def _merge_samples(v1: Path, v2: Path, merged_path: Path) -> int:
    v1_data = json.loads(v1.read_text(encoding="utf-8"))
    v2_data = json.loads(v2.read_text(encoding="utf-8"))
    merged = {
        "description": "REQ-027 v1+v2 merged weak recall samples",
        "samples": list(v1_data.get("samples", []) or []) + list(v2_data.get("samples", []) or []),
        "questions": list(v1_data.get("questions", []) or []) + list(v2_data.get("questions", []) or []),
    }
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(merged["questions"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_req027_validation")
    parser.add_argument(
        "--allow-llm",
        action="store_true",
        help="Allow sending retrieved context / prompt to the configured LLM provider.",
    )
    parser.add_argument(
        "--skip-v1",
        action="store_true",
        help="Skip Round 1 (v1 re-run); only run Round 2 (v1+v2 merged).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if not SCRIPT.exists():
        print(f"missing base script: {SCRIPT}", file=sys.stderr)
        return 2
    if not V1_SAMPLES.exists() or not V2_SAMPLES.exists():
        print(f"missing sample set(s): v1={V1_SAMPLES.exists()} v2={V2_SAMPLES.exists()}", file=sys.stderr)
        return 2
    SPECS.mkdir(parents=True, exist_ok=True)

    rc = 0
    if not args.skip_v1:
        rc1 = _run_round(
            V1_SAMPLES,
            V1_REPORT,
            allow_llm=args.allow_llm,
            title=f"REQ-027 P2 RAG 弱召回样例 v1 复跑报告 ({'real LLM' if args.allow_llm else 'dry-run'})",
        )
        rc = rc or rc1
        print(f"v1 report: {V1_REPORT} (rc={rc1})")

    merged_path = Path("/tmp/req027_merged.json")
    total = _merge_samples(V1_SAMPLES, V2_SAMPLES, merged_path)
    print(f"merged {total} questions -> {merged_path}")
    rc2 = _run_round(
        merged_path,
        V2_REPORT,
        allow_llm=args.allow_llm,
        title=f"REQ-027 P2 RAG 弱召回样例 v1+v2 报告 ({'real LLM' if args.allow_llm else 'dry-run'})",
    )
    rc = rc or rc2
    print(f"v2 report: {V2_REPORT} (rc={rc2})")
    return rc


if __name__ == "__main__":
    sys.exit(main())