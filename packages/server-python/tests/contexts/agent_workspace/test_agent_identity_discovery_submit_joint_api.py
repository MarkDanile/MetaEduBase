"""TD-114 契约 §10-B 组：bootstrap → discovery → submit 三真实公开 API 联合测试。

契约：docs/02-delivery-plans/01-specs/2026-10-19-td-114-agent-identity-bootstrap-contract.md
关联：discovery 契约 §8（#655 冻结）、phase-A 公共 submit API 契约（#642 冻结）

本文件是 **B 组独立联合验收**（契约 §10-B），不重复 A 组（#659 实现 PR）与
discovery 后端组（#661 实现 PR）的单端点验收；它只证明三件事在**同一条真实
链路上**成立：

1. B-1：新 tenant 经 ``POST /agent-identity/bootstrap`` 200 → ``GET
   /servable-agent-definitions`` 返回 V1 可服务项 → ``POST /conversations/{id}
   /turns`` 用 discovery 返回的 id 完成真实提交并返回 **201**。
2. B-2：未初始化 tenant 的 discovery 为空且 **GET 零写库**（承接 discovery 契约
   D-19 在「初始化路径已落地」新前提下的复跑）。
3. B-3：bootstrap 重复调用幂等、bootstrap 后重复 discovery 结果一致、submit 201
   后同键同快照重放返回 200。

## 联合测试场景矩阵

| 编号 | 场景 | 断言落点 |
|------|------|----------|
| B-1 | bootstrap 200 → discovery 1 项 → submit 201 | HTTP 响应 + 真实 PG 行 |
| B-1-1 | discovery 返回的 definition id 确实被 submit 接受（跨端点数据流） | submit 201 + receipt |
| B-1-2 | identity 归属：definition.created_by = 认证 actor | 真实 PG 行 |
| B-1-3 | capability digest = V1 冻结快照摘要；profile 与 definition 同 tenant | 真实 PG 行 |
| B-1-4 | server-selected 字段：响应不返回、客户端提交即 422 | HTTP 响应 + PG 无副作用 |
| B-2 | 未初始化 tenant：discovery 空 + GET 零写库 | 真实 PG 行数前后一致 |
| B-3-1 | bootstrap 幂等：两次 200，identity 行数不变、id 不变 | HTTP + 真实 PG 行 |
| B-3-2 | bootstrap 后重复 discovery 结果完全一致 | 两次 HTTP 响应相等 |
| B-3-3 | submit 201 后同键同快照重放 200 + idempotent_replay | HTTP + PG 仍单行 |
| CT-1 | 跨 tenant：A 的 definition id 在 B 提交 → 422 且 B 无副作用 | HTTP + 真实 PG 行 |
| CT-2 | 跨 tenant：B 的 discovery 看不到 A 的项 | HTTP |
| ERR-1 | 未认证 bootstrap / discovery / submit → 401/403 | HTTP |
| ERR-2 | bootstrap 请求体含任何字段（含 tenant_id）→ 422 | HTTP |
| ERR-3 | submit 携带 server-selected 字段 → 422 且无 durable 副作用 | HTTP + PG |

## fixture 边界

- 每个用例自建**独立随机 tenant** + 独立用户，真实 ``/auth/login`` 拿 token；
  无跨用例共享可变状态，失败后可重跑。
- **identity 记录只经生产 bootstrap API 产生**；discovery 返回的 id 是 submit
  的唯一 ``agent_definition_version_id`` 来源。禁止直插 identity 表、禁止伪造
  内部 DTO、禁止用测试 bootstrap 冒充生产路径（契约 §11）。
- 直连数据库仅用于三处：建 tenant 行（仓库无公开 tenant provisioning API）、
  只读断言、清理。**不写生产库、不执行 backfill**（契约 §7 执行授权）。
- 清理按依赖顺序在 ``finally`` 执行：先子表后父表，末删 tenant；``users`` /
  ``agent_runtime_profiles`` / ``agent_definition_versions`` 不在 workspace
  conftest 的清理清单内，故本文件显式按 tenant 维度删除。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
)
from app.contexts.agent_execution.domain import snapshot_digest
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio

_BOOTSTRAP_PATH = "/api/v1/agent-workspace/agent-identity/bootstrap"
_DISCOVERY_PATH = "/api/v1/agent-workspace/servable-agent-definitions"
_CONVERSATIONS_PATH = "/api/v1/agent-workspace/conversations"
_TURNS_PATH = "/api/v1/agent-workspace/conversations/{cid}/turns"

_V1_PROFILE_KEY = "compat.direct_rag.v1"
_V1_DEFINITION_KEY = "system.direct_rag"
_V1_DEFINITION_VERSION = 1
_V1_CAPABILITY_DIGEST = snapshot_digest(DIRECT_RAG_CAPABILITIES)


# --------------------------------------------------------------------------
# fixture 辅助
# --------------------------------------------------------------------------


async def _make_tenant_and_actor(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """建独立 tenant + 真实用户并登录；返回 (tenant_id, actor_id, headers)。

    actor_id 由认证用户行反查——断言 identity 归属时用它与
    ``agent_definition_versions.created_by`` 对照。
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
            "name": f"td114b-{tenant_id.hex[:8]}",
            "school": "TD-114 B",
            "now": now,
        },
    )
    await db_session.commit()
    username = f"td114b_{uuid.uuid4().hex[:12]}"
    token = await register_and_login(
        client,
        username=username,
        role="teacher",
        tenant_id=str(tenant_id),
    )
    actor_id = (
        await db_session.execute(
            text("SELECT id FROM metaedu.users WHERE username = :username"),
            {"username": username},
        )
    ).scalar_one()
    return tenant_id, actor_id, {"Authorization": f"Bearer {token}"}


