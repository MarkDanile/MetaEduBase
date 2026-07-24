from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.domain import (
    TERMINAL_RUN_STATUSES,
    ExecutionIntegrationConflictError,
    OutputPublishState,
    RunStatus,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionInboxModel,
    ExecutionOutboxModel,
    TurnInputModel,
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
    parse_integration_event,
)

EXECUTION_TURN_CONSUMER = "agent_execution.turn_requested.v1"


class ExecutionBridgeRepository:
    """Execution-owned integration facts. The caller owns transaction boundaries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def begin_turn_receipt(
        self, *, event: TurnRequestedV1, payload_digest: str
    ) -> bool:
        existing = (
            await self._session.execute(
                select(ExecutionInboxModel)
                .where(
                    ExecutionInboxModel.tenant_id == event.tenant_id,
                    ExecutionInboxModel.consumer_name == EXECUTION_TURN_CONSUMER,
                    ExecutionInboxModel.event_id == event.event_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            self._validate_turn_inbox(
                existing, event=event, payload_digest=payload_digest
            )
            if existing.status == "consumed":
                return False
            raise ExecutionIntegrationConflictError(
                "turn inbox receipt is not in a replayable state"
            )
        self._session.add(
            ExecutionInboxModel(
                tenant_id=event.tenant_id,
                consumer_name=EXECUTION_TURN_CONSUMER,
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

    async def consume_turn_receipt(
        self, *, event: TurnRequestedV1, consumed_at: datetime
    ) -> None:
        row = (
            await self._session.execute(
                select(ExecutionInboxModel)
                .where(
                    ExecutionInboxModel.tenant_id == event.tenant_id,
                    ExecutionInboxModel.consumer_name == EXECUTION_TURN_CONSUMER,
                    ExecutionInboxModel.event_id == event.event_id,
                )
                .with_for_update()
            )
        ).scalar_one()
        if row.status != "processing":
            raise ExecutionIntegrationConflictError(
                "turn inbox receipt must be processing before consumption"
            )
        row.status = "consumed"
        row.consumed_at = consumed_at
        row.last_error_code = None
        await self._session.flush()

    async def has_turn_acceptance(
        self, event: TurnRequestedV1, *, payload_digest: str
    ) -> bool:
        receipt = (
            await self._session.execute(
                select(ExecutionInboxModel).where(
                    ExecutionInboxModel.tenant_id == event.tenant_id,
                    ExecutionInboxModel.consumer_name == EXECUTION_TURN_CONSUMER,
                    ExecutionInboxModel.event_id == event.event_id,
                )
            )
        ).scalar_one_or_none()
        run = (
            await self._session.execute(
                select(AgentRunModel).where(
                    AgentRunModel.tenant_id == event.tenant_id,
                    AgentRunModel.id == event.run_id,
                    AgentRunModel.conversation_id == event.conversation_id,
                )
            )
        ).scalar_one_or_none()
        if receipt is None and run is None:
            return False
        if receipt is None or run is None:
            raise ExecutionIntegrationConflictError(
                "turn acceptance has only one side of its atomic receipt/Run facts"
            )
        self._validate_turn_inbox(
            receipt, event=event, payload_digest=payload_digest
        )
        if receipt.status != "consumed":
            raise ExecutionIntegrationConflictError(
                "turn acceptance receipt is not consumed"
            )
        if (
            run.root_input_message_id != event.message_id
            or run.queue_seq != event.queue_seq
            or run.parent_run_id != event.launch.parent_run_id
            or run.created_by != event.created_by
            or run.correlation_id != event.correlation_id
            or run.agent_definition_version_id
            != event.launch.agent_definition_version_id
            or run.runtime_profile_id != event.launch.runtime_profile_id
            or run.runtime_binding_id != event.launch.runtime_binding_id
            or run.runtime_capability_snapshot
            != event.launch.runtime_capability_snapshot.model_dump(mode="json")
            or run.run_config_snapshot
            != event.launch.run_config_snapshot.model_dump(mode="json")
            or run.context_snapshot_ref != event.launch.context_snapshot_ref
            or run.context_snapshot_digest != event.launch.context_snapshot_digest
            or run.context_snapshot_classification
            != event.launch.context_snapshot_classification
            or run.budget_snapshot
            != event.launch.budget_snapshot.model_dump(mode="json")
        ):
            raise ExecutionIntegrationConflictError(
                "turn acceptance Run conflicts with its requested identity"
            )
        root = (
            await self._session.execute(
                select(TurnInputModel).where(
                    TurnInputModel.tenant_id == event.tenant_id,
                    TurnInputModel.run_id == event.run_id,
                    TurnInputModel.ordinal == 0,
                )
            )
        ).scalar_one_or_none()
        if (
            root is None
            or root.message_id != event.message_id
            or root.request_id != event.root_request_id
            or root.context_digest != event.root_context_digest
        ):
            raise ExecutionIntegrationConflictError(
                "turn acceptance root input conflicts with its request"
            )
        return True

    async def has_non_terminal_run(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        statement = (
            select(AgentRunModel.id)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.status.not_in(
                    [status.value for status in TERMINAL_RUN_STATUSES]
                ),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def claim_output_outbox(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        event_id: uuid.UUID | None = None,
    ) -> tuple[
        ExecutionOutboxModel, AssistantMessagePublishRequestedV1 | None
    ] | None:
        eligible = or_(
            and_(
                ExecutionOutboxModel.status == "pending",
                ExecutionOutboxModel.next_attempt_at <= now,
            ),
            and_(
                ExecutionOutboxModel.status == "claimed",
                ExecutionOutboxModel.claimed_at <= stale_before,
            ),
        )
        statement = (
            select(ExecutionOutboxModel)
            .where(
                ExecutionOutboxModel.event_type
                == ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1,
                eligible,
            )
            .order_by(ExecutionOutboxModel.created_at, ExecutionOutboxModel.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if event_id is not None:
            statement = statement.where(ExecutionOutboxModel.id == event_id)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        row.status = "claimed"
        row.attempt_count += 1
        row.claimed_at = now
        row.claimed_by = worker_id[:100]
        row.last_error_code = None
        try:
            event = self.parse_publish_event(row)
        except ExecutionIntegrationConflictError:
            row.status = "dead_letter"
            row.claimed_at = None
            row.claimed_by = None
            row.last_error_code = "invalid_event_envelope"
            run = (
                await self._session.execute(
                    select(AgentRunModel)
                    .where(
                        AgentRunModel.tenant_id == row.tenant_id,
                        AgentRunModel.id == row.aggregate_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if run is not None and RunStatus(run.status) is RunStatus.COMPLETED:
                run.output_publish_state = OutputPublishState.DEAD_LETTER.value
                run.updated_at = now
            await self._session.flush()
            return row, None
        await self._session.flush()
        return row, event

    async def acknowledge_output(self, *, ack: InboxAckV1) -> None:
        run, row = await self._lock_output_then_run(
            tenant_id=ack.tenant_id, event_id=ack.event_id
        )
        if row.payload_digest != ack.payload_digest:
            raise ExecutionIntegrationConflictError("output ACK payload digest conflicts")
        if row.status == "published":
            if run.output_publish_state != OutputPublishState.PUBLISHED.value:
                raise ExecutionIntegrationConflictError(
                    "published output outbox conflicts with Run projection state"
                )
            return
        if row.status == "cancelled":
            if run.output_publish_state == OutputPublishState.SUPPRESSED.value:
                return
            raise ExecutionIntegrationConflictError(
                "suppressed output cannot be acknowledged as published"
            )
        if (
            row.status != "claimed"
            or row.attempt_count != ack.delivery_attempt
            or row.claimed_by != ack.claimant_id
        ):
            raise ExecutionIntegrationConflictError(
                "output ACK does not own the current delivery claim"
            )
        if RunStatus(run.status) is not RunStatus.COMPLETED:
            raise ExecutionIntegrationConflictError(
                "only a completed Run can publish assistant output"
            )
        row.status = "published"
        row.published_at = ack.consumed_at
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        run.output_publish_state = OutputPublishState.PUBLISHED.value
        run.updated_at = ack.consumed_at
        await self._session.flush()

    async def validate_output_claim(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        expected_attempt: int,
        claimant_id: str,
    ) -> None:
        _, row = await self._lock_output_then_run(
            tenant_id=tenant_id, event_id=event_id
        )
        if (
            row.status != "claimed"
            or row.payload_digest != payload_digest
            or row.attempt_count != expected_attempt
            or row.claimed_by != claimant_id
        ):
            raise ExecutionIntegrationConflictError(
                "output claim was superseded or no longer owns delivery"
            )

    async def record_output_delivery_failure(
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
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, event_id=event_id
        )
        if row.payload_digest != payload_digest:
            raise ExecutionIntegrationConflictError("output failure digest conflicts")
        if (
            row.status == "cancelled"
            and run.output_publish_state == OutputPublishState.SUPPRESSED.value
        ):
            return False
        if row.status == "published":
            return False
        if (
            row.status != "claimed"
            or row.attempt_count != expected_attempt
            or row.claimed_by != claimant_id
        ):
            raise ExecutionIntegrationConflictError(
                "output failure does not own the current delivery claim"
            )
        dead_lettered = row.attempt_count >= max_attempts
        row.status = "dead_letter" if dead_lettered else "pending"
        row.next_attempt_at = next_attempt_at
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = error_code[:100]
        run.output_publish_state = (
            OutputPublishState.DEAD_LETTER.value
            if dead_lettered
            else OutputPublishState.PENDING.value
        )
        run.updated_at = next_attempt_at
        await self._session.flush()
        return dead_lettered

    async def reconcile_output_published(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        published_at: datetime,
    ) -> None:
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, event_id=event_id
        )
        if row.payload_digest != payload_digest:
            raise ExecutionIntegrationConflictError(
                "output reconcile payload digest conflicts"
            )
        if row.status == "cancelled" or (
            run.output_publish_state == OutputPublishState.SUPPRESSED.value
        ):
            raise ExecutionIntegrationConflictError(
                "suppressed output cannot reconcile as published"
            )
        row.status = "published"
        row.published_at = published_at
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        run.output_publish_state = OutputPublishState.PUBLISHED.value
        run.updated_at = published_at
        await self._session.flush()

    async def retry_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime,
    ) -> ExecutionOutboxModel:
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if (
            run.output_publish_state != OutputPublishState.DEAD_LETTER.value
            or row.status != "dead_letter"
        ):
            raise ExecutionIntegrationConflictError(
                "only a dead-lettered output can be retried"
            )
        row.status = "pending"
        row.attempt_count = 0
        row.next_attempt_at = now
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        run.output_publish_state = OutputPublishState.PENDING.value
        run.updated_at = now
        await self._session.flush()
        return row

    async def requeue_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime,
    ) -> None:
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if run.output_publish_state not in {
            OutputPublishState.PENDING.value,
            OutputPublishState.DEAD_LETTER.value,
        }:
            raise ExecutionIntegrationConflictError(
                "resolved output projection cannot be requeued"
            )
        if row.status == "published":
            raise ExecutionIntegrationConflictError(
                "published output outbox cannot be requeued"
            )
        row.status = "pending"
        row.next_attempt_at = now
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = None
        run.output_publish_state = OutputPublishState.PENDING.value
        run.updated_at = now
        await self._session.flush()

    async def suppress_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if RunStatus(run.status) is not RunStatus.COMPLETED:
            raise ExecutionIntegrationConflictError(
                "only completed output can be suppressed"
            )
        if run.output_publish_state not in {
            OutputPublishState.PENDING.value,
            OutputPublishState.DEAD_LETTER.value,
        }:
            raise ExecutionIntegrationConflictError(
                "resolved output projection cannot be suppressed"
            )
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ExecutionIntegrationConflictError("suppression reason is required")
        stored_reason = normalized_reason[:500]
        row.status = "cancelled"
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = "projection_suppressed"
        row.decision_actor_id = actor_id
        row.decision_reason = stored_reason
        row.decision_digest = snapshot_digest(
            {
                "actor_id": str(actor_id),
                "reason": stored_reason,
                "output_digest": run.terminal_output_digest,
            }
        )
        row.decided_at = decided_at
        run.output_publish_state = OutputPublishState.SUPPRESSED.value
        run.updated_at = decided_at
        await self._session.flush()

    async def require_publish_outbox(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        for_update: bool = False,
    ) -> ExecutionOutboxModel:
        statement = select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.tenant_id == tenant_id,
            ExecutionOutboxModel.aggregate_id == run_id,
            ExecutionOutboxModel.event_type
            == ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1,
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise ExecutionIntegrationConflictError("output outbox event is missing")
        return row

    def parse_publish_event(
        self, row: ExecutionOutboxModel
    ) -> AssistantMessagePublishRequestedV1:
        if row.payload_inline is None:
            raise ExecutionIntegrationConflictError("output outbox payload is unavailable")
        try:
            event = parse_integration_event(row.payload_inline)
        except ValidationError as exc:
            raise ExecutionIntegrationConflictError(
                "output outbox payload does not match its versioned schema"
            ) from exc
        if not isinstance(event, AssistantMessagePublishRequestedV1):
            raise ExecutionIntegrationConflictError("output outbox event type conflicts")
        digest = integration_event_digest(event)
        if (
            row.id != event.event_id
            or row.event_type != event.event_type
            or row.schema_version != event.schema_version
            or row.tenant_id != event.tenant_id
            or row.aggregate_id != event.aggregate_id
            or row.aggregate_type != event.aggregate_type
            or row.correlation_id != event.correlation_id
            or row.causation_id != event.causation_id
            or row.payload_digest != digest
        ):
            raise ExecutionIntegrationConflictError(
                "output outbox envelope conflicts with its durable payload"
            )
        return event

    async def _lock_output_then_run(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
    ) -> tuple[AgentRunModel, ExecutionOutboxModel]:
        if event_id is None and run_id is None:
            raise ValueError("event_id or run_id is required")
        statement = select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.tenant_id == tenant_id,
            ExecutionOutboxModel.event_type
            == ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1,
        )
        if event_id is not None:
            statement = statement.where(ExecutionOutboxModel.id == event_id)
        if run_id is not None:
            statement = statement.where(ExecutionOutboxModel.aggregate_id == run_id)
        row = (
            await self._session.execute(statement.with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise ExecutionIntegrationConflictError("output outbox event not found")
        run = (
            await self._session.execute(
                select(AgentRunModel)
                .where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.id == row.aggregate_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if run is None:
            raise ExecutionIntegrationConflictError("output Run not found")
        self.parse_publish_event(row)
        return run, row

    @staticmethod
    def _validate_turn_inbox(
        row: ExecutionInboxModel,
        *,
        event: TurnRequestedV1,
        payload_digest: str,
    ) -> None:
        if (
            row.event_type != TURN_REQUESTED_V1
            or row.schema_version != event.schema_version
            or row.payload_digest != payload_digest
            or row.correlation_id != event.correlation_id
            or row.causation_id != event.causation_id
        ):
            raise ExecutionIntegrationConflictError(
                "turn inbox replay conflicts with its durable receipt"
            )
