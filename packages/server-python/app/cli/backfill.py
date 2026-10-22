"""`backfill` 管理命令 CLI 入口 — REQ-010 Slice 6.

3 个 backfill 子命令 + 1 个 dry-run 模式：
- backfill node-source-chunk   — knowledge_nodes.source_chunk_id
- backfill chunk-embedding     — document_chunks.embedding / content_tsvector
- backfill file-metadata       — files.doc_type

用法：
    python -m app.cli.backfill <subcommand> [--tenant <uuid>] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.agent_identity_bootstrap import (
    actor_exists,
    backfill_agent_identity,
    list_all_tenant_ids,
)
from app.contexts.document.application.backfill_chunk_embedding import (
    backfill_chunk_embedding,
)
from app.contexts.document.application.backfill_file_metadata import (
    backfill_file_metadata,
)
from app.contexts.knowledge.application.backfill_node_source import (
    backfill_knowledge_node_source,
    list_distinct_tenants,
)
from app.contexts.knowledge.application.embedding_service import get_embedding
from app.shared.infrastructure.database import engine

logger = logging.getLogger(__name__)


async def _run_node_source(
    session: AsyncSession, tenant: str | None, dry_run: bool
) -> dict[str, Any]:
    tenants = [uuid.UUID(tenant)] if tenant else await list_distinct_tenants(session)
    results: list[dict[str, Any]] = []
    for tid in tenants:
        stats = await backfill_knowledge_node_source(session, tid, dry_run=dry_run)
        results.append({"tenant": str(tid), **stats.as_dict()})
    return {"subcommand": "node-source-chunk", "tenants": results, "dry_run": dry_run}


async def _run_chunk_embedding(
    session: AsyncSession, tenant: str | None, dry_run: bool
) -> dict[str, Any]:
    tenants = [uuid.UUID(tenant)] if tenant else await list_distinct_tenants(session)
    results: list[dict[str, Any]] = []
    for tid in tenants:
        stats = await backfill_chunk_embedding(session, tid, get_embedding, dry_run=dry_run)
        results.append({"tenant": str(tid), **stats.as_dict()})
    return {"subcommand": "chunk-embedding", "tenants": results, "dry_run": dry_run}


async def _run_file_metadata(
    session: AsyncSession, tenant: str | None, dry_run: bool
) -> dict[str, Any]:
    tenants = [uuid.UUID(tenant)] if tenant else await list_distinct_tenants(session)
    results: list[dict[str, Any]] = []
    for tid in tenants:
        stats = await backfill_file_metadata(session, tid, dry_run=dry_run)
        results.append({"tenant": str(tid), **stats.as_dict()})
    return {"subcommand": "file-metadata", "tenants": results, "dry_run": dry_run}


async def _run_agent_identity(
    session_factory,
    tenant: str | None,
    dry_run: bool,
    actor: str | None,
) -> tuple[dict[str, Any], int]:
    """TD-114 契约 §7/§8：存量补齐 agent identity。

    ``--actor`` 必填且必须存在于 metaedu.users（不存在即报错不执行）。
    返回 (report_dict, exit_code)：任何 failed/conflict 非零 -> exit 1。
    """
    if not actor:
        raise SystemExit("agent-identity 需要 --actor <uuid>（执行运维的真实 user id）")
    try:
        actor_id = uuid.UUID(actor)
    except ValueError:
        raise SystemExit(f"--actor 非法 UUID: {actor}") from None
    async with session_factory() as session:
        if not await actor_exists(session, actor_id):
            raise SystemExit(f"--actor {actor_id} 不存在于 metaedu.users，未执行")
        if tenant:
            tenant_ids = [uuid.UUID(tenant)]
        else:
            tenant_ids = await list_all_tenant_ids(session)
    report = await backfill_agent_identity(
        session_factory,
        tenant_ids=tenant_ids,
        actor_id=actor_id,
        dry_run=dry_run,
    )
    payload = {
        "subcommand": "agent-identity",
        "dry_run": report.dry_run,
        "failed": report.failed,
        "failure_samples": [
            {
                "tenant": str(s.tenant_id),
                "classification": s.classification,
                "error_type": s.error_type,
                "message": s.message,
            }
            for s in report.failure_samples
        ],
        "tenants": [
            {
                "tenant": str(t.tenant_id),
                "classification": t.classification,
                "created": t.created,
                "skipped": t.skipped,
                "would_create": t.would_create,
                "error": t.error,
            }
            for t in report.tenants
        ],
    }
    return payload, report.exit_code


_SUBCOMMANDS = {
    "node-source-chunk": _run_node_source,
    "chunk-embedding": _run_chunk_embedding,
    "file-metadata": _run_file_metadata,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.backfill",
        description="REQ-010 Slice 6 — 历史数据 backfill",
    )
    parser.add_argument(
        "subcommand",
        choices=sorted([*_SUBCOMMANDS.keys(), "agent-identity"]),
        help="要回填的数据维度",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="只回填指定 tenant_id (UUID)；不传则全量",
    )
    parser.add_argument(
        "--actor",
        default=None,
        help="agent-identity 必填：执行运维的真实 user id（必须存在于 metaedu.users）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只计算统计，不写 DB",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if args.subcommand == "agent-identity":
        payload, exit_code = asyncio.run(
            _run_agent_identity(factory, args.tenant, args.dry_run, args.actor)
        )
        asyncio.run(engine.dispose())
        import json as json_mod

        print(json_mod.dumps(payload, ensure_ascii=False, indent=2))
        return exit_code

    handler = _SUBCOMMANDS[args.subcommand]

    async def _runner() -> dict[str, Any]:
        async with factory() as session:
            return await handler(session, args.tenant, args.dry_run)

    try:
        result = asyncio.run(_runner())
    finally:
        asyncio.run(engine.dispose())

    import json as json_mod

    print(json_mod.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
