from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contexts.agent_execution.application.bridge import (
    AgentExecutionBridgeService,
    ClaimedExecutionEvent,
    PoisonedExecutionEvent,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import AgentRun
from app.contexts.agent_workspace.application.bridge import (
    AgentWorkspaceBridgeService,
    ClaimedWorkspaceEvent,
    PoisonedWorkspaceEvent,
    SubmitTurnReceipt,
)
from app.contexts.agent_workspace.application.dto import TurnCommand
from app.contexts.agent_workspace.application.ports import (
    ResourceReferenceAccessPort,
    TerminalOutputReaderPort,
)
from app.contexts.agent_workspace.domain import Conversation, TurnDispatchState
from app.shared.schemas.agent_integration import InboxAckV1, TurnLaunchSpecV1


class AgentControlPlaneError(Exception):
    """Base class for stable composition-layer command failures."""


class ConversationHasPendingTurnError(AgentControlPlaneError):
    pass


class ConversationHasNonTerminalRunError(AgentControlPlaneError):
    pass


class ExecutionPortUnavailableError(AgentControlPlaneError):
    pass


class PoisonedIntegrationEventError(AgentControlPlaneError):
    pass


class ConversationExecutionGuard:
    """Transaction-scoped serialization for one tenant Conversation."""

    async def acquire(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        key = conversation_guard_key(tenant_id, conversation_id)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:guard_key)"),
            {"guard_key": key},
        )


