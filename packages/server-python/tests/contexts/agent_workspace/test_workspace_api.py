from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.domain import MessagePartType
from app.main import app
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_conversation_idempotency_rejects_payload_mismatch(
    client: AsyncClient, auth_headers: dict[str, str]
):
    conversation_id = str(uuid.uuid4())
    payload = {"conversation_id": conversation_id, "title": "Stable create"}
    created = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json=payload,
    )
    assert created.status_code == 201
    replay = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == conversation_id
    conflict = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"conversation_id": conversation_id, "title": "Changed command"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


async def test_owner_private_crud_cas_and_history(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    create = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "Workspace thread"},
    )
    assert create.status_code == 201, create.text
    conversation = create.json()
    conversation_id = uuid.UUID(conversation["id"])
    assert conversation["revision"] == 1

    missing_precondition = await client.patch(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=auth_headers,
        json={"title": "Renamed"},
    )
    assert missing_precondition.status_code == 428
    renamed = await client.patch(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": 'W/"1"'},
        json={"title": "Renamed"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["revision"] == 2
    stale = await client.patch(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": "1"},
        json={"title": "Stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    pinned = await client.put(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/pin",
        headers=auth_headers,
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned_at"] is not None
    unpinned = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/pin",
        headers=auth_headers,
    )
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned_at"] is None

    reserved = await AgentWorkspaceService(
        db_session, cursor_secret="test-secret"
    ).reserve_user_turn(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
        conversation_id=conversation_id,
        command=TurnCommand(
            client_message_id=uuid.uuid4(),
            parts=(
                MessagePartInput(
                    type=MessagePartType.TEXT,
                    text="durable history",
                ),
            ),
            agent_definition_version_id=uuid.uuid4(),
        ),
    )
    await db_session.commit()
    history = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/messages",
        headers=auth_headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["id"] == str(reserved.message.id)
    assert history.json()["items"][0]["parts"][0]["text"] == "durable history"

    archived = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/archive",
        headers={**auth_headers, "If-Match": "2"},
    )
    assert archived.status_code == 200
    assert archived.json()["state"] == "archived"
    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "3"},
    )
    assert restored.status_code == 200
    assert restored.json()["state"] == "active"


async def test_super_admin_role_does_not_grant_other_owners_message_access(
    client: AsyncClient, auth_headers: dict[str, str]
):
    create = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "Admin private"},
    )
    conversation_id = create.json()["id"]
    token = await register_and_login(
        client,
        username=f"other_admin_{uuid.uuid4().hex[:8]}",
        role="super_admin",
    )
    other_headers = _headers(token)
    detail = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=other_headers,
    )
    assert detail.status_code == 404
    history = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/messages",
        headers=other_headers,
    )
    assert history.status_code == 404
    listing = await client.get(
        "/api/v1/agent-workspace/conversations",
        headers=other_headers,
    )
    assert conversation_id not in {item["id"] for item in listing.json()["items"]}


async def test_b1_registers_guarded_delete_but_keeps_submit_turn_route_closed():
    paths = app.openapi()["paths"]
    base = "/api/v1/agent-workspace/conversations/{conversation_id}"
    assert "delete" in paths[base]
    assert f"{base}/turns" not in paths
    assert "delete" in paths[f"{base}/pin"]
