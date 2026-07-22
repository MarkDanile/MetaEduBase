"""SkillRunner v2 tests (REQ-046 PR-3): mixed step types + evidence trace + structured report.

Covers the v2 extensions on top of the REQ-045 engine (which stays green):
- mcp steps run via ``invoke_with_trace`` and carry ``invocation_audit_id``.
- ``internal_query`` steps run via an injectable query callable and carry
  ``query_audit_id``.
- ``SkillStepResult`` exposes the audit binding per step (AC-6 evidence_refs).
- ``report_contract`` present -> LLM output is JSON-parsed + jsonschema-
  validated; valid output lands in ``SkillResult.report_json``; invalid output
  retries once then fails ``report_invalid`` (audited, never fabricated).
Real DB, mocked invocation / query / llm — no network.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    InvocationTrace,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillRegistryService,
)
from app.contexts.skill_registry.application.skill_runner import (
    SkillExecutionError,
    SkillRunner,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _clean_tables(db_session):
    for table in (
        "skill_execution_audit", "skills", "mcp_invocation_audit", "mcp_servers",
    ):
        await db_session.execute(
            text(f"DELETE FROM metaedu.{table} WHERE tenant_id = :tid"),
            {"tid": DEFAULT_TENANT_ID},
        )
    await db_session.flush()
    yield


def _caller(role: str = "admin") -> InvocationCaller:
    return InvocationCaller(
        caller_type="service", role=role, user_id=DEFAULT_ADMIN_ID
    )


MIXED_SOP = """\
name: park-investment-dd
description: 园区招商企业 360 背调
mcp_dependencies:
  - {server: qcc, required: true}
  - {server: internal_customer, required: true}
steps:
  - id: subject_verify
    type: mcp
    server: qcc
    tool: get_company_registration_info
    output: 主体档案
  - id: internal_customer
    type: mcp
    server: internal_customer
    tool: get_customer_360
    output: 内部客户事实
  - id: unpaid_query
    type: internal_query
    question_template: "{company_name} 过去 3 年欠费"
    entity_type: bill
    output: 欠费问数
report_template: |
  ## 事实数据
  ## AI 分析
"""

CONTRACT_SOP = """\
name: park-investment-dd
description: 园区招商企业 360 背调(结构化)
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: subject_verify
    type: mcp
    server: qcc
    tool: get_company_registration_info
    output: 主体档案
report_contract:
  schema:
    type: object
    required: [summary, external_facts, internal_facts]
    properties:
      summary: {type: array}
      external_facts: {type: array}
      internal_facts: {type: array}
"""


EVIDENCE_CONTRACT_SOP = """\
name: park-investment-evidence
description: 园区招商证据绑定
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: subject_verify
    type: mcp
    server: qcc
    tool: get_company_registration_info
report_contract:
  schema:
    type: object
    required: [summary, external_facts, internal_facts, evidence_refs]
    properties:
      summary: {type: array}
      external_facts: {type: array}
      internal_facts: {type: array}
      evidence_refs:
        type: array
        items:
          type: object
          required: [source_step, evidence_type, ref_id]
          additionalProperties: false
          properties:
            source_step: {type: string}
            evidence_type: {enum: [mcp_invocation, data_query]}
            ref_id: {type: string, format: uuid}
"""


QUERY_CONTRACT_SOP = """\
name: park-investment-query
description: 园区招商内部问数
steps:
  - id: unpaid_query
    type: internal_query
    question_template: "{company_name} 过去 3 年欠费"
    entity_type: bill
report_contract:
  schema:
    type: object
    required: [summary, external_facts, internal_facts, evidence_refs]
    properties:
      summary: {type: array}
      external_facts: {type: array}
      internal_facts: {type: array}
      evidence_refs: {type: array}