def conversation_guard_key(
    tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> int:
    material = tenant_id.bytes + conversation_id.bytes
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


class WorkspaceRunStartBarrier:
    """R1-S3-C round-7 commit-6：start barrier 仅校验 actor + queue_seq。

    ``can_start_run`` 内部仍调 ``lock_owned_conversation``，但 caller
    （``ConversationExecutionCoordinator.start_run``）已在 Guard + Conv 行锁
    内；同事务内 SELECT FOR UPDATE 同 row 是 reentrant，无 lock-on-lock。
    """

    def __init__(
        self, workspace: AgentWorkspaceBridgeService, *, actor_id: uuid.UUID
    ):
        self._workspace = workspace
        self._actor_id = actor_id

    async def can_start(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool:
        return await self._workspace.can_start_run(
            tenant_id=tenant_id,
            actor_id=self._actor_id,
            conversation_id=conversation_id,
            run_id=run_id,
            queue_seq=queue_seq,
        )


class ConversationExecutionCoordinator:
    """Single-transaction B1 coordination over bounded-context application ports."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        guard: ConversationExecutionGuard | None = None,
        output_reader: TerminalOutputReaderPort | None = None,
        resource_access: ResourceReferenceAccessPort | None = None,
    ):
        self._session = session
        self._guard = guard or ConversationExecutionGuard()
        self._workspace = AgentWorkspaceBridgeService(
            session,
            output_reader=output_reader,
            resource_access=resource_access,
        )
        self._execution = AgentExecutionBridgeService(session)

    async def submit_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        command: TurnCommand,
        launch: TurnLaunchSpecV1,
    ) -> SubmitTurnReceipt:
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        return await self._workspace.submit_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=command,
            launch=launch,
        )

    async def consume_turn_event(
        self,
        claimed: ClaimedWorkspaceEvent,
        *,
        consumed_at: datetime,
        pre_create_callback,  # 必填：S3-C round-7 强制 verdict 无条件
    ) -> tuple[AgentRun, InboxAckV1, bool]:
        event = claimed.event
        await self._guard.acquire(
            self._session,
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=event.tenant_id,
            actor_id=event.created_by,
            conversation_id=event.conversation_id,
            include_deleted=False,
        )
        await self._workspace.validate_turn_claim(claimed)
        # R1-S3-C round-7：verdict-before-writer unconditional。pre_create_callback
        # 必填，create AND replay 都走 fence 裁决（Guard + Conversation 行锁
        # 已持）；erasing/erased fence raise LateBodyWriteRejectedError（replay
        # 不允许 ACK downstream）。advance 仅 created=True 时调（caller 侧）。
        #
        # 锁环修复（commit 1）：``advance_ingress_checkpoint_for_update`` 已
        # 恢复 Conversation FOR UPDATE，verdict 在 Guard + Conversation 行锁
        # 内调 owner lock + fence FOR UPDATE 不再与 fenced_* writer 形成
        # 2-way deadlock（writer 的 advance 现在用 caller 已持的 Conv 行锁）。
        await pre_create_callback(
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
        )
        run, ack, created = await self._execution.consume_turn_requested(
            event=event,
            payload_digest=claimed.payload_digest,
            delivery_attempt=claimed.attempt_count,
            claimant_id=claimed.claimant_id,
            consumed_at=consumed_at,
        )
        return run, ack, created

    async def start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
    ):
        # R1-S3-C round-7 commit-6：start_run 锁序修复。原顺序 Guard ->
        # fenced_start_run（owner -> fence -> start_barrier can_start_run 取
        # Conv row），违反 Spec §6.1（Guard -> Conv -> owner -> fence）。
        # 现顺序 Guard -> lock_owned_conversation -> fenced_start_run；
        # WorkspaceRunStartBarrier.can_start_run 通过 actor/queue 校验（不再
        # 二次取 Conv 行锁，避免 lock-on-lock）。
        from app.composition.execution_fenced_port import FencedExecutionPort

        run = await RunCoordinator(self._session).require_run(
            tenant_id=tenant_id, run_id=run_id
        )
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=run.created_by_or_raise,
            conversation_id=run.conversation_id,
            include_deleted=False,
        )
        port = FencedExecutionPort(self._session)
        barrier = WorkspaceRunStartBarrier(
            self._workspace, actor_id=run.created_by_or_raise
        )
        return await port.fenced_start_run(
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
            run_id=run_id,
            expected_revision=expected_revision,
            start_barrier=barrier,
        )

    async def consume_output_event(
        self,
        claimed: ClaimedExecutionEvent,
        *,
        consumed_at: datetime,
    ) -> InboxAckV1:
        event = claimed.event
        await self._guard.acquire(
            self._session,
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
        )
        await self._workspace.lock_output_conversation(event)
        await self._execution.validate_output_claim(claimed)
        return await self._workspace.consume_assistant_publish(
            event=event,
            payload_digest=claimed.payload_digest,
            delivery_attempt=claimed.attempt_count,
            claimant_id=claimed.claimant_id,
            consumed_at=consumed_at,
        )

    async def delete_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        now: datetime | None = None,
    ) -> Conversation:
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=False,
        )
        if await self._workspace.has_unacknowledged_turn(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            raise ConversationHasPendingTurnError(
                "Conversation has a turn that execution has not acknowledged"
            )
        try:
            has_non_terminal = await self._execution.has_non_terminal_run(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
        except SQLAlchemyError as exc:
            raise ExecutionPortUnavailableError(
                "execution state is unavailable; deletion failed closed"
            ) from exc
        if has_non_terminal:
            raise ConversationHasNonTerminalRunError(
                "Conversation has a non-terminal Agent Run"
            )
        # 裁决时间必须在 Guard + Conversation 行锁之后采样；生产默认读数据库
        # clock_timestamp（测试经 now 注入）。deleted_at 与 purge_after 同源
        # （purge_after = deleted_at + 30 天恢复窗口，Spec §3）。
        effective_now = now
        if effective_now is None:
            effective_now = await self._session.scalar(
                select(func.clock_timestamp())
            )
            assert effective_now is not None
        return await self._workspace.soft_delete_after_guard(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
            purge_after=effective_now + timedelta(days=30),
            deleted_at=effective_now,
        )

    async def restore_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        now: datetime | None = None,
    ) -> Conversation:
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=True,
        )
        # 裁决时间在 bridge 内于 owner lock + fence FOR UPDATE 之后采样
        # （生产默认 DB clock_timestamp）；now 仅作测试注入透传。
        return await self._workspace.restore_after_guard(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
            now=now,
        )

    async def acquire_purge_preflight(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """Establish B1's purge lock order without performing R1 erasure."""
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=True,
        )

    async def retry_turn_dispatch(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        now: datetime | None = None,
    ) -> None:
        effective_now = now or datetime.now(UTC)
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        await self._workspace.retry_turn_dispatch(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            now=effective_now,
        )

    async def abandon_turn_dispatch(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        now: datetime | None = None,
    ) -> TurnDispatchState:
        effective_now = now or datetime.now(UTC)
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        event, payload_digest = await self._workspace.require_turn_event(
            tenant_id=tenant_id, message_id=message_id
        )
        accepted = await self._execution.has_turn_acceptance(
            event, payload_digest=payload_digest
        )
        return await self._workspace.abandon_or_reconcile_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            execution_accepted=accepted,
            now=effective_now,
        )

    async def retry_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime | None = None,
    ) -> None:
        event, _ = await self._execution.require_publish_event(
            tenant_id=tenant_id, run_id=run_id
        )
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=event.conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=event.conversation_id,
            include_deleted=True,
        )
        await self._execution.retry_output_projection(
            tenant_id=tenant_id,
            run_id=run_id,
            now=now or datetime.now(UTC),
        )

    async def reconcile_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
        now: datetime | None = None,
    ) -> bool:
        effective_now = now or datetime.now(UTC)
        event, payload_digest = await self._execution.require_publish_event(
            tenant_id=tenant_id, run_id=run_id
        )
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=event.conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=event.conversation_id,
            include_deleted=True,
        )
        projected = await self._workspace.output_is_projected(
            event=event, payload_digest=payload_digest
        )
        if projected:
            await self._execution.reconcile_output_published(
                tenant_id=tenant_id,
                event_id=event.event_id,
                payload_digest=payload_digest,
                published_at=effective_now,
            )
            return True
        await self._execution.requeue_output_projection(
            tenant_id=tenant_id, run_id=run_id, now=effective_now
        )
        return False

    async def suppress_output_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        run_id: uuid.UUID,
        reason: str,
        now: datetime | None = None,
    ) -> None:
        effective_now = now or datetime.now(UTC)
        event, payload_digest = await self._execution.require_publish_event(
            tenant_id=tenant_id, run_id=run_id
        )
        await self._guard.acquire(
            self._session,
            tenant_id=tenant_id,
            conversation_id=event.conversation_id,
        )
        await self._workspace.lock_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=event.conversation_id,
            include_deleted=True,
        )
        await self._workspace.suppress_assistant_publish(
            event=event,
            payload_digest=payload_digest,
            reason=reason,
            consumed_at=effective_now,
        )
        await self._execution.suppress_output_projection(
            tenant_id=tenant_id,
            run_id=run_id,
            actor_id=actor_id,
            reason=reason,
            decided_at=effective_now,
        )