async def _cleanup_tenant(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """按依赖顺序删除该 tenant 的全部残留行。

    workspace conftest 的清理清单只覆盖 conversation 侧表，不含 users /
    agent_runtime_profiles / agent_definition_versions / tenants，故本文件显式
    按 tenant 维度补齐，避免跨用例累积。
    """
    for statement in (
        "DELETE FROM metaedu.agent_conversation_legal_holds WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_conversation_purge_owners WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_conversation_purges WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_erasure_fences WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_workspace_inbox WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_workspace_outbox WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_message_parts WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_messages WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_conversation_user_state WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_conversations WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_runs WHERE tenant_id = :tid",
        "DELETE FROM metaedu.users WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_definition_versions WHERE tenant_id = :tid",
        "DELETE FROM metaedu.tenants WHERE id = :tid",
    ):
        await db_session.execute(text(statement), {"tid": tenant_id})
    await db_session.commit()


async def _identity_counts(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[int, int]:
    definitions = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_definition_versions "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
    ).scalar_one()
    profiles = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_runtime_profiles "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
    ).scalar_one()
    return definitions, profiles


async def _definition_row(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT id, definition_key, version, status, created_by "
                "FROM metaedu.agent_definition_versions WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
    ).one()
    return {
        "id": str(row[0]),
        "definition_key": row[1],
        "version": row[2],
        "status": row[3],
        "created_by": str(row[4]),
    }


async def _profile_row(db_session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT id, profile_key, runtime_kind, adapter_key, "
                "capability_digest, enabled FROM metaedu.agent_runtime_profiles "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
    ).one()
    return {
        "id": str(row[0]),
        "profile_key": row[1],
        "runtime_kind": row[2],
        "adapter_key": row[3],
        "capability_digest": row[4],
        "enabled": row[5],
    }


async def _message_count(
    db_session: AsyncSession, conversation_id: str
) -> int:
    return (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_messages "
                "WHERE conversation_id = :cid"
            ),
            {"cid": uuid.UUID(conversation_id)},
        )
    ).scalar_one()


async def _outbox_rows(
    db_session: AsyncSession, conversation_id: str
) -> list[dict]:
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


def _submit_payload(
    definition_id: str, *, client_message_id: uuid.UUID | None = None
) -> dict:
    return {
        "client_message_id": str(client_message_id or uuid.uuid4()),
        "parts": [{"type": "text", "text": "hello from TD-114 B", "format": "plain_text"}],
        "agent_definition_version_id": definition_id,
    }