"""


async def _register_skill(db_session, *, sop: str, code: str = "dd") -> uuid.UUID:
    for srv in ("qcc", "internal_customer"):
        await MCPRegistryService(db_session).create(
            tenant_id=DEFAULT_TENANT_ID,
            code=srv,
            name=f"MCP-{srv}",
            server_url="https://mcp.example.com/rpc",
            created_by=DEFAULT_ADMIN_ID,
            role="super_admin",
        )
    svc = SkillRegistryService(db_session)
    skill = await svc.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        version="1.0.0",
        name=f"Skill-{code}",
        sop_template=sop,
        created_by=DEFAULT_ADMIN_ID,
        allowed_roles=["admin"],
        role="super_admin",
    )
    await svc.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id,
        enabled=True, role="super_admin",
    )
    await db_session.commit()
    return skill.id


def _mock_invocation() -> AsyncMock:
    async def _invoke_with_trace(*, server_code, tool_name, params, caller, tenant_id):
        return InvocationTrace(
            result={"server": server_code, "tool": tool_name},
            audit_id=uuid.uuid4(),
        )

    mock = AsyncMock()
    mock.invoke_with_trace = AsyncMock(side_effect=_invoke_with_trace)
    return mock


def _mock_query() -> AsyncMock:
    async def _query(*, question, entity_type, subject, caller, tenant_id):
        return {
            "ok": True,
            "result_rows": [{"unpaid": 0}],
            "audit_id": uuid.uuid4(),
        }

    return AsyncMock(side_effect=_query)


async def test_mixed_steps_carry_audit_ids(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="## 事实数据\nx"),
    )
    await _register_skill(db_session, sop=MIXED_SOP)
    runner = SkillRunner(
        db_session,
        invocation_service=_mock_invocation(),
        query_runner=_mock_query(),
    )
    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
        subject={"company_name": "ACME"}, caller=_caller(),
    )
    by_id = {s.id: s for s in result.steps}
    assert by_id["subject_verify"].invocation_audit_id is not None
    assert by_id["internal_customer"].invocation_audit_id is not None
    assert by_id["unpaid_query"].query_audit_id is not None


async def test_mcp_step_maps_company_name_to_searchkey_for_qcc(db_session, monkeypatch):
    """真实 QCC 工具入参是 ``searchKey``（AC-8 联调暴露）。subject 携带
    ``{company_name, credit_code}``；调 qcc server 的 mcp step 必须映射成
    ``searchKey=company_name``，否则 QCC 报 searchKey undefined。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="## 事实数据\nx"),
    )
    await _register_skill(db_session, sop=MIXED_SOP)
    invocation = _mock_invocation()
    runner = SkillRunner(
        db_session, invocation_service=invocation, query_runner=_mock_query(),
    )
    await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
        subject={"company_name": "ACME", "credit_code": "91X"}, caller=_caller(),
    )
    qcc_call = next(
        c for c in invocation.invoke_with_trace.call_args_list
        if c.kwargs["server_code"] == "qcc"
    )
    assert qcc_call.kwargs["params"] == {"searchKey": "ACME"}


async def test_mcp_step_passes_full_subject_to_internal_customer(db_session, monkeypatch):
    """internal_customer ``get_customer_360`` 要 ``company_name``+``credit_code``，
    与 confirmed_subject 形状一致，原样透传（不做 searchKey 映射）。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="## 事实数据\nx"),
    )
    await _register_skill(db_session, sop=MIXED_SOP)
    invocation = _mock_invocation()
    runner = SkillRunner(
        db_session, invocation_service=invocation, query_runner=_mock_query(),
    )
    await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
        subject={"company_name": "ACME", "credit_code": "91X"}, caller=_caller(),
    )
    ic_call = next(
        c for c in invocation.invoke_with_trace.call_args_list
        if c.kwargs["server_code"] == "internal_customer"
    )
    assert ic_call.kwargs["params"] == {"company_name": "ACME", "credit_code": "91X"}


async def test_internal_query_missing_subject_field_is_audited_tool_error(
    db_session, monkeypatch
):
    """question_template 缺主体字段时不得泄露为未审计 KeyError。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="unused"),
    )
    skill_id = await _register_skill(db_session, sop=QUERY_CONTRACT_SOP)
    runner = SkillRunner(
        db_session,
        invocation_service=_mock_invocation(),
        query_runner=_mock_query(),
    )

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"credit_code": "91110000"},
            caller=_caller(),
        )

    assert exc.value.error_code == "tool_error"
    row = await db_session.execute(
        text(
            "SELECT ok, error_code FROM metaedu.skill_execution_audit "
            "WHERE skill_id = :sid"
        ),
        {"sid": skill_id},
    )
    assert row.first() == (False, "tool_error")


