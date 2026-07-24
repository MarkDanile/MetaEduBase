from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_workspace.application.command_digest import (
    message_content_digest,
    message_part_digest,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput
from app.contexts.agent_workspace.domain import (
    AuthorType,
    ContentClassification,
    ConversationNotFoundError,
    ConversationState,
    InvalidConversationStateError,
    MessageContentState,
    MessageKind,
    MessagePartType,
    TurnDispatchState,
    WorkspaceIntegrationConflictError,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    MessageModel,
    MessagePartModel,
    WorkspaceInboxModel,
    WorkspaceOutboxModel,
)
from app.shared.schemas.agent_integration import (
    ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1,
    TURN_REQUESTED_V1,
    AssistantMessagePublishRequestedV1,
    InboxAckV1,
    TurnRequestedV1,
)
from app.shared.schemas.agent_integration_codec import (
    integration_event_digest,
    integration_event_payload,
    parse_integration_event,
)

WORKSPACE_TURN_CONSUMER = "agent_execution.turn_requested.v1"
WORKSPACE_OUTPUT_CONSUMER = "agent_workspace.assistant_publish.v1"


class WorkspaceBridgeRepository:
    """Workspace-owned integration facts. The caller owns transaction boundaries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_turn_outbox(self, event: TurnRequestedV1) -> WorkspaceOutboxModel:
        digest = integration_event_digest(event)
        existing = await self._turn_outbox_for_message(
            tenant_id=event.tenant_id,
            message_id=event.message_id,
            for_update=False,
        )
        if existing is not None:
            self._validate_outbox(existing, event=event, payload_digest=digest)
            return existing
        row = WorkspaceOutboxModel(
            id=event.event_id,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            aggregate_id=event.message_id,
            aggregate_type=event.aggregate_type,
            payload_inline=integration_event_payload(event),
            payload_ref=None,
            payload_digest=digest,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            status="pending",
            attempt_count=0,
            next_attempt_at=event.occurred_at,
            created_at=event.occurred_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def require_turn_outbox(
        self, *, tenant_id: uuid.UUID, message_id: uuid.UUID, for_update: bool = False
    ) -> WorkspaceOutboxModel:
        row = await self._turn_outbox_for_message(
            tenant_id=tenant_id,
            message_id=message_id,
            for_update=for_update,
        )
        if row is None:
            raise WorkspaceIntegrationConflictError("turn outbox event is missing")
        return row

    async def claim_turn_outbox(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        event_id: uuid.UUID | None = None,
    ) -> tuple[WorkspaceOutboxModel, TurnRequestedV1 | None] | None:
        eligible = or_(
            and_(
                WorkspaceOutboxModel.status == "pending",
                WorkspaceOutboxModel.next_attempt_at <= now,
            ),
            and_(
                WorkspaceOutboxModel.status == "claimed",
                WorkspaceOutboxModel.claimed_at <= stale_before,
            ),
        )
        statement = (
            select(WorkspaceOutboxModel)
            .where(
                WorkspaceOutboxModel.event_type == TURN_REQUESTED_V1,
                eligible,
            )
            .order_by(WorkspaceOutboxModel.created_at, WorkspaceOutboxModel.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if event_id is not None:
            statement = statement.where(WorkspaceOutboxModel.id == event_id)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        row.status = "claimed"
        row.attempt_count += 1
        row.claimed_at = now
        row.claimed_by = worker_id[:100]
        row.last_error_code = None
        try:
            event = self.parse_turn_event(row)
        except WorkspaceIntegrationConflictError:
            row.status = "dead_letter"
            row.claimed_at = None
            row.claimed_by = None
            row.last_error_code = "invalid_event_envelope"
            message = (
                await self._session.execute(
                    select(MessageModel)
                    .where(
                        MessageModel.tenant_id == row.tenant_id,
                        MessageModel.id == row.aggregate_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if message is not None:
                message.turn_dispatch_state = TurnDispatchState.DEAD_LETTER.value
                message.turn_dispatch_error_code = "invalid_event_envelope"
                message.turn_dispatch_updated_at = now
            await self._session.flush()
            return row, None
        await self._session.flush()
        return row, event

    async def validate_turn_claim(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        expected_attempt: int,
        claimant_id: str,
    ) -> None:
        row = await self._require_outbox_for_update(
            tenant_id=tenant_id, event_id=event_id
        )
        if (
            row.status != "claimed"
            or row.payload_digest != payload_digest
            or row.attempt_count != expected_attempt
            or row.claimed_by != claimant_id
        ):
            raise WorkspaceIntegrationConflictError(
                "turn claim was superseded or no longer owns delivery"
            )

    async def acknowledge_turn_outbox(
        self, *, ack: InboxAckV1
    ) -> WorkspaceOutboxModel:
        row = await self._require_outbox_for_update(
            tenant_id=ack.tenant_id, event_id=ack.event_id
        )
        if row.payload_digest != ack.payload_digest:
            raise WorkspaceIntegrationConflictError("turn ACK payload digest conflicts")
        message = await self._require_message_for_update(
            tenant_id=ack.tenant_id, message_id=row.aggregate_id
        )
        if row.status == "published":
            if message.turn_dispatch_state != TurnDispatchState.ACCEPTED.value:
                raise WorkspaceIntegrationConflictError(
                    "published turn outbox is not projected as accepted"
                )
            return row
        if row.status == "cancelled":
            raise WorkspaceIntegrationConflictError("abandoned turn cannot be ACKed")
        if (
            row.status != "claimed"
            or row.attempt_count != ack.delivery_attempt
            or row.claimed_by != ack.claimant_id
        ):
            raise WorkspaceIntegrationConflictError(
                "turn ACK does not own the current delivery claim"
            )
        now = ack.consumed_at
        row.status = "published"
        row.published_at = now
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        message.turn_dispatch_state = TurnDispatchState.ACCEPTED.value
        message.turn_dispatch_error_code = None
        message.turn_dispatch_updated_at = now
        await self._session.flush()
        return row

    async def record_turn_delivery_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        error_code: str,
        next_attempt_at: datetime,
        max_attempts: int,
        expected_attempt: int,
        claimant_id: str,
    ) -> bool:
        row = await self._require_outbox_for_update(
            tenant_id=tenant_id, event_id=event_id
        )
        if row.payload_digest != payload_digest:
            raise WorkspaceIntegrationConflictError("turn failure digest conflicts")
        if row.status == "published":
            return False
        if (
            row.status != "claimed"
            or row.attempt_count != expected_attempt
            or row.claimed_by != claimant_id
        ):
            raise WorkspaceIntegrationConflictError(
                "turn failure does not own the current delivery claim"
            )
        dead_lettered = row.attempt_count >= max_attempts
        row.status = "dead_letter" if dead_lettered else "pending"
        row.next_attempt_at = next_attempt_at
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = error_code[:100]
        message = await self._require_message_for_update(
            tenant_id=tenant_id, message_id=row.aggregate_id
        )
        message.turn_dispatch_state = (
            TurnDispatchState.DEAD_LETTER.value
            if dead_lettered
            else TurnDispatchState.PENDING.value
        )
        message.turn_dispatch_error_code = error_code[:100]
        message.turn_dispatch_updated_at = datetime.now(UTC)
        await self._session.flush()
        return dead_lettered

    async def retry_turn_dispatch(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        now: datetime,
    ) -> WorkspaceOutboxModel:
        await self.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=False,
        )
        row = await self.require_turn_outbox(
            tenant_id=tenant_id, message_id=message_id, for_update=True
        )
        message = await self._require_message_for_update(
            tenant_id=tenant_id,
            message_id=message_id,
            conversation_id=conversation_id,
        )
        if (
            message.turn_dispatch_state != TurnDispatchState.DEAD_LETTER.value
            or row.status != "dead_letter"
        ):
            raise WorkspaceIntegrationConflictError(
                "only a dead-lettered turn can be retried"
            )
        row.status = "pending"
        row.attempt_count = 0
        row.next_attempt_at = now
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        message.turn_dispatch_state = TurnDispatchState.PENDING.value
        message.turn_dispatch_error_code = None
        message.turn_dispatch_updated_at = now
        await self._session.flush()
        return row

    async def prepare_turn_retry_authorization(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> tuple[uuid.UUID, ...]:
        await self.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=False,
        )
        row = await self.require_turn_outbox(
            tenant_id=tenant_id, message_id=message_id, for_update=True
        )
        message = await self._require_message_for_update(
            tenant_id=tenant_id,
            message_id=message_id,
            conversation_id=conversation_id,
        )
        if (
            row.status != "dead_letter"
            or message.turn_dispatch_state != TurnDispatchState.DEAD_LETTER.value
        ):
            raise WorkspaceIntegrationConflictError(
                "only a dead-lettered turn can be authorized for retry"
            )
        resource_ids = (
            await self._session.execute(
                select(MessagePartModel.resource_id).where(
                    MessagePartModel.tenant_id == tenant_id,
                    MessagePartModel.message_id == message_id,
                    MessagePartModel.resource_id.is_not(None),
                )
            )
        ).scalars()
        return tuple(resource_id for resource_id in resource_ids if resource_id)

    async def abandon_or_reconcile_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        execution_accepted: bool,
        now: datetime,
    ) -> TurnDispatchState:
        await self.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=False,
        )
        row = await self.require_turn_outbox(
            tenant_id=tenant_id, message_id=message_id, for_update=True
        )
        message = await self._require_message_for_update(
            tenant_id=tenant_id,
            message_id=message_id,
            conversation_id=conversation_id,
        )
        if execution_accepted:
            row.status = "published"
            row.published_at = now
            row.claimed_at = None
            row.claimed_by = None
            message.turn_dispatch_state = TurnDispatchState.ACCEPTED.value
            message.turn_dispatch_error_code = None
            message.turn_dispatch_updated_at = now
            await self._session.flush()
            return TurnDispatchState.ACCEPTED
        if row.status == "claimed":
            raise WorkspaceIntegrationConflictError(
                "a claimed turn must finish or expire before abandon"
            )
        if row.status not in {"pending", "dead_letter"} or (
            message.turn_dispatch_state
            not in {
                TurnDispatchState.PENDING.value,
                TurnDispatchState.DEAD_LETTER.value,
            }
        ):
            raise WorkspaceIntegrationConflictError("turn cannot be abandoned")
        row.status = "cancelled"
        row.claimed_at = None
        row.claimed_by = None
        message.turn_dispatch_state = TurnDispatchState.ABANDONED.value
        message.turn_dispatch_error_code = None
        message.turn_dispatch_updated_at = now
        await self._session.flush()
        return TurnDispatchState.ABANDONED

    async def share_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> ConversationModel:
        statement = self._owned_conversation_statement(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=include_deleted,
        )
        row = (
            await self._session.execute(statement.with_for_update(read=True))
        ).scalar_one_or_none()
        if row is None:
            raise ConversationNotFoundError("Conversation not found")
        return row

    async def lock_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> ConversationModel:
        statement = self._owned_conversation_statement(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=include_deleted,
        )
        row = (
            await self._session.execute(statement.with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise ConversationNotFoundError("Conversation not found")
        return row

    @staticmethod
    def _owned_conversation_statement(
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ):
        statement = select(ConversationModel).where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.id == conversation_id,
            ConversationModel.created_by == actor_id,
        )
        if not include_deleted:
            statement = statement.where(
                ConversationModel.state != ConversationState.DELETED.value
            )
        return statement

    async def has_unacknowledged_turn(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        statement = (
            select(MessageModel.id)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.message_kind == MessageKind.USER_INPUT.value,
                MessageModel.turn_dispatch_state.in_(
                    [
                        TurnDispatchState.PENDING.value,
                        TurnDispatchState.DEAD_LETTER.value,
                    ]
                ),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def can_start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool:
        conversation = await self.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=True,
        )
        if conversation.state != ConversationState.ACTIVE.value:
            return False
        candidate = (
            await self._session.execute(
                select(MessageModel).where(
                    MessageModel.tenant_id == tenant_id,
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.requested_run_id == run_id,
                    MessageModel.requested_run_queue_seq == queue_seq,
                    MessageModel.message_kind == MessageKind.USER_INPUT.value,
                )
            )
        ).scalar_one_or_none()
        if (
            candidate is None
            or candidate.turn_dispatch_state != TurnDispatchState.ACCEPTED.value
        ):
            return False
        unresolved_predecessor = (
            await self._session.execute(
                select(MessageModel.id)
                .where(
                    MessageModel.tenant_id == tenant_id,
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.requested_run_queue_seq < queue_seq,
                    MessageModel.turn_dispatch_state.in_(
                        [
                            TurnDispatchState.PENDING.value,
                            TurnDispatchState.DEAD_LETTER.value,
                        ]
                    ),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return unresolved_predecessor is None

    async def begin_output_receipt(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
    ) -> bool:
        existing = (
            await self._session.execute(
                select(WorkspaceInboxModel)
                .where(
                    WorkspaceInboxModel.tenant_id == event.tenant_id,
                    WorkspaceInboxModel.consumer_name == WORKSPACE_OUTPUT_CONSUMER,
                    WorkspaceInboxModel.event_id == event.event_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            self._validate_inbox(existing, event=event, payload_digest=payload_digest)
            if existing.status == "consumed":
                return False
            raise WorkspaceIntegrationConflictError(
                "output inbox receipt is not in a replayable state"
            )
        self._session.add(
            WorkspaceInboxModel(
                tenant_id=event.tenant_id,
                consumer_name=WORKSPACE_OUTPUT_CONSUMER,
                event_id=event.event_id,
                event_type=event.event_type,
                schema_version=event.schema_version,
                payload_digest=payload_digest,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                status="processing",
                created_at=event.occurred_at,
            )
        )
        await self._session.flush()
        return True

    async def lock_projection_conversation(
        self, event: AssistantMessagePublishRequestedV1
    ) -> None:
        await self._lock_projection_conversation(event)

    async def project_assistant_message(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        content_digest: str,
        text_content: str,
        content_format: str,
        part_digest: str,
        consumed_at: datetime,
    ) -> None:
        conversation = await self._lock_projection_conversation(event)
        existing = await self._existing_output_message(event)
        if existing is not None:
            raise WorkspaceIntegrationConflictError(
                "output Message exists without a consumed inbox receipt"
            )
        message = MessageModel(
            id=event.message_id,
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
            seq=conversation.next_message_seq,
            message_kind=MessageKind.ASSISTANT_OUTPUT.value,
            author_type=AuthorType.AGENT.value,
            author_id=event.agent_definition_version_id,
            origin_run_id=event.run_id,
            output_ordinal=event.output_ordinal,
            reply_to_message_id=event.reply_to_message_id,
            content_state=MessageContentState.VISIBLE.value,
            content_digest=content_digest,
            created_at=consumed_at,
        )
        self._session.add(message)
        self._session.add(
            MessagePartModel(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                message_id=event.message_id,
                part_seq=1,
                part_type="text",
                text_content=text_content,
                content_format=content_format,
                resource_id=None,
                media_type=event.output_media_type,
                display_name=None,
                digest=part_digest,
                classification=event.output_classification,
            )
        )
        conversation.next_message_seq += 1
        if conversation.state != ConversationState.DELETED.value:
            conversation.last_activity_at = consumed_at
        conversation.updated_at = consumed_at
        await self._consume_output_receipt(event=event, consumed_at=consumed_at)

    async def project_suppressed_output(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        reason: str,
        consumed_at: datetime,
    ) -> None:
        conversation = await self._lock_projection_conversation(event)
        existing = await self._existing_output_message(event)
        if existing is not None:
            raise WorkspaceIntegrationConflictError(
                "suppressed output Message conflicts with an existing projection"
            )
        self._session.add(
            MessageModel(
                id=event.message_id,
                tenant_id=event.tenant_id,
                conversation_id=event.conversation_id,
                seq=conversation.next_message_seq,
                message_kind=MessageKind.ASSISTANT_OUTPUT.value,
                author_type=AuthorType.AGENT.value,
                author_id=event.agent_definition_version_id,
                origin_run_id=event.run_id,
                output_ordinal=event.output_ordinal,
                reply_to_message_id=event.reply_to_message_id,
                content_state=MessageContentState.REDACTED.value,
                content_digest=event.output_digest,
                created_at=consumed_at,
                redacted_at=consumed_at,
                redacted_reason=reason[:200],
            )
        )
        conversation.next_message_seq += 1
        conversation.updated_at = consumed_at
        await self._consume_output_receipt(event=event, consumed_at=consumed_at)

    async def output_projection_state(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
    ) -> MessageContentState | None:
        inbox = (
            await self._session.execute(
                select(WorkspaceInboxModel).where(
                    WorkspaceInboxModel.tenant_id == event.tenant_id,
                    WorkspaceInboxModel.consumer_name == WORKSPACE_OUTPUT_CONSUMER,
                    WorkspaceInboxModel.event_id == event.event_id,
                )
            )
        ).scalar_one_or_none()
        if inbox is None:
            return None
        self._validate_inbox(inbox, event=event, payload_digest=payload_digest)
        if inbox.status != "consumed":
            return None
        message = await self._existing_output_message(event)
        if message is None:
            return None
        await self._validate_output_message(message, event)
        return MessageContentState(message.content_state)

    def parse_turn_event(self, row: WorkspaceOutboxModel) -> TurnRequestedV1:
        if row.payload_inline is None:
            raise WorkspaceIntegrationConflictError("turn outbox payload is unavailable")
        try:
            event = parse_integration_event(row.payload_inline)
        except ValidationError as exc:
            raise WorkspaceIntegrationConflictError(
                "turn outbox payload does not match its versioned schema"
            ) from exc
        if not isinstance(event, TurnRequestedV1):
            raise WorkspaceIntegrationConflictError("turn outbox event type conflicts")
        self._validate_outbox(
            row, event=event, payload_digest=integration_event_digest(event)
        )
        return event

    async def _lock_projection_conversation(
        self, event: AssistantMessagePublishRequestedV1
    ) -> ConversationModel:
        conversation = (
            await self._session.execute(
                select(ConversationModel)
                .where(
                    ConversationModel.tenant_id == event.tenant_id,
                    ConversationModel.id == event.conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found for output projection")
        if conversation.purge_state in {"running", "completed"}:
            raise InvalidConversationStateError(
                "output projection is fenced by Conversation purge"
            )
        return conversation

    async def _consume_output_receipt(
        self, *, event: AssistantMessagePublishRequestedV1, consumed_at: datetime
    ) -> None:
        receipt = (
            await self._session.execute(
                select(WorkspaceInboxModel)
                .where(
                    WorkspaceInboxModel.tenant_id == event.tenant_id,
                    WorkspaceInboxModel.consumer_name == WORKSPACE_OUTPUT_CONSUMER,
                    WorkspaceInboxModel.event_id == event.event_id,
                )
                .with_for_update()
            )
        ).scalar_one()
        if receipt.status != "processing":
            raise WorkspaceIntegrationConflictError(
                "output inbox receipt must be processing before consumption"
            )
        receipt.status = "consumed"
        receipt.consumed_at = consumed_at
        receipt.last_error_code = None
        await self._session.flush()

    async def _existing_output_message(
        self, event: AssistantMessagePublishRequestedV1
    ) -> MessageModel | None:
        return (
            await self._session.execute(
                select(MessageModel).where(
                    MessageModel.tenant_id == event.tenant_id,
                    or_(
                        MessageModel.id == event.message_id,
                        and_(
                            MessageModel.origin_run_id == event.run_id,
                            MessageModel.output_ordinal == event.output_ordinal,
                        ),
                    ),
                )
            )
        ).scalar_one_or_none()

    async def _validate_output_message(
        self, message: MessageModel, event: AssistantMessagePublishRequestedV1
    ) -> None:
        if (
            message.id != event.message_id
            or message.tenant_id != event.tenant_id
            or message.conversation_id != event.conversation_id
            or message.message_kind != MessageKind.ASSISTANT_OUTPUT.value
            or message.author_type != AuthorType.AGENT.value
            or message.author_id != event.agent_definition_version_id
            or message.origin_run_id != event.run_id
            or message.output_ordinal != event.output_ordinal
            or message.reply_to_message_id != event.reply_to_message_id
        ):
            raise WorkspaceIntegrationConflictError(
                "assistant Message conflicts with its output event identity"
            )
        parts = list(
            (
                await self._session.execute(
                    select(MessagePartModel)
                    .where(
                        MessagePartModel.tenant_id == event.tenant_id,
                        MessagePartModel.message_id == event.message_id,
                    )
                    .order_by(MessagePartModel.part_seq)
                )
            ).scalars()
        )
        if message.content_state == MessageContentState.REDACTED.value:
            if parts or message.content_digest != event.output_digest:
                raise WorkspaceIntegrationConflictError(
                    "redacted output tombstone conflicts with its terminal digest"
                )
            return
        if message.content_state != MessageContentState.VISIBLE.value or len(parts) != 1:
            raise WorkspaceIntegrationConflictError(
                "visible assistant output must contain exactly one text part"
            )
        part = parts[0]
        expected_format = (
            "markdown" if event.output_media_type == "text/markdown" else "plain_text"
        )
        if (
            part.part_seq != 1
            or part.part_type != "text"
            or part.text_content is None
            or part.content_format != expected_format
            or part.media_type != event.output_media_type
            or part.classification != event.output_classification
        ):
            raise WorkspaceIntegrationConflictError(
                "assistant output part metadata conflicts with its terminal envelope"
            )
        raw_content = part.text_content.encode("utf-8")
        if (
            len(raw_content) != event.output_size
            or hashlib.sha256(raw_content).hexdigest() != event.output_digest
        ):
            raise WorkspaceIntegrationConflictError(
                "assistant output bytes conflict with its terminal envelope"
            )
        projected_part = MessagePartInput(
            type=MessagePartType.TEXT,
            text=part.text_content,
            format=part.content_format,
            media_type=part.media_type,
            classification=ContentClassification(part.classification),
        )
        if (
            part.digest != message_part_digest(projected_part)
            or message.content_digest != message_content_digest((projected_part,))
        ):
            raise WorkspaceIntegrationConflictError(
                "assistant output digest metadata conflicts with its content"
            )

    async def _turn_outbox_for_message(
        self,
        *,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        for_update: bool,
    ) -> WorkspaceOutboxModel | None:
        statement = select(WorkspaceOutboxModel).where(
            WorkspaceOutboxModel.tenant_id == tenant_id,
            WorkspaceOutboxModel.aggregate_id == message_id,
            WorkspaceOutboxModel.event_type == TURN_REQUESTED_V1,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def _require_outbox_for_update(
        self, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> WorkspaceOutboxModel:
        row = (
            await self._session.execute(
                select(WorkspaceOutboxModel)
                .where(
                    WorkspaceOutboxModel.tenant_id == tenant_id,
                    WorkspaceOutboxModel.id == event_id,
                    WorkspaceOutboxModel.event_type == TURN_REQUESTED_V1,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise WorkspaceIntegrationConflictError("turn outbox event not found")
        return row

    async def _require_message_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
    ) -> MessageModel:
        statement = select(MessageModel).where(
            MessageModel.tenant_id == tenant_id,
            MessageModel.id == message_id,
        )
        if conversation_id is not None:
            statement = statement.where(
                MessageModel.conversation_id == conversation_id
            )
        row = (
            await self._session.execute(statement.with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise WorkspaceIntegrationConflictError("workspace Message not found")
        return row

    @staticmethod
    def _validate_outbox(
        row: WorkspaceOutboxModel,
        *,
        event: TurnRequestedV1,
        payload_digest: str,
    ) -> None:
        if (
            row.id != event.event_id
            or row.event_type != event.event_type
            or row.schema_version != event.schema_version
            or row.tenant_id != event.tenant_id
            or row.aggregate_id != event.aggregate_id
            or row.aggregate_type != event.aggregate_type
            or row.correlation_id != event.correlation_id
            or row.causation_id != event.causation_id
            or row.payload_digest != payload_digest
        ):
            raise WorkspaceIntegrationConflictError(
                "turn outbox envelope conflicts with its durable payload"
            )

    @staticmethod
    def _validate_inbox(
        row: WorkspaceInboxModel,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
    ) -> None:
        if (
            row.event_type != ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1
            or row.schema_version != event.schema_version
            or row.payload_digest != payload_digest
            or row.correlation_id != event.correlation_id
            or row.causation_id != event.causation_id
        ):
            raise WorkspaceIntegrationConflictError(
                "output inbox replay conflicts with its durable receipt"
            )
