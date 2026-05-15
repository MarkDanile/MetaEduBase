"""Structured data context API router — datasets CRUD + rows."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.application.dto import (
    DatasetDTO,
    DatasetRowDTO,
    DatasetUpdate,
)
from app.contexts.structured_data.infrastructure.dataset_repository import DatasetRepository
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter()


def _dataset_row_to_dto(row: dict) -> DatasetDTO:
    return DatasetDTO(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        description=row.get("description"),
        column_names=row.get("column_names"),
        column_types=row.get("column_types"),
        row_count=row["row_count"],
        source_file=row.get("source_file"),
        tags=row.get("tags"),
        status=row["status"],
        kg_status=row["kg_status"],
        sort_order=row["sort_order"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/datasets", response_model=list[DatasetDTO])
async def list_datasets(
    tag: str | None = None,
    status: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = DatasetRepository(session)
    rows = await repo.list_datasets(tid, tag=tag, status=status, limit=limit, offset=offset)
    return [_dataset_row_to_dto(r) for r in rows]


@router.post("/datasets/upload", response_model=DatasetDTO, status_code=201)
async def upload_dataset(
    file: UploadFile,
    name: str | None = None,
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

    dataset_name = name or file.filename.rsplit(".", 1)[0]
    repo = DatasetRepository(session)
    row = await repo.create(
        tenant_id=tid,
        name=dataset_name,
        description=None,
        source_file=file.filename,
        tags=[],
        created_by=uid,
    )
    return _dataset_row_to_dto(row)


@router.get("/datasets/{dataset_id}", response_model=DatasetDTO)
async def get_dataset(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    repo = DatasetRepository(session)
    row = await repo.get_by_id(uuid.UUID(dataset_id), tid)
    if not row:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return _dataset_row_to_dto(row)


@router.get("/datasets/{dataset_id}/rows", response_model=list[DatasetRowDTO])
async def list_dataset_rows(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    did = uuid.UUID(dataset_id)
    repo = DatasetRepository(session)
    existing = await repo.get_by_id(did, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="数据集不存在")
    rows = await repo.list_rows(did, tid, limit=limit, offset=offset)
    return [
        DatasetRowDTO(
            id=r["id"],
            dataset_id=r["dataset_id"],
            row_index=r["row_index"],
            data=r["data"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    did = uuid.UUID(dataset_id)
    repo = DatasetRepository(session)
    existing = await repo.get_by_id(did, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="数据集不存在")
    await repo.delete_rows(did, tid)
    await repo.delete(did, tid)


@router.patch("/datasets/{dataset_id}", response_model=DatasetDTO)
async def update_dataset(
    dataset_id: str,
    data: DatasetUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    did = uuid.UUID(dataset_id)
    repo = DatasetRepository(session)
    existing = await repo.get_by_id(did, tid)
    if not existing:
        raise HTTPException(status_code=404, detail="数据集不存在")
    await repo.update(
        did,
        tid,
        name=data.name,
        description=data.description,
        tags=data.tags,
        sort_order=data.sort_order,
    )
    row = await repo.get_by_id(did, tid)
    return _dataset_row_to_dto(row)
