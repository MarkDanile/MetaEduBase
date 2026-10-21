"""TD-114 Agent identity 显式初始化端点（独立小 router）。

契约：docs/02-delivery-plans/01-specs/2026-10-19-td-114-agent-identity-bootstrap-contract.md

与 conversations router 分离是刻意的：现 workspace router prefix 为
``/api/v1/agent-workspace/conversations``，本端点在其外（契约 §9）。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_identity_bootstrap import build_agent_identity_bootstrap
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter(
    prefix="/api/v1/agent-workspace",
    tags=["agent-workspace"],
)


class BootstrapResponse(BaseModel):
    """契约 §2：恰两字段；禁带 profile id / digest / budget 等 launch 字段。"""

    model_config = ConfigDict(extra="forbid")

    initialized: bool
    disabled_existing: bool


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.post(
    "/agent-identity/bootstrap",
    response_model=BootstrapResponse,
    status_code=200,
)
async def bootstrap_agent_identity(
    payload: dict | None = Body(None),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
) -> BootstrapResponse:
    """契约 §2：空请求体；tenant/actor 仅从认证令牌派生；幂等。"""
    # 契约 §2：请求体出现任何字段（含 tenant_id）一律 422——不信任客户端
    # 任意传入的 tenant；空体（None / {}）合法。
    if payload:
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", "request body must be empty"),
        )
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    actor_id = uuid.UUID(str(current_user["id"]))

    outcome = await build_agent_identity_bootstrap(session).bootstrap_v1_identity(
        tenant_id=tenant_id, actor_id=actor_id
    )
    if outcome.conflict:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "identity_conflict",
                outcome.conflict_reason or "identity records conflict with V1",
            ),
        )
    await session.commit()
    return BootstrapResponse(
        initialized=outcome.initialized,
        disabled_existing=outcome.disabled_existing,
    )


__all__ = ["router"]
