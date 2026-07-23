"""Resource API routes used by the TD-083 targeted CI probe."""

import json
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.resource.infrastructure.resource_repository import ResourceRepository
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

router = APIRouter()

UPLOAD_ROOT = Path(os.environ.get("METAEDU_UPLOAD_DIR", "/tmp/metaedu_uploads"))


def _ensure_upload_dir(tenant_id: uuid.UUID) -> Path:
    tenant_dir = UPLOAD_ROOT / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir


def _format_resource_row(r: dict) -> dict:
    if r.get("knowledge_point_ids"):
        r["knowledge_point_ids"] = [str(kp) for kp in r["knowledge_point_ids"]]
    for key in ("id", "tenant_id", "uploaded_by"):
        if key in r and r[key] is not None:
            r[key] = str(r[key])
    for key in ("created_at", "updated_at"):
        if key in r and r[key] is not None:
            r[key] = r[key].isoformat()
    return r


@router.get("/")
async def list_resources(
    resource_type: str | None = None,
    domain: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = ResourceRepository(session)
    total = await repo.count(tid, resource_type=resource_type, domain=domain)
    rows = await repo.list_resources(
        tid,
        resource_type=resource_type,
        domain=domain,
        limit=limit,
        offset=offset,
    )
    items = [_format_resource_row(dict(r)) for r in rows]
    return {"total": total, "items": items}


@router.post("/upload", status_code=201)
async def upload_resource(
    file: Annotated[UploadFile, File(...)],
    title: str = Form(...),
    resource_type: str = Form(default="document"),
    domain: str | None = Form(default=None),
    description: str | None = Form(default=None),
    knowledge_point_ids: str = Form(default="[]"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    uid = uuid.UUID(str(current_user["id"]))
    resource_id = uuid.uuid4()

    kp_ids = json.loads(knowledge_point_ids)
    kp_uuids = [uuid.UUID(kp) for kp in kp_ids] if kp_ids else []

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # BUG-020 AC-1/AC-4: 安全显示名 + 服务端 storage_key（resource_id.ext）
    try:
        _, display_name = safe_storage_key(str(tid), file.filename)
    except UploadSafetyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    file_type = (
        display_name.rsplit(".", 1)[-1].lower() if "." in display_name else "unknown"
    )
    # BUG-020 AC-3: 类型白名单（用安全显示名提取 ext）
    try:
        validate_upload_type(
            "resource", filename=display_name, content_type=file.content_type,
        )
    except UploadTypeUnsupported as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    storage_key = (
        f"{resource_id}.{file_type}" if file_type != "unknown" else str(resource_id)
    )
    tenant_dir = _ensure_upload_dir(tid)
    file_path = tenant_dir / storage_key
    # AC-1: containment 校验
    try:
        validate_storage_path_containment(file_path, tenant_dir)
    except UploadSafetyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # BUG-020 AC-2: 流式分块 + size 上限
    tmp_dir = tenant_dir / ".tmp"
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

    repo = ResourceRepository(session)
    await repo.create(
        resource_id=resource_id,
        tenant_id=tid,
        title=title,
        description=description,
        resource_type=resource_type,
        domain=domain,
        knowledge_point_ids=kp_uuids if kp_uuids else None,
        file_size=file_size,
        file_type=file_type,
        storage_key=storage_key,
        uploaded_by=uid,
    )
    await session.commit()

    return {
        "id": str(resource_id),
        "title": title,
        "resource_type": resource_type,
        "file_size": file_size,
        "file_type": file_type,
        "storage_key": storage_key,
    }


@router.get("/{resource_id}")
async def get_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = ResourceRepository(session)
    row = await repo.get_by_id_and_tenant(uuid.UUID(resource_id), tid)
    if not row or row["is_deleted"]:
        raise HTTPException(status_code=404, detail="资源不存在")
    return _format_resource_row(row)


@router.get("/{resource_id}/download")
async def download_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = ResourceRepository(session)
    info = await repo.get_storage_info(uuid.UUID(resource_id), tid)
    if not info:
        raise HTTPException(status_code=404, detail="资源不存在")

    file_path = UPLOAD_ROOT / str(tid) / info["storage_key"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件已被清理")

    filename = (
        f"{info['title']}.{info['file_type']}" if info["file_type"] else info["title"]
    )
    return FileResponse(
        path=str(file_path), filename=filename, media_type="application/octet-stream"
    )


@router.delete("/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = ResourceRepository(session)
    rowcount = await repo.soft_delete(uuid.UUID(resource_id), tid)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="资源不存在")
    await session.commit()
