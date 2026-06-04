import asyncio
import uuid
from datetime import UTC, datetime

import bcrypt
from sqlalchemy import text

from app.config import settings
from app.shared.infrastructure.database import async_session_factory, engine

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


async def seed_default_data() -> None:
    if not settings.allow_default_seed:
        raise RuntimeError("默认开发 seed 需要显式设置 ALLOW_DEFAULT_SEED=true")

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM metaedu.tenants WHERE id = :id"),
            {"id": DEFAULT_TENANT_ID},
        )
        if result.scalar_one_or_none():
            return

        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                """
                INSERT INTO metaedu.tenants
                    (id, name, school_name, isolation, is_active, created_at, updated_at)
                VALUES
                    (:id, :name, :school_name, :isolation, true, :now, :now)
                """
            ),
            {
                "id": DEFAULT_TENANT_ID,
                "name": "default",
                "school_name": "默认学校",
                "isolation": "shared",
                "now": now,
            },
        )

        password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        await session.execute(
            text(
                """
                INSERT INTO metaedu.users
                    (
                        id,
                        tenant_id,
                        username,
                        email,
                        password_hash,
                        role,
                        clearance_level,
                        is_active,
                        created_at,
                        updated_at
                    )
                VALUES
                    (
                        :id,
                        :tenant_id,
                        :username,
                        :email,
                        :password_hash,
                        :role,
                        5,
                        true,
                        :now,
                        :now
                    )
                """
            ),
            {
                "id": DEFAULT_ADMIN_ID,
                "tenant_id": DEFAULT_TENANT_ID,
                "username": "admin",
                "email": "admin@metaedu.local",
                "password_hash": password_hash,
                "role": "super_admin",
                "now": now,
            },
        )

        await session.commit()
        print("✅ 种子数据已插入: 默认租户 + admin 用户")


async def seed_development_database() -> None:
    try:
        await seed_default_data()
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(seed_development_database())


if __name__ == "__main__":
    main()
