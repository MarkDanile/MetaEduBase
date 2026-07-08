"""Semantic model repository — CRUD + column scan + drift detection (REQ-052).

Public surface:

- :meth:`SemanticModelRepository.create` — persist a new semantic model row.
- :meth:`SemanticModelRepository.get_by_entity_type` — fetch the active
  semantic model for a ``(tenant, entity_type, data_source_config)`` triple.
  Inactive (``status != 'active'``) rows are filtered out.
- :meth:`SemanticModelRepository.scan_dataset_columns` — return the distinct
  JSONB keys that appear in ``metaedu.dataset_rows.data`` for the given
  dataset. Powers drift detection and on-boarding flows.
- :meth:`SemanticModelRepository.detect_drift` — convenience wrapper around
  :meth:`scan_dataset_columns` that compares actual vs registered columns.

The repository never touches the adapter layer; it deals exclusively with
``metaedu.semantic_models`` and ``metaedu.dataset_rows``. Adapters live in
``infrastructure/imported_dataset_adapter.py`` etc.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.models import DatasetRowModel
from app.contexts.structured_data.infrastructure.semantic_models_models import (
    SemanticModelModel,
)


class SemanticModelRepository:
    """Repository over ``metaedu.semantic_models``.

    The constructor takes the AsyncSession so that callers can compose the
    repository into a larger unit-of-work (FastAPI dependency, batch job).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        model: SemanticModel,
        catalog_id: uuid.UUID | None = None,
    ) -> None:
        """Persist a new semantic model row.

        Uses ``flush`` (not commit) so the caller's transaction controls the
        boundary. JSONB columns are populated via the dataclass-to-dict
        converters, which guarantees the on-disk shape stays in sync with
        the dataclass contract.

        ``catalog_id`` is REQUIRED (REQ-054): every semantic model belongs to
        a specific data catalog, and the new unique constraint
        ``(tenant_id, catalog_id, entity_type, data_source_config)`` enforces
        this. The caller must pass it explicitly via the ``catalog_id``
        argument (or by setting ``model.catalog_id`` before calling
        ``create``) — auto-resolution has been removed so the caller can
        always choose the correct catalog for multi-tenant / multi-catalog
        setups.
        """
        # REQ-054: catalog_id is now an explicit, caller-supplied value.
        # Accept it from the function argument first, then fall back to the
        # domain model. We do NOT auto-resolve to "education" anymore —
        # explicit beats implicit once a tenant can have multiple catalogs.
        resolved_catalog_id = catalog_id if catalog_id is not None else model.catalog_id
        if resolved_catalog_id is None:
            raise ValueError(
                "catalog_id is required (REQ-054): pass it to create() or "
                "set model.catalog_id before persisting"
            )
        row = SemanticModelModel(
            id=model.id,
            tenant_id=model.tenant_id,
            catalog_id=resolved_catalog_id,
            dataset_id=model.dataset_id,
            entity_type=model.entity_type,
            entity_name=model.entity_name,
            data_source_config=model.data_source_config,
            column_mapping={
                key: value.to_dict() for key, value in model.column_mapping.items()
            },
            metric_definitions={
                key: value.to_dict() for key, value in model.metric_definitions.items()
            },
            version=model.version,
            status=model.status,
            created_by=model.created_by,
        )
        self._session.add(row)
        await self._session.flush()

    async def get_by_entity_type(
        self,
        tenant_id: uuid.UUID,
        entity_type: str,
        data_source_config: dict,
    ) -> SemanticModel | None:
        """Return the active semantic model for the given triple, or ``None``.

        Filters out non-active rows so callers don't have to second-guess
        the status. The ``data_source_config.cast(JSONB) ==`` comparison is
        defensive — SQLAlchemy already serializes dict-typed JSONB columns
        for equality, but the explicit cast guards against any dialect
        edge-case where the column type metadata is missing.
        """
        stmt = select(SemanticModelModel).where(
            SemanticModelModel.tenant_id == tenant_id,
            SemanticModelModel.entity_type == entity_type,
            SemanticModelModel.data_source_config.cast(JSONB) == data_source_config,
            SemanticModelModel.status == "active",
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def get_active_by_catalog_and_entity_type(
        self,
        tenant_id: uuid.UUID,
        catalog_id: uuid.UUID,
        entity_type: str,
    ) -> SemanticModel | None:
        """REQ-054: 按 (catalog_id, entity_type) 双键查询 active model.

        Filters by BOTH ``catalog_id`` and ``entity_type`` (plus
        ``status='active'``) so the lookup is safe even when a tenant has
        multiple catalogs with different schemas for the same
        ``entity_type``. The old single-key method
        :meth:`get_active_by_entity_type` would raise
        ``MultipleResultsFound`` as soon as a tenant creates a second
        catalog — this method replaces it for any caller that has a
        ``catalog_id`` in scope.
        """
        stmt = select(SemanticModelModel).where(
            SemanticModelModel.tenant_id == tenant_id,
            SemanticModelModel.catalog_id == catalog_id,
            SemanticModelModel.entity_type == entity_type,
            SemanticModelModel.status == "active",
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def get_active_by_entity_type(
        self,
        tenant_id: uuid.UUID,
        entity_type: str,
    ) -> SemanticModel | None:
        """Return the active semantic model for ``(tenant_id, entity_type)``.

        .. deprecated::
            REQ-054: this method does NOT filter by ``catalog_id`` and is
            unsafe once a tenant has more than one catalog. The SQL
            query orders by ``updated_at DESC`` and applies ``LIMIT 1``,
            so when multiple active rows share ``(tenant_id, entity_type)``
            the method **silently returns one of them** (the most
            recently updated row). Callers therefore cannot tell whether
            they got the "right" row for their catalog. New callers MUST
            use :meth:`get_active_by_catalog_and_entity_type` and pass
            an explicit ``catalog_id``. This method is kept for backward
            compatibility with the REQ-052 single-tenant path until the
            router migrates (tracked outside this task).
        """
        stmt = (
            select(SemanticModelModel)
            .where(
                SemanticModelModel.tenant_id == tenant_id,
                SemanticModelModel.entity_type == entity_type,
                SemanticModelModel.status == "active",
            )
            .order_by(SemanticModelModel.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def scan_dataset_columns(self, dataset_id: uuid.UUID) -> set[str]:
        """Return the distinct JSONB keys present in ``dataset_rows.data``.

        PostgreSQL's ``jsonb_object_keys`` returns one row per top-level key
        across all rows of the dataset; ``DISTINCT`` collapses duplicates.
        If no rows exist the result is an empty set (no exception).
        """
        stmt = (
            select(func.jsonb_object_keys(DatasetRowModel.data).label("key"))
            .where(DatasetRowModel.dataset_id == dataset_id)
            .distinct()
        )
        result = await self._session.execute(stmt)
        return {row.key for row in result.all()}

    async def detect_drift(
        self, dataset_id: uuid.UUID, model: SemanticModel
    ) -> dict:
        """Compare actual dataset columns against the registered mapping.

        Returns ``{"new_columns": [...], "removed_columns": [...]}`` where:

        - ``new_columns`` are present in the data but not in
          ``model.column_mapping``.
        - ``removed_columns`` are registered in ``model.column_mapping``
          but no longer present in the data.
        """
        actual = await self.scan_dataset_columns(dataset_id)
        registered = set(model.column_mapping.keys())
        return {
            "new_columns": sorted(actual - registered),
            "removed_columns": sorted(registered - actual),
        }

    def _to_domain(self, row: SemanticModelModel) -> SemanticModel:
        """Map an ORM row back to the :class:`SemanticModel` dataclass."""
        return SemanticModel(
            id=row.id,
            tenant_id=row.tenant_id,
            catalog_id=row.catalog_id,
            dataset_id=row.dataset_id,
            entity_type=row.entity_type,
            entity_name=row.entity_name,
            data_source_config=row.data_source_config,
            column_mapping={
                key: ColumnMapping.from_dict(value)
                for key, value in row.column_mapping.items()
            },
            metric_definitions={
                key: MetricDefinition.from_dict(value)
                for key, value in row.metric_definitions.items()
            },
            version=row.version,
            status=row.status,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
