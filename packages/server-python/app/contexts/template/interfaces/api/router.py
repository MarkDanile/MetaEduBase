from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.template.application.dto import (
    TemplateAIInitRequest,
    TemplateAIInitResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.contexts.template.application.service import TemplateService
from app.contexts.template.interfaces.api.dependencies import get_template_service
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    return await service.list(UUID(tenant_id))

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    result = await service.get(UUID(template_id), UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    dto: TemplateCreate,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    return await service.create(dto, UUID(tenant_id))

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    dto: TemplateUpdate,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    result = await service.update(UUID(template_id), dto, UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    await service.delete(UUID(template_id), UUID(tenant_id))

@router.post("/init-by-ai", response_model=TemplateAIInitResponse)
async def init_template_by_ai(
    dto: TemplateAIInitRequest,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/check-doc-type", response_model=dict)
async def check_doc_type(
    doc_type: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    templates = await service.list(UUID(tenant_id))
    used_by = [t for t in templates if doc_type in t["doc_types"]]
    return {
        "doc_type": doc_type,
        "used": len(used_by) > 0,
        "templates": [{"id": t["id"], "name": t["name"]} for t in used_by],
    }