async def _create_conversation(
    client: AsyncClient, headers: dict[str, str], *, title: str
) -> str:
    resp = await client.post(
        _CONVERSATIONS_PATH, headers=headers, json={"title": title}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------------------------------------------------------------------------
# B-1 成功路径：bootstrap → discovery → submit 201
# --------------------------------------------------------------------------


async def test_b1_bootstrap_then_discovery_then_submit_returns_201(
    client: AsyncClient, db_session
):
    """B-1：新 tenant 三真实公开 API 串联，全链真实 PostgreSQL。

    断言落点：公开 HTTP 响应 + 真实 PG 行。这是 B 组主验收用例。
    """
    tenant_id, actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        # --- 步骤 1：bootstrap（真实公开 API）---
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # 契约 §2：恰两字段。
        assert body == {"initialized": True, "disabled_existing": False}

        # --- 步骤 2：discovery（真实公开 API）---
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1, items
        item = items[0]
        assert set(item.keys()) == {"id", "definition_key", "version"}
        assert item["definition_key"] == _V1_DEFINITION_KEY
        assert item["version"] == _V1_DEFINITION_VERSION
        definition_id = item["id"]

        # --- 步骤 3：submit，用 discovery 返回的 id（不硬编码、不直查库）---
        conversation_id = await _create_conversation(
            client, headers, title="TD-114 B joint"
        )
        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_id),
            headers=headers,
            json=_submit_payload(definition_id),
        )
        assert resp.status_code == 201, resp.text
        receipt = resp.json()
        for field in (
            "message_id",
            "message_seq",
            "run_id",
            "run_queue_seq",
            "dispatch_state",
            "idempotent_replay",
            "correlation_id",
            "created_at",
        ):
            assert field in receipt, f"missing receipt field {field}: {receipt}"
        assert receipt["dispatch_state"] == "pending"
        assert receipt["idempotent_replay"] is False

        # --- 真实 PG 状态断言：durable 原子边界 ---
        assert await _message_count(db_session, conversation_id) == 1
        outbox = await _outbox_rows(db_session, conversation_id)
        assert len(outbox) == 1, outbox
        assert outbox[0]["event_type"] == "turn.requested.v1"
        # outbox 的聚合根是 Message（phase-A §8 durable 原子边界）：
        # 聚合 id 恰为 receipt 返回的 message_id，证明 receipt 与真实落库行同源。
        assert outbox[0]["aggregate_id"] == receipt["message_id"]
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_b1_discovery_id_is_accepted_by_submit(
    client: AsyncClient, db_session
):
    """B-1-1：discovery 返回的记录确实能被 submit 接受（跨端点数据流）。

    反例对照：同一 tenant 下**未**经 discovery 取得来源的随机 id 必须被
    422 拒绝——证明 submit 不是「接受任意 definition id」，而是接受
    discovery 真实返回的那一条。
    """
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        discovered_id = items[0]["id"]

        conversation_id = await _create_conversation(
            client, headers, title="TD-114 B dataflow"
        )

        # 反例：非 discovery 来源的 id（该 tenant 确无此行）→ 422
        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_id),
            headers=headers,
            json=_submit_payload(str(uuid.uuid4())),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "validation_error"
        assert await _message_count(db_session, conversation_id) == 0
        assert await _outbox_rows(db_session, conversation_id) == []

        # 正例：discovery 返回的 id → 201
        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_id),
            headers=headers,
            json=_submit_payload(discovered_id),
        )
        assert resp.status_code == 201, resp.text
        assert await _message_count(db_session, conversation_id) == 1
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_b1_identity_attribution_and_capability_digest(
    client: AsyncClient, db_session
):
    """B-1-2 + B-1-3：identity 归属与 definition/profile 关联 + capability digest。

    - definition.created_by = **认证派生的真实 actor**（契约 §8）；
    - profile 与 definition 同 tenant 且 profile_key 为 V1 冻结键；
    - profile.capability_digest = V1 冻结 capability 快照摘要（discovery §3-5
      与 submit 期判定同源，digest 不符则两端都判不可服务）。
    """
    tenant_id, actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text

        assert await _identity_counts(db_session, tenant_id) == (1, 1)

        definition = await _definition_row(db_session, tenant_id)
        assert definition["definition_key"] == _V1_DEFINITION_KEY
        assert definition["version"] == _V1_DEFINITION_VERSION
        assert definition["status"] == "published"
        # 审计真实：created_by 就是发起 bootstrap 的认证 actor。
        assert definition["created_by"] == str(actor_id)

        profile = await _profile_row(db_session, tenant_id)
        assert profile["profile_key"] == _V1_PROFILE_KEY
        assert profile["runtime_kind"] == "compatibility"
        assert profile["adapter_key"] == "direct_rag"
        assert profile["enabled"] is True
        assert profile["capability_digest"] == _V1_CAPABILITY_DIGEST

        # discovery 与 submit 共用同一份 identity 事实：返回的 id 即该行 id。
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.json()["items"][0]["id"] == definition["id"]
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_b1_server_selected_fields_absent_from_responses_and_rejected(
    client: AsyncClient, db_session
):
    """B-1-4：server-selected 字段双向边界。

    - 读面：discovery 与 submit 响应都不得携带 server-selected launch 输入；
    - 写面：客户端提交 server-selected 字段一律 422 且无 durable 副作用
      （phase-A §3/§4）。
    """
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        definition_id = resp.json()["items"][0]["id"]
        for forbidden in (
            "runtime_profile_id",
            "runtime_binding_id",
            "capability_digest",
            "capability_snapshot",
            "budget",
            "revision",
            "config_digest",
        ):
            assert forbidden not in resp.text, forbidden

        conversation_id = await _create_conversation(
            client, headers, title="TD-114 B server-selected"
        )
        payload = _submit_payload(definition_id)
        payload["runtime_profile_id"] = str(uuid.uuid4())
        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_id),
            headers=headers,
            json=payload,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "validation_error"
        assert await _message_count(db_session, conversation_id) == 0
        assert await _outbox_rows(db_session, conversation_id) == []
    finally:
        await _cleanup_tenant(db_session, tenant_id)


