from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentDefinitionVersionModel(Base):
    __tablename__ = "agent_definition_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "id", name="uq_agent_definition_tenant_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "definition_key",
            "version",
            name="uq_agent_definition_key_version",
        ),
        CheckConstraint("version >= 1", name="ck_agent_definition_version"),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_agent_definition_status",
        ),
        CheckConstraint(
            "char_length(definition_digest) = 64",
            name="ck_agent_definition_digest",
        ),
        Index(
            "ix_agent_definition_catalog",
            "tenant_id",
            "status",
            "definition_key",
            "version",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    definition_key: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    definition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class RuntimeProfileModel(Base):
    __tablename__ = "agent_runtime_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_runtime_profile_tenant_id"),
        UniqueConstraint(
            "tenant_id", "profile_key", name="uq_agent_runtime_profile_key"
        ),
        CheckConstraint(
            "char_length(config_digest) = 64 AND "
            "char_length(capability_digest) = 64",
            name="ck_agent_runtime_profile_digests",
        ),
        CheckConstraint("revision >= 1", name="ck_agent_runtime_profile_revision"),
        Index(
            "ix_agent_runtime_profile_resolve",
            "tenant_id",
            "enabled",
            "profile_key",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(150), nullable=False)
    runtime_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RuntimeSessionBindingModel(Base):
    __tablename__ = "agent_runtime_session_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_runtime_binding_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_runtime_binding_profile",
        ),
        CheckConstraint(
            "status IN ('creating', 'active', 'resume_required', 'closed', 'invalid')",
            name="ck_agent_runtime_binding_status",
        ),
        CheckConstraint(
            "current_epoch >= 1 AND next_expected_runtime_seq >= 1 AND "
            "acked_through_runtime_seq >= 0 AND "
            "next_expected_runtime_seq = acked_through_runtime_seq + 1",
            name="ck_agent_runtime_binding_cursor",
        ),
        CheckConstraint("revision >= 1", name="ck_agent_runtime_binding_revision"),
        CheckConstraint(
            "(active_stream_id IS NULL AND stream_lease_expires_at IS NULL) OR "
            "(active_stream_id IS NOT NULL AND stream_lease_expires_at IS NOT NULL)",
            name="ck_agent_runtime_binding_stream_lease",
        ),
        CheckConstraint(
            "runtime_session_ref IS NULL OR char_length(runtime_session_ref) > 0",
            name="ck_agent_runtime_binding_session_ref",
        ),
        Index(
            "uq_agent_runtime_binding_session_ref",
            "tenant_id",
            "runtime_profile_id",
            "runtime_session_ref",
            unique=True,
            postgresql_where=text("runtime_session_ref IS NOT NULL"),
        ),
        Index(
            "ix_agent_runtime_binding_conversation",
            "tenant_id",
            "conversation_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_agent_runtime_binding_stream_lease",
            "tenant_id",
            "stream_lease_expires_at",
            postgresql_where=text("active_stream_id IS NOT NULL"),
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    runtime_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    runtime_session_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="creating"
    )
    current_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    next_expected_runtime_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1
    )
    acked_through_runtime_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    active_stream_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    stream_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
