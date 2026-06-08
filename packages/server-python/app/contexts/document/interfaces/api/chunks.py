"""Document chunks router — list chunks for a file."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import ChunkDTO
from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter()


@router.get("/files/{file_id}/chunks", response_model=list[ChunkDTO])
async def list_chunks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    chunk_repo = ChunkRepository(session)
    rows = await chunk_repo.list_by_file(fid, tid)
    return [
        ChunkDTO(
            id=r["id"],
            file_id=r["file_id"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            section_title=r.get("section_title"),
            section_path=r.get("section_path"),
            char_start=r.get("char_start"),
            char_end=r.get("char_end"),
            has_embedding=r.get("has_embedding", False),
            created_at=r["created_at"],
        )
        for r in rows
    ]
