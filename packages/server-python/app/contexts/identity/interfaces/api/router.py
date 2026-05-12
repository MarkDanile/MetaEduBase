import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database import get_session
from app.contexts.identity.application.auth_service import verify_password, hash_password, create_access_token
from app.contexts.identity.interfaces.api.dependencies import get_current_user

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
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text(
            "SELECT u.id, u.tenant_id, u.username, u.role, u.domain, u.password_hash, u.is_active "
            "FROM metaedu.users u WHERE u.username = :username"
        ),
        {"username": data.username},
    )
    row = result.mappings().first()

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
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(
        text("SELECT id FROM metaedu.users WHERE username = :username"),
        {"username": data.username},
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    password_hash = hash_password(data.password)
    user_id = uuid.uuid4()
    tenant_id = uuid.UUID(data.tenant_id)

    await session.execute(
        text(
            "INSERT INTO metaedu.users "
            "(id, tenant_id, username, email, password_hash, role, domain, clearance_level, is_active, created_at, updated_at) "
            "VALUES (:id, :tenant_id, :username, :email, :password_hash, :role, :domain, 0, true, :now, :now)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "username": data.username,
            "email": data.email,
            "password_hash": password_hash,
            "role": data.role,
            "domain": data.domain,
            "now": __import__("datetime").datetime.utcnow(),
        },
    )
    await session.commit()

    return {"id": str(user_id), "username": data.username, "role": data.role}


@router.get("/me")
async def read_current_user(current_user: dict = Depends(get_current_user)):
    return current_user
