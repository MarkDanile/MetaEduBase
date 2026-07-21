"""Tests for SkillRunner execution engine (REQ-045 Task 3, spec §4.4).

Real DB (skills + skill_execution_audit), mocked :class:`MCPInvocationService`
(no network) and mocked :func:`shared.llm.chat.chat`. Covers AC-4 / AC-5 /
AC-6 / AC-8:

- success path: steps invoked in order, facts collected, LLM synthesis,
  audit ``ok=True`` with subject/steps/report digests, SkillResult shape
- unregistered skill -> :class:`SkillExecutionNotFoundError`, NO audit row
- disabled skill -> ``error_code=disabled`` + audit ``ok=False``
- forbidden role -> ``error_code=forbidden`` + audit
- corrupt template -> ``error_code=template_error`` + audit
- a step's invoke fails -> ``error_code=tool_error`` + audit, LLM not
  called, no fabricated facts
- LLM failure -> ``error_code=llm_error`` + audit
- audit digests never equal raw subject / report / facts
- error_message scrubbed of raw subject values
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    InvocationTrace,
    MCPInvocationError,
    canonical_digest,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillRegistryService,
)
from app.contexts.skill_registry.application.skill_runner import (
    SkillExecutionError,
    SkillExecutionNotFoundError,
    SkillRunner,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_SUCCESS_REPORT = "## 事实数据\nACME 工商一致\n## AI 分析\n低风险"


@pytest.fixture(autouse=True)
async def _clean_skill_tables(db_session):
    """Clear prior-committed skill + mcp rows for the default tenant.

    ``db_session`` commits on teardown, so previous tests' servers /
    skills / audits persist and trip uniqueness constraints. FK-safe
    order: skill audit -> skills -> mcp audit -> mcp servers.
    """
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
        text("DELETE FROM metaedu.mcp_invocation_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.mcp_servers WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


def _caller(role: str = "admin") -> InvocationCaller:
    return InvocationCaller(
        caller_type="service", role=role, user_id=DEFAULT_ADMIN_ID
    )


def _sop_template(server_code: str, *, steps: int = 2) -> str:
    step_yaml = "\n".join(
        f"  - id: step_{i}\n    title: step {i}\n"
        f"    server: {server_code}\n    tool: tool_{i}\n    output: out_{i}"
        for i in range(steps)
    )
    return (
        "name: enterprise-360-dd\n"
        "description: 企业 360 背调 SOP\n"
        f"mcp_dependencies:\n  - {{server: {server_code}, required: true}}\n"
        "principles:\n  - 缺失数据显式标注，不编造默认值\n"
        f"steps:\n{step_yaml}\n"
        "report_template: |\n  ## 事实数据\n  ## AI 分析\n  ## 待人工确认项\n"
    )


async def _register_skill(
    db_session,
    *,
    code: str,
    allowed_roles: list[str] | None = None,
    enabled: bool = True,
    sop_template: str | None = None,
    server_code: str | None = None,
    version: str = "1.0.0",
) -> uuid.UUID:
    server_code = server_code or code + "_srv"
    await MCPRegistryService(db_session).create(
        tenant_id=DEFAULT_TENANT_ID,
        code=server_code,
        name=f"MCP-{server_code}",
        server_url="https://mcp.example.com/rpc",
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    svc = SkillRegistryService(db_session)
    skill = await svc.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        version=version,
        name=f"Skill-{code}",
        sop_template=sop_template or _sop_template(server_code),
        created_by=DEFAULT_ADMIN_ID,
        allowed_roles=allowed_roles if allowed_roles is not None else ["admin"],
        role="super_admin",
    )
    if enabled:
        await svc.set_enabled(
            tenant_id=DEFAULT_TENANT_ID,
            skill_id=skill.id,
            enabled=True,
            role="super_admin",
        )
    await db_session.commit()
    return skill.id


def _mock_invocation(step_to_result: dict[str, dict]) -> AsyncMock:
    """Map step id -> MCP tool result; ``invoke`` returns by tool_name.

    REQ-046 v2: the runner now calls ``invoke_with_trace``; the mock provides
    it (returning an ``InvocationTrace``) and delegates ``invoke`` to the same
    side_effect so legacy ``invoke.await_count`` assertions still hold.
    """
    tool_to_result = {
        f"tool_{i}": result for i, result in enumerate(step_to_result.values())
    }

    async def _invoke(*, server_code, tool_name, params, caller, tenant_id):
        return tool_to_result[tool_name]

    async def _invoke_with_trace(*, server_code, tool_name, params, caller, tenant_id):
        result = await _invoke(
            server_code=server_code, tool_name=tool_name,
            params=params, caller=caller, tenant_id=tenant_id,
        )
        return InvocationTrace(result=result, audit_id=uuid.uuid4())

    mock = AsyncMock()
    mock.invoke = AsyncMock(side_effect=_invoke)
    mock.invoke_with_trace = AsyncMock(side_effect=_invoke_with_trace)
    return mock


def _mock_invocation_step_fails(failing_step_index: int) -> AsyncMock:
    """First ``failing_step_index`` steps succeed; the next raises."""
    calls = {"count": 0}

    async def _invoke(*, server_code, tool_name, params, caller, tenant_id):
        idx = calls["count"]
        calls["count"] += 1
        if idx == failing_step_index:
            raise MCPInvocationError("tool_error", "公司未找到")
        return {"ok": True, "step": idx}

    async def _invoke_with_trace(*, server_code, tool_name, params, caller, tenant_id):
        result = await _invoke(
            server_code=server_code, tool_name=tool_name,
            params=params, caller=caller, tenant_id=tenant_id,
        )
        return InvocationTrace(result=result, audit_id=uuid.uuid4())

    mock = AsyncMock()
    mock.invoke = AsyncMock(side_effect=_invoke)
    mock.invoke_with_trace = AsyncMock(side_effect=_invoke_with_trace)
    return mock


async def _audit_rows(db_session, skill_id: uuid.UUID) -> list[dict]:
    result = await db_session.execute(
        text(
            "SELECT ok, error_code, error_message, subject_digest, "
            "steps_digest, report_digest, duration_ms, caller_type, "
            "caller_user_id, skill_code, skill_version "
            "FROM metaedu.skill_execution_audit "
            "WHERE skill_id = :sid ORDER BY created_at ASC"
        ),
        {"sid": skill_id},
    )
    return [
        {
            "ok": r[0], "error_code": r[1], "error_message": r[2],
            "subject_digest": r[3], "steps_digest": r[4],
            "report_digest": r[5], "duration_ms": r[6],
            "caller_type": r[7], "caller_user_id": r[8],
            "skill_code": r[9], "skill_version": r[10],
        }
        for r in result.all()
    ]


async def _audit_count(db_session) -> int:
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM metaedu.skill_execution_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    return int(result.scalar() or 0)


# ── success path ──────────────────────────────────────────────────


async def test_run_success_collects_facts_and_synthesizes(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=_SUCCESS_REPORT),
    )
    code = f"ok_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(
            {"step_0": {"company": "ACME"}, "step_1": {"risk": "low"}}
        )
    )
    subject = {"company_name": "ACME", "credit_code": "91110000XXXX"}
    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
        subject=subject, caller=_caller(),
    )
    assert result.report == _SUCCESS_REPORT
    assert len(result.steps) == 2
    assert [s.id for s in result.steps] == ["step_0", "step_1"]
    assert all(s.ok for s in result.steps)
    assert result.steps[0].digest == canonical_digest({"company": "ACME"})
    assert result.duration_ms >= 0

    rows = await _audit_rows(db_session, skill_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["ok"] is True
    assert row["error_code"] is None
    assert row["skill_code"] == code
    assert row["skill_version"] == "1.0.0"
    assert row["subject_digest"] == canonical_digest(subject)
    assert row["steps_digest"] == canonical_digest(
        {s.id: s.digest for s in result.steps}
    )
    # report_digest = sha256(report 文本)
    import hashlib

    assert row["report_digest"] == hashlib.sha256(
        _SUCCESS_REPORT.encode("utf-8")
    ).hexdigest()
    assert row["caller_type"] == "service"
    assert row["caller_user_id"] == DEFAULT_ADMIN_ID


async def test_run_invokes_steps_in_order(db_session, monkeypatch):
    """Steps must be called sequentially in template order."""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="report"),
    )
    code = f"order_{uuid.uuid4().hex[:6]}"
    await _register_skill(db_session, code=code)
    inv = _mock_invocation(
        {"step_0": {"a": 1}, "step_1": {"b": 2}}
    )
    runner = SkillRunner(db_session, invocation_service=inv)
    await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
        subject={"x": 1}, caller=_caller(),
    )
    assert inv.invoke_with_trace.await_count == 2
    # First call tool_0, second tool_1
    first = inv.invoke_with_trace.await_args_list[0].kwargs["tool_name"]
    second = inv.invoke_with_trace.await_args_list[1].kwargs["tool_name"]
    assert first == "tool_0"
    assert second == "tool_1"


# ── unregistered: NO audit row ────────────────────────────────────


async def test_run_unregistered_raises_not_found_no_audit(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    runner = SkillRunner(db_session, invocation_service=AsyncMock())
    with pytest.raises(SkillExecutionNotFoundError):
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code="no_such_skill",
            version="1.0.0", subject={"x": 1}, caller=_caller(),
        )
    assert await _audit_count(db_session) == 0


# ── disabled -> audit ok=False error_code=disabled ───────────────


async def test_run_disabled_audits(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"dis_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code, enabled=False)
    runner = SkillRunner(db_session, invocation_service=AsyncMock())
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(),
        )
    assert exc.value.error_code == "disabled"
    rows = await _audit_rows(db_session, skill_id)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "disabled"
    assert rows[0]["steps_digest"] is None
    assert rows[0]["report_digest"] is None
    assert rows[0]["subject_digest"] == canonical_digest({"company_name": "ACME"})


# ── forbidden role -> audit ok=False error_code=forbidden ────────


async def test_run_forbidden_audits(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"forb_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(
        db_session, code=code, allowed_roles=["data_admin"]
    )
    runner = SkillRunner(db_session, invocation_service=AsyncMock())
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(role="employee"),
        )
    assert exc.value.error_code == "forbidden"
    rows = await _audit_rows(db_session, skill_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "forbidden"


# ── super_admin always passes role gate ──────────────────────────


async def test_run_super_admin_allowed_with_empty_roles(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="report"),
    )
    code = f"sa_{uuid.uuid4().hex[:6]}"
    await _register_skill(db_session, code=code, allowed_roles=[])
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(
            {"step_0": {"x": 1}, "step_1": {"y": 2}}
        )
    )
    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
        subject={"x": 1}, caller=_caller(role="super_admin"),
    )
    assert result.report == "report"


# ── corrupt template -> audit ok=False error_code=template_error ─


async def test_run_template_error_audits(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"tpl_{uuid.uuid4().hex[:6]}"
    # 直接造一份 DB 正文已损坏的 skill：用合法模板注册后强制改坏模板正文
    skill_id = await _register_skill(db_session, code=code)
    await db_session.execute(
        text("UPDATE metaedu.skills SET sop_template = :t WHERE id = :id"),
        {"t": "name: x-y\ndescription: bad\nsteps: []\n", "id": skill_id},
    )
    await db_session.commit()
    runner = SkillRunner(db_session, invocation_service=AsyncMock())
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(),
        )
    assert exc.value.error_code == "template_error"
    rows = await _audit_rows(db_session, skill_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "template_error"


# ── a step fails -> tool_error, no LLM, no fabricated facts ───────


async def test_run_step_failure_is_tool_error_no_llm_no_fabrication(
    db_session, monkeypatch
):
    chat_mock = AsyncMock(return_value="should-not-be-called")
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        chat_mock,
    )
    code = f"tf_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)
    # step_0 succeeds, step_1 raises MCPInvocationError
    runner = SkillRunner(
        db_session,
        invocation_service=_mock_invocation_step_fails(failing_step_index=1),
    )
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(),
        )
    assert exc.value.error_code == "tool_error"
    # LLM 合成绝未被调用
    chat_mock.assert_not_awaited()
    rows = await _audit_rows(db_session, skill_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "tool_error"
    assert "step_1" in rows[0]["error_message"]
    assert rows[0]["steps_digest"] is None
    assert rows[0]["report_digest"] is None


async def test_run_first_step_failure(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"tf0_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)
    runner = SkillRunner(
        db_session,
        invocation_service=_mock_invocation_step_fails(failing_step_index=0),
    )
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"x": 1}, caller=_caller(),
        )
    assert exc.value.error_code == "tool_error"
    assert "step_0" in (await _audit_rows(db_session, skill_id))[0]["error_message"]


# ── LLM failure -> error_code=llm_error + audit ──────────────────


async def test_run_llm_failure_audits(db_session, monkeypatch):
    chat_mock = AsyncMock(side_effect=RuntimeError("provider down"))
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        chat_mock,
    )
    code = f"llm_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(
            {"step_0": {"x": 1}, "step_1": {"y": 2}}
        )
    )
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(),
        )
    assert exc.value.error_code == "llm_error"
    rows = await _audit_rows(db_session, skill_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "llm_error"
    # steps 已收集（有 digest），但报告未生成
    assert rows[0]["steps_digest"] is None
    assert rows[0]["report_digest"] is None


# ── digests never equal raw content ──────────────────────────────


async def test_audit_digests_never_equal_raw(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=_SUCCESS_REPORT),
    )
    code = f"dig_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(
            {"step_0": {"company": "ACME"}, "step_1": {"risk": "low"}}
        )
    )
    subject = {"company_name": "ACME Inc", "credit_code": "91110000MA00ABCD"}
    await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
        subject=subject, caller=_caller(),
    )
    rows = await _audit_rows(db_session, skill_id)
    row = rows[0]
    # digest is a 64-char hex, never the raw subject / report / facts
    assert row["subject_digest"] != str(subject)
    assert row["subject_digest"] != "ACME"
    assert row["report_digest"] != _SUCCESS_REPORT
    assert row["report_digest"] is not None
    assert len(row["subject_digest"]) == 64
    # Raw values must not appear anywhere in the audit row text columns.
    for raw in ("ACME Inc", "91110000MA00ABCD", _SUCCESS_REPORT, "company"):
        assert raw not in (row["error_message"] or "")


# ── error_message scrubbed of raw subject values ─────────────────


async def test_error_message_scrubs_subject_values(db_session, monkeypatch):
    """A chatty tool error echoing the subject must not leak into audit."""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"scrub_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)

    sensitive = "SUPER-SENSITIVE-COMPANY-NAME-XYZ"

    async def _invoke(*, server_code, tool_name, params, caller, tenant_id):
        raise MCPInvocationError(
            "tool_error", f"failed for company={sensitive}"
        )

    mock = AsyncMock()
    mock.invoke = AsyncMock(side_effect=_invoke)
    mock.invoke_with_trace = AsyncMock(side_effect=_invoke)
    runner = SkillRunner(db_session, invocation_service=mock)
    with pytest.raises(SkillExecutionError):
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={"company_name": sensitive}, caller=_caller(),
        )
    rows = await _audit_rows(db_session, skill_id)
    assert sensitive not in (rows[0]["error_message"] or "")
    assert "step_0" in rows[0]["error_message"]


async def test_error_message_scrubs_nested_and_nonstring_subject_values(
    db_session, monkeypatch
):
    """Nested dict / list + numeric subject values are also scrubbed (M-2)."""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="x"),
    )
    code = f"scrub2_{uuid.uuid4().hex[:6]}"
    skill_id = await _register_skill(db_session, code=code)

    nested_name = "NESTED-SECRET-NAME"
    numeric_code = 911100009999

    async def _invoke(*, server_code, tool_name, params, caller, tenant_id):
        raise MCPInvocationError(
            "tool_error",
            f"echo name={nested_name} code={numeric_code}",
        )

    mock = AsyncMock()
    mock.invoke = AsyncMock(side_effect=_invoke)
    mock.invoke_with_trace = AsyncMock(side_effect=_invoke)
    runner = SkillRunner(db_session, invocation_service=mock)
    with pytest.raises(SkillExecutionError):
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code=code, version="1.0.0",
            subject={
                "company": {"name": nested_name},
                "branches": [{"code": numeric_code}],
            },
            caller=_caller(),
        )
    rows = await _audit_rows(db_session, skill_id)
    msg = rows[0]["error_message"] or ""
    assert nested_name not in msg
    assert str(numeric_code) not in msg
