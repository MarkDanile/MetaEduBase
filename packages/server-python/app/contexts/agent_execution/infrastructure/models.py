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
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
        UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            "runtime_profile_id",
            name="uq_agent_runtime_binding_owner",
        ),
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


class AgentRunModel(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_run_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            name="uq_agent_run_tenant_conversation_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            "correlation_id",
            name="uq_agent_run_event_owner",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            "runtime_profile_id",
            "runtime_binding_id",
            name="uq_agent_run_runtime_owner",
        ),
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "queue_seq",
            name="uq_agent_run_queue_seq",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_definition_version_id"],
            [
                "metaedu.agent_definition_versions.tenant_id",
                "metaedu.agent_definition_versions.id",
            ],
            name="fk_agent_run_definition",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_run_profile",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "runtime_binding_id"],
            [
                "metaedu.agent_runtime_session_bindings.tenant_id",
                "metaedu.agent_runtime_session_bindings.id",
            ],
            name="fk_agent_run_binding",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "runtime_binding_id",
                "conversation_id",
                "runtime_profile_id",
            ],
            [
                "metaedu.agent_runtime_session_bindings.tenant_id",
                "metaedu.agent_runtime_session_bindings.id",
                "metaedu.agent_runtime_session_bindings.conversation_id",
                "metaedu.agent_runtime_session_bindings.runtime_profile_id",
            ],
            name="fk_agent_run_binding_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_run_parent",
        ),
        CheckConstraint(
            "status IN ('queued', 'starting', 'running', 'waiting_input', "
            "'waiting_approval', 'resume_required', 'cancelling', 'completed', "
            "'failed', 'cancelled', 'expired')",
            name="ck_agent_run_status",
        ),
        CheckConstraint(
            "output_publish_state IN ('not_required', 'pending', 'published', "
            "'dead_letter', 'suppressed')",
            name="ck_agent_run_output_publish_state",
        ),
        CheckConstraint(
            "queue_seq >= 1 AND status_revision >= 1 AND next_event_seq >= 1 "
            "AND first_available_event_seq >= 1 AND last_event_seq >= 0 "
            "AND next_event_seq = last_event_seq + 1 "
            "AND first_available_event_seq <= next_event_seq",
            name="ck_agent_run_sequences",
        ),
        CheckConstraint(
            "char_length(creation_digest) = 64",
            name="ck_agent_run_creation_digest",
        ),
        CheckConstraint(
            "(context_snapshot_ref IS NULL AND context_snapshot_digest IS NULL "
            "AND context_snapshot_classification IS NULL) OR "
            "(context_snapshot_ref IS NOT NULL AND "
            "char_length(context_snapshot_digest) = 64 AND "
            "context_snapshot_classification IN ('public', 'internal', 'restricted'))",
            name="ck_agent_run_context_snapshot",
        ),
        CheckConstraint(
            "pg_column_size(runtime_capability_snapshot) <= 32768 AND "
            "pg_column_size(run_config_snapshot) <= 32768 AND "
            "pg_column_size(budget_snapshot) <= 32768 AND "
            "pg_column_size(usage_summary) <= 32768",
            name="ck_agent_run_snapshot_size",
        ),
        CheckConstraint(
            "(status NOT IN ('completed', 'failed', 'cancelled', 'expired') "
            "AND ended_at IS NULL AND terminal_result_digest IS NULL "
            "AND terminal_code IS NULL AND terminal_reason IS NULL) OR "
            "(status IN ('completed', 'failed', 'cancelled', 'expired') "
            "AND ended_at IS NOT NULL AND char_length(terminal_result_digest) = 64 "
            "AND terminal_code IS NOT NULL AND terminal_reason IS NOT NULL)",
            name="ck_agent_run_terminal_envelope",
        ),
        CheckConstraint(
            "(status = 'completed' AND terminal_output_ref IS NOT NULL "
            "AND char_length(btrim(terminal_output_ref)) > 0 "
            "AND terminal_output_ref = btrim(terminal_output_ref) "
            "AND char_length(terminal_output_digest) = 64 "
            "AND terminal_output_size >= 0 AND terminal_output_media_type IS NOT NULL "
            "AND char_length(btrim(terminal_output_media_type)) > 0 "
            "AND terminal_output_media_type = btrim(terminal_output_media_type) "
            "AND position('/' IN terminal_output_media_type) > 1 "
            "AND position('/' IN terminal_output_media_type) "
            "< char_length(terminal_output_media_type) "
            "AND terminal_output_classification IN ('public', 'internal', 'restricted') "
            "AND terminal_message_id IS NOT NULL "
            "AND output_publish_state IN ('pending', 'published', 'dead_letter', "
            "'suppressed')) OR "
            "(status <> 'completed' AND terminal_output_ref IS NULL "
            "AND terminal_output_digest IS NULL AND terminal_output_size IS NULL "
            "AND terminal_output_media_type IS NULL "
            "AND terminal_output_classification IS NULL "
            "AND terminal_message_id IS NULL "
            "AND output_publish_state = 'not_required')",
            name="ck_agent_run_terminal_output",
        ),
        Index(
            "uq_agent_run_one_active",
            "tenant_id",
            "conversation_id",
            unique=True,
            postgresql_where=text(
                "status IN ('starting', 'running', 'waiting_input', "
                "'waiting_approval', 'resume_required', 'cancelling')"
            ),
        ),
        Index(
            "ix_agent_run_queue",
            "tenant_id",
            "conversation_id",
            "queue_seq",
            "status",
        ),
        Index(
            "ix_agent_run_recovery",
            "tenant_id",
            "status",
            "updated_at",
            "id",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    queue_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    root_input_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    agent_definition_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    runtime_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    runtime_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    creation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    status_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    next_event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    first_available_event_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1
    )
    last_event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    event_log_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminal_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    terminal_result_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    terminal_output_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    terminal_output_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    terminal_output_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    terminal_output_media_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    terminal_output_classification: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    terminal_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    output_publish_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_required"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    runtime_capability_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    run_config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_snapshot_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_snapshot_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    context_snapshot_classification: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    budget_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usage_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class TurnInputModel(Base):
    __tablename__ = "agent_turn_inputs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "run_id", "ordinal", name="uq_agent_turn_input_ordinal"
        ),
        UniqueConstraint(
            "tenant_id", "request_id", name="uq_agent_turn_input_request"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_turn_input_run",
        ),
        CheckConstraint("ordinal >= 0", name="ck_agent_turn_input_ordinal"),
        CheckConstraint(
            "input_kind IN ('root', 'steer', 'human_response')",
            name="ck_agent_turn_input_kind",
        ),
        CheckConstraint(
            "(input_kind = 'root' AND ordinal = 0 AND expected_runtime_epoch IS NULL) "
            "OR (input_kind IN ('steer', 'human_response') AND ordinal >= 1 "
            "AND expected_runtime_epoch >= 1)",
            name="ck_agent_turn_input_envelope",
        ),
        CheckConstraint(
            "char_length(context_digest) = 64",
            name="ck_agent_turn_input_context_digest",
        ),
        Index(
            "uq_agent_turn_input_root",
            "tenant_id",
            "run_id",
            unique=True,
            postgresql_where=text("input_kind = 'root'"),
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    input_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expected_runtime_epoch: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class RunEventModel(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_run_event_tenant_id"),
        UniqueConstraint(
            "tenant_id", "run_id", "seq", name="uq_agent_run_event_seq"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_run_event_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "conversation_id"],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
            ],
            name="fk_agent_run_event_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "conversation_id", "correlation_id"],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
                "metaedu.agent_runs.correlation_id",
            ],
            name="fk_agent_run_event_owner",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "run_id",
                "conversation_id",
                "runtime_profile_id",
                "runtime_binding_id",
            ],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
                "metaedu.agent_runs.runtime_profile_id",
                "metaedu.agent_runs.runtime_binding_id",
            ],
            name="fk_agent_run_event_runtime_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_run_event_profile",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "runtime_binding_id"],
            [
                "metaedu.agent_runtime_session_bindings.tenant_id",
                "metaedu.agent_runtime_session_bindings.id",
            ],
            name="fk_agent_run_event_binding",
        ),
        CheckConstraint("seq >= 1", name="ck_agent_run_event_seq"),
        CheckConstraint("schema_version >= 1", name="ck_agent_run_event_schema"),
        CheckConstraint(
            "visibility IN ('user', 'tenant_admin', 'internal')",
            name="ck_agent_run_event_visibility",
        ),
        CheckConstraint(
            "classification IN ('public', 'internal', 'restricted')",
            name="ck_agent_run_event_classification",
        ),
        CheckConstraint(
            "payload_state IN ('inline', 'external', 'redacted', 'expired', 'archived')",
            name="ck_agent_run_event_payload_state",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64 AND payload_size >= 0",
            name="ck_agent_run_event_payload_digest",
        ),
        CheckConstraint(
            "char_length(btrim(media_type)) > 2 "
            "AND media_type = btrim(media_type) "
            "AND position('/' IN media_type) > 1 "
            "AND position('/' IN media_type) < char_length(media_type)",
            name="ck_agent_run_event_media_type",
        ),
        CheckConstraint(
            "(payload_state = 'inline' AND payload_inline IS NOT NULL "
            "AND payload_ref IS NULL AND classification <> 'restricted' "
            "AND payload_size <= 32768 AND pg_column_size(payload_inline) <= 32768) "
            "OR (payload_state = 'external' AND payload_inline IS NULL "
            "AND payload_ref IS NOT NULL) "
            "OR (payload_state IN ('redacted', 'expired', 'archived') "
            "AND payload_inline IS NULL)",
            name="ck_agent_run_event_payload",
        ),
        CheckConstraint(
            "(runtime_profile_id IS NULL AND runtime_binding_id IS NULL "
            "AND runtime_epoch IS NULL AND runtime_seq IS NULL "
            "AND runtime_event_id IS NULL AND runtime_event_digest IS NULL) OR "
            "(runtime_profile_id IS NOT NULL AND runtime_binding_id IS NOT NULL "
            "AND runtime_epoch IS NOT NULL AND runtime_epoch >= 1 "
            "AND runtime_seq IS NOT NULL AND runtime_seq >= 1 "
            "AND runtime_event_id IS NOT NULL "
            "AND runtime_event_digest IS NOT NULL "
            "AND char_length(runtime_event_digest) = 64)",
            name="ck_agent_run_event_runtime_provenance",
        ),
        Index(
            "uq_agent_run_event_runtime_seq",
            "tenant_id",
            "runtime_binding_id",
            "runtime_epoch",
            "runtime_seq",
            unique=True,
            postgresql_where=text("runtime_binding_id IS NOT NULL"),
        ),
        Index(
            "uq_agent_run_event_runtime_id",
            "tenant_id",
            "runtime_binding_id",
            "runtime_epoch",
            "runtime_event_id",
            unique=True,
            postgresql_where=text("runtime_binding_id IS NOT NULL"),
        ),
        Index(
            "uq_agent_run_event_terminal",
            "tenant_id",
            "run_id",
            unique=True,
            postgresql_where=text(
                "event_type IN ('run.completed', 'run.failed', "
                "'run.cancelled', 'run.expired')"
            ),
        ),
        Index(
            "ix_agent_run_event_replay", "tenant_id", "run_id", "seq"
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    persisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_inline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload_state: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    runtime_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    runtime_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    runtime_epoch: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    runtime_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    runtime_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    runtime_event_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class ExecutionOutboxModel(Base):
    __tablename__ = "agent_execution_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'published', 'dead_letter', 'cancelled')",
            name="ck_agent_exec_outbox_status",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_exec_outbox_digest",
        ),
        Index(
            "ix_agent_exec_outbox_dispatch",
            "tenant_id",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ExecutionInboxModel(Base):
    __tablename__ = "agent_execution_inbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "consumer_name",
            "event_id",
            name="uq_agent_exec_inbox_event",
        ),
        CheckConstraint(
            "status IN ('processing', 'consumed', 'rejected')",
            name="ck_agent_exec_inbox_status",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_exec_inbox_digest",
        ),
        Index(
            "ix_agent_exec_inbox_status", "tenant_id", "status", "created_at"
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consumer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
