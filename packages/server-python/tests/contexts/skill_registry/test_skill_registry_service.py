"""Tests for SkillRegistryService + /api/v1/skills router (REQ-045 Task 2).

Covers spec §4.5 (first 7 endpoints) / AC-2 / AC-3 / AC-7 / AC-11:

- RBAC 矩阵：admin / data_admin / super_admin 可 create / update /
  enable / disable / delete；employee / teacher / student 管理操作 403，
  但可 list / get。
- CRUD + 版本全流程：同 code 多版本并存、list_versions、
  get_by_code_version；`(code, version)` 冲突 409（含软删后同
  code+version 重注册 409，不 500）。
- SOP 模板校验编排：缺步骤 / 引用未注册 server 各 422；PATCH 改
  sop_template 被拒 422；code / version 格式非法 422。
- tenant 隔离：tenant A 的 skill 对 tenant B 不可见 / 不可操作。

Service 层用 ``db_session``，router 层用 ``client`` + ``auth_headers``
（admin = super_admin seed）。步骤引用的 server 校验需要先在 test DB
注册对应 ``mcp_servers`` 行（经 ``MCPRegistryService``）。uuid-suffixed
codes 保证可重跑。
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SKILL_REGISTRY_ADMIN_ROLES,
    SkillNotFoundError,
    SkillRegistryPermissionError,
    SkillRegistryService,
    SkillVersionConflictError,
)
from app.contexts.skill_registry.domain.skill import Skill, SopTemplateError
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

NON_ADMIN_ROLES = ["employee", "teacher", "student"]

# 响应 DTO 的精确字段集 — 防回归：不允许出现任何疑似 secret 的字段
DTO_KEYS = {
    "id",
    "tenant_id",
    "code",
    "version",
    "name",
    "description",
    "sop_template",
    "source_ref",
    "allowed_roles",
    "enabled",
    "created_by",
    "created_at",
    "updated_at",
}


def _unique_code(prefix: str = "skl") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _sop_template(server_code: str) -> str:
    """合法 SOP 模板：引用一个已注册的 MCP server。"""
    return f"""name: enterprise-360-dd
description: 企业 360 背调 SOP
mcp_dependencies:
  - {{server: {server_code}, required: true}}
principles:
  - 缺失数据显式标注，不编造默认值
steps:
  - id: subject_verify
    title: 主体工商核验
    server: {server_code}
    tool: get_company_registration_info
    analysis_rules:
      - 工商二要素不一致即标记高风险
    output: 主体身份档案
report_template: |
  ## 事实数据
  ## AI 分析
  ## 待人工确认项
