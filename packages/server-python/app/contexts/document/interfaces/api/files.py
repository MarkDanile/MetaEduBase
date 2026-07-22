"""Document files router — list / upload / get / delete / update / reinitialize."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.document.application.cleanup import cleanup_file_derivatives
from app.contexts.document.application.dto import FileDTO, FileUpdate
from app.contexts.document.application.tasks import parse_document
from app.contexts.document.infrastructure.file_repository import FileRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.shared.upload_safety import (
    DEFAULT_MAX_BYTES,
    UploadSafetyError,
    UploadSizeExceeded,
    UploadTypeUnsupported,
    commit_tmpfile,
    read_chunked_to_tempfile,
    safe_storage_key,
    validate_storage_path_containment,
    validate_upload_type,
)

logger = logging.getLogger(__name__)


# --- File helpers (private to this module) ---


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


router = APIRouter()


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

    # BUG-020 AC-1/AC-4: 服务端生成 storage_key（不拼用户原始路径）+ 安全显示名
    try:
        storage_key, display_name = safe_storage_key(str(tid), file.filename)
    except UploadSafetyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # BUG-020 AC-3: 类型白名单（用安全显示名提取 ext，防 ../etc/passwd 伪造 ext）
    try:
        validate_upload_type(
            "document", filename=display_name, content_type=file.content_type,
        )
    except UploadTypeUnsupported as e:
        raise HTTPException(status_code=415, detail=str(e)) from e

    upload_base = Path(settings.upload_dir)
    file_path = upload_base / storage_key
    # AC-1: containment 校验防 symlink/.. 逃逸
    try:
        validate_storage_path_containment(file_path.parent, upload_base)
    except UploadSafetyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # BUG-020 AC-2: 流式分块 + size 上限；超限 413 + 删临时文件
    tmp_dir = upload_base / str(tid) / ".tmp"
    try:
        tmp_path, file_size = await read_chunked_to_tempfile(
            file, max_bytes=DEFAULT_MAX_BYTES, tmp_dir=tmp_dir,
        )
    except UploadSizeExceeded as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    try:
        commit_tmpfile(tmp_path, file_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{e}") from e

    file_type = (
        display_name.rsplit(".", 1)[-1].lower() if "." in display_name else "unknown"
    )
    tags: list[str] = []

    repo = FileRepository(session)
    row = await repo.create(
        tenant_id=tid,
        folder_id=uuid.UUID(folder_id) if folder_id else None,
        filename=display_name,
        file_type=file_type,
        doc_type=doc_type,
        file_size=file_size,
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
    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    repo = FileRepository(session)
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Cascade delete: chunks → knowledge edges+nodes → tasks → file
    await cleanup_file_derivatives(session, fid, tid)
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
    existing = await repo.get_by_id(fid, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Guard: if file is currently processing, refuse reinitialize to avoid race condition
    if existing["status"] == "processing":
        raise HTTPException(
            status_code=409,
            detail="文件正在处理中，请等待当前任务完成后再重新初始化",
        )

    # Cascade delete: chunks → knowledge edges+nodes → tasks
    await cleanup_file_derivatives(session, fid, tid)

    # Reset file status to 'uploaded' and clear structured_data
    await session.execute(
        text(
            "UPDATE metaedu.files "
            "SET status = 'uploaded', structured_data = NULL, "
            "updated_at = :now "
            "WHERE id = :fid AND tenant_id = :tid"
        ),
        {"fid": fid, "tid": tid, "now": datetime.now(UTC).replace(tzinfo=None)},
    )

    # Capture the NEW updated_at AFTER the update — this is our pipeline version marker
    result = await session.execute(
        text("SELECT updated_at FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
        {"fid": fid, "tid": tid},
    )
    row = result.mappings().first()
    pipeline_version = row["updated_at"] if row else None
    pv_str = pipeline_version.isoformat() if pipeline_version else ""

    logger.info("reinitialize dispatch: file=%s pipeline_version=%s", fid, pv_str)

    # Trigger parse_document pipeline (pass pipeline_version for stale-task detection)
    try:
        parse_document.delay(str(fid), str(tid), pv_str)
    except Exception:
        logger.warning("Failed to dispatch parse_document task — Celery unavailable")

    row = await repo.get_by_id(fid, tid)
    return _file_row_to_dto(row)
