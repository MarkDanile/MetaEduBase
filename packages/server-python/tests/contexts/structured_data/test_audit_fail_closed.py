"""Audit fail-closed tests for QueryService (REQ-056 Task 4).

REQ-056 AC-5: 审计失败 fail-closed. The ``_audit`` helper inside
:class:`QueryService.ask` MUST propagate any exception thrown by
``PermissionsRepository.log_query`` — the user-visible response
(``result_rows``) is only returned after the audit row is durably
written, otherwise we would leak sensitive data to a user whose
activity the regulator cannot trace.

Coverage:

- ``test_audit_failure_does_not_return_results`` (mocked): builds a
  QueryService where the audit repo's ``log_query`` raises. Calls
  ``ask(...)`` and asserts the exception propagates AND no result
  payload is returned to the caller.

- ``test_audit_success_writes_row`` (real DB): runs the full pipeline
  with a real ``PermissionsRepository`` against the test DB; asserts
  one row was appended to ``metaedu.query_audit_log`` and the
  response carries ``ok=True`` with ``result_rows``.

- ``test_audit_failure_propagates_real_db`` (real DB): runs the same
  full pipeline but with ``PermissionsRepository.log_query`` patched
  to raise. Asserts the exception propagates out of ``ask(...)`` and
  ``result_rows`` is NOT returned.

The mocked test is the contract pin: even if the real DB hides
exceptions, a synthetic failure must not be swallowed. The real DB
tests prove the integration with a real session / commit boundary.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import DEFAULT_TEST_DB_URL

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_semantic_model(
    dataset_id: uuid.UUID,
    *,
    entity_type: str = "bill",
    catalog_id: uuid.UUID | None = None,
) -> SemanticModel:
    """Build an in-memory :class:`SemanticModel` for tests.

    Mirrors the schema used by ``sample_semantic_model`` in
    ``tests/contexts/structured_data/conftest.py`` but constructed
    inline so this test file does not depend on that fixture (we
    want the mocked test to run without a DB fixture).

    ``catalog_id`` defaults to ``None`` so the mocked test (which
    doesn't actually persist the audit row) does not need to
    resolve a real catalog. Tests that exercise the real DB path
    pass the seeded ``education`` catalog UUID.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type=entity_type,
        entity_name="账单" if entity_type == "bill" else entity_type,
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
        catalog_id=catalog_id,  # REQ-054: catalog attribution
    )


async def _resolve_education_catalog_id(session: AsyncSession) -> uuid.UUID:
    """Return the ``id`` of the seeded ``education`` catalog for the default tenant.

    Required for the success-path test because ``query_audit_log.catalog_id``
    has a FK to ``data_catalogs.id``. Mirrors the helper in
    ``tests/contexts/structured_data/test_query_router.py``.
    """
    row = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    return row.scalar_one()


def _build_query_service_with_mock_collaborators(
    session: AsyncSession,
) -> QueryService:
    """Build a QueryService whose collaborators are real except for the
    planner + adapter + explainer, which are stubbed.

    The audit call path is intentionally left REAL — it goes through
    the real ``PermissionsRepository(session).log_query`` so the test
    can patch ``PermissionsRepository.log_query`` to inject a failure.
    """
    qs = QueryService(session_factory=lambda: session)
    # Stub planner to return a deterministic, valid query_plan.
    qs._planner = AsyncMock()
    qs._planner.plan = AsyncMock(
        return_value={
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 10,
        }
    )
    # Stub adapter to return one row (proves the row WOULD be returned
    # to the user if the audit didn't fail).
    fake_adapter = AsyncMock()
    fake_adapter.query = AsyncMock(
        return_value=[{"company_name": "ACME", "amount": 100.0}]
    )

    async def _adapter_factory(s, cfg):
        return fake_adapter

    qs._adapter_factory = _adapter_factory
    # Stub explainer to a deterministic summary.
    qs._explainer = AsyncMock()
    qs._explainer.explain = AsyncMock(
        return_value=type(
            "ExplainerResult",
            (),
            {
                "summary": "test summary",
                "metric_values": {},
                "filters_applied": [],
                "caveats": [],
                "confidence": 0.9,
            },
        )()
    )
    # Stub SqlGuard via the collaborators we control — easiest is to
    # leave the real SqlGuard in place; it only depends on RBAC +
    # PII. For a one-row result with no visibility rules, it returns
    # the row unchanged. We rely on the default-tenant seed having no
    # role_permissions row for ``bill`` (strict-default MASKED). To
    # avoid masking the row out, we seed a permissive rule inline via
    # a small helper below.
    return qs


async def _seed_permissive_visibility(session: AsyncSession) -> None:
    """Insert a ``leader`` rule that marks both fields VISIBLE so the
    real SqlGuard does not mask our single test row. Idempotent.
    """
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


