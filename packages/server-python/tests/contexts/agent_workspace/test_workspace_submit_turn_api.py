"""WS-S2 phase-C 公共 submit turn 端点的真实 PostgreSQL contract tests。

覆盖矩阵：

- phase-A §1/§2/§3/§4/§5/§7/§10 公共契约（端点、可提交字段、server-selected
  字段拒绝、owner 反枚举 404、archived 409、幂等重放与冲突、receipt 形状、
  完整错误表含 429 + Retry-After）
- phase-B §5.1 B-1～B-9 验收矩阵（launch 不变量、definition 可服务性、
  capability fail-closed、resource 授权）
- durable 边界（Message + outbox 原子提交、只产生一次）
- 并发（既有 ``ConversationExecutionGuard`` 语义下不产生重复 durable 结果）
- revision 边界（phase-A §6：submit 不使用 Conversation revision CAS）

测试直验 HTTP 响应与数据库最终状态，不只断言状态码。真实 PostgreSQL；
不 mock repository。外部服务不需要（LLM/broker 不在本端点路径上）。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
    ExecutionIdentityService,
)
from app.contexts.agent_workspace.interfaces.api.submit_turn_rate_limit import (
    submit_turn_rate_limiter,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio

_TURNS_PATH = "/api/v1/agent-workspace/conversations/{conversation_id}/turns"


async def _bootstrap_v1_identity(session: AsyncSession):
    """在 seed tenant 下 publish-or-get V1 compatibility identity。

    这正是 V1 提交期要求的既有事实源（``compat.direct_rag.v1`` enabled profile +
    ``system.direct_rag`` definition version）。这里不改状态机，只是让 tenant
    具备可被 V1 launch policy 解析的登记事实。
    """
    identity = await ExecutionIdentityService(session).bootstrap_direct_rag(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
    )
    await session.commit()
    return identity


async def _create_conversation(
    client: AsyncClient, headers: dict[str, str], *, title: str = "phase-C contract"
) -> str:
    resp = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=headers,
        json={"title": title},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _login_in_tenant(
    client: AsyncClient, db_session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, str]:
    """在指定 tenant 下建用户并登录，返回 Authorization 头。

    用户名带随机后缀：``users`` 表不在 workspace conftest 的清理清单里，
    固定用户名会在同进程重复运行时报「用户名已存在」。
    """
    token = await register_and_login(
        client,
        username=f"phasec_b6_{uuid.uuid4().hex[:12]}",
        role="student",
        tenant_id=str(tenant_id),
    )
    return {"Authorization": f"Bearer {token}"}


def _payload(
    definition_id: uuid.UUID,
    *,
    client_message_id: uuid.UUID | None = None,
    text: str = "hello from phase-C",
) -> dict:
    return {
        "client_message_id": str(client_message_id or uuid.uuid4()),
        "parts": [{"type": "text", "text": text, "format": "plain_text"}],
        "agent_definition_version_id": str(definition_id),
    }


async def _outbox_rows(db_session: AsyncSession, conversation_id: str) -> list[dict]:
    rows = (
        await db_session.execute(
            text(
                "SELECT aggregate_id, event_type, status FROM "
                "metaedu.agent_workspace_outbox WHERE conversation_id = :cid "
                "ORDER BY id"
            ),
            {"cid": uuid.UUID(conversation_id)},
        )
    ).all()
    return [
        {"aggregate_id": str(r[0]), "event_type": r[1], "status": r[2]} for r in rows
    ]


async def _message_rows(db_session: AsyncSession, conversation_id: str) -> list[dict]:
    rows = (
        await db_session.execute(
            text(
                "SELECT id, seq, requested_run_id, requested_run_queue_seq, "
                "turn_dispatch_state FROM metaedu.agent_messages "
                "WHERE conversation_id = :cid ORDER BY seq"
            ),
            {"cid": uuid.UUID(conversation_id)},
        )
    ).all()
    return [
        {
            "id": str(r[0]),
            "seq": r[1],
            "requested_run_id": str(r[2]),
            "requested_run_queue_seq": r[3],
            "dispatch_state": r[4],
        }
        for r in rows
    ]


async def _launch_payload(db_session: AsyncSession, message_id: str) -> dict:
    raw = (
        await db_session.execute(
            text(
                "SELECT payload_inline FROM metaedu.agent_workspace_outbox "
                "WHERE aggregate_id = :mid"
            ),
            {"mid": uuid.UUID(message_id)},
        )
    ).scalar_one()
    # JSONB 列在 asyncpg 下已是 dict；兼容字符串形态以免驱动差异。
    payload = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
    return payload["launch"]


async def _disable_compatibility_profile(db_session: AsyncSession, tenant_id: uuid.UUID):
    """临时 disable V1 profile。

    ``tests/contexts/agent_workspace/conftest.py`` 的清理清单只覆盖 workspace 表，
    不含 ``agent_runtime_profiles``，所以调用方必须在 finally 里恢复，否则会污染
    同进程后续用例。
    """
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_runtime_profiles SET enabled = false "
            "WHERE tenant_id = :tid AND profile_key = 'compat.direct_rag.v1'"
        ),
        {"tid": tenant_id},
    )
    await db_session.commit()


async def _enable_compatibility_profile(db_session: AsyncSession, tenant_id: uuid.UUID):
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_runtime_profiles SET enabled = true "
            "WHERE tenant_id = :tid AND profile_key = 'compat.direct_rag.v1'"
        ),
        {"tid": tenant_id},
    )
    await db_session.commit()


async def _insert_unservable_definition(
    db_session: AsyncSession, tenant_id: uuid.UUID, status: str = "retired"
) -> uuid.UUID:
    """插入一行「存在但不可服务」的 definition，返回其 id。

    刻意**不复用** V1 正在服务的 ``system.direct_rag`` 行：DB 层有
    ``published agent definition identity is immutable`` 约束，既禁止改动已
    published 行，也禁止 retired -> published 复活，因此测试无法靠改回来自清理。
    独立 key/version 的行不参与 ``bootstrap_direct_rag``，用完即可删除。

    ``publish_agent_definition_version`` 是唯一写入路径且恒写 ``published``，
    全仓暂无 retire 代码路径，故这里直接 INSERT 构造该状态以覆盖 phase-A §3
    要求的「启用状态校验」fail-closed 分支。
    """
    definition_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            " created_by, created_at) "
            "VALUES (:id, :tid, :key, 1, :status, :digest, :created_by, now())"
        ),
        {
            "id": definition_id,
            "tid": tenant_id,
            "key": f"test.unservable.{definition_id.hex[:8]}",
            "status": status,
            "digest": "a" * 64,
            "created_by": DEFAULT_ADMIN_ID,
        },
    )
    await db_session.commit()
    return definition_id


async def _delete_definition(
    db_session: AsyncSession, tenant_id: uuid.UUID, definition_id: uuid.UUID
):
    await db_session.execute(
        text(
            "DELETE FROM metaedu.agent_definition_versions "
            "WHERE tenant_id = :tid AND id = :did"
        ),
        {"tid": tenant_id, "did": definition_id},
    )
    await db_session.commit()


async def _capability_digest(db_session: AsyncSession, tenant_id: uuid.UUID) -> str:
    return (
        await db_session.execute(
            text(
                "SELECT capability_digest FROM metaedu.agent_runtime_profiles "
                "WHERE tenant_id = :tid AND profile_key = 'compat.direct_rag.v1'"
            ),
            {"tid": tenant_id},
        )
    ).scalar_one()


async def _set_capability_digest(
    db_session: AsyncSession, tenant_id: uuid.UUID, digest: str
):
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_runtime_profiles SET capability_digest = :digest "
            "WHERE tenant_id = :tid AND profile_key = 'compat.direct_rag.v1'"
        ),
        {"tid": tenant_id, "digest": digest},
    )
    await db_session.commit()


async def _seed_mismatched_profile_tenant(
    db_session: AsyncSession
) -> tuple[uuid.UUID, uuid.UUID]:
    """为独立 tenant 播种「capability digest 与 V1 快照不一致」的 profile。

    无法在默认 tenant 上触发 B-6：``trg_agent_runtime_profile_immutable`` 禁止修改
    已 published 的 profile identity，且 ``(tenant_id, profile_key)`` 唯一，
    所以只能换一个新 tenant 直接 INSERT 一行 digest 不匹配的 profile。
    返回 ``(tenant_id, definition_version_id)``。
    """
    tenant_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school, 'shared', true, :now, :now)"
        ),
        {
            "id": tenant_id,
            "name": f"phasec-b6-{tenant_id.hex[:8]}",
            "school": "phase-C B6",
            "now": now,
        },
    )
    definition_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            " created_by, created_at) "
            "VALUES (:id, :tid, 'system.direct_rag', 1, 'published', :digest, "
            "        :created_by, :now)"
        ),
        {
            "id": definition_id,
            "tid": tenant_id,
            "digest": "a" * 64,
            "created_by": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            " capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES (:id, :tid, 'compat.direct_rag.v1', 'compatibility', 'direct_rag', "
            "        :config_digest, :capability_digest, true, 1, :now, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "config_digest": "b" * 64,
            # 与真实 V1 capability 快照的 digest 刻意不一致 -> 触发 B-6。
            "capability_digest": "f" * 64,
            "now": now,
        },
    )
    await db_session.commit()
    return tenant_id, definition_id


# --------------------------------------------------------------------------
# phase-A §1/§7 + phase-B B-1/B-8：合法提交 -> 201 + receipt + durable 事实
# --------------------------------------------------------------------------
#
# TD-085 依赖方向的 composition 装配取证在独立文件
# ``test_workspace_submit_turn_composition_wiring.py``：TD-032 源文件行数硬限制
# 不允许本文件继续增长。


async def test_submit_turn_returns_201_receipt_and_durable_rows(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(identity.agent_definition_version.id),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # phase-A §7：receipt 公共字段全集，且不暴露 server-selected / digest / event_id。
    assert set(body) == {
        "message_id",
        "message_seq",
        "run_id",
        "run_queue_seq",
        "dispatch_state",
        "idempotent_replay",
        "correlation_id",
        "created_at",
    }
    assert body["dispatch_state"] == "pending"
    assert body["idempotent_replay"] is False
    assert body["message_seq"] >= 1
    assert body["run_queue_seq"] >= 1
    assert "event_id" not in body and "turn_request_digest" not in body

    # durable 事实：Message 与 outbox 恰好一条，且字段与 receipt 一致。
    messages = await _message_rows(db_session, conversation_id)
    assert len(messages) == 1
    assert messages[0]["id"] == body["message_id"]
    assert messages[0]["requested_run_id"] == body["run_id"]
    assert messages[0]["requested_run_queue_seq"] == body["run_queue_seq"]
    assert messages[0]["dispatch_state"] == "pending"

    outbox = await _outbox_rows(db_session, conversation_id)
    assert len(outbox) == 1
    assert outbox[0]["aggregate_id"] == body["message_id"]
    assert outbox[0]["event_type"] == "turn.requested.v1"


async def test_v1_launch_satisfies_phase_b_invariants(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-B B-1/B-8：binding/context 全 None、budget 冻结六项、capability 全 False。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(identity.agent_definition_version.id, text="launch invariants"),
    )
    assert resp.status_code == 201, resp.text
    launch = await _launch_payload(db_session, resp.json()["message_id"])

    # §2.4：V1 恒 None / 全 None。
    assert launch["runtime_binding_id"] is None
    assert launch["parent_run_id"] is None
    assert launch["context_snapshot_ref"] is None
    assert launch["context_snapshot_digest"] is None
    assert launch["context_snapshot_classification"] is None

    # §2.3：budget 六项冻结值，且双写一致。
    budget = launch["budget_snapshot"]
    assert budget == {
        "schema_version": 1,
        "max_steps": 2,
        "max_wall_seconds": 300,
        "max_tokens": 100_000,
        "max_cost_micros": 2_000_000,
        "max_tool_calls": 1,
        "max_retries": 0,
    }
    # schema 内建不变量：run_config.budget == budget_snapshot。
    assert launch["run_config_snapshot"]["budget"] == budget

    # §2.2：capability 快照与既有常量逐字段相等（全 False）。
    expected = DIRECT_RAG_CAPABILITIES.model_dump(mode="json")
    actual = launch["runtime_capability_snapshot"]
    assert {k: actual[k] for k in expected} == expected
    assert actual["runtime_kind"] == "compatibility"
    assert actual["adapter_key"] == "direct_rag"

    # §1：definition 与 profile 均为 V1 冻结目标。
    assert launch["agent_definition_version_id"] == str(
        identity.agent_definition_version.id
    )
    assert launch["runtime_profile_id"] == str(identity.runtime_profile.id)
    assert launch["run_config_snapshot"]["policy_version"] == "compat.direct_rag.v1"
    assert launch["run_config_snapshot"]["model_profile_key"] is None
    assert launch["run_config_snapshot"]["autonomy_level"] == 0
    assert launch["run_config_snapshot"]["tool_keys"] == []


async def test_client_options_cannot_inflate_budget(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-B §1：budget 不得由客户端选项放大。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    payload = _payload(identity.agent_definition_version.id, text="budget floor")
    payload["client_options"] = {
        "budget": {"max_steps": 9999, "max_tokens": 10**9},
        "max_steps": 9999,
    }
    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    launch = await _launch_payload(db_session, resp.json()["message_id"])
    assert launch["budget_snapshot"]["max_steps"] == 2
    assert launch["budget_snapshot"]["max_tokens"] == 100_000


# --------------------------------------------------------------------------
# phase-A §4 + phase-B B-2：server-selected 字段严格拒绝
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "server_selected",
    [
        {"tenant_id": "00000000-0000-0000-0000-000000000001"},
        {"actor_id": "00000000-0000-0000-0000-000000000002"},
        {"runtime_profile_id": "00000000-0000-0000-0000-000000000009"},
        {"runtime_binding_id": None},
        {"budget_snapshot": {"max_steps": 5}},
        {"run_config_snapshot": {"autonomy_level": 3}},
        {"runtime_capability_snapshot": {"tool_calls": True}},
        {"context_snapshot_ref": "ctx-1"},
        {"context_snapshot_digest": "a" * 64},
        {"context_snapshot_classification": "public"},
        {"parent_run_id": "00000000-0000-0000-0000-00000000000a"},
        {"message_seq": 1},
        {"run_queue_seq": 1},
        {"unexpected_field": "x"},
    ],
)
async def test_server_selected_or_unknown_field_returns_422(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    server_selected: dict,
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    payload = _payload(identity.agent_definition_version.id)
    payload.update(server_selected)
    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "validation_error"
    # 拒绝路径不得产生 durable 副作用。
    assert await _message_rows(db_session, conversation_id) == []
    assert await _outbox_rows(db_session, conversation_id) == []


# --------------------------------------------------------------------------
# phase-A §2/§10：owner 隔离与统一 404 反枚举
# --------------------------------------------------------------------------


async def test_unknown_conversation_returns_404(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    resp = await client.post(
        _TURNS_PATH.format(conversation_id=uuid.uuid4()),
        headers=auth_headers,
        json=_payload(identity.agent_definition_version.id),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "conversation_not_found"


async def test_deleted_conversation_returns_same_404(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """deleted 与「不存在」「非 owner」共用同一 404，不泄露存在性（phase-A §2/§10）。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    deleted = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": 'W/"1"'},
    )
    assert deleted.status_code == 202, deleted.text

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(identity.agent_definition_version.id),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "conversation_not_found"


