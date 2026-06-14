#!/usr/bin/env python3
"""BUG-004 one-shot cleanup: delete all orphan document_tasks rows.

Orphan = document_tasks.file_id NOT NULL AND files.id IS NULL
(in the same tenant).

BUG-004 root cause: historical session commit failures left 1178
document_tasks rows pointing to deleted files. The cascade in
cleanup_file_derivatives ran for the most-recent deletes but the
older orphans accumulated. This script is a one-shot fix that
deletes all such orphan rows.

AC-1: After running this script, the per-table orphan count from
check_orphans.py (AC-5) should be 0 for document_tasks.

This script is idempotent — re-running it after the cascade fix
removes 0 rows.

Usage:
    python scripts/ai/cleanup_orphan_tasks.py [--dry-run] [--tenant default]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

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


_DELETE_SQL = text(
    "DELETE FROM metaedu.document_tasks "
    "WHERE file_id IS NOT NULL "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM metaedu.files f "
    "  WHERE f.tenant_id = metaedu.document_tasks.tenant_id "
    "    AND f.id = metaedu.document_tasks.file_id"
    ")"
)


_COUNT_SQL = text(
    "SELECT COUNT(*) FROM metaedu.document_tasks "
    "WHERE file_id IS NOT NULL "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM metaedu.files f "
    "  WHERE f.tenant_id = metaedu.document_tasks.tenant_id "
    "    AND f.id = metaedu.document_tasks.file_id"
    ")"
)


async def cleanup_orphan_tasks(
    session: AsyncSession, *, dry_run: bool
) -> int:
    """Delete orphan document_tasks. Returns the number of rows affected.

    When dry_run=True, counts without deleting.
    """
    count_r = await session.execute(_COUNT_SQL)
    orphan_count = int(count_r.scalar() or 0)

    if dry_run:
        return 0  # don't actually delete in dry-run

    if orphan_count > 0:
        result = await session.execute(_DELETE_SQL)
        await session.commit()
        return int(result.rowcount or 0)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count orphans without deleting (default: actually delete)",
    )
    args = parser.parse_args(argv)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _runner() -> int:
        async with factory() as session:
            # Always show the count first
            count_r = await session.execute(_COUNT_SQL)
            orphan_count = int(count_r.scalar() or 0)
            print(f"[cleanup_orphan_tasks] orphan rows found: {orphan_count}")

            deleted = await cleanup_orphan_tasks(session, dry_run=args.dry_run)

            if args.dry_run:
                print(f"[cleanup_orphan_tasks] dry-run: would delete {orphan_count} rows")
            elif orphan_count > 0:
                print(f"[cleanup_orphan_tasks] deleted {deleted} orphan rows")
            else:
                print("[cleanup_orphan_tasks] no orphan rows to delete")

            return 0

    try:
        asyncio.run(_runner())
    finally:
        asyncio.run(engine.dispose())
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
