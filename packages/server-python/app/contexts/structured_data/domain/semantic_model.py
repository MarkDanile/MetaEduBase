"""Semantic model domain entities (REQ-052).

The semantic layer is the bridge between raw datasets / external data sources
and the business entities the intelligent-data-query pipeline reasons about.

Three enums anchor the vocabulary:

- :class:`DataSourceType` — which adapter should service this semantic model.
- :class:`ColumnRole` — what a column is *for* in the business sense
  (entity key, metric, dimension, filter).
- :class:`ColumnType` — the column's storage shape (``str`` / ``float`` etc).

Two value dataclasses:

- :class:`ColumnMapping` — the role + type + sensitivity + synonyms for a
  single dataset column.
- :class:`MetricDefinition` — a derived measure (e.g. ``total_amount`` =
  ``SUM(amount)``).

And the aggregate:

- :class:`SemanticModel` — the full entity mapping. Stored in
  ``metaedu.semantic_models`` (Task 1 schema).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class DataSourceType(StrEnum):
    """Which adapter family the semantic model is bound to.

    V1 ships :attr:`IMPORTED_DATASET`; :attr:`DIRECT_DB` and :attr:`MCP` are
    declared so the contract is in place but the implementations are
    intentional NotImplementedError placeholders.
    """

    IMPORTED_DATASET = "imported_dataset"
    DIRECT_DB = "direct_db"  # V1 placeholder
    MCP = "mcp"  # V1 placeholder


class ColumnRole(StrEnum):
    """Business role of a column in the semantic model."""

    ENTITY_KEY = "entity_key"
    METRIC = "metric"
    DIMENSION = "dimension"
    FILTER = "filter"


class ColumnType(StrEnum):
    """Storage shape of a column.

    Matches the ``str`` / ``float`` / ``int`` / ``date`` / ``bool`` strings
    stored in ``metaedu.datasets.column_types``.
    """

    STR = "str"
    FLOAT = "float"
    INT = "int"
    DATE = "date"
    BOOL = "bool"


@dataclass
class ColumnMapping:
    """Role + type + sensitivity + synonyms for one dataset column.

    ``to_dict`` / ``from_dict`` are symmetric so the repository can serialize
    to JSONB on write and rebuild the dataclass on read without losing
    information. ``synonym`` is a list (preserves order) and defaults to
    empty so a freshly-registered column doesn't need to specify it.
    """

    role: ColumnRole
    type: ColumnType
    sensitive: bool = False
    synonym: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "type": self.type.value,
            "sensitive": self.sensitive,
            "synonym": list(self.synonym),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ColumnMapping:
        return cls(
            role=ColumnRole(d["role"]),
            type=ColumnType(d["type"]),
            sensitive=d.get("sensitive", False),
            synonym=list(d.get("synonym", [])),
        )


@dataclass
class MetricDefinition:
    """A derived measure the question-answering pipeline can emit.

    ``aggregation`` is intentionally ``str`` (not an enum) because we expect
    new SQL aggregations (``percentile_cont``, ``array_agg`` ...) to be added
    over time without a migration.
    """

    column: str
    aggregation: str  # sum / count / avg / ...
    label: str

    def to_dict(self) -> dict:
        return {
            "column": self.column,
            "aggregation": self.aggregation,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MetricDefinition:
        return cls(
            column=d["column"],
            aggregation=d["aggregation"],
            label=d["label"],
        )


@dataclass
class SemanticModel:
    """The full semantic mapping for one business entity.

    ``column_mapping`` and ``metric_definitions`` are stored as nested
    dataclasses in-memory and as JSONB dicts on disk — the repository
    bridges the two via :meth:`ColumnMapping.to_dict` / :meth:`from_dict`.

    ``created_at`` / ``updated_at`` are optional because callers building
    a new model in tests or service code may not have them yet; the DB
    column defaults will fill them in on flush.

    ``catalog_id`` is REQ-054's tenant-scoped database identity; it is
    placed after the required positional fields so it can keep a default
    of ``None`` (preserving the historical constructor shape for callers
    that don't yet care about multi-catalog routing). The repository
    rejects ``catalog_id=None`` at create time.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: str
    entity_name: str
    data_source_config: dict
    column_mapping: dict[str, ColumnMapping]
    metric_definitions: dict[str, MetricDefinition]
    dataset_id: uuid.UUID | None = None
    version: str = "v1"
    status: str = "active"
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    catalog_id: uuid.UUID | None = None  # REQ-054: 所属数据库
