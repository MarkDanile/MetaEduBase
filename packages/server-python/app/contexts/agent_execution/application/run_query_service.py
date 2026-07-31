from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import EventReplayBatch
from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_POLICY_VERSION,
)
from app.contexts.agent_execution.application.ports import (
    ConversationAccessDecision,
    RunConversationAccessPort,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    AgentRun,
    EventCursorAheadError,
    EventGapDetectedError,
    EventHistoryExpiredError,
    RunActorAnonymizedError,
    RunNotFoundError,
    RunStatus,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.execution_query_repository import (
    AgentExecutionQueryRepository,
)


class RunQueryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        conversation_access: RunConversationAccessPort,
    ):
        self._repository = AgentExecutionQueryRepository(session)
        self._coordinator = RunCoordinator(session)
        self._conversation_access = conversation_access
        self._session = session

    async def get_run(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> AgentRun:
        run, _ = await self._require_run_access(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
        )
        # S3-B round-4 P2-1：tombstone Run 不能被 read/cancel/replay 返回（actor 已匿名化）。
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone); "
                "live actor required"
            )
        return run

    async def request_cancel(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
    ) -> AgentRun:
        run, access = await self._require_run_access(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
        )
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone); "
                "live actor required"
            )
        if not access.can_cancel:
            raise RunNotFoundError("Agent Run not found")
        current, reserved = await self._coordinator.reserve_cancel_intent(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_revision=expected_revision,
        )
        if not reserved or current.status is RunStatus.CANCELLING:
            return current
        if current.run_config_snapshot.policy_version == DIRECT_RAG_POLICY_VERSION:
            if current.status in {RunStatus.QUEUED, RunStatus.RESUME_REQUIRED}:
                cancelled, _, _ = await self._coordinator.commit_terminal(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    expected_status=current.status,
                    expected_revision=current.status_revision,
                    result=TerminalResult(
                        outcome="cancelled",
                        code="direct_rag_cancelled",
                        reason="Legacy Direct RAG compatibility request was cancelled",
                    ),
                )
                return cancelled
            cancelling, _ = await self._coordinator.transition_run(
                tenant_id=tenant_id,
                run_id=run_id,
                expected_status=current.status,
                expected_revision=current.status_revision,
                target_status=RunStatus.CANCELLING,
                summary="Cancelling legacy Direct RAG compatibility request",
            )
            cancelled, _, _ = await self._coordinator.commit_terminal(
                tenant_id=tenant_id,
                run_id=run_id,
                expected_status=RunStatus.CANCELLING,
                expected_revision=cancelling.status_revision,
                result=TerminalResult(
                    outcome="cancelled",
                    code="direct_rag_cancelled",
                    reason="Legacy Direct RAG compatibility request was cancelled",
                ),
            )
            return cancelled
        if current.status in {RunStatus.QUEUED, RunStatus.RESUME_REQUIRED}:
            cancelled, _, _ = await self._coordinator.commit_terminal(
                tenant_id=tenant_id,
                run_id=run_id,
                expected_status=current.status,
                expected_revision=expected_revision,
                result=TerminalResult(
                    outcome="cancelled",
                    code="user_cancel_requested",
                    reason="Cancellation requested by the conversation owner",
                ),
            )
            return cancelled
        cancelling, _ = await self._coordinator.transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=current.status,
            expected_revision=expected_revision,
            target_status=RunStatus.CANCELLING,
            summary="Cancellation requested by the conversation owner",
        )
        return cancelling

    async def read_event_batch(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
        after_seq: int,
        limit: int = 100,
        validate_full_range: bool = False,
    ) -> EventReplayBatch:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if not 1 <= limit <= 500:
            raise ValueError("event replay limit must be between 1 and 500")
        run, access = await self._require_run_access(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
        )
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone); "
                "live actor required"
            )
        window = await self._repository.read_event_replay_window(
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq=after_seq,
            limit=limit,
            validate_full_range=validate_full_range,
        )
        if window is None or window.run.conversation_id != run.conversation_id:
            raise RunNotFoundError("Agent Run not found")
        current = window.run
        if after_seq < current.first_available_event_seq - 1:
            if current.event_log_complete:
                raise EventGapDetectedError(
                    expected_seq=after_seq + 1,
                    received_seq=current.first_available_event_seq,
                )
            raise EventHistoryExpiredError(
                first_available_event_seq=current.first_available_event_seq,
                run_status=current.status.value,
                event_log_complete=current.event_log_complete,
            )
        if after_seq > current.last_event_seq:
            raise EventCursorAheadError(
                after_seq=after_seq,
                last_event_seq=current.last_event_seq,
            )
        expected_seq = after_seq + 1
        for event in window.events:
            if event.seq != expected_seq:
                raise EventGapDetectedError(
                    expected_seq=expected_seq,
                    received_seq=event.seq,
                )
            expected_seq += 1
        if len(window.events) < limit and expected_seq <= current.last_event_seq:
            raise EventGapDetectedError(
                expected_seq=expected_seq,
                received_seq=None,
            )
        return EventReplayBatch(
            run=current,
            events=window.events,
            access=access,
            after_seq=after_seq,
        )

    async def _require_run_access(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> tuple[AgentRun, ConversationAccessDecision]:
        run = await self._repository.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise RunNotFoundError("Agent Run not found")
        access = await self._conversation_access.resolve(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=run.conversation_id,
        )
        if access is None:
            raise RunNotFoundError("Agent Run not found")
        return run, access
