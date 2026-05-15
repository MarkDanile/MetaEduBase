"""Document context API router — folders, files, chunks."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.document.application.dto import (
    ChunkDTO,
    FileDTO,
    FileUpdate,
    FolderCreate,
    FolderDTO,
    FolderMove,
    FolderUpdate,
)
from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.document.infrastructure.file_repository import FileRepository
from app.contexts.document.infrastructure.folder_repository import FolderRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter()


# --- Folder helpers ---

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


# --- Folders ---

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


# --- File helpers ---

def _file_row_to_dto(row: dict) -> FileDTO:
    return FileDTO(
        id=row["id"],
        tenant_id=row["tenant_id"],
        folder_id=row.get("folder_id"),
        filename=row["filename"],
        file_type=row["file_type"],
        doc_type=row.get("doc_type"),
        file_size=row.get("file_size"),
        tags=row.get("tags"),
        status=row["status"],
        structured_data=row.get("structured_data"),
        uploaded_by=row["uploaded_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# --- Files ---

@router.get("/files", response_model=list[FileDTO])
async def list_files(
    folder_id: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = FileRepository(session)
    rows = await repo.list_files(
        tid,
        folder_id=uuid.UUID(folder_id) if folder_id else None,
        tag=tag,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_file_row_to_dto(r) for r in rows]


@router.post("/files/upload", response_model=FileDTO, status_code=201)
async def upload_file(
    file: UploadFile,
    folder_id: str | None = None,
    doc_type: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    uid = current_user["id"]

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    upload_dir = os.path.join(settings.upload_dir, str(tid))
    os.makedirs(upload_dir, exist_ok=True)

    storage_key = f"{tid}/{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(settings.upload_dir, storage_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_type = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "unknown"
    tags: list[str] = []

    repo = FileRepository(session)
    row = await repo.create(
        tenant_id=tid,
        folder_id=uuid.UUID(folder_id) if folder_id else None,
        filename=file.filename,
        file_type=file_type,
        doc_type=doc_type,
        file_size=len(content),
        storage_key=storage_key,
        tags=tags,
        uploaded_by=uid,
    )
    return _file_row_to_dto(row)


@router.get("/files/{file_id}", response_model=FileDTO)
async def get_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = FileRepository(session)
    row = await repo.get_by_id(uuid.UUID(file_id), tid)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    return _file_row_to_dto(row)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    repo = FileRepository(session)
    chunk_repo = ChunkRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")
    await chunk_repo.delete_by_file(fid, tid)
    await repo.delete(fid, tid)


@router.patch("/files/{file_id}", response_model=FileDTO)
async def update_file(
    file_id: str,
    data: FileUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    repo = FileRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")
    await repo.update(fid, tid, tags=data.tags, doc_type=data.doc_type, folder_id=data.folder_id)
    row = await repo.get_by_id(fid, tid)
    return _file_row_to_dto(row)


# --- Chunks ---

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
