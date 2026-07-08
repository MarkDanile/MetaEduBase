"""Catalog domain entity for REQ-054.

A catalog is a tenant-scoped thematic database that groups datasets, semantic
models, knowledge nodes and query audit logs into a business domain
(e.g. ``education``, ``finance``, ``facility``). This dataclass is the
pure-Python domain representation — persistence is handled by
:class:`CatalogModel` (ORM) and :class:`CatalogRepository` (CRUD).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Catalog:
    """Domain entity for a thematic database catalog."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    entity_types: list[str] = field(default_factory=list)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    default_business_purpose: str | None = None
    is_active: bool = True
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def allows_entity_type(self, entity_type: str) -> bool:
        """白名单校验：entity_type 是否在该 catalog 支持列表内。"""
        return entity_type in self.entity_types
