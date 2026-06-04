"""Dataset cleanup — shared cascade delete logic for dataset deletion and re-initialization."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.document.infrastructure.task_repository import DocumentTaskRepository
from app.contexts.knowledge.infrastructure.knowledge_repository import KnowledgeNodeRepository
from app.contexts.structured_data.infrastructure.dataset_repository import DatasetRepository


async def cleanup_dataset_derivatives(
    session: AsyncSession,
    dataset_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """Delete all derived data for a dataset: rows, chunks, knowledge edges+nodes, tasks.

    Deletion order respects FK constraints:
    rows → chunks → knowledge edges → knowledge nodes → tasks.
    Both dataset deletion and re-initialization must use this function
    to avoid duplicated cascade SQL.
    """
    repo = DatasetRepository(session)
    await repo.delete_rows(dataset_id, tenant_id)
    # ds_embed stores chunks with file_id = dataset_id
    await ChunkRepository(session).delete_by_file(dataset_id, tenant_id)
    await KnowledgeNodeRepository(session).delete_cascade_by_source_dataset(tenant_id, dataset_id)
    await DocumentTaskRepository(session).delete_by_dataset(dataset_id, tenant_id)