"""


async def _register_mcp_server(db_session, code: str) -> None:
    """在 test DB 注册一个 MCP server，供 SOP 步骤引用校验通过。"""
    await MCPRegistryService(db_session).create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        name=f"MCP-{code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )


async def _create(
    service: SkillRegistryService,
    *,
    code: str,
    version: str = "1.0.0",
    role: str = "super_admin",
    **kwargs: object,
) -> Skill:
    return await service.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        version=version,
        name=kwargs.pop("name", f"Skill-{code}"),
        sop_template=kwargs.pop("sop_template"),
        created_by=DEFAULT_ADMIN_ID,
        role=role,
        **kwargs,
    )


@pytest.fixture
async def server_code(db_session) -> str:
    code = _unique_code("srv")
    await _register_mcp_server(db_session, code)
    return code


# ---------------------------------------------------------------------------
# Service: RBAC 矩阵
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(SKILL_REGISTRY_ADMIN_ROLES))
async def test_admin_roles_can_create(db_session, server_code: str, role: str):
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("adm"), sop_template=_sop_template(server_code),
        role=role,
    )
    assert skill.tenant_id == DEFAULT_TENANT_ID
    assert skill.enabled is False  # 注册后默认停用


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_non_admin_roles_cannot_create(db_session, server_code: str, role: str):
    service = SkillRegistryService(db_session)
    with pytest.raises(SkillRegistryPermissionError):
        await _create(
            service, code=_unique_code("forb"),
            sop_template=_sop_template(server_code), role=role,
        )


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_non_admin_roles_cannot_update_enable_disable_delete(
    db_session, server_code: str, role: str
):
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("mgr"), sop_template=_sop_template(server_code)
    )
    with pytest.raises(SkillRegistryPermissionError):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, role=role, name="越权"
        )
    with pytest.raises(SkillRegistryPermissionError):
        await service.set_enabled(
            tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, enabled=True, role=role
        )
    with pytest.raises(SkillRegistryPermissionError):
        await service.delete(
            tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, role=role
        )


@pytest.mark.parametrize("role", sorted(SKILL_REGISTRY_ADMIN_ROLES))
async def test_admin_roles_can_update_enable_disable_delete(
    db_session, server_code: str, role: str
):
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("ops"), sop_template=_sop_template(server_code),
        role=role,
    )
    updated = await service.update(
        tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, role=role, name="改名"
    )
    assert updated.name == "改名"
    enabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, enabled=True, role=role
    )
    assert enabled.enabled is True
    disabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, enabled=False, role=role
    )
    assert disabled.enabled is False
    await service.delete(tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, role=role)
    with pytest.raises(SkillNotFoundError):
        await service.get_by_id(DEFAULT_TENANT_ID, skill.id)


async def test_all_roles_may_read(db_session, server_code: str):
    """list / get 不做角色门禁（service 层读接口不收 role 参数）。"""
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("read"), sop_template=_sop_template(server_code)
    )
    fetched = await service.get_by_id(DEFAULT_TENANT_ID, skill.id)
    assert fetched.code == skill.code
    codes = {s.code for s in await service.list_by_tenant(DEFAULT_TENANT_ID)}
    assert skill.code in codes


# ---------------------------------------------------------------------------
# Service: CRUD + 版本全流程
# ---------------------------------------------------------------------------


async def test_crud_happy_path(db_session, server_code: str):
    service = SkillRegistryService(db_session)
    code = _unique_code("crud")
    skill = await _create(
        service,
        code=code,
        sop_template=_sop_template(server_code),
        description="企业 360 背调",
        source_ref="https://agent.qcc.com/skills/1",
        allowed_roles=["admin", "data_admin"],
    )
    assert skill.version == "1.0.0"
    assert skill.allowed_roles == ["admin", "data_admin"]
    assert skill.is_active is True
    assert skill.enabled is False

    updated = await service.update(
        tenant_id=DEFAULT_TENANT_ID,
        skill_id=skill.id,
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

    await service.delete(tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, role="admin")
    codes = {s.code for s in await service.list_by_tenant(DEFAULT_TENANT_ID)}
    assert code not in codes


async def test_multiple_versions_coexist(db_session, server_code: str):
    """AC-11：同 code 多版本并存，list_versions / get_by_code_version 可用。"""
    service = SkillRegistryService(db_session)
    code = _unique_code("ver")
    v1 = await _create(
        service, code=code, version="1.0.0",
        sop_template=_sop_template(server_code),
    )
    v2 = await _create(
        service, code=code, version="1.1.0",
        sop_template=_sop_template(server_code), name="v2",
    )
    assert v1.id != v2.id

    versions = await service.list_versions(DEFAULT_TENANT_ID, code)
    assert [s.version for s in versions] == ["1.0.0", "1.1.0"]

    fetched = await service.get_by_code_version(DEFAULT_TENANT_ID, code, "1.1.0")
    assert fetched.id == v2.id
    assert fetched.name == "v2"

    # 版本可独立启停
    enabled = await service.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, skill_id=v2.id, enabled=True, role="admin"
    )
    assert enabled.enabled is True
    still_disabled = await service.get_by_id(DEFAULT_TENANT_ID, v1.id)
    assert still_disabled.enabled is False


async def test_code_version_conflict_raises(db_session, server_code: str):
    service = SkillRegistryService(db_session)
    code = _unique_code("cfl")
    await _create(service, code=code, sop_template=_sop_template(server_code))
    with pytest.raises(SkillVersionConflictError):
        await _create(service, code=code, sop_template=_sop_template(server_code))


async def test_same_code_version_allowed_in_other_tenant(
    db_session, server_code: str
):
    service = SkillRegistryService(db_session)
    code = _unique_code("xtenant")
    await _create(service, code=code, sop_template=_sop_template(server_code))
    # 引用闭合校验是 tenant 级的：他 tenant 也需注册同名 server 才能建 skill
    other_tenant = uuid.uuid4()
    await MCPRegistryService(db_session).create(
        tenant_id=other_tenant,
        code=server_code,
        name=f"MCP-{server_code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    other = await service.create(
        tenant_id=other_tenant,
        code=code,
        version="1.0.0",
        name="other tenant",
        sop_template=_sop_template(server_code),
        created_by=DEFAULT_ADMIN_ID,
        role="admin",
    )
    assert other.code == code


# ---------------------------------------------------------------------------
# Service: 模板校验编排 + 格式校验
# ---------------------------------------------------------------------------


async def test_create_rejects_template_without_steps(db_session):
    """缺步骤的模板 -> SopTemplateError（router 映射 422）。"""
    service = SkillRegistryService(db_session)
    bad_template = "name: enterprise-360-dd\ndescription: 缺步骤\nsteps: []\n"
    with pytest.raises(SopTemplateError):
        await _create(
            service, code=_unique_code("bad"), sop_template=bad_template
        )


async def test_create_rejects_unregistered_server(db_session):
    """步骤引用未注册 server -> ValueError 指明哪个 server（router 422）。"""
    service = SkillRegistryService(db_session)
    ghost = _unique_code("ghost")
    with pytest.raises(ValueError, match=ghost):
        await _create(
            service,
            code=_unique_code("unreg"),
            sop_template=_sop_template(ghost),
        )


async def test_bad_code_raises_value_error(db_session, server_code: str):
    service = SkillRegistryService(db_session)
    with pytest.raises(ValueError, match="code"):
        await _create(
            service, code="InvalidCode", sop_template=_sop_template(server_code)
        )


@pytest.mark.parametrize("bad_version", ["1.0", "v1.0.0", "1.0.0-beta", "abc"])
async def test_bad_version_raises_value_error(
    db_session, server_code: str, bad_version: str
):
    service = SkillRegistryService(db_session)
    with pytest.raises(ValueError, match="version"):
        await _create(
            service,
            code=_unique_code("ver"),
            version=bad_version,
            sop_template=_sop_template(server_code),
        )


async def test_update_rejects_sop_template_change(db_session, server_code: str):
    """sop_template 改动须走新版本 — PATCH 显式拒绝。"""
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("pat"), sop_template=_sop_template(server_code)
    )
    with pytest.raises(ValueError, match="sop_template"):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID,
            skill_id=skill.id,
            role="admin",
            sop_template=_sop_template(server_code),
        )


async def test_not_found_raises(db_session):
    service = SkillRegistryService(db_session)
    missing = uuid.uuid4()
    with pytest.raises(SkillNotFoundError):
        await service.get_by_id(DEFAULT_TENANT_ID, missing)
    with pytest.raises(SkillNotFoundError):
        await service.get_by_code_version(DEFAULT_TENANT_ID, "no_such", "1.0.0")
    with pytest.raises(SkillNotFoundError):
        await service.update(
            tenant_id=DEFAULT_TENANT_ID, skill_id=missing, role="admin", name="x"
        )
    with pytest.raises(SkillNotFoundError):
        await service.set_enabled(
            tenant_id=DEFAULT_TENANT_ID, skill_id=missing, enabled=True, role="admin"
        )
    with pytest.raises(SkillNotFoundError):
        await service.delete(tenant_id=DEFAULT_TENANT_ID, skill_id=missing, role="admin")


async def test_tenant_isolation(db_session, server_code: str):
    """AC-7：tenant B 看不到 / 改不到 / 删不到 tenant A 的 skill。"""
    service = SkillRegistryService(db_session)
    skill = await _create(
        service, code=_unique_code("iso"), sop_template=_sop_template(server_code)
    )
    other_tenant = uuid.uuid4()
    with pytest.raises(SkillNotFoundError):
        await service.get_by_id(other_tenant, skill.id)
    with pytest.raises(SkillNotFoundError):
        await service.get_by_code_version(other_tenant, skill.code, "1.0.0")
    codes = {s.code for s in await service.list_by_tenant(other_tenant)}
    assert skill.code not in codes
    assert await service.list_versions(other_tenant, skill.code) == []
    with pytest.raises(SkillNotFoundError):
        await service.update(
            tenant_id=other_tenant, skill_id=skill.id, role="admin", name="越租户"
        )
    with pytest.raises(SkillNotFoundError):
        await service.delete(tenant_id=other_tenant, skill_id=skill.id, role="admin")
    # 跨租户状态变更（enable/disable）同样被隔离（review Minor #4）。
    with pytest.raises(SkillNotFoundError):
        await service.set_enabled(
            tenant_id=other_tenant, skill_id=skill.id, enabled=True, role="admin"
        )


# ---------------------------------------------------------------------------
# Router: /api/v1/skills
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


async def _register_server_via_api(client: AsyncClient, auth_headers: dict) -> str:
    code = _unique_code("srv")
    resp = await client.post(
        "/api/v1/mcp-servers",
        json={
            "code": code,
            "name": f"MCP-{code}",
            "server_url": "https://mcp.example.com/rpc",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return code


def _make_payload(code: str, server_code: str, version: str = "1.0.0") -> dict:
    return {
        "code": code,
        "version": version,
        "name": f"企业360背调-{code}",
        "description": "入驻/投决前核验主体与风险",
        "sop_template": _sop_template(server_code),
        "source_ref": "https://agent.qcc.com/skills/1",
        "allowed_roles": ["admin", "data_admin"],
    }


async def _create_via_api(
    client: AsyncClient, auth_headers: dict, code: str, server_code: str,
    version: str = "1.0.0",
) -> dict:
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(code, server_code, version),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_api_create_201_admin(client: AsyncClient, auth_headers: dict):
    server_code = await _register_server_via_api(client, auth_headers)
    code = _unique_code("api")
    body = await _create_via_api(client, auth_headers, code, server_code)
    assert set(body.keys()) == DTO_KEYS
    assert body["code"] == code
    assert body["version"] == "1.0.0"
    assert body["enabled"] is False
    assert body["allowed_roles"] == ["admin", "data_admin"]
    assert "steps" in body["sop_template"]  # 模板正文可见，无 secret


async def test_api_create_201_data_admin(client: AsyncClient, auth_headers: dict):
    server_code = await _register_server_via_api(client, auth_headers)
    token = await _register_and_login(
        client, username=f"da_{uuid.uuid4().hex[:6]}", role="data_admin"
    )
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(_unique_code("da"), server_code),
        headers=_headers(token),
    )
    assert resp.status_code == 201


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_api_create_403_non_admin(
    client: AsyncClient, auth_headers: dict, role: str
):
    server_code = await _register_server_via_api(client, auth_headers)
    token = await _register_and_login(
        client, username=f"{role[:3]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(_unique_code("forb"), server_code),
        headers=_headers(token),
    )
    assert resp.status_code == 403
    assert "无权" in resp.json()["detail"]


async def test_api_create_401_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/v1/skills", json=_make_payload(_unique_code("noauth"), "any_server")
    )
    assert resp.status_code == 401


async def test_api_create_409_code_version_conflict(
    client: AsyncClient, auth_headers: dict
):
    server_code = await _register_server_via_api(client, auth_headers)
    code = _unique_code("cfl")
    await _create_via_api(client, auth_headers, code, server_code)
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(code, server_code),
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "已存在" in resp.json()["detail"]


async def test_api_create_409_reregister_after_soft_delete(
    client: AsyncClient, auth_headers: dict
):
    """软删后同 (code, version) 重新注册 -> 409，而不是未处理 500。

    仿 REQ-044 commit 66e013bd：唯一约束是普通（非部分）UNIQUE，服务层
    预查只看 active 行，软删后的 (code, version) 会触达 DB 约束，router
    必须把 IntegrityError 映射为 409。
    """
    server_code = await _register_server_via_api(client, auth_headers)
    code = _unique_code("rereg")
    body = await _create_via_api(client, auth_headers, code, server_code)
    del_resp = await client.delete(
        f"/api/v1/skills/{body['id']}", headers=auth_headers
    )
    assert del_resp.status_code in (200, 204), del_resp.text
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(code, server_code),
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "已存在" in resp.json()["detail"]


async def test_api_create_201_new_version_after_soft_delete(
    client: AsyncClient, auth_headers: dict
):
    """软删 v1.0.0 后注册同 code 的 v1.1.0 不受影响。"""
    server_code = await _register_server_via_api(client, auth_headers)
    code = _unique_code("rv")
    body = await _create_via_api(client, auth_headers, code, server_code)
    await client.delete(f"/api/v1/skills/{body['id']}", headers=auth_headers)
    resp = await client.post(
        "/api/v1/skills",
        json=_make_payload(code, server_code, version="1.1.0"),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


async def test_api_create_422_template_missing_steps(
    client: AsyncClient, auth_headers: dict
):
    payload = _make_payload(_unique_code("bad"), "any_server")
    payload["sop_template"] = "name: x-y\ndescription: 缺步骤\nsteps: []\n"
    resp = await client.post("/api/v1/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "steps" in resp.json()["detail"]


async def test_api_create_422_unregistered_server(
    client: AsyncClient, auth_headers: dict
):
    ghost = _unique_code("ghost")
    payload = _make_payload(_unique_code("unreg"), ghost)
    resp = await client.post("/api/v1/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert ghost in resp.json()["detail"]  # 指明哪个 server 未注册


async def test_api_create_422_bad_code(client: AsyncClient, auth_headers: dict):
    payload = _make_payload("InvalidCode", "any_server")
    resp = await client.post("/api/v1/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 422


async def test_api_create_422_bad_version(client: AsyncClient, auth_headers: dict):
    payload = _make_payload(_unique_code("ver"), "any_server", version="1.0")
    resp = await client.post("/api/v1/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_api_read_allowed_for_all_roles(
    client: AsyncClient, auth_headers: dict, role: str
):
    """非管理角色可 list / get（只读）。"""
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("ro"), server_code
    )
    token = await _register_and_login(
        client, username=f"ro{role[:2]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.get("/api/v1/skills", headers=_headers(token))
    assert resp.status_code == 200
    assert created["id"] in {s["id"] for s in resp.json()}
    resp = await client.get(
        f"/api/v1/skills/{created['id']}", headers=_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert resp.json()["sop_template"]  # 详情含模板正文


async def test_api_list_includes_all_versions(
    client: AsyncClient, auth_headers: dict
):
    server_code = await _register_server_via_api(client, auth_headers)
    code = _unique_code("lst")
    v1 = await _create_via_api(client, auth_headers, code, server_code, "1.0.0")
    v2 = await _create_via_api(client, auth_headers, code, server_code, "1.1.0")
    resp = await client.get("/api/v1/skills", headers=auth_headers)
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert v1["id"] in ids and v2["id"] in ids
    for row in resp.json():
        assert set(row.keys()) == DTO_KEYS


async def test_api_get_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/v1/skills/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


async def test_api_update_200(client: AsyncClient, auth_headers: dict):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("pat"), server_code
    )
    resp = await client.patch(
        f"/api/v1/skills/{created['id']}",
        json={
            "name": "改后的名称",
            "description": "新描述",
            "source_ref": "enterprise_360_dd.yaml",
            "allowed_roles": ["admin"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "改后的名称"
    assert body["description"] == "新描述"
    assert body["source_ref"] == "enterprise_360_dd.yaml"
    assert body["allowed_roles"] == ["admin"]
    assert body["code"] == created["code"]
    assert body["sop_template"] == created["sop_template"]


async def test_api_update_422_sop_template_change(
    client: AsyncClient, auth_headers: dict
):
    """PATCH 改 sop_template 被拒 422 — 改动须走新版本。"""
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("p422"), server_code
    )
    resp = await client.patch(
        f"/api/v1/skills/{created['id']}",
        json={"sop_template": _sop_template(server_code)},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "sop_template" in resp.json()["detail"]


async def test_api_update_404(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/v1/skills/{uuid.uuid4()}",
        json={"name": "不存在"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_api_update_403_employee(client: AsyncClient, auth_headers: dict):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("p403"), server_code
    )
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.patch(
        f"/api/v1/skills/{created['id']}",
        json={"name": "employee 改名"},
        headers=_headers(token),
    )
    assert resp.status_code == 403


async def test_api_enable_disable_flips_flag(
    client: AsyncClient, auth_headers: dict
):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("ena"), server_code
    )
    assert created["enabled"] is False

    resp = await client.post(
        f"/api/v1/skills/{created['id']}/enable", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["updated_at"] > created["updated_at"]

    resp = await client.post(
        f"/api/v1/skills/{created['id']}/disable", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_api_enable_404(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/skills/{uuid.uuid4()}/enable", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_enable_disable_403_employee(
    client: AsyncClient, auth_headers: dict
):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("e403"), server_code
    )
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    for action in ("enable", "disable"):
        resp = await client.post(
            f"/api/v1/skills/{created['id']}/{action}", headers=_headers(token)
        )
        assert resp.status_code == 403


async def test_api_delete_204_then_get_404(
    client: AsyncClient, auth_headers: dict
):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("del"), server_code
    )
    resp = await client.delete(
        f"/api/v1/skills/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/skills/{created['id']}", headers=auth_headers)
    assert resp.status_code == 404


async def test_api_delete_404(client: AsyncClient, auth_headers: dict):
    resp = await client.delete(
        f"/api/v1/skills/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_api_delete_403_employee(client: AsyncClient, auth_headers: dict):
    server_code = await _register_server_via_api(client, auth_headers)
    created = await _create_via_api(
        client, auth_headers, _unique_code("d403"), server_code
    )
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.delete(
        f"/api/v1/skills/{created['id']}", headers=_headers(token)
    )
    assert resp.status_code == 403
