"""Tests for MCPRegistryService + /api/v1/mcp-servers router (REQ-044 Task 2).

Covers spec §4.5 / AC-2 / AC-3:

- RBAC 矩阵：admin / data_admin / super_admin 可 create / update /
  enable / disable / delete；employee / teacher / student 管理操作 403，
  但可 list / get。
- CRUD happy path；code 冲突 409；credential_ref 非法 422；code 非法
  422；transport 非法 422；not found 404。
- enable 翻转 enabled=True 且 updated_at 前进；disable 翻转 False。
- 响应 DTO 不含任何 secret（只有 env key 引用名）；canary env 值不出现在
  响应体中。
- tenant 隔离：他 tenant 不可见 / 不可操作。

Service 层用 ``db_session``，router 层用 ``client`` + ``auth_headers``
（admin = super_admin seed）。uuid-suffixed codes 保证可重跑。
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCP_REGISTRY_ADMIN_ROLES,
    MCPRegistryPermissionError,
    MCPRegistryService,
    MCPServerCodeConflictError,
    MCPServerNotFoundError,
)
from app.contexts.mcp_registry.domain.mcp_server import MCPServer
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

NON_ADMIN_ROLES = ["employee", "teacher", "student"]

# 响应 DTO 的精确字段集 — 防回归：任何疑似 secret 的字段都不允许出现
DTO_KEYS = {
    "id",
    "tenant_id",
    "code",
    "name",
    "description",
    "transport",
    "server_url",
    "credential_ref",
    "allowed_roles",
    "enabled",
    "timeout_ms",
    "created_by",
    "created_at",
    "updated_at",
}


def _unique_code(prefix: str = "svc") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create(
    service: MCPRegistryService,
    *,
    code: str,
    role: str = "super_admin",
    **kwargs: object,
) -> MCPServer:
    return await service.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        name=f"MCP-{code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role=role,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Service: RBAC 矩阵
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(MCP_REGISTRY_ADMIN_ROLES))
async def test_admin_roles_can_create(db_session, role: str):
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("adm"), role=role)
    assert server.tenant_id == DEFAULT_TENANT_ID
    assert server.enabled is False  # 注册后默认停用


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_non_admin_roles_cannot_create(db_session, role: str):
    service = MCPRegistryService(db_session)
    with pytest.raises(MCPRegistryPermissionError):
        await _create(service, code=_unique_code("forb"), role=role)


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_non_admin_roles_cannot_update_enable_disable_delete(
    db_session, role: str
):
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("mgr"))
    with pytest.raises(MCPRegistryPermissionError):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID,
            server_id=server.id,
            role=role,
            name="越权改名",
        )
    with pytest.raises(MCPRegistryPermissionError):
        await service.set_enabled(
            tenant_id=DEFAULT_TENANT_ID,
            server_id=server.id,
            enabled=True,
            role=role,
        )
    with pytest.raises(MCPRegistryPermissionError):
        await service.delete(
            tenant_id=DEFAULT_TENANT_ID, server_id=server.id, role=role
        )


@pytest.mark.parametrize("role", sorted(MCP_REGISTRY_ADMIN_ROLES))
async def test_admin_roles_can_update_enable_disable_delete(db_session, role: str):
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("ops"), role=role)
    updated = await service.update(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        role=role,
        name="改名",
    )
    assert updated.name == "改名"
    enabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        enabled=True,
        role=role,
    )
    assert enabled.enabled is True
    disabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        enabled=False,
        role=role,
    )
    assert disabled.enabled is False
    await service.delete(
        tenant_id=DEFAULT_TENANT_ID, server_id=server.id, role=role
    )
    with pytest.raises(MCPServerNotFoundError):
        await service.get_by_id(DEFAULT_TENANT_ID, server.id)


async def test_all_roles_may_read(db_session):
    """list / get 不做角色门禁（service 层读接口不收 role 参数）。"""
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("read"))
    fetched = await service.get_by_id(DEFAULT_TENANT_ID, server.id)
    assert fetched.code == server.code
    codes = {s.code for s in await service.list_by_tenant(DEFAULT_TENANT_ID)}
    assert server.code in codes


# ---------------------------------------------------------------------------
# Service: CRUD happy path + 校验
# ---------------------------------------------------------------------------


async def test_crud_happy_path(db_session):
    service = MCPRegistryService(db_session)
    code = _unique_code("crud")
    server = await _create(
        service,
        code=code,
        description="企查查",
        transport="sse",
        credential_ref="QCC_MCP_TOKEN",
        allowed_roles=["admin", "data_admin"],
        timeout_ms=15000,
    )
    assert server.transport == "sse"
    assert server.credential_ref == "QCC_MCP_TOKEN"
    assert server.allowed_roles == ["admin", "data_admin"]
    assert server.timeout_ms == 15000
    assert server.is_active is True

    updated = await service.update(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        role="admin",
        name="新名字",
        allowed_roles=["admin"],
        # 不在白名单的字段被忽略
        code="should_not_change",
        enabled=True,
    )
    assert updated.name == "新名字"
    assert updated.allowed_roles == ["admin"]
    assert updated.code == code  # code 不可变
    assert updated.enabled is False  # enabled 只能经 enable/disable 翻转

    await service.delete(
        tenant_id=DEFAULT_TENANT_ID, server_id=server.id, role="admin"
    )
    codes = {s.code for s in await service.list_by_tenant(DEFAULT_TENANT_ID)}
    assert code not in codes


async def test_code_conflict_raises(db_session):
    service = MCPRegistryService(db_session)
    code = _unique_code("cfl")
    await _create(service, code=code)
    with pytest.raises(MCPServerCodeConflictError):
        await _create(service, code=code)


async def test_same_code_allowed_in_other_tenant(db_session):
    service = MCPRegistryService(db_session)
    code = _unique_code("xtenant")
    await _create(service, code=code)
    other = await service.create(
        tenant_id=uuid.uuid4(),
        code=code,
        name="other tenant",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="admin",
    )
    assert other.code == code


async def test_bad_credential_ref_raises_value_error(db_session):
    service = MCPRegistryService(db_session)
    with pytest.raises(ValueError, match="credential_ref"):
        await _create(
            service, code=_unique_code("cred"), credential_ref="qcc-token"
        )


async def test_bad_code_raises_value_error(db_session):
    service = MCPRegistryService(db_session)
    with pytest.raises(ValueError, match="code"):
        await _create(service, code="InvalidCode")


async def test_bad_transport_raises_value_error(db_session):
    service = MCPRegistryService(db_session)
    with pytest.raises(ValueError, match="transport"):
        await _create(service, code=_unique_code("tr"), transport="stdio")


async def test_update_bad_credential_ref_raises(db_session):
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("upc"))
    with pytest.raises(ValueError, match="credential_ref"):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID,
            server_id=server.id,
            role="admin",
            credential_ref="not-an-env-key",
        )


async def test_not_found_raises(db_session):
    service = MCPRegistryService(db_session)
    missing = uuid.uuid4()
    with pytest.raises(MCPServerNotFoundError):
        await service.get_by_id(DEFAULT_TENANT_ID, missing)
    with pytest.raises(MCPServerNotFoundError):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID,
            server_id=missing,
            role="admin",
            name="x",
        )
    with pytest.raises(MCPServerNotFoundError):
        await service.set_enabled(
            tenant_id=DEFAULT_TENANT_ID,
            server_id=missing,
            enabled=True,
            role="admin",
        )
    with pytest.raises(MCPServerNotFoundError):
        await service.delete(
            tenant_id=DEFAULT_TENANT_ID, server_id=missing, role="admin"
        )


async def test_enable_bumps_updated_at(db_session):
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("ena"))
    assert server.enabled is False
    enabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        enabled=True,
        role="admin",
    )
    assert enabled.enabled is True
    assert enabled.updated_at > server.updated_at
    disabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID,
        server_id=server.id,
        enabled=False,
        role="admin",
    )
    assert disabled.enabled is False
    assert disabled.updated_at > enabled.updated_at


async def test_tenant_isolation(db_session):
    """tenant B 看不到 / 改不到 / 删不到 tenant A 的 server。"""
    service = MCPRegistryService(db_session)
    server = await _create(service, code=_unique_code("iso"))
    other_tenant = uuid.uuid4()
    with pytest.raises(MCPServerNotFoundError):
        await service.get_by_id(other_tenant, server.id)
    codes = {s.code for s in await service.list_by_tenant(other_tenant)}
    assert server.code not in codes
    with pytest.raises(MCPServerNotFoundError):
        await service.update(
            tenant_id=other_tenant,
            server_id=server.id,
            role="admin",
            name="越租户",
        )
    with pytest.raises(MCPServerNotFoundError):
        await service.delete(
            tenant_id=other_tenant, server_id=server.id, role="admin"
        )


# ---------------------------------------------------------------------------
# Router: /api/v1/mcp-servers
# ---------------------------------------------------------------------------


async def _register_and_login(
    client: AsyncClient, *, username: str, role: str
) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "Test1234!",
            "email": f"{username}@test.local",
            "role": role,
        },
    )
    assert resp.status_code == 201, f"register failed: {resp.text}"
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Test1234!"},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_payload(code: str) -> dict:
    return {
        "code": code,
        "name": f"企查查-{code}",
        "server_url": "https://mcp.qcc.example.com/rpc",
        "transport": "streamable_http",
        "credential_ref": "QCC_MCP_TOKEN",
        "allowed_roles": ["admin", "data_admin"],
        "timeout_ms": 15000,
    }


async def _create_via_api(
    client: AsyncClient, auth_headers: dict, code: str
) -> dict:
    resp = await client.post(
        "/api/v1/mcp-servers", json=_make_payload(code), headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_api_create_201_admin(client: AsyncClient, auth_headers: dict):
    code = _unique_code("api")
    body = await _create_via_api(client, auth_headers, code)
    assert set(body.keys()) == DTO_KEYS
    assert body["code"] == code
    assert body["credential_ref"] == "QCC_MCP_TOKEN"  # 引用名，不是值
    assert body["allowed_roles"] == ["admin", "data_admin"]
    assert body["enabled"] is False
    assert body["timeout_ms"] == 15000


async def test_api_create_201_data_admin(client: AsyncClient):
    token = await _register_and_login(
        client, username=f"da_{uuid.uuid4().hex[:6]}", role="data_admin"
    )
    resp = await client.post(
        "/api/v1/mcp-servers",
        json=_make_payload(_unique_code("da")),
        headers=_headers(token),
    )
    assert resp.status_code == 201


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_api_create_403_non_admin(client: AsyncClient, role: str):
    token = await _register_and_login(
        client, username=f"{role[:3]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.post(
        "/api/v1/mcp-servers",
        json=_make_payload(_unique_code("forb")),
        headers=_headers(token),
    )
    assert resp.status_code == 403
    assert "无权" in resp.json()["detail"]


async def test_api_create_401_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/v1/mcp-servers", json=_make_payload(_unique_code("noauth"))
    )
    assert resp.status_code == 401


async def test_api_create_409_code_conflict(
    client: AsyncClient, auth_headers: dict
):
    code = _unique_code("cfl")
    await _create_via_api(client, auth_headers, code)
    resp = await client.post(
        "/api/v1/mcp-servers", json=_make_payload(code), headers=auth_headers
    )
    assert resp.status_code == 409
    assert "已存在" in resp.json()["detail"]


async def test_api_create_409_reregister_after_soft_delete(
    client: AsyncClient, auth_headers: dict
):
    """软删后同 code 重新注册 → 409，而不是未处理 500。

    Reviewer Important #1: ``uq_mcp_servers_tenant_code`` 是普通（非部分）
    UNIQUE，服务层预查只看 active 行，所以软删后的 code 会触达 DB 约束。
    router 必须把 ``IntegrityError`` 映射为 409（同时覆盖 check-then-insert
    竞态），不得返回 500 让 code 永久不可复用。
    """
    code = _unique_code("rereg")
    body = await _create_via_api(client, auth_headers, code)
    # 软删
    del_resp = await client.delete(
        f"/api/v1/mcp-servers/{body['id']}", headers=auth_headers
    )
    assert del_resp.status_code in (200, 204), del_resp.text
    # 同 code 重新注册 → 唯一约束冲突 → 409（非 500）
    resp = await client.post(
        "/api/v1/mcp-servers", json=_make_payload(code), headers=auth_headers
    )
    assert resp.status_code == 409, resp.text
    assert "已存在" in resp.json()["detail"]


async def test_api_create_422_bad_credential_ref(
    client: AsyncClient, auth_headers: dict
):
    payload = _make_payload(_unique_code("cred"))
    payload["credential_ref"] = "qcc-token-lowercase"
    resp = await client.post(
        "/api/v1/mcp-servers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422
    assert "credential_ref" in resp.json()["detail"]


async def test_api_create_422_bad_code(client: AsyncClient, auth_headers: dict):
    payload = _make_payload("InvalidCode")
    resp = await client.post(
        "/api/v1/mcp-servers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_api_create_422_bad_transport(
    client: AsyncClient, auth_headers: dict
):
    payload = _make_payload(_unique_code("tr"))
    payload["transport"] = "stdio"
    resp = await client.post(
        "/api/v1/mcp-servers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_api_read_allowed_for_all_roles(
    client: AsyncClient, auth_headers: dict, role: str
):
    """非管理角色可 list / get（只读）。"""
    created = await _create_via_api(client, auth_headers, _unique_code("ro"))
    token = await _register_and_login(
        client, username=f"ro{role[:2]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.get("/api/v1/mcp-servers", headers=_headers(token))
    assert resp.status_code == 200
    assert created["code"] in {s["code"] for s in resp.json()}
    resp = await client.get(
        f"/api/v1/mcp-servers/{created['id']}", headers=_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_api_list_includes_created(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("lst"))
    resp = await client.get("/api/v1/mcp-servers", headers=auth_headers)
    assert resp.status_code == 200
    codes = {s["code"] for s in resp.json()}
    assert created["code"] in codes
    for row in resp.json():
        assert set(row.keys()) == DTO_KEYS


async def test_api_get_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/v1/mcp-servers/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_update_200(client: AsyncClient, auth_headers: dict):
    created = await _create_via_api(client, auth_headers, _unique_code("pat"))
    resp = await client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"name": "改后的名称", "allowed_roles": ["admin"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "改后的名称"
    assert body["allowed_roles"] == ["admin"]
    assert body["code"] == created["code"]


async def test_api_update_422_bad_credential_ref(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("upc"))
    resp = await client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"credential_ref": "bad-ref"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_api_update_404(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/v1/mcp-servers/{uuid.uuid4()}",
        json={"name": "不存在"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_api_update_403_employee(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("p403"))
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"name": "employee 改名"},
        headers=_headers(token),
    )
    assert resp.status_code == 403


async def test_api_enable_disable_flips_flag(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("ena"))
    assert created["enabled"] is False

    # probe=false keeps the test hermetic: with probe=true (default) the
    # enable endpoint would run probe_connectivity, and if a developer
    # has QCC_MCP_TOKEN set in .env for AC-9 manual verification, that
    # probe makes a real HTTP call to the configured server_url.
    resp = await client.post(
        f"/api/v1/mcp-servers/{created['id']}/enable",
        headers=auth_headers,
        params={"probe": "false"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["updated_at"] > created["updated_at"]

    resp = await client.post(
        f"/api/v1/mcp-servers/{created['id']}/disable", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_api_enable_probe_warning_when_credential_missing(
    client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """probe=true on a server whose credential env var is absent:

    enable still succeeds (probe is non-blocking) and the response carries
    a non-empty ``warning`` - the connectivity check was skipped because
    the credential could not be resolved. Hermetic: no network call is
    made (credential resolution short-circuits before list_tools).
    """
    missing_env = "REQ044_PROBE_MISSING_TOKEN"
    monkeypatch.delenv(missing_env, raising=False)
    payload = _make_payload(_unique_code("prb"))
    payload["credential_ref"] = missing_env
    resp = await client.post("/api/v1/mcp-servers", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    server_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/mcp-servers/{server_id}/enable", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True  # probe never blocks enable
    assert body.get("warning"), "missing-credential probe must surface a warning"


async def test_api_enable_404(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/mcp-servers/{uuid.uuid4()}/enable", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_enable_disable_403_employee(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("e403"))
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    for action in ("enable", "disable"):
        resp = await client.post(
            f"/api/v1/mcp-servers/{created['id']}/{action}",
            headers=_headers(token),
        )
        assert resp.status_code == 403


async def test_api_delete_204_then_get_404(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("del"))
    resp = await client.delete(
        f"/api/v1/mcp-servers/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    resp = await client.get(
        f"/api/v1/mcp-servers/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_delete_404(client: AsyncClient, auth_headers: dict):
    resp = await client.delete(
        f"/api/v1/mcp-servers/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_delete_403_employee(
    client: AsyncClient, auth_headers: dict
):
    created = await _create_via_api(client, auth_headers, _unique_code("d403"))
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.delete(
        f"/api/v1/mcp-servers/{created['id']}", headers=_headers(token)
    )
    assert resp.status_code == 403


async def test_api_response_never_contains_secret_value(
    client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """AC-3：即使 env 里有真实值，响应体也只含引用名，绝不含值。"""
    canary = "response-leak-canary-1a2b3c4d"
    monkeypatch.setenv("QCC_MCP_TOKEN", canary)
    created = await _create_via_api(client, auth_headers, _unique_code("sec"))
    assert created["credential_ref"] == "QCC_MCP_TOKEN"

    for resp in (
        await client.get("/api/v1/mcp-servers", headers=auth_headers),
        await client.get(
            f"/api/v1/mcp-servers/{created['id']}", headers=auth_headers
        ),
    ):
        assert resp.status_code == 200
        assert canary not in resp.text
        # 字段名层面也不允许出现 token/secret/value 类字段
        for body in resp.json() if isinstance(resp.json(), list) else [resp.json()]:
            for key in body:
                assert "token" not in key.lower() or key == "credential_ref"
                assert "secret" not in key.lower()
