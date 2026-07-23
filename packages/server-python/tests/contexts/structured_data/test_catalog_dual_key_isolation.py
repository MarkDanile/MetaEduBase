"""REQ-057 Task 2 (AC-5): 两 Catalog 同 entity_type 隔离集成测试.

Two catalogs (``education`` + ``park``) both declare a semantic model
with the SAME ``entity_type="bill"`` but different ``column_mapping``
labels and different underlying datasets. This is the multi-theme
scenario the catalog architecture (REQ-054) was built for: 中高职教育
数据库 and 产业园区数据库 both track "账单", but the data and schema
must stay fully isolated per catalog.

The test drives the FULL router path (``POST /api/v1/data-query/ask``),
which internally resolves the semantic model via the dual-key lookup
:meth:`SemanticModelRepository.get_active_by_catalog_and_entity_type`
— so a passing test proves:

1. **Semantic-model isolation** — the router picks the model whose
   ``catalog_id`` matches the request, not "any active bill model"
   (which the deprecated single-key ``get_active_by_entity_type``
   would silently do via ``LIMIT 1``).
2. **Data isolation** — querying the education catalog returns
   education rows (ACME/BetaCorp), querying the park catalog returns
   park rows (ParkCorpA) — never a cross-catalog leak.
3. **Audit isolation** — each ``query_audit_log`` row carries the
   ``catalog_id`` of the catalog that was actually queried.

All collaborators are real; only the LLM (planner + explainer) is
mocked, consistent with the rest of the REQ-052/REQ-054 router suite.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
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
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _resolve_catalog_id(session: AsyncSession, code: str) -> uuid.UUID:
    """Return the ``id`` of the catalog with ``code`` for the default tenant."""
    row = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = :code"
        ),
        {"tid": DEFAULT_TENANT_ID, "code": code},
    )
    return row.scalar_one()


async def _get_or_create_park_catalog(session: AsyncSession) -> uuid.UUID:
    """Return a clean ``park`` catalog id for the default tenant.

    A prior test run commits its ``park`` catalog + datasets (the
    ``db_session`` fixture commits on teardown), and ``datasets.catalog_id``
    is ``ON DELETE RESTRICT`` — so we cannot delete-then-reinsert the
    catalog. Instead we reuse the catalog row when present (or INSERT on
    first use), then clear its child rows (semantic_models → dataset_rows →
    datasets, FK-safe order) so the dual-key ``scalar_one_or_none()`` lookup
    sees exactly one active ``bill`` model per catalog per test.
    """
    existing = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'park'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    row = existing.first()
    if row:
        catalog_id = row[0]
    else:
        catalog_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                "INSERT INTO metaedu.data_catalogs "
                "(id, tenant_id, code, name, description, entity_types, is_active, "
                " created_by, created_at, updated_at) "
                "VALUES (:id, :tid, 'park', '产业园区数据库', 'park theme', "
                " '[]'::jsonb, true, :uid, :now, :now)"
            ),
            {"id": catalog_id, "tid": DEFAULT_TENANT_ID, "uid": DEFAULT_ADMIN_ID, "now": now},
        )
        await session.flush()

    # Clear prior park children so each test starts from a single-model
    # slate (FK-safe order: semantic_models reference datasets, dataset_rows
    # reference datasets).
    await session.execute(
        text("DELETE FROM metaedu.semantic_models WHERE catalog_id = :cid"),
        {"cid": catalog_id},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.dataset_rows WHERE dataset_id IN "
            "(SELECT id FROM metaedu.datasets WHERE catalog_id = :cid)"
        ),
        {"cid": catalog_id},
    )
    await session.execute(
        text("DELETE FROM metaedu.datasets WHERE catalog_id = :cid"),
        {"cid": catalog_id},
    )
    await session.flush()
    return catalog_id


async def _persist_dataset(
    session: AsyncSession,
    *,
    catalog_id: uuid.UUID,
    name: str,
    company_names: list[str],
) -> uuid.UUID:
    """Persist a dataset + one JSONB row per company into ``catalog_id``.

    Each row carries only ``company_name`` + ``amount`` so the two
    catalogs' datasets have distinguishable payloads (education →
    ACME/BetaCorp, park → ParkCorpA).
    """
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    cnames_literal = json.dumps(["company_name", "amount"])
    ctypes_literal = json.dumps(["str", "float"])
    await session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, catalog_id, name, description, column_names, column_types, "
            f"row_count, source_file, tags, status, kg_status, sort_order, "
            f"created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, :name, NULL, '{cnames_literal}'::jsonb, "
            f"'{ctypes_literal}'::jsonb, :rcount, NULL, NULL, 'uploaded', "
            f"'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
            "name": name,
            "rcount": len(company_names),
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )
    for i, company in enumerate(company_names):
        payload_literal = json.dumps({"company_name": company, "amount": 100.0})
        await session.execute(
            text(
                f"INSERT INTO metaedu.dataset_rows "
                f"(id, tenant_id, dataset_id, row_index, data, created_at) "
                f"VALUES (:id, :tid, :did, :idx, '{payload_literal}'::jsonb, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": DEFAULT_TENANT_ID,
                "did": dataset_id,
                "idx": i,
                "now": now,
            },
        )
    await session.flush()
    return dataset_id


async def _persist_bill_model(
    session: AsyncSession,
    *,
    catalog_id: uuid.UUID,
    dataset_id: uuid.UUID,
    entity_name: str,
) -> None:
    """Persist an active ``bill`` semantic model into ``catalog_id``.

    Both catalogs use ``entity_type="bill"``; only ``catalog_id`` and
    the human-readable ``entity_name`` differ — exactly the dual-key
    collision the deprecated single-key lookup could not disambiguate.
    """
    repo = SemanticModelRepository(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type="bill",
        entity_name=entity_name,
        data_source_config={
            "type": "imported_dataset",
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
                sensitive=False,
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
    await session.flush()


async def _latest_audit_row() -> tuple[uuid.UUID | None, int | None]:
    """Return ``(catalog_id, result_count)`` of the most recent audit row."""
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            result = await s.execute(
                text(
                    "SELECT catalog_id, result_count FROM metaedu.query_audit_log "
                    "WHERE tenant_id = :tid "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"tid": DEFAULT_TENANT_ID},
            )
            row = result.first()
            return (row[0], row[1]) if row else (None, None)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# AC-5: two-catalog same-entity_type isolation
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_catalogs(db_session, seed_rbac):
    """Set up education + park catalogs, each with a distinct ``bill`` model.

    The router authenticates as the seeded ``super_admin``. That role is not
    in the RBAC ``Role`` enum, so ``SqlGuard`` falls back to MASKED for
    sensitive fields — but ``company_name`` is marked non-sensitive and
    "ACME"/"ParkCorpA" match no PII pattern, so the values survive
    unmasked. ``seed_rbac``'s load-bearing contribution here is clearing
    ``query_audit_log`` (so "latest audit row" is unambiguous), not field
    visibility. Returns the two catalog ids plus their company payloads for
    assertions.
    """
    education_catalog_id = await _resolve_catalog_id(db_session, "education")
    park_catalog_id = await _get_or_create_park_catalog(db_session)

    # Clear any prior committed ``bill`` model in the education catalog so
    # the dual-key ``scalar_one_or_none()`` lookup sees exactly one active
    # model per catalog (other tests in this suite persist bill models via
    # the committing ``db_session`` teardown).
    await db_session.execute(
        text(
            "DELETE FROM metaedu.semantic_models "
            "WHERE catalog_id = :cid AND entity_type = 'bill'"
        ),
        {"cid": education_catalog_id},
    )
    await db_session.flush()

    education_dataset_id = await _persist_dataset(
        db_session,
        catalog_id=education_catalog_id,
        name="education-bill-dataset",
        company_names=["ACME", "BetaCorp"],
    )
    park_dataset_id = await _persist_dataset(
        db_session,
        catalog_id=park_catalog_id,
        name="park-bill-dataset",
        company_names=["ParkCorpA"],
    )

    await _persist_bill_model(
        db_session,
        catalog_id=education_catalog_id,
        dataset_id=education_dataset_id,
        entity_name="教育账单",
    )
    await _persist_bill_model(
        db_session,
        catalog_id=park_catalog_id,
        dataset_id=park_dataset_id,
        entity_name="园区账单",
    )
    await db_session.commit()

    return {
        "education_catalog_id": education_catalog_id,
        "park_catalog_id": park_catalog_id,
        "education_companies": {"ACME", "BetaCorp"},
        "park_companies": {"ParkCorpA"},
    }


async def _ask(client, auth_headers, catalog_id, question):
    """Drive the ask endpoint with a mocked planner/explainer; return JSON."""
    planner_response = json.dumps(
        {
            "entity": "bill",
            "metrics": [],
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
                "question": question,
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


def _row_companies(data: dict) -> set:
    """Extract the set of ``company_name`` values from result_rows."""
    return {row.get("company_name") for row in data.get("result_rows", [])}


async def test_two_catalogs_same_entity_type_data_isolated(
    client: AsyncClient, auth_headers: dict, two_catalogs
):
    """同 entity_type=bill：education 查不到 park 数据，反之亦然。"""
    edu = await _ask(
        client, auth_headers, two_catalogs["education_catalog_id"], "查询教育账单"
    )
    assert edu["ok"] is True
    assert _row_companies(edu) == two_catalogs["education_companies"]
    assert "ParkCorpA" not in _row_companies(edu)

    park = await _ask(
        client, auth_headers, two_catalogs["park_catalog_id"], "查询园区账单"
    )
    assert park["ok"] is True
    assert _row_companies(park) == two_catalogs["park_companies"]
    assert "ACME" not in _row_companies(park)
    assert "BetaCorp" not in _row_companies(park)


async def test_two_catalogs_same_entity_type_audit_isolated(
    client: AsyncClient, auth_headers: dict, two_catalogs
):
    """同 entity_type=bill：审计行的 catalog_id 与被查询 catalog 一致。"""
    await _ask(
        client, auth_headers, two_catalogs["education_catalog_id"], "查询教育账单"
    )
    catalog_id, _ = await _latest_audit_row()
    assert catalog_id == two_catalogs["education_catalog_id"]

    await _ask(
        client, auth_headers, two_catalogs["park_catalog_id"], "查询园区账单"
    )
    catalog_id, _ = await _latest_audit_row()
    assert catalog_id == two_catalogs["park_catalog_id"]


async def test_dual_key_lookup_resolves_correct_model_per_catalog(
    db_session, two_catalogs
):
    """仓储层双键查询：同 entity_type 按 catalog_id 路由到不同 model."""
    repo = SemanticModelRepository(db_session)
    edu_model = await repo.get_active_by_catalog_and_entity_type(
        DEFAULT_TENANT_ID, two_catalogs["education_catalog_id"], "bill"
    )
    park_model = await repo.get_active_by_catalog_and_entity_type(
        DEFAULT_TENANT_ID, two_catalogs["park_catalog_id"], "bill"
    )
    assert edu_model is not None and park_model is not None
    assert edu_model.id != park_model.id
    assert edu_model.entity_name == "教育账单"
    assert park_model.entity_name == "园区账单"
    # Each model points at its own catalog's dataset.
    assert edu_model.catalog_id == two_catalogs["education_catalog_id"]
    assert park_model.catalog_id == two_catalogs["park_catalog_id"]
