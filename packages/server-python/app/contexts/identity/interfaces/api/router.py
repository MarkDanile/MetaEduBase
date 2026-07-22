import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.application.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.contexts.identity.application.security_logger import log_security_event
from app.contexts.identity.domain.role import RoleEnum
from app.contexts.identity.infrastructure.user_repository import UserRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter()

# BUG-017 AC-1: 公开自注册的默认 tenant（V0 单租户园区）。register 不得接受
# 客户端 tenant_id，匿名用户只能进入此默认 tenant 且仅获最低权限。
DEFAULT_REGISTER_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    role: str
    domain: str | None = None
    username: str


class RegisterRequest(BaseModel):
    """BUG-017 AC-1: 公开注册只接受最低权限主体字段。

    ``role`` / ``tenant_id`` 由服务端强制（teacher + 默认 tenant），客户端
    不得指定。``extra='forbid'`` 让客户端传 role / tenant_id 直接 422，
    显式拒绝高权自注册。
    """

    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    email: str | None = None
    domain: str | None = None


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):  # noqa: B008
    repo = UserRepository(session)
    row = await repo.find_by_username(data.username)

    if row is None or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not verify_password(data.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token({"sub": str(row["id"]), "tid": str(row["tenant_id"])})

    return LoginResponse(
        access_token=token,
        tenant_id=str(row["tenant_id"]),
        role=row["role"],
        domain=row["domain"],
        username=row["username"],
    )


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_session)):  # noqa: B008
    """BUG-017 AC-1: 公开注册强制 role=teacher + 默认 tenant。

    客户端无法指定 role / tenant_id（RegisterRequest extra='forbid'）；
    服务端固定写入最低权限与默认 tenant，匿名不得获得管理角色或进入
    指定已有 tenant。高权用户经 ``/api/v1/admin/users`` 管理员入口创建。
    """
    repo = UserRepository(session)

    if await repo.exists_by_username(data.username):
        log_security_event(
            event_type="register",
            target_user_id=None,
            result="denied",
            detail={"reason": "duplicate_username", "username": data.username},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user_id = uuid.uuid4()
    tenant_id = DEFAULT_REGISTER_TENANT_ID
    password_hash = hash_password(data.password)

    await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        username=data.username,
        email=data.email,
        password_hash=password_hash,
        role=RoleEnum.TEACHER.value,
        domain=data.domain,
    )
    await session.commit()
    log_security_event(
        event_type="register",
        target_user_id=str(user_id),
        result="success",
        detail={"role": RoleEnum.TEACHER.value},
    )

    return {"id": str(user_id), "username": data.username, "role": RoleEnum.TEACHER.value}


@router.get("/me")
async def read_current_user(current_user: dict = Depends(get_current_user)):  # noqa: B008
    return current_user
