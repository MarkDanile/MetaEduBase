from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_workspace.application.command_digest import (
    message_content_digest,
    message_part_digest,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import (
    MessagePartInput,
    ReservedUserTurn,
    TurnCommand,
)
from app.contexts.agent_workspace.application.ports import (
    FailClosedTerminalOutputReader,
    ResourceReferenceAccessPort,
    TerminalOutputReaderPort,
)
from app.contexts.agent_workspace.domain import (
    ContentClassification,
    Conversation,
    MessageContentState,
    MessagePartType,
    ResourceReferenceForbiddenError,
    TurnDispatchState,
    WorkspaceIntegrationConflictError,
)
from app.contexts.agent_workspace.infrastructure.bridge_repository import (
    WorkspaceBridgeRepository,
)
from app.contexts.agent_workspace.infrastructure.repository import (
    AgentWorkspaceRepository,
)
from app.shared.schemas.agent_integration import (
    AssistantMessagePublishRequestedV1,
    InboxAckV1,
    TurnLaunchSpecV1,
    TurnRequestedV1,
)
from app.shared.schemas.agent_integration_codec import integration_event_digest


@dataclass(frozen=True, slots=True)
class SubmitTurnReceipt:
    reserved: ReservedUserTurn
    event_id: uuid.UUID
    correlation_id: uuid.UUID
    dispatch_state: TurnDispatchState


@dataclass(frozen=True, slots=True)
class ClaimedWorkspaceEvent:
    event: TurnRequestedV1
    payload_digest: str
    attempt_count: int
    claimant_id: str


@dataclass(frozen=True, slots=True)
class PoisonedWorkspaceEvent:
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    error_code: str


class AgentWorkspaceBridgeService:
    """Workspace application port for the B1 control-plane composition root."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        output_reader: TerminalOutputReaderPort | None = None,
        resource_access: ResourceReferenceAccessPort | None = None,
    ):
        self._session = session
        self._workspace = AgentWorkspaceService(
            session, resource_access=resource_access
        )
        self._workspace_repo = AgentWorkspaceRepository(session)
        self._bridge_repo = WorkspaceBridgeRepository(session)
        self._output_reader = output_reader or FailClosedTerminalOutputReader()
        self._resource_access = resource_access

    async def submit_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        command: TurnCommand,
        launch: TurnLaunchSpecV1,
    ) -> SubmitTurnReceipt:
        if (
            command.agent_definition_version_id
            != launch.agent_definition_version_id
        ):
            raise WorkspaceIntegrationConflictError(
                "turn command Agent definition conflicts with the execution launch"
            )
        reserved = await self._workspace.reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=command,
        )
        message = reserved.message
        assert message.requested_run_id is not None
        assert message.requested_run_queue_seq is not None
        assert message.client_message_id is not None
        if reserved.idempotent_replay:
            row = await self._bridge_repo.require_turn_outbox(
                tenant_id=tenant_id, message_id=message.id
            )
            event = self._bridge_repo.parse_turn_event(row)
        else:
            occurred_at = datetime.now(UTC)
            event = TurnRequestedV1(
                event_id=uuid.uuid4(),
                tenant_id=tenant_id,
                aggregate_id=message.id,
                conversation_id=conversation_id,
                message_id=message.id,
                run_id=message.requested_run_id,
                queue_seq=message.requested_run_queue_seq,
                root_request_id=message.client_message_id,
                root_context_digest=message.content_digest,
                created_by=actor_id,
                correlation_id=uuid.uuid4(),
                launch=launch,
                occurred_at=occurred_at,
            )
            await self._bridge_repo.add_turn_outbox(event)
        return SubmitTurnReceipt(
            reserved=reserved,
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            dispatch_state=message.turn_dispatch_state or TurnDispatchState.PENDING,
        )

    async def claim_turn_event(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        event_id: uuid.UUID | None = None,
    ) -> ClaimedWorkspaceEvent | PoisonedWorkspaceEvent | None:
        result = await self._bridge_repo.claim_turn_outbox(
            worker_id=worker_id,
            now=now,
            stale_before=stale_before,
            event_id=event_id,
        )
        if result is None:
            return None
        row, event = result
        if event is None:
            return PoisonedWorkspaceEvent(
                tenant_id=row.tenant_id,
                event_id=row.id,
                error_code=row.last_error_code or "invalid_event_envelope",
            )
        assert row.claimed_by is not None
        return ClaimedWorkspaceEvent(
            event=event,
            payload_digest=row.payload_digest,
            attempt_count=row.attempt_count,
            claimant_id=row.claimed_by,
        )

    async def require_turn_event(
        self, *, tenant_id: uuid.UUID, message_id: uuid.UUID
    ) -> tuple[TurnRequestedV1, str]:
        row = await self._bridge_repo.require_turn_outbox(
            tenant_id=tenant_id, message_id=message_id
        )
        return self._bridge_repo.parse_turn_event(row), row.payload_digest

    async def acknowledge_turn(self, ack: InboxAckV1) -> None:
        await self._bridge_repo.acknowledge_turn_outbox(ack=ack)

    async def validate_turn_claim(
        self, claimed: ClaimedWorkspaceEvent
    ) -> None:
        await self._bridge_repo.validate_turn_claim(
            tenant_id=claimed.event.tenant_id,
            event_id=claimed.event.event_id,
            payload_digest=claimed.payload_digest,
            expected_attempt=claimed.attempt_count,
            claimant_id=claimed.claimant_id,
        )

    async def record_turn_failure(
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
        return await self._bridge_repo.record_turn_delivery_failure(
            tenant_id=tenant_id,
            event_id=event_id,
            payload_digest=payload_digest,
            error_code=error_code,
            next_attempt_at=next_attempt_at,
            max_attempts=max_attempts,
            expected_attempt=expected_attempt,
            claimant_id=claimant_id,
        )

    async def retry_turn_dispatch(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        now: datetime,
    ) -> None:
        resource_ids = await self._bridge_repo.prepare_turn_retry_authorization(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        if resource_ids and (
            self._resource_access is None
            or not await (
                self._resource_access.can_reference_resources(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    resource_ids=resource_ids,
                )
            )
        ):
            raise ResourceReferenceForbiddenError(
                "one or more resource references are no longer authorized"
            )
        await self._bridge_repo.retry_turn_dispatch(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            now=now,
        )

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
        return await self._bridge_repo.abandon_or_reconcile_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            execution_accepted=execution_accepted,
            now=now,
        )

    async def consume_assistant_publish(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
        delivery_attempt: int,
        claimant_id: str,
        consumed_at: datetime,
    ) -> InboxAckV1:
        self._require_event_digest(event, payload_digest)
        await self._bridge_repo.lock_projection_conversation(event)
        should_project = await self._bridge_repo.begin_output_receipt(
            event=event, payload_digest=payload_digest
        )
        if not should_project:
            state = await self._bridge_repo.output_projection_state(
                event=event, payload_digest=payload_digest
            )
            if state is None:
                raise WorkspaceIntegrationConflictError(
                    "consumed output receipt is missing its Message projection"
                )
        if should_project:
            output = await self._output_reader.read_terminal_output(
                tenant_id=event.tenant_id,
                conversation_id=event.conversation_id,
                run_id=event.run_id,
                output_ref=event.output_ref,
            )
            if output.media_type != event.output_media_type:
                raise WorkspaceIntegrationConflictError(
                    "terminal output media type conflicts with its envelope"
                )
            if len(output.content) != event.output_size:
                raise WorkspaceIntegrationConflictError(
                    "terminal output size conflicts with its envelope"
                )
            if len(output.content) > 64 * 1024:
                raise WorkspaceIntegrationConflictError(
                    "assistant Message text exceeds the 64 KiB workspace limit"
                )
            if hashlib.sha256(output.content).hexdigest() != event.output_digest:
                raise WorkspaceIntegrationConflictError(
                    "terminal output digest conflicts with its envelope"
                )
            content_format = self._content_format(event.output_media_type)
            try:
                text_content = output.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WorkspaceIntegrationConflictError(
                    "terminal text output is not valid UTF-8"
                ) from exc
            part = MessagePartInput(
                type=MessagePartType.TEXT,
                text=text_content,
                format=content_format,
                media_type=event.output_media_type,
                classification=ContentClassification(event.output_classification),
            )
            await self._bridge_repo.project_assistant_message(
                event=event,
                content_digest=message_content_digest((part,)),
                text_content=text_content,
                content_format=content_format,
                part_digest=message_part_digest(part),
                consumed_at=consumed_at,
            )
        return InboxAckV1(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            consumer_name="agent_workspace.assistant_publish.v1",
            payload_digest=payload_digest,
            delivery_attempt=delivery_attempt,
            claimant_id=claimant_id,
            consumed_at=consumed_at,
        )

    async def lock_output_conversation(
        self, event: AssistantMessagePublishRequestedV1
    ) -> None:
        await self._bridge_repo.lock_projection_conversation(event)

    async def suppress_assistant_publish(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
        reason: str,
        consumed_at: datetime,
    ) -> None:
        self._require_event_digest(event, payload_digest)
        await self._bridge_repo.lock_projection_conversation(event)
        should_project = await self._bridge_repo.begin_output_receipt(
            event=event, payload_digest=payload_digest
        )
        if not should_project:
            state = await self._bridge_repo.output_projection_state(
                event=event, payload_digest=payload_digest
            )
            if state is MessageContentState.VISIBLE:
                raise WorkspaceIntegrationConflictError(
                    "visible output must reconcile as published, not suppressed"
                )
            if state is not MessageContentState.REDACTED:
                raise WorkspaceIntegrationConflictError(
                    "consumed suppression receipt is missing its Message tombstone"
                )
        if should_project:
            await self._bridge_repo.project_suppressed_output(
                event=event,
                reason=reason,
                consumed_at=consumed_at,
            )

    async def output_is_projected(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
    ) -> bool:
        self._require_event_digest(event, payload_digest)
        state = await self._bridge_repo.output_projection_state(
            event=event, payload_digest=payload_digest
        )
        return state is MessageContentState.VISIBLE

    async def lock_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> None:
        await self._bridge_repo.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=include_deleted,
        )

    async def has_unacknowledged_turn(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        return await self._bridge_repo.has_unacknowledged_turn(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

    async def can_start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool:
        return await self._bridge_repo.can_start_run(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            run_id=run_id,
            queue_seq=queue_seq,
        )

    async def soft_delete_after_guard(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        purge_after: datetime,
    ) -> Conversation:
        return await self._workspace_repo.soft_delete_after_guard(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
            purge_after=purge_after,
        )

    async def restore_after_guard(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
    ) -> Conversation:
        return await self._workspace_repo.restore(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
        )

    @staticmethod
    def _require_event_digest(
        event: AssistantMessagePublishRequestedV1, payload_digest: str
    ) -> None:
        if integration_event_digest(event) != payload_digest:
            raise WorkspaceIntegrationConflictError(
                "assistant publish payload digest conflicts"
            )

    @staticmethod
    def _content_format(media_type: str) -> str:
        if media_type == "text/plain":
            return "plain_text"
        if media_type == "text/markdown":
            return "markdown"
        raise WorkspaceIntegrationConflictError(
            "B1 assistant projection only accepts text/plain or text/markdown"
        )
