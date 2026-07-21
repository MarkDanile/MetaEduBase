"""Skill registry CRUD API for REQ-045 (Task 2).

Endpoints (spec §4.5):
- ``POST   /api/v1/skills``             — register (admin/data_admin/super_admin)
- ``GET    /api/v1/skills``             — list (any authenticated user, own tenant)
- ``GET    /api/v1/skills/{id}``        — detail incl. sop_template (any user, own tenant)
- ``PATCH  /api/v1/skills/{id}``        — update metadata / allowed_roles (admin roles)
- ``POST   /api/v1/skills/{id}/enable`` — enable this version (admin roles)
- ``POST   /api/v1/skills/{id}/disable``— disable this version (admin roles)
- ``DELETE /api/v1/skills/{id}``        — soft delete (admin roles)
- ``GET    /api/v1/skills/{id}/executions`` — execution audit query (admin roles, paginated)
- ``POST   /api/v1/skills/{id}/run``    — trial run via SkillRunner (admin roles)

The router is intentionally light: auth + payload parsing + typed-error
mapping (403 / 404 / 409 / 422 / 500). The response DTO contains **no
secret** — the SOP template body is declarative YAML (metadata + workflow
steps + report skeleton) and never carries credentials by design. The
``/run`` response carries the synthesized report to the privileged caller
only; it is never written to audit or logs.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.skill_registry.application.dd_query_runner import (
    build_dd_internal_query_runner,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SKILL_REGISTRY_ADMIN_ROLES,
    SkillNotFoundError,
    SkillRegistryPermissionError,
    SkillRegistryService,
    SkillVersionConflictError,
)
from app.contexts.skill_registry.application.skill_runner import (
    SkillExecutionError,
    SkillExecutionNotFoundError,
    SkillRunner,
)
from app.contexts.skill_registry.domain.skill import Skill, SopTemplateError
from app.contexts.skill_registry.infrastructure.skill_execution_audit_repository import (
    SkillExecutionAuditRepository,
)
from app.contexts.skill_registry.infrastructure.skill_models import (
    SkillExecutionAuditModel,
)
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


# ---------------------------------------------------------------------------
# Task 3: execution audit query + trial run (spec §4.5 last two rows)
# ---------------------------------------------------------------------------


class ExecutionDTO(BaseModel):
    """Audit row DTO — digests only, never raw subject / facts / report."""

    id: uuid.UUID
    skill_id: uuid.UUID
    skill_code: str
    skill_version: str
    caller_type: str
    caller_user_id: uuid.UUID | None
    subject_digest: str | None
    steps_digest: str | None
    report_digest: str | None
    ok: bool
    error_code: str | None
    error_message: str | None
    duration_ms: int
    created_at: str


class ExecutionListResponse(BaseModel):
    items: list[ExecutionDTO]
    total: int
    limit: int
    offset: int


def _to_execution_dto(row: SkillExecutionAuditModel) -> ExecutionDTO:
    return ExecutionDTO(
        id=row.id,
        skill_id=row.skill_id,
        skill_code=row.skill_code,
        skill_version=row.skill_version,
        caller_type=row.caller_type,
        caller_user_id=row.caller_user_id,
        subject_digest=row.subject_digest,
        steps_digest=row.steps_digest,
        report_digest=row.report_digest,
        ok=row.ok,
        error_code=row.error_code,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


class SkillRunRequest(BaseModel):
    version: str = Field(..., min_length=1, max_length=20)
    # subject upper bound mirrors the SOP template abuse guard - admin-only
    # endpoint, but oversized subject still inflates the LLM prompt.
    subject: dict = Field(..., min_length=1, max_length=1000)


# Map SkillRunner error_code -> HTTP status. Client-state failures (the skill
# is disabled / its template is corrupt) are 4xx; upstream failures (the MCP
# tool or the LLM blew up) are 5xx. `forbidden` -> 403, `not_registered` is
# raised as SkillExecutionNotFoundError -> 404 (handled separately).
_RUN_ERROR_STATUS: dict[str, int] = {
    "forbidden": 403,
    "disabled": 409,
    "template_error": 422,
    "tool_error": 500,
    "llm_error": 500,
}


class SkillRunStepDTO(BaseModel):
    """Per-step summary — digest only, no raw facts."""

    id: str
    ok: bool
    digest: str | None


class SkillRunResponse(BaseModel):
    """Trial-run artifact: report goes to the privileged caller only."""

    report: str
    execution_audit_id: uuid.UUID
    duration_ms: int
    steps: list[SkillRunStepDTO]


def _check_admin_role(role: str) -> None:
    if role not in SKILL_REGISTRY_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="无权执行该管理操作")


@router.get("/{skill_id}/executions", response_model=ExecutionListResponse)
async def list_executions(
    skill_id: str,
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """Paginated execution audit for one skill (spec §4.5).

    Admin roles only; the skill lookup and the audit query are both
    tenant-forced, so another tenant's skill id yields 404 and its audit
    rows are never reachable.
    """
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    _check_admin_role(str(current_user.get("role", "employee")))
    service = _service(session)
    try:
        skill = await service.get_by_id(tenant_id, uuid.UUID(skill_id))
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    rows, total = await SkillExecutionAuditRepository(session).list_by_skill(
        tenant_id, skill.id, limit=limit, offset=offset
    )
    return ExecutionListResponse(
        items=[_to_execution_dto(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{skill_id}/run", response_model=SkillRunResponse)
async def run_skill(
    skill_id: str,
    req: SkillRunRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """Trial run (management-page debug entry, spec §4.5).

    Admin roles only. Resolves the skill by id (tenant-forced -> 404 for
    another tenant), then delegates to :class:`SkillRunner` pinned to the
    requested ``version``. Failure branches are audited by the runner; the
    audit row is committed BEFORE the error is re-raised as an HTTP error,
    otherwise ``get_session`` would roll it back.

    REQ-046 PR-5: wire the production ``internal_query`` channel. The runner
    gets a ``query_runner`` bound to the request-scoped ``QueryService``
    (``app.state.query_service`` re-bound to this session, mirroring the
    query_router wiring) so ``internal_query`` steps execute governed
    structured-data queries; skills without such steps are unaffected.
    """
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    role = str(current_user.get("role", "employee"))
    _check_admin_role(role)
    service = _service(session)
    try:
        skill = await service.get_by_id(tenant_id, uuid.UUID(skill_id))
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    query_runner = build_dd_internal_query_runner(
        request.app.state.query_service, session
    )
    runner = SkillRunner(session, query_runner=query_runner)
    caller = InvocationCaller(
        caller_type="http_api",
        role=role,
        user_id=uuid.UUID(str(current_user["id"])),
    )
    try:
        result = await runner.run(
            tenant_id=tenant_id,
            skill_code=skill.code,
            version=req.version,
            subject=req.subject,
            caller=caller,
        )
    except SkillExecutionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SkillExecutionError as e:
        # Persist the failure audit row before surfacing the error.
        await session.commit()
        # Map error_code to the most accurate HTTP status: client-state
        # failures (disabled / template_error) are 4xx, upstream failures
        # (tool_error / llm_error) are 5xx. forbidden is 403.
        status_code = _RUN_ERROR_STATUS.get(e.error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail=f"skill 执行失败 (error_code={e.error_code}): {e}",
        ) from e
    await session.commit()
    return SkillRunResponse(
        report=result.report,
        execution_audit_id=result.execution_audit_id,
        duration_ms=result.duration_ms,
        steps=[
            SkillRunStepDTO(id=s.id, ok=s.ok, digest=s.digest)
            for s in result.steps
        ],
    )
