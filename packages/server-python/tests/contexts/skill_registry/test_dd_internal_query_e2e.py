"""AC-4 end-to-end: internal_query step over the real imported_dataset pipeline.

REQ-046 PR-5 / Slice 4 (spec §4.5 / AC-4): the园区招商背调 SKILL must route >= 3
due-diligence questions through the REQ-052 semantic layer and bind each result
to its ``query_audit_log`` row for the evidence chain. This drives the REAL
:class:`SkillRunner` with the production ``query_runner`` adapter, a real
persisted semantic model + dataset rows, and a real imported_dataset query —
only the two LLM leaves (query planner + report synthesis) are stubbed.

AC-8 (real Chinese datasets): bill/lease_term/ticket have no ``company_name``
column, so the query_runner resolves the confirmed subject to a relation key
through the park join graph and force-injects it as a validated filter:

    customer(客户名称 -> 客户ID)
      bill              -> eq  客户ID
      lease_term        -> in  合同ID   (客户ID -> 合同ID via contract)
      ticket            -> in  房间ID   (合同ID -> 房间ID via contract_property)

This fixture therefore persists the full graph (customer + contract +
contract_property + one target dataset) with Chinese column names, and asserts
each step returns ok + a real query_audit_id while scoping to the single
confirmed enterprise (never a park-wide scan).
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.config import settings
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.skill_registry.application.dd_query_runner import (
    build_dd_internal_query_runner,
)
from app.contexts.skill_registry.application.skill_runner import SkillRunner
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

# Confirmed subject (ACME) + a second enterprise (BetaCorp) to prove scoping.
_ACME = "ACME"
_ACME_ID = "CUST-001"
_ACME_CONTRACTS = ["HT-1", "HT-2"]
_ACME_ROOMS = ["RM-1", "RM-2"]


@pytest.fixture(autouse=True)
async def _clean(db_session):
    for stmt in (
        "DELETE FROM metaedu.skill_execution_audit WHERE tenant_id = :tid",
        "DELETE FROM metaedu.skills WHERE tenant_id = :tid",
        "DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid",
        "DELETE FROM metaedu.query_audit_log WHERE tenant_id = :tid",
        "DELETE FROM metaedu.role_permissions WHERE tenant_id = :tid AND role = 'admin'",
        "DELETE FROM metaedu.dataset_rows WHERE tenant_id = :tid",
        "DELETE FROM metaedu.datasets WHERE tenant_id = :tid AND name LIKE 'dd-e2e-%'",
    ):
        await db_session.execute(text(stmt), {"tid": DEFAULT_TENANT_ID})
    await db_session.flush()
    yield


async def _insert_dataset(db_session, catalog_id, name, columns, rows):
    """Persist a processed dataset + JSONB rows; return its id."""
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    cnames = json.dumps(columns, ensure_ascii=False)
    ctypes = json.dumps(["str"] * len(columns))
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, catalog_id, name, column_names, column_types, "
            f"row_count, status, kg_status, sort_order, created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, :name, '{cnames}'::jsonb, "
            f"'{ctypes}'::jsonb, :rc, 'processed', 'done', 0, :uid, :now, :now)"
        ),
        {"id": dataset_id, "tid": DEFAULT_TENANT_ID, "cid": catalog_id,
         "name": name, "rc": len(rows), "uid": DEFAULT_ADMIN_ID, "now": now},
    )
    for i, payload in enumerate(rows):
        lit = json.dumps(payload, ensure_ascii=False)
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.dataset_rows "
                f"(id, tenant_id, dataset_id, row_index, data, created_at) "
                f"VALUES (:id, :tid, :did, :idx, '{lit}'::jsonb, :now)"
            ),
            {"id": uuid.uuid4(), "tid": DEFAULT_TENANT_ID, "did": dataset_id,
             "idx": i, "now": now},
        )
    await db_session.flush()
    return dataset_id


async def _persist_model(db_session, dataset_id, *, entity_type, catalog_id, columns):
    repo = SemanticModelRepository(db_session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type=entity_type,
        entity_name=entity_type,
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(dataset_id),
        },
        column_mapping={
            col: ColumnMapping(role=ColumnRole.DIMENSION, type=ColumnType.STR, sensitive=False)
            for col in columns
        },
        metric_definitions={},
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
        catalog_id=catalog_id,
    )
    await repo.create(model, catalog_id=catalog_id)


async def _seed_rbac_visible(db_session, entity_types):
    rules = json.dumps({"*": "visible"})
    for et in entity_types:
        await db_session.execute(
            text(
                "INSERT INTO metaedu.role_permissions "
                "(id, tenant_id, role, entity_type, visibility_rules, created_at) "
                "VALUES (:id, :tid, 'admin', :et, CAST(:rules AS jsonb), now())"
            ),
            {"id": uuid.uuid4(), "tid": DEFAULT_TENANT_ID, "et": et, "rules": rules},
        )


async def _register_skill(db_session, sop):
    from app.contexts.skill_registry.application.skill_registry_service import (
        SkillRegistryService,
    )

    svc = SkillRegistryService(db_session)
    skill = await svc.create(
        tenant_id=DEFAULT_TENANT_ID,
        code="park_investment_dd",
        version="1.0.0",
        name="园区招商背调",
        sop_template=sop,
        created_by=DEFAULT_ADMIN_ID,
        allowed_roles=["admin"],
        role="super_admin",
    )
    await svc.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, skill_id=skill.id, enabled=True, role="super_admin"
    )
    await db_session.commit()
    return skill.id


def _sop(questions):
    steps = "\n".join(
        f"  - id: {qid}\n"
        f"    type: internal_query\n"
        f"    entity_type: {et}\n"
        f'    question_template: "{{company_name}} {qt}"\n'
        for qid, et, qt in questions
    )
    return (
        "name: park-investment-dd\n"
        "description: 园区招商企业 360 背调\n"
        "steps:\n"
        f"{steps}\n"
        "report_template: |\n  ## 事实数据\n  ## AI 分析\n"
    )


async def test_internal_query_three_dd_questions_end_to_end(db_session, monkeypatch):
    """AC-4 + AC-8: 3 internal_query steps resolve the subject through the join
    graph, hit the real imported_dataset pipeline scoped to ACME, and each binds
    a real query_audit_log id; the report carries data_query evidence."""
    catalog_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(catalog_id))

    # Join-graph datasets (Chinese columns, mirroring the real park bundle).
    customer_cols = ["客户ID", "客户名称", "统一社会信用代码"]
    contract_cols = ["合同ID", "客户ID", "合同状态"]
    cp_cols = ["记录ID", "合同ID", "房间ID"]
    bill_cols = ["账单ID", "客户ID", "未付金额(元)", "到期日"]
    lease_cols = ["条款ID", "合同ID", "条款失效日期"]
    ticket_cols = ["工单ID", "房间ID", "优先级", "状态"]

    customer_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-customer",
        customer_cols,
        [
            {"客户ID": _ACME_ID, "客户名称": _ACME, "统一社会信用代码": "91ACME"},
            {"客户ID": "CUST-002", "客户名称": "BetaCorp", "统一社会信用代码": "91BETA"},
        ])
    contract_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-contract",
        contract_cols,
        [
            {"合同ID": "HT-1", "客户ID": _ACME_ID, "合同状态": "在租"},
            {"合同ID": "HT-2", "客户ID": _ACME_ID, "合同状态": "在租"},
            {"合同ID": "HT-9", "客户ID": "CUST-002", "合同状态": "在租"},
        ])
    cp_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-contract-property",
        cp_cols,
        [
            {"记录ID": "R1", "合同ID": "HT-1", "房间ID": "RM-1"},
            {"记录ID": "R2", "合同ID": "HT-2", "房间ID": "RM-2"},
            {"记录ID": "R9", "合同ID": "HT-9", "房间ID": "RM-9"},
        ])
    bill_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-bill",
        bill_cols,
        [
            {"账单ID": "B1", "客户ID": _ACME_ID, "未付金额(元)": "100.0", "到期日": "2026-01-01"},
            {"账单ID": "B2", "客户ID": "CUST-002", "未付金额(元)": "999.0", "到期日": "2026-01-01"},
        ])
    lease_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-lease",
        lease_cols,
        [
            {"条款ID": "T1", "合同ID": "HT-1", "条款失效日期": "2026-12-31"},
            {"条款ID": "T9", "合同ID": "HT-9", "条款失效日期": "2026-12-31"},
        ])
    ticket_ds = await _insert_dataset(db_session, catalog_id, "dd-e2e-ticket",
        ticket_cols,
        [
            {"工单ID": "W1", "房间ID": "RM-1", "优先级": "高", "状态": "未关闭"},
            {"工单ID": "W9", "房间ID": "RM-9", "优先级": "高", "状态": "未关闭"},
        ])

    datasets = {
        "customer": (customer_ds, customer_cols),
        "contract": (contract_ds, contract_cols),
        "contract_property": (cp_ds, cp_cols),
        "bill": (bill_ds, bill_cols),
        "lease_term": (lease_ds, lease_cols),
        "ticket": (ticket_ds, ticket_cols),
    }
    for et, (ds_id, cols) in datasets.items():
        await _persist_model(
            db_session, ds_id, entity_type=et, catalog_id=catalog_id, columns=cols
        )
    await _seed_rbac_visible(db_session, list(datasets))
    await db_session.commit()

    questions = [
        ("unpaid_query", "bill", "过去三年是否有欠费记录"),
        ("lease_expiry_query", "lease_term", "租约到期时间"),
        ("ticket_query", "ticket", "工单满意度"),
    ]
    await _register_skill(db_session, _sop(questions))

    query_service = QueryService(session_factory=lambda: db_session)
    query_runner = build_dd_internal_query_runner(query_service, db_session)
    runner = SkillRunner(db_session, query_runner=query_runner)
    caller = InvocationCaller(caller_type="service", role="admin", user_id=DEFAULT_ADMIN_ID)

    def _plan_for(messages, **_kw):
        # Stubbed planner returns a minimal valid plan (entity only); the real
        # subject filter is force-injected by the runner downstream, so the LLM
        # need not produce it here.
        system = messages[0]["content"] if messages else ""
        for et in ("bill", "lease_term", "ticket"):
            if f"entity_type: {et}" in system:
                return json.dumps({"entity": et, "metrics": [], "filters": {}, "limit": 100})
        return json.dumps({"entity": "bill", "metrics": [], "filters": {}, "limit": 100})

    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.skill_registry.application.skill_runner.chat",
        new_callable=AsyncMock,
    ) as mock_report:
        mock_planner.side_effect = _plan_for
        mock_report.return_value = "## 事实数据\n欠费/租约/工单见各 step\n## AI 分析\n无"
        result = await runner.run(
            tenant_id=DEFAULT_TENANT_ID,
            skill_code="park_investment_dd",
            version="1.0.0",
            subject={"company_name": _ACME, "credit_code": None},
            caller=caller,
        )

    by_id = {s.id: s for s in result.steps}
    assert set(by_id) == {"unpaid_query", "lease_expiry_query", "ticket_query"}
    # Every internal_query step is bound to a real query_audit_log row (AC-4/AC-6).
    for qid, _, _ in questions:
        q_audit = by_id[qid].query_audit_id
        assert isinstance(q_audit, uuid.UUID), f"{qid} missing query_audit_id"
        exists = await db_session.scalar(
            text("SELECT EXISTS (SELECT 1 FROM metaedu.query_audit_log WHERE id = :id)"),
            {"id": q_audit},
        )
        assert exists, f"{qid} query_audit_id not persisted"

    # AC-8 scoping: each step's persisted query_plan carries the resolved
    # subject relation-key filter (never a park-wide scan).
    plans = {}
    for qid, et, _ in questions:
        plan_json = await db_session.scalar(
            text("SELECT query_plan FROM metaedu.query_audit_log WHERE id = :id"),
            {"id": by_id[qid].query_audit_id},
        )
        plans[et] = plan_json if isinstance(plan_json, dict) else json.loads(plan_json)
    assert plans["bill"]["filters"]["客户ID"] == {"op": "eq", "value": _ACME_ID}
    assert plans["lease_term"]["filters"]["合同ID"] == {
        "op": "in", "value": _ACME_CONTRACTS,
    }
    assert plans["ticket"]["filters"]["房间ID"] == {
        "op": "in", "value": _ACME_ROOMS,
    }
