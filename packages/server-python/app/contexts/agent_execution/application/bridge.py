from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import CreateRunCommand
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    AgentRun,
    ExecutionIntegrationConflictError,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RuntimeCapabilitySnapshot,
    SnapshotClassification,
)
from app.contexts.agent_execution.infrastructure.bridge_repository import (
    ExecutionBridgeRepository,
)
from app.shared.schemas.agent_integration import (
    AssistantMessagePublishRequestedV1,
    InboxAckV1,
    TurnRequestedV1,
)
from app.shared.schemas.agent_integration_codec import integration_event_digest


@dataclass(frozen=True, slots=True)
class ClaimedExecutionEvent:
    event: AssistantMessagePublishRequestedV1
    payload_digest: str
    attempt_count: int
    claimant_id: str


@dataclass(frozen=True, slots=True)
class PoisonedExecutionEvent:
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    run_id: uuid.UUID
    error_code: str


class AgentExecutionBridgeService:
    """Execution application port for the B1 control-plane composition root."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._bridge_repo = ExecutionBridgeRepository(session)
        self._runs = RunCoordinator(session)

    async def consume_turn_requested(
        self,
        *,
        event: TurnRequestedV1,
        payload_digest: str,
        delivery_attempt: int,
        claimant_id: str,
        consumed_at: datetime,
    ) -> tuple[AgentRun, InboxAckV1]:
        if integration_event_digest(event) != payload_digest:
            raise ExecutionIntegrationConflictError("turn payload digest conflicts")
        should_create = await self._bridge_repo.begin_turn_receipt(
            event=event, payload_digest=payload_digest
        )
        if should_create:
            launch = event.launch
            result = await self._runs.create_run(
                CreateRunCommand(
                    run_id=event.run_id,
                    tenant_id=event.tenant_id,
                    conversation_id=event.conversation_id,
                    queue_seq=event.queue_seq,
                    root_input_message_id=event.message_id,
                    root_request_id=event.root_request_id,
                    root_context_digest=event.root_context_digest,
                    parent_run_id=launch.parent_run_id,
                    agent_definition_version_id=launch.agent_definition_version_id,
                    runtime_profile_id=launch.runtime_profile_id,
                    runtime_binding_id=launch.runtime_binding_id,
                    runtime_capability_snapshot=(
                        RuntimeCapabilitySnapshot.model_validate(
                            launch.runtime_capability_snapshot.model_dump(mode="json")
                        )
                    ),
                    run_config_snapshot=RunConfigSnapshot.model_validate(
                        launch.run_config_snapshot.model_dump(mode="json")
                    ),
                    context_snapshot_ref=launch.context_snapshot_ref,
                    context_snapshot_digest=launch.context_snapshot_digest,
                    context_snapshot_classification=(
                        SnapshotClassification(
                            launch.context_snapshot_classification
                        )
                        if launch.context_snapshot_classification is not None
                        else None
                    ),
                    budget_snapshot=RunBudgetSnapshot.model_validate(
                        launch.budget_snapshot.model_dump(mode="json")
                    ),
                    created_by=event.created_by,
                    correlation_id=event.correlation_id,
                )
            )
            run = result.run
            await self._bridge_repo.consume_turn_receipt(
                event=event, consumed_at=consumed_at
            )
        else:
            run = await self._runs.require_run(
                tenant_id=event.tenant_id, run_id=event.run_id
            )
            if not await self._bridge_repo.has_turn_acceptance(
                event, payload_digest=payload_digest
            ):
                raise ExecutionIntegrationConflictError(
                    "consumed turn receipt is missing its persisted Run"
                )
        return run, InboxAckV1(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            consumer_name="agent_execution.turn_requested.v1",
            payload_digest=payload_digest,
            delivery_attempt=delivery_attempt,
            claimant_id=claimant_id,
            consumed_at=consumed_at,
        )

    async def has_turn_acceptance(
        self, event: TurnRequestedV1, *, payload_digest: str
    ) -> bool:
        return await self._bridge_repo.has_turn_acceptance(
            event, payload_digest=payload_digest
        )

    async def has_non_terminal_run(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        return await self._bridge_repo.has_non_terminal_run(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

    async def claim_output_event(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        event_id: uuid.UUID | None = None,
    ) -> ClaimedExecutionEvent | PoisonedExecutionEvent | None:
        result = await self._bridge_repo.claim_output_outbox(
            worker_id=worker_id,
            now=now,
            stale_before=stale_before,
            event_id=event_id,
        )
        if result is None:
            return None
        row, event = result
        if event is None:
            return PoisonedExecutionEvent(
                tenant_id=row.tenant_id,
                event_id=row.id,
                run_id=row.aggregate_id,
                error_code=row.last_error_code or "invalid_event_envelope",
            )
        assert row.claimed_by is not None
        return ClaimedExecutionEvent(
            event=event,
            payload_digest=row.payload_digest,
            attempt_count=row.attempt_count,
            claimant_id=row.claimed_by,
        )

    async def acknowledge_output(self, ack: InboxAckV1) -> None:
        await self._bridge_repo.acknowledge_output(ack=ack)

    async def validate_output_claim(
        self, claimed: ClaimedExecutionEvent
    ) -> None:
        await self._bridge_repo.validate_output_claim(
            tenant_id=claimed.event.tenant_id,
            event_id=claimed.event.event_id,
            payload_digest=claimed.payload_digest,
            expected_attempt=claimed.attempt_count,
            claimant_id=claimed.claimant_id,
        )

    async def record_output_failure(
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
        return await self._bridge_repo.record_output_delivery_failure(
            tenant_id=tenant_id,
            event_id=event_id,
            payload_digest=payload_digest,
            error_code=error_code,
            next_attempt_at=next_attempt_at,
            max_attempts=max_attempts,
            expected_attempt=expected_attempt,
            claimant_id=claimant_id,
        )

    async def reconcile_output_published(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        published_at: datetime,
    ) -> None:
        await self._bridge_repo.reconcile_output_published(
            tenant_id=tenant_id,
            event_id=event_id,
            payload_digest=payload_digest,
            published_at=published_at,
        )

    async def retry_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime,
    ) -> None:
        await self._bridge_repo.retry_output_projection(
            tenant_id=tenant_id, run_id=run_id, now=now
        )

    async def requeue_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime,
    ) -> None:
        await self._bridge_repo.requeue_output_projection(
            tenant_id=tenant_id, run_id=run_id, now=now
        )

    async def suppress_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        decided_at: datetime,
    ) -> None:
        await self._bridge_repo.suppress_output_projection(
            tenant_id=tenant_id,
            run_id=run_id,
            actor_id=actor_id,
            reason=reason,
            decided_at=decided_at,
        )

    async def require_publish_event(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[AssistantMessagePublishRequestedV1, str]:
        row = await self._bridge_repo.require_publish_outbox(
            tenant_id=tenant_id, run_id=run_id
        )
        return self._bridge_repo.parse_publish_event(row), row.payload_digest
