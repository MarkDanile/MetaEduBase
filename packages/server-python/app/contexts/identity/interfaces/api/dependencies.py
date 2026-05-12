from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import set_tenant_context, clear_tenant_context
from app.contexts.identity.application.auth_service import decode_access_token

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: AsyncSession = Depends(get_session),
) -> dict:
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    user_id = payload.get("sub")
    tenant_id = payload.get("tid")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌缺少必要信息")

    result = await session.execute(
        text(
            "SELECT u.id, u.tenant_id, u.username, u.role, u.domain, u.clearance_level, u.is_active "
            "FROM metaedu.users u WHERE u.id = :user_id AND u.tenant_id = :tenant_id"
        ),
        {"user_id": UUID(user_id), "tenant_id": UUID(tenant_id)},
    )
    row = result.mappings().first()
    if row is None or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    set_tenant_context(
        tenant_id=UUID(tenant_id),
        domain=row["domain"],
        clearance=row["clearance_level"],
    )

    return dict(row)
