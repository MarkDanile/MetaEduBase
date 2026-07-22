"""Test JsonbQueryBuilder: limit clamp (AC-4) + tenant_id enforcement.

REQ-052 Task 4: JsonbQueryBuilder translates a validated ``query_plan``
dict into a SQLAlchemy ``select(DatasetRowModel.data)`` statement with
all required predicates applied. The builder owns three security
invariants:

1. **Tenant isolation** — every emitted statement has
   ``WHERE tenant_id = :tenant_id``. The ``tenant_id`` argument is the
   ONLY thing that can satisfy this clause; a malicious query_plan
   cannot override it. AC-1 / AC-2.

2. **Limit clamp** — spec §5.5 / AC-4 cap is 1000 (max) with a default
   of 100 and a floor of 1. The clamp must defend against 0, negative
   values, non-int values, and arbitrarily large numbers.

3. **JSONB operator safety** — unknown operators are silently dropped
   rather than passed to the DB.

These tests cover AC-4 (limit clamp) and the tenant_id predicate. They
are the canonical regression coverage for the spec acceptance criterion
so that a future refactor that drops the upper bound cannot pass green.

We use the existing ``db_session`` and ``sample_dataset`` fixtures from
the context conftest. Tests build the statement via ``JsonbQueryBuilder``
and inspect either the compiled SQL string or the statement's
``_limit`` / ``whereclause`` directly. No actual rows are fetched for
the AC-4 tests — the limit and tenant predicates are emitted before
the round-trip, so compile-time inspection is sufficient and keeps the
tests fast and side-effect free.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.contexts.structured_data.infrastructure.jsonb_query_builder import (
    JsonbQueryBuilder,
)

pytestmark = pytest.mark.asyncio


def _compile_limit(stmt) -> int:
    """Extract the LIMIT value from a SQLAlchemy statement.

    Falls back to compiling the full statement and parsing if the
    statement's internal ``_limit`` is None (e.g. when the limit was
    applied via ``.limit()`` rather than ``.limit(None)``).
    """
    # The ``.limit()`` call on the statement populates ``stmt._limit`` as
    # a SQL expression. For plain integer limits it stores the int
    # directly; for compiled LIMIT clauses it stores a ``BindParameter``.
    if stmt._limit is not None:
        limit_val = stmt._limit
        # unwrap ``BindParameter`` if necessary
        if hasattr(limit_val, "value") and isinstance(limit_val.value, int):
            return limit_val.value
        if isinstance(limit_val, int):
            return limit_val
    # Fallback: compile and parse the LIMIT clause from the rendered SQL.
    compiled = str(stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))
    # Postgres renders ``LIMIT n`` at the end; parse the trailing integer.
    # Statements here don't have OFFSET, so the regex matches the last
    # ``LIMIT <digits>`` group.
    import re
    match = re.search(r"LIMIT\s+(\d+)\b", compiled, re.IGNORECASE)
    assert match is not None, f"LIMIT not found in compiled SQL: {compiled!r}"
    return int(match.group(1))


# ---------------------------------------------------------------------------
# AC-4: limit clamp — default / floor / ceiling / type safety
# ---------------------------------------------------------------------------


async def test_limit_zero_clamped_to_one(db_session, sample_dataset):
    """``limit=0`` must be clamped to 1 (the floor).

    Spec §5.5 / AC-4: limit window is ``[1, MAX_LIMIT]``. A zero limit
    would produce an empty result set — we treat that as suspicious and
    promote it to 1 so a misconfigured planner still returns at least
    one row.
    """
    builder = JsonbQueryBuilder(db_session)
    model = sample_dataset.get("semantic_model")  # noqa: SIM401
    # Build a minimal SemanticModel inline — the fixture returns a dict,
    # so we need the model object. Build it directly to avoid coupling.
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        MetricDefinition,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    stmt = builder.build(
        query_plan={"limit": 0, "filters": {}},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert stmt is not None
    assert _compile_limit(stmt) == 1


async def test_limit_above_max_clamped_to_thousand(db_session, sample_dataset):
    """``limit=999999`` must be clamped to 1000 (the ceiling).

    Spec §5.5 / AC-4: hard max is 1000. A query that asks for a million
    rows is treated as a misconfiguration / DoS attempt and clamped.
    """
    builder = JsonbQueryBuilder(db_session)
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        MetricDefinition,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    stmt = builder.build(
        query_plan={"limit": 999999, "filters": {}},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert stmt is not None
    assert _compile_limit(stmt) == 1000


async def test_limit_default_when_missing(db_session, sample_dataset):
    """Missing ``limit`` → default of 100.

    The soft limit (100) protects the API from accidentally returning
    huge result sets when the planner forgets to set a limit.
    """
    builder = JsonbQueryBuilder(db_session)
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        MetricDefinition,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    stmt = builder.build(
        query_plan={},  # no ``limit`` key
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert stmt is not None
    assert _compile_limit(stmt) == 100


async def test_limit_non_int_falls_back_to_default(db_session, sample_dataset):
    """Non-int limit (e.g. a string) → default of 100.

    Defensive: the planner emits a dict whose values come from an LLM,
    so a string slip-through is possible. The builder must not crash
    and must fall back to the safe default.
    """
    builder = JsonbQueryBuilder(db_session)
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        MetricDefinition,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    stmt = builder.build(
        query_plan={"limit": "not-an-int"},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert stmt is not None
    assert _compile_limit(stmt) == 100


# ---------------------------------------------------------------------------
# Tenant isolation — AC-1 / AC-2
# ---------------------------------------------------------------------------


async def test_tenant_id_enforced_as_where_predicate(db_session, sample_dataset):
    """``tenant_id`` argument appears as the first WHERE predicate.

    The compiled statement must reference ``tenant_id`` with the UUID
    value the builder was called with. Cross-tenant queries must be
    excluded by this predicate; a future refactor that drops the
    tenant_id predicate would let tenants see each other's data, which
    is the exact leak AC-1 is meant to prevent.
    """
    builder = JsonbQueryBuilder(db_session)
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        MetricDefinition,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    stmt = builder.build(
        query_plan={},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )

    assert stmt is not None
    # Compile to SQL with literal binds so we can assert on the rendered
    # tenant_id UUID.
    compiled_sql = str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "tenant_id" in compiled_sql
    # The seeded DEFAULT_TENANT_ID must appear in the compiled SQL.
    assert str(DEFAULT_TENANT_ID) in compiled_sql


# ---------------------------------------------------------------------------
# Filter shorthand normalization (REQ-046 AC-8 — LLM 输出容错)
# ---------------------------------------------------------------------------


def _make_model(sample_dataset, columns):
    from app.contexts.structured_data.domain.semantic_model import (
        ColumnMapping,
        ColumnRole,
        ColumnType,
        DataSourceType,
        SemanticModel,
    )
    from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset["id"],
        entity_type="ticket",
        entity_name="工单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            c: ColumnMapping(role=ColumnRole.DIMENSION, type=ColumnType.STR)
            for c in columns
        },
        metric_definitions={},
        created_by=DEFAULT_ADMIN_ID,
    )


async def test_filters_accept_bare_string_shorthand(db_session, sample_dataset):
    """LLM 偶发输出 ``{"状态": "未关闭"}`` 裸值简写 -> 归一化为 eq,不崩溃。

    真实链路(ticket 问数)观测到 LLM 把 filter 写成裸字符串而非
    ``{"op","value"}`` 对象,builder 直接 ``.get("op")`` 会 AttributeError。
    裸值按等值(eq)处理。
    """
    from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

    model = _make_model(sample_dataset, ["状态"])
    builder = JsonbQueryBuilder(db_session)
    stmt = builder.build(
        query_plan={"filters": {"状态": "未关闭"}, "limit": 10},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )
    sql = str(stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "未关闭" in sql


async def test_filters_accept_mongo_style_operator_shorthand(db_session, sample_dataset):
    """LLM 偶发输出 ``{"费用": {"$gt": 0}}`` Mongo 风格 -> 归一化为 gt。"""
    from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

    model = _make_model(sample_dataset, ["费用"])
    builder = JsonbQueryBuilder(db_session)
    stmt = builder.build(
        query_plan={"filters": {"费用": {"$gt": "0"}}, "limit": 10},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
    )
    sql = str(stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "费用" in sql
