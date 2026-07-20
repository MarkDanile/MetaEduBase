"""Backfill `metaedu.knowledge_nodes.embedding` for all 599 existing nodes.

TD-069 schema fix: after 030 migration changed `embedding` to `vector(4096)`,
the existing 599 nodes are NULL. This script generates siliconflow 8B
embeddings for each node's `title` (the primary semantic identifier) and
UPDATE the column.

This is a one-shot backfill. Re-running is idempotent (overwrites NULLs only
if `--force` is passed; otherwise skips nodes with existing embedding).

TD-075 fix: default (non-force) mode no longer uses OFFSET. Each batch
re-queries ``WHERE embedding IS NULL LIMIT :limit`` so successful UPDATEs
shrink the result set and the next batch picks up the next pending row
instead of skipping it (the old OFFSET approach advanced past positions
that no longer existed in the shrunk result set). The script also reports
the remaining NULL count and exits non-zero if processable rows are still
NULL after a default run, so CI/ops can detect partial completion.

Usage:
    cd packages/server-python && python -m app.scripts.backfill_knowledge_node_embeddings

Environment:
    SILICONFLOW_API_KEY must be set (or use --provider openai/etc.)
    DATABASE_URL must be set
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

# Allow `python -m app.scripts.backfill_knowledge_node_embeddings` from
# packages/server-python/ cwd.
SERVER_PYTHON_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.contexts.knowledge.application.embedding_service import get_embedding  # noqa: E402

logger = logging.getLogger(__name__)

# Type alias for the embedding function (allows test stub injection).
EmbeddingFn = Callable[[str], Awaitable[list[float] | None]]


@dataclass
class BackfillResult:
    """Stats from a backfill run.

    - ``total``: rows successfully updated (embedding written).
    - ``skipped``: rows skipped because title was empty or provider
      returned None/empty embedding (no exception).
    - ``failed``: rows that raised an exception during embedding/update.
    - ``remaining``: rows still NULL with a non-empty title after the run
      (processable rows that could be retried on re-run). Empty-title
      rows are excluded because they cannot be embedded.
    """

    total: int = 0
    skipped: int = 0
    failed: int = 0
    remaining: int = 0


async def backfill_loop(
    session,
    *,
    batch_size: int = 50,
    force: bool = False,
    embedding_fn: EmbeddingFn = get_embedding,
) -> BackfillResult:
    """Core backfill loop - reusable with any AsyncSession + embedding_fn.

    TD-075: default (``force=False``) mode re-queries
    ``WHERE embedding IS NULL LIMIT :limit`` each batch WITHOUT OFFSET.
    Successful UPDATEs shrink the result set, so the next batch picks up
    the next pending row. The old OFFSET approach skipped rows because it
    advanced past positions that no longer existed in the shrunk result
    set.

    ``force=True`` keeps OFFSET because re-processing all rows leaves the
    result set stable (no rows are filtered out by UPDATE), so OFFSET
    pagination is correct for that case.

    A per-run "attempted IDs" guard (force=False only) ensures each row is
    processed at most once per run. Failed/skipped rows remain NULL and
    would otherwise be re-queried every batch; the guard filters them out
    so stats are not double-counted and the loop terminates as soon as no
    fresh rows remain. Those rows are reported via ``remaining`` and
    retried on the next run (re-run converges once the provider/data issue
    clears).
    """
    where_clause = "" if force else "WHERE embedding IS NULL"
    count_result = await session.execute(
        text(f"SELECT COUNT(*) FROM metaedu.knowledge_nodes {where_clause}")
    )
    target_count = count_result.scalar() or 0
    logger.info("starting backfill: %d target nodes (force=%s)", target_count, force)

    result = BackfillResult()
    offset = 0
    # TD-075: track row IDs attempted this run so failed/skipped rows
    # (which remain NULL and get re-queried) are not retried within the
    # same run - each row is attempted at most once, stats are accurate,
    # and the loop terminates as soon as no fresh rows remain.
    attempted_ids: set = set()
    while True:
        if force:
            # force=True: result set stable, OFFSET pagination is correct.
            rows_result = await session.execute(
                text(
                    f"SELECT id, title FROM metaedu.knowledge_nodes "
                    f"{where_clause} ORDER BY created_at "
                    f"LIMIT :limit OFFSET :offset"
                ),
                {"limit": batch_size, "offset": offset},
            )
        else:
            # TD-075: force=False re-queries fresh each batch (no OFFSET).
            rows_result = await session.execute(
                text(
                    f"SELECT id, title FROM metaedu.knowledge_nodes "
                    f"{where_clause} ORDER BY created_at LIMIT :limit"
                ),
                {"limit": batch_size},
            )
        rows = rows_result.mappings().all()
        if not rows:
            break

        if not force:
            # Filter out rows already attempted this run (failed/skipped
            # rows remain NULL and get re-queried). If every row in the
            # batch was already attempted, no progress is possible - break
            # to avoid an infinite loop without double-counting failures.
            fresh_rows = [r for r in rows if r["id"] not in attempted_ids]
            if not fresh_rows:
                logger.warning(
                    "batch returned only already-attempted rows; stopping "
                    "to avoid infinite loop. Re-run after fixing "
                    "provider/data issues to converge."
                )
                break
            rows = fresh_rows

        for row in rows:
            node_id = row["id"]
            title = row["title"]
            if not force:
                attempted_ids.add(node_id)
            if not title:
                logger.warning("skip node %s: empty title", node_id)
                result.skipped += 1
                continue
            try:
                embedding = await embedding_fn(title)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "skip node %s: embedding call raised: %s", node_id, exc
                )
                result.failed += 1
                continue
            if not embedding:
                logger.warning(
                    "skip node %s: empty embedding for title=%r",
                    node_id,
                    title[:40],
                )
                result.skipped += 1
                continue
            emb_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
            try:
                await session.execute(
                    text(
                        "UPDATE metaedu.knowledge_nodes "
                        "SET embedding = CAST(:emb AS vector), updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"emb": emb_str, "id": node_id},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("skip node %s: UPDATE raised: %s", node_id, exc)
                result.failed += 1
                continue
            result.total += 1
        await session.commit()
        logger.info(
            "processed batch: total_backfilled=%d/%d (skipped=%d failed=%d)",
            result.total,
            target_count,
            result.skipped,
            result.failed,
        )
        if force:
            offset += batch_size

    # TD-075: report remaining processable rows (NULL embedding with a
    # non-empty title). Empty-title rows are excluded because they cannot
    # be embedded and are a data-quality issue, not a backfill failure.
    if not force:
        remaining_result = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.knowledge_nodes "
                "WHERE embedding IS NULL AND COALESCE(title, '') <> ''"
            )
        )
        result.remaining = remaining_result.scalar() or 0
    logger.info(
        "backfill loop done: total=%d skipped=%d failed=%d remaining=%d",
        result.total,
        result.skipped,
        result.failed,
        result.remaining,
    )
    return result


async def backfill(batch_size: int = 50, force: bool = False) -> BackfillResult:
    """Generate embeddings for all NULL knowledge_nodes.embedding rows."""
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await backfill_loop(
                session,
                batch_size=batch_size,
                force=force,
                embedding_fn=get_embedding,
            )
    finally:
        await engine.dispose()


async def main() -> int:
    parser = argparse.ArgumentParser(prog="backfill_knowledge_node_embeddings")
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Rows per batch (default 50)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing embeddings (default: skip non-NULL rows)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = await backfill(batch_size=args.batch_size, force=args.force)
    logger.info(
        "backfill complete: %d nodes updated (skipped=%d failed=%d remaining=%d)",
        result.total,
        result.skipped,
        result.failed,
        result.remaining,
    )
    # TD-075: non-zero exit if processable rows are still NULL after a
    # default run, so CI/ops can detect partial completion and re-run to
    # converge. force=True is an explicit re-process request, so it does
    # not fail on remaining NULLs.
    if not args.force and result.remaining > 0:
        logger.error(
            "backfill incomplete: %d nodes still have NULL embedding with a "
            "non-empty title (skipped=%d failed=%d); re-run to converge",
            result.remaining,
            result.skipped,
            result.failed,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
