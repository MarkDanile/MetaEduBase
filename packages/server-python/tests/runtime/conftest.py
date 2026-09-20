"""Shared fixtures for runtime tests (TD-085 Slice A).

The runtime package hosts the ``LlmProvider`` port + the OpenAI-
compatible adapter. Tests under ``tests/runtime/`` only need asyncio
support; no DB, no FastAPI client, no external network.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def event_loop_policy():
    """Expose the default asyncio policy for tests that need it."""
    return asyncio.DefaultEventLoopPolicy()
