"""Skill execution audit repository + digest convention (REQ-045 Task 3).

Real-DB integration test for AC-6: asserts the ``skill_execution_audit``
row carries the full field set (skill_code / skill_version / subject_digest
/ steps_digest / report_digest / ok / error / duration_ms / tenant /
caller) and that the digest convention matches REQ-044
(``sha256(canonical_json)``). Raw subject / facts / report never appear.
"""
from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    canonical_digest,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillRegistryService,
)
from app.contexts.skill_registry.infrastructure.skill_execution_audit_repository import (
    SkillExecutionAuditRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _clean_skill_tables(db_session):
    # FK 顺序：mcp_invocation_audit -> mcp_servers。mcp_registry 测试可能在
    # test DB 残留 invocation audit 行引用 server，必须先清 invocation audit，
    # 否则下文 DELETE mcp_servers 触发 ForeignKeyViolationError（跨模块污染）。
    await db_session.execute(
        text("DELETE FROM metaedu.mcp_invocation_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.skill_execution_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.skills WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.mcp_servers WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


async def _make_skill(db_session, code: str) -> uuid.UUID:
    server_code = code + "_srv"
    await MCPRegistryService(db_session).create(
        tenant_id=DEFAULT_TENANT_ID,
        code=server_code,
        name=f"MCP-{server_code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    skill = await SkillRegistryService(db_session).create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        version="1.0.0",
        name=f"Skill-{code}",
        sop_template=(
            "name: enterprise-360-dd\n"
            "description: 企业 360 背调 SOP\n"
            f"mcp_dependencies:\n  - {{server: {server_code}, required: true}}\n"
            f"steps:\n  - id: step_0\n    server: {server_code}\n    tool: tool_0\n"
            "report_template: |\n  ## 事实数据\n"
        ),
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    await db_session.commit()
    return skill.id


async def test_audit_row_field_set_complete(db_session):
    skill_id = await _make_skill(db_session, f"audit_{uuid.uuid4().hex[:6]}")
    repo = SkillExecutionAuditRepository(db_session)
    subject = {"company_name": "ACME", "credit_code": "91110000XXXX"}
    row = await repo.write(
        tenant_id=DEFAULT_TENANT_ID,
        skill_id=skill_id,
        skill_code="audit_skill",
        skill_version="1.0.0",
        caller_type="service",
        caller_user_id=DEFAULT_ADMIN_ID,
        subject_digest=canonical_digest(subject),
        steps_digest=canonical_digest({"step_0": "abc"}),
        report_digest=hashlib.sha256(b"report").hexdigest(),
        ok=True,
        error_code=None,
        error_message=None,
        duration_ms=42,
    )
    await db_session.commit()
    assert row.tenant_id == DEFAULT_TENANT_ID
    assert row.skill_id == skill_id
    assert row.skill_code == "audit_skill"
    assert row.skill_version == "1.0.0"
    assert row.caller_type == "service"
    assert row.caller_user_id == DEFAULT_ADMIN_ID
    assert row.ok is True
    assert row.duration_ms == 42
    assert len(row.subject_digest) == 64
    assert len(row.steps_digest) == 64
    assert len(row.report_digest) == 64
    assert row.created_at is not None


async def test_list_by_skill_pagination_newest_first(db_session):
    skill_id = await _make_skill(db_session, f"pg_{uuid.uuid4().hex[:6]}")
    repo = SkillExecutionAuditRepository(db_session)
    # 写入 3 行（不同时间戳靠 created_at 自然差异 + 排序）
    for i in range(3):
        await repo.write(
            tenant_id=DEFAULT_TENANT_ID,
            skill_id=skill_id,
            skill_code="pg_skill",
            skill_version="1.0.0",
            caller_type="service",
            caller_user_id=DEFAULT_ADMIN_ID,
            subject_digest=None,
            steps_digest=None,
            report_digest=None,
            ok=False,
            error_code="disabled",
            error_message=f"msg-{i}",
            duration_ms=i,
        )
        await db_session.commit()
    rows, total = await repo.list_by_skill(
        DEFAULT_TENANT_ID, skill_id, limit=2, offset=0
    )
    assert total == 3
    assert len(rows) == 2
    # newest-first -> error_message 序号降序
    msgs = [r.error_message for r in rows]
    assert msgs == ["msg-2", "msg-1"]
    # offset=2 拿到最旧那行
    rows2, _ = await repo.list_by_skill(
        DEFAULT_TENANT_ID, skill_id, limit=2, offset=2
    )
    assert [r.error_message for r in rows2] == ["msg-0"]


async def test_list_by_skill_tenant_isolation(db_session):
    """另一 tenant 查不到本 tenant 的 audit 行。"""
    skill_id = await _make_skill(db_session, f"iso_{uuid.uuid4().hex[:6]}")
    repo = SkillExecutionAuditRepository(db_session)
    await repo.write(
        tenant_id=DEFAULT_TENANT_ID,
        skill_id=skill_id,
        skill_code="iso_skill",
        skill_version="1.0.0",
        caller_type="service",
        caller_user_id=DEFAULT_ADMIN_ID,
        subject_digest=None,
        steps_digest=None,
        report_digest=None,
        ok=True,
        error_code=None,
        error_message=None,
        duration_ms=1,
    )
    await db_session.commit()
    other = uuid.uuid4()
    rows, total = await repo.list_by_skill(other, skill_id, limit=10, offset=0)
    assert total == 0
    assert rows == []


async def test_digest_convention_matches_req044(db_session):
    """subject_digest = canonical_digest(subject) = sha256(canonical_json)."""
    subject = {"b": 2, "a": 1}  # 乱序 key，验证 sort_keys
    expected = hashlib.sha256(
        json.dumps(
            subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert canonical_digest(subject) == expected
    # canonical 与直接 dump 不同（分隔符不同）
    assert canonical_digest(subject) != json.dumps(subject)
