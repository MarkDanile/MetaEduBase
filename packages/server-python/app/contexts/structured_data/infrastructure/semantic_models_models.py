"""Semantic models + RBAC + audit log ORM for REQ-052.

Maps the four REQ-052 schema tables introduced in alembic migrations 012-015:

- ``metaedu.semantic_models`` -> :class:`SemanticModelModel`
- ``metaedu.role_permissions`` -> :class:`RolePermissionModel`
- ``metaedu.tenant_access_grants`` -> :class:`TenantAccessGrantModel`
- ``metaedu.query_audit_log`` -> :class:`QueryAuditLogModel`

All four classes share the ``metaedu`` schema via ``__table_args__`` and use
``app.shared.infrastructure.database.Base`` as the declarative base.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    """Naive UTC ``datetime`` matching the project convention (see
    ``app/contexts/structured_data/infrastructure/dataset_repository.py``)."""
    return datetime.now(UTC).replace(tzinfo=None)


class SemanticModelModel(Base):
    __tablename__ = "semantic_models"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.datasets.id", ondelete="CASCADE"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_source_config: Mapped[dict] = mapped_column(
        PG_JSONB, nullable=False, default=dict
    )
    column_mapping: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    metric_definitions: Mapped[dict] = mapped_column(
        PG_JSONB, nullable=False, default=dict
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility_rules: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class TenantAccessGrantModel(Base):
    __tablename__ = "tenant_access_grants"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    grantee_tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class QueryAuditLogModel(Base):
    __tablename__ = "query_audit_log"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    business_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_plan: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    data_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data_source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, index=True
    )