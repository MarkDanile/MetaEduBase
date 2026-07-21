"""QueryService.ask returns audit_id (REQ-046 PR-3).

REQ-046 evidence chain (spec §4.5 / AC-4): the intelligent-data-query adapter
must bind each 问数 result to its ``query_audit_log`` row. ``QueryService.ask``
now surfaces ``audit_id`` (success + validator-rejected paths) so the REQ-046
runner can record evidence_refs without the audit table exposing raw rows.
Real DB session, stubbed planner / adapter / explainer, real audit repo.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.interfaces.api.query_router import AskResponse
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


def _make_semantic_model(
    dataset_id: uuid.UUID, *, catalog_id: uuid.UUID | None = None
) -> SemanticModel:
    now = datetime.now(UTC).replace(tzinfo=None)
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR, sensitive=False
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC, type=ColumnType.FLOAT, sensitive=True
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
        catalog_id=catalog_id,
    )


def _stub_query_service(session) -> QueryService:
    qs = QueryService(session_factory=lambda: session)
    qs._planner = AsyncMock()
    qs._planner.plan = AsyncMock(
        return_value={"entity": "bill", "metrics": ["total_amount"], "filters": {}}
    )
    fake_adapter = AsyncMock()
    fake_adapter.query = AsyncMock(
        return_value=[{"company_name": "ACME", "amount": 100.0}]
    )

    async def _adapter_factory(s, cfg):
        return fake_adapter

    qs._adapter_factory = _adapter_factory
    qs._explainer = AsyncMock()
    qs._explainer.explain = AsyncMock(
        return_value=type(
            "ExplainerResult",
            (),
            {
                "summary": "s",
                "metric_values": {},
                "filters_applied": [],
                "caveats": [],
                "confidence": 0.9,
            },
        )()
    )
    return qs


async def _seed_permissive(session) -> None:
    await session.execute(
        text(
            "DELETE FROM metaedu.role_permissions WHERE tenant_id = :tid "
            "AND role = 'leader' AND entity_type = 'bill'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    rules = json.dumps({"amount": "visible", "company_name": "visible"})
    await session.execute(
        text(
            f"INSERT INTO metaedu.role_permissions "
            f"(id, tenant_id, role, entity_type, visibility_rules, created_at) "
            f"VALUES (:id, :tid, 'leader', 'bill', '{rules}'::jsonb, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": DEFAULT_TENANT_ID,
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    )
    await session.execute(
        text("DELETE FROM metaedu.query_audit_log WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await session.commit()


async def test_ask_success_returns_audit_id(db_session):
    await _seed_permissive(db_session)
    sm = _make_semantic_model(dataset_id=uuid.uuid4())
    qs = _stub_query_service(db_session)
    result = await qs.ask(
        question="这企业欠费多少",
        semantic_model=sm,
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role="leader",
    )
    assert result["ok"] is True
    # audit_id 指向真实 query_audit_log 行
    row_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.query_audit_log WHERE tenant_id = :tid"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert result.get("audit_id") == row_id


async def test_ask_response_contract_preserves_audit_id(db_session):
    """FastAPI response_model 不得丢弃 QueryService 返回的 audit_id。"""
    await _seed_permissive(db_session)
    sm = _make_semantic_model(dataset_id=uuid.uuid4())
    qs = _stub_query_service(db_session)
    result = await qs.ask(
        question="这企业欠费多少",
        semantic_model=sm,
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role="leader",
    )

    response = AskResponse(ok=True, audit_id=result["audit_id"]).model_dump(
        exclude_none=True
    )
    assert response["audit_id"] == result["audit_id"]


async def test_ask_validator_rejected_returns_audit_id(db_session):
    """validator 拒绝路径也写审计行,audit_id 同样透出。"""
    await _seed_permissive(db_session)
    sm = _make_semantic_model(dataset_id=uuid.uuid4())
    qs = _stub_query_service(db_session)
    # 让 planner 返回一个 validator 会拒绝的 plan(entity 不在语义模型里)
    qs._planner.plan = AsyncMock(
        return_value={"entity": "wrong_entity", "metrics": ["total_amount"]}
    )
    result = await qs.ask(
        question="空指标问题",
        semantic_model=sm,
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role="leader",
    )
    assert result["ok"] is False
    row_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.query_audit_log WHERE tenant_id = :tid"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert row_id is not None
    assert result.get("audit_id") == row_id