@pytest.mark.parametrize(
    "question_template",
    ["{0}", "{company_name.missing}"],
)
async def test_internal_query_format_errors_are_audited_tool_errors(
    db_session, monkeypatch, question_template
):
    """str.format 的位置/属性错误不得泄露为未审计异常。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="unused"),
    )
    sop = QUERY_CONTRACT_SOP.replace(
        'question_template: "{company_name} 过去 3 年欠费"',
        f'question_template: "{question_template}"',
    )
    await _register_skill(db_session, sop=sop)
    runner = SkillRunner(
        db_session,
        invocation_service=_mock_invocation(),
        query_runner=_mock_query(),
    )

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    assert exc.value.error_code == "tool_error"


async def test_internal_query_unsuccessful_result_fails_closed(
    db_session, monkeypatch
):
    """QueryService ok=False 是工具失败，不能标成成功 step 交给 LLM。"""
    chat_mock = AsyncMock(return_value="unused")
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat", chat_mock
    )
    await _register_skill(db_session, sop=QUERY_CONTRACT_SOP)
    query = AsyncMock(
        return_value={
            "ok": False,
            "errors": ["semantic validation failed"],
            "audit_id": uuid.uuid4(),
        }
    )
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(), query_runner=query
    )

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    assert exc.value.error_code == "tool_error"
    chat_mock.assert_not_awaited()


async def test_internal_query_without_audit_id_fails_closed(db_session, monkeypatch):
    """问数结果没有 query_audit_log 绑定时不得进入报告合成。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value="unused"),
    )
    await _register_skill(db_session, sop=QUERY_CONTRACT_SOP)
    query = AsyncMock(return_value={"ok": True, "result_rows": []})
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(), query_runner=query
    )

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    assert exc.value.error_code == "tool_error"


async def test_structured_report_binds_evidence_refs_to_step_audits(
    db_session, monkeypatch
):
    """Runner 注入真实 audit id；LLM 只能声明 source_step，不能伪造 ref_id。"""
    payload = {
        "summary": ["a"],
        "external_facts": [],
        "internal_facts": [],
        "evidence_refs": [{"source_step": "subject_verify"}],
    }
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=json.dumps(payload)),
    )
    await _register_skill(db_session, sop=EVIDENCE_CONTRACT_SOP)
    invocation = _mock_invocation()
    runner = SkillRunner(db_session, invocation_service=invocation)

    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID,
        skill_code="dd",
        version="1.0.0",
        subject={"company_name": "ACME"},
        caller=_caller(),
    )

    step = result.steps[0]
    assert result.report_json is not None
    assert result.report_json["evidence_refs"] == [
        {
            "source_step": "subject_verify",
            "evidence_type": "mcp_invocation",
            "ref_id": str(step.invocation_audit_id),
        }
    ]


async def test_structured_report_binds_query_evidence_ref(db_session, monkeypatch):
    """internal_query 的 source_step 绑定 query_audit_id。"""
    payload = {
        "summary": [],
        "external_facts": [],
        "internal_facts": [],
        "evidence_refs": [{"source_step": "unpaid_query"}],
    }
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=json.dumps(payload)),
    )
    await _register_skill(db_session, sop=QUERY_CONTRACT_SOP)
    query = _mock_query()
    runner = SkillRunner(
        db_session, invocation_service=_mock_invocation(), query_runner=query
    )

    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID,
        skill_code="dd",
        version="1.0.0",
        subject={"company_name": "ACME"},
        caller=_caller(),
    )

    step = result.steps[0]
    assert result.report_json is not None
    assert result.report_json["evidence_refs"] == [
        {
            "source_step": "unpaid_query",
            "evidence_type": "data_query",
            "ref_id": str(step.query_audit_id),
        }
    ]


async def test_structured_report_rejects_unknown_evidence_step(
    db_session, monkeypatch
):
    """未知 source_step 无法绑定证据，必须 fail closed。"""
    payload = {
        "summary": [],
        "external_facts": [],
        "internal_facts": [],
        "evidence_refs": [{"source_step": "not_a_step"}],
    }
    sop = CONTRACT_SOP.replace(
        "required: [summary, external_facts, internal_facts]",
        "required: [summary, external_facts, internal_facts, evidence_refs]",
    )
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(side_effect=[json.dumps(payload), json.dumps(payload)]),
    )
    await _register_skill(db_session, sop=sop)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    assert exc.value.error_code == "report_invalid"


