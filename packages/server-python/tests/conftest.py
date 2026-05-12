import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.shared.infrastructure.database import Base, get_session
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID, DEFAULT_ADMIN_ID
from app.main import app


TEST_DB_URL = "postgresql+asyncpg://metaedu@localhost:5432/metaedu_test"


async def _get_test_session():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metaedu"))
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_seed(engine)
    await engine.dispose()

    app.dependency_overrides[get_session] = _get_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _ensure_seed(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            text("SELECT id FROM metaedu.tenants WHERE id = :id"),
            {"id": DEFAULT_TENANT_ID},
        )
        if result.scalar_one_or_none():
            return
        import bcrypt
        from datetime import datetime

        now = datetime.utcnow()
        await session.execute(
            text(
                "INSERT INTO metaedu.tenants (id, name, school_name, isolation, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :school_name, :isolation, true, :now, :now)"
            ),
            {"id": DEFAULT_TENANT_ID, "name": "test", "school_name": "测试学校", "isolation": "shared", "now": now},
        )
        pw_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        await session.execute(
            text(
                "INSERT INTO metaedu.users (id, tenant_id, username, email, password_hash, role, clearance_level, is_active, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :username, :email, :password_hash, :role, 5, true, :now, :now)"
            ),
            {
                "id": DEFAULT_ADMIN_ID, "tenant_id": DEFAULT_TENANT_ID,
                "username": "admin", "email": "admin@test.local",
                "password_hash": pw_hash, "role": "super_admin", "now": now,
            },
        )
        await session.commit()


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str):
    return {"Authorization": f"Bearer {auth_token}"}
