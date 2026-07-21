"""AC-4 end-to-end: internal_query step over the real imported_dataset pipeline.

REQ-046 PR-5 / Slice 4 (spec §4.5 / AC-4): the园区招商背调 SKILL must route >= 3
due-diligence questions through the REQ-052 semantic layer and bind each result
to its ``query_audit_log`` row for the evidence chain. This drives the REAL
:class:`SkillRunner` with the production ``query_runner`` adapter, a real
persisted semantic model + dataset rows, and a real imported_dataset query —
only the two LLM leaves (query planner + report synthesis) are stubbed.

Covers the three canonical DD angles (欠费 / 租约到期 / 工单满意度) and the
AC-4 contract that each internal_query step carries a ``query_audit_id``.
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


@pytest.fixture(autouse=True)
async def _clean(db_session):
    for stmt in (
        "DELETE FROM metaedu.skill_execution_audit WHERE tenant_id = :tid",
        "DELETE FROM metaedu.skills WHERE tenant_id = :tid",
        "DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid",
        "DELETE FROM metaedu.query_audit_log WHERE tenant_id = :tid",
        "DELETE FROM metaedu.role_permissions WHERE tenant_id = :tid AND role = 'admin'",
        "DELETE FROM metaedu.dataset_rows WHERE tenant_id = :tid",
        "DELETE FROM metaedu.datasets WHERE tenant_id = :tid AND name = 'dd-e2e-bill'",
    ):
        await db_session.execute(text(stmt), {"tid": DEFAULT_TENANT_ID})
    await db_session.flush()
    yield


@pytest.fixture
async def sample_dataset(db_session):
    """Persist a bill dataset + 2 rows in the education catalog (mirrors the
    structured_data conftest fixture, which is not visible from this context)."""
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    catalog_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    cnames = json.dumps(["company_name", "amount", "billing_date"])
    ctypes = json.dumps(["str", "float", "date"])
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, catalog_id, name, column_names, column_types, "
            f"row_count, status, kg_status, sort_order, created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, 'dd-e2e-bill', '{cnames}'::jsonb, "
            f"'{ctypes}'::jsonb, 2, 'processed', 'done', 0, :uid, :now, :now)"
        ),
        {"id": dataset_id, "tid": DEFAULT_TENANT_ID, "cid": catalog_id,
         "uid": DEFAULT_ADMIN_ID, "now": now},
    )
    for i, payload in enumerate(
        [
            {"company_name": "ACME", "amount": 100.0, "billing_date": "2026-01-01"},
            {"company_name": "BetaCorp", "amount": 50.5, "billing_date": "2026-02-01"},
        ]
    ):
        lit = json.dumps(payload)
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
    yield {"id": dataset_id, "tenant_id": DEFAULT_TENANT_ID}


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


async def test_internal_query_three_dd_questions_end_to_end(
    db_session, sample_dataset, monkeypatch
):
    """AC-4: 3 internal_query steps hit the real imported_dataset pipeline and
    each binds a real query_audit_log id; the report carries data_query evidence."""
    catalog_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(catalog_id))

    # Three DD angles; all point at the same sample bill dataset for the query
    # (each entity_type gets its own active semantic model over that dataset).
    # Each model carries a unique marker column so the stubbed planner can tell
    # which entity_type it is planning for from the system prompt content.
    entity_types = ["bill", "lease_term", "ticket"]
    marker = {"bill": "bill_marker", "lease_term": "lease_marker", "ticket": "ticket_marker"}
    for et in entity_types:
        await _persist_model(
            db_session,
            sample_dataset["id"],
            entity_type=et,
            catalog_id=catalog_id,
            columns=["company_name", "amount", "billing_date", marker[et]],
        )
    await _seed_rbac_visible(db_session, entity_types)
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
        system = messages[0]["content"] if messages else ""
        for et, mk in marker.items():
            if mk in system:
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
            subject={"company_name": "ACME"},
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