# --------------------------------------------------------------------------
# B-2 未初始化 tenant：discovery 空 + GET 零写库
# --------------------------------------------------------------------------


async def test_b2_uninitialized_tenant_discovery_empty_and_zero_writes(
    client: AsyncClient, db_session
):
    """B-2：初始化前 discovery 为空，且 GET 前后 identity 两表行数不变。

    承接 discovery 契约 D-19 在「初始化路径已落地」新前提下的复跑：空列表
    仍只表示「当前无可服务项」，**不得**被解读为「未初始化」；GET 仍零写库。
    """
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        before = await _identity_counts(db_session, tenant_id)
        assert before == (0, 0)

        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": []}

        assert await _identity_counts(db_session, tenant_id) == before
    finally:
        await _cleanup_tenant(db_session, tenant_id)


# --------------------------------------------------------------------------
# B-3 幂等：bootstrap 重复 / discovery 重复 / submit 同键重放
# --------------------------------------------------------------------------


async def test_b3_bootstrap_is_idempotent(client: AsyncClient, db_session):
    """B-3-1：重复 bootstrap 返回 200，identity 行数与 id 不变（幂等）。"""
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        first = await _definition_row(db_session, tenant_id)
        assert await _identity_counts(db_session, tenant_id) == (1, 1)

        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"initialized": True, "disabled_existing": False}

        assert await _identity_counts(db_session, tenant_id) == (1, 1)
        assert await _definition_row(db_session, tenant_id) == first
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_b3_repeated_discovery_is_consistent(client: AsyncClient, db_session):
    """B-3-2：bootstrap 后重复 discovery 结果完全一致。"""
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text

        first = await client.get(_DISCOVERY_PATH, headers=headers)
        assert first.status_code == 200, first.text
        second = await client.get(_DISCOVERY_PATH, headers=headers)
        assert second.status_code == 200, second.text
        assert first.json() == second.json()
        assert len(first.json()["items"]) == 1
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_b3_submit_replay_same_key_returns_200(client: AsyncClient, db_session):
    """B-3-3：submit 201 后同键同快照重放 → 200 + idempotent_replay。

    durable 侧仍只 1 条 Message + 1 条 outbox——重放不产生新行（phase-A §5）。
    """
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        definition_id = resp.json()["items"][0]["id"]

        conversation_id = await _create_conversation(
            client, headers, title="TD-114 B replay"
        )
        key = uuid.uuid4()
        payload = _submit_payload(definition_id, client_message_id=key)

        first = await client.post(
            _TURNS_PATH.format(cid=conversation_id), headers=headers, json=payload
        )
        assert first.status_code == 201, first.text
        assert first.json()["idempotent_replay"] is False

        second = await client.post(
            _TURNS_PATH.format(cid=conversation_id), headers=headers, json=payload
        )
        assert second.status_code == 200, second.text
        replay = second.json()
        assert replay["idempotent_replay"] is True
        # 重放返回原 receipt。
        assert replay["message_id"] == first.json()["message_id"]
        assert replay["run_id"] == first.json()["run_id"]

        assert await _message_count(db_session, conversation_id) == 1
        outbox = await _outbox_rows(db_session, conversation_id)
        assert len(outbox) == 1, outbox
    finally:
        await _cleanup_tenant(db_session, tenant_id)


