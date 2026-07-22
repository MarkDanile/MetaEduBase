from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.ai_app.domain.enums import AiAppEntryType, AiAppStatus, AiAppVisibility


class AiAppCreate(BaseModel):
    """BUG-018 AC-3: client 不得指定 tenant_id / is_platform（extra='forbid'）；
    服务端强制 tenant_id=current_user.tenant_id；is_platform 仅 super_admin 可设。"""

    model_config = ConfigDict(extra="forbid")

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


class AiAppPublicResponse(BaseModel):
    """BUG-018 AC-4/AC-5: 默认列表/详情响应不含 token / config_schema / owner 私有配置。

    公开 endpoint、管理端点默认都返回此类型（管理超管加 ?scope=admin 才看 AdminResponse）。
    """

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
    required_capabilities: list[str] | None
    version: str
    sort_order: int
    tenant_id: UUID | None
    is_platform: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiAppAdminResponse(AiAppPublicResponse):
    """BUG-018 AC-4: 超管 ?scope=admin 才返回 token 字段（含 share_token/api_token）。"""

    owner: str | None
    config_schema: dict[str, Any] | None
    share_token: str | None
    api_token: str | None


class AiAppTokenResponse(BaseModel):
    """BUG-018 AC-4: rotate 只返回对应 token 字段，不含整 DTO。"""

    token: str


class AiAppListResponse(BaseModel):
    items: list[AiAppPublicResponse]
    total: int
