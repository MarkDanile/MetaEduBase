"""Document folders router — list / create / update / delete / move."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import FolderCreate, FolderDTO, FolderMove, FolderUpdate
from app.contexts.document.infrastructure.folder_repository import FolderRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

# --- Folder helpers (private to this module) ---


def _folder_row_to_dto(row: dict) -> FolderDTO:
    return FolderDTO(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        parent_id=row.get("parent_id"),
        path=row["path"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _build_tree(flat: list[dict]) -> list[FolderDTO]:
    by_id: dict[uuid.UUID, FolderDTO] = {}
    for row in flat:
        by_id[row["id"]] = _folder_row_to_dto(row)
    roots: list[FolderDTO] = []
    for row in flat:
        node = by_id[row["id"]]
        if row.get("parent_id") and row["parent_id"] in by_id:
            parent = by_id[row["parent_id"]]
            if parent.children is None:
                parent.children = []
            parent.children.append(node)
        else:
            roots.append(node)
    return roots


router = APIRouter()


@router.get("/folders", response_model=list[FolderDTO])
async def list_folders(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = FolderRepository(session)
    flat = await repo.list_tree(tid)
    return _build_tree(flat)


@router.post("/folders", response_model=FolderDTO, status_code=201)
async def create_folder(
    data: FolderCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = FolderRepository(session)
    row = await repo.create(tid, data.name, data.parent_id, data.sort_order)
    return _folder_row_to_dto(row)


@router.patch("/folders/{folder_id}", response_model=FolderDTO)
async def update_folder(
    folder_id: str,
    data: FolderUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(folder_id)
    repo = FolderRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    await repo.update(fid, tid, name=data.name, sort_order=data.sort_order)
    row = await repo.get_by_id(fid, tid)
    return _folder_row_to_dto(row)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(folder_id)
    repo = FolderRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    file_count = await repo.count_files(fid, tid)
    if file_count > 0:
        raise HTTPException(status_code=409, detail="文件夹内还有文件，请先移动或删除文件")
    await repo.delete(fid, tid)


@router.patch("/folders/{folder_id}/move", response_model=FolderDTO)
async def move_folder(
    folder_id: str,
    data: FolderMove,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(folder_id)
    repo = FolderRepository(session)
    await repo.move(fid, tid, data.parent_id)
    row = await repo.get_by_id(fid, tid)
    return _folder_row_to_dto(row)