async def test_non_owner_sees_same_404_as_unknown(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """非 owner 必须与「不存在」返回完全相同的 404（反枚举不变量）。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    # 唯一用户名：``users`` 表不在 agent_workspace conftest 的清理清单里，
    # 固定用户名会在同进程重复运行时报「用户名已存在」。
    other_token = await register_and_login(
        client, username=f"phasec_other_{uuid.uuid4().hex[:12]}", role="student"
    )
    other = {"Authorization": f"Bearer {other_token}"}

    non_owner = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=other,
        json=_payload(identity.agent_definition_version.id),
    )
    unknown = await client.post(
        _TURNS_PATH.format(conversation_id=uuid.uuid4()),
        headers=other,
        json=_payload(identity.agent_definition_version.id),
    )
    assert non_owner.status_code == 404
    assert unknown.status_code == 404
    assert (
        non_owner.json()["detail"]["code"] == unknown.json()["detail"]["code"]
        == "conversation_not_found"
    )


# --------------------------------------------------------------------------
# phase-A §2/§6/§10：archived 拒收 + revision 边界
# --------------------------------------------------------------------------


async def test_archived_conversation_returns_409_conversation_not_active(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    current = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=auth_headers,
    )
    archived = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/archive",
        headers={**auth_headers, "If-Match": f'W/"{current.json()["revision"]}"'},
    )
    assert archived.status_code == 200, archived.text

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(identity.agent_definition_version.id),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "conversation_not_active"
    assert await _message_rows(db_session, conversation_id) == []


async def test_submit_ignores_conversation_revision_changes(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-A §6：submit 不接受 expected revision；无关 revision 推进不得拒绝提交。

    即使客户端带上过期的 ``If-Match``，submit 也不得返回 ``revision_conflict``。
    """
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    # 先做一次无关的 revision 推进（rename）。
    current = await client.get(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers=auth_headers,
    )
    revision = current.json()["revision"]
    renamed = await client.patch(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": f'W/"{revision}"'},
        json={"title": "renamed before submit"},
    )
    assert renamed.status_code == 200, renamed.text

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers={**auth_headers, "If-Match": f'W/"{revision}"'},
        json=_payload(identity.agent_definition_version.id, text="revision agnostic"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["dispatch_state"] == "pending"


# --------------------------------------------------------------------------
# phase-A §5 + phase-B B-9：幂等重放与冲突
# --------------------------------------------------------------------------


async def test_idempotent_replay_returns_original_receipt_without_new_rows(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    client_message_id = uuid.uuid4()
    payload = _payload(
        identity.agent_definition_version.id, client_message_id=client_message_id
    )

    first = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=payload,
    )
    assert first.status_code == 201, first.text
    replay = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=payload,
    )
    # phase-A §1：重放 200 + idempotent_replay=true。
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["idempotent_replay"] is True
    for field in ("message_id", "run_id", "message_seq", "run_queue_seq"):
        assert replay_body[field] == first.json()[field]

    # B-9：durable 事实不因重放改变（仍各一条）。
    assert len(await _message_rows(db_session, conversation_id)) == 1
    assert len(await _outbox_rows(db_session, conversation_id)) == 1


async def test_same_key_different_digest_returns_409_idempotency_conflict(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    client_message_id = uuid.uuid4()

    first = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(
            identity.agent_definition_version.id,
            client_message_id=client_message_id,
            text="first body",
        ),
    )
    assert first.status_code == 201, first.text

    conflict = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(
            identity.agent_definition_version.id,
            client_message_id=client_message_id,
            text="different body",
        ),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    assert len(await _message_rows(db_session, conversation_id)) == 1
    assert len(await _outbox_rows(db_session, conversation_id)) == 1


# --------------------------------------------------------------------------
# phase-B §3.2-1/2 + B-4/B-5：definition 可服务性 fail-closed
# --------------------------------------------------------------------------


async def test_unknown_definition_returns_422(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=_payload(uuid.uuid4()),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "validation_error"
    assert await _message_rows(db_session, conversation_id) == []


async def test_non_published_definition_returns_403_capability_denied(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-A §3：服务端校验 definition 的**启用状态**，未启用 -> 403。

    未知 definition 走 422（另一条用例），本例覆盖「行存在但 retired」，
    必须 fail-closed 拒绝而非因「行存在」放行。
    """
    await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    unservable_id = await _insert_unservable_definition(db_session, DEFAULT_TENANT_ID)
    try:
        resp = await client.post(
            _TURNS_PATH.format(conversation_id=conversation_id),
            headers=auth_headers,
            json=_payload(unservable_id),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "capability_denied"
        # fail-closed：拒绝路径不得留下任何 durable 副作用。
        assert await _message_rows(db_session, conversation_id) == []
        assert await _outbox_rows(db_session, conversation_id) == []
    finally:
        await _delete_definition(db_session, DEFAULT_TENANT_ID, unservable_id)


async def test_capability_digest_mismatch_returns_500_internal_error(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-B B-6：capability 快照与 profile 登记 digest 不一致 -> 500 fail-closed。"""
    tenant_id, definition_id = await _seed_mismatched_profile_tenant(db_session)
    other_headers = await _login_in_tenant(client, db_session, tenant_id)
    conversation_id = await _create_conversation(client, other_headers)

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=other_headers,
        json=_payload(definition_id),
    )
    assert resp.status_code == 500, resp.text
    assert resp.json()["detail"]["code"] == "internal_error"
    # 构造失败即提交失败：不得产生 Message / Run request / outbox。
    assert await _message_rows(db_session, conversation_id) == []
    assert await _outbox_rows(db_session, conversation_id) == []


async def test_unmapped_exception_returns_stable_internal_error_code(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-A §10：未列举异常也必须返回稳定 code `internal_error`。

    用未列入映射表的 ``RuntimeError`` 走 submit 路径，证明兜底生效且
    客户端不依赖内部异常 message 即可分流。
    """
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    from app.contexts.agent_workspace.interfaces.api import router as ws_router

    original = ws_router.build_v1_launch_policy

    class _BoomPolicy:
        async def build_launch(self, **_kwargs):
            raise RuntimeError("synthetic unmapped failure")

    ws_router.build_v1_launch_policy = lambda _session: _BoomPolicy()
    try:
        resp = await client.post(
            _TURNS_PATH.format(conversation_id=conversation_id),
            headers=auth_headers,
            json=_payload(identity.agent_definition_version.id),
        )
    finally:
        ws_router.build_v1_launch_policy = original

    assert resp.status_code == 500, resp.text
    assert resp.json()["detail"]["code"] == "internal_error"
    # 响应不得泄露内部异常 message。
    assert "synthetic unmapped failure" not in resp.text
    assert await _message_rows(db_session, conversation_id) == []
    assert await _outbox_rows(db_session, conversation_id) == []


async def test_disabled_compatibility_profile_returns_403_capability_denied(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-B B-4：profile disabled -> 403 capability_denied，fail-closed 不降级。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    await _disable_compatibility_profile(db_session, DEFAULT_TENANT_ID)
    try:
        resp = await client.post(
            _TURNS_PATH.format(conversation_id=conversation_id),
            headers=auth_headers,
            json=_payload(identity.agent_definition_version.id),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "capability_denied"
        assert await _message_rows(db_session, conversation_id) == []
        assert await _outbox_rows(db_session, conversation_id) == []
    finally:
        await _enable_compatibility_profile(db_session, DEFAULT_TENANT_ID)


# --------------------------------------------------------------------------
# phase-B §3.2-4 + B-7：resource 授权
# --------------------------------------------------------------------------


async def test_unauthorized_resource_reference_returns_403(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-B B-7：resource_ref 未通过授权 -> 403 resource_access_denied。

    未装配 resource authorization adapter 时既有实现一律 fail-closed 拒绝。
    """
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    payload = _payload(identity.agent_definition_version.id, text="ignored")
    payload["parts"] = [
        {"type": "resource_ref", "resource_id": str(uuid.uuid4())},
    ]
    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "resource_access_denied"
    assert await _message_rows(db_session, conversation_id) == []


# --------------------------------------------------------------------------
# phase-A §10：未认证与提交限流
# --------------------------------------------------------------------------


async def test_unauthenticated_submit_returns_401(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    resp = await client.post(
        _TURNS_PATH.format(conversation_id=conversation_id),
        json=_payload(identity.agent_definition_version.id),
    )
    assert resp.status_code in (401, 403)
    assert await _message_rows(db_session, conversation_id) == []


async def test_rate_limited_submit_returns_429_with_retry_after(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """phase-A §10：429 rate_limited + Retry-After 响应头。"""
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    submit_turn_rate_limiter.reset()
    original = submit_turn_rate_limiter._limit
    submit_turn_rate_limiter._limit = 2
    try:
        statuses = []
        for _ in range(3):
            resp = await client.post(
                _TURNS_PATH.format(conversation_id=conversation_id),
                headers=auth_headers,
                json=_payload(identity.agent_definition_version.id),
            )
            statuses.append(resp)
        assert [r.status_code for r in statuses] == [201, 201, 429]
        limited = statuses[-1]
        assert limited.json()["detail"]["code"] == "rate_limited"
        assert int(limited.headers["Retry-After"]) >= 1
    finally:
        submit_turn_rate_limiter._limit = original
        submit_turn_rate_limiter.reset()


# --------------------------------------------------------------------------
# 并发：既有 ConversationExecutionGuard 语义下不产生重复 durable 结果
# --------------------------------------------------------------------------


async def test_concurrent_submit_same_key_produces_single_durable_result(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)
    client_message_id = uuid.uuid4()
    payload = _payload(
        identity.agent_definition_version.id, client_message_id=client_message_id
    )

    import asyncio

    responses = await asyncio.gather(
        *[
            client.post(
                _TURNS_PATH.format(conversation_id=conversation_id),
                headers=auth_headers,
                json=payload,
            )
            for _ in range(5)
        ]
    )
    codes = sorted(r.status_code for r in responses)
    # Guard 串行化：要么 201 首次接受，要么 200 幂等重放；不得出现重复首次接受。
    assert codes.count(201) <= 1
    assert all(code in (200, 201) for code in codes)

    messages = await _message_rows(db_session, conversation_id)
    assert len(messages) == 1
    assert len(await _outbox_rows(db_session, conversation_id)) == 1

    message_ids = {r.json()["message_id"] for r in responses}
    assert len(message_ids) == 1


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
