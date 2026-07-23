"""REQ-045 AC-9: 背调 SOP 真实端到端验收（manual / 真实验证，非 CI）。

本文件验证 REQ-045 的端到端执行能力 -- 以企业 360 背调 SOP
(``enterprise_360_dd``) 为首个真实 Skill，经真实企查查 QCC MCP + 真实 LLM
完成一次端到端执行。**手工验收**：仅在显式 opt-in 时运行（默认 skip），
不进入常规 CI，不冒充自动化测试。

两阶段：

1. ``test_skill_template_loads`` -- 加载首个背调 SOP 模板文件并通过
   ``SopTemplate.parse`` 结构校验（不联网，验证 seed 模板可用）。
2. ``test_due_diligence_runs_end_to_end`` -- 仅当额外设置
   ``RUN_SKILL_AC9=1`` + ``QCC_MCP_TOKEN`` + LLM provider key 时运行：
   在 dev/test 库注册 QCC server + 背调 skill -> ``SkillRunner.run`` 对一个
   公开样例企业真实执行 -> 断言结构化产物含事实 / AI 分析 / 待人工确认
   三分区、执行审计行齐备（subject/steps/report digest、duration、ok=True）、
   **secret 与企业敏感原文不进审计**。

安全约束：

- token 仅从 ``os.environ`` 读（与 ``CredentialRef.resolve`` 一致），
  永不写入文件、永不进入断言失败消息的明文。
- 验收证据只打印 digest 前 12 字符 + 步骤数 + 耗时 + ok + report 分区标题，
  不含 token、不含完整企业敏感数据。
- report 含企业敏感事实，仅打印分区标题验证结构，不打印 report 全文。

运行方式（手工）::

    export RUN_SKILL_AC9=1
    export QCC_MCP_TOKEN=<token>          # 仅 shell env，勿提交
    export QCC_AC9_COMPANY=<公开样例企业名>  # 如 "阿里巴巴"
    # LLM provider key 需已在 .env（MINIMAX_API_KEY 等）
    cd packages/server-python
    pytest tests/real_world/test_req045_due_diligence_acceptance.py -v -s
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationService,
)
from app.contexts.mcp_registry.infrastructure.mcp_server_repository import (
    MCPServerRepository,
)
from app.contexts.skill_registry.application.skill_registry_service import (
    SkillRegistryService,
)
from app.contexts.skill_registry.application.skill_runner import SkillRunner
from app.contexts.skill_registry.domain.skill import SopTemplate
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL, _ensure_seed

# AC-9 是手工验收：必须显式 opt-in（RUN_SKILL_AC9=1）+ QCC token，否则 skip。
# 与 REQ-044 AC-9 同款独立 opt-in 闸门，保证套件默认 hermetic。
load_dotenv()
QCC_TOKEN = os.environ.get("QCC_MCP_TOKEN")
_RUN_AC9 = os.environ.get("RUN_SKILL_AC9")
QCC_AC9_COMPANY = os.environ.get("QCC_AC9_COMPANY", "阿里巴巴")
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "contexts"
    / "skill_registry"
    / "templates"
    / "enterprise_360_dd.yaml"
)

pytestmark_skill = pytest.mark.skipif(
    not (_RUN_AC9 and QCC_TOKEN),
    reason="AC-9 manual: set RUN_SKILL_AC9=1 + QCC_MCP_TOKEN to run real due-diligence (not CI)",
)


def test_skill_template_loads():
    """phase 0（不联网）：首个背调 SOP 模板加载并通过结构校验。"""
    assert TEMPLATE_PATH.exists(), f"template not found: {TEMPLATE_PATH}"
    tpl_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    tpl = SopTemplate.parse(tpl_text)
    assert tpl.name == "enterprise-360-dd"
    assert len(tpl.steps) >= 9, f"expected >=9 steps, got {len(tpl.steps)}"
    # 三分区报告骨架对齐 REQ-046 AC-5
    report = tpl.report_template or ""
    assert "事实数据" in report
    assert "AI 分析" in report
    assert "待人工确认项" in report
    # 所有步骤绑定 qcc server
    assert all(s.server == "qcc" for s in tpl.steps)


@pytest_asyncio.fixture
async def ac9_session():
    """Real DB session for AC-9 (test metaedu DB at head 022).

    Ensure seed (tenant + super_admin) so mcp_servers / skills FK targets
    exist on a freshly ``make init-test-db``'d test DB; ``_ensure_seed`` is
    idempotent (no-op if seed rows already present). Aligns with REQ-044
    AC-9 ``engine`` fixture pattern.
    """
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    await _ensure_seed(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def ac9_qcc_skill(ac9_session: AsyncSession):
    """Register a real QCC server + the due-diligence skill, then clean up."""
    tenant_id = DEFAULT_TENANT_ID
    admin_id = DEFAULT_ADMIN_ID

    mcp_repo = MCPServerRepository(ac9_session)
    existing = await mcp_repo.get_by_code(tenant_id, "qcc")
    if existing is None:
        from app.contexts.mcp_registry.domain.mcp_server import MCPServer

        server = MCPServer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code="qcc",
            name="企查查 QCC",
            transport="streamable_http",
            server_url="https://agent.qcc.com/mcp/company/stream",
            credential_ref="QCC_MCP_TOKEN",
            allowed_roles=["admin", "data_admin", "super_admin"],
            enabled=True,
            timeout_ms=30000,
            is_active=True,
            created_by=admin_id,
        )
        await mcp_repo.create(server)
    else:
        # Prior test runs may have left a qcc row with a different
        # credential_ref / disabled; align it to the AC-9 token + enabled.
        await mcp_repo.update(
            tenant_id,
            existing.id,
            credential_ref="QCC_MCP_TOKEN",
            server_url="https://agent.qcc.com/mcp/company/stream",
            enabled=True,
            is_active=True,
        )
        await mcp_repo.set_enabled(tenant_id, existing.id, True)
    await ac9_session.commit()

    skill_service = SkillRegistryService(ac9_session)
    tpl_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    # Hard-clean any prior AC-9 skill rows + their audit rows so re-runs are
    # idempotent. The (tenant_id, code, version) UNIQUE constraint is not
    # is_active-aware, so soft-deleted prior rows would still collide.
    # AC-9 is scaffolding (not production audit history), so hard-delete is
    # appropriate here (FK-safe: audit rows deleted first).
    from sqlalchemy import text

    await ac9_session.execute(
        text(
            "DELETE FROM metaedu.skill_execution_audit "
            "WHERE skill_id IN (SELECT id FROM metaedu.skills "
            "WHERE tenant_id = :tid AND code = :code)"
        ),
        {"tid": tenant_id, "code": "enterprise_360_dd"},
    )
    await ac9_session.execute(
        text(
            "DELETE FROM metaedu.skills "
            "WHERE tenant_id = :tid AND code = :code"
        ),
        {"tid": tenant_id, "code": "enterprise_360_dd"},
    )
    await ac9_session.commit()

    skill = await skill_service.create(
        tenant_id=tenant_id,
        role="super_admin",
        created_by=admin_id,
        code="enterprise_360_dd",
        version="1.0.0",
        name="企业 360 背调",
        description="AC-9 真实端到端验收背调 SOP",
        sop_template=tpl_text,
        source_ref="https://agent.qcc.com/skill/v1/banking/credit-due-diligence-qcc/SKILL.md",
        allowed_roles=["admin", "data_admin", "super_admin"],
    )
    await skill_service.set_enabled(
        tenant_id=tenant_id, skill_id=skill.id, enabled=True, role="super_admin"
    )
    await ac9_session.commit()
    yield skill

    # Cleanup: hard-remove the AC-9 skill + its audit rows; leave QCC server.
    await ac9_session.execute(
        text(
            "DELETE FROM metaedu.skill_execution_audit "
            "WHERE skill_id = :sid"
        ),
        {"sid": skill.id},
    )
    await ac9_session.execute(text("DELETE FROM metaedu.skills WHERE id = :sid"), {"sid": skill.id})
    await ac9_session.commit()


@pytestmark_skill
@pytest.mark.external_network
@pytest.mark.asyncio
async def test_due_diligence_runs_end_to_end(ac9_qcc_skill):
    """phase 1（真实 QCC + 真实 LLM）：背调 SOP 端到端执行验收。

    断言：
    - SkillRunner.run 成功（不抛），返回 SkillResult 含 report + execution_audit_id
    - report 含事实 / AI 分析 / 待人工确认项三分区（REQ-046 AC-5 对齐）
    - 执行审计行 ok=True，subject/steps/report digest 齐备，duration_ms > 0
    - token（bare + Bearer 两形态）不出现在审计 error_message / 任何 digest 列
      （正常成功路径 error_message 为 None，这里同时断言 report_digest 非空）
    - 企业敏感原文（QCC_AC9_COMPANY）不进审计列（只可能在 report，不在 audit）
    """
    tenant_id = DEFAULT_TENANT_ID
    skill = ac9_qcc_skill

    # Fresh session for the runner (the fixture's session committed registration).
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    caller = InvocationCaller(
        caller_type="http_api",
        role="super_admin",
        user_id=DEFAULT_ADMIN_ID,
    )
    subject = {"searchKey": QCC_AC9_COMPANY}

    async with factory() as session:
        runner = SkillRunner(session, invocation_service=MCPInvocationService(session))
        result = await runner.run(
            tenant_id=tenant_id,
            skill_code=skill.code,
            version="1.0.0",
            subject=subject,
            caller=caller,
        )
        await session.commit()

    # ── 结构化产物 ──
    assert result.report, "report should not be empty"
    report = result.report
    for section in ("事实数据", "AI 分析", "待人工确认项"):
        assert section in report, f"report missing section: {section}"
    print(
        f"[AC-9] report sections OK: "
        f"facts={'事实数据' in report} analysis={'AI 分析' in report} "
        f"confirm={'待人工确认项' in report}"
    )

    # ── 执行审计 ──
    async with factory() as session:
        from app.contexts.skill_registry.infrastructure.skill_execution_audit_repository import (
            SkillExecutionAuditRepository,
        )

        audit_repo = SkillExecutionAuditRepository(session)
        rows, total = await audit_repo.list_by_skill(
            tenant_id, skill.id, limit=5, offset=0
        )
        assert total >= 1, "at least one execution audit row expected"
        audit = rows[0]
        assert audit.ok is True, f"audit ok=False error_code={audit.error_code}"
        assert audit.duration_ms > 0
        assert audit.subject_digest, "subject_digest missing"
        assert audit.steps_digest, "steps_digest missing"
        assert audit.report_digest, "report_digest missing"
        print(
            f"[AC-9] audit ok: duration_ms={audit.duration_ms} "
            f"subject_digest={audit.subject_digest[:12]}… "
            f"steps_digest={audit.steps_digest[:12]}… "
            f"report_digest={audit.report_digest[:12]}…"
        )

        # ── secret / 敏感原文不泄漏 ──
        leak_needles = [QCC_TOKEN, f"Bearer {QCC_TOKEN}"]
        leaked_cols = [
            col_name
            for col_name, val in [
                ("error_message", audit.error_message),
                ("subject_digest", audit.subject_digest),
                ("steps_digest", audit.steps_digest),
                ("report_digest", audit.report_digest),
                ("skill_code", audit.skill_code),
            ]
            if val is not None
            and any(n in str(val) for n in leak_needles if n)
        ]
        assert not leaked_cols, (
            f"TOKEN LEAKED into audit column(s): {leaked_cols} (values NOT printed)"
        )
        # defense-in-depth: token 也不应出现在 report 产物里（token 经 Bearer
        # header 去 MCP server，理论不到 LLM 合成路径；与 REQ-044 AC-9 一致）。
        assert QCC_TOKEN not in report, "TOKEN LEAKED into report product"
        # 企业敏感原文不进审计列（report 含事实是预期的，但 audit 列不应含公司名原文）
        sensitive_cols = [
            col_name
            for col_name, val in [
                ("error_message", audit.error_message),
                ("skill_code", audit.skill_code),
            ]
            if val is not None and QCC_AC9_COMPANY in str(val)
        ]
        assert not sensitive_cols, (
            f"company name leaked into audit column(s): {sensitive_cols}"
        )

    await engine.dispose()
    print("[AC-9] REQ-045 due-diligence end-to-end PASSED")
