from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.domain import (
    ConversationRecoveryExpiredError,
    MessagePartType,
)
from app.contexts.agent_workspace.infrastructure.repository import (
    AgentWorkspaceRepository,
)
from app.main import app
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_control_plane.helpers import (
    create_baseline_fences_via_engine,
    set_core_fence_erasing_via_engine,
)
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio

_OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000002"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _ensure_other_tenant() -> None:
    """第二租户（不存在才插入），用于跨租户不可见判别；与 client 同一 TEST_DB_URL。"""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    try:
        async with engine.begin() as conn:
            exists = await conn.execute(
                text("SELECT id FROM metaedu.tenants WHERE id = :id"),
                {"id": _OTHER_TENANT_ID},
            )
            if exists.scalar_one_or_none() is not None:
                return
            now = datetime.now(UTC).replace(tzinfo=None)
            await conn.execute(
                text(
                    "INSERT INTO metaedu.tenants "
                    "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :school_name, :isolation, true, :now, :now)"
                ),
                {
                    "id": _OTHER_TENANT_ID,
                    "name": "other",
                    "school_name": "其他学校",
                    "isolation": "shared",
                    "now": now,
                },
            )
    finally:
        await engine.dispose()


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
    # R1-S2：restore 要求预期 owner fence 集合完整且全部 active（backfill 基线）。
    await create_baseline_fences_via_engine(
        tenant_id=DEFAULT_TENANT_ID, conversation_id=conversation_id
    )
    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "3"},
    )
    assert restored.status_code == 200
    assert restored.json()["state"] == "active"


async def test_late_body_write_rejected_returns_409_e2e(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """R1-S2 S2-C item 5：fence 非 active（erasing）时，经 API 的 title writer
    （rename PATCH）必须返回 409 ``late_body_write_rejected``，而非 500——
    LateBodyWriteRejectedError 在 router 映射为确定性 409，不得复活清除路径
    上的 title。"""
    create = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "to be fenced"},
    )
    assert create.status_code == 201, create.text
    conversation_id = uuid.UUID(create.json()["id"])
    # 推进 workspace.core.v1 fence 到 erasing（独立 engine 经生产 CAS 路径）。
    await set_core_fence_erasing_via_engine(
        tenant_id=DEFAULT_TENANT_ID, conversation_id=conversation_id
    )

    rejected = await client.patch(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": 'W/"1"'},
        json={"title": "should be rejected"},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "late_body_write_rejected"
    # title 未被改写（清除路径上的 title 不得复活）。
    detail = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=auth_headers,
    )
    assert detail.json()["title"] == "to be fenced"


