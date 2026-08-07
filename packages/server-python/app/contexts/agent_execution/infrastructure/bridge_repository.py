from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_suppression_reasons import suppression_reason_code
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

    async def register_epoch_unresolvable_issue(
        self,
        *,
        tenant_id: uuid.UUID,
        owner_key: str,
        source_table: str,
        source_row_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
    ) -> None:
        """R1-S4-C（S4-C round-4/5 状态表 Tx1）：登记 ``epoch_unresolvable`` ledger。

        幂等（唯一键 ON CONFLICT DO NOTHING）。scope 已知 -> ``conversation_scope``
        （带 conversation_id，ck_..._class_scope 强制）；未知 -> ``tenant_scope``
        （不带）。
        """
        from app.composition.agent_erasure_locks import (
            acquire_transport_aggregate_lock,
        )

        # 集合锁（D8 最内层 owner aggregate 位置）；消费路径已持 Guard +
        # Conversation 行锁 + owner + fence，此处取集合锁与 backfill 同序。
        await acquire_transport_aggregate_lock(
            self._session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            source_table=source_table,
            source_row_id=source_row_id,
        )
        from app.composition.agent_transport_backfill import (
            _recompute_projection,
            _register_issue,
        )

        await _register_issue(
            self._session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            table=source_table,
            source_row_id=source_row_id,
            conversation_id=conversation_id,
            reconcile_class=(
                "conversation_scope" if conversation_id is not None else "tenant_scope"
            ),
            issue_code="epoch_unresolvable",
        )
        # R3 (d)：投影重算与 issue 插入同在集合锁临界区内（ledger 唯一事实源，
        # 行内 scope_reconcile_state 为派生投影）。
        await _recompute_projection(
            self._session,
            table=source_table,
            tenant_id=tenant_id,
            owner_key=owner_key,
            source_row_id=source_row_id,
        )

    async def create_turn_receipt_rejected(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        consumer_name: str,
        reason: str,
        receipt_tombstone_digest: str,
        correlation_id: uuid.UUID,
    ) -> uuid.UUID:
        """R1-S4-C（S4-C round-4/5 状态表 Tx1）：新建 execution inbox receipt 为
        ``rejected`` + tombstone 证据（epoch unknown/stale 拒绝）。

        消费 epoch 分类在 ``begin_turn_receipt`` 之前，故此处直接 INSERT rejected
        receipt（不进入 processing）。reason 为具名 code（``epoch_unknown_rejected``
        / ``epoch_stale_rejected``），``receipt_tombstone_digest`` 为 64-hex 证据
        （B1f）。幂等：已有行则校验 tombstone 一致返回。

        返回 **inbox 行 PK**：R3 集合锁目标/ledger ``source_row_id`` = inbox 行 PK
        （与 backfill/verify 的 ``r.source_row_id = t.id`` 匹配），不是 event_id。
        """
        from app.contexts.agent_execution.infrastructure.models import (
            ExecutionInboxModel,
        )

        existing = (
            await self._session.execute(
                select(ExecutionInboxModel)
                .where(
                    ExecutionInboxModel.tenant_id == tenant_id,
                    ExecutionInboxModel.consumer_name == consumer_name,
                    ExecutionInboxModel.event_id == event_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.status != "rejected"
                or existing.receipt_tombstone_digest != receipt_tombstone_digest
            ):
                raise ExecutionIntegrationConflictError(
                    "turn receipt rejected state conflicts with existing receipt"
                )
            return existing.id
        receipt_id = uuid.uuid4()
        self._session.add(
            ExecutionInboxModel(
                id=receipt_id,
                tenant_id=tenant_id,
                consumer_name=consumer_name,
                event_id=event_id,
                event_type=TURN_REQUESTED_V1,
                schema_version=1,
                payload_digest=payload_digest,
                correlation_id=correlation_id,
                causation_id=None,
                status="rejected",
                last_error_code=reason,
                receipt_tombstone_state="redacted",
                receipt_tombstone_digest=receipt_tombstone_digest,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        return receipt_id

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
        expected_conversation_id: uuid.UUID | None,
        expected_producer_purge_revision: int | None,
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
        # R1-S4-C（S4-C C3）：六元 CAS 追加 scope/epoch——仅当行值非 NULL 时
        # 比对（历史 NULL 行不参与值比较，由消费 epoch 分类处理）。
        if row.conversation_id is not None and (
            row.conversation_id != expected_conversation_id
        ):
            raise ExecutionIntegrationConflictError(
                "output claim conversation scope drifted between claim and consume"
            )
        if row.producer_purge_revision is not None and (
            row.producer_purge_revision != expected_producer_purge_revision
        ):
            raise ExecutionIntegrationConflictError(
                "output claim producer epoch drifted between claim and consume"
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
        # P2（独立 max 复核）：decision_reason 只存受控 reason code，自由文本
        # （可能含正文/提示词/secret）不落库也不进入 decision_digest 输入，与
        # workspace tombstone 的 redacted_reason 归一到同一 code。
        stored_reason = suppression_reason_code(normalized_reason)
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

    async def terminalize_output_late_write(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        expected_attempt: int,
        claimant_id: str,
        decided_at: datetime,
    ) -> None:
        """R1-S3-E round-1 P1/P2：purge 拦截的迟到 publish -> deterministic 终态。

        与人工 ``suppress_output_projection`` 两点不同（round-1 复审）：

        - **幂等接受 already-suppressed Run**（P1）：S3-D eraser 先把 completed Run
          翻 ``suppressed`` 并保留 execution outbox 给 S4；此后迟到的 publish 仍会
          经 dispatch 到达。本原语接受 Run 已 ``suppressed``（或飞行中
          ``pending``/``dead_letter``），仍把 outbox 事件置终态，不因 Run 已
          suppressed 抛冲突而放任 outbox 重试。Run 已 ``suppressed`` 时不再改
          ``output_publish_state``（幂等）。
        - **绑定当前 delivery claim**（P2）：与 ``record_output_delivery_failure``
          同一组 CAS（payload_digest + status=claimed + attempt_count + claimed_by），
          过期 worker 不得清掉后来 worker 的 claim 或覆盖同期人工裁决。

        不清 transport owner 正文（``payload_inline``/``payload_ref`` 原样保留，
        归 execution.transport.v1，S4）。
        """
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, event_id=event_id
        )
        if row.payload_digest != payload_digest:
            raise ExecutionIntegrationConflictError("output late-write digest conflicts")
        # round-2 P1：仅对**完整匹配的既有 late-write 终态**幂等 no-op；其余非
        # claimed 状态（pending/dead_letter/published/其他 cancelled）一律 fail
        # closed，不静默吞掉——否则 takeover 后回 pending 的事件会被 stale worker
        # 误判为「已 terminalize」而放任继续重试。
        if row.status != "claimed":
            expected_digest = snapshot_digest(
                {
                    "actor_id": str(uuid.UUID(int=0)),
                    "reason": suppression_reason_code("late_body_write_rejected"),
                    "output_digest": run.terminal_output_digest,
                }
            )
            already_terminal = (
                row.status == "cancelled"
                and row.decision_reason
                == suppression_reason_code("late_body_write_rejected")
                and row.decision_digest == expected_digest
                and run.output_publish_state == OutputPublishState.SUPPRESSED.value
            )
            if already_terminal:
                return
            raise ExecutionIntegrationConflictError(
                f"output late-write cannot terminalize from status {row.status!r}"
            )
        if row.attempt_count != expected_attempt or row.claimed_by != claimant_id:
            raise ExecutionIntegrationConflictError(
                "output late-write does not own the current delivery claim"
            )
        if RunStatus(run.status) is not RunStatus.COMPLETED:
            raise ExecutionIntegrationConflictError(
                "only completed output can be terminalized for late write"
            )
        if run.output_publish_state not in {
            OutputPublishState.PENDING.value,
            OutputPublishState.DEAD_LETTER.value,
            OutputPublishState.SUPPRESSED.value,
        }:
            raise ExecutionIntegrationConflictError(
                "resolved output projection cannot be terminalized for late write"
            )
        stored_reason = suppression_reason_code("late_body_write_rejected")
        row.status = "cancelled"
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = "late_body_write_rejected"
        row.decision_actor_id = uuid.UUID(int=0)  # 系统裁决，无操作员 actor
        row.decision_reason = stored_reason
        row.decision_digest = snapshot_digest(
            {
                "actor_id": str(uuid.UUID(int=0)),
                "reason": stored_reason,
                "output_digest": run.terminal_output_digest,
            }
        )
        row.decided_at = decided_at
        # Run 已 suppressed（S3-D 先行）时保持；否则投影终态 suppressed。
        if run.output_publish_state != OutputPublishState.SUPPRESSED.value:
            run.output_publish_state = OutputPublishState.SUPPRESSED.value
        run.updated_at = decided_at
        await self._session.flush()

    async def terminalize_output_epoch_rejected(
        self,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        payload_digest: str,
        expected_attempt: int,
        claimant_id: str,
        reason: str,
        receipt_tombstone_digest: str,
        decided_at: datetime,
    ) -> None:
        """R1-S4-C（S4-C round-4/5 状态表 Tx2）：epoch unknown/stale 拒绝 ->
        execution output outbox 确定性终态。

        与 ``terminalize_output_late_write`` 同构，两点差异（round-7/8 冻结）：
        - **decision digest envelope 冻结**：``snapshot_digest({schema_version,
          actor_id=UUID(0), reason=<具名 code>, event_id,
          receipt_tombstone_digest=<Tx1 证据>})``——键名/版本/helper 冻结，不得
          自造 digest 输入（round-8 P1）。
        - **精确终态谓词**：``cancelled`` + 清 claim + decision 四元精确匹配
          （actor_id=UUID(0) + reason 同一具名 code + digest 重算匹配 +
          decided_at 非空）+ Run ``suppressed`` -> no-op；``status='claimed'``
          且 claim 四元匹配 -> 终态化；其余（pending/dead_letter/published/其他
          cancelled）-> fail closed（round-6/7 三分支）。
        """
        run, row = await self._lock_output_then_run(
            tenant_id=tenant_id, event_id=event_id
        )
        if row.payload_digest != payload_digest:
            raise ExecutionIntegrationConflictError(
                "output epoch-reject digest conflicts"
            )
        expected_digest = snapshot_digest(
            {
                "schema_version": 1,
                "actor_id": str(uuid.UUID(int=0)),
                "reason": reason,
                "event_id": str(event_id),
                "receipt_tombstone_digest": receipt_tombstone_digest,
            }
        )
        already_terminal = (
            row.status == "cancelled"
            and row.claimed_at is None
            and row.claimed_by is None
            and row.decision_actor_id == uuid.UUID(int=0)
            and row.decision_reason == reason
            and row.decision_digest == expected_digest
            and row.decided_at is not None
            and run.output_publish_state == OutputPublishState.SUPPRESSED.value
        )
        if already_terminal:
            return
        if row.status != "claimed":
            raise ExecutionIntegrationConflictError(
                f"output epoch-reject cannot terminalize from status {row.status!r}"
            )
        if row.attempt_count != expected_attempt or row.claimed_by != claimant_id:
            raise ExecutionIntegrationConflictError(
                "output epoch-reject does not own the current delivery claim"
            )
        if RunStatus(run.status) is not RunStatus.COMPLETED:
            raise ExecutionIntegrationConflictError(
                "only completed output can be terminalized for epoch reject"
            )
        row.status = "cancelled"
        row.claimed_at = None
        row.claimed_by = None
        row.last_error_code = reason
        row.decision_actor_id = uuid.UUID(int=0)  # 系统裁决，无操作员 actor
        row.decision_reason = reason
        row.decision_digest = expected_digest
        row.decided_at = decided_at
        # Run 已 suppressed（S3-D 先行）时保持；否则投影终态 suppressed。
        if run.output_publish_state != OutputPublishState.SUPPRESSED.value:
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
