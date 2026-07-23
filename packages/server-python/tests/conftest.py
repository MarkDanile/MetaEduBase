# REQ-010: ensure repo root is on sys.path so tests can import scripts.ai.*
# The sys.path side effect lives in tests._paths; importing it here keeps
# conftest.py itself free of module-level statements that break E402.
import os
from unittest.mock import patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests._paths import _REPO_ROOT  # noqa: F401  (re-exported for fixtures)

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
    # REQ-052 Task 5: build a placeholder QueryService so the router
    # can read ``app.state.query_service`` during the request. Tests
    # that need the orchestrator to actually do work override this with
    # a fully-wired QueryService via the ``query_service`` fixture in
    # ``tests/contexts/structured_data/conftest.py`` — that fixture
    # uses the ``query_service`` autouse override below to swap in a
    # real instance after this fixture sets the placeholder.
    from app.contexts.structured_data.application.query_service import (
        QueryService,
    )
    from app.shared.infrastructure.database import async_session_factory

    app.state.query_service = QueryService(session_factory=async_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    app.state.query_service = None

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
        tenant_exists = result.scalar_one_or_none() is not None
        from datetime import UTC, datetime

        import bcrypt

        now = datetime.now(UTC).replace(tzinfo=None)
        if not tenant_exists:
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
                    "id": DEFAULT_ADMIN_ID,
                    "tenant_id": DEFAULT_TENANT_ID,
                    "username": "admin",
                    "email": "admin@test.local",
                    "password_hash": pw_hash,
                    "role": "super_admin",
                    "now": now,
                },
            )
        await session.execute(
            text(
                "INSERT INTO metaedu.data_catalogs "
                "(tenant_id, code, name, description, entity_types, "
                "default_business_purpose, is_active, created_by) "
                "VALUES (:tenant_id, 'education', '中高职教育数据库', "
                "'测试环境默认教育主题域', "
                "'[\"customer\",\"bill\",\"contract\"]'::jsonb, "
                "'教育数据分析', true, :created_by) "
                "ON CONFLICT (tenant_id, code) DO NOTHING"
            ),
            {
                "tenant_id": DEFAULT_TENANT_ID,
                "created_by": DEFAULT_ADMIN_ID,
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
