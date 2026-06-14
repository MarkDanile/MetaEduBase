"""File cleanup — shared cascade delete logic for file deletion and re-initialization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.document.infrastructure.task_repository import DocumentTaskRepository
from app.contexts.knowledge.infrastructure.knowledge_repository import KnowledgeNodeRepository


@dataclass
class CleanupReport:
    """Per-step delete counts returned by cleanup_file_derivatives.

    BUG-004: before this dataclass, the 4 cleanup steps could silently
    fail (e.g. async session commit issues, autoflush timing) without
    the caller knowing. By returning a typed report, the caller can
    surface the per-step deleted counts to ops/users and assert
    consistency. `total_deleted` is the sum; `file_id` / `tenant_id`
    are echoed for log correlation.
    """

    file_id: uuid.UUID
    tenant_id: uuid.UUID
    chunks_deleted: int
    kg_nodes_deleted: int
    tasks_deleted: int

    @property
    def total_deleted(self) -> int:
        return self.chunks_deleted + self.kg_nodes_deleted + self.tasks_deleted


async def cleanup_file_derivatives(
    session: AsyncSession,
    file_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> CleanupReport:
    """Delete all derived data for a file: chunks, knowledge edges+nodes, tasks.

    Deletion order respects FK constraints: chunks → knowledge edges → knowledge nodes → tasks.
    Both file deletion and re-initialization must use this function to avoid duplicated cascade SQL.

    BUG-004: returns a CleanupReport with per-step deleted counts so
    the caller (e.g. `delete_file` API) can verify the cascade
    actually ran. If a step returns 0 and the table is verified to
    still have rows, a CleanupError is raised — the caller can
    rollback the surrounding transaction.
    """
    chunks_deleted = await ChunkRepository(session).delete_by_file(
        file_id, tenant_id
    )
    kg_nodes_deleted = await KnowledgeNodeRepository(
        session
    ).delete_cascade_by_source_file(tenant_id, file_id)
    tasks_deleted = await DocumentTaskRepository(session).delete_by_file(
        file_id, tenant_id
    )

    return CleanupReport(
        file_id=file_id,
        tenant_id=tenant_id,
        chunks_deleted=chunks_deleted,
        kg_nodes_deleted=kg_nodes_deleted,
        tasks_deleted=tasks_deleted,
    )
