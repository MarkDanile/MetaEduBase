from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ConversationModel(Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_conv_tenant_id"),
        CheckConstraint(
            "title_source IN ('none', 'auto', 'user')",
            name="ck_agent_conv_title_source",
        ),
        CheckConstraint(
            "state IN ('active', 'archived', 'deleted')",
            name="ck_agent_conv_state",
        ),
        CheckConstraint(
            "purge_state IN ('not_scheduled', 'scheduled', 'running', "
            "'blocked', 'failed', 'completed')",
            name="ck_agent_conv_purge_state",
        ),
        CheckConstraint(
            "next_message_seq >= 1 AND next_run_queue_seq >= 1",
            name="ck_agent_conv_next_seq",
        ),
        CheckConstraint(
            "char_length(creation_digest) = 64",
            name="ck_agent_conv_creation_digest",
        ),
        CheckConstraint("revision >= 1", name="ck_agent_conv_revision"),
        Index(
            "ix_agent_conv_owner_state_activity",
            "tenant_id",
            "created_by",
            "state",
            "last_activity_at",
            "id",
        ),
        Index(
            "ix_agent_conv_deleted",
            "tenant_id",
            "deleted_at",
            postgresql_where=text("state = 'deleted'"),
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    creation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="none"
    )
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    parent_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    forked_from_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    next_message_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1
    )
    next_run_queue_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    purge_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purge_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_scheduled"
    )
    purge_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ConversationUserStateModel(Base):
    __tablename__ = "agent_conversation_user_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_conv_state_conversation",
        ),
        CheckConstraint(
            "last_read_message_seq >= 0", name="ck_agent_conv_state_last_read"
        ),
        Index(
            "ix_agent_conv_user_pin", "tenant_id", "user_id", "pinned_at"
        ),
        {"schema": "metaedu"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_read_message_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class MessageModel(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_msg_tenant_id"),
        UniqueConstraint(
            "tenant_id", "conversation_id", "seq", name="uq_agent_msg_seq"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_msg_conversation",
        ),
        CheckConstraint(
            "message_kind IN ('user_input', 'assistant_output', 'system_notice')",
            name="ck_agent_msg_kind",
        ),
        CheckConstraint(
            "author_type IN ('user', 'agent', 'system')",
            name="ck_agent_msg_author_type",
        ),
        CheckConstraint(
            "turn_dispatch_state IS NULL OR turn_dispatch_state IN "
            "('pending', 'accepted', 'dead_letter', 'abandoned')",
            name="ck_agent_msg_dispatch_state",
        ),
        CheckConstraint(
            "content_state IN ('visible', 'redacted', 'superseded')",
            name="ck_agent_msg_content_state",
        ),
        CheckConstraint("seq >= 1", name="ck_agent_msg_seq_positive"),
        CheckConstraint(
            "requested_run_queue_seq IS NULL OR requested_run_queue_seq >= 1",
            name="ck_agent_msg_queue_seq_positive",
        ),
        CheckConstraint(
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
        CheckConstraint(
            "char_length(content_digest) = 64 AND "
            "(turn_request_digest IS NULL OR char_length(turn_request_digest) = 64)",
            name="ck_agent_msg_digest_length",
        ),
        Index(
            "uq_agent_msg_client",
            "tenant_id",
            "conversation_id",
            "author_id",
            "client_message_id",
            unique=True,
            postgresql_where=text(
                "client_message_id IS NOT NULL AND message_kind = 'user_input'"
            ),
        ),
        Index(
            "uq_agent_msg_run_queue",
            "tenant_id",
            "conversation_id",
            "requested_run_queue_seq",
            unique=True,
            postgresql_where=text("requested_run_queue_seq IS NOT NULL"),
        ),
        Index(
            "uq_agent_msg_origin",
            "tenant_id",
            "origin_run_id",
            "output_ordinal",
            unique=True,
            postgresql_where=text("origin_run_id IS NOT NULL"),
        ),
        Index(
            "ix_agent_msg_history", "tenant_id", "conversation_id", "seq"
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
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    author_type: Mapped[str] = mapped_column(String(12), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    requested_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    requested_run_queue_seq: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    turn_request_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turn_dispatch_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    turn_dispatch_error_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    turn_dispatch_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    origin_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    output_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    content_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="visible"
    )
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redacted_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MessagePartModel(Base):
    __tablename__ = "agent_message_parts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "message_id", "part_seq", name="uq_agent_msg_part_seq"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["metaedu.agent_messages.tenant_id", "metaedu.agent_messages.id"],
            name="fk_agent_msg_part_message",
        ),
        CheckConstraint("part_seq >= 1", name="ck_agent_msg_part_seq_positive"),
        CheckConstraint(
            "part_type IN ('text', 'resource_ref')",
            name="ck_agent_msg_part_type",
        ),
        CheckConstraint(
            "classification IN ('public', 'internal', 'restricted')",
            name="ck_agent_msg_part_classification",
        ),
        CheckConstraint(
            "(part_type = 'text' AND text_content IS NOT NULL AND "
            "content_format IN ('plain_text', 'markdown') AND resource_id IS NULL) "
            "OR (part_type = 'resource_ref' AND resource_id IS NOT NULL AND "
            "text_content IS NULL AND content_format IS NULL)",
            name="ck_agent_msg_part_payload",
        ),
        CheckConstraint(
            "char_length(digest) = 64", name="ck_agent_msg_part_digest_length"
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    part_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    part_type: Mapped[str] = mapped_column(String(16), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(
        String(16), nullable=False, default="internal"
    )


class WorkspaceOutboxModel(Base):
    __tablename__ = "agent_workspace_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'published', 'dead_letter', 'cancelled')",
            name="ck_agent_ws_outbox_status",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_ws_outbox_digest_length",
        ),
        CheckConstraint(
            "(payload_inline IS NOT NULL AND payload_ref IS NULL "
            "AND pg_column_size(payload_inline) <= 32768) OR "
            "(payload_inline IS NULL AND payload_ref IS NOT NULL)",
            name="ck_agent_ws_outbox_payload",
        ),
        Index(
            "uq_agent_ws_outbox_turn",
            "tenant_id",
            "aggregate_id",
            unique=True,
            postgresql_where=text("event_type = 'turn.requested.v1'"),
        ),
        Index(
            "ix_agent_ws_outbox_dispatch",
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
    payload_inline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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


class WorkspaceInboxModel(Base):
    __tablename__ = "agent_workspace_inbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "consumer_name", "event_id", name="uq_agent_ws_inbox_event"
        ),
        CheckConstraint(
            "status IN ('processing', 'consumed', 'rejected')",
            name="ck_agent_ws_inbox_status",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_ws_inbox_digest_length",
        ),
        Index(
            "ix_agent_ws_inbox_status", "tenant_id", "status", "created_at"
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
