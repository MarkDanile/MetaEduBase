from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import owner_registry
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
    ConversationPurgedError,
    ConversationPurgeInProgressError,
    ConversationRestoreNotAllowedError,
    ErasureFence,
    ErasureFenceState,
    MessageContentState,
    MessagePartType,
    ResourceReferenceForbiddenError,
    TurnDispatchState,
    WorkspaceIntegrationConflictError,
)
from app.contexts.agent_workspace.infrastructure.bridge_repository import (
    WorkspaceBridgeRepository,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
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
    # R1-S4-C（S4-C C1 hop3）：claim 短事务内从 outbox 行锁定读取的
    # scope/epoch，供消费事务六元 CAS 比对（C3）。
    conversation_id: uuid.UUID | None
    producer_purge_revision: int | None


@dataclass(frozen=True, slots=True)
class PoisonedWorkspaceEvent:
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    error_code: str


def _require_restorable_fences(fences: Sequence[ErasureFence]) -> None:
    """restore 的 fence 集合裁决（Spec §3/§4.2，fail closed）。

    预期 owner 集合 = code-defined ``owner_registry()``（与 backfill 建的
    baseline fence 一一对应）。判定优先级（确定性，强信号优先）：

    - 任一 fence ``erased`` -> ConversationPurgedError（终态优先）；
    - 任一 fence ``blocked/erasing`` -> ConversationPurgeInProgressError；
    - 未知 owner fence、预期 fence 缺失、owner_version 漂移 ->
      ConversationRestoreNotAllowedError（没有查到 fence 不是隐式安全；
      缺失不视为安全，即使对从未建过 fence 的全新/历史会话也 fail closed）。
    """
    if any(fence.state is ErasureFenceState.ERASED for fence in fences):
        raise ConversationPurgedError(
            "conversation owner purge has completed; cannot be restored"
        )
    if any(
        fence.state in {ErasureFenceState.BLOCKED, ErasureFenceState.ERASING}
        for fence in fences
    ):
        raise ConversationPurgeInProgressError(
            "conversation owner purge is in progress or paused; "
            "cannot be restored"
        )
    expected = {owner.owner_key: owner for owner in owner_registry()}
    unknown = sorted(
        fence.owner_key for fence in fences if fence.owner_key not in expected
    )
    if unknown:
        raise ConversationRestoreNotAllowedError(
            f"conversation has erasure fences from unknown owners: {unknown}"
        )
    by_owner = {fence.owner_key: fence for fence in fences}
    missing = sorted(key for key in expected if key not in by_owner)
    if missing:
        raise ConversationRestoreNotAllowedError(
            "conversation erasure fence ledger is incomplete; "
            f"missing owners: {missing}"
        )
    drifted = sorted(
        owner_key
        for owner_key, fence in by_owner.items()
        if fence.owner_version != expected[owner_key].owner_version
    )
    if drifted:
        raise ConversationRestoreNotAllowedError(
            "conversation erasure fence owner version no longer matches the "
            f"installed registry: {drifted}"
        )


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
            # R1-S4-C（S4-C C1/C2）：outbox 新写带结构化 owner scope。epoch 必须是
            # 产生同事务、Conversation 行锁内读到的真实 purge_revision；禁拿
            # fence CAS revision/fence purge_revision/时间戳冒充（R1）。该行已被
            # reserve_user_turn 在同一事务 FOR UPDATE 锁住，此处重读同值不新增锁。
            conversation_row = await self._workspace_repo.get_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
            )
            if conversation_row is None:
                raise WorkspaceIntegrationConflictError(
                    "conversation disappeared during turn outbox write"
                )
            conversation, _ = conversation_row
            await self._bridge_repo.add_turn_outbox(
                event,
                conversation_id=conversation_id,
                producer_purge_revision=conversation.purge_revision,
            )
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
            # R1-S4-C（S4-C C1 hop3）：从 claim 短事务内 FOR UPDATE 锁定的
            # outbox 行装载 scope/epoch（非 NULL 成员供六元 CAS 比对）。
            conversation_id=row.conversation_id,
            producer_purge_revision=row.producer_purge_revision,
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
            # R1-S4-C（S4-C C3）：六元 CAS 追加 scope/epoch（非 NULL 成员比对）。
            expected_conversation_id=claimed.conversation_id,
            expected_producer_purge_revision=claimed.producer_purge_revision,
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
        # suppressed tombstone 路径：purge running/completed 时只写无正文
        # redacted 占位（联合契约），不经 output_reader 读 output ref，锁
        # Conversation 时放行 purge_fenced，不得把迟到 output 拒进死信。
        await self._bridge_repo.lock_projection_conversation(
            event, allow_purge_fenced=True
        )
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

    async def share_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> None:
        await self._bridge_repo.share_owned_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=include_deleted,
        )

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
        deleted_at: datetime | None = None,
    ) -> Conversation:
        return await self._workspace_repo.soft_delete_after_guard(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
            purge_after=purge_after,
            deleted_at=deleted_at,
        )

    async def restore_after_guard(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        now: datetime | None = None,
    ) -> Conversation:
        # R1-S2 恢复截止（Spec §3/§4.2）：restore 要求预期 owner fence 集合
        # （registry 全部固定 owner）完整且全部 active，与 purge 竞争时不得
        # 复活正文。锁序：Guard -> Conversation row -> owner advisory lock ->
        # fence FOR UPDATE（单 owner 操作只取 workspace.core.v1 一个 owner
        # lock）。生产裁决时间在全部锁取得之后读数据库 clock_timestamp()
        # （请求可能在截止前进入、锁等待跨截止，锁后采样必须 fail closed）；
        # 测试经 now 注入时钟。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
        )
        fences = await AgentErasureRepository(
            self._session
        ).list_fences_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        _require_restorable_fences(fences)
        effective_now = now
        if effective_now is None:
            effective_now = await self._session.scalar(
                select(func.clock_timestamp())
            )
            assert effective_now is not None
        return await self._workspace_repo.restore(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
            now=effective_now,
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
