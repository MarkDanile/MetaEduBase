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
from app.contexts.agent_execution.domain import (
    AgentRun,
    LateOutputReadRejectedError,
)
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
from app.contexts.agent_workspace.domain.erasure import (
    ErasureFence,
    ErasureFenceState,
)
from app.contexts.agent_workspace.domain.errors import (
    ConversationNotFoundError,
    LateBodyWriteRejectedError,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
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


@dataclass(frozen=True, slots=True)
class ConsumeEpochVerdict:
    """R1-S4-C（S4-C C3/R4）：消费时点的 epoch 分类（deterministic outcome）。

    - ``normal``：producer epoch == 当前且 fence active -> 正常消费。
    - ``stale``：producer epoch < 当前且 fence 非 active（purge 已推进）-> 迟到
      写，Tx1 tombstone 证据 + Tx2 终态化，**不**登记 ledger。
    - ``unknown``：producer epoch 缺失（历史 NULL 行）-> Tx1 inbox rejected +
      tombstone 证据 + ledger ``epoch_unresolvable`` + Tx2 终态化。
    - ``data_anomaly``：producer epoch > 当前（fence 对齐窗口制造）-> fail
      closed，不消费、不登记（C3）。
    """

    kind: str  # normal | stale | unknown | data_anomaly
    current_purge_revision: int


def classify_consume_epoch(
    *,
    producer_purge_revision: int | None,
    current_purge_revision: int,
    fence_state: ErasureFenceState,
) -> ConsumeEpochVerdict:
    """按契约 R4 分类消费 epoch（Guard + Conversation 行锁后、fence 裁决处）。

    stale 判定须同时看 fence 状态：仅当 fence erasing/erased（purge 已推进）才
    stale；soft-delete（SCHEDULED）/restore 推进 token 但 fence 仍 active 时，
    pre-existing 事件**不得**仅因 token 推进被 tombstone（R4 carve-out）。
    """
    if producer_purge_revision is None:
        return ConsumeEpochVerdict(kind="unknown", current_purge_revision=current_purge_revision)
    if producer_purge_revision > current_purge_revision:
        return ConsumeEpochVerdict(
            kind="data_anomaly", current_purge_revision=current_purge_revision
        )
    if producer_purge_revision < current_purge_revision:
        # 仅 fence 非 active（purge 进行中/已完成）才 stale；fence active
        # （soft-delete/restore）视为 normal（R4）。
        if fence_state not in {ErasureFenceState.ERASING, ErasureFenceState.ERASED}:
            return ConsumeEpochVerdict(kind="normal", current_purge_revision=current_purge_revision)
        return ConsumeEpochVerdict(kind="stale", current_purge_revision=current_purge_revision)
    return ConsumeEpochVerdict(kind="normal", current_purge_revision=current_purge_revision)


def conversation_guard_key(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> int:
    material = tenant_id.bytes + conversation_id.bytes
    return int.from_bytes(hashlib.sha256(material).digest()[:8], byteorder="big", signed=True)


class WorkspaceRunStartBarrier:
    """R1-S3-C round-7 commit-14：start barrier 仅校验 actor + queue_seq。

    ``can_start_run`` 内部仍调 ``lock_owned_conversation``——caller（commit-6
    修复后）已在 Guard + Conv 行锁内，同事务内 SELECT FOR UPDATE 同 row 是
    reentrant（同 row 加 FOR UPDATE 多次不阻塞，已持锁事务可重取），不
    引起 lock-on-lock；但 ``can_start_run`` 的二次取锁在事务日志里留下
    痕迹。计划 S3-D 阶段把 ``can_start_run`` 拆为 ``can_start_check``（无锁）
    + ``lock_owned_conversation``（caller 持锁调用），本次保留二次锁但
    docstring 明确语义，避免误判"重复锁"为 AB-BA 风险。
    """

    def __init__(self, workspace: AgentWorkspaceBridgeService, *, actor_id: uuid.UUID):
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

    async def _conversation_epoch_state(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> tuple[int, str]:
        """Guard + Conversation 行锁内读当前 purge_revision + purge_state。

        R1-S4-C（S4-C C3/R4）：epoch 分类用 Conversation 当前 purge_revision
        （行锁内读，非 fence 对齐值）。调用方已持 Guard + Conversation 行锁，
        此处重读同值不新增锁。
        """
        row = (
            await self._session.execute(
                select(
                    ConversationModel.purge_revision,
                    ConversationModel.purge_state,
                ).where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise ConversationNotFoundError(
                f"conversation {conversation_id} not found for epoch verdict"
            )
        return int(row[0]), str(row[1])

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
    ) -> tuple[AgentRun, InboxAckV1, bool, ErasureFence]:
        """R1-S3-C round-7 commit-18：verdict 内建（不再 callback 参数）。

        Guard + Conversation 行锁内、writer commit 前调
        ``FencedExecutionPort.require_active_fence``（unconditional，create
        AND replay 都走 verdict）；erasing/erased fence raise
        ``LateBodyWriteRejectedError``。返回 fence 对象供 caller 在
        ``created=True`` 时 ``advance_checkpoint``。
        """
        from app.composition.execution_fenced_port import FencedExecutionPort

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
        # verdict-before-writer unconditional（commit-1 恢复 Conv FOR UPDATE
        # 后，verdict 在 Guard + Conv 行锁内调 owner lock + fence FOR UPDATE
        # 不再与 fenced_* writer 形成 2-way deadlock）。
        fence = await FencedExecutionPort(self._session).require_active_fence(
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
        return run, ack, created, fence

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

        run = await RunCoordinator(self._session).require_run(tenant_id=tenant_id, run_id=run_id)
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
        barrier = WorkspaceRunStartBarrier(self._workspace, actor_id=run.created_by_or_raise)
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
            raise ConversationHasNonTerminalRunError("Conversation has a non-terminal Agent Run")
        # 裁决时间必须在 Guard + Conversation 行锁之后采样；生产默认读数据库
        # clock_timestamp（测试经 now 注入）。deleted_at 与 purge_after 同源
        # （purge_after = deleted_at + 30 天恢复窗口，Spec §3）。
        effective_now = now
        if effective_now is None:
            effective_now = await self._session.scalar(select(func.clock_timestamp()))
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
        accepted = await self._execution.has_turn_acceptance(event, payload_digest=payload_digest)
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
        event, _ = await self._execution.require_publish_event(tenant_id=tenant_id, run_id=run_id)
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

    async def dispatch_turn(self, *, event_id: uuid.UUID | None = None) -> AgentRun | None:
        claimed = await self._claim_turn(event_id=event_id)
        if claimed is None:
            return None
        if isinstance(claimed, PoisonedWorkspaceEvent):
            raise PoisonedIntegrationEventError(
                f"workspace event {claimed.event_id} was quarantined: {claimed.error_code}"
            )
        try:
            # R1-S3-C round-7 commit-18：verdict 内建于 consume_turn_event
            # （不再 callback 参数）。create AND replay 都走 fence 裁决；
            # advance 仅 ``created=True`` 时调。
            from app.composition.execution_fenced_port import FencedExecutionPort

            async with self._session_factory() as session, session.begin():
                port = FencedExecutionPort(session)
                run, ack, created, fence = await ConversationExecutionCoordinator(
                    session
                ).consume_turn_event(
                    claimed,
                    consumed_at=datetime.now(UTC),
                )
                if created:
                    await port.advance_checkpoint(
                        fence=fence,
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

    async def dispatch_output(self, *, event_id: uuid.UUID | None = None) -> bool:
        claimed = await self._claim_output(event_id=event_id)
        if claimed is None:
            return False
        if isinstance(claimed, PoisonedExecutionEvent):
            raise PoisonedIntegrationEventError(
                f"execution event {claimed.event_id} was quarantined: {claimed.error_code}"
            )
        try:
            async with self._session_factory() as session, session.begin():
                ack = await ConversationExecutionCoordinator(
                    session, output_reader=self._output_reader
                ).consume_output_event(claimed, consumed_at=datetime.now(UTC))
            async with self._session_factory() as session, session.begin():
                await AgentExecutionBridgeService(session).acknowledge_output(ack)
            return True
        except (LateBodyWriteRejectedError, LateOutputReadRejectedError):
            # R1-S3-E §8：purge 拦截的迟到 publish 是 deterministic 结果（重试永远
            # 无法写入正文，R1-AC8 不盲重试正文写）。两类来源统一处理：
            # - ``LateBodyWriteRejectedError``：workspace.core.v1 fence 非 active
            #   （project_assistant_message 裁决）。
            # - ``LateOutputReadRejectedError``（round-2）：terminal/compatibility
            #   正文已被 purge 清除，迟到 publish 在 fence 裁决前的 terminal-read
            #   阶段即无法读取正文。
            # 不排 next_attempt_at 重试、不走 backoff，直接把 outbox 事件转为不可
            # 重试终态（row.status=cancelled + Run.output_publish_state=suppressed +
            # decision_reason=late_body_write_rejected + decision_digest），并清零
            # 在途 claim。不清 transport owner 正文（payload_* 归 S4）。
            await self._record_output_late_write_rejected(claimed=claimed)
            raise
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
                stale_before=database_now - timedelta(seconds=self._policy.claim_timeout_seconds),
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
                stale_before=database_now - timedelta(seconds=self._policy.claim_timeout_seconds),
                event_id=event_id,
            )

    async def _record_turn_failure(self, *, claimed: ClaimedWorkspaceEvent, exc: Exception) -> None:
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

    async def _record_output_late_write_rejected(self, *, claimed: ClaimedExecutionEvent) -> None:
        """R1-S3-E §8：把 purge 拦截的迟到 publish 落为 deterministic 终态。

        与 ``_record_output_failure``（transient，排 next_attempt_at backoff 重试）
        相对：本路径**不重试**，直接把 outbox 事件转为不可重试终态并清零在途 claim。
        round-1 P2：传完整 claim 身份（event_id/payload_digest/attempt_count/
        claimant_id）做 CAS，过期 worker 不得覆盖后来 worker 的 claim 或人工裁决。
        """
        async with self._session_factory() as session, session.begin():
            await AgentExecutionBridgeService(session).mark_output_late_write_rejected(
                tenant_id=claimed.event.tenant_id,
                event_id=claimed.event.event_id,
                payload_digest=claimed.payload_digest,
                expected_attempt=claimed.attempt_count,
                claimant_id=claimed.claimant_id,
                decided_at=datetime.now(UTC),
            )

    def _backoff(self, attempt_count: int) -> timedelta:
        seconds = min(
            self._policy.max_backoff_seconds,
            2 ** min(max(attempt_count, 1), 16),
        )
        return timedelta(seconds=seconds)
