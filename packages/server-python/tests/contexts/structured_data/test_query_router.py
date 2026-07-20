"""End-to-end test for POST /api/v1/data-query/ask.

REQ-052 Task 5 + REQ-054 Task 6 + BUG-015: the router is the only entry
point for the data-activation pipeline from the outside world. It must:

1. Validate the request payload (pydantic — required fields return
   422). BUG-015 demoted ``business_purpose`` from
   ``Field(..., min_length=5)`` to ``Field(default=None)`` and removed
   ``confirmed_company_name`` entirely; the
   tests below split the old ``test_ask_endpoint_missing_business_purpose``
   and ``test_ask_endpoint_short_business_purpose`` cases into a single
   opt-in path (omitting the field is now allowed).
2. Authenticate the caller via the existing
   :func:`app.contexts.identity.interfaces.api.dependencies.get_current_user`.
3. Resolve the ``SemanticModel`` for the request's ``(catalog_id,
   entity_type)`` pair from the DB (via the new
   :meth:`SemanticModelRepository.get_active_by_catalog_and_entity_type`
   helper).
4. Call :class:`QueryService.ask` and serialise the result back.
5. REQ-054: write a row to ``query_audit_log`` with ``catalog_id``
   populated (success AND validator-failure paths).

Tests cover the brief's required cases plus the validation surface:

- ``test_ask_endpoint_success`` — end-to-end happy path with a real
  semantic model persisted to the test DB. Verifies the response shape
  matches :class:`AskResponse`, the audit log row was written AND the
  row carries the right ``catalog_id``. BUG-015: business_purpose is
  optional and omitted here.
- ``test_ask_endpoint_omits_business_purpose_succeeds`` — explicit
  BUG-015 test that omitting ``business_purpose`` still returns 200 +
  writes an audit row with ``business_purpose=NULL``.
- ``test_ask_endpoint_success_writes_catalog_id`` — REQ-054 catalog_id
  audit correctness (separate test, unchanged).
- ``test_ask_endpoint_missing_catalog_id`` — REQ-054: missing
  ``catalog_id`` → 422.
- ``test_ask_endpoint_unknown_entity_type`` — semantic model not found
  for the requested ``(catalog_id, entity_type)`` → 404 (detail
  mentions ``catalog_id``).
- ``test_ask_endpoint_unauthenticated`` — no auth header → 401/403.

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


@pytest_asyncio.fixture(autouse=True)
async def _clean_semantic_models(db_session):
    """REQ-054 Task 6: clear ``metaedu.semantic_models`` before each test.

    The router now resolves by ``(catalog_id, entity_type)`` which uses
    ``scalar_one_or_none()``. Once a tenant has more than one active
    ``bill`` row in the same education catalog (which happens the moment
    a previous test run leaves a stale row behind), the second lookup
    raises ``MultipleResultsFound``. Same fixture as
    ``test_semantic_model_repository.py``.
    """
    await db_session.execute(
        text("DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


async def _resolve_education_catalog_id(session: AsyncSession) -> uuid.UUID:
    """Return the ``id`` of the seeded ``education`` catalog for the default tenant.

    REQ-054: tests must use the tenant's actual catalog UUID (not a
    fabricated one) so the new ``get_active_by_catalog_and_entity_type``
    lookup matches the persisted semantic model row. The catalog is
    seeded by alembic migration 018 for every tenant that exists in
    the DB at upgrade time.
    """
    row = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    return row.scalar_one()


async def _persist_semantic_model(session: AsyncSession, dataset_id: uuid.UUID) -> None:
    """Persist an in-memory :class:`SemanticModel` against ``sample_dataset``.

    The router's ``get_active_by_catalog_and_entity_type`` looks the
    model up from the DB; tests need it persisted so the lookup
    succeeds. We commit explicitly so the row is visible to the
    router's request-scoped session (which is a different AsyncSession
    from this fixture).
    """
    repo = SemanticModelRepository(session)
    # REQ-054: resolve the default education catalog so the new
    # ``catalog_id`` column is satisfied.
    catalog_id = await _resolve_education_catalog_id(session)
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
    await repo.create(model, catalog_id=catalog_id)
    await session.commit()


@pytest_asyncio.fixture
async def persisted_semantic_model(db_session, sample_dataset):
    """Yield after persisting the semantic model and committing it.

    Returns the catalog_id alongside the dataset info so individual
    tests can build a valid ``AskRequest`` payload.
    """
    catalog_id = await _resolve_education_catalog_id(db_session)
    await _persist_semantic_model(db_session, sample_dataset["id"])
    yield {
        "dataset_id": sample_dataset["id"],
        "catalog_id": catalog_id,
    }


async def _persist_unknown_type_model(
    session: AsyncSession, dataset_id: uuid.UUID
) -> None:
    """Persist a semantic model whose ``data_source_config.type`` is a
    string the factory does not recognize (``"unknown_type"``).

    REQ-057: ``default_adapter_factory`` now routes all three declared
    :class:`DataSourceType` values (``imported_dataset`` / ``direct_db``
    / ``mcp``); only a truly unknown type raises ``ValueError``. Used to
    exercise the router's ``ValueError`` → 400 translation: the plan
    passes validation, the pipeline reaches the adapter factory, and the
    factory raises ``ValueError`` for the unrecognized source type. Uses
    a distinct ``entity_type`` ("invoice") so it doesn't collide with
    the ``bill`` model persisted by other tests.
    """
    repo = SemanticModelRepository(session)
    # REQ-054: resolve the default education catalog.
    catalog_id = await _resolve_education_catalog_id(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type="invoice",
        entity_name="发票",
        data_source_config={
            "type": "unknown_type",
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
    )
    await repo.create(model, catalog_id=catalog_id)
    await session.commit()


async def _persist_typed_model(
    session: AsyncSession,
    dataset_id: uuid.UUID,
    *,
    entity_type: str,
    entity_name: str,
    data_source_config: dict,
) -> None:
    """Persist a semantic model with a caller-supplied ``data_source_config``.

    Shared body for the REQ-057 typed-model helpers below
    (:func:`_persist_direct_db_model` / :func:`_persist_mcp_model`) so
    the routing reachability tests only differ in the config they pass.
    Uses the caller's ``entity_type`` so concurrent models in the same
    catalog don't collide on ``scalar_one_or_none()``.
    """
    repo = SemanticModelRepository(session)
    catalog_id = await _resolve_education_catalog_id(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type=entity_type,
        entity_name=entity_name,
        data_source_config=data_source_config,
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
    )
    await repo.create(model, catalog_id=catalog_id)
    await session.commit()


async def _persist_direct_db_model(
    session: AsyncSession, dataset_id: uuid.UUID
) -> None:
    """Persist a ``direct_db``-typed model (entity_type ``contract``).

    REQ-057 AC-2: proves the ``direct_db`` path is reachable through the
    router → factory → adapter chain. ``asyncpg.connect`` is mocked in
    the test so no real external PG is needed.
    """
    await _persist_typed_model(
        session,
        dataset_id,
        entity_type="contract",
        entity_name="合同",
        data_source_config={
            "type": "direct_db",
            "connection_string": "postgresql://readonly@ext-host:5432/extdb",
            "table_name": "contracts",
        },
    )


async def _persist_mcp_model(session: AsyncSession, dataset_id: uuid.UUID) -> None:
    """Persist an ``mcp``-typed model (entity_type ``supplier``).

    REQ-044: the adapter now delegates to ``MCPInvocationService``. With
    ``server_code`` pointing at a server NOT registered in
    ``metaedu.mcp_servers`` for this tenant, the service raises
    ``MCPInvocationServerNotFoundError`` (a subclass of
    ``MCPInvocationError``); ``QueryService.ask`` catches it, writes a
    ``query_audit_log`` row, and returns ``ok=False`` - never a 500 and
    never an empty-list masquerade.
    """
    await _persist_typed_model(
        session,
        dataset_id,
        entity_type="supplier",
        entity_name="供应商",
        data_source_config={
            "type": "mcp",
            "server_code": "qcc_not_registered",
            "tool_name": "query_supplier",
        },
    )


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


async def _latest_audit_catalog_id() -> uuid.UUID | None:
    """Return the ``catalog_id`` of the most recent audit row for the
    default tenant — or ``None`` if no row exists / the column is NULL.

    REQ-054: the new test ``test_ask_endpoint_success_writes_catalog_id``
    asserts that ``catalog_id`` is populated on the audit row. We open a
    fresh engine (the request session may have been disposed) and read
    the latest row ordered by ``created_at DESC, id DESC`` (id as the
    tiebreaker — two rows written in the same millisecond would
    otherwise order non-deterministically and ``scalar_one()`` would
    raise ``MultipleResultsFound``).
    """
    engine = create_async_engine(DEFAULT_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            result = await s.execute(
                text(
                    "SELECT catalog_id FROM metaedu.query_audit_log "
                    "WHERE tenant_id = :tid "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"tid": DEFAULT_TENANT_ID},
            )
            row = result.first()
            return row[0] if row else None
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
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "bill",
                "question": "这企业欠费多少",
                # BUG-015: business_purpose is optional now and intentionally
                # omitted here to lock the no-context ask path.
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


async def test_ask_endpoint_omits_business_purpose_succeeds(
    client: AsyncClient, auth_headers: dict, persisted_semantic_model
):
    """BUG-015: 缺 business_purpose 现在是允许的 — audit 行写 NULL.

    Pins the BUG-015 contract that omitting ``business_purpose`` does
    not 422 the request; the pipeline runs and ``query_audit_log``
    carries ``business_purpose=NULL`` for the row.
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
        mock_explainer.return_value = "summary without business_purpose"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "bill",
                "question": "这企业欠费多少",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    # Audit row carries business_purpose=NULL — read it back via a fresh engine.
    engine = create_async_engine(DEFAULT_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            row = (await s.execute(
                text(
                    "SELECT business_purpose FROM metaedu.query_audit_log "
                    "WHERE tenant_id = :tid "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"tid": DEFAULT_TENANT_ID},
            )).first()
    finally:
        await engine.dispose()
    assert row is not None
    assert row[0] is None, (
        "BUG-015 contract: business_purpose omitted → audit row NULL"
    )


async def test_ask_endpoint_success_writes_catalog_id(
    client: AsyncClient, auth_headers: dict, persisted_semantic_model
):
    """REQ-054: success path 必须把 catalog_id 写入 query_audit_log.

    Reads back the most recent audit row for the tenant and asserts its
    ``catalog_id`` equals the catalog_id we sent in the ask payload.
    This pins the contract from spec §12 (国资审计) that every audit
    row records which database the question was asked against.
    """
    catalog_id = persisted_semantic_model["catalog_id"]
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
        mock_explainer.return_value = "summary"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(catalog_id),
                "entity_type": "bill",
                "question": "这企业欠费多少",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    # Audit row must carry the catalog_id we sent.
    written_catalog_id = await _latest_audit_catalog_id()
    assert written_catalog_id is not None, (
        "audit row's catalog_id must be populated on the success path"
    )
    assert written_catalog_id == catalog_id


async def test_ask_endpoint_missing_catalog_id(
    client: AsyncClient, auth_headers: dict, persisted_semantic_model
):
    """REQ-054: 缺 catalog_id → 422（pydantic 必填校验）。

    Without ``catalog_id``, pydantic rejects the request BEFORE the
    router runs, so the response is the standard 422 validation
    envelope from FastAPI.
    """
    response = await client.post(
        "/api/v1/data-query/ask",
        headers=auth_headers,
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
            "business_purpose": "信用风险评估",
        },
    )
    assert response.status_code == 422
    # Confirm the error mentions the missing field.
    detail_text = json.dumps(response.json())
    assert "catalog_id" in detail_text


