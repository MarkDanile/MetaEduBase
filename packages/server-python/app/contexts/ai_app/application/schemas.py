from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.contexts.ai_app.domain.enums import AiAppEntryType, AiAppStatus, AiAppVisibility


class AiAppCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(None, max_length=100)
    icon: str | None = Field(None, max_length=500)
    status: AiAppStatus = AiAppStatus.DRAFT
    visibility: AiAppVisibility = AiAppVisibility.INTERNAL
    entry_type: AiAppEntryType = AiAppEntryType.INTERNAL_ROUTE
    route_path: str | None = Field(None, max_length=200)
    external_url: str | None = Field(None, max_length=500)
    config_schema: dict[str, Any] | None = None
    required_capabilities: list[str] | None = None
    owner: str | None = Field(None, max_length=200)
    version: str = "1.0.0"
    sort_order: int = 0
    tenant_id: UUID | None = None


class AiAppUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(None, max_length=100)
    icon: str | None = Field(None, max_length=500)
    status: AiAppStatus | None = None
    visibility: AiAppVisibility | None = None
    entry_type: AiAppEntryType | None = None
    route_path: str | None = Field(None, max_length=200)
    external_url: str | None = Field(None, max_length=500)
    config_schema: dict[str, Any] | None = None
    required_capabilities: list[str] | None = None
    owner: str | None = Field(None, max_length=200)
    version: str | None = Field(None, max_length=20)
    sort_order: int | None = None


class AiAppResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    category: str | None
    icon: str | None
    status: AiAppStatus
    visibility: AiAppVisibility
    entry_type: AiAppEntryType
    route_path: str | None
    external_url: str | None
    config_schema: dict[str, Any] | None
    required_capabilities: list[str] | None
    owner: str | None
    version: str
    sort_order: int
    tenant_id: UUID | None
    share_token: str | None
    api_token: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiAppListResponse(BaseModel):
    items: list[AiAppResponse]
    total: int