async def _count_audit_rows() -> int:
    """Open a fresh engine and count rows in ``query_audit_log`` for
    the default tenant.
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
# Test 1: mock-only — audit failure MUST propagate
# ---------------------------------------------------------------------------


async def test_audit_failure_does_not_return_results(db_session):
    """If ``PermissionsRepository.log_query`` raises, ``QueryService.ask``
    must propagate the exception and NOT return ``result_rows`` to the
    caller.

    This is the contract pin for REQ-056 AC-5 (审计 fail-closed). We
    mock the planner + adapter so we don't need a real dataset — the
    only real DB call is the audit write, which we force to fail.
    """
    await _seed_permissive_visibility(db_session)

    sm = _make_semantic_model(dataset_id=uuid.uuid4())
    qs = _build_query_service_with_mock_collaborators(db_session)

    # Inject the audit failure at the repository level. The QueryService
    # constructs ``PermissionsRepository(session)`` internally, so we
    # patch the class method.
    boom = RuntimeError("simulated audit DB failure")
    with (
        patch(
            "app.contexts.structured_data.infrastructure.permissions_repository"
            ".PermissionsRepository.log_query",
            new_callable=AsyncMock,
            side_effect=boom,
        ),
        pytest.raises(RuntimeError, match="simulated audit DB failure"),
    ):
        await qs.ask(
            question="这企业欠费多少",
            semantic_model=sm,
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role="leader",
            business_purpose="审计 fail-closed 单元测试",
        )

    # Sanity: no audit row was written (the flush failed, and the
    # session was rolled back when the context manager exited on the
    # exception path).
    assert await _count_audit_rows() == 0, (
        "audit row must NOT be persisted when log_query raises"
    )


# ---------------------------------------------------------------------------
# Test 2: real DB — success path writes the audit row
# ---------------------------------------------------------------------------


async def test_audit_success_writes_row(db_session):
    """Sanity baseline: with a real ``PermissionsRepository``, the
    success path writes one row to ``query_audit_log`` and returns
    ``ok=True`` with ``result_rows``. Establishes the "before" half
    of the before/after comparison.
    """
    await _seed_permissive_visibility(db_session)
    real_catalog_id = await _resolve_education_catalog_id(db_session)

    sm = _make_semantic_model(
        dataset_id=uuid.uuid4(), catalog_id=real_catalog_id
    )
    qs = _build_query_service_with_mock_collaborators(db_session)

    result = await qs.ask(
        question="这企业欠费多少",
        semantic_model=sm,
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role="leader",
        business_purpose="审计 fail-closed 单元测试 success",
    )

    assert result["ok"] is True, result
    assert "result_rows" in result
    assert result["result_count"] == 1
    # Real DB: one audit row written.
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Test 3: real DB + injected audit failure — fail-closed evidence
# ---------------------------------------------------------------------------


async def test_audit_failure_propagates_real_db(db_session):
    """End-to-end: real DB session, real RBAC / PII / SqlGuard, mocked
    audit log write. The exception MUST propagate out of ``ask`` and
    ``result_rows`` MUST NOT be returned to the caller.

    This is the load-bearing AC-5 test: it proves the integration
    boundary between the request session and the audit write does not
    silently swallow failures.
    """
    await _seed_permissive_visibility(db_session)

    sm = _make_semantic_model(dataset_id=uuid.uuid4())
    qs = _build_query_service_with_mock_collaborators(db_session)

    boom = RuntimeError("simulated audit DB failure (real DB)")
    raised = False
    with patch(
        "app.contexts.structured_data.infrastructure.permissions_repository"
        ".PermissionsRepository.log_query",
        new_callable=AsyncMock,
        side_effect=boom,
    ):
        try:
            await qs.ask(
                question="这企业欠费多少",
                semantic_model=sm,
                user_id=DEFAULT_ADMIN_ID,
                tenant_id=DEFAULT_TENANT_ID,
                role="leader",
                business_purpose="审计 fail-closed 端到端",
            )
        except RuntimeError as e:
            assert "simulated audit DB failure (real DB)" in str(e)
            raised = True
        # If the exception did NOT propagate, this assertion fails
        # the test — the ask() call would have returned a dict
        # containing ``result_rows``, which is the bug we are
        # guarding against.
        assert raised, (
            "QueryService.ask must propagate audit-write failures "
            "instead of returning a result dict to the caller"
        )

    # The flush failed; the session context manager rolled back. No
    # audit row is persisted.
    assert await _count_audit_rows() == 0, (
        "audit row must NOT be persisted when log_query raises"
    )


# ---------------------------------------------------------------------------
# BUG-015: business_purpose is now optional — audit write with None must succeed
# ---------------------------------------------------------------------------


async def test_audit_business_purpose_none_writes_row(db_session):
    """BUG-015 contract pin: ``business_purpose=None`` must persist a row
    and the row's ``business_purpose`` column must be NULL.

    The audit write path used to reject empty-string business_purpose.
    Migration 020 flipped the column to NULL-able, the router demoted
    the field to optional, and :class:`QueryService.ask` forwards
    ``None`` straight through. This test pins the integration: a real
    write against the test DB with ``business_purpose=None`` produces a
    row whose column is NULL — no ``IntegrityError``, no ValueError.
    """
    from sqlalchemy import select

    from app.contexts.structured_data.infrastructure.semantic_models_models import (
        QueryAuditLogModel,
    )

    await _seed_permissive_visibility(db_session)
    real_catalog_id = await _resolve_education_catalog_id(db_session)

    sm = _make_semantic_model(
        dataset_id=uuid.uuid4(), catalog_id=real_catalog_id
    )
    qs = _build_query_service_with_mock_collaborators(db_session)

    result = await qs.ask(
        question="这企业欠费多少",
        semantic_model=sm,
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role="leader",
        business_purpose=None,  # BUG-015: omitted intent context
    )

    assert result["ok"] is True, result
    assert "result_rows" in result
    assert result["result_count"] == 1

    # Direct-read the audit row to verify business_purpose is NULL.
    rows = (
        await db_session.execute(
            select(QueryAuditLogModel).where(
                QueryAuditLogModel.tenant_id == DEFAULT_TENANT_ID
            )
        )
    ).scalars().all()
    assert len(rows) == 1, "BUG-015: one audit row expected"
    assert rows[0].business_purpose is None, (
        "BUG-015: audit row.business_purpose must be NULL when omitted"
    )
    # Core audit fields must still be intact.
    assert rows[0].user_id == DEFAULT_ADMIN_ID
    assert rows[0].question == "这企业欠费多少"
    assert rows[0].result_count == 1
