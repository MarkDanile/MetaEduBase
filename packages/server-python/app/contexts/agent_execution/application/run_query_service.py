from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_control_plane import ConversationExecutionGuard
from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_execution.application.dto import EventReplayBatch
from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_POLICY_VERSION,
)
from app.contexts.agent_execution.application.ports import (
    ConversationAccessDecision,
    FencedWriterPort,
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
from app.contexts.agent_workspace.application.ports import WorkspaceReadPort


class RunQueryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        conversation_access: RunConversationAccessPort,
        workspace_read: WorkspaceReadPort | None = None,
        fenced_writer: FencedWriterPort | None = None,
    ):
        self._session = session
        self._repository = AgentExecutionQueryRepository(session)
        self._coordinator = RunCoordinator(session)
        self._conversation_access = conversation_access
        # R1-S3-C round-7 commit-5：跨边界 protocol 依赖。默认从 composition
        # 实例化（用于生产）；单测可注入 mock。
        self._fenced_writer: FencedWriterPort = (
            fenced_writer if fenced_writer is not None
            else FencedExecutionPort(session)  # type: ignore[assignment]
        )
        # WorkspaceReadPort 提供 lock_owned_conversation（与 dispatch_turn /
        # delete_conversation 同路径），避免反向 import AgentWorkspaceBridgeService
        # 触发跨上下文违规。
        self._workspace_read: WorkspaceReadPort | None = workspace_read

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
        # R1-S3-C round-7 commit-5：取消 AB-BA 锁序。``request_cancel`` 之前先
        # 调 ``reserve_cancel_intent`` 锁 AgentRun FOR UPDATE，与 S3-D
        # ``Conversation -> owner/fence -> AgentRun`` 形成 AB-BA 死锁。现
        # 在 caller 侧严格持 Guard + Conv 行锁（与 ``delete_conversation``
        # 同序），cancel intent CAS 下推到 fenced_commit_terminal /
        # fenced_transition_run 内部 SQL（``cancel_intent_revision`` 参数）。
        # Writer 内部先取 ``_require_run_for_update`` 再做 CAS，锁链为：
        # ``Guard -> Conv row -> owner lock -> fence row -> AgentRun FOR UPDATE``。
        await ConversationExecutionGuard().acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
        )
        # Conv 行锁：复用 lock_owned_conversation（与 dispatch_turn /
        # delete_conversation 同路径）。通过 WorkspaceReadPort protocol 注入，
        # 避免反向 import AgentWorkspaceBridgeService 触发跨上下文违规。
        # 单测可传 None 跳过（绕开 lock_owned_conversation，依赖现有 fixture
        # 上下文）。
        if self._workspace_read is not None:
            await self._workspace_read.lock_owned_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=run.conversation_id,
                include_deleted=False,
            )

        if run.status is RunStatus.CANCELLING:
            return run

        if run.run_config_snapshot.policy_version == DIRECT_RAG_POLICY_VERSION:
            if run.status in {RunStatus.QUEUED, RunStatus.RESUME_REQUIRED}:
                cancelled, _, _ = await self._fenced_writer.fenced_commit_terminal(
                    tenant_id=tenant_id,
                    conversation_id=run.conversation_id,
                    run_id=run_id,
                    queue_seq=run.queue_seq,
                    expected_status=run.status,
                    expected_revision=run.status_revision,
                    result=TerminalResult(
                        outcome="cancelled",
                        code="direct_rag_cancelled",
                        reason="Legacy Direct RAG compatibility request was cancelled",
                    ),
                    cancel_intent_revision=expected_revision,
                )
                return cancelled
            cancelling, _ = await self._fenced_writer.fenced_transition_run(
                tenant_id=tenant_id,
                conversation_id=run.conversation_id,
                run_id=run_id,
                expected_status=run.status,
                expected_revision=run.status_revision,
                target_status=RunStatus.CANCELLING,
                summary="Cancelling legacy Direct RAG compatibility request",
                cancel_intent_revision=expected_revision,
            )
            cancelled, _, _ = await self._fenced_writer.fenced_commit_terminal(
                tenant_id=tenant_id,
                conversation_id=run.conversation_id,
                run_id=run_id,
                queue_seq=run.queue_seq,
                expected_status=RunStatus.CANCELLING,
                expected_revision=cancelling.status_revision,
                result=TerminalResult(
                    outcome="cancelled",
                    code="direct_rag_cancelled",
                    reason="Legacy Direct RAG compatibility request was cancelled",
                ),
                cancel_intent_revision=expected_revision,
            )
            return cancelled
        if run.status in {RunStatus.QUEUED, RunStatus.RESUME_REQUIRED}:
            cancelled, _, _ = await self._fenced_writer.fenced_commit_terminal(
                tenant_id=tenant_id,
                conversation_id=run.conversation_id,
                run_id=run_id,
                queue_seq=run.queue_seq,
                expected_status=run.status,
                expected_revision=expected_revision,
                result=TerminalResult(
                    outcome="cancelled",
                    code="user_cancel_requested",
                    reason="Cancellation requested by the conversation owner",
                ),
                cancel_intent_revision=expected_revision,
            )
            return cancelled
        cancelling, _ = await self._fenced_writer.fenced_transition_run(
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
            run_id=run_id,
            expected_status=run.status,
            expected_revision=expected_revision,
            target_status=RunStatus.CANCELLING,
            summary="Cancellation requested by the conversation owner",
            cancel_intent_revision=expected_revision,
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
