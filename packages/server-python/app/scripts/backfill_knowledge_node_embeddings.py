"""Backfill `metaedu.knowledge_nodes.embedding` for all 599 existing nodes.

TD-069 schema fix: after 030 migration changed `embedding` to `vector(4096)`,
the existing 599 nodes are NULL. This script generates siliconflow 8B
embeddings for each node's `title` (the primary semantic identifier) and
UPDATE the column.

This is a one-shot backfill. Re-running is idempotent (overwrites NULLs only
if `--force` is passed; otherwise skips nodes with existing embedding).

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
from pathlib import Path

# Allow `python -m app.scripts.backfill_knowledge_node_embeddings` from
# packages/server-python/ cwd.
SERVER_PYTHON_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402

from app.contexts.knowledge.application.embedding_service import get_embedding  # noqa: E402
from app.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


async def backfill(batch_size: int = 50, force: bool = False) -> int:
    """Generate embeddings for all NULL knowledge_nodes.embedding rows.

    Returns the number of nodes successfully backfilled.
    """
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    total = 0
    try:
        async with session_factory() as session:
            where_clause = "" if force else "WHERE embedding IS NULL"
            count_result = await session.execute(
                text(f"SELECT COUNT(*) FROM metaedu.knowledge_nodes {where_clause}")
            )
            target_count = count_result.scalar() or 0
            logger.info(
                "starting backfill: %d target nodes (force=%s)", target_count, force
            )

            offset = 0
            while True:
                rows_result = await session.execute(
                    text(
                        f"SELECT id, title FROM metaedu.knowledge_nodes "
                        f"{where_clause} ORDER BY created_at LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": batch_size, "offset": offset},
                )
                rows = rows_result.mappings().all()
                if not rows:
                    break
                for row in rows:
                    node_id = row["id"]
                    title = row["title"]
                    if not title:
                        logger.warning("skip node %s: empty title", node_id)
                        continue
                    embedding = await get_embedding(title)
                    if not embedding:
                        logger.warning("skip node %s: empty embedding for title=%r", node_id, title[:40])
                        continue
                    emb_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
                    await session.execute(
                        text(
                            "UPDATE metaedu.knowledge_nodes "
                            "SET embedding = CAST(:emb AS vector), updated_at = NOW() "
                            "WHERE id = :id"
                        ),
                        {"emb": emb_str, "id": node_id},
                    )
                    total += 1
                await session.commit()
                logger.info(
                    "processed batch: offset=%d, total_backfilled=%d/%d",
                    offset + len(rows), total, target_count,
                )
                offset += batch_size
    finally:
        await engine.dispose()
    return total


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
    total = await backfill(batch_size=args.batch_size, force=args.force)
    logger.info("backfill complete: %d nodes updated", total)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
