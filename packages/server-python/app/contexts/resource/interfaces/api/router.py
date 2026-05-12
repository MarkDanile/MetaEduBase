import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.contexts.identity.interfaces.api.dependencies import get_current_user

router = APIRouter()

UPLOAD_ROOT = Path(os.environ.get("METAEDU_UPLOAD_DIR", "/tmp/metaedu_uploads"))


def _ensure_upload_dir(tenant_id: uuid.UUID) -> Path:
    tenant_dir = UPLOAD_ROOT / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir


@router.get("/")
async def list_resources(
    resource_type: str | None = None,
    domain: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    conditions = ["r.tenant_id = :tid", "r.is_deleted = false"]
    params: dict = {"tid": tid, "limit": limit, "offset": offset}

    if resource_type:
        conditions.append("r.resource_type = :rtype")
        params["rtype"] = resource_type
    if domain:
        conditions.append("r.domain = :domain")
        params["domain"] = domain

    where = " AND ".join(conditions)
    count_result = await session.execute(
        text(f"SELECT count(*) FROM metaedu.resources r WHERE {where}"),
        params,
    )
    total = count_result.scalar_one()

    result = await session.execute(
        text(
            f"SELECT r.id, r.tenant_id, r.title, r.description, r.resource_type, "
            f"r.status, r.domain, r.file_size, r.file_type, r.storage_key, "
            f"r.knowledge_point_ids, r.uploaded_by, r.created_at, r.updated_at "
            f"FROM metaedu.resources r WHERE {where} "
            f"ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = [dict(row) for row in result.mappings().all()]
    for r in rows:
        if r.get("knowledge_point_ids"):
            r["knowledge_point_ids"] = [str(kp) for kp in r["knowledge_point_ids"]]
        for key in ("id", "tenant_id", "uploaded_by"):
            if key in r and r[key] is not None:
                r[key] = str(r[key])
        for key in ("created_at", "updated_at"):
            if key in r and r[key] is not None:
                r[key] = r[key].isoformat()
    return {"total": total, "items": rows}


@router.post("/upload", status_code=201)
async def upload_resource(
    file: UploadFile = File(...),
    title: str = Form(...),
    resource_type: str = Form(default="document"),
    domain: str | None = Form(default=None),
    description: str | None = Form(default=None),
    knowledge_point_ids: str = Form(default="[]"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    uid = uuid.UUID(str(current_user["id"]))
    resource_id = uuid.uuid4()

    kp_ids = json.loads(knowledge_point_ids)
    kp_uuids = [uuid.UUID(kp) for kp in kp_ids] if kp_ids else []

    content = await file.read()
    file_size = len(content)
    file_type = Path(file.filename or "unknown").suffix.lstrip(".").lower() if file.filename else "unknown"

    storage_key = f"{resource_id}.{file_type}"
    tenant_dir = _ensure_upload_dir(tid)
    file_path = tenant_dir / storage_key
    with open(file_path, "wb") as f:
        f.write(content)

    now = datetime.utcnow()
    await session.execute(
        text(
            "INSERT INTO metaedu.resources "
            "(id, tenant_id, title, description, resource_type, status, domain, "
            "knowledge_point_ids, file_size, file_type, storage_key, metadata, "
            "uploaded_by, is_deleted, created_at, updated_at) "
            "VALUES (:id, :tid, :title, :desc, :rtype, 'uploaded', :domain, "
            ":kp_ids, :fsize, :ftype, :skey, '{}', :uid, false, :now, :now)"
        ),
        {
            "id": resource_id,
            "tid": tid,
            "title": title,
            "desc": description,
            "rtype": resource_type,
            "domain": domain,
            "kp_ids": kp_uuids if kp_uuids else None,
            "fsize": file_size,
            "ftype": file_type,
            "skey": storage_key,
            "uid": uid,
            "now": now,
        },
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
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    result = await session.execute(
        text(
            "SELECT r.id, r.tenant_id, r.title, r.description, r.resource_type, "
            "r.status, r.domain, r.file_size, r.file_type, r.storage_key, "
            "r.knowledge_point_ids, r.uploaded_by, r.is_deleted, r.created_at, r.updated_at "
            "FROM metaedu.resources r WHERE r.id = :rid AND r.tenant_id = :tid"
        ),
        {"rid": uuid.UUID(resource_id), "tid": tid},
    )
    row = result.mappings().first()
    if not row or row["is_deleted"]:
        raise HTTPException(status_code=404, detail="资源不存在")
    data = dict(row)
    if data.get("knowledge_point_ids"):
        data["knowledge_point_ids"] = [str(kp) for kp in data["knowledge_point_ids"]]
    for key in ("id", "tenant_id", "uploaded_by"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])
    for key in ("created_at", "updated_at"):
        if key in data and data[key] is not None:
            data[key] = data[key].isoformat()
    return data


@router.get("/{resource_id}/download")
async def download_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    result = await session.execute(
        text("SELECT storage_key, title, file_type FROM metaedu.resources "
             "WHERE id = :rid AND tenant_id = :tid AND is_deleted = false"),
        {"rid": uuid.UUID(resource_id), "tid": tid},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在")

    file_path = UPLOAD_ROOT / str(tid) / row["storage_key"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件已被清理")

    filename = f"{row['title']}.{row['file_type']}" if row["file_type"] else row["title"]
    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")


@router.delete("/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()
    now = datetime.utcnow()
    result = await session.execute(
        text("UPDATE metaedu.resources SET is_deleted = true, updated_at = :now "
             "WHERE id = :rid AND tenant_id = :tid AND is_deleted = false"),
        {"rid": uuid.UUID(resource_id), "tid": tid, "now": now},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="资源不存在")
    await session.commit()
