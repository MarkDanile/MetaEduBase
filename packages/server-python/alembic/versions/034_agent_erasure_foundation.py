"""R1-S1 erasure fence / hold / purge schema foundation (expand-only).

Revision ID: 034_agent_erasure_foundation
Revises: 033_agent_compat_output
Create Date: 2026-07-28

本迁移只做 expand：新增四张 coordination 表（ErasureFence、PurgeOperation、
PurgeOwnerCheckpoint、ConversationLegalHold）、Conversation.hold_revision、
Message.body_state、CompatibilityOutput.payload_state，并放宽 tombstone
表达所需的 CHECK。它不执行任何全表 backfill；既有 Conversation 的
baseline fence 由独立、可恢复、分批、tenant 限流的 backfill 命令补齐。

正常未擦除写路径的强约束不因 expand 放宽而削弱：
- completed Run 未 suppress 时仍强制完整 terminal output envelope；
- CompatibilityOutput ``payload_state='present'`` 仍要求正文非空；
- outbox 非 cancelled 状态仍要求恰好一个 payload 来源。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "034_agent_erasure_foundation"
down_revision: str | None = "033_agent_compat_output"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Conversation: hold_revision + actor tombstone ----------------------
    op.add_column(
        "agent_conversations",
        sa.Column(
            "hold_revision",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_conv_hold_revision",
        "agent_conversations",
        "hold_revision >= 0",
        schema="metaedu",
    )
    # actor tombstone：redacted 可清 created_by，保留不可逆 creator_identity_digest。
    op.add_column(
        "agent_conversations",
        sa.Column(
            "actor_state",
            sa.String(16),
            nullable=False,
            server_default="present",
        ),
        schema="metaedu",
    )
    op.add_column(
        "agent_conversations",
        sa.Column(
            "creator_identity_digest",
            sa.String(64),
            nullable=True,
        ),
        schema="metaedu",
    )
    op.alter_column(
        "agent_conversations",
        "created_by",
        existing_type=UUID(as_uuid=True),
        nullable=True,
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_conv_actor",
        "agent_conversations",
        "(actor_state = 'present' AND created_by IS NOT NULL "
        "AND creator_identity_digest IS NULL) OR "
        "(actor_state = 'redacted' AND created_by IS NULL "
        "AND creator_identity_digest IS NOT NULL "
        "AND char_length(creator_identity_digest) = 64)",
        schema="metaedu",
    )

    # --- Message: body_state + actor tombstone ------------------------------
    op.add_column(
        "agent_messages",
        sa.Column(
            "body_state",
            sa.String(16),
            nullable=False,
            server_default="present",
        ),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_msg_body_state",
        "agent_messages",
        "body_state IN ('present', 'redacted') AND "
        "(body_state <> 'redacted' OR content_state = 'redacted')",
        schema="metaedu",
    )
    # actor tombstone：不可逆 actor identity digest；redacted 时清除 author_id。
    op.add_column(
        "agent_messages",
        sa.Column(
            "actor_identity_digest",
            sa.String(64),
            nullable=True,
        ),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_msg_actor_digest",
        "agent_messages",
        "actor_identity_digest IS NULL OR "
        "char_length(actor_identity_digest) = 64",
        schema="metaedu",
    )
    # 重做 envelope CHECK：user_input present 仍强制 author_id 非空；redacted
    # tombstone 允许 author_id NULL 但要求 actor_identity_digest 保留。其余
    # message_kind 分支保持原样（不弱化正常写路径）。
    op.drop_constraint(
        "ck_agent_msg_envelope",
        "agent_messages",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_msg_envelope",
        "agent_messages",
        "(message_kind = 'user_input' AND author_type = 'user' "
        "AND body_state <> 'redacted' AND author_id IS NOT NULL AND "
        "client_message_id IS NOT NULL AND requested_run_id IS NOT NULL AND "
        "requested_run_queue_seq IS NOT NULL AND turn_request_digest IS NOT NULL "
        "AND turn_dispatch_state IS NOT NULL AND origin_run_id IS NULL "
        "AND output_ordinal IS NULL) OR "
        "(message_kind = 'user_input' AND author_type = 'user' "
        "AND body_state = 'redacted' AND author_id IS NULL "
        "AND actor_identity_digest IS NOT NULL "
        "AND char_length(actor_identity_digest) = 64 "
        "AND client_message_id IS NOT NULL AND requested_run_id IS NOT NULL AND "
        "requested_run_queue_seq IS NOT NULL AND turn_request_digest IS NOT NULL "
        "AND turn_dispatch_state IS NOT NULL AND origin_run_id IS NULL "
        "AND output_ordinal IS NULL) OR "
        "(message_kind = 'assistant_output' AND author_type = 'agent' "
        "AND client_message_id IS NULL AND requested_run_id IS NULL "
        "AND requested_run_queue_seq IS NULL AND turn_request_digest IS NULL "
        "AND turn_dispatch_state IS NULL AND origin_run_id IS NOT NULL "
        "AND output_ordinal >= 0) OR "
        "(message_kind = 'system_notice' AND author_type = 'system' "
        "AND client_message_id IS NULL AND requested_run_id IS NULL "
        "AND requested_run_queue_seq IS NULL AND turn_request_digest IS NULL "
        "AND turn_dispatch_state IS NULL AND origin_run_id IS NULL "
        "AND output_ordinal IS NULL)",
        schema="metaedu",
    )

    # --- AgentRun terminal output tombstone（重做 CHECK，expand-only）------
    op.drop_constraint(
        "ck_agent_run_terminal_output",
        "agent_runs",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_run_terminal_output",
        "agent_runs",
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
        "(status = 'completed' AND output_publish_state = 'suppressed' "
        "AND terminal_output_ref IS NULL "
        "AND char_length(terminal_output_digest) = 64 "
        "AND terminal_output_size >= 0 "
        "AND terminal_output_media_type IS NULL "
        "AND terminal_output_classification IS NULL "
        "AND terminal_message_id IS NULL) OR "
        "(status <> 'completed' AND terminal_output_ref IS NULL "
        "AND terminal_output_digest IS NULL AND terminal_output_size IS NULL "
        "AND terminal_output_media_type IS NULL "
        "AND terminal_output_classification IS NULL "
        "AND terminal_message_id IS NULL "
        "AND output_publish_state = 'not_required')",
        schema="metaedu",
    )

    # --- CompatibilityOutput payload tombstone -----------------------------
    op.alter_column(
        "agent_compatibility_outputs",
        "reply_text",
        existing_type=sa.Text(),
        nullable=True,
        schema="metaedu",
    )
    op.alter_column(
        "agent_compatibility_outputs",
        "response_envelope",
        existing_type=JSONB,
        nullable=True,
        schema="metaedu",
    )
    op.add_column(
        "agent_compatibility_outputs",
        sa.Column(
            "payload_state",
            sa.String(16),
            nullable=False,
            server_default="present",
        ),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_compat_output_payload_state",
        "agent_compatibility_outputs",
        "payload_state IN ('present', 'redacted')",
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_compat_output_payload",
        "agent_compatibility_outputs",
        "(payload_state = 'present' AND reply_text IS NOT NULL "
        "AND response_envelope IS NOT NULL) OR "
        "(payload_state = 'redacted' AND reply_text IS NULL "
        "AND response_envelope IS NULL)",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_compat_output_envelope_size",
        "agent_compatibility_outputs",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_compat_output_envelope_size",
        "agent_compatibility_outputs",
        "response_envelope IS NULL OR "
        "(jsonb_typeof(response_envelope) = 'object' "
        "AND pg_column_size(response_envelope) <= 262144)",
        schema="metaedu",
    )

    # --- Outbox payload tombstone（两侧，重做 CHECK）-----------------------
    # 新增 ``suppressed`` 状态作为 R1-S1 tombstone：清正文 ref/inline，保留
    # digest。正常 ``cancelled`` 保持原有“保留 payload”语义，不受影响。
    op.drop_constraint(
        "ck_agent_ws_outbox_status",
        "agent_workspace_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_ws_outbox_status",
        "agent_workspace_outbox",
        "status IN ('pending', 'claimed', 'published', 'dead_letter', "
        "'cancelled', 'suppressed')",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_ws_outbox_payload",
        "agent_workspace_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_ws_outbox_payload",
        "agent_workspace_outbox",
        "(status = 'suppressed' AND payload_inline IS NULL "
        "AND payload_ref IS NULL) OR "
        "(status <> 'suppressed' AND "
        "((payload_inline IS NOT NULL AND payload_ref IS NULL "
        "AND pg_column_size(payload_inline) <= 32768) OR "
        "(payload_inline IS NULL AND payload_ref IS NOT NULL)))",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_exec_outbox_status",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_exec_outbox_status",
        "agent_execution_outbox",
        "status IN ('pending', 'claimed', 'published', 'dead_letter', "
        "'cancelled', 'suppressed')",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_exec_outbox_payload",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_exec_outbox_payload",
        "agent_execution_outbox",
        "(status = 'suppressed' AND payload_inline IS NULL "
        "AND payload_ref IS NULL) OR "
        "(status <> 'suppressed' AND "
        "((payload_inline IS NOT NULL AND payload_ref IS NULL "
        "AND pg_column_size(payload_inline) <= 32768) OR "
        "(payload_inline IS NULL AND payload_ref IS NOT NULL)))",
        schema="metaedu",
    )

    # --- Coordination tables ------------------------------------------------
    op.create_table(
        "agent_erasure_fences",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_key", sa.String(100), nullable=False),
        sa.Column("owner_version", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "purge_revision", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "hold_revision", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("ingress_checkpoint", JSONB, nullable=False, server_default="{}"),
        sa.Column("ingress_digest", sa.String(64), nullable=False),
        sa.Column("last_body_write_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_digest", sa.String(64), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint(
            "tenant_id", "conversation_id", "owner_key", name="pk_agent_erasure_fences"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "owner_key",
            name="uq_agent_erasure_fence_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["metaedu.agent_conversations.tenant_id", "metaedu.agent_conversations.id"],
            name="fk_agent_erasure_fence_conversation",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'erasing', 'erased', 'blocked')",
            name="ck_agent_erasure_fence_state",
        ),
        sa.CheckConstraint(
            "owner_version >= 1 AND purge_revision >= 0 AND hold_revision >= 0 "
            "AND revision >= 1",
            name="ck_agent_erasure_fence_revisions",
        ),
        sa.CheckConstraint(
            "char_length(ingress_digest) = 64",
            name="ck_agent_erasure_fence_ingress_digest",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(ingress_checkpoint) = 'object' "
            "AND pg_column_size(ingress_checkpoint) <= 16384",
            name="ck_agent_erasure_fence_ingress_checkpoint",
        ),
        sa.CheckConstraint(
            "(state = 'erased' AND ack_digest IS NOT NULL "
            "AND char_length(ack_digest) = 64 AND acked_at IS NOT NULL) OR "
            "(state <> 'erased' AND ack_digest IS NULL AND acked_at IS NULL)",
            name="ck_agent_erasure_fence_ack",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_erasure_fence_conversation",
        "agent_erasure_fences",
        ["tenant_id", "conversation_id"],
        schema="metaedu",
    )

    op.create_table(
        "agent_conversation_purges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("purge_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("registry_digest", sa.String(64), nullable=False),
        sa.Column(
            "registry_snapshot",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "retention_policy_snapshot",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("retention_policy_digest", sa.String(64), nullable=False),
        sa.Column(
            "hold_revision_snapshot",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("lease_epoch", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_purge_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "purge_revision",
            name="uq_agent_purge_revision",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["metaedu.agent_conversations.tenant_id", "metaedu.agent_conversations.id"],
            name="fk_agent_purge_conversation",
        ),
        sa.CheckConstraint(
            "state IN ('scheduled', 'running', 'blocked', 'failed', "
            "'completed', 'cancelled')",
            name="ck_agent_purge_state",
        ),
        sa.CheckConstraint(
            "purge_revision >= 1 AND lease_epoch >= 0 AND revision >= 1 "
            "AND hold_revision_snapshot >= 0",
            name="ck_agent_purge_revisions",
        ),
        sa.CheckConstraint(
            "char_length(registry_digest) = 64 "
            "AND char_length(retention_policy_digest) = 64",
            name="ck_agent_purge_digests",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(registry_snapshot) = 'array' "
            "AND pg_column_size(registry_snapshot) <= 65536",
            name="ck_agent_purge_registry_snapshot",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(retention_policy_snapshot) = 'object' "
            "AND pg_column_size(retention_policy_snapshot) <= 16384",
            name="ck_agent_purge_retention_snapshot",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_purge_schedule",
        "agent_conversation_purges",
        ["tenant_id", "state", "scheduled_at"],
        schema="metaedu",
    )

    op.create_table(
        "agent_conversation_purge_owners",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("purge_operation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_key", sa.String(100), nullable=False),
        sa.Column("owner_version", sa.Integer(), nullable=False),
        sa.Column("capability_digest", sa.String(64), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_digest", sa.String(64), nullable=True),
        sa.Column("ack_digest", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(100), nullable=True),
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
        sa.UniqueConstraint(
            "tenant_id",
            "purge_operation_id",
            "owner_key",
            name="uq_agent_purge_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purge_operation_id"],
            [
                "metaedu.agent_conversation_purges.tenant_id",
                "metaedu.agent_conversation_purges.id",
            ],
            name="fk_agent_purge_owner_operation",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'erasing', 'blocked', 'failed', 'acked')",
            name="ck_agent_purge_owner_state",
        ),
        sa.CheckConstraint("attempt >= 0", name="ck_agent_purge_owner_attempt"),
        sa.CheckConstraint(
            "owner_version >= 1", name="ck_agent_purge_owner_version"
        ),
        sa.CheckConstraint(
            "char_length(capability_digest) = 64",
            name="ck_agent_purge_owner_capability_digest",
        ),
        sa.CheckConstraint(
            "checkpoint_digest IS NULL OR char_length(checkpoint_digest) = 64",
            name="ck_agent_purge_owner_checkpoint_digest",
        ),
        sa.CheckConstraint(
            "(state = 'acked' AND ack_digest IS NOT NULL "
            "AND char_length(ack_digest) = 64) OR "
            "(state <> 'acked' AND ack_digest IS NULL)",
            name="ck_agent_purge_owner_ack",
        ),
        schema="metaedu",
    )

    op.create_table(
        "agent_conversation_legal_holds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
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
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["metaedu.agent_conversations.tenant_id", "metaedu.agent_conversations.id"],
            name="fk_agent_legal_hold_conversation",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'expired', 'released')",
            name="ck_agent_legal_hold_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_agent_legal_hold_revision"),
        sa.CheckConstraint(
            "char_length(btrim(reason_code)) > 0 AND reason_code = btrim(reason_code) "
            "AND char_length(reason_code) <= 100",
            name="ck_agent_legal_hold_reason",
        ),
        sa.CheckConstraint(
            "(state = 'released' AND released_at IS NOT NULL "
            "AND released_by IS NOT NULL) OR "
            "(state <> 'released' AND released_at IS NULL AND released_by IS NULL)",
            name="ck_agent_legal_hold_release",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_legal_hold_conversation",
        "agent_conversation_legal_holds",
        ["tenant_id", "conversation_id", "state"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_legal_hold_conversation",
        table_name="agent_conversation_legal_holds",
        schema="metaedu",
    )
    op.drop_table("agent_conversation_legal_holds", schema="metaedu")
    op.drop_table("agent_conversation_purge_owners", schema="metaedu")
    op.drop_index(
        "ix_agent_purge_schedule",
        table_name="agent_conversation_purges",
        schema="metaedu",
    )
    op.drop_table("agent_conversation_purges", schema="metaedu")
    op.drop_index(
        "ix_agent_erasure_fence_conversation",
        table_name="agent_erasure_fences",
        schema="metaedu",
    )
    op.drop_table("agent_erasure_fences", schema="metaedu")

    # Outbox CHECK 还原为“恰好一个 payload 来源”，status 还原为不含 suppressed。
    op.drop_constraint(
        "ck_agent_exec_outbox_payload",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_exec_outbox_payload",
        "agent_execution_outbox",
        "(payload_inline IS NOT NULL AND payload_ref IS NULL "
        "AND pg_column_size(payload_inline) <= 32768) OR "
        "(payload_inline IS NULL AND payload_ref IS NOT NULL)",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_exec_outbox_status",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_exec_outbox_status",
        "agent_execution_outbox",
        "status IN ('pending', 'claimed', 'published', 'dead_letter', 'cancelled')",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_ws_outbox_payload",
        "agent_workspace_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_ws_outbox_payload",
        "agent_workspace_outbox",
        "(payload_inline IS NOT NULL AND payload_ref IS NULL "
        "AND pg_column_size(payload_inline) <= 32768) OR "
        "(payload_inline IS NULL AND payload_ref IS NOT NULL)",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_ws_outbox_status",
        "agent_workspace_outbox",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_ws_outbox_status",
        "agent_workspace_outbox",
        "status IN ('pending', 'claimed', 'published', 'dead_letter', 'cancelled')",
        schema="metaedu",
    )

    # CompatibilityOutput 还原。
    op.drop_constraint(
        "ck_agent_compat_output_envelope_size",
        "agent_compatibility_outputs",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_compat_output_envelope_size",
        "agent_compatibility_outputs",
        "jsonb_typeof(response_envelope) = 'object' "
        "AND pg_column_size(response_envelope) <= 262144",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_compat_output_payload",
        "agent_compatibility_outputs",
        schema="metaedu",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_compat_output_payload_state",
        "agent_compatibility_outputs",
        schema="metaedu",
        type_="check",
    )
    op.drop_column(
        "agent_compatibility_outputs", "payload_state", schema="metaedu"
    )
    op.alter_column(
        "agent_compatibility_outputs",
        "response_envelope",
        existing_type=JSONB,
        nullable=False,
        schema="metaedu",
    )
    op.alter_column(
        "agent_compatibility_outputs",
        "reply_text",
        existing_type=sa.Text(),
        nullable=False,
        schema="metaedu",
    )

    # AgentRun terminal output CHECK 还原。
    op.drop_constraint(
        "ck_agent_run_terminal_output",
        "agent_runs",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_run_terminal_output",
        "agent_runs",
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
        schema="metaedu",
    )

    # Message / Conversation 还原。
    op.drop_constraint(
        "ck_agent_msg_envelope",
        "agent_messages",
        schema="metaedu",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_msg_envelope",
        "agent_messages",
        "(message_kind = 'user_input' AND author_type = 'user' "
        "AND author_id IS NOT NULL AND "
        "client_message_id IS NOT NULL AND requested_run_id IS NOT NULL AND "
        "requested_run_queue_seq IS NOT NULL AND turn_request_digest IS NOT NULL "
        "AND turn_dispatch_state IS NOT NULL AND origin_run_id IS NULL "
        "AND output_ordinal IS NULL) OR "
        "(message_kind = 'assistant_output' AND author_type = 'agent' "
        "AND client_message_id IS NULL AND requested_run_id IS NULL "
        "AND requested_run_queue_seq IS NULL AND turn_request_digest IS NULL "
        "AND turn_dispatch_state IS NULL AND origin_run_id IS NOT NULL "
        "AND output_ordinal >= 0) OR "
        "(message_kind = 'system_notice' AND author_type = 'system' "
        "AND client_message_id IS NULL AND requested_run_id IS NULL "
        "AND requested_run_queue_seq IS NULL AND turn_request_digest IS NULL "
        "AND turn_dispatch_state IS NULL AND origin_run_id IS NULL "
        "AND output_ordinal IS NULL)",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_msg_actor_digest",
        "agent_messages",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_messages", "actor_identity_digest", schema="metaedu")
    op.drop_constraint(
        "ck_agent_msg_body_state",
        "agent_messages",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_messages", "body_state", schema="metaedu")

    # Conversation actor tombstone / hold_revision 还原。
    op.drop_constraint(
        "ck_agent_conv_actor",
        "agent_conversations",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_conversations", "creator_identity_digest", schema="metaedu")
    op.drop_column("agent_conversations", "actor_state", schema="metaedu")
    op.alter_column(
        "agent_conversations",
        "created_by",
        existing_type=UUID(as_uuid=True),
        nullable=False,
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_conv_hold_revision",
        "agent_conversations",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_conversations", "hold_revision", schema="metaedu")
