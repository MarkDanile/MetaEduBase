"""create REQ-047 E1 Agent Run and Event durable core

Revision ID: 030_agent_execution_durable_core
Revises: 029_agent_execution_identity
Create Date: 2026-07-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "030_agent_execution_durable_core"
down_revision: str | None = "029_agent_execution_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agent_runtime_binding_owner",
        "agent_runtime_session_bindings",
        ["tenant_id", "id", "conversation_id", "runtime_profile_id"],
        schema="metaedu",
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("queue_seq", sa.BigInteger(), nullable=False),
        sa.Column("root_input_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_definition_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_binding_id", UUID(as_uuid=True), nullable=True),
        sa.Column("creation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("status_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("next_event_seq", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "first_available_event_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("last_event_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "event_log_complete", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_code", sa.String(100), nullable=True),
        sa.Column("terminal_reason", sa.String(500), nullable=True),
        sa.Column("terminal_result_digest", sa.String(64), nullable=True),
        sa.Column("terminal_output_ref", sa.String(500), nullable=True),
        sa.Column("terminal_output_digest", sa.String(64), nullable=True),
        sa.Column("terminal_output_size", sa.BigInteger(), nullable=True),
        sa.Column("terminal_output_media_type", sa.String(100), nullable=True),
        sa.Column("terminal_output_classification", sa.String(16), nullable=True),
        sa.Column("terminal_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "output_publish_state",
            sa.String(20),
            nullable=False,
            server_default="not_required",
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_capability_snapshot", JSONB(), nullable=False),
        sa.Column("run_config_snapshot", JSONB(), nullable=False),
        sa.Column("context_snapshot_ref", sa.String(500), nullable=True),
        sa.Column("context_snapshot_digest", sa.String(64), nullable=True),
        sa.Column("context_snapshot_classification", sa.String(16), nullable=True),
        sa.Column("budget_snapshot", JSONB(), nullable=False),
        sa.Column("usage_summary", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_run_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            name="uq_agent_run_tenant_conversation_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            "correlation_id",
            name="uq_agent_run_event_owner",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "conversation_id",
            "runtime_profile_id",
            "runtime_binding_id",
            name="uq_agent_run_runtime_owner",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "queue_seq",
            name="uq_agent_run_queue_seq",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_definition_version_id"],
            [
                "metaedu.agent_definition_versions.tenant_id",
                "metaedu.agent_definition_versions.id",
            ],
            name="fk_agent_run_definition",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_run_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "runtime_binding_id"],
            [
                "metaedu.agent_runtime_session_bindings.tenant_id",
                "metaedu.agent_runtime_session_bindings.id",
            ],
            name="fk_agent_run_binding",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_run_parent",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'starting', 'running', 'waiting_input', "
            "'waiting_approval', 'resume_required', 'cancelling', 'completed', "
            "'failed', 'cancelled', 'expired')",
            name="ck_agent_run_status",
        ),
        sa.CheckConstraint(
            "output_publish_state IN ('not_required', 'pending', 'published', "
            "'dead_letter', 'suppressed')",
            name="ck_agent_run_output_publish_state",
        ),
        sa.CheckConstraint(
            "queue_seq >= 1 AND status_revision >= 1 AND next_event_seq >= 1 "
            "AND first_available_event_seq >= 1 AND last_event_seq >= 0 "
            "AND next_event_seq = last_event_seq + 1 "
            "AND first_available_event_seq <= next_event_seq",
            name="ck_agent_run_sequences",
        ),
        sa.CheckConstraint(
            "char_length(creation_digest) = 64", name="ck_agent_run_creation_digest"
        ),
        sa.CheckConstraint(
            "(context_snapshot_ref IS NULL AND context_snapshot_digest IS NULL "
            "AND context_snapshot_classification IS NULL) OR "
            "(context_snapshot_ref IS NOT NULL AND "
            "char_length(context_snapshot_digest) = 64 AND "
            "context_snapshot_classification IN ('public', 'internal', 'restricted'))",
            name="ck_agent_run_context_snapshot",
        ),
        sa.CheckConstraint(
            "pg_column_size(runtime_capability_snapshot) <= 32768 AND "
            "pg_column_size(run_config_snapshot) <= 32768 AND "
            "pg_column_size(budget_snapshot) <= 32768 AND "
            "pg_column_size(usage_summary) <= 32768",
            name="ck_agent_run_snapshot_size",
        ),
        sa.CheckConstraint(
            "(status NOT IN ('completed', 'failed', 'cancelled', 'expired') "
            "AND ended_at IS NULL AND terminal_result_digest IS NULL "
            "AND terminal_code IS NULL AND terminal_reason IS NULL) OR "
            "(status IN ('completed', 'failed', 'cancelled', 'expired') "
            "AND ended_at IS NOT NULL AND char_length(terminal_result_digest) = 64 "
            "AND terminal_code IS NOT NULL AND terminal_reason IS NOT NULL)",
            name="ck_agent_run_terminal_envelope",
        ),
        sa.CheckConstraint(
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
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_run_one_active",
        "agent_runs",
        ["tenant_id", "conversation_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text(
            "status IN ('starting', 'running', 'waiting_input', "
            "'waiting_approval', 'resume_required', 'cancelling')"
        ),
    )
    op.create_index(
        "ix_agent_run_queue",
        "agent_runs",
        ["tenant_id", "conversation_id", "queue_seq", "status"],
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_run_recovery",
        "agent_runs",
        ["tenant_id", "status", "updated_at", "id"],
        schema="metaedu",
    )

    op.create_table(
        "agent_turn_inputs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("input_kind", sa.String(24), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("expected_runtime_epoch", sa.BigInteger(), nullable=True),
        sa.Column("context_digest", sa.String(64), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "ordinal", name="uq_agent_turn_input_ordinal"
        ),
        sa.UniqueConstraint(
            "tenant_id", "request_id", name="uq_agent_turn_input_request"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_turn_input_run",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_agent_turn_input_ordinal"),
        sa.CheckConstraint(
            "input_kind IN ('root', 'steer', 'human_response')",
            name="ck_agent_turn_input_kind",
        ),
        sa.CheckConstraint(
            "(input_kind = 'root' AND ordinal = 0 AND expected_runtime_epoch IS NULL) "
            "OR (input_kind IN ('steer', 'human_response') AND ordinal >= 1 "
            "AND expected_runtime_epoch >= 1)",
            name="ck_agent_turn_input_envelope",
        ),
        sa.CheckConstraint(
            "char_length(context_digest) = 64",
            name="ck_agent_turn_input_context_digest",
        ),
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_turn_input_root",
        "agent_turn_inputs",
        ["tenant_id", "run_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("input_kind = 'root'"),
    )

    op.create_table(
        "agent_run_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("payload_inline", JSONB(), nullable=True),
        sa.Column("payload_ref", sa.String(500), nullable=True),
        sa.Column("payload_state", sa.String(16), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("payload_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_profile_id", UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_binding_id", UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_epoch", sa.BigInteger(), nullable=True),
        sa.Column("runtime_seq", sa.BigInteger(), nullable=True),
        sa.Column("runtime_event_id", UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_event_digest", sa.String(64), nullable=True),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_agent_run_event_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "seq", name="uq_agent_run_event_seq"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["metaedu.agent_runs.tenant_id", "metaedu.agent_runs.id"],
            name="fk_agent_run_event_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "conversation_id"],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
            ],
            name="fk_agent_run_event_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "conversation_id", "correlation_id"],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
                "metaedu.agent_runs.correlation_id",
            ],
            name="fk_agent_run_event_owner",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_run_event_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "runtime_binding_id"],
            [
                "metaedu.agent_runtime_session_bindings.tenant_id",
                "metaedu.agent_runtime_session_bindings.id",
            ],
            name="fk_agent_run_event_binding",
        ),
        sa.CheckConstraint("seq >= 1", name="ck_agent_run_event_seq"),
        sa.CheckConstraint("schema_version >= 1", name="ck_agent_run_event_schema"),
        sa.CheckConstraint(
            "visibility IN ('user', 'tenant_admin', 'internal')",
            name="ck_agent_run_event_visibility",
        ),
        sa.CheckConstraint(
            "classification IN ('public', 'internal', 'restricted')",
            name="ck_agent_run_event_classification",
        ),
        sa.CheckConstraint(
            "payload_state IN ('inline', 'external', 'redacted', 'expired', 'archived')",
            name="ck_agent_run_event_payload_state",
        ),
        sa.CheckConstraint(
            "char_length(payload_digest) = 64 AND payload_size >= 0",
            name="ck_agent_run_event_payload_digest",
        ),
        sa.CheckConstraint(
            "char_length(btrim(media_type)) > 2 "
            "AND media_type = btrim(media_type) "
            "AND position('/' IN media_type) > 1 "
            "AND position('/' IN media_type) < char_length(media_type)",
            name="ck_agent_run_event_media_type",
        ),
        sa.CheckConstraint(
            "(payload_state = 'inline' AND payload_inline IS NOT NULL "
            "AND payload_ref IS NULL AND classification <> 'restricted' "
            "AND payload_size <= 32768 AND pg_column_size(payload_inline) <= 32768) "
            "OR (payload_state = 'external' AND payload_inline IS NULL "
            "AND payload_ref IS NOT NULL) "
            "OR (payload_state IN ('redacted', 'expired', 'archived') "
            "AND payload_inline IS NULL)",
            name="ck_agent_run_event_payload",
        ),
        sa.CheckConstraint(
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
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_run_event_runtime_seq",
        "agent_run_events",
        ["tenant_id", "runtime_binding_id", "runtime_epoch", "runtime_seq"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("runtime_binding_id IS NOT NULL"),
    )
    op.create_index(
        "uq_agent_run_event_runtime_id",
        "agent_run_events",
        ["tenant_id", "runtime_binding_id", "runtime_epoch", "runtime_event_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("runtime_binding_id IS NOT NULL"),
    )
    op.create_index(
        "uq_agent_run_event_terminal",
        "agent_run_events",
        ["tenant_id", "run_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text(
            "event_type IN ('run.completed', 'run.failed', "
            "'run.cancelled', 'run.expired')"
        ),
    )
    op.create_index(
        "ix_agent_run_event_replay",
        "agent_run_events",
        ["tenant_id", "run_id", "seq"],
        schema="metaedu",
    )

    _create_execution_outbox()
    _create_execution_inbox()

    op.execute(
        """
        CREATE FUNCTION metaedu.guard_agent_run_event_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'agent_run_events is append-only in E1'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_run_event_append_only
        BEFORE UPDATE OR DELETE ON metaedu.agent_run_events
        FOR EACH ROW EXECUTE FUNCTION metaedu.guard_agent_run_event_append_only()
        """
    )


def _create_execution_outbox() -> None:
    op.create_table(
        "agent_execution_outbox",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(60), nullable=False),
        sa.Column("payload_ref", sa.String(500), nullable=True),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'published', 'dead_letter', 'cancelled')",
            name="ck_agent_exec_outbox_status",
        ),
        sa.CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_exec_outbox_digest",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_exec_outbox_dispatch",
        "agent_execution_outbox",
        ["tenant_id", "status", "next_attempt_at", "created_at"],
        schema="metaedu",
    )


def _create_execution_inbox() -> None:
    op.create_table(
        "agent_execution_inbox",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_name", sa.String(100), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "consumer_name",
            "event_id",
            name="uq_agent_exec_inbox_event",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'consumed', 'rejected')",
            name="ck_agent_exec_inbox_status",
        ),
        sa.CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_exec_inbox_digest",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_exec_inbox_status",
        "agent_execution_inbox",
        ["tenant_id", "status", "created_at"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_agent_run_event_append_only "
        "ON metaedu.agent_run_events"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS metaedu.guard_agent_run_event_append_only()"
    )
    op.drop_index(
        "ix_agent_exec_inbox_status",
        table_name="agent_execution_inbox",
        schema="metaedu",
    )
    op.drop_table("agent_execution_inbox", schema="metaedu")
    op.drop_index(
        "ix_agent_exec_outbox_dispatch",
        table_name="agent_execution_outbox",
        schema="metaedu",
    )
    op.drop_table("agent_execution_outbox", schema="metaedu")
    op.drop_index(
        "ix_agent_run_event_replay",
        table_name="agent_run_events",
        schema="metaedu",
    )
    op.drop_index(
        "uq_agent_run_event_terminal",
        table_name="agent_run_events",
        schema="metaedu",
    )
    op.drop_index(
        "uq_agent_run_event_runtime_id",
        table_name="agent_run_events",
        schema="metaedu",
    )
    op.drop_index(
        "uq_agent_run_event_runtime_seq",
        table_name="agent_run_events",
        schema="metaedu",
    )
    op.drop_table("agent_run_events", schema="metaedu")
    op.drop_index(
        "uq_agent_turn_input_root",
        table_name="agent_turn_inputs",
        schema="metaedu",
    )
    op.drop_table("agent_turn_inputs", schema="metaedu")
    op.drop_index(
        "ix_agent_run_recovery", table_name="agent_runs", schema="metaedu"
    )
    op.drop_index("ix_agent_run_queue", table_name="agent_runs", schema="metaedu")
    op.drop_index(
        "uq_agent_run_one_active", table_name="agent_runs", schema="metaedu"
    )
    op.drop_table("agent_runs", schema="metaedu")
    op.execute(
        "ALTER TABLE metaedu.agent_runtime_session_bindings "
        "DROP CONSTRAINT IF EXISTS uq_agent_runtime_binding_owner"
    )
