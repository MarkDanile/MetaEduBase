"""create the REQ-041 Agent Workspace durable store

Revision ID: 028_agent_workspace_store
Revises: 027_tenant_config_audit
Create Date: 2026-07-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "028_agent_workspace_store"
down_revision: str | None = "027_tenant_config_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("creation_digest", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "title_source", sa.String(10), nullable=False, server_default="none"
        ),
        sa.Column("state", sa.String(12), nullable=False, server_default="active"),
        sa.Column("parent_conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("forked_from_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "next_message_seq", sa.BigInteger(), nullable=False, server_default="1"
        ),
        sa.Column(
            "next_run_queue_seq", sa.BigInteger(), nullable=False, server_default="1"
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "purge_state",
            sa.String(20),
            nullable=False,
            server_default="not_scheduled",
        ),
        sa.Column(
            "purge_revision", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_conv_tenant_id"),
        sa.CheckConstraint(
            "title_source IN ('none', 'auto', 'user')",
            name="ck_agent_conv_title_source",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'archived', 'deleted')",
            name="ck_agent_conv_state",
        ),
        sa.CheckConstraint(
            "purge_state IN ('not_scheduled', 'scheduled', 'running', "
            "'blocked', 'failed', 'completed')",
            name="ck_agent_conv_purge_state",
        ),
        sa.CheckConstraint(
            "next_message_seq >= 1 AND next_run_queue_seq >= 1",
            name="ck_agent_conv_next_seq",
        ),
        sa.CheckConstraint(
            "char_length(creation_digest) = 64",
            name="ck_agent_conv_creation_digest",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_agent_conv_revision"),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_conv_owner_state_activity",
        "agent_conversations",
        ["tenant_id", "created_by", "state", "last_activity_at", "id"],
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_conv_deleted",
        "agent_conversations",
        ["tenant_id", "deleted_at"],
        unique=False,
        schema="metaedu",
        postgresql_where=sa.text("state = 'deleted'"),
    )

    op.create_table(
        "agent_conversation_user_state",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_read_message_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_conv_state_conversation",
        ),
        sa.CheckConstraint(
            "last_read_message_seq >= 0", name="ck_agent_conv_state_last_read"
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_conv_user_pin",
        "agent_conversation_user_state",
        ["tenant_id", "user_id", "pinned_at"],
        schema="metaedu",
    )

    op.create_table(
        "agent_messages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("message_kind", sa.String(24), nullable=False),
        sa.Column("author_type", sa.String(12), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), nullable=True),
        sa.Column("client_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("requested_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("requested_run_queue_seq", sa.BigInteger(), nullable=True),
        sa.Column("turn_request_digest", sa.String(64), nullable=True),
        sa.Column("turn_dispatch_state", sa.String(20), nullable=True),
        sa.Column("turn_dispatch_error_code", sa.String(100), nullable=True),
        sa.Column(
            "turn_dispatch_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("origin_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("output_ordinal", sa.Integer(), nullable=True),
        sa.Column("reply_to_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "content_state", sa.String(16), nullable=False, server_default="visible"
        ),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redacted_reason", sa.String(200), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_msg_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "conversation_id", "seq", name="uq_agent_msg_seq"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_msg_conversation",
        ),
        sa.CheckConstraint(
            "message_kind IN ('user_input', 'assistant_output', 'system_notice')",
            name="ck_agent_msg_kind",
        ),
        sa.CheckConstraint(
            "author_type IN ('user', 'agent', 'system')",
            name="ck_agent_msg_author_type",
        ),
        sa.CheckConstraint(
            "turn_dispatch_state IS NULL OR turn_dispatch_state IN "
            "('pending', 'accepted', 'dead_letter', 'abandoned')",
            name="ck_agent_msg_dispatch_state",
        ),
        sa.CheckConstraint(
            "content_state IN ('visible', 'redacted', 'superseded')",
            name="ck_agent_msg_content_state",
        ),
        sa.CheckConstraint("seq >= 1", name="ck_agent_msg_seq_positive"),
        sa.CheckConstraint(
            "requested_run_queue_seq IS NULL OR requested_run_queue_seq >= 1",
            name="ck_agent_msg_queue_seq_positive",
        ),
        sa.CheckConstraint(
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
            name="ck_agent_msg_envelope",
        ),
        sa.CheckConstraint(
            "char_length(content_digest) = 64 AND "
            "(turn_request_digest IS NULL OR char_length(turn_request_digest) = 64)",
            name="ck_agent_msg_digest_length",
        ),
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_msg_client",
        "agent_messages",
        ["tenant_id", "conversation_id", "author_id", "client_message_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text(
            "client_message_id IS NOT NULL AND message_kind = 'user_input'"
        ),
    )
    op.create_index(
        "uq_agent_msg_run_queue",
        "agent_messages",
        ["tenant_id", "conversation_id", "requested_run_queue_seq"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("requested_run_queue_seq IS NOT NULL"),
    )
    op.create_index(
        "uq_agent_msg_origin",
        "agent_messages",
        ["tenant_id", "origin_run_id", "output_ordinal"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("origin_run_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_msg_history",
        "agent_messages",
        ["tenant_id", "conversation_id", "seq"],
        schema="metaedu",
    )

    op.create_table(
        "agent_message_parts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("part_seq", sa.Integer(), nullable=False),
        sa.Column("part_type", sa.String(16), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("content_format", sa.String(20), nullable=True),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("media_type", sa.String(100), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "classification", sa.String(16), nullable=False, server_default="internal"
        ),
        sa.UniqueConstraint(
            "tenant_id", "message_id", "part_seq", name="uq_agent_msg_part_seq"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["metaedu.agent_messages.tenant_id", "metaedu.agent_messages.id"],
            name="fk_agent_msg_part_message",
        ),
        sa.CheckConstraint("part_seq >= 1", name="ck_agent_msg_part_seq_positive"),
        sa.CheckConstraint(
            "part_type IN ('text', 'resource_ref')",
            name="ck_agent_msg_part_type",
        ),
        sa.CheckConstraint(
            "classification IN ('public', 'internal', 'restricted')",
            name="ck_agent_msg_part_classification",
        ),
        sa.CheckConstraint(
            "(part_type = 'text' AND text_content IS NOT NULL AND "
            "content_format IN ('plain_text', 'markdown') AND resource_id IS NULL) "
            "OR (part_type = 'resource_ref' AND resource_id IS NOT NULL AND "
            "text_content IS NULL AND content_format IS NULL)",
            name="ck_agent_msg_part_payload",
        ),
        sa.CheckConstraint(
            "char_length(digest) = 64", name="ck_agent_msg_part_digest_length"
        ),
        schema="metaedu",
    )

    op.create_table(
        "agent_workspace_outbox",
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
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
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
            name="ck_agent_ws_outbox_status",
        ),
        sa.CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_ws_outbox_digest_length",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_ws_outbox_dispatch",
        "agent_workspace_outbox",
        ["tenant_id", "status", "next_attempt_at", "created_at"],
        schema="metaedu",
    )

    op.create_table(
        "agent_workspace_inbox",
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
            "tenant_id", "consumer_name", "event_id", name="uq_agent_ws_inbox_event"
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'consumed', 'rejected')",
            name="ck_agent_ws_inbox_status",
        ),
        sa.CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_ws_inbox_digest_length",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_ws_inbox_status",
        "agent_workspace_inbox",
        ["tenant_id", "status", "created_at"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_ws_inbox_status",
        table_name="agent_workspace_inbox",
        schema="metaedu",
    )
    op.drop_table("agent_workspace_inbox", schema="metaedu")
    op.drop_index(
        "ix_agent_ws_outbox_dispatch",
        table_name="agent_workspace_outbox",
        schema="metaedu",
    )
    op.drop_table("agent_workspace_outbox", schema="metaedu")
    op.drop_table("agent_message_parts", schema="metaedu")
    op.drop_index(
        "ix_agent_msg_history", table_name="agent_messages", schema="metaedu"
    )
    op.drop_index(
        "uq_agent_msg_origin", table_name="agent_messages", schema="metaedu"
    )
    op.drop_index(
        "uq_agent_msg_run_queue", table_name="agent_messages", schema="metaedu"
    )
    op.drop_index(
        "uq_agent_msg_client", table_name="agent_messages", schema="metaedu"
    )
    op.drop_table("agent_messages", schema="metaedu")
    op.drop_index(
        "ix_agent_conv_user_pin",
        table_name="agent_conversation_user_state",
        schema="metaedu",
    )
    op.drop_table("agent_conversation_user_state", schema="metaedu")
    op.drop_index(
        "ix_agent_conv_deleted", table_name="agent_conversations", schema="metaedu"
    )
    op.drop_index(
        "ix_agent_conv_owner_state_activity",
        table_name="agent_conversations",
        schema="metaedu",
    )
    op.drop_table("agent_conversations", schema="metaedu")
