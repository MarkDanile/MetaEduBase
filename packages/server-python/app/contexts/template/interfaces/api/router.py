from contextlib import suppress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.template.application.dto import (
    CloneTemplateRequest,
    DeprecateTemplateRequest,
    FieldDTO,
    ImportTemplateRequest,
    TemplateAIInitRequest,
    TemplateAIInitResponse,
    TemplateCreate,
    TemplateExportResponse,
    TemplateResponse,
    TemplateUpdate,
    TemplateVersionDetailResponse,
    TemplateVersionResponse,
)
from app.contexts.template.application.service import TemplateService
from app.contexts.template.interfaces.api.dependencies import get_template_service
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
    # REQ-002-4: include_deprecated filter (default false hides deprecated)
    include_deprecated: bool = False,
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    return await service.list_with_filter(tenant_uuid, include_deprecated=include_deprecated)


# NOTE: Specific routes must be defined BEFORE /{template_id}
# to avoid being matched as a template_id
@router.get("/check-doc-type", response_model=dict)
async def check_doc_type(
    doc_type: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    templates = await service.list(tenant_id)
    used_by = [t for t in templates if doc_type in t["doc_types"]]
    return {
        "doc_type": doc_type,
        "used": len(used_by) > 0,
        "templates": [{"id": t["id"], "name": t["name"]} for t in used_by],
    }


@router.post("/init-by-ai", response_model=TemplateAIInitResponse)
async def init_template_by_ai(
    dto: TemplateAIInitRequest,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    source_file_uuid = UUID(dto.source_file_id) if dto.source_file_id else None
    # get_tenant_id() may return UUID or str depending on context
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    fields = await service.init_by_ai(dto.doc_type, source_file_uuid, tenant_uuid, dto.ai_context)
    # Validate and convert to FieldDTO
    validated = []
    for f in fields:
        with suppress(Exception):
            validated.append(FieldDTO(**f))
    return TemplateAIInitResponse(fields=validated)


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    dto: TemplateCreate,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    try:
        return await service.create(dto, tenant_uuid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    result = await service.get(UUID(template_id), tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    dto: TemplateUpdate,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    try:
        result = await service.update(UUID(template_id), dto, tenant_uuid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    await service.delete(UUID(template_id), tenant_id)


# REQ-002-2: clone / version / export / import endpoints
# NOTE: /import must be defined BEFORE /{template_id} patterns
# but since it uses POST /import (no {template_id} segment), order is safe.


@router.post("/import", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def import_template(
    dto: ImportTemplateRequest,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
    response: Response,
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    if dto.template.get("format") and dto.template["format"] != "metaedu-template-v1":
        raise HTTPException(status_code=400, detail="Unsupported format")
    try:
        result = await service.import_template(dto, tenant_uuid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    # AC-8: schema_version warning header
    payload_schema = dto.template.get("schema_version", 1)
    if payload_schema > 1:
        response.headers["X-Import-Warning"] = (
            f"schema_version mismatch: imported={payload_schema}, current=1"
        )
    return result


@router.post(
    "/{template_id}/clone",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_template(
    template_id: str,
    dto: CloneTemplateRequest,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    try:
        result = await service.clone(UUID(template_id), dto, tenant_uuid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.get("/{template_id}/versions", response_model=list[TemplateVersionResponse])
async def list_template_versions(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = 20,
    offset: int = 0,
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    return await service.list_versions(UUID(template_id), tenant_uuid, limit, offset)


@router.get(
    "/{template_id}/versions/{version_number}",
    response_model=TemplateVersionDetailResponse,
)
async def get_template_version(
    template_id: str,
    version_number: int,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    result = await service.get_version(UUID(template_id), tenant_uuid, version_number)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return result


@router.post(
    "/{template_id}/rollback/{version_number}",
    response_model=TemplateResponse,
)
async def rollback_template(
    template_id: str,
    version_number: int,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    result = await service.rollback(UUID(template_id), version_number, tenant_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Template or version not found")
    return result


@router.get(
    "/{template_id}/export",
    response_model=TemplateExportResponse,
)
async def export_template(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    result = await service.export_template(UUID(template_id), tenant_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


# REQ-002-4: deprecation endpoints
# NOTE: must be defined BEFORE /{template_id} catch-all but since they
# use POST .../{id}/deprecate, they are unique paths and order is safe.


@router.post("/{template_id}/deprecate", response_model=TemplateResponse)
async def deprecate_template(
    template_id: str,
    dto: DeprecateTemplateRequest,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    result = await service.deprecate(UUID(template_id), dto.reason, tenant_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.post("/{template_id}/undeprecate", response_model=TemplateResponse)
async def undeprecate_template(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
    result = await service.undeprecate(UUID(template_id), tenant_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result
