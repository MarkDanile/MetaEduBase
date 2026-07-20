"""Skill registry CRUD API for REQ-045 (Task 2).

Endpoints (spec §4.5, first 7 rows):
- ``POST   /api/v1/skills``             — register (admin/data_admin/super_admin)
- ``GET    /api/v1/skills``             — list (any authenticated user, own tenant)
- ``GET    /api/v1/skills/{id}``        — detail incl. sop_template (any user, own tenant)
- ``PATCH  /api/v1/skills/{id}``        — update metadata / allowed_roles (admin roles)
- ``POST   /api/v1/skills/{id}/enable`` — enable this version (admin roles)
- ``POST   /api/v1/skills/{id}/disable``— disable this version (admin roles)
- ``DELETE /api/v1/skills/{id}``        — soft delete (admin roles)

``GET /{id}/executions`` and ``POST /{id}/run`` are Task 3 (SkillRunner)
and intentionally not present here.

The router is intentionally light: auth + payload parsing + typed-error
mapping (403 / 404 / 409 / 422). The response DTO contains **no secret** —
the SOP template body is declarative YAML (metadata + workflow steps +
report skeleton) and never carries credentials by design.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillNotFoundError,
    SkillRegistryPermissionError,
    SkillRegistryService,
    SkillVersionConflictError,
)
from app.contexts.skill_registry.domain.skill import Skill, SopTemplateError
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/skills", tags=["skill-registry"])

_CODE_PATTERN = r"^[a-z][a-z0-9_]*$"
_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"


class SkillCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, pattern=_CODE_PATTERN)
    version: str = Field(..., min_length=1, max_length=20, pattern=_VERSION_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)
    sop_template: str = Field(..., min_length=1)
    description: str | None = None
    source_ref: str | None = Field(default=None, max_length=500)
    allowed_roles: list[str] = Field(default_factory=list)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    source_ref: str | None = Field(default=None, max_length=500)
    allowed_roles: list[str] | None = None
    # 接受该字段只为让 service 显式拒绝（422）— 模板改动须走新版本；
    # 若不在模型里，pydantic 会静默丢弃，客户端误以为改成功了。
    sop_template: str | None = None


class SkillDTO(BaseModel):
    """Public representation — declarative SOP only, contains no secret."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    version: str
    name: str
    description: str | None
    sop_template: str
    source_ref: str | None
    allowed_roles: list[str]
    enabled: bool
    created_by: uuid.UUID | None
    created_at: str
    updated_at: str


def _to_dto(skill: Skill) -> SkillDTO:
    return SkillDTO(
        id=skill.id,
        tenant_id=skill.tenant_id,
        code=skill.code,
        version=skill.version,
        name=skill.name,
        description=skill.description,
        sop_template=skill.sop_template,
        source_ref=skill.source_ref,
        allowed_roles=skill.allowed_roles,
        enabled=skill.enabled,
        created_by=skill.created_by,
        created_at=skill.created_at.isoformat() if skill.created_at else "",
        updated_at=skill.updated_at.isoformat() if skill.updated_at else "",
    )


def _service(session: AsyncSession) -> SkillRegistryService:
    return SkillRegistryService(session)


@router.post("", response_model=SkillDTO, status_code=201)
async def create_skill(
    req: SkillCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        skill = await service.create(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            code=req.code,
            version=req.version,
            name=req.name,
            sop_template=req.sop_template,
            description=req.description,
            source_ref=req.source_ref,
            allowed_roles=req.allowed_roles,
            created_by=uuid.UUID(str(current_user["id"])),
            role=str(current_user.get("role", "employee")),
        )
        await session.commit()
    except SkillRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SkillVersionConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except IntegrityError as e:
        # uq_skills_tenant_code_version is a plain (non-partial) UNIQUE on
        # (tenant_id, code, version). The service pre-check only looks at
        # active rows, so re-registering a soft-deleted (code, version) —
        # or a check-then-insert race — reaches the DB constraint (on flush
        # inside create() or on commit) and raises IntegrityError. Map it to
        # the spec §4.5 "(code,version) 冲突 409" contract instead of an
        # unhandled 500 (same handling as REQ-044 commit 66e013bd).
        await session.rollback()
        if "uq_skills_tenant_code_version" in str(e.orig):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"skill '{req.code}' version '{req.version}' "
                    "已存在（含已删除记录）"
                ),
            ) from e
        raise
    except SopTemplateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _to_dto(skill)


@router.get("", response_model=list[SkillDTO])
async def list_skills(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    skills = await service.list_by_tenant(uuid.UUID(str(current_user["tenant_id"])))
    return [_to_dto(s) for s in skills]


@router.get("/{skill_id}", response_model=SkillDTO)
async def get_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        skill = await service.get_by_id(
            uuid.UUID(str(current_user["tenant_id"])),
            uuid.UUID(skill_id),
        )
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_dto(skill)


@router.patch("/{skill_id}", response_model=SkillDTO)
async def update_skill(
    skill_id: str,
    req: SkillUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        skill = await service.update(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            skill_id=uuid.UUID(skill_id),
            role=str(current_user.get("role", "employee")),
            **req.model_dump(exclude_unset=True),
        )
    except SkillRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await session.commit()
    return _to_dto(skill)


async def _set_enabled(
    skill_id: str,
    enabled: bool,
    session: AsyncSession,
    current_user: dict,
) -> Skill:
    service = _service(session)
    try:
        skill = await service.set_enabled(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            skill_id=uuid.UUID(skill_id),
            enabled=enabled,
            role=str(current_user.get("role", "employee")),
        )
    except SkillRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session.commit()
    return skill


@router.post("/{skill_id}/enable", response_model=SkillDTO)
async def enable_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    # spec §4.5 的可选 list_tools 探活属于执行侧能力，随 Task 3 SkillRunner
    # 一起交付；Task 2 的 enable 只做状态翻转。
    skill = await _set_enabled(skill_id, True, session, current_user)
    return _to_dto(skill)


@router.post("/{skill_id}/disable", response_model=SkillDTO)
async def disable_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    skill = await _set_enabled(skill_id, False, session, current_user)
    return _to_dto(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        await service.delete(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            skill_id=uuid.UUID(skill_id),
            role=str(current_user.get("role", "employee")),
        )
    except SkillRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session.commit()
