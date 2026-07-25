from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DB_URL
from tests.shared.agent_control_plane import clean_agent_control_plane


@pytest_asyncio.fixture(autouse=True)
async def clean_direct_rag_control_plane(request):
    """Isolate Agent facts created by real-client AI Chat tests."""
    if "client" not in request.fixturenames:
        yield
        return

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    await clean_agent_control_plane(engine)
    try:
        yield
    finally:
        await clean_agent_control_plane(engine)
        await engine.dispose()
