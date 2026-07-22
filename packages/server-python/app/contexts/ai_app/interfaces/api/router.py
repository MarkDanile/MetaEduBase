from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.ai_app.application.schemas import (
    AiAppAdminResponse,
    AiAppCreate,
    AiAppListResponse,
    AiAppPublicResponse,
    AiAppTokenResponse,
    AiAppUpdate,
)
from app.contexts.ai_app.application.service import AiAppService
from app.contexts.ai_app.domain.enums import AiAppStatus
from app.contexts.identity.application.security_logger import log_security_event
from app.contexts.identity.domain.role import HIGH_PRIVILEGE_ROLES
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter()


async def get_service(session: AsyncSession = Depends(get_session)) -> AiAppService:  # noqa: B008
    return AiAppService(session)


def _require_admin(current_user: dict) -> None:
    """BUG-018 AC-1: 管理端点仅对 HIGH_PRIVILEGE_ROLES 开放（403），匿名 401。"""
    if current_user.get("role") not in HIGH_PRIVILEGE_ROLES:
        log_security_event(
            event_type="admin_access_denied",
            actor_user_id=str(current_user.get("id")),
            result="denied",
            detail={"role": current_user.get("role"), "endpoint": "ai-app-admin"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅 super_admin / data_admin / admin 可管理 AI App",
        )


@router.get("/public", response_model=AiAppListResponse)
async def list_public_ai_apps(
    service: Annotated[AiAppService, Depends(get_service)],
):
    """BUG-018 AC-5: 匿名公开广场，仅 PUBLISHED + visibility=public + is_platform=True。"""
    items = await service.list_published_public()
    return AiAppListResponse(items=items, total=len(items))


@router.get("", response_model=AiAppListResponse)
async def list_ai_apps(
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
    status_filter: AiAppStatus | None = Query(None, alias="status"),  # noqa: B008
    include_archived: bool = False,
    scope: str | None = Query(None),
):
    """BUG-018 AC-4: 默认 PublicResponse；超管 ?scope=admin 返 AiAppAdminResponse。"""
    _require_admin(current_user)
    items, total = await service.list(
        status=status_filter,
        tenant_id=UUID(str(current_user["tenant_id"])),
        include_archived=include_archived,
        viewer_role=current_user.get("role"),
    )
    if scope == "admin" and current_user.get("role") == "super_admin":
        items_dict = [AiAppAdminResponse.model_validate(m).model_dump(mode="json") for m in items]
    else:
        items_dict = [AiAppPublicResponse.model_validate(m).model_dump(mode="json") for m in items]
    return {"items": items_dict, "total": total}


@router.get("/{app_id}")
async def get_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
    scope: str | None = Query(None),
):
    """BUG-018 AC-4: 详情默认 PublicResponse；超管 ?scope=admin 返 AdminResponse。

    不声明 response_model（FastAPI 会强制 schema 过滤掉 Admin 额外字段），改为手动 dict。
    """
    _require_admin(current_user)
    model = await service.get_by_id(
        app_id,
        viewer_tenant_id=UUID(str(current_user["tenant_id"])),
        viewer_role=current_user.get("role"),
    )
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    if scope == "admin" and current_user.get("role") == "super_admin":
        return AiAppAdminResponse.model_validate(model).model_dump(mode="json")
    return AiAppPublicResponse.model_validate(model).model_dump(mode="json")


@router.post("", response_model=AiAppPublicResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_app(
    data: AiAppCreate,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    try:
        model = await service.create(
            data,
            tenant_id=UUID(str(current_user["tenant_id"])),
            operator_role=current_user.get("role", ""),
        )
        return AiAppPublicResponse.model_validate(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.put("/{app_id}", response_model=AiAppPublicResponse)
async def update_ai_app(
    app_id: UUID,
    data: AiAppUpdate,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    try:
        model = await service.update(
            app_id, data,
            viewer_tenant_id=UUID(str(current_user["tenant_id"])),
            viewer_role=current_user.get("role"),
        )
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
        return AiAppPublicResponse.model_validate(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    try:
        model = await service.archive(
            app_id,
            viewer_tenant_id=UUID(str(current_user["tenant_id"])),
            viewer_role=current_user.get("role"),
        )
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/publish", response_model=AiAppPublicResponse)
async def publish_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    tid = UUID(str(current_user["tenant_id"]))
    role = current_user.get("role")
    try:
        model = await service.update(
            app_id, AiAppUpdate(status=AiAppStatus.PUBLISHED),
            viewer_tenant_id=tid, viewer_role=role,
        )
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
        return AiAppPublicResponse.model_validate(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/disable", response_model=AiAppPublicResponse)
async def disable_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    tid = UUID(str(current_user["tenant_id"]))
    role = current_user.get("role")
    try:
        model = await service.update(
            app_id, AiAppUpdate(status=AiAppStatus.DISABLED),
            viewer_tenant_id=tid, viewer_role=role,
        )
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
        return AiAppPublicResponse.model_validate(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/enable", response_model=AiAppPublicResponse)
async def enable_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    tid = UUID(str(current_user["tenant_id"]))
    role = current_user.get("role")
    try:
        model = await service.update(
            app_id, AiAppUpdate(status=AiAppStatus.PUBLISHED),
            viewer_tenant_id=tid, viewer_role=role,
        )
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
        return AiAppPublicResponse.model_validate(model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/archive", response_model=AiAppPublicResponse)
async def archive_ai_app_action(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    model = await service.archive(
        app_id,
        viewer_tenant_id=UUID(str(current_user["tenant_id"])),
        viewer_role=current_user.get("role"),
    )
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return AiAppPublicResponse.model_validate(model)


@router.post("/{app_id}/regenerate-share-token", response_model=AiAppTokenResponse)
async def regenerate_share_token(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    token = await service.regenerate_share_token(
        app_id,
        viewer_tenant_id=UUID(str(current_user["tenant_id"])),
        viewer_role=current_user.get("role"),
    )
    if token is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return AiAppTokenResponse(token=token)


@router.post("/{app_id}/regenerate-api-token", response_model=AiAppTokenResponse)
async def regenerate_api_token(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
    current_user: Annotated[dict, Depends(get_current_user)],  # noqa: B008
):
    _require_admin(current_user)
    token = await service.regenerate_api_token(
        app_id,
        viewer_tenant_id=UUID(str(current_user["tenant_id"])),
        viewer_role=current_user.get("role"),
    )
    if token is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return AiAppTokenResponse(token=token)
