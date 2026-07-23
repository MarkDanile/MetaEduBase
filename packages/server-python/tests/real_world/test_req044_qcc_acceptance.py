"""REQ-044 AC-9: QCC 真实 MCP 调用验收（manual / 真实验证，非 CI）。

本文件验证 REQ-044 的端到端真实调用能力 -- 以企查查 qcc-company MCP
server 为首个真实接入对象。**手工验收**：仅在 ``QCC_MCP_TOKEN`` 环境变量
存在时运行（默认 skip），不进入常规 CI，不冒充自动化测试。

两阶段：

1. ``test_qcc_list_tools_discovers_tools`` -- 经 ``MCPClient.list_tools``
   真实连通 QCC ``/mcp/company/stream`` 端点，发现并打印工具清单 +
   inputSchema。验证 streamable_http transport 对 QCC /stream 端点可用。
2. ``test_qcc_invoke_audited_no_secret_leak`` -- 仅当额外设置
   ``QCC_AC9_TOOL`` + ``QCC_AC9_PARAMS`` 时运行：经
   ``MCPInvocationService.invoke`` 真实调用一个 QCC 工具，断言审计行
   ``ok=True`` + ``params_digest`` / ``response_digest`` / ``duration_ms``
   齐备，且 **token 值不出现在任何审计列 / invoke 结果**。

安全约束：

- token 仅从 ``os.environ`` 读（与 ``CredentialRef.resolve`` 一致），
  永不写入文件、永不进入断言失败消息的明文（leak 断言用固定文案，
  不打印被检值）。
- 验收证据只打印 digest 前 12 字符 + tool 名 + 耗时 + ok，不含 token、
  不含企业敏感原始数据。
- **token 曾在交付通信中明文传输，验收后必须轮换。**

运行方式（手工）::

    # phase 1: 发现工具
    export QCC_MCP_TOKEN=<token>   # 仅 shell env，勿提交
    cd packages/server-python
    pytest tests/real_world/test_req044_qcc_acceptance.py -v -s

    # phase 2: 真实调用（用 phase 1 输出的 tool 名 + 构造参数）
    export QCC_AC9_TOOL=<tool_name>
    export QCC_AC9_PARAMS='{"keyword": "<public company name>"}'
    pytest tests/real_world/test_req044_qcc_acceptance.py \
        ::test_qcc_invoke_audited_no_secret_leak -v -s
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
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
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.mcp_registry.domain.mcp_server import CredentialRef
from app.contexts.mcp_registry.infrastructure.invocation_audit_repository import (
    InvocationAuditRepository,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPClient
from app.contexts.mcp_registry.infrastructure.mcp_server_repository import (
    MCPServerRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL, _ensure_seed

# Load .env (gitignored) into os.environ so QCC_MCP_TOKEN is visible both to
# the skip gate below and to CredentialRef.resolve() at call time. The app's
# pydantic-settings only populates declared Settings fields from .env, not
# arbitrary os.environ keys -- so an explicit load_dotenv is needed for the
# credential_ref env-key resolution path to work in dev. load_dotenv does not
# override already-set env vars, so a real shell env still wins.
load_dotenv()

# AC-9 是手工验收：必须显式 opt-in（RUN_QCC_AC9=1）且有真实 token，否则 skip。
# 只查 token 不够 — .env 持久化 token 会让本地套件每次都对 QCC 发真实请求
# （QCC 不可达 / token 轮换后本地套件会红），所以用独立 opt-in 闸门保证套件
# 默认 hermetic，AC-9 只在显式运行时执行真实调用。
QCC_TOKEN = os.environ.get("QCC_MCP_TOKEN")
_RUN_AC9 = os.environ.get("RUN_QCC_AC9")
QCC_SERVER_URL = "https://agent.qcc.com/mcp/company/stream"
QCC_SERVER_CODE = "qcc_company_ac9"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (_RUN_AC9 and QCC_TOKEN),
        reason="AC-9 manual: set RUN_QCC_AC9=1 + QCC_MCP_TOKEN to run real QCC call (not CI)",
    ),
]


@pytest_asyncio.fixture
async def engine():
    """Test DB engine with seed ensured (tenant + super_admin)."""
    e = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    await _ensure_seed(e)
    yield e
    await e.dispose()


async def _reset_qcc_server(session: AsyncSession) -> None:
    """Hard-delete any prior AC-9 qcc server + its audit rows (FK-safe order).

    AC-9 is repeatable: each run registers a fresh server rather than
    accumulating soft-deleted rows that would trip the (tenant_id, code)
    unique constraint.
    """
    await session.execute(
        text(
            "DELETE FROM metaedu.mcp_invocation_audit "
            "WHERE server_id IN (SELECT id FROM metaedu.mcp_servers "
            "WHERE tenant_id = :tid AND code = :code)"
        ),
        {"tid": DEFAULT_TENANT_ID, "code": QCC_SERVER_CODE},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.mcp_servers "
            "WHERE tenant_id = :tid AND code = :code"
        ),
        {"tid": DEFAULT_TENANT_ID, "code": QCC_SERVER_CODE},
    )
    await session.commit()


async def _register_qcc(session: AsyncSession):
    """Register the qcc-company server fresh; return the MCPServer domain obj."""
    await _reset_qcc_server(session)
    service = MCPRegistryService(session)
    server = await service.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=QCC_SERVER_CODE,
        name="企查查-企业信息 (AC-9)",
        server_url=QCC_SERVER_URL,
        transport="streamable_http",
        credential_ref="QCC_MCP_TOKEN",
        allowed_roles=["super_admin"],
        timeout_ms=30000,
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    await session.commit()
    return server


async def test_qcc_list_tools_discovers_tools(engine):
    """AC-9 phase 1: real list_tools against QCC /stream endpoint.

    Verifies the streamable_http transport (initialize -> tools/list)
    works end-to-end against QCC's real endpoint, and surfaces the tool
    catalog for phase 2.
    """
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        server = await _register_qcc(session)
        cred = (
            CredentialRef(server.credential_ref).resolve()
            if server.credential_ref
            else None
        )
        client = MCPClient()
        tools = await client.list_tools(server, cred)

    assert tools, "QCC list_tools returned an empty tool list"
    print(
        f"\n[AC-9 phase 1] QCC qcc-company exposed {len(tools)} tool(s):",
        file=sys.stderr,
    )
    for t in tools:
        name = t.get("name")
        schema = t.get("inputSchema", {})
        print(
            f"  - {name}: {json.dumps(schema, ensure_ascii=False)}",
            file=sys.stderr,
        )


async def test_qcc_invoke_audited_no_secret_leak(engine):
    """AC-9 phase 2: real invoke through MCPInvocationService -> audit row.

    Asserts the full registry -> client -> audit pipeline produces an
    ``ok=True`` audit row with digests + duration, and that the resolved
    token value never appears in any persisted audit column or the
    invoke result.
    """
    tool = os.environ.get("QCC_AC9_TOOL")
    params_raw = os.environ.get("QCC_AC9_PARAMS")
    if not tool or params_raw is None:
        pytest.skip("set QCC_AC9_TOOL + QCC_AC9_PARAMS to run real invoke")
    params = json.loads(params_raw)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # register + enable + invoke (all through the service layer)
    async with factory() as session:
        server = await _register_qcc(session)
        service = MCPRegistryService(session)
        if not server.enabled:
            await service.set_enabled(
                tenant_id=DEFAULT_TENANT_ID,
                server_id=server.id,
                enabled=True,
                role="super_admin",
            )
            await session.commit()
        inv = MCPInvocationService(session)
        result = await inv.invoke(
            tenant_id=DEFAULT_TENANT_ID,
            server_code=QCC_SERVER_CODE,
            tool_name=tool,
            params=params,
            caller=InvocationCaller(
                caller_type="ac9:manual",
                role="super_admin",
                user_id=DEFAULT_ADMIN_ID,
            ),
        )
        await session.commit()

    # fetch the latest audit row for this server
    async with factory() as session:
        repo = MCPServerRepository(session)
        server = await repo.get_by_code(DEFAULT_TENANT_ID, QCC_SERVER_CODE)
        rows, total = await InvocationAuditRepository(session).list_by_server(
            DEFAULT_TENANT_ID, server.id, limit=1, offset=0
        )

    assert total >= 1, "no audit row written for the invoke"
    audit = rows[0]
    assert audit.ok is True, (
        f"invoke failed: error_code={audit.error_code} "
        "(msg not printed to avoid leaking credential)"
    )
    assert audit.tool_name == tool
    assert audit.duration_ms >= 0, "duration_ms must be recorded"
    assert audit.params_digest, "params_digest must be persisted"
    assert audit.response_digest, "response_digest must be persisted for an ok call"

    # CRITICAL security invariant: the credential must not appear in ANY audit
    # column, in either form the wire could carry (bare secret or the composed
    # "Bearer <secret>" header value). Fixed failure message -- never print the
    # leaked value. Use module-level QCC_TOKEN directly (no local binding) so a
    # failure traceback can't surface the credential as a local variable.
    leak_needles = [QCC_TOKEN, f"Bearer {QCC_TOKEN}"]
    leaked_cols = [
        col_name
        for col_name, val in [
            ("error_message", audit.error_message),
            ("params_digest", audit.params_digest),
            ("response_digest", audit.response_digest),
            ("server_code", audit.server_code),
            ("tool_name", audit.tool_name),
            ("caller_type", audit.caller_type),
        ]
        if val is not None and any(n in str(val) for n in leak_needles)
    ]
    assert not leaked_cols, (
        f"TOKEN LEAKED into audit column(s): {leaked_cols} "
        "(column values NOT printed to avoid leaking the credential)"
    )

    # Defensive: the credential must not be echoed in the tool's result data
    # either (again, bare or composed form).
    result_str = json.dumps(result, ensure_ascii=False, default=str)
    assert not any(n in result_str for n in leak_needles), (
        "credential leaked into invoke result (result NOT printed to avoid leaking it)"
    )

    print(
        f"\n[AC-9 phase 2] invoke ok: tool={tool} duration_ms={audit.duration_ms} "
        f"params_digest={audit.params_digest[:12]}... "
        f"response_digest={audit.response_digest[:12]}... ok={audit.ok}",
        file=sys.stderr,
    )
