
import os
import sys
from unittest.mock import patch

# REQ-010: ensure repo root is on sys.path so tests can import scripts.ai.*
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


@pytest_asyncio.fixture(autouse=True)
async def mock_celery_tasks():
    """Patch Celery task dispatch to prevent broker connection in tests."""
    with patch("app.contexts.document.interfaces.api.router.parse_document") as mock_doc, \
         patch("app.contexts.structured_data.interfaces.api.router.ds_parse") as mock_ds:
        mock_doc.delay = lambda *a, **k: None
        mock_ds.delay = lambda *a, **k: None
        yield


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

    # Clean template table before test run to ensure fresh state.
    # Schema/tables are expected to exist (run `./dev.sh init-test-db` or
    # `make init-test-db` once per environment); we only ensure the schema
    # namespace exists for older databases and reset per-test state.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metaedu"))
        await conn.execute(text("TRUNCATE TABLE metaedu.templates RESTART IDENTITY CASCADE"))
    await _ensure_seed(engine)
    await engine.dispose()

    app.dependency_overrides[get_session] = _get_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

    # Clean up template table after each test to prevent data leaking between tests
    cleanup_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with cleanup_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE metaedu.templates RESTART IDENTITY CASCADE"))
    await cleanup_engine.dispose()


async def _ensure_seed(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            text("SELECT id FROM metaedu.tenants WHERE id = :id"),
            {"id": DEFAULT_TENANT_ID},
        )
        if result.scalar_one_or_none():
            return
        from datetime import UTC, datetime

        import bcrypt

        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                "INSERT INTO metaedu.tenants "
                "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :school_name, :isolation, true, :now, :now)"
            ),
            {
                "id": DEFAULT_TENANT_ID,
                "name": "test",
                "school_name": "测试学校",
                "isolation": "shared",
                "now": now,
            },
        )
        pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        await session.execute(
            text(
                "INSERT INTO metaedu.users "
                "(id, tenant_id, username, email, password_hash, role, "
                "clearance_level, is_active, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :username, :email, :password_hash, "
                ":role, 5, true, :now, :now)"
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
