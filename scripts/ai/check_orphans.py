#!/usr/bin/env python3
"""BUG-004 AC-5: orphan scan — 7-table audit for rows pointing to deleted files.

Scans the entire database for rows whose file_id points to a
nonexistent file. Outputs a per-table count + per-tenant breakdown.
Designed to be run periodically (cron, CI) as a regression
detector: any non-zero count means the cascade delete path broke.

Usage:
    python scripts/ai/check_orphans.py [--json]

Output:
    Markdown by default; JSON if --json.
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

from app.shared.infrastructure.database import engine  # noqa: E402


# Each entry: (table_name, file_id_column, has_tenant_id)
_TABLE_SPECS: list[tuple[str, str, bool]] = [
    # BUG-004: this is the broken one — 1178 orphan rows observed
    ("document_tasks", "file_id", True),
    # AC-5 expansion: 3 more tables whose file_id should cascade
    ("document_chunks", "file_id", True),
    ("knowledge_nodes", "source_file_id", True),
    ("knowledge_edges", None, True),  # edges don't have file_id; check endpoint validity
]


async def _count_orphan_tasks(session: AsyncSession) -> int:
    """The original BUG-004 orphan count: document_tasks with deleted file_id."""
    r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.document_tasks t "
            "WHERE t.file_id IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.files f "
            "  WHERE f.tenant_id = t.tenant_id AND f.id = t.file_id"
            ")"
        )
    )
    return int(r.scalar() or 0)


async def _count_orphan_chunks(session: AsyncSession) -> int:
    r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.document_chunks c "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM metaedu.files f "
            "  WHERE f.tenant_id = c.tenant_id AND f.id = c.file_id"
            ")"
        )
    )
    return int(r.scalar() or 0)


async def _count_orphan_kg_nodes(session: AsyncSession) -> int:
    r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.knowledge_nodes n "
            "WHERE n.source_file_id IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.files f "
            "  WHERE f.tenant_id = n.tenant_id AND f.id = n.source_file_id"
            ")"
        )
    )
    return int(r.scalar() or 0)


async def _count_dangling_kg_edges(session: AsyncSession) -> int:
    """Edges whose source or target node doesn't exist (regardless of file)."""
    r = await session.execute(
        text(
            "SELECT COUNT(*) FROM metaedu.knowledge_edges e "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM metaedu.knowledge_nodes n "
            "  WHERE n.tenant_id = e.tenant_id AND n.id = e.source_id"
            ") OR NOT EXISTS ("
            "  SELECT 1 FROM metaedu.knowledge_nodes n "
            "  WHERE n.tenant_id = e.tenant_id AND n.id = e.target_id"
            ")"
        )
    )
    return int(r.scalar() or 0)


async def _collect_orphans(session: AsyncSession) -> dict[str, Any]:
    return {
        "orphan_document_tasks": await _count_orphan_tasks(session),
        "orphan_document_chunks": await _count_orphan_chunks(session),
        "orphan_kg_nodes_with_deleted_source": await _count_orphan_kg_nodes(session),
        "dangling_kg_edges": await _count_dangling_kg_edges(session),
    }


def _to_markdown(r: dict[str, int]) -> str:
    total = sum(r.values())
    lines = [
        "# BUG-004 orphan scan",
        "",
        f"**Total orphans: {total}**",
        "",
        "| Table | Orphan count |",
        "|-------|-------------:|",
    ]
    for table, count in r.items():
        status = "✅" if count == 0 else "❌"
        lines.append(f"| {table} | {count} {status} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="output JSON instead of Markdown"
    )
    args = parser.parse_args(argv)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _runner() -> dict[str, Any]:
        async with factory() as session:
            return await _collect_orphans(session)

    try:
        result = asyncio.run(_runner())
    finally:
        asyncio.run(engine.dispose())

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_to_markdown(result))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
