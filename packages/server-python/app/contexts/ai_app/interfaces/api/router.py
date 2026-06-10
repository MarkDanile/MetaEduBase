from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.ai_app.application.schemas import (
    AiAppCreate,
    AiAppListResponse,
    AiAppResponse,
    AiAppUpdate,
)
from app.contexts.ai_app.application.service import AiAppService
from app.contexts.ai_app.domain.enums import AiAppStatus
from app.shared.infrastructure.database import get_session

router = APIRouter()


async def get_service(session: AsyncSession = Depends(get_session)) -> AiAppService:  # noqa: B008
    return AiAppService(session)


@router.get("", response_model=AiAppListResponse)
async def list_ai_apps(
    service: Annotated[AiAppService, Depends(get_service)],
    status_filter: AiAppStatus | None = Query(None, alias="status"),  # noqa: B008
    tenant_id: UUID | None = None,
    include_archived: bool = False,
):
    items, total = await service.list(
        status=status_filter,
        tenant_id=tenant_id,
        include_archived=include_archived,
    )
    return AiAppListResponse(items=items, total=total)


@router.get("/{app_id}", response_model=AiAppResponse)
async def get_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    model = await service.get_by_id(app_id)
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return model


@router.post("", response_model=AiAppResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_app(
    data: AiAppCreate,
    service: Annotated[AiAppService, Depends(get_service)],
):
    try:
        model = await service.create(data)
        return model
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.put("/{app_id}", response_model=AiAppResponse)
async def update_ai_app(
    app_id: UUID,
    data: AiAppUpdate,
    service: Annotated[AiAppService, Depends(get_service)],
):
    try:
        model = await service.update(app_id, data)
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
        return model
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    try:
        model = await service.archive(app_id)
        if model is None:
            raise HTTPException(status_code=404, detail="AI application not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


class StatusChangeRequest(BaseModel):
    pass


@router.post("/{app_id}/publish", response_model=AiAppResponse)
async def publish_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    model = await service.get_by_id(app_id)
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    try:
        model = await service.update(app_id, AiAppUpdate(status=AiAppStatus.PUBLISHED))
        return model
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/disable", response_model=AiAppResponse)
async def disable_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    model = await service.get_by_id(app_id)
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    try:
        model = await service.update(app_id, AiAppUpdate(status=AiAppStatus.DISABLED))
        return model
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/enable", response_model=AiAppResponse)
async def enable_ai_app(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    model = await service.get_by_id(app_id)
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    try:
        model = await service.update(app_id, AiAppUpdate(status=AiAppStatus.PUBLISHED))
        return model
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/{app_id}/archive", response_model=AiAppResponse)
async def archive_ai_app_action(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    model = await service.archive(app_id)
    if model is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return model


class TokenResponse(BaseModel):
    token: str


@router.post("/{app_id}/regenerate-share-token", response_model=TokenResponse)
async def regenerate_share_token(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    token = await service.regenerate_share_token(app_id)
    if token is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return TokenResponse(token=token)


@router.post("/{app_id}/regenerate-api-token", response_model=TokenResponse)
async def regenerate_api_token(
    app_id: UUID,
    service: Annotated[AiAppService, Depends(get_service)],
):
    token = await service.regenerate_api_token(app_id)
    if token is None:
        raise HTTPException(status_code=404, detail="AI application not found")
    return TokenResponse(token=token)