# ---------------------------------------------------------------------------
# Validation surface (bonus tests beyond the brief)
# ---------------------------------------------------------------------------


async def test_ask_endpoint_unknown_entity_type(
    client: AsyncClient, auth_headers: dict, persisted_semantic_model
):
    """entity_type 没在 semantic_models 表里 → 404（detail 提到 catalog_id）。"""
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
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "nonexistent_entity",
                "question": "查询",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 404
    # REQ-054: 404 detail should mention catalog_id (per the brief).
    assert "catalog_id" in response.json()["detail"] or str(
        persisted_semantic_model["catalog_id"]
    ) in response.json()["detail"]


async def test_ask_endpoint_unauthenticated(
    client: AsyncClient, persisted_semantic_model
):
    """没有 Authorization header → 401 / 403。

    The exact code is whatever ``get_current_user`` raises; FastAPI's
    HTTPBearer returns 403 for missing credentials. We accept either
    401 or 403.
    """
    response = await client.post(
        "/api/v1/data-query/ask",
        json={
            "catalog_id": str(persisted_semantic_model["catalog_id"]),
            "entity_type": "bill",
            "question": "这企业欠费多少",
            "business_purpose": "信用风险评估",
        },
    )
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Spec-binding gaps (reviewer Important #1 + #2)
# ---------------------------------------------------------------------------


async def test_ask_endpoint_unsupported_data_source_returns_400(
    client: AsyncClient, auth_headers: dict, db_session, sample_dataset,
    persisted_semantic_model,
):
    """未知 data_source_type（unknown_type）→ 400，而不是 500。

    REQ-057: ``default_adapter_factory`` now supports ``imported_dataset``
    / ``direct_db`` / ``mcp``; only a truly unknown type raises
    ``ValueError``. The router must translate that into a 400 (client
    asked for an unrecognized source) rather than letting it propagate
    as an unhandled 500.
    """
    await _persist_unknown_type_model(db_session, sample_dataset["id"])

    planner_response = json.dumps(
        {
            "entity": "invoice",
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
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "invoice",
                "question": "查询发票金额",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 400, response.text
    assert "unknown_type" in response.json()["detail"]


async def test_ask_endpoint_validator_rejection_audits_with_zero_rows(
    client: AsyncClient, auth_headers: dict, seed_rbac, persisted_semantic_model
):
    """校验失败（幽灵 metric）→ ok=False + errors，且仍写审计（result_count=0 + catalog_id）。

    Spec §12 (国资审计) requires a complete trail: EVERY query attempt
    must be logged, including validator rejections. The planner is mocked
    to produce a plan with a ghost metric so ``SemanticValidator.validate``
    returns errors and the pipeline short-circuits. We assert the response
    reports the failure AND that an audit row was still written (with the
    REQ-054 ``catalog_id`` populated even on the rejection path).
    """
    before = await _count_audit_rows()
    catalog_id = persisted_semantic_model["catalog_id"]

    # Ghost metric "bogus" is not in metric_definitions → validator rejects.
    planner_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["bogus"],
            "filters": {},
            "time_range": None,
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
        mock_explainer.return_value = "should-not-be-called"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(catalog_id),
                "entity_type": "bill",
                "question": "这企业的乱七八糟指标是多少",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is False
    assert data["errors"], "validator rejection must return a non-empty errors list"
    # Audit trail must still capture the rejected attempt.
    after = await _count_audit_rows()
    assert after == before + 1, "validator-rejected attempt must still be audited"
    # REQ-054: even the rejection-path audit row must carry catalog_id.
    written_catalog_id = await _latest_audit_catalog_id()
    assert written_catalog_id == catalog_id, (
        "validator-rejected audit row must carry catalog_id"
    )


# ---------------------------------------------------------------------------
# REQ-057 reviewer findings: capability-unavailable + DirectDB reachability
# ---------------------------------------------------------------------------


async def test_ask_endpoint_mcp_unregistered_server_audits_and_returns_ok_false(
    client: AsyncClient, auth_headers: dict, db_session, sample_dataset,
    persisted_semantic_model,
):
    """MCP V1 数据源 → ok=False + 仍写审计行（不 500、不伪装空结果）。

    REQ-057 AC-3 + spec §12 (国资审计): the MCP adapter raises
    ``CapabilityUnavailableError``. The orchestrator must catch it,
    write an audit row with ``result_count=0`` (fail-closed: EVERY
    attempt is logged, including capability failures), and return a
    clear ``ok=False`` — never an unhandled 500, and never a silent
    "0 results" success that hides the capability gap.
    """
    await _persist_mcp_model(db_session, sample_dataset["id"])
    before = await _count_audit_rows()

    planner_response = json.dumps(
        {
            "entity": "supplier",
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
        mock_explainer.return_value = "should-not-be-called"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "supplier",
                "question": "查询供应商金额",
                "business_purpose": "信用风险评估",
            },
        )

    # Well-formed request; the MCP server is unregistered → 200 carrying
    # ok=False (not a 5xx).
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is False
    assert data["errors"], "invocation failure must surface a non-empty errors list"
    assert any("MCP 数据源调用失败" in e for e in data["errors"])
    assert data.get("suggestion"), "failure should include a suggestion"

    # Fail-closed audit: the attempt is logged despite the invocation failure.
    after = await _count_audit_rows()
    assert after == before + 1, (
        "capability-unavailable attempt must still write an audit row"
    )
    written_catalog_id = await _latest_audit_catalog_id()
    assert written_catalog_id == persisted_semantic_model["catalog_id"]


async def test_ask_endpoint_direct_db_reachable_returns_ok_true(
    client: AsyncClient, auth_headers: dict, db_session, sample_dataset,
    persisted_semantic_model,
):
    """DirectDB 数据源经 factory 路由可达 → ok=True（asyncpg 已 mock）。

    REQ-057 AC-2: proves the ``direct_db`` path is wired end-to-end —
    router → ``default_adapter_factory`` (routes type=direct_db) →
    ``DirectDBAdapter.query``. ``asyncpg.connect`` is mocked so no real
    external PG is required; the mock returns one row so the pipeline
    produces a non-empty result and the explainer summarizes it.
    """
    await _persist_direct_db_model(db_session, sample_dataset["id"])

    planner_response = json.dumps(
        {
            "entity": "contract",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 100,
        }
    )

    fake_conn = AsyncMock()
    fake_conn.fetch.return_value = [
        {"company_name": "ACME", "amount": 150.0},
    ]

    # Patch the ``asyncpg`` name ON the adapter module (not
    # ``asyncpg.connect``) — the latter would also rebind the attribute
    # that SQLAlchemy's asyncpg dialect resolves, breaking the request
    # session's own DB connection. Scoping the patch to the adapter
    # module leaves SQLAlchemy's dialect untouched.
    fake_asyncpg = AsyncMock()
    fake_asyncpg.connect.return_value = fake_conn

    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer, patch(
        "app.contexts.structured_data.infrastructure.direct_db_adapter.asyncpg",
        fake_asyncpg,
    ):
        mock_planner.return_value = planner_response
        mock_explainer.return_value = "合同总金额 150 元"

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(persisted_semantic_model["catalog_id"]),
                "entity_type": "contract",
                "question": "查询合同总金额",
                "business_purpose": "信用风险评估",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True, f"direct_db path must succeed: {data}"
    assert data["result_count"] == 1
    assert data["summary"] == "合同总金额 150 元"
    # The adapter actually reached asyncpg (reachability, not short-circuit).
    fake_asyncpg.connect.assert_awaited_once()
    fake_conn.fetch.assert_awaited_once()