@dataclass(frozen=True, slots=True)
class DispatchPolicy:
    claim_timeout_seconds: int = 60
    max_attempts: int = 5
    max_backoff_seconds: int = 300


class AgentBridgeDispatcher:
    """Claim, consume, and ACK integration events in separate transactions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        worker_id: str,
        output_reader: TerminalOutputReaderPort | None = None,
        policy: DispatchPolicy | None = None,
    ):
        self._session_factory = session_factory
        self._worker_id = worker_id
        self._output_reader = output_reader
        self._policy = policy or DispatchPolicy()

    async def dispatch_turn(
        self, *, event_id: uuid.UUID | None = None
    ) -> AgentRun | None:
        claimed = await self._claim_turn(event_id=event_id)
        if claimed is None:
            return None
        if isinstance(claimed, PoisonedWorkspaceEvent):
            raise PoisonedIntegrationEventError(
                f"workspace event {claimed.event_id} was quarantined: "
                f"{claimed.error_code}"
            )
        try:
            # R1-S3-C round-6：verdict-before-writer 无条件 + advance 按 created
            # 条件。``pre_create_callback`` 在 Guard + Conversation 行锁内、
            # writer commit 前执行 fence 裁决；create AND replay 都走 verdict
            # （erasing/erased fence raise，不 ACK downstream）。advance 仅
            # ``created=True`` 时调。
            #
            # 锁环修复（commit 1）：``advance_ingress_checkpoint_for_update`` 不再
            # 重取 Conversation 行锁，verdict 在 Guard + Conversation 行锁内调
            # owner lock + fence FOR UPDATE 不再与并发 fenced_* writer 死锁。
            from app.composition.execution_fenced_port import FencedExecutionPort

            async with self._session_factory() as session, session.begin():
                port = FencedExecutionPort(session)
                fence_holder: dict = {}

                async def _verdict(*, tenant_id, conversation_id):
                    fence_holder["fence"] = await port.require_active_fence(
                        tenant_id=tenant_id, conversation_id=conversation_id
                    )

                run, ack, created = await ConversationExecutionCoordinator(
                    session
                ).consume_turn_event(
                    claimed,
                    consumed_at=datetime.now(UTC),
                    pre_create_callback=_verdict,
                )
                if created:
                    await port.advance_checkpoint(
                        fence=fence_holder["fence"],
                        conversation_id=claimed.event.conversation_id,
                        source_key="run_context_body",
                        watermark=run.queue_seq,
                    )
            async with self._session_factory() as session, session.begin():
                await AgentWorkspaceBridgeService(session).acknowledge_turn(ack)
            return run
        except Exception as exc:
            await self._record_turn_failure(claimed=claimed, exc=exc)
            raise

    async def dispatch_output(
        self, *, event_id: uuid.UUID | None = None
    ) -> bool:
        claimed = await self._claim_output(event_id=event_id)
        if claimed is None:
            return False
        if isinstance(claimed, PoisonedExecutionEvent):
            raise PoisonedIntegrationEventError(
                f"execution event {claimed.event_id} was quarantined: "
                f"{claimed.error_code}"
            )
        try:
            async with self._session_factory() as session, session.begin():
                ack = await ConversationExecutionCoordinator(
                    session, output_reader=self._output_reader
                ).consume_output_event(claimed, consumed_at=datetime.now(UTC))
            async with self._session_factory() as session, session.begin():
                await AgentExecutionBridgeService(session).acknowledge_output(ack)
            return True
        except Exception as exc:
            await self._record_output_failure(claimed=claimed, exc=exc)
            raise

    async def _claim_turn(
        self, *, event_id: uuid.UUID | None
    ) -> ClaimedWorkspaceEvent | PoisonedWorkspaceEvent | None:
        async with self._session_factory() as session, session.begin():
            database_now = await session.scalar(select(func.clock_timestamp()))
            assert database_now is not None
            return await AgentWorkspaceBridgeService(session).claim_turn_event(
                worker_id=self._worker_id,
                now=database_now,
                stale_before=database_now
                - timedelta(seconds=self._policy.claim_timeout_seconds),
                event_id=event_id,
            )

    async def _claim_output(
        self, *, event_id: uuid.UUID | None
    ) -> ClaimedExecutionEvent | PoisonedExecutionEvent | None:
        async with self._session_factory() as session, session.begin():
            database_now = await session.scalar(select(func.clock_timestamp()))
            assert database_now is not None
            return await AgentExecutionBridgeService(session).claim_output_event(
                worker_id=self._worker_id,
                now=database_now,
                stale_before=database_now
                - timedelta(seconds=self._policy.claim_timeout_seconds),
                event_id=event_id,
            )

    async def _record_turn_failure(
        self, *, claimed: ClaimedWorkspaceEvent, exc: Exception
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await AgentWorkspaceBridgeService(session).record_turn_failure(
                tenant_id=claimed.event.tenant_id,
                event_id=claimed.event.event_id,
                payload_digest=claimed.payload_digest,
                error_code=type(exc).__name__,
                next_attempt_at=now + self._backoff(claimed.attempt_count),
                    max_attempts=self._policy.max_attempts,
                    expected_attempt=claimed.attempt_count,
                    claimant_id=claimed.claimant_id,
                )

    async def _record_output_failure(
        self, *, claimed: ClaimedExecutionEvent, exc: Exception
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await AgentExecutionBridgeService(session).record_output_failure(
                tenant_id=claimed.event.tenant_id,
                event_id=claimed.event.event_id,
                payload_digest=claimed.payload_digest,
                error_code=type(exc).__name__,
                next_attempt_at=now + self._backoff(claimed.attempt_count),
                    max_attempts=self._policy.max_attempts,
                    expected_attempt=claimed.attempt_count,
                    claimant_id=claimed.claimant_id,
                )

    def _backoff(self, attempt_count: int) -> timedelta:
        seconds = min(
            self._policy.max_backoff_seconds,
            2 ** min(max(attempt_count, 1), 16),
        )
        return timedelta(seconds=seconds)
