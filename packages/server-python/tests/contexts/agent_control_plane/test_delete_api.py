from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.shared.infrastructure.seed import DEFAULT_TENANT_ID
from tests.contexts.agent_control_plane.helpers import (
    create_baseline_fences_via_engine,
)

pytestmark = pytest.mark.asyncio


async def test_delete_and_restore_use_revisioned_control_plane_guard(
    client: AsyncClient, auth_headers: dict[str, str]
):
    created = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "Delete through B1"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    missing_revision = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=auth_headers,
    )
    assert missing_revision.status_code == 428
    deleted = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": "1"},
    )
    assert deleted.status_code == 202, deleted.text
    assert deleted.json()["state"] == "deleted"
    assert deleted.json()["revision"] == 2

    # R1-S2：restore 要求预期 owner fence 集合完整且全部 active（backfill 基线）。
    await create_baseline_fences_via_engine(
        tenant_id=DEFAULT_TENANT_ID, conversation_id=uuid.UUID(conversation_id)
    )
    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "2"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["state"] == "active"
    assert restored.json()["revision"] == 3
