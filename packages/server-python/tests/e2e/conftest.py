"""E2E shared fixtures; external brokers/providers remain mocked by default."""

from __future__ import annotations

import os

import pytest

from app.config import settings


@pytest.fixture
def e2e_db_url():
    """Point ``settings.database_url`` at the test database."""
    test_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    original = settings.database_url
    settings.database_url = test_url
    try:
        yield test_url
    finally:
        settings.database_url = original
