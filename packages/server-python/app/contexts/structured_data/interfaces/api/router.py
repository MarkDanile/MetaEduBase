"""Structured data context API router — datasets CRUD + rows."""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

# Celery tasks — imported at module level for testability
from app.celery_app import celery_app
from app.config import settings
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.application.catalog_service import CatalogService
from app.contexts.structured_data.application.cleanup import cleanup_dataset_derivatives
from app.contexts.structured_data.application.dto import (
    DatasetDTO,
    DatasetRowDTO,
    DatasetUpdate,
)
from app.contexts.structured_data.application.tasks import ds_parse
from app.contexts.structured_data.infrastructure.dataset_repository import DatasetRepository
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)

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
        entity_type=row.get("entity_type"),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/datasets", response_model=list[DatasetDTO])
async def list_datasets(
    catalog_id: str | None = None,
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
    repo = DatasetRepository(session)
    rows = await repo.list_datasets(
        tid,
        catalog_id=uuid.UUID(catalog_id) if catalog_id else None,
        tag=tag,
        status=status,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return [_dataset_row_to_dto(r) for r in rows]


@router.post("/datasets/upload", response_model=DatasetDTO, status_code=201)
async def upload_dataset(
    file: UploadFile,
    catalog_id: str = Form(...),
    entity_type: str = Form(...),
    name: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    uid = current_user["id"]

    # REQ-054 review fix V1: catalog existence check (replaces the old
    # whitelist validation). entity_type is now free-text and persisted to
    # datasets.entity_type; the catalog's discovered list is aggregated
    # from datasets rather than declared upfront.
    catalog_service = CatalogService(session)
    catalog = await catalog_service.get_by_id(uuid.UUID(catalog_id), tid)
    if not catalog:
        raise HTTPException(status_code=400, detail="数据库不存在")

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
        source_file=storage_key,
        tags=[],
        created_by=uid,
        catalog_id=uuid.UUID(catalog_id),
        entity_type=entity_type,
    )

    # New-entity warning: if this is the first dataset with this entity_type
    # in this catalog, surface a confirmation hint. count == 1 means the row
    # we just inserted is the only one.
    warning: str | None = None
    count = await repo.count_by_catalog_and_entity_type(
        tid, uuid.UUID(catalog_id), entity_type
    )
    if count == 1:
        warning = f"发现新实体类型 {entity_type}，请确认是否属于本主题"

    # Trigger dataset processing pipeline
    try:
        celery_app.send_task("ds_parse", args=[str(row["id"]), str(tid)])
    except Exception as e:
        logger.warning(f"Failed to dispatch ds_parse task — {type(e).__name__}: {e}")

    dto = _dataset_row_to_dto(row)
    dto.warning = warning
    return dto


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

    # Cascade delete: rows → chunks → knowledge edges+nodes → tasks → dataset
    await cleanup_dataset_derivatives(session, did, tid)
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
        entity_type=data.entity_type,
    )
    row = await repo.get_by_id(did, tid)
    return _dataset_row_to_dto(row)


@router.post("/datasets/{dataset_id}/reinitialize", response_model=DatasetDTO)
async def reinitialize_dataset(
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

    # Cascade delete: rows → chunks → knowledge edges+nodes → tasks
    await cleanup_dataset_derivatives(session, did, tid)

    # Reset dataset status to 'uploaded' and kg_status to 'pending'
    await repo.update(
        did, tid,
        status="uploaded", kg_status="pending",
        row_count=0, column_names=None, column_types=None,
    )

    # Trigger ds_parse pipeline
    try:
        ds_parse.delay(str(did), str(tid))
    except Exception as e:
        logger.warning(f"Failed to dispatch ds_parse task — {type(e).__name__}: {e}")

    row = await repo.get_by_id(did, tid)
    return _dataset_row_to_dto(row)
