"""File cleanup — shared cascade delete logic for file deletion and re-initialization."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.document.infrastructure.task_repository import DocumentTaskRepository
from app.contexts.knowledge.infrastructure.knowledge_repository import KnowledgeNodeRepository


async def cleanup_file_derivatives(
    session: AsyncSession,
    file_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """Delete all derived data for a file: chunks, knowledge edges+nodes, tasks.

    Deletion order respects FK constraints: chunks → knowledge edges → knowledge nodes → tasks.
    Both file deletion and re-initialization must use this function to avoid duplicated cascade SQL.
    """
    await ChunkRepository(session).delete_by_file(file_id, tenant_id)
    await KnowledgeNodeRepository(session).delete_cascade_by_source_file(tenant_id, file_id)
    await DocumentTaskRepository(session).delete_by_file(file_id, tenant_id)
