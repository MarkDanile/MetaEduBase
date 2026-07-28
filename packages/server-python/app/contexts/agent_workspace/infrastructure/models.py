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
            "hold_revision >= 0",
            name="ck_agent_conv_hold_revision",
        ),
        CheckConstraint(
            "next_message_seq >= 1 AND next_run_queue_seq >= 1",
            name="ck_agent_conv_next_seq",
        ),
        CheckConstraint(
            "char_length(creation_digest) = 64",
            name="ck_agent_conv_creation_digest",
        ),
        CheckConstraint(
            "(actor_state = 'present' AND created_by IS NOT NULL "
            "AND creator_identity_digest IS NULL) OR "
            "(actor_state = 'redacted' AND created_by IS NULL "
            "AND creator_identity_digest IS NOT NULL "
            "AND char_length(creator_identity_digest) = 64)",
            name="ck_agent_conv_actor",
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
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    actor_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="present"
    )
    creator_identity_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
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
    hold_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
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
        CheckConstraint(
            "body_state IN ('present', 'redacted') AND "
            "(body_state <> 'redacted' OR content_state = 'redacted')",
            name="ck_agent_msg_body_state",
        ),
        CheckConstraint(
            "actor_identity_digest IS NULL OR "
            "char_length(actor_identity_digest) = 64",
            name="ck_agent_msg_actor_digest",
        ),
        CheckConstraint("seq >= 1", name="ck_agent_msg_seq_positive"),
        CheckConstraint(
            "requested_run_queue_seq IS NULL OR requested_run_queue_seq >= 1",
            name="ck_agent_msg_queue_seq_positive",
        ),
        CheckConstraint(
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
    body_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="present"
    )
    actor_identity_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
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
            "status IN ('pending', 'claimed', 'published', 'dead_letter', "
            "'cancelled', 'suppressed')",
            name="ck_agent_ws_outbox_status",
        ),
        CheckConstraint(
            "char_length(payload_digest) = 64",
            name="ck_agent_ws_outbox_digest_length",
        ),
        CheckConstraint(
            # suppressed 是 R1-S1 tombstone：清正文 ref/inline，保留 digest。
            "(status = 'suppressed' AND payload_inline IS NULL "
            "AND payload_ref IS NULL) OR "
            # 其余状态（含正常 cancelled）保持原有“恰好一个 payload 来源”。
            "(status <> 'suppressed' AND "
            "((payload_inline IS NOT NULL AND payload_ref IS NULL "
            "AND pg_column_size(payload_inline) <= 32768) OR "
            "(payload_inline IS NULL AND payload_ref IS NOT NULL)))",
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


# ---------------------------------------------------------------------------
# R1-S1 coordination infrastructure（Spec §5）。
#
# ErasureFence / PurgeOperation / PurgeOwnerCheckpoint / ConversationLegalHold
# 属于 control-plane coordination infrastructure，由 ``agent_workspace`` 持有
# legal-hold lifecycle envelope 与 Conversation 生命周期。它们不建跨
# bounded-context 外键或 ORM cascade；``agent_execution`` 经 composition
# port 使用，不 import 这些 ORM。R1-S1 只提供 schema 基座，不启动
# scheduler、不清除正文。
# ---------------------------------------------------------------------------


class ErasureFenceModel(Base):
    __tablename__ = "agent_erasure_fences"
    __table_args__ = (
        # PK = (tenant_id, conversation_id, owner_key)（下方 primary_key=True）。
        # 不再声明同三列 UK：PostgreSQL 对「UK 列 ⊆ PK 列」去重，UK 从不创建
        # （死声明）。也不再建 (tenant_id, conversation_id) 前缀 Index：PK btree
        # 已可服务该前缀查询，冗余 ix 只增写放大（TD-089）。
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_erasure_fence_conversation",
        ),
        CheckConstraint(
            "state IN ('active', 'erasing', 'erased', 'blocked')",
            name="ck_agent_erasure_fence_state",
        ),
        CheckConstraint(
            "owner_version >= 1 AND purge_revision >= 0 AND hold_revision >= 0 "
            "AND revision >= 1",
            name="ck_agent_erasure_fence_revisions",
        ),
        CheckConstraint(
            "char_length(ingress_digest) = 64",
            name="ck_agent_erasure_fence_ingress_digest",
        ),
        CheckConstraint(
            "jsonb_typeof(ingress_checkpoint) = 'object' "
            "AND pg_column_size(ingress_checkpoint) <= 16384",
            name="ck_agent_erasure_fence_ingress_checkpoint",
        ),
        CheckConstraint(
            "(state = 'erased' AND ack_digest IS NOT NULL "
            "AND char_length(ack_digest) = 64 AND acked_at IS NOT NULL) OR "
            "(state <> 'erased' AND ack_digest IS NULL AND acked_at IS NULL)",
            name="ck_agent_erasure_fence_ack",
        ),
        {"schema": "metaedu"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    owner_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    purge_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    hold_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ingress_checkpoint: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    ingress_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    last_body_write_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class PurgeOperationModel(Base):
    __tablename__ = "agent_conversation_purges"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_purge_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "purge_revision",
            name="uq_agent_purge_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_purge_conversation",
        ),
        CheckConstraint(
            "state IN ('scheduled', 'running', 'blocked', 'failed', "
            "'completed', 'cancelled')",
            name="ck_agent_purge_state",
        ),
        CheckConstraint(
            "purge_revision >= 1 AND lease_epoch >= 0 AND revision >= 1 "
            "AND hold_revision_snapshot >= 0",
            name="ck_agent_purge_revisions",
        ),
        CheckConstraint(
            "char_length(registry_digest) = 64 "
            "AND char_length(retention_policy_digest) = 64",
            name="ck_agent_purge_digests",
        ),
        CheckConstraint(
            "jsonb_typeof(registry_snapshot) = 'array' "
            "AND pg_column_size(registry_snapshot) <= 65536",
            name="ck_agent_purge_registry_snapshot",
        ),
        CheckConstraint(
            "jsonb_typeof(retention_policy_snapshot) = 'object' "
            "AND pg_column_size(retention_policy_snapshot) <= 16384",
            name="ck_agent_purge_retention_snapshot",
        ),
        Index(
            "ix_agent_purge_schedule",
            "tenant_id",
            "state",
            "scheduled_at",
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
    purge_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    registry_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_snapshot: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    retention_policy_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    retention_policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    hold_revision_snapshot: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    lease_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class PurgeOwnerCheckpointModel(Base):
    __tablename__ = "agent_conversation_purge_owners"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "purge_operation_id",
            "owner_key",
            name="uq_agent_purge_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purge_operation_id"],
            [
                "metaedu.agent_conversation_purges.tenant_id",
                "metaedu.agent_conversation_purges.id",
            ],
            name="fk_agent_purge_owner_operation",
        ),
        CheckConstraint(
            "state IN ('pending', 'erasing', 'blocked', 'failed', 'acked')",
            name="ck_agent_purge_owner_state",
        ),
        CheckConstraint("attempt >= 0", name="ck_agent_purge_owner_attempt"),
        CheckConstraint(
            "owner_version >= 1", name="ck_agent_purge_owner_version"
        ),
        CheckConstraint(
            "char_length(capability_digest) = 64",
            name="ck_agent_purge_owner_capability_digest",
        ),
        CheckConstraint(
            "checkpoint_digest IS NULL OR char_length(checkpoint_digest) = 64",
            name="ck_agent_purge_owner_checkpoint_digest",
        ),
        CheckConstraint(
            "(state = 'acked' AND ack_digest IS NOT NULL "
            "AND char_length(ack_digest) = 64) OR "
            "(state <> 'acked' AND ack_digest IS NULL)",
            name="ck_agent_purge_owner_ack",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purge_operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    owner_key: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_version: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ack_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ConversationLegalHoldModel(Base):
    __tablename__ = "agent_conversation_legal_holds"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [
                "metaedu.agent_conversations.tenant_id",
                "metaedu.agent_conversations.id",
            ],
            name="fk_agent_legal_hold_conversation",
        ),
        CheckConstraint(
            "state IN ('active', 'expired', 'released')",
            name="ck_agent_legal_hold_state",
        ),
        CheckConstraint("revision >= 1", name="ck_agent_legal_hold_revision"),
        CheckConstraint(
            "char_length(btrim(reason_code)) > 0 AND reason_code = btrim(reason_code) "
            "AND char_length(reason_code) <= 100",
            name="ck_agent_legal_hold_reason",
        ),
        CheckConstraint(
            "(state = 'released' AND released_at IS NOT NULL "
            "AND released_by IS NOT NULL) OR "
            "(state <> 'released' AND released_at IS NULL AND released_by IS NULL)",
            name="ck_agent_legal_hold_release",
        ),
        Index(
            "ix_agent_legal_hold_conversation",
            "tenant_id",
            "conversation_id",
            "state",
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
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
