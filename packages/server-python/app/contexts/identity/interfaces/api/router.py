import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.application.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.contexts.identity.infrastructure.user_repository import UserRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter()


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
    username: str
    password: str
    email: str | None = None
    role: str = "teacher"
    domain: str | None = None
    tenant_id: str = "00000000-0000-0000-0000-000000000001"


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
    repo = UserRepository(session)

    if await repo.exists_by_username(data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user_id = uuid.uuid4()
    tenant_id = uuid.UUID(data.tenant_id)
    password_hash = hash_password(data.password)

    await repo.create(
        user_id=user_id,
        tenant_id=tenant_id,
        username=data.username,
        email=data.email,
        password_hash=password_hash,
        role=data.role,
        domain=data.domain,
    )
    await session.commit()

    return {"id": str(user_id), "username": data.username, "role": data.role}


@router.get("/me")
async def read_current_user(current_user: dict = Depends(get_current_user)):  # noqa: B008
    return current_user