async def test_structured_report_prompt_includes_schema_and_evidence_rule(
    db_session, monkeypatch
):
    payload = {
        "summary": [],
        "external_facts": [],
        "internal_facts": [],
        "evidence_refs": [{"source_step": "subject_verify"}],
    }
    chat_mock = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat", chat_mock
    )
    await _register_skill(db_session, sop=EVIDENCE_CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())

    await runner.run(
        tenant_id=DEFAULT_TENANT_ID,
        skill_code="dd",
        version="1.0.0",
        subject={"company_name": "ACME"},
        caller=_caller(),
    )

    messages = chat_mock.await_args.args[0]
    prompt = "\n".join(message["content"] for message in messages)
    assert '"evidence_refs"' in prompt
    assert '"source_step"' in prompt
    assert "不要生成 ref_id" in prompt


async def test_invalid_report_value_is_not_written_to_audit(
    db_session, monkeypatch
):
    """schema 错误摘要不得把报告原值写入 digest-only 审计。"""
    secret_report_value = "CONFIDENTIAL_REPORT_VALUE"
    invalid = json.dumps(
        {
            "summary": secret_report_value,
            "external_facts": [],
            "internal_facts": [],
        }
    )
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=invalid),
    )
    skill_id = await _register_skill(db_session, sop=CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())

    with pytest.raises(SkillExecutionError):
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    row = await db_session.execute(
        text(
            "SELECT error_message FROM metaedu.skill_execution_audit "
            "WHERE skill_id = :sid"
        ),
        {"sid": skill_id},
    )
    assert secret_report_value not in row.scalar_one()


async def test_structured_report_non_object_fails_as_report_invalid(
    db_session, monkeypatch
):
    """合法 JSON 但非 object 时也必须走已审计 report_invalid。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=json.dumps([])),
    )
    await _register_skill(db_session, sop=CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())

    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="dd",
            version="1.0.0",
            subject={"company_name": "ACME"},
            caller=_caller(),
        )

    assert exc.value.error_code == "report_invalid"


async def test_structured_report_valid(db_session, monkeypatch):
    payload = {"summary": ["a"], "external_facts": [], "internal_facts": []}
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=json.dumps(payload)),
    )
    await _register_skill(db_session, sop=CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())
    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
        subject={"company_name": "ACME"}, caller=_caller(),
    )
    assert result.report_json == payload


async def test_structured_report_invalid_fails_after_retry(db_session, monkeypatch):
    """LLM 两次都输出不合 schema 的 JSON -> report_invalid(审计落行,不编造)。"""
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat",
        AsyncMock(return_value=json.dumps({"wrong": "shape"})),
    )
    skill_id = await _register_skill(db_session, sop=CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())
    with pytest.raises(SkillExecutionError) as exc:
        await runner.run(
            tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
            subject={"company_name": "ACME"}, caller=_caller(),
        )
    assert exc.value.error_code == "report_invalid"
    row = await db_session.execute(
        text(
            "SELECT ok, error_code FROM metaedu.skill_execution_audit "
            "WHERE skill_id = :sid"
        ),
        {"sid": skill_id},
    )
    r = row.first()
    assert r[0] is False and r[1] == "report_invalid"


async def test_structured_report_retry_succeeds(db_session, monkeypatch):
    """第一次不合 schema,重试后合法 -> 成功。"""
    good = json.dumps({"summary": [], "external_facts": [], "internal_facts": []})
    chat_mock = AsyncMock(side_effect=[json.dumps({"bad": 1}), good])
    monkeypatch.setattr(
        "app.contexts.skill_registry.application.skill_runner.chat", chat_mock
    )
    await _register_skill(db_session, sop=CONTRACT_SOP)
    runner = SkillRunner(db_session, invocation_service=_mock_invocation())
    result = await runner.run(
        tenant_id=DEFAULT_TENANT_ID, skill_code="dd", version="1.0.0",
        subject={"company_name": "ACME"}, caller=_caller(),
    )
    assert result.report_json == {"summary": [], "external_facts": [], "internal_facts": []}
    assert chat_mock.await_count == 2
