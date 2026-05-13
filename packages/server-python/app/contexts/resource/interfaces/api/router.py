import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.resource.infrastructure.resource_repository import ResourceRepository
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

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
    file: UploadFile = File(...),
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

    content = await file.read()
    file_size = len(content)
    file_type = (
        Path(file.filename or "unknown").suffix.lstrip(".").lower()
        if file.filename
        else "unknown"
    )

    storage_key = f"{resource_id}.{file_type}"
    tenant_dir = _ensure_upload_dir(tid)
    file_path = tenant_dir / storage_key
    with open(file_path, "wb") as f:
        f.write(content)

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