async def test_deleted_state_listing_returns_410_e2e(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """R1-S2 S2-C P1-3 复审：公开 list/search 带 state=deleted 必须 fail closed
    （410 deleted_conversation_listing），不得返回原始 title 或搜索正文——
    deleted/purged fail-closed。deleted 恢复走 get include_deleted redacted 路径。"""
    listed = await client.get(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        params={"state": "deleted"},
    )
    assert listed.status_code == 410, listed.text
    assert listed.json()["detail"]["code"] == "deleted_conversation_listing"
    # search 同样 fail closed。
    searched = await client.get(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        params={"state": "deleted", "q": "anything"},
    )
    assert searched.status_code == 410
    assert searched.json()["detail"]["code"] == "deleted_conversation_listing"


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


async def test_durable_history_survives_new_client_reauth_and_actor_isolation(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """REQ-041 AC-3：持久化历史经「全新 client + 全新会话 + 重新鉴权」仍可读
    （公开 list + history API），且其他 owner / 其他 tenant 不可见。

    判别点：写入经 ``db_session``（独立 engine+session）commit；读取经第二个
    全新 ``AsyncClient``（新 transport），其每次请求由 ``_get_test_session``
    新建 engine+session 并重新校验 token——读写不共享同一会话/仓储缓存，证明
    durable 落库而非 same-session 假象。"""
    create = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "Durable across sessions"},
    )
    assert create.status_code == 201, create.text
    conversation_id = create.json()["id"]

    reserved = await AgentWorkspaceService(
        db_session, cursor_secret="test-secret"
    ).reserve_user_turn(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
        conversation_id=uuid.UUID(conversation_id),
        command=TurnCommand(
            client_message_id=uuid.uuid4(),
            parts=(
                MessagePartInput(
                    type=MessagePartType.TEXT,
                    text="durable history re-auth",
                ),
            ),
            agent_definition_version_id=uuid.uuid4(),
        ),
    )
    await db_session.commit()

    # 全新 client（新 transport）：每次请求新建 session + 重新鉴权。
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as fresh_client:
        listing = await fresh_client.get(
            "/api/v1/agent-workspace/conversations",
            headers=auth_headers,
        )
        assert listing.status_code == 200, listing.text
        assert conversation_id in {
            item["id"] for item in listing.json()["items"]
        }
        history = await fresh_client.get(
            f"/api/v1/agent-workspace/conversations/{conversation_id}/messages",
            headers=auth_headers,
        )
        assert history.status_code == 200, history.text
        assert history.json()["items"][0]["id"] == str(reserved.message.id)
        assert (
            history.json()["items"][0]["parts"][0]["text"]
            == "durable history re-auth"
        )

    # 其他 owner（同 tenant 新 super_admin）不可见。
    other_owner = _headers(
        await register_and_login(
            client,
            username=f"other_owner_{uuid.uuid4().hex[:8]}",
            role="super_admin",
        )
    )
    assert (
        await client.get(
            f"/api/v1/agent-workspace/conversations/{conversation_id}",
            headers=other_owner,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/agent-workspace/conversations/{conversation_id}/messages",
            headers=other_owner,
        )
    ).status_code == 404

    # 其他 tenant 的 super_admin 不可见。
    await _ensure_other_tenant()
    other_tenant = _headers(
        await register_and_login(
            client,
            username=f"other_tenant_{uuid.uuid4().hex[:8]}",
            role="super_admin",
            tenant_id=_OTHER_TENANT_ID,
        )
    )
    assert (
        await client.get(
            f"/api/v1/agent-workspace/conversations/{conversation_id}",
            headers=other_tenant,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/agent-workspace/conversations/{conversation_id}/messages",
            headers=other_tenant,
        )
    ).status_code == 404


async def test_restore_recovery_30_day_exact_cutoff_boundary(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    """R1-AC1：30 天恢复窗口精确边界（repository.restore 注入 clock，非本机时钟）。

    判据 ``effective_now >= purge_after → ConversationRecoveryExpiredError``：
    - before（purge_after = now+1s）→ 允许恢复；
    - equal（purge_after = now，含等于）→ 拒绝；
    - after（purge_after = now-1s）→ 拒绝；
    - 非 UTC offset 等值瞬时（+08:00 表达 == now UTC 瞬时）→ 与 UTC 同等拒绝。
    """
    injected_now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)
    repository = AgentWorkspaceRepository(db_session)

    async def _seed_deleted(purge_after: datetime) -> uuid.UUID:
        create = await client.post(
            "/api/v1/agent-workspace/conversations",
            headers=auth_headers,
            json={"title": "recovery window"},
        )
        assert create.status_code == 201, create.text
        cid = uuid.UUID(create.json()["id"])
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_conversations "
                "SET state = 'deleted', deleted_at = :deleted_at, "
                "deleted_by = :actor, purge_after = :purge_after, "
                "purge_state = 'not_scheduled' "
                "WHERE tenant_id = :tid AND id = :cid"
            ),
            {
                "tid": DEFAULT_TENANT_ID,
                "cid": cid,
                "deleted_at": injected_now - timedelta(days=1),
                "actor": DEFAULT_ADMIN_ID,
                "purge_after": purge_after,
            },
        )
        return cid

    async def _restore(cid: uuid.UUID):
        return await repository.restore(
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=DEFAULT_ADMIN_ID,
            conversation_id=cid,
            expected_revision=1,
            now=injected_now,
        )

    # before：窗口仍开放 → 恢复成功。
    before_cid = await _seed_deleted(injected_now + timedelta(seconds=1))
    restored = await _restore(before_cid)
    assert restored.state.value == "active"

    # equal：恰等截止（含等于）→ 拒绝。
    equal_cid = await _seed_deleted(injected_now)
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(equal_cid)

    # after：已过期 → 拒绝。
    after_cid = await _seed_deleted(injected_now - timedelta(seconds=1))
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(after_cid)

    # 非 UTC offset 等值瞬时（+08:00 表达 == injected_now UTC 瞬时）→ 同等拒绝。
    offset_equal = injected_now.astimezone(timezone(timedelta(hours=8)))
    offset_cid = await _seed_deleted(offset_equal)
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(offset_cid)
