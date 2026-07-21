"""Skill execution tenant isolation (REQ-045 Task 3, AC-7).

Real-DB integration: a skill registered in tenant A cannot be executed by
tenant B, and tenant B cannot read tenant A's execution audit rows. Both
the skill lookup (``get_by_code_version`` / ``get_by_id``) and the audit
query (``list_by_skill``) are tenant-forced, so cross-tenant access is
rejected before any audit row is written.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillRegistryService,
)
from app.contexts.skill_registry.application.skill_runner import (
    SkillExecutionNotFoundError,
    SkillRunner,
)
from app.contexts.skill_registry.infrastructure.skill_execution_audit_repository import (
    SkillExecutionAuditRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_OTHER_TENANT = uuid.uuid4()


@pytest.fixture(autouse=True)
async def _clean_tables(db_session):
    for tid in (DEFAULT_TENANT_ID, _OTHER_TENANT):
        await db_session.execute(
            text("DELETE FROM metaedu.skill_execution_audit "
                 "WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        await db_session.execute(
            text("DELETE FROM metaedu.skills WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        await db_session.execute(
            text("DELETE FROM metaedu.mcp_invocation_audit "
                 "WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        await db_session.execute(
            text("DELETE FROM metaedu.mcp_servers WHERE tenant_id = :tid"),
            {"tid": tid},
        )
    await db_session.flush()
    yield


def _sop_template(server_code: str) -> str:
    return (
        "name: enterprise-360-dd\n"
        "description: 企业 360 背调 SOP\n"
        f"mcp_dependencies:\n  - {{server: {server_code}, required: true}}\n"
        f"steps:\n  - id: step_0\n    server: {server_code}\n    tool: tool_0\n"
        "report_template: |\n  ## 事实数据\n"
    )


async def _register_enabled_skill(
    db_session, tenant_id: uuid.UUID, code: str
) -> uuid.UUID:
    server_code = code + "_srv"
    await MCPRegistryService(db_session).create(
        tenant_id=tenant_id,
        code=server_code,
        name=f"MCP-{server_code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    svc = SkillRegistryService(db_session)
    skill = await svc.create(
        tenant_id=tenant_id,
        code=code,
        version="1.0.0",
        name=f"Skill-{code}",
        sop_template=_sop_template(server_code),
        created_by=DEFAULT_ADMIN_ID,
        allowed_roles=["admin"],
        role="super_admin",
    )
    await svc.set_enabled(
        tenant_id=tenant_id, skill_id=skill.id, enabled=True, role="super_admin"
    )
    await db_session.commit()
    return skill.id


async def test_run_cross_tenant_not_found_no_audit(db_session, monkeypatch):
    """tenant B 执行 tenant A 的 skill -> NotFound，不写审计。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="report"),
    )
    code = f"iso_{uuid.uuid4().hex[:6]}"
    await _register_enabled_skill(db_session, DEFAULT_TENANT_ID, code)
    # tenant B 在他自己的 scope 查不到该 code -> NotFound，不写审计
    runner = SkillRunner(db_session, invocation_service=AsyncMock())
    with pytest.raises(SkillExecutionNotFoundError):
        await runner.run(
            tenant_id=_OTHER_TENANT, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=InvocationCaller(
                caller_type="service", role="admin", user_id=DEFAULT_ADMIN_ID
            ),
        )
    count = await db_session.execute(
        text("SELECT COUNT(*) FROM metaedu.skill_execution_audit "
             "WHERE tenant_id = :tid"),
        {"tid": _OTHER_TENANT},
    )
    assert int(count.scalar() or 0) == 0


async def test_execution_audit_cross_tenant_invisible(db_session, monkeypatch):
    """tenant A 的 audit 行对 tenant B 不可见。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="report"),
    )
    code = f"aud_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_enabled_skill(db_session, DEFAULT_TENANT_ID, code)

    async def _invoke(*, server_code, tool_name, params, caller, tenant_id):
        return {"company": "ACME"}

    mock = AsyncMock()
    mock.invoke = AsyncMock(side_effect=_invoke)
    runner = SkillRunner(db_session, invocation_service=mock)
    await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
        subject={"company_name": "ACME"}, caller=InvocationCaller(
            caller_type="service", role="admin", user_id=DEFAULT_ADMIN_ID
        ),
    )
    await db_session.commit()
    # tenant A 看得到
    rows_a, total_a = await SkillExecutionAuditRepository(db_session).list_by_skill(
        DEFAULT_TENANT_ID, skill_id, limit=10, offset=0
    )
    assert total_a == 1
    assert len(rows_a) == 1
    # tenant B 看不到（即使持 tenant A 的 skill_id）
    rows_b, total_b = await SkillExecutionAuditRepository(db_session).list_by_skill(
        _OTHER_TENANT, skill_id, limit=10, offset=0
    )
    assert total_b == 0
    assert rows_b == []
