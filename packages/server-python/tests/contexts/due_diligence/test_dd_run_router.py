"""Router tests for DD run + report store + evidence ledger (REQ-046 Slice 5).

HTTP-level contract for AC-2/5/6/7. The full pipeline runs end-to-end with a
real DB session and the real orchestrator + SkillRunner; only the network /
LLM leaves are stubbed (MCP ``invoke_with_trace``, the internal-query planner
chat, and the report synthesis chat). Covers:
- AC-1: run on an unconfirmed task -> 422, no skill call.
- run produces a report draft (201) whose evidence_refs become ledger rows.
- report confirm locks the version; evidence endpoint returns the bound refs.
- tenant isolation on report / evidence reads.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationTrace,
)
from tests.contexts.identity._helpers import register_and_login as _register_and_login

pytestmark = pytest.mark.asyncio


# _register_and_login 经 tests.contexts.identity._helpers 注入（BUG-017，
# 支持 tenant_id 参数用于跨租户测试）。


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_and_confirm_task(client: AsyncClient, token: str) -> dict:
    resp = await client.post(
        "/api/v1/dd/tasks",
        json={"title": "园区入驻背调", "subject_query": "ACME"},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    resp = await client.post(
        f"/api/v1/dd/tasks/{task['id']}/confirm-subject",
        json={"company_name": "ACME", "credit_code": "9111"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _register_park_skill(client: AsyncClient, token: str) -> None:
    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:8]
    qcc_code = f"qcc_{suffix}"
    intcust_code = f"internal_customer_{suffix}"
    skill_code = f"park_investment_dd_{suffix}"
    for code in (qcc_code, intcust_code):
        resp = await client.post(
            "/api/v1/mcp-servers",
            json={
                "code": code,
                "name": f"MCP-{code}",
                "server_url": "https://mcp.example.com/rpc",
            },
            headers=_headers(token),
        )
        assert resp.status_code in (201, 409), resp.text
    sop = (
        f"name: park-investment-dd\n"
        f"description: 园区招商背调\n"
        f"mcp_dependencies:\n  - {{server: {qcc_code}, required: true}}\n"
        f"steps:\n"
        f"  - id: subject_verify\n    type: mcp\n    server: {qcc_code}\n"
        f"    tool: get_company_registration_info\n"
        f"report_contract:\n  schema:\n    type: object\n"
        f"    required: [summary, external_facts, internal_facts, risk_watch_items,"
        f" human_review_items, evidence_refs, report_sections]\n"
        f"    properties:\n"
        f"      summary: {{type: array}}\n"
        f"      external_facts: {{type: array}}\n"
        f"      internal_facts: {{type: array}}\n"
        f"      risk_watch_items: {{type: array}}\n"
        f"      human_review_items: {{type: array}}\n"
        f"      evidence_refs: {{type: array}}\n"
        f"      report_sections: {{type: array}}\n"
    )
    resp = await client.post(
        "/api/v1/skills",
        json={
            "code": skill_code,
            "version": "1.0.0",
            "name": "园区招商背调",
            "sop_template": sop,
            "allowed_roles": ["admin", "leader"],
        },
        headers=_headers(token),
    )
    assert resp.status_code in (201, 409), resp.text
    if resp.status_code == 201:
        skill_id = resp.json()["id"]
        en = await client.post(
            f"/api/v1/skills/{skill_id}/enable", headers=_headers(token)
        )
        assert en.status_code == 200, en.text
    # REQ-058: V0 SOP 硬编码 skill code 'park_investment_dd'（DD_SKILL_CODE）。
    # fixture 末尾确保 V0 skill 存在 + allowed_roles 含 leader + enabled。
    v0_sop = sop.replace(qcc_code, "qcc").replace(skill_code, "park_investment_dd")
    resp = await client.post(
        "/api/v1/skills",
        json={
            "code": "park_investment_dd",
            "version": "1.0.0",
            "name": "园区招商背调",
            "sop_template": v0_sop,
            "allowed_roles": ["admin", "leader"],
        },
        headers=_headers(token),
    )
    assert resp.status_code in (201, 409), resp.text
    resp = await client.get("/api/v1/skills", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    v0_skill = next(
        (s for s in resp.json() if s["code"] == "park_investment_dd"), None
    )
    assert v0_skill is not None, "V0 park_investment_dd 应已被创建"
    patch_resp = await client.patch(
        f"/api/v1/skills/{v0_skill['id']}",
        json={"allowed_roles": ["admin", "leader"]},
        headers=_headers(token),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    if not v0_skill.get("enabled"):
        en = await client.post(
            f"/api/v1/skills/{v0_skill['id']}/enable", headers=_headers(token)
        )
        assert en.status_code == 200, en.text


_SEVEN_KEY_REPORT = {
    "summary": ["总体良好"],
    "external_facts": ["工商存续"],
    "internal_facts": ["在租 1 间"],
    "risk_watch_items": [],
    "human_review_items": ["核实欠费"],
    "evidence_refs": [{"source_step": "subject_verify"}],
    "report_sections": [],
}


def _run_mocks():
    inv = AsyncMock(return_value=InvocationTrace(result={"ok": 1}, audit_id=uuid.uuid4()))
    report_chat = AsyncMock(return_value=json.dumps(_SEVEN_KEY_REPORT))
    return (
        patch(
            "app.contexts.skill_registry.application.skill_runner.MCPInvocationService.invoke_with_trace",
            inv,
        ),
        patch(
            "app.contexts.skill_registry.application.skill_runner.chat",
            report_chat,
        ),
    )


async def test_run_unconfirmed_task_422(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddrun"), role="admin")
    resp = await client.post(
        "/api/v1/dd/tasks",
        json={"title": "t", "subject_query": "ACME"},
        headers=_headers(token),
    )
    task_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/dd/tasks/{task_id}/run", headers=_headers(token)
    )
    assert resp.status_code == 422


async def test_run_produces_report_and_evidence(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddrun"), role="admin")
    await _register_park_skill(client, token)
    task = await _create_and_confirm_task(client, token)

    inv_patch, report_patch = _run_mocks()
    with inv_patch, report_patch:
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/run", headers=_headers(token)
        )
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["status"] == "draft"
    assert report["report_json"]["external_facts"] == ["工商存续"]
    assert "内部事实" in report["report_markdown"]

    # AC-6: evidence ledger rows bound to the runner-injected audit id.
    resp = await client.get(
        f"/api/v1/dd/reports/{report['id']}/evidence", headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["evidence_type"] == "mcp_invocation"
    assert rows[0]["ref_id"]


async def test_report_confirm_locks_version(client: AsyncClient):
    # REQ-058 AC-3: leader 创建+run，admin（不同用户）confirm。
    leader_token = await _register_and_login(
        client, username=_uname("ddrun_leader"), role="leader",
    )
    admin_token = await _register_and_login(
        client, username=_uname("ddrun_admin"), role="admin",
    )
    # MCP server 注册需 admin/data_admin/super_admin（用 admin_token）
    await _register_park_skill(client, admin_token)
    task = await _create_and_confirm_task(client, leader_token)
    inv_patch, report_patch = _run_mocks()
    with inv_patch, report_patch:
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/run", headers=_headers(leader_token)
        )
    assert resp.status_code == 201, resp.text
    report_id = resp.json()["id"]

    # admin（不同人）confirm
    resp = await client.post(
        f"/api/v1/dd/reports/{report_id}/confirm", headers=_headers(admin_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"
    assert resp.json()["confirmed_by"]

    # re-confirm -> 422
    resp = await client.post(
        f"/api/v1/dd/reports/{report_id}/confirm", headers=_headers(admin_token)
    )
    assert resp.status_code == 422


async def test_report_read_tenant_isolated(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddrun"), role="admin")
    await _register_park_skill(client, token)
    task = await _create_and_confirm_task(client, token)
    inv_patch, report_patch = _run_mocks()
    with inv_patch, report_patch:
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/run", headers=_headers(token)
        )
    report_id = resp.json()["id"]

    # A user in a *different* tenant must not read this tenant's report.
    other_tenant = str(uuid.uuid4())
    await _seed_tenant(client, other_tenant)
    other = await _register_and_login(
        client, username=_uname("ddother"), role="admin", tenant_id=other_tenant
    )
    resp = await client.get(
        f"/api/v1/dd/reports/{report_id}", headers=_headers(other)
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/dd/reports/{report_id}/evidence", headers=_headers(other)
    )
    assert resp.status_code == 404


async def _seed_tenant(client: AsyncClient, tenant_id: str) -> None:
    """Insert a tenant row so a user can register under it (users.tenant_id FK)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO metaedu.tenants "
                "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                "VALUES (:id, 'other', 'other', 'shared', true, now(), now())"
            ),
            {"id": tenant_id},
        )
        await session.commit()
    await engine.dispose()
