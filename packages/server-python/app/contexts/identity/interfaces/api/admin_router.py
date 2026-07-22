"""BUG-017 Slice 3: 管理员建用户与角色授予入口（AC-2）。

受控的身份管理入口--只有 ``super_admin`` 可建用户、授予或变更角色、启停
账号。公开 register 只能创建最低权限（teacher），高权角色经此入口授予。

越权（非 super_admin）一律 403；role 必须在受控枚举内；跨租户操作不命中。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.application.auth_service import hash_password
from app.contexts.identity.application.security_logger import log_security_event
from app.contexts.identity.domain.role import is_valid_role
from app.contexts.identity.infrastructure.user_repository import UserRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter()


def _require_super_admin(current_user: dict) -> None:
    if current_user.get("role") != "super_admin":
        log_security_event(
            event_type="admin_access_denied",
            actor_user_id=str(current_user.get("id")),
            result="denied",
            detail={"role": current_user.get("role")},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="仅 super_admin 可管理用户"
        )


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    role: str
    tenant_id: str
    email: str | None = None
    domain: str | None = None
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    is_active: bool | None = None


@router.post("/users", status_code=201)
async def create_user(
    data: CreateUserRequest,
    current_user: dict = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    """super_admin 建用户（受控 role + 指定 tenant）。"""
    _require_super_admin(current_user)
    if not is_valid_role(data.role):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"role '{data.role}' 不在受控枚举内",
        )
    repo = UserRepository(session)
    if await repo.exists_by_username(data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user_id = uuid.uuid4()
    try:
        tenant_id = uuid.UUID(data.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="tenant_id 非法"
        ) from exc

    await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        domain=data.domain,
    )
    if not data.is_active:
        await repo.update_role_and_status(
            user_id=user_id, tenant_id=tenant_id, is_active=False
        )
    await session.commit()
    log_security_event(
        event_type="admin_create_user",
        actor_user_id=str(current_user["id"]),
        target_user_id=str(user_id),
        result="success",
        detail={"role": data.role, "tenant_id": str(tenant_id)},
    )
    return {
        "id": str(user_id),
        "username": data.username,
        "role": data.role,
        "tenant_id": str(tenant_id),
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    data: UpdateUserRequest,
    current_user: dict = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    """super_admin 变更用户角色 / 启停账号。"""
    _require_super_admin(current_user)
    if data.role is None and data.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="需至少指定 role 或 is_active",
        )
    if data.role is not None and not is_valid_role(data.role):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"role '{data.role}' 不在受控枚举内",
        )
    repo = UserRepository(session)
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    existing = await repo.find_by_id(user_id, tenant_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    hit = await repo.update_role_and_status(
        user_id=user_id,
        tenant_id=tenant_id,
        role=data.role,
        is_active=data.is_active,
    )
    if not hit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await session.commit()
    event_type = "admin_update_role" if data.role is not None else "admin_disable_user"
    log_security_event(
        event_type=event_type,
        actor_user_id=str(current_user["id"]),
        target_user_id=str(user_id),
        result="success",
        detail={"role": data.role, "is_active": data.is_active},
    )
    return {
        "id": str(user_id),
        "role": data.role or existing["role"],
        "is_active": data.is_active if data.is_active is not None else existing["is_active"],
    }
