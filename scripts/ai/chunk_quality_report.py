#!/usr/bin/env python3
"""TD-051 chunk quality report — document_chunks metadata governance.

Outputs 7 metrics for the current PG database:
1. total_chunks — overall row count
2. section_path_empty — count + ratio of chunks with NULL/'' section_path
3. section_title_empty — count + ratio of chunks with NULL/'' section_title
4. char_start_null — count of chunks where char_start IS NULL
5. char_start_zero_zero — count of chunks where char_start=0 AND char_end=0
6. orphan_chunks — count of chunks whose file_id has no matching files.id
7. length_buckets — distribution of LENGTH(content) into 7 buckets
8. offset_overlaps — count of chunks where (char_start, char_end) overlaps
   the next chunk in the same file (catches re-chunk bugs)

Usage:
    python scripts/ai/chunk_quality_report.py [--tenant default] [--json]
    python scripts/ai/chunk_quality_report.py --baseline-before path.json

Output:
    Markdown by default; JSON if --json. Also writes a baseline JSON
    (--baseline-after path.json) for before/after diff.

Note: complements scripts/ai/evidence_coverage_report.py (REQ-010 metrics).
TD-051 AC-5 requires running this BEFORE and AFTER rebuild_document_chunks
to prove structural metadata improved.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Ensure server-python is importable when run from repo root
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "packages",
        "server-python",
    ),
)

from app.config import settings  # noqa: E402
from app.shared.infrastructure.database import engine  # noqa: E402


_LENGTH_BUCKETS = [
    ("<100", 0, 99),
    ("100-199", 100, 199),
    ("200-349", 200, 349),
    ("350-499", 350, 499),
    ("500-799", 500, 799),
    ("800-1199", 800, 1199),
    (">=1200", 1200, 10**9),
]


async def _collect_quality(
    session: AsyncSession, tenant_id: str
) -> dict[str, Any]:
    """Run all TD-051 quality metrics for one tenant."""
    tid = tenant_id

    # 1. total chunks
    total_r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.document_chunks "
            "WHERE tenant_id = :tid"
        ),
        {"tid": tid},
    )
    total = int(total_r.scalar() or 0)

    # 2-5. empty / null metadata
    summary_r = await session.execute(
        text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE section_path IS NULL OR section_path = '') AS sp_empty, "
            "  COUNT(*) FILTER (WHERE section_title IS NULL OR section_title = '') AS st_empty, "
            "  COUNT(*) FILTER (WHERE char_start IS NULL) AS cs_null, "
            "  COUNT(*) FILTER (WHERE char_start = 0 AND char_end = 0) AS cs_zero_zero "
            "FROM metaedu.document_chunks "
            "WHERE tenant_id = :tid"
        ),
        {"tid": tid},
    )
    srow = summary_r.first()
    sp_empty = int(srow[0])
    st_empty = int(srow[1])
    cs_null = int(srow[2])
    cs_zero_zero = int(srow[3])

    # 6. orphan chunks (file_id no matching files.id)
    orphan_r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.document_chunks c "
            "WHERE c.tenant_id = :tid "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.files f "
            "  WHERE f.tenant_id = c.tenant_id AND f.id = c.file_id"
            ")"
        ),
        {"tid": tid},
    )
    orphan = int(orphan_r.scalar() or 0)

    # 7. length buckets
    bucket_counts: list[dict[str, Any]] = []
    for label, lo, hi in _LENGTH_BUCKETS:
        r = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.document_chunks "
                "WHERE tenant_id = :tid "
                "AND LENGTH(content) >= :lo AND LENGTH(content) <= :hi"
            ),
            {"tid": tid, "lo": lo, "hi": hi},
        )
        bucket_counts.append(
            {"bucket": label, "count": int(r.scalar() or 0)}
        )

    # 8. offset overlaps (catches re-chunk monotonicity bugs)
    # Two consecutive chunks (by file_id, chunk_index) overlap if
    # next.char_start < prev.char_end. We approximate by checking
    # each pair where both char_start and char_end are non-null.
    overlap_r = await session.execute(
        text(
            "SELECT COUNT(*) FROM ("
            "  SELECT "
            "    char_start, char_end, "
            "    LEAD(char_start) OVER ("
            "      PARTITION BY file_id ORDER BY chunk_index"
            "    ) AS next_cs "
            "  FROM metaedu.document_chunks "
            "  WHERE tenant_id = :tid "
            "  AND char_start IS NOT NULL AND char_end IS NOT NULL "
            ") s "
            "WHERE next_cs IS NOT NULL AND next_cs < char_end"
        ),
        {"tid": tid},
    )
    offset_overlaps = int(overlap_r.scalar() or 0)

    return {
        "tenant_id": tid,
        "total_chunks": total,
        "section_path_empty": sp_empty,
        "section_title_empty": st_empty,
        "char_start_null": cs_null,
        "char_start_zero_zero": cs_zero_zero,
        "orphan_chunks": orphan,
        "length_buckets": bucket_counts,
        "offset_overlaps": offset_overlaps,
    }


def _pct(part: int, total: int) -> float:
    return round((part / total * 100), 2) if total else 0.0


def _to_markdown(r: dict[str, Any]) -> str:
    total = r["total_chunks"]
    lines = [
        f"# TD-051 chunk quality — tenant `{r['tenant_id']}`",
        "",
        "| Metric | Value | % of total |",
        "|--------|------:|----------:|",
        f"| total_chunks | {total} | 100.0% |",
        f"| section_path_empty | {r['section_path_empty']} | {_pct(r['section_path_empty'], total)}% |",
        f"| section_title_empty | {r['section_title_empty']} | {_pct(r['section_title_empty'], total)}% |",
        f"| char_start_null | {r['char_start_null']} | {_pct(r['char_start_null'], total)}% |",
        f"| char_start_zero_zero | {r['char_start_zero_zero']} | {_pct(r['char_start_zero_zero'], total)}% |",
        f"| orphan_chunks | {r['orphan_chunks']} | {_pct(r['orphan_chunks'], total)}% |",
        f"| offset_overlaps | {r['offset_overlaps']} | {_pct(r['offset_overlaps'], total)}% |",
        "",
        "## Length buckets",
        "",
        "| Bucket | Count | % of total |",
        "|--------|------:|----------:|",
    ]
    for b in r["length_buckets"]:
        c = b["count"]
        lines.append(
            f"| {b['bucket']} | {c} | {_pct(c, total)}% |"
        )
    return "\n".join(lines) + "\n"


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Return a diff dict for numeric metrics (after - before).

    Used to compare before/after baselines.
    """
    keys_simple = [
        "total_chunks",
        "section_path_empty",
        "section_title_empty",
        "char_start_null",
        "char_start_zero_zero",
        "orphan_chunks",
        "offset_overlaps",
    ]
    diff: dict[str, Any] = {"tenant_id": after.get("tenant_id")}
    for k in keys_simple:
        diff[k] = after.get(k, 0) - before.get(k, 0)
    # length buckets per-bucket diff
    diff["length_buckets"] = []
    b_buckets = {b["bucket"]: b["count"] for b in before.get("length_buckets", [])}
    for b in after.get("length_buckets", []):
        diff["length_buckets"].append(
            {
                "bucket": b["bucket"],
                "before": b_buckets.get(b["bucket"], 0),
                "after": b["count"],
                "delta": b["count"] - b_buckets.get(b["bucket"], 0),
            }
        )
    return diff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant", default="default", help="tenant_id (default: 'default')"
    )
    parser.add_argument(
        "--json", action="store_true", help="output JSON instead of Markdown"
    )
    parser.add_argument(
        "--baseline-before",
        metavar="PATH",
        help="path to a JSON file written by an earlier --baseline-after run; "
        "when present, also output a before/after diff section",
    )
    parser.add_argument(
        "--baseline-after",
        metavar="PATH",
        help="path to write this run's results as JSON (for later --baseline-before)",
    )
    args = parser.parse_args(argv)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _runner() -> dict[str, Any]:
        async with factory() as session:
            return await _collect_quality(session, args.tenant)

    try:
        result = asyncio.run(_runner())
    finally:
        asyncio.run(engine.dispose())

    if args.baseline_after:
        with open(args.baseline_after, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    if args.baseline_before:
        with open(args.baseline_before, "r", encoding="utf-8") as f:
            before = json.load(f)
        diff = _diff(before, result)
        if args.json:
            print(
                json.dumps(
                    {"current": result, "before": before, "diff": diff},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            sys.stdout.write(_to_markdown(result))
            sys.stdout.write("\n## Diff vs before\n\n")
            sys.stdout.write(_to_diff_markdown(diff))
    else:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(_to_markdown(result))
    return 0


def _to_diff_markdown(d: dict[str, Any]) -> str:
    lines = [
        "| Metric | Delta (after - before) |",
        "|--------|----------------------:|",
    ]
    for k in [
        "total_chunks",
        "section_path_empty",
        "section_title_empty",
        "char_start_null",
        "char_start_zero_zero",
        "orphan_chunks",
        "offset_overlaps",
    ]:
        lines.append(f"| {k} | {d[k]:+d} |")
    lines.append("")
    lines.append("### Length bucket delta")
    lines.append("")
    lines.append("| Bucket | Before | After | Delta |")
    lines.append("|--------|------:|------:|------:|")
    for b in d["length_buckets"]:
        lines.append(
            f"| {b['bucket']} | {b['before']} | {b['after']} | {b['delta']:+d} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
