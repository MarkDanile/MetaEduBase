"""REQ-042 WS-S2 definition discovery 端点的真实 PostgreSQL contract tests。

契约验收归属（#655 §8 跨切片矩阵中标注「后端真实 PG contract tests」的行）：

- D-1 未认证 401/403；他 tenant 数据不可见
- D-2 无任何注册时返回 ``{"items": []}``（200 非错误）
- D-3 draft/retired definition 不出现
- D-4 profile 缺失或 ``enabled=false`` 时不出现
- D-5 profile 身份（runtime_kind/adapter_key）不符 V1 时不出现
- D-17 后端部分：共享 profile digest 缺陷 → 200 + 空列表 + 按缺陷去重单条
  warning（2 个 published definition 也只一条 warning）
- D-7 响应项恰三字段、无 server-selected launch 字段
- D-8 GET 前后两表行数不变（无隐式写）
- D-9 多 definition 按 (definition_key, version) 升序全返回
- D-10 TOCTOU：发现含该项后 profile 置 disabled，提交仍 403 capability_denied
- D-19 新 tenant 零初始化：空列表且 GET 零写库

测试直验 HTTP 响应与数据库最终状态；真实 PostgreSQL；不 mock repository。
初始化一律经生产 bootstrap API（``POST /agent-identity/bootstrap``），
不用测试 fixture 冒充生产路径。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio

_DISCOVERY_PATH = "/api/v1/agent-workspace/servable-agent-definitions"
_BOOTSTRAP_PATH = "/api/v1/agent-workspace/agent-identity/bootstrap"
_TURNS_PATH = "/api/v1/agent-workspace/conversations/{cid}/turns"
_CONVERSATIONS_PATH = "/api/v1/agent-workspace/conversations"


async def _make_tenant_and_headers(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[uuid.UUID, dict[str, str]]:
    tenant_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school, 'shared', true, :now, :now)"
        ),
        {"id": tenant_id, "name": f"disc-{tenant_id.hex[:8]}", "school": "discovery", "now": now},
    )
    await db_session.commit()
    token = await register_and_login(
        client,
        username=f"disc_{uuid.uuid4().hex[:12]}",
        role="teacher",
        tenant_id=str(tenant_id),
    )
    return tenant_id, {"Authorization": f"Bearer {token}"}


async def _cleanup_tenant(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
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


async def _identity_counts(db_session: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, int]:
    definitions = (
        await db_session.execute(
            text("SELECT count(*) FROM metaedu.agent_definition_versions WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    profiles = (
        await db_session.execute(
            text("SELECT count(*) FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    return definitions, profiles


async def _bootstrap(client: AsyncClient, headers: dict[str, str]) -> None:
    """经生产 bootstrap API 初始化 tenant V1 identity（TD-114 已合并路径）。"""
    resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"initialized": True, "disabled_existing": False}


async def _seed_definition(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    definition_key: str,
    version: int,
    status: str,
) -> uuid.UUID:
    """直接 INSERT 构造 definition 状态（publish 恒写 published，无 draft 写入路径）。"""
    definition_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, "
            " definition_digest, created_by, created_at) "
            "VALUES (:id, :tid, :key, :ver, :status, :digest, :actor, :now)"
        ),
        {
            "id": definition_id,
            "tid": tenant_id,
            "key": definition_key,
            "ver": version,
            "status": status,
            "digest": "a" * 64,
            "actor": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )
    await db_session.commit()
    return definition_id


async def test_unauthenticated_returns_401(client: AsyncClient):
    resp = await client.get(_DISCOVERY_PATH)
    assert resp.status_code in (401, 403)


async def test_uninitialized_tenant_returns_empty_and_writes_nothing(
    client: AsyncClient, db_session
):
    """D-2 + D-19：零初始化 tenant → 200 + 空列表；GET 零写库。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        before = await _identity_counts(db_session, tenant_id)
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"items": []}
        assert await _identity_counts(db_session, tenant_id) == before == (0, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_servable_definition_discovered(client: AsyncClient, db_session):
    """D-7：初始化后返回 V1 项；每项恰三字段、无 server-selected launch 字段。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert set(item.keys()) == {"id", "definition_key", "version"}
        assert item["definition_key"] == "system.direct_rag"
        assert item["version"] == 1
        for forbidden in (
            "runtime_profile_id",
            "runtime_binding_id",
            "capability_digest",
            "capability_snapshot",
            "budget",
            "revision",
            "config_digest",
        ):
            assert forbidden not in item
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_tenant_isolation(client: AsyncClient, db_session):
    """D-1：tenant B 已初始化，tenant A 未初始化时 A 仍为空；互不可见。"""
    tenant_a, headers_a = await _make_tenant_and_headers(client, db_session)
    tenant_b, headers_b = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers_b)
        resp = await client.get(_DISCOVERY_PATH, headers=headers_a)
        assert resp.json() == {"items": []}
        resp = await client.get(_DISCOVERY_PATH, headers=headers_b)
        assert len(resp.json()["items"]) == 1
    finally:
        await _cleanup_tenant(db_session, tenant_a)
        await _cleanup_tenant(db_session, tenant_b)


async def test_draft_and_retired_definitions_excluded(client: AsyncClient, db_session):
    """D-3：draft/retired definition 不出现；published 正常出现。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        await _seed_definition(
            db_session,
            tenant_id,
            definition_key="custom.draft",
            version=1,
            status="draft",
        )
        await _seed_definition(
            db_session,
            tenant_id,
            definition_key="custom.retired",
            version=1,
            status="retired",
        )
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        keys = [item["definition_key"] for item in resp.json()["items"]]
        assert keys == ["system.direct_rag"]
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_disabled_profile_returns_empty(client: AsyncClient, db_session):
    """D-4：profile disabled → 空列表。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_runtime_profiles SET enabled = false WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        await db_session.commit()
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"items": []}
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_profile_identity_mismatch_returns_empty(client: AsyncClient, db_session):
    """D-5：profile 身份不符 V1（runtime_kind 不符）→ 空列表。

    身份字段受 immutability trigger 保护，无法 UPDATE 已存在行；
    故以独立 tenant 直接 INSERT 一行身份不符的 profile（不经 bootstrap）。
    """
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db_session.execute(
            text(
                "INSERT INTO metaedu.agent_definition_versions "
                "(id, tenant_id, definition_key, version, status, "
                " definition_digest, created_by, created_at) "
                "VALUES (:id, :tid, 'system.direct_rag', 1, 'published', "
                "        :digest, :actor, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "digest": "a" * 64,
                "actor": DEFAULT_ADMIN_ID,
                "now": now,
            },
        )
        await db_session.execute(
            text(
                "INSERT INTO metaedu.agent_runtime_profiles "
                "(id, tenant_id, profile_key, runtime_kind, adapter_key, "
                " config_digest, capability_digest, enabled, revision, "
                " created_at, updated_at) "
                "VALUES (:id, :tid, 'compat.direct_rag.v1', 'pi', 'pi-sdk', "
                "        :cd, :pd, true, 1, :now, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "cd": "b" * 64,
                "pd": "c" * 64,
                "now": now,
            },
        )
        await db_session.commit()
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.json() == {"items": []}
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_shared_profile_digest_defect_returns_empty_with_single_warning(
    client: AsyncClient, db_session, caplog
):
    """D-17 后端部分：digest 缺陷 → 200 + 空列表 + 按缺陷去重单条 warning。

    2 个 published definition 共享同一缺陷 profile，warning 只发一条
    （不按 definition 重复刷）。
    """
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        # 两个 published definition 共享同一缺陷 profile
        for key in ("system.direct_rag", "custom.other"):
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_definition_versions "
                    "(id, tenant_id, definition_key, version, status, "
                    " definition_digest, created_by, created_at) "
                    "VALUES (:id, :tid, :key, 1, 'published', :digest, :actor, :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "key": key,
                    "digest": "a" * 64,
                    "actor": DEFAULT_ADMIN_ID,
                    "now": now,
                },
            )
        # digest 缺陷 profile（capability_digest 与 V1 冻结值不符）
        await db_session.execute(
            text(
                "INSERT INTO metaedu.agent_runtime_profiles "
                "(id, tenant_id, profile_key, runtime_kind, adapter_key, "
                " config_digest, capability_digest, enabled, revision, "
                " created_at, updated_at) "
                "VALUES (:id, :tid, 'compat.direct_rag.v1', 'compatibility', "
                "        'direct_rag', :cd, :pd, true, 1, :now, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "cd": "b" * 64,
                "pd": "f" * 64,
                "now": now,
            },
        )
        await db_session.commit()

        with caplog.at_level(logging.WARNING, logger="app.composition.servable_definition_catalog"):
            resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"items": []}
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and str(tenant_id) in r.getMessage()
        ]
        assert len(warnings) == 1, f"expected exactly 1 deduped warning, got {len(warnings)}"
        assert "compat.direct_rag.v1" in warnings[0].getMessage()
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_multiple_definitions_sorted_by_key_and_version(client: AsyncClient, db_session):
    """D-9：多 definition 按 (definition_key, version) 升序全返回。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        await _seed_definition(
            db_session,
            tenant_id,
            definition_key="custom.zeta",
            version=2,
            status="published",
        )
        await _seed_definition(
            db_session,
            tenant_id,
            definition_key="custom.alpha",
            version=1,
            status="published",
        )
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        keys = [(i["definition_key"], i["version"]) for i in resp.json()["items"]]
        assert keys == sorted(keys)
        assert len(keys) == 3
        assert ("system.direct_rag", 1) in keys
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_get_writes_nothing_with_initialized_tenant(client: AsyncClient, db_session):
    """D-8：已初始化 tenant 的 GET 前后两表行数不变（无隐式写）。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        before = await _identity_counts(db_session, tenant_id)
        assert before == (1, 1)
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert await _identity_counts(db_session, tenant_id) == before
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_discovery_does_not_substitute_submit_time_check(client: AsyncClient, db_session):
    """D-10：TOCTOU——发现含该项后 profile 置 disabled，提交仍 403。

    服务端拒绝语义（后端部分）；浏览器端到端复核归 phase-E。
    """
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await _bootstrap(client, headers)
        resp = await client.get(_DISCOVERY_PATH, headers=headers)
        items = resp.json()["items"]
        assert len(items) == 1
        definition_id = items[0]["id"]

        # 建会话（提交前提）
        resp = await client.post(_CONVERSATIONS_PATH, headers=headers, json={"title": "D-10"})
        assert resp.status_code == 201, resp.text
        conversation_id = resp.json()["id"]

        # 发现后、提交前把 profile 置 disabled
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_runtime_profiles SET enabled = false WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        await db_session.commit()

        resp = await client.post(
            _TURNS_PATH.format(cid=conversation_id),
            headers=headers,
            json={
                "client_message_id": str(uuid.uuid4()),
                "parts": [{"type": "text", "text": "hi", "format": "plain_text"}],
                "agent_definition_version_id": definition_id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "capability_denied"
    finally:
        await _cleanup_tenant(db_session, tenant_id)
