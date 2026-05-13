import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_username(self, username: str) -> dict | None:
        result = await self._session.execute(
            text(
                "SELECT u.id, u.tenant_id, u.username, u.role, u.domain, "
                "u.password_hash, u.is_active "
                "FROM metaedu.users u WHERE u.username = :username"
            ),
            {"username": username},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def exists_by_username(self, username: str) -> bool:
        result = await self._session.execute(
            text("SELECT id FROM metaedu.users WHERE username = :username"),
            {"username": username},
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        username: str,
        email: str | None,
        password_hash: str,
        role: str,
        domain: str | None,
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.users "
                "(id, tenant_id, username, email, password_hash, role, domain, "
                "clearance_level, is_active, created_at, updated_at) "
                "VALUES (:id, :tid, :username, :email, :pw_hash, :role, "
                ":domain, 0, true, :now, :now)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "username": username,
                "email": email,
                "pw_hash": password_hash,
                "role": role,
                "domain": domain,
                "now": now,
            },
        )
