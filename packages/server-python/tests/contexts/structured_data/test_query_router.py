"""End-to-end test for POST /api/v1/data-query/ask.

REQ-052 Task 5: the router is the only entry point for the
data-activation pipeline from the outside world. It must:

1. Validate the request payload (pydantic ``business_purpose`` >= 5
   chars enforced; missing fields return 422).
2. Authenticate the caller via the existing
   :func:`app.contexts.identity.interfaces.api.dependencies.get_current_user`.
3. Resolve the ``SemanticModel`` for the request's ``entity_type`` from
   the DB (via the new ``get_active_by_entity_type`` helper).
4. Call :class:`QueryService.ask` and serialise the result back.

Tests cover the brief's required cases plus the validation surface:

- ``test_ask_endpoint_success`` — end-to-end happy path with a real
  semantic model persisted to the test DB. Verifies the response shape
  matches :class:`AskResponse` and the audit log row was written.
- ``test_ask_endpoint_missing_business_purpose`` — missing
  ``business_purpose`` → 422.
- ``test_ask_endpoint_short_business_purpose`` — ``business_purpose``
  under 5 chars → 422.
- ``test_ask_endpoint_unknown_entity_type`` — semantic model not found
  for the requested entity_type → 404.
- ``test_ask_endpoint_unauthenticated`` — no auth header → 401/403 (or
  whatever the existing ``get_current_user`` returns).

All collaborators (Planner, Explainer, PII detector, RBAC, audit repo)
are real; only the LLM is patched (consistent with the rest of the
REQ-052 test suite).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import DEFAULT_TEST_DB_URL

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _persist_semantic_model(session: AsyncSession, dataset_id: uuid.UUID) -> None:
    """Persist an in-memory :class:`SemanticModel` against ``sample_dataset``.

    The router's ``get_active_by_entity_type`` looks the model up from
    the DB; tests need it persisted so the lookup succeeds. We commit
    explicitly so the row is visible to the router's request-scoped
    session (which is a different AsyncSession from this fixture).
    """
    repo = SemanticModelRepository(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
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
                role=ColumnRole.ENTITY_KEY,
                type=ColumnType.STR,
                sensitive=False,
                synonym=["企业名称"],
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC,
                type=ColumnType.FLOAT,
                sensitive=True,
                synonym=["金额"],
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER,
                type=ColumnType.DATE,
                sensitive=False,
                synonym=["账单日期"],
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
            "unpaid_amount": MetricDefinition(
                column="amount", aggregation="sum", label="欠费金额"
            ),
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )
    await repo.create(model)
    await session.commit()


@pytest_asyncio.fixture
async def persisted_semantic_model(db_session, sample_dataset):
    """Yield after persisting the semantic model and committing it."""
    await _persist_semantic_model(db_session, sample_dataset["id"])
    yield sample_dataset


async def _count_audit_rows() -> int:
    """Open a fresh engine and count rows in ``query_audit_log``.

    The router's request-scoped session commits when the dependency
    tears down; this helper opens a separate session to verify the row
    landed.
    """
    engine = create_async_engine(DEFAULT_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            result = await s.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.query_audit_log "
                    "WHERE tenant_id = :tid"
                ),
                {"tid": DEFAULT_TENANT_ID},
            )
            return int(result.scalar() or 0)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Brief's 2 required cases
# ---------------------------------------------------------------------------


async def test_ask_endpoint_success(
    client: AsyncClient, auth_headers: dict, persisted_semantic_model
):
    """完整流程：POST → query_plan + result_rows + summary。

    The LLM is mocked to return a deterministic summary string so the
    test does not depend on a real provider. The audit log row count is
    checked to confirm the audit pipeline fired.
    """
    planner_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["unpaid_amount"],
            "filters": {},
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer:
        mock_planner.return_value = planner_response
        mock_explainer.return_value = "该企业过去三年累计欠费 150 元"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "entity_type": "bill",
                "question": "这企业欠费多少",
                "business_purpose": "评估客户信用风险",
                "confirmed_company_name": "ACME",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert "query_plan" in data
    assert "summary" in data
    assert data["summary"] == "该企业过去三年累计欠费 150 元"
    assert data["result_count"] >= 0
    # Audit log row must be persisted for every successful ask.
    assert await _count_audit_rows() >= 1


async def test_ask_endpoint_missing_business_purpose(client: AsyncClient, auth_headers: dict):
    """缺 business_purpose → 422（pydantic 必填校验）。"""
    response = await client.post(
        "/api/v1/data-query/ask",
        headers=auth_headers,
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Validation surface (bonus tests beyond the brief)
# ---------------------------------------------------------------------------


async def test_ask_endpoint_short_business_purpose(client: AsyncClient, auth_headers: dict):
    """``business_purpose`` 少于 5 字 → 422。"""
    response = await client.post(
        "/api/v1/data-query/ask",
        headers=auth_headers,
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
            "business_purpose": "abc",  # 3 chars, < 5
        },
    )
    assert response.status_code == 422


async def test_ask_endpoint_unknown_entity_type(
    client: AsyncClient, auth_headers: dict
):
    """entity_type 没在 semantic_models 表里 → 404。"""
    planner_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer:
        mock_planner.return_value = planner_response
        mock_explainer.return_value = "summary"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "entity_type": "nonexistent_entity",
                "question": "查询",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 404


async def test_ask_endpoint_unauthenticated(client: AsyncClient):
    """没有 Authorization header → 401 / 403。

    The exact code is whatever ``get_current_user`` raises; FastAPI's
    HTTPBearer returns 403 for missing credentials. We accept either
    401 or 403.
    """
    response = await client.post(
        "/api/v1/data-query/ask",
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
            "business_purpose": "信用风险评估",
        },
    )
    assert response.status_code in (401, 403)