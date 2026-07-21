"""Internal Customer MCP contract tests (REQ-046 PR-4).

Real PostgreSQL rows, in-process ASGI transport, and the production REQ-044
MCPClient validate the complete initialize -> tools/list/tools/call dialect.
No network or mock customer facts.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text

from app.config import settings
from app.contexts.mcp_registry.domain.mcp_server import AuthCredential, MCPServer
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPClient
from app.contexts.structured_data.infrastructure.dataset_repository import (
    DatasetRepository,
)
from app.internal_mcp.customer_service import InternalCustomerService
from app.main import app
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


async def _seed_dataset(
    session,
    *,
    catalog_id: uuid.UUID,
    entity_type: str,
    rows: list[dict],
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
) -> uuid.UUID:
    repo = DatasetRepository(session)
    dataset = await repo.create(
        tenant_id=tenant_id,
        name=f"test-{entity_type}-{uuid.uuid4().hex[:6]}",
        description=None,
        source_file=f"test/{entity_type}.xlsx",
        tags=["req046-test"],
        created_by=DEFAULT_ADMIN_ID,
        catalog_id=catalog_id,
        entity_type=entity_type,
    )
    await repo.bulk_insert_rows(tenant_id, dataset["id"], rows)
    await repo.update(
        dataset["id"],
        tenant_id,
        status="processed",
        row_count=len(rows),
    )
    return dataset["id"]


async def _seed_catalog(session, tenant_id=DEFAULT_TENANT_ID) -> uuid.UUID:
    row = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid ORDER BY created_at LIMIT 1"
        ),
        {"tid": tenant_id},
    )
    catalog_id = row.scalar_one_or_none()
    if catalog_id is not None:
        return catalog_id

    catalog_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.data_catalogs "
            "(id, tenant_id, code, name, entity_types, is_active, created_by, "
            "created_at, updated_at) VALUES "
            "(:id, :tid, :code, :name, CAST('[]' AS jsonb), true, :uid, :now, :now)"
        ),
        {
            "id": catalog_id,
            "tid": tenant_id,
            "code": f"park_{uuid.uuid4().hex[:8]}",
            "name": "REQ-046 园区测试库",
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )
    return catalog_id


async def _seed_customer_360(session) -> uuid.UUID:
    catalog_id = await _seed_catalog(session)
    customer_id = "C-REQ046-001"
    contract_id = "CT-REQ046-001"
    room_id = "R-REQ046-001"
    bill_id = "B-REQ046-001"
    payment_id = "P-REQ046-001"

    datasets = {
        "customer": [
            {
                "客户ID": customer_id,
                "客户名称": "示例科技有限公司",
                "统一社会信用代码": "91110000REQ046001",
                "所属行业": "软件和信息技术服务业",
            }
        ],
        "contract": [
            {
                "合同ID": contract_id,
                "客户ID": customer_id,
                "合同编号": "HT-001",
                "合同状态": "履行中",
                "项目ID": "PROJECT-REQ046-001",
            }
        ],
        "contract_property": [
            {"记录ID": "CP-001", "合同ID": contract_id, "房间ID": room_id}
        ],
        "lease_term": [
            {
                "条款ID": "LT-001",
                "合同ID": contract_id,
                "费用类型": "租金",
                "每期金额(元)": "12000",
            }
        ],
        "bill": [
            {
                "账单ID": bill_id,
                "合同ID": contract_id,
                "客户ID": customer_id,
                "应付金额(元)": "12000",
                "未付金额(元)": "0",
            }
        ],
        "payment": [
            {
                "流水ID": payment_id,
                "合同ID": contract_id,
                "客户ID": customer_id,
                "金额(元)": "12000",
            }
        ],
        "payment_allocation": [
            {
                "记录ID": "PA-001",
                "流水ID": payment_id,
                "账单ID": bill_id,
                "核销金额(元)": "12000",
            }
        ],
        "ticket": [
            {
                "工单ID": "TK-001",
                "房间ID": room_id,
                "项目ID": "PROJECT-REQ046-001",
                "工单类型": "维修",
                "状态": "已完成",
            }
        ],
        "cooperation_note": [
            {
                "跟进ID": "N-001",
                "客户ID": customer_id,
                "跟进阶段": "需求确认",
                "跟进记录": "[模拟待审核] 用于园区招商背调流程测试",
                "数据来源": "synthetic",
                "审核状态": "待审核",
            }
        ],
    }
    for entity_type, rows in datasets.items():
        await _seed_dataset(
            session,
            catalog_id=catalog_id,
            entity_type=entity_type,
            rows=rows,
        )
    await session.commit()
    return catalog_id


async def test_get_customer_360_joins_six_dimensions(db_session):
    await _seed_customer_360(db_session)

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="示例科技有限公司",
        credit_code="91110000REQ046001",
    )

    assert result["source_type"] == "imported_dataset"
    assert result["subject"]["客户ID"] == "C-REQ046-001"
    assert len(result["contract_history"]) == 1
    assert {row["record_type"] for row in result["lease_history"]} == {
        "contract_property",
        "lease_term",
    }
    assert {row["record_type"] for row in result["payment_history"]} == {
        "bill",
        "payment",
        "payment_allocation",
    }
    assert result["service_tickets"][0]["工单ID"] == "TK-001"
    assert result["cooperation_notes"][0]["数据来源"] == "synthetic"


async def test_latest_processed_dataset_wins_for_same_entity_type(db_session):
    catalog_id = await _seed_catalog(db_session)
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        rows=[{"客户ID": "OLD", "客户名称": "版本企业"}],
    )
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        rows=[{"客户ID": "NEW", "客户名称": "版本企业"}],
    )
    await db_session.commit()

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="版本企业",
    )

    assert result["subject"]["客户ID"] == "NEW"


async def test_connected_dimension_without_company_rows_returns_empty_list(db_session):
    catalog_id = await _seed_catalog(db_session)
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        rows=[{"客户ID": "C-EMPTY", "客户名称": "无合同企业"}],
    )
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="contract",
        rows=[{"合同ID": "OTHER-CONTRACT", "客户ID": "OTHER-CUSTOMER"}],
    )
    await db_session.commit()

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="无合同企业",
    )

    assert result["contract_history"] == []


async def test_credit_code_miss_falls_back_to_exact_company_name(db_session):
    catalog_id = await _seed_catalog(db_session)
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        rows=[
            {
                "客户ID": "C-FALLBACK",
                "客户名称": "名称回退企业",
                "统一社会信用代码": "",
            }
        ],
    )
    await db_session.commit()

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="名称回退企业",
        credit_code="QCC-CODE-NOT-IN-INTERNAL-DATA",
    )

    assert result["subject"]["客户ID"] == "C-FALLBACK"


async def test_missing_dimension_is_explicit_not_connected(db_session):
    catalog_id = await _seed_catalog(db_session)
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        rows=[{"客户ID": "C-2", "客户名称": "缺维企业"}],
    )
    await db_session.commit()

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="缺维企业",
    )

    assert result["subject"]["客户ID"] == "C-2"
    assert result["cooperation_notes"] == {
        "status": "not_connected",
        "note": "cooperation_note 数据集未接入或未处理完成",
    }
    assert result["contract_history"]["status"] == "not_connected"


async def test_customer_lookup_is_tenant_scoped(db_session):
    other_tenant = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :name, 'shared', true, :now, :now)"
        ),
        {"id": other_tenant, "name": f"other-{other_tenant.hex[:8]}", "now": now},
    )
    catalog_id = await _seed_catalog(db_session, tenant_id=other_tenant)
    await _seed_dataset(
        db_session,
        catalog_id=catalog_id,
        entity_type="customer",
        tenant_id=other_tenant,
        rows=[{"客户ID": "OTHER", "客户名称": "跨租户企业"}],
    )
    await db_session.commit()

    result = await InternalCustomerService(db_session).get_customer_360(
        tenant_id=DEFAULT_TENANT_ID,
        company_name="跨租户企业",
    )

    assert result["subject"]["status"] == "not_connected"


async def test_mcp_client_contract_lists_and_calls_tool(
    client, db_session, monkeypatch
):
    await _seed_customer_360(db_session)
    monkeypatch.setattr(settings, "internal_mcp_tenant_id", str(DEFAULT_TENANT_ID))
    monkeypatch.setattr(settings, "internal_mcp_token", "test-internal-token")
    transport = httpx.ASGITransport(app=app)
    mcp_client = MCPClient(transport=transport)
    server = MCPServer(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        code="internal_customer",
        name="Internal Customer MCP",
        server_url="http://test/internal-mcp",
        transport="streamable_http",
        enabled=True,
    )
    credential = AuthCredential("Bearer test-internal-token")

    tools = await mcp_client.list_tools(server, credential)
    assert [tool["name"] for tool in tools] == ["get_customer_360"]

    call = await mcp_client.call_tool(
        server,
        credential,
        "get_customer_360",
        {
            "company_name": "示例科技有限公司",
            "credit_code": "91110000REQ046001",
        },
    )
    assert call.ok is True
    payload = call.result["structuredContent"]
    assert payload["subject"]["客户ID"] == "C-REQ046-001"
    assert payload["source_type"] == "imported_dataset"


async def test_internal_mcp_rejects_missing_bearer(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_mcp_tenant_id", str(DEFAULT_TENANT_ID))
    monkeypatch.setattr(settings, "internal_mcp_token", "test-internal-token")

    response = await client.post(
        "/internal-mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 401
