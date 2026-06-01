"""Document context API router — folders, files, chunks."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
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
    TaskDTO,
)

# Celery tasks — imported at module level for testability
from app.contexts.document.application.tasks import parse_document
from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.document.infrastructure.file_repository import FileRepository
from app.contexts.document.infrastructure.folder_repository import FolderRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)

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
        uploaded_by_name=row.get("username"),
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
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
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
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return [_file_row_to_dto(r) for r in rows]


@router.post("/files/upload", response_model=FileDTO, status_code=201)
async def upload_file(
    file: UploadFile,
    folder_id: str | None = Form(None),
    doc_type: str | None = Form(None),
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

    # Trigger document processing pipeline
    try:
        parse_document.delay(str(row["id"]), str(tid))
    except Exception:
        logger.warning("Failed to dispatch parse_document task — Celery/RabbitMQ unavailable")

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
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    repo = FileRepository(session)
    chunk_repo = ChunkRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Cascade delete related data
    # 1. Delete document chunks
    await chunk_repo.delete_by_file(fid, tid)

    # 2. Delete knowledge nodes linked to this file
    await session.execute(
        text("DELETE FROM metaedu.knowledge_nodes WHERE tenant_id = :tid AND source_file_id = :fid"),
        {"tid": tid, "fid": fid},
    )

    # 3. Delete document tasks linked to this file
    await session.execute(
        text("DELETE FROM metaedu.document_tasks WHERE tenant_id = :tid AND file_id = :fid"),
        {"tid": tid, "fid": fid},
    )

    # 4. Delete the file record
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


@router.post("/files/{file_id}/reinitialize", response_model=FileDTO)
async def reinitialize_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    repo = FileRepository(session)
    chunk_repo = ChunkRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Guard: if file is currently processing, refuse reinitialize to avoid race condition
    if existing["status"] == "processing":
        raise HTTPException(
            status_code=409,
            detail="文件正在处理中，请等待当前任务完成后再重新初始化",
        )

    # 1. Delete document chunks
    await chunk_repo.delete_by_file(fid, tid)

    # 2. Delete knowledge edges linked to nodes of this file
    await session.execute(
        text(
            "DELETE FROM metaedu.knowledge_edges WHERE source_id IN "
            "(SELECT id FROM metaedu.knowledge_nodes WHERE tenant_id = :tid AND source_file_id = :fid) "
            "OR target_id IN "
            "(SELECT id FROM metaedu.knowledge_nodes WHERE tenant_id = :tid AND source_file_id = :fid)"
        ),
        {"tid": tid, "fid": fid},
    )

    # 3. Delete knowledge nodes linked to this file
    await session.execute(
        text("DELETE FROM metaedu.knowledge_nodes WHERE tenant_id = :tid AND source_file_id = :fid"),
        {"tid": tid, "fid": fid},
    )

    # 4. Delete document tasks linked to this file
    await session.execute(
        text("DELETE FROM metaedu.document_tasks WHERE tenant_id = :tid AND file_id = :fid"),
        {"tid": tid, "fid": fid},
    )

    # 5. Reset file status to 'uploaded' and clear structured_data (repo.update auto-updates updated_at)
    await session.execute(
        text(
            "UPDATE metaedu.files SET status = 'uploaded', structured_data = NULL, updated_at = :now "
            "WHERE id = :fid AND tenant_id = :tid"
        ),
        {"fid": fid, "tid": tid, "now": datetime.now(UTC).replace(tzinfo=None)},
    )

    # 6. Capture the NEW updated_at AFTER the update — this is our pipeline version marker
    result = await session.execute(
        text("SELECT updated_at FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
        {"fid": fid, "tid": tid},
    )
    row = result.mappings().first()
    pipeline_version = row["updated_at"] if row else None
    pv_str = pipeline_version.isoformat() if pipeline_version else ""

    logger.info("reinitialize dispatch: file=%s pipeline_version=%s", fid, pv_str)

    # 7. Trigger parse_document pipeline (pass pipeline_version for stale-task detection)
    try:
        parse_document.delay(str(fid), str(tid), pv_str)
    except Exception:
        logger.warning("Failed to dispatch parse_document task — Celery unavailable")

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


# --- Tasks ---


_TASK_TYPE_LABELS: dict[str, str] = {
    "parse": "文档解析",
    "chunk": "结构切片",
    "embed": "向量化",
    "index_tsv": "全文索引",
    "extract_template": "模板抽取",
    "extract_kg": "知识图谱",
}


@router.get("/files/{file_id}/tasks", response_model=list[TaskDTO])
async def list_file_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)

    result = await session.execute(
        text(
            "SELECT id, file_id, dataset_id, task_type, status, progress, "
            "error_message, started_at, completed_at, created_at "
            "FROM metaedu.document_tasks "
            "WHERE tenant_id = :tid AND file_id = :fid "
            "ORDER BY created_at ASC"
        ),
        {"tid": tid, "fid": fid},
    )
    rows = result.mappings().all()
    return [
        TaskDTO(
            id=r["id"],
            file_id=r["file_id"],
            dataset_id=r["dataset_id"],
            task_type=r["task_type"],
            status=r["status"],
            progress=r["progress"],
            error_message=r["error_message"],
            label=_TASK_TYPE_LABELS.get(r["task_type"], r["task_type"]),
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("/files/{file_id}/retry", response_model=list[TaskDTO])
async def retry_file_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)

    # Reset failed/pending tasks to pending
    await session.execute(
        text(
            "UPDATE metaedu.document_tasks "
            "SET status = 'pending', progress = 0, error_message = NULL "
            "WHERE tenant_id = :tid AND file_id = :fid AND status IN ('failed', 'pending')"
        ),
        {"tid": tid, "fid": fid},
    )
    await session.commit()

    # Re-dispatch the first pending task (parse_document chains to the rest)
    await parse_document.delay(file_id, str(tid))

    # Return updated tasks
    result = await session.execute(
        text(
            "SELECT id, file_id, dataset_id, task_type, status, progress, "
            "error_message, started_at, completed_at, created_at "
            "FROM metaedu.document_tasks "
            "WHERE tenant_id = :tid AND file_id = :fid "
            "ORDER BY created_at ASC"
        ),
        {"tid": tid, "fid": fid},
    )
    rows = result.mappings().all()
    return [
        TaskDTO(
            id=r["id"],
            file_id=r["file_id"],
            dataset_id=r["dataset_id"],
            task_type=r["task_type"],
            status=r["status"],
            progress=r["progress"],
            error_message=r["error_message"],
            label=_TASK_TYPE_LABELS.get(r["task_type"], r["task_type"]),
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
