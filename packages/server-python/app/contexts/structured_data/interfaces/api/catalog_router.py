"""Catalog CRUD API for REQ-054.

Endpoints:
- ``POST   /api/v1/catalogs``      — create (admin/data_admin/super_admin)
- ``GET    /api/v1/catalogs``      — list (any authenticated user)
- ``GET    /api/v1/catalogs/{id}`` — get one (any authenticated user)
- ``PATCH  /api/v1/catalogs/{id}`` — update (admin/data_admin/super_admin)
- ``DELETE /api/v1/catalogs/{id}`` — soft/hard delete (admin/data_admin/super_admin)

Auth + tenant isolation come from the existing ``get_current_user`` /
``get_session`` dependencies — the service layer scopes every query by
``tenant_id`` from the token, so a user can only see their own tenant's
catalogs.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.application.catalog_service import (
    CatalogCodeConflictError,
    CatalogPermissionError,
    CatalogService,
)
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/catalogs", tags=["catalogs"])


class CatalogCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=200)
    # REQ-054 review fix V1: entity_types is now optional - the catalog's
    # effective entity-type list is discovered from uploaded datasets (see
    # CatalogService.get_discovered_entity_types). The stored field is kept
    # as optional metadata; callers may pass [] or omit it entirely.
    entity_types: list[str] = Field(default_factory=list)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    default_business_purpose: str | None = None


class CatalogUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    entity_types: list[str] | None = None
    default_business_purpose: str | None = None


class CatalogDTO(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    description: str | None
    icon: str | None
    color: str | None
    entity_types: list[str]
    default_business_purpose: str | None
    is_active: bool
    created_by: uuid.UUID
    created_at: str
    updated_at: str


def _to_dto(catalog: object) -> CatalogDTO:
    return CatalogDTO(
        id=catalog.id,  # type: ignore[arg-type]
        tenant_id=catalog.tenant_id,  # type: ignore[arg-type]
        code=catalog.code,  # type: ignore[arg-type]
        name=catalog.name,  # type: ignore[arg-type]
        description=catalog.description,  # type: ignore[arg-type]
        icon=catalog.icon,  # type: ignore[arg-type]
        color=catalog.color,  # type: ignore[arg-type]
        entity_types=catalog.entity_types,  # type: ignore[arg-type]
        default_business_purpose=catalog.default_business_purpose,  # type: ignore[arg-type]
        is_active=catalog.is_active,  # type: ignore[arg-type]
        created_by=catalog.created_by,  # type: ignore[arg-type]
        created_at=catalog.created_at.isoformat() if catalog.created_at else "",  # type: ignore[union-attr]
        updated_at=catalog.updated_at.isoformat() if catalog.updated_at else "",  # type: ignore[union-attr]
    )


@router.post("", response_model=CatalogDTO, status_code=201)
async def create_catalog(
    req: CatalogCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        catalog = await service.create(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            code=req.code,
            name=req.name,
            entity_types=req.entity_types,
            description=req.description,
            icon=req.icon,
            color=req.color,
            default_business_purpose=req.default_business_purpose,
            created_by=uuid.UUID(str(current_user["id"])),
            role=str(current_user.get("role", "employee")),
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except CatalogCodeConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await session.commit()
    return _to_dto(catalog)


@router.get("", response_model=list[CatalogDTO])
async def list_catalogs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    catalogs = await service.list_by_tenant(
        uuid.UUID(str(current_user["tenant_id"]))
    )
    return [_to_dto(c) for c in catalogs]


@router.get("/{catalog_id}", response_model=CatalogDTO)
async def get_catalog(
    catalog_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    catalog = await service.get_by_id(
        uuid.UUID(catalog_id),
        uuid.UUID(str(current_user["tenant_id"])),
    )
    if not catalog:
        raise HTTPException(status_code=404, detail="数据库不存在")
    return _to_dto(catalog)


@router.patch("/{catalog_id}", response_model=CatalogDTO)
async def update_catalog(
    catalog_id: str,
    req: CatalogUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        catalog = await service.update(
            catalog_id=uuid.UUID(catalog_id),
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            role=str(current_user.get("role", "employee")),
            **req.model_dump(exclude_unset=True),
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not catalog:
        raise HTTPException(status_code=404, detail="数据库不存在")
    await session.commit()
    return _to_dto(catalog)


@router.delete("/{catalog_id}", status_code=204)
async def delete_catalog(
    catalog_id: str,
    hard: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        ok = await service.delete(
            catalog_id=uuid.UUID(catalog_id),
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            role=str(current_user.get("role", "employee")),
            hard=hard,
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="数据库不存在")
    await session.commit()
