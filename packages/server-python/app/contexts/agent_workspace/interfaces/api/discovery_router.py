"""REQ-042 WS-S2 definition discovery 端点（独立小 router）。

契约：docs/02-delivery-plans/01-specs/2026-10-19-req-042-ws-s2-definition-discovery-contract.md

与 conversations router 分离：现 workspace router prefix 为
``/api/v1/agent-workspace/conversations``，本端点在其外（契约 §7）。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.servable_definition_catalog import (
    build_servable_definition_catalog,
)
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter(
    prefix="/api/v1/agent-workspace",
    tags=["agent-workspace"],
)


class ServableDefinitionDTO(BaseModel):
    """契约 §2：每项恰三字段；禁带 server-selected launch 输入。"""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    definition_key: str
    version: int


class ServableDefinitionListResponse(BaseModel):
    """契约 §2：``{"items": [...]}``；空列表是正常语义。"""

    model_config = ConfigDict(extra="forbid")

    items: list[ServableDefinitionDTO]


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.get(
    "/servable-agent-definitions",
    response_model=ServableDefinitionListResponse,
    status_code=200,
)
async def list_servable_agent_definitions(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
) -> ServableDefinitionListResponse:
    """契约 §2/§3/§4：tenant 从鉴权派生；只读，零写库；空 = 200 正常语义。"""
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    try:
        items = await build_servable_definition_catalog(session).list_servable_definitions(
            tenant_id=tenant_id
        )
    except Exception as exc:
        # 契约 §2：未预期失败 500 internal_error（phase-A §10 形状）。
        raise HTTPException(
            status_code=500,
            detail=_error_detail("internal_error", "definition discovery failed"),
        ) from exc
    return ServableDefinitionListResponse(
        items=[
            ServableDefinitionDTO(
                id=item.id,
                definition_key=item.definition_key,
                version=item.version,
            )
            for item in items
        ]
    )


__all__ = ["router"]