# --------------------------------------------------------------------------
# 跨 tenant 拒绝
# --------------------------------------------------------------------------


async def test_ct1_other_tenant_definition_id_is_rejected(
    client: AsyncClient, db_session
):
    """CT-1：tenant A 的 definition id 在 tenant B 提交 → 422 且 B 无副作用。"""
    tenant_a, _actor_a, headers_a = await _make_tenant_and_actor(client, db_session)
    tenant_b, _actor_b, headers_b = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers_a)
        assert resp.status_code == 200, resp.text
        resp = await client.get(_DISCOVERY_PATH, headers=headers_a)
        definition_id_a = resp.json()["items"][0]["id"]

        conversation_b = await _create_conversation(
            client, headers_b, title="TD-114 B cross tenant"
        )
        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_b),
            headers=headers_b,
            json=_submit_payload(definition_id_a),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "validation_error"
        assert await _message_count(db_session, conversation_b) == 0
        assert await _outbox_rows(db_session, conversation_b) == []

        # A 的 identity 不受影响。
        assert await _identity_counts(db_session, tenant_a) == (1, 1)
        assert await _identity_counts(db_session, tenant_b) == (0, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_a)
        await _cleanup_tenant(db_session, tenant_b)


async def test_ct2_discovery_does_not_leak_across_tenants(
    client: AsyncClient, db_session
):
    """CT-2：tenant B 的 discovery 看不到 tenant A 的项。"""
    tenant_a, _actor_a, headers_a = await _make_tenant_and_actor(client, db_session)
    tenant_b, _actor_b, headers_b = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers_a)
        assert resp.status_code == 200, resp.text

        resp = await client.get(_DISCOVERY_PATH, headers=headers_a)
        assert len(resp.json()["items"]) == 1

        resp = await client.get(_DISCOVERY_PATH, headers=headers_b)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": []}
    finally:
        await _cleanup_tenant(db_session, tenant_a)
        await _cleanup_tenant(db_session, tenant_b)


# --------------------------------------------------------------------------
# 错误状态
# --------------------------------------------------------------------------


async def test_err1_unauthenticated_endpoints_rejected(client: AsyncClient):
    """ERR-1：未认证访问 bootstrap / discovery → 401/403。"""
    for method, path in (
        ("post", _BOOTSTRAP_PATH),
        ("get", _DISCOVERY_PATH),
    ):
        resp = await getattr(client, method)(path)
        assert resp.status_code in (401, 403), (path, resp.status_code, resp.text)


async def test_err2_bootstrap_rejects_non_empty_body(client: AsyncClient, db_session):
    """ERR-2：请求体出现任何字段（含 tenant_id）→ 422（不信任客户端传 tenant）。"""
    tenant_id, _actor_id, headers = await _make_tenant_and_actor(client, db_session)
    try:
        resp = await client.post(
            _BOOTSTRAP_PATH, headers=headers, json={"tenant_id": str(tenant_id)}
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "validation_error"
        # 拒绝路径零写入。
        assert await _identity_counts(db_session, tenant_id) == (0, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_id)
