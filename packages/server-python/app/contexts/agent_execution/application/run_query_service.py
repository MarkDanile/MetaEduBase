from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import EventReplayBatch
from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_POLICY_VERSION,
)
from app.contexts.agent_execution.application.ports import (
    ConversationAccessDecision,
    FencedWriterPort,
    GuardLockPort,
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
    RunRevisionConflictError,
    RunStatus,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.execution_query_repository import (
    AgentExecutionQueryRepository,
)
from app.contexts.agent_workspace.application.ports import WorkspaceReadPort


class RunQueryService:
    """R1-S3-C round-7 commit-12：跨边界协议注入（必填）。

    三个依赖（Guard、Conversation row lock、fenced writer）都是必填本地
    Protocol。production 在 composition 层组装实现（``build_run_query_service``）；
    单测可注入 mock。不接受任何无锁 fallback——conversation row lock 必填
    保证 Spec §6.1 锁序。
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        conversation_access: RunConversationAccessPort,
        workspace_read: WorkspaceReadPort,
        guard: GuardLockPort,
        fenced_writer: FencedWriterPort,
    ):
        self._session = session
        self._repository = AgentExecutionQueryRepository(session)
        self._coordinator = RunCoordinator(session)
        self._conversation_access = conversation_access
        self._workspace_read = workspace_read
        self._guard = guard
        self._fenced_writer = fenced_writer

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
        # R1-S3-C round-7 commit-17（P1-2）：Guard 必须前置于 access resolution。
        # round-7 commit-5/11 的顺序 ``_require_run_access``（含
        # ``share_owned_conversation FOR SHARE``）-> ``Guard.acquire`` ->
        # ``lock_owned_conversation FOR UPDATE`` 与 delete 路径
        # ``Guard -> Conversation FOR UPDATE`` 形成 AB-BA
        # （Conv SHARE -> Guard vs Guard -> Conv UPDATE）。修复：先读-only
        # 拿 conversation_id，再 Guard，再 access resolve（SHARE 在 Guard 内），
        # 再 Conv FOR UPDATE，再锁后重读 Run（authoritative），再 fenced writer。
        run = await self._repository.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise RunNotFoundError("Agent Run not found")
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
        )
        access = await self._conversation_access.resolve(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=run.conversation_id,
        )
        if access is None:
            raise RunNotFoundError("Agent Run not found")
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone); "
                "live actor required"
            )
        if not access.can_cancel:
            raise RunNotFoundError("Agent Run not found")
        await self._workspace_read.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=run.conversation_id,
            include_deleted=False,
        )
        # 锁后重读 Run（authoritative snapshot）。round-7 commit-11 之前的
        # early-return ``if run.status is CANCELLING: return run`` 用锁前旧
        # 快照，可能返回旧状态或让同 revision 并发 cancel 错误变成 revision
        # conflict。现重读后做权威幂等检查：
        # - cancel_requested_revision == expected_revision -> 幂等返回（已记录）
        # - cancel_requested_revision != expected_revision -> RunRevisionConflictError
        # - 无 cancel intent -> 走 fenced writer（writer 内 FOR UPDATE + CAS 写入）
        run = await self._repository.get_run(tenant_id=tenant_id, run_id=run_id)
        assert run is not None  # lock_owned_conversation 已保证 Conversation 存在
        # R1-S3-C round-7 commit-20（P1）：锁后权威重读必须重新校验 tombstone。
        # 等待 Guard 期间 Run 可能被 purge 匿名化（created_by -> None,
        # actor_state -> redacted）。pre-lock 快照的 tombstone 校验（line 112）
        # 用旧快照，漏掉 present -> 等锁 -> redacted 竞态。此处权威重读后
        # 再校验，确保 anonymized Run 不进入 fenced cancel writer。
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone) "
                "during cancel; live actor required"
            )
        if run.cancel_requested_revision is not None:
            if run.cancel_requested_revision != expected_revision:
                raise RunRevisionConflictError(
                    "Agent Run cancel intent belongs to another revision"
                )
            return run  # 幂等：同 revision cancel intent 已记录（CANCELLING/CANCELLED）
        # caller 的 expected_revision 必须匹配当前 status_revision（authoritative）。
        # 若 run 已被并发推进（如 start_run），caller 的 stale revision -> conflict。
        # 等价于原 ``reserve_cancel_intent`` 的 ``status_revision != expected_revision`` 校验。
        if run.status_revision != expected_revision:
            raise RunRevisionConflictError(
                "Agent Run cancel revision precondition failed"
            )

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
