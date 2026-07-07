"""Catalog ORM for REQ-054 (metaedu.data_catalogs).

Maps the ``metaedu.data_catalogs`` table introduced in alembic migration
016. A catalog is a tenant-scoped thematic database that groups datasets,
semantic models, knowledge nodes and query audit logs into a business
domain (e.g. ``education``, ``finance``, ``facility``).

The model mirrors the column layout defined in the migration exactly —
``entity_types`` is a JSONB list of entity type codes that belong to this
catalog, ``is_active`` allows soft-deactivation without losing FK
references, and ``created_by`` ties the catalog to the admin who created
it (default-seed rows use ``DEFAULT_ADMIN_ID``).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    """Naive UTC datetime matching the project convention."""
    return datetime.now(UTC).replace(tzinfo=None)


class CatalogModel(Base):
    """ORM row over ``metaedu.data_catalogs``."""

    __tablename__ = "data_catalogs"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity_types: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    default_business_purpose: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
