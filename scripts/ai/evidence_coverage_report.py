#!/usr/bin/env python3
"""REQ-010 Slice 6 — evidence coverage report.

Outputs 4 metrics for the current PG database:
1. node_source_chunk: knowledge_nodes with source_chunk_id set / total
2. chunk_embedding: document_chunks with embedding set / total
3. chunk_tsvector: document_chunks with content_tsvector set / total
4. file_metadata: files with doc_type set / total

Usage:
    python scripts/ai/evidence_coverage_report.py [--json]

Output:
    Markdown table by default; JSON if --json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Ensure server-python is importable when run from repo root
import os

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


_METRICS = [
    (
        "node_source_chunk",
        "SELECT "
        "  COUNT(*) FILTER (WHERE source_chunk_id IS NOT NULL) AS resolved, "
        "  COUNT(*) AS total "
        "FROM metaedu.knowledge_nodes",
    ),
    (
        "chunk_embedding",
        "SELECT "
        "  COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS resolved, "
        "  COUNT(*) AS total "
        "FROM metaedu.document_chunks",
    ),
    (
        "chunk_tsvector",
        "SELECT "
        "  COUNT(*) FILTER (WHERE content_tsvector IS NOT NULL) AS resolved, "
        "  COUNT(*) AS total "
        "FROM metaedu.document_chunks",
    ),
    (
        "file_metadata",
        "SELECT "
        "  COUNT(*) FILTER (WHERE doc_type IS NOT NULL) AS resolved, "
        "  COUNT(*) AS total "
        "FROM metaedu.files",
    ),
]


async def _collect_coverage(session: AsyncSession) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, sql in _METRICS:
        r = await session.execute(text(sql))
        row = r.first()
        resolved = int(row[0])
        total = int(row[1])
        pct = (resolved / total * 100) if total else 100.0
        results.append(
            {
                "metric": name,
                "resolved": resolved,
                "total": total,
                "coverage_pct": round(pct, 2),
            }
        )
    return results


def _to_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# REQ-010 evidence coverage",
        "",
        "| Metric | Resolved | Total | Coverage |",
        "|--------|---------:|------:|---------:|",
    ]
    for r in results:
        lines.append(
            f"| {r['metric']} | {r['resolved']} | {r['total']} | {r['coverage_pct']}% |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON 而非 Markdown"
    )
    args = parser.parse_args(argv)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _runner() -> list[dict[str, Any]]:
        async with factory() as session:
            return await _collect_coverage(session)

    try:
        results = asyncio.run(_runner())
    finally:
        asyncio.run(engine.dispose())

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_to_markdown(results))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
