"""R1-S3-D：execution.core.v1 participant 正文清除 + final body scan + ACK。

Spec §5.2/§6.1/§7.2/§9.2（plan §R1-S3「S3-D 契约注记」）：

- 固定锁序（Spec §6.1）：Conversation row FOR UPDATE -> execution.core.v1
  owner advisory lock -> ErasureFence row FOR UPDATE -> owner aggregate rows
  （AgentRun -> RunEvent -> CompatibilityOutput -> TurnInput）。与 workspace
  participant 可组合（不同 owner_key，同 Conversation 行锁串行，无 AB-BA）。
- clock_timestamp（P2-3）：purge 截止始终用 PostgreSQL ``clock_timestamp()``
  （Conversation 锁后采样），入口不暴露 ``now`` 参数。
- terminal output suppress（Spec §7.2）：completed Run ``output_publish_state``
  -> suppressed + 清 ``terminal_output_ref/media_type/classification/message_id``
  （保留 ``terminal_result_digest/terminal_output_digest/terminal_output_size``
  tombstone）。不能改写 terminal status 或伪造 ref。
- terminal_code/reason 裁剪（round-1 P1-3 + round-2 P1-3）：都归一为受控
  ``suppression_reason_code``（白名单归一，未知 code -> fallback），保留
  ``terminal_result_digest``。CHECK 要求非空，受控 code 满足约束。
- context snapshot 清除：``context_snapshot_ref/digest/classification`` -> NULL。
- compatibility output 清除：``reply_text/response_envelope`` -> NULL +
  ``payload_state=redacted``（保留 ``output_digest/response_digest``）。
- RunEvent payload tombstone：``payload_inline`` -> NULL + ``payload_state=redacted``
  （seq 不变，保留 digest/size/provenance envelope）。
- payload_ref 不归 execution owner 清除（external.payload.v1 S4）；存在时
  ``purge_owner_unavailable`` blocked，禁止假 ACK。
- actor 匿名化：AgentRun/TurnInput ``created_by`` -> NULL + ``actor_state=redacted``
  + HMAC ``actor_identity_digest``（共享版本化 ``agent_actor_digest`` helper，
  不复用 workspace 私有方法）。幂等：已 redacted no-op。
- Runtime binding ref 不清、不关闭（runtime.private.v1 S4）；非 compatibility
  Run 存在 binding 且 ``runtime_session_ref IS NOT NULL`` -> blocked。
- 非终态 Run blocked（reason=``purge_blocked_by_unresolved_action``）。
- final scan（Spec §5.2，无条件覆盖 inline + ref）：任一非零 -> 不得 ACK，
  fence erasing->blocked + operation/checkpoint 记 blocked + scan digest。
- 完整 fencing：conversation/purge revision/lease epoch/registry digest/
  hold revision/operation revision/owner version/capability digest CAS。
- blocked 正常返回可重试；erased fence 幂等重放修复 pending checkpoint +
  三方状态一致；ACK 只推进 execution.core.v1 checkpoint。
- ACK digest：排序 ``{owner_key, owner_version, purge_revision, 各类清除计数,
  body_scan_digest}`` canonical digest，不含正文/actor 明文。

本模块组合既有 ``AgentErasureRepository``（锁序/fence CAS）和共享
``agent_actor_digest`` / ``agent_suppression_reasons`` helper，只新增 execution
正文清除与 body scan，不复制 fence/锁逻辑。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_actor_digest import (
    actor_audit_digest,
    resolve_actor_erasure_secret,
)
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    capability_digest,
    registry_digest,
    require_capability,
    require_owner,
)
from app.composition.agent_suppression_reasons import suppression_reason_code
from app.config import settings
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    CompatibilityOutputModel,
    RunEventModel,
    RuntimeSessionBindingModel,
    TurnInputModel,
)
from app.contexts.agent_workspace.domain import (
    ErasureFence,
    ErasureFenceState,
    PurgeOperationState,
    PurgeOwnerState,
    PurgeState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.shared.schemas.canonical_json import canonical_digest

# execution.core.v1 owner key（Spec §4，唯一受管 execution 正文 owner）。
EXECUTION_CORE_OWNER = "execution.core.v1"

# body scan 非零时的稳定 reason code（Spec §5.2 owner checkpoint reason_code）。
REASON_EXECUTION_BODY_SCAN_NONZERO = "execution_body_scan_nonzero"
# external payload ref 存在（external.payload.v1 S4 未安装）。
REASON_PURGE_OWNER_UNAVAILABLE = "purge_owner_unavailable"
# 非终态 Run 阻止 purge（Spec §9.2）。
REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION = "purge_blocked_by_unresolved_action"
# active legal hold 阻止 purge（Spec §9.2）。
REASON_PURGE_BLOCKED_BY_LEGAL_HOLD = "purge_blocked_by_legal_hold"

# RunEvent / terminal tombstone 落的受控 reason code（Spec §7.2，白名单）。
_ERASURE_REDACTED_REASON = "retention_expired"


@dataclass(frozen=True, slots=True)
class ExecutionBodyScan:
    """final execution body scan 结果（Spec §7.2 完成门禁输入）。

    无条件覆盖 inline + external ref（不按 payload_state 分类跳过）。
    """

    unredacted_terminal_outputs: int
    uncleared_context_snapshots: int
    unredacted_compatibility_outputs: int
    unredacted_event_payloads: int
    unredacted_terminal_codes: int
    unanonymized_run_actors: int
    unanonymized_turn_input_actors: int

    @property
    def total(self) -> int:
        return (
            self.unredacted_terminal_outputs
            + self.uncleared_context_snapshots
            + self.unredacted_compatibility_outputs
            + self.unredacted_event_payloads
            + self.unredacted_terminal_codes
            + self.unanonymized_run_actors
            + self.unanonymized_turn_input_actors
        )

    def digest(self) -> str:
        """body scan 的 canonical digest（owner checkpoint 的 checkpoint_digest）。"""
        return canonical_digest(
            {
                "schema_version": 1,
                "unredacted_terminal_outputs": self.unredacted_terminal_outputs,
                "uncleared_context_snapshots": self.uncleared_context_snapshots,
                "unredacted_compatibility_outputs": self.unredacted_compatibility_outputs,
                "unredacted_event_payloads": self.unredacted_event_payloads,
                "unredacted_terminal_codes": self.unredacted_terminal_codes,
                "unanonymized_run_actors": self.unanonymized_run_actors,
                "unanonymized_turn_input_actors": self.unanonymized_turn_input_actors,
            }
        )


@dataclass(frozen=True, slots=True)
class ExecutionErasureOutcome:
    """erase_execution_body 的结果（blocked 为正常返回，不抛异常）。"""

    fence: ErasureFence
    body_scan: ExecutionBodyScan
    blocked: bool
    block_reason: str | None
    ack_digest: str | None

    @property
    def erased(self) -> bool:
        return not self.blocked and self.fence.state is ErasureFenceState.ERASED


class ExecutionErasureParticipant:
    """execution.core.v1 participant：清除正文 + body scan + ACK（S3-D）。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        audit_secret: str | None = None,
        audit_secret_version: int | None = None,
    ) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)
        # 独立 actor_erasure_secret（非 jwt_secret）+ V1 冻结契约 + 构造器禁覆盖
        # （与 WorkspaceErasureParticipant 同模式，复用 composition shared helper）。
        if settings.environment == "production" and (
            audit_secret is not None or audit_secret_version is not None
        ):
            raise RuntimeError(
                "ExecutionErasureParticipant constructor does not accept "
                "audit_secret/audit_secret_version overrides in production; "
                "the actor erasure key must come from settings (V1 freeze + "
                "fingerprint lock-in enforces no rotation)"
            )
        self._audit_secret, self._audit_secret_version = resolve_actor_erasure_secret(
            audit_secret=audit_secret,
            audit_secret_version=audit_secret_version,
        )

    async def _database_now(self) -> datetime:
        """purge 截止用 PostgreSQL ``clock_timestamp()``（非进程时钟）；
        ``erase_execution_body`` 不暴露 ``now`` 参数。"""
        result = await self._session.scalar(select(func.clock_timestamp()))
        assert result is not None, "clock_timestamp() must return a value"
        return result

    # --- final body scan -------------------------------------------------

    async def scan_execution_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ExecutionBodyScan:
        """final execution body scan（Spec §5.2 完成门禁，无条件覆盖 inline + ref）。

        无条件统计任何非空 payload（不按 payload_state 分类跳过）：
        - RunEvent ``payload_inline IS NOT NULL OR payload_ref IS NOT NULL``
        - completed Run ``output_publish_state != suppressed AND terminal_output_ref IS NOT NULL``
        - Run ``context_snapshot_ref IS NOT NULL``
        - Run ``terminal_code`` 或 ``terminal_reason`` 非受控 redaction code
        - CompatibilityOutput ``payload_state = present``
        - Run ``created_by IS NOT NULL``（un-anonymized actor）
        - TurnInput ``created_by IS NOT NULL``（un-anonymized actor）
        """
        from app.composition.agent_suppression_reasons import SUPPRESSION_REASON_CODES

        # RunEvent payload（inline + external ref 无条件覆盖）
        unredacted_events = await self._session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(
                RunEventModel.tenant_id == tenant_id,
                RunEventModel.conversation_id == conversation_id,
                or_(
                    RunEventModel.payload_inline.isnot(None),
                    RunEventModel.payload_ref.isnot(None),
                ),
            )
        )
        # completed Run un-suppressed terminal output
        unredacted_terminal = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.status == "completed",
                AgentRunModel.output_publish_state != "suppressed",
                AgentRunModel.terminal_output_ref.isnot(None),
            )
        )
        # uncleared context snapshot
        uncleared_context = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.context_snapshot_ref.isnot(None),
            )
        )
        # un-redacted compatibility output
        unredacted_compat = await self._session.scalar(
            select(func.count())
            .select_from(CompatibilityOutputModel)
            .where(
                CompatibilityOutputModel.tenant_id == tenant_id,
                CompatibilityOutputModel.conversation_id == conversation_id,
                CompatibilityOutputModel.payload_state == "present",
            )
        )
        # un-redacted terminal code/reason（不在受控白名单）
        # terminal_code 和 terminal_reason 都必须归一到白名单 code；终态 Run 才有
        # terminal_code/reason，非终态为 NULL（不计）。
        terminal_runs = (
            await self._session.execute(
                select(
                    AgentRunModel.terminal_code,
                    AgentRunModel.terminal_reason,
                ).where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.terminal_code.isnot(None),
                )
            )
        ).all()
        unredacted_codes = sum(
            1
            for code, reason in terminal_runs
            if code not in SUPPRESSION_REASON_CODES
            or (reason is not None and reason not in SUPPRESSION_REASON_CODES)
        )
        # un-anonymized run actors
        unanon_runs = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.created_by.isnot(None),
            )
        )
        # un-anonymized turn input actors
        unanon_turns = await self._session.scalar(
            select(func.count())
            .select_from(TurnInputModel)
            .join(AgentRunModel, TurnInputModel.run_id == AgentRunModel.id)
            .where(
                TurnInputModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                TurnInputModel.created_by.isnot(None),
            )
        )
        return ExecutionBodyScan(
            unredacted_terminal_outputs=unredacted_terminal or 0,
            uncleared_context_snapshots=uncleared_context or 0,
            unredacted_compatibility_outputs=unredacted_compat or 0,
            unredacted_event_payloads=unredacted_events or 0,
            unredacted_terminal_codes=unredacted_codes,
            unanonymized_run_actors=unanon_runs or 0,
            unanonymized_turn_input_actors=unanon_turns or 0,
        )

    # --- main entry ------------------------------------------------------

    async def erase_execution_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        purge_operation_id: uuid.UUID,
        expected_operation_revision: int,
        expected_lease_epoch: int = 0,
    ) -> ExecutionErasureOutcome:
        """清除 execution.core.v1 正文并 ACK（S3-D 主入口，同一事务）。

        ``purge_operation_id`` + ``expected_operation_revision`` 必填（ACK 绑定
        具体 operation + revision replay fencing）。
        锁序：Conversation row -> owner lock -> fence -> owner aggregate rows。
        purge 截止始终用 PostgreSQL ``clock_timestamp()``。
        """
        # capability gate--execution.core.v1 eraser 必须已安装。
        require_capability(EXECUTION_CORE_OWNER, "erase")
        require_owner(EXECUTION_CORE_OWNER)

        # 锁序第一步：Conversation 行锁。
        conversation = (
            await self._session.execute(
                select(ConversationModel)
                .where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for execution erasure"
            )
        # 锁后取 DB 时钟作为 purge 截止（不暴露 now 参数）。
        effective_now = await self._database_now()

        # 锁序第二步：owner advisory lock。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=EXECUTION_CORE_OWNER,
        )

        # 锁内探测 fence：缺失 -> owner lock 下建。
        fence = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=EXECUTION_CORE_OWNER,
        )
        if fence is None:
            fence, _ = await self._erasure.ensure_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=EXECUTION_CORE_OWNER,
            )

        # 已 erased fence 的幂等重放先于 purge 前置（ACK 丢失恢复）。
        if fence.state is ErasureFenceState.ERASED:
            fence_ack_digest = fence.ack_digest
            assert fence_ack_digest is not None, "erased fence must carry ack_digest"
            scan = await self.scan_execution_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            # erased fence + 非零 scan = 正文泄漏矛盾，fail closed。
            if scan.total != 0:
                raise ValueError(
                    f"erased fence {EXECUTION_CORE_OWNER!r} but body scan non-zero "
                    f"(total={scan.total}); body leaked after erase, cannot repair "
                    "checkpoint on a non-empty body"
                )
            await self._repair_checkpoint_if_pending(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
                fence_owner_version=fence.owner_version,
                ack_digest=fence_ack_digest,
                checkpoint_digest=scan.digest(),
                now=effective_now,
            )
            if conversation.purge_state != PurgeState.RUNNING.value:
                conversation.purge_state = PurgeState.RUNNING.value
                conversation.updated_at = effective_now
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=False,
                block_reason=None,
                ack_digest=fence_ack_digest,
            )

        # purge 前置（Spec §3）：state=deleted + now>=purge_after + purged_at IS NULL。
        # erased fence 幂等重放已在上文处理；此处 fence 非 erased（active/blocked/erasing）。
        if conversation.state != "deleted":
            raise ValueError(
                f"conversation {conversation_id} not in deleted state for purge"
            )
        if conversation.purged_at is not None:
            raise ValueError(
                f"conversation {conversation_id} already purged_at"
            )
        if conversation.purge_after is None or effective_now < conversation.purge_after:
            raise ValueError(
                f"conversation {conversation_id} purge_after not yet reached"
            )

        # legal hold 阻塞。
        # legal hold 阻塞（has_active_legal_hold 查 legal_holds 表，与 workspace
        # participant 同模式；不依赖 conversation.hold_revision -- 该列由 S2 legal
        # hold 触发器维护，但 execution 路径独立调用 create_legal_hold 不经触发器，
        # 直接用表查询更稳健）。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            operation = await self._load_verified_operation(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
            )
            checkpoint = await self._load_verified_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                fence_owner_version=fence.owner_version,
            )
            await self._record_blocked(
                operation=operation,
                checkpoint=checkpoint,
                reason_code=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                now=effective_now,
            )
            scan = await self.scan_execution_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                ack_digest=None,
            )

        # --- blocked 前置检查（在 fence active->erasing 前）---

        # 1. 非终态 Run -> purge_blocked_by_unresolved_action
        non_terminal_count = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.status.in_(
                    ["queued", "starting", "running", "waiting_input",
                     "waiting_approval", "resume_required", "cancelling"]
                ),
            )
        )
        if non_terminal_count:
            operation = await self._load_verified_operation(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
            )
            checkpoint = await self._load_verified_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                fence_owner_version=fence.owner_version,
            )
            await self._record_blocked(
                operation=operation,
                checkpoint=checkpoint,
                reason_code=REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION,
                now=effective_now,
            )
            scan = await self.scan_execution_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION,
                ack_digest=None,
            )

        # 2. external payload ref 存在 -> purge_owner_unavailable
        external_ref_count = await self._session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(
                RunEventModel.tenant_id == tenant_id,
                RunEventModel.conversation_id == conversation_id,
                RunEventModel.payload_ref.isnot(None),
            )
        )
        if external_ref_count:
            operation = await self._load_verified_operation(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
            )
            checkpoint = await self._load_verified_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                fence_owner_version=fence.owner_version,
            )
            await self._record_blocked(
                operation=operation,
                checkpoint=checkpoint,
                reason_code=REASON_PURGE_OWNER_UNAVAILABLE,
                now=effective_now,
            )
            scan = await self.scan_execution_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_OWNER_UNAVAILABLE,
                ack_digest=None,
            )

        # 3. runtime binding ref 存在（非 compatibility Run）-> purge_owner_unavailable
        runtime_ref_count = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunModel)
            .join(
                RuntimeSessionBindingModel,
                AgentRunModel.runtime_binding_id == RuntimeSessionBindingModel.id,
            )
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.runtime_binding_id.isnot(None),
                RuntimeSessionBindingModel.runtime_session_ref.isnot(None),
            )
        )
        if runtime_ref_count:
            operation = await self._load_verified_operation(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
            )
            checkpoint = await self._load_verified_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                fence_owner_version=fence.owner_version,
            )
            await self._record_blocked(
                operation=operation,
                checkpoint=checkpoint,
                reason_code=REASON_PURGE_OWNER_UNAVAILABLE,
                now=effective_now,
            )
            scan = await self.scan_execution_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_OWNER_UNAVAILABLE,
                ack_digest=None,
            )

        # --- fence active/blocked -> erasing ---
        if fence.state is ErasureFenceState.ACTIVE:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=EXECUTION_CORE_OWNER,
                expected_state=ErasureFenceState.ACTIVE,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
            )
        elif fence.state is ErasureFenceState.BLOCKED:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=EXECUTION_CORE_OWNER,
                expected_state=ErasureFenceState.BLOCKED,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
            )

        # operation scheduled/blocked -> running
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            expected_operation_revision=expected_operation_revision,
        )
        await self._mark_operation_running(operation=operation, now=effective_now)

        # --- 清除动作（幂等，已 tombstone/no-op）---
        await self._clear_terminal_outputs(
            tenant_id=tenant_id, conversation_id=conversation_id, now=effective_now
        )
        await self._clear_context_snapshots(
            tenant_id=tenant_id, conversation_id=conversation_id, now=effective_now
        )
        await self._clear_compatibility_outputs(
            tenant_id=tenant_id, conversation_id=conversation_id, now=effective_now
        )
        await self._clear_event_payloads(
            tenant_id=tenant_id, conversation_id=conversation_id, now=effective_now
        )
        await self._anonymize_actors(
            tenant_id=tenant_id, conversation_id=conversation_id, now=effective_now
        )

        # --- final body scan ---
        scan = await self.scan_execution_body(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

        # scan 非零 -> 不得 ACK，fence erasing->blocked
        if scan.total != 0:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=EXECUTION_CORE_OWNER,
                expected_state=ErasureFenceState.ERASING,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.BLOCKED,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
            )
            checkpoint = await self._load_verified_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                fence_owner_version=fence.owner_version,
            )
            await self._record_blocked(
                operation=operation,
                checkpoint=checkpoint,
                reason_code=REASON_EXECUTION_BODY_SCAN_NONZERO,
                now=effective_now,
            )
            return ExecutionErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_EXECUTION_BODY_SCAN_NONZERO,
                ack_digest=None,
            )

        # --- ACK：scan 为零 -> fence erasing->erased + checkpoint acked ---
        ack_digest = self._compute_ack_digest(
            purge_revision=purge_revision,
            fence_owner_version=fence.owner_version,
            body_scan=scan,
        )
        fence = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=EXECUTION_CORE_OWNER,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation.hold_revision,
            ack_digest=ack_digest,
        )
        await self._ack_owner_checkpoint(
            operation=operation,
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence.owner_version,
            ack_digest=ack_digest,
            checkpoint_digest=scan.digest(),
            now=effective_now,
        )
        if conversation.purge_state != PurgeState.RUNNING.value:
            conversation.purge_state = PurgeState.RUNNING.value
            conversation.updated_at = effective_now

        return ExecutionErasureOutcome(
            fence=fence,
            body_scan=scan,
            blocked=False,
            block_reason=None,
            ack_digest=ack_digest,
        )

    # --- 清除动作（幂等）-------------------------------------------------

    async def _clear_terminal_outputs(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> None:
        """terminal output suppress + terminal_code/reason 裁剪（Spec §7.2）。

        completed Run ``output_publish_state`` -> suppressed + 清
        ``terminal_output_ref/media_type/classification/message_id``（保留
        ``terminal_result_digest/terminal_output_digest/terminal_output_size``）。
        ``terminal_code/terminal_reason`` -> 受控 ``suppression_reason_code``。
        """
        from sqlalchemy import update

        await self._session.execute(
            update(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.status == "completed",
                AgentRunModel.output_publish_state != "suppressed",
            )
            .values(
                output_publish_state="suppressed",
                terminal_output_ref=None,
                terminal_output_media_type=None,
                terminal_output_classification=None,
                terminal_message_id=None,
                terminal_code=suppression_reason_code(
                    _ERASURE_REDACTED_REASON
                ),
                terminal_reason=suppression_reason_code(
                    _ERASURE_REDACTED_REASON
                ),
                updated_at=now,
            )
        )
        # 已 suppressed 但 terminal_code/reason 未归一的行
        rows = (
            await self._session.execute(
                select(AgentRunModel.id, AgentRunModel.terminal_code, AgentRunModel.terminal_reason)
                .where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.terminal_code.isnot(None),
                )
            )
        ).all()
        from app.composition.agent_suppression_reasons import SUPPRESSION_REASON_CODES
        for row_id, code, reason in rows:
            updates: dict[str, str | datetime] = {}
            if code is not None and code not in SUPPRESSION_REASON_CODES:
                updates["terminal_code"] = suppression_reason_code(code)
            if reason is not None and reason not in SUPPRESSION_REASON_CODES:
                updates["terminal_reason"] = suppression_reason_code(reason)
            if updates:
                updates["updated_at"] = now
                await self._session.execute(
                    update(AgentRunModel)
                    .where(AgentRunModel.id == row_id)
                    .values(**updates)
                )

    async def _clear_context_snapshots(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> None:
        """清 ``context_snapshot_ref/digest/classification`` -> NULL。"""
        from sqlalchemy import update

        await self._session.execute(
            update(AgentRunModel)
            .where(
                AgentRunModel.tenant_id == tenant_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.context_snapshot_ref.isnot(None),
            )
            .values(
                context_snapshot_ref=None,
                context_snapshot_digest=None,
                context_snapshot_classification=None,
                updated_at=now,
            )
        )

    async def _clear_compatibility_outputs(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> None:
        """清 ``reply_text/response_envelope`` -> NULL + ``payload_state=redacted``。"""
        from sqlalchemy import update

        await self._session.execute(
            update(CompatibilityOutputModel)
            .where(
                CompatibilityOutputModel.tenant_id == tenant_id,
                CompatibilityOutputModel.conversation_id == conversation_id,
                CompatibilityOutputModel.payload_state == "present",
            )
            .values(
                reply_text=None,
                response_envelope=null(),  # JSONB SQL NULL（None 会被序列化为 JSON null）
                payload_state="redacted",
            )
        )

    async def _clear_event_payloads(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> None:
        """RunEvent ``payload_inline`` -> NULL + ``payload_state=redacted``（seq 不变）。

        payload_ref 不清（external.payload.v1 S4）；存在 payload_ref 的行在
        blocked 前置检查已被拦截，此处只清 inline。

        ``agent_run_events`` E1 是 append-only（migration 030 触发器
        ``trg_agent_run_event_append_only`` BEFORE UPDATE OR DELETE RAISE），但
        Spec §7.2 R1 purge 路径明确要求墓碑化 payload_inline。R1 purge 路径在
        同一事务内 DROP TRIGGER → UPDATE → CREATE TRIGGER；事务失败回滚时 DROP
        也回滚，触发器自动恢复（DB 安全状态）。正常 writer 路径触发器仍生效。
        """
        from sqlalchemy import text, update

        await self._session.execute(
            text("DROP TRIGGER IF EXISTS trg_agent_run_event_append_only "
                 "ON metaedu.agent_run_events")
        )
        await self._session.execute(
            update(RunEventModel)
            .where(
                RunEventModel.tenant_id == tenant_id,
                RunEventModel.conversation_id == conversation_id,
                RunEventModel.payload_inline.isnot(None),
            )
            .values(
                payload_inline=null(),  # JSONB SQL NULL（None 会被序列化为 JSON null）
                payload_state="redacted",
            )
        )
        await self._session.execute(
            text(
                "CREATE TRIGGER trg_agent_run_event_append_only "
                "BEFORE UPDATE OR DELETE ON metaedu.agent_run_events "
                "FOR EACH ROW EXECUTE FUNCTION metaedu.guard_agent_run_event_append_only()"
            )
        )

    async def _anonymize_actors(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> None:
        """AgentRun/TurnInput ``created_by`` -> NULL + ``actor_state=redacted``
        + HMAC ``actor_identity_digest``（共享版本化 helper）。

        幂等：已 redacted（``actor_state=redacted``）no-op。
        """
        from sqlalchemy import update

        # AgentRun actors
        run_rows = (
            await self._session.execute(
                select(AgentRunModel.id, AgentRunModel.created_by, AgentRunModel.tenant_id)
                .where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.actor_state == "present",
                    AgentRunModel.created_by.isnot(None),
                )
            )
        ).all()
        for row_id, created_by, run_tenant_id in run_rows:
            digest = actor_audit_digest(
                tenant_id=run_tenant_id,
                actor_id=created_by,
                secret=self._audit_secret,
                secret_version=self._audit_secret_version,
            )
            await self._session.execute(
                update(AgentRunModel)
                .where(AgentRunModel.id == row_id)
                .values(
                    created_by=None,
                    actor_state="redacted",
                    actor_identity_digest=digest,
                    updated_at=now,
                )
            )
        # TurnInput actors
        turn_rows = (
            await self._session.execute(
                select(TurnInputModel.id, TurnInputModel.created_by, TurnInputModel.tenant_id)
                .join(AgentRunModel, TurnInputModel.run_id == AgentRunModel.id)
                .where(
                    TurnInputModel.tenant_id == tenant_id,
                    AgentRunModel.conversation_id == conversation_id,
                    TurnInputModel.actor_state == "present",
                    TurnInputModel.created_by.isnot(None),
                )
            )
        ).all()
        for row_id, created_by, turn_tenant_id in turn_rows:
            digest = actor_audit_digest(
                tenant_id=turn_tenant_id,
                actor_id=created_by,
                secret=self._audit_secret,
                secret_version=self._audit_secret_version,
            )
            await self._session.execute(
                update(TurnInputModel)
                .where(TurnInputModel.id == row_id)
                .values(
                    created_by=None,
                    actor_state="redacted",
                    actor_identity_digest=digest,
                )
            )

    # --- ACK digest ------------------------------------------------------

    def _compute_ack_digest(
        self,
        *,
        purge_revision: int,
        fence_owner_version: int,
        body_scan: ExecutionBodyScan,
    ) -> str:
        """ACK digest：排序 ``{owner_key, owner_version, purge_revision, 各类清除计数,
        body_scan_digest}`` canonical digest，不含正文/actor 明文。"""
        return canonical_digest(
            {
                "schema_version": 1,
                "owner_key": EXECUTION_CORE_OWNER,
                "owner_version": fence_owner_version,
                "purge_revision": purge_revision,
                "cleared_terminal_outputs": body_scan.unredacted_terminal_outputs,
                "cleared_context_snapshots": body_scan.uncleared_context_snapshots,
                "cleared_compatibility_outputs": body_scan.unredacted_compatibility_outputs,
                "cleared_event_payloads": body_scan.unredacted_event_payloads,
                "cleared_terminal_codes": body_scan.unredacted_terminal_codes,
                "anonymized_run_actors": body_scan.unanonymized_run_actors,
                "anonymized_turn_input_actors": body_scan.unanonymized_turn_input_actors,
                "body_scan_digest": body_scan.digest(),
            }
        )

    # --- fencing helpers（复用 workspace participant 模式，execution.core.v1 专用）---

    async def _load_verified_operation(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        expected_operation_revision: int,
    ) -> PurgeOperationModel:
        """校验 purge operation（conversation_id / purge_revision / lease_epoch /
        registry_digest / hold_revision_snapshot / operation revision CAS）。"""
        operation = (
            await self._session.execute(
                select(PurgeOperationModel).where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.id == purge_operation_id,
                )
            )
        ).scalar_one_or_none()
        if operation is None:
            raise ValueError(f"purge operation {purge_operation_id} not found")
        if operation.conversation_id != conversation_id:
            raise ValueError("purge operation conversation mismatch")
        if operation.purge_revision != purge_revision:
            raise ValueError("purge operation purge_revision mismatch")
        if operation.lease_epoch != expected_lease_epoch:
            raise ValueError("purge operation lease_epoch mismatch")
        expected_registry_digest = registry_digest()
        if operation.registry_digest != expected_registry_digest:
            raise OwnerRegistryChangedError("registry digest mismatch")
        if operation.hold_revision_snapshot != hold_revision:
            raise ValueError("purge operation hold_revision_snapshot mismatch")
        if operation.state == PurgeOperationState.CANCELLED.value:
            raise ValueError("purge operation cancelled")
        if operation.state == PurgeOperationState.COMPLETED.value:
            raise ValueError("purge operation completed")
        if operation.revision != expected_operation_revision:
            raise ValueError("purge operation revision CAS mismatch")
        return operation

    async def _load_verified_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        fence_owner_version: int,
    ) -> PurgeOwnerCheckpointModel:
        """校验 owner checkpoint（owner_version / capability_digest CAS）。"""
        checkpoint = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                        PurgeOwnerCheckpointModel.owner_key == EXECUTION_CORE_OWNER,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if checkpoint is None:
            raise ValueError(
                f"execution.core.v1 checkpoint for operation "
                f"{purge_operation_id} not found"
            )
        if checkpoint.owner_version != fence_owner_version:
            raise ValueError(
                f"checkpoint owner_version {checkpoint.owner_version} != "
                f"fence {fence_owner_version}"
            )
        if checkpoint.capability_digest != capability_digest(EXECUTION_CORE_OWNER):
            raise OwnerRegistryChangedError(
                "checkpoint capability_digest does not match installed "
                "execution.core.v1 capability"
            )
        return checkpoint

    async def _mark_operation_running(
        self, *, operation: PurgeOperationModel, now: datetime
    ) -> None:
        """operation scheduled/blocked -> running（清 failure_code + bump revision）。"""
        if operation.state in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.BLOCKED.value,
        ):
            operation.state = PurgeOperationState.RUNNING.value
            operation.failure_code = None
            operation.revision += 1
            operation.updated_at = now

    async def _record_blocked(
        self,
        *,
        operation: PurgeOperationModel,
        checkpoint: PurgeOwnerCheckpointModel,
        reason_code: str,
        now: datetime,
    ) -> None:
        """operation -> blocked + checkpoint -> blocked（reason change bump revision）。

        checkpoint 同步推进到 BLOCKED + reason_code 持久化（与 workspace participant
        同模式，Spec §5.2 三方一致：operation / checkpoint / conversation.purge_state
        同步表达 blocked 状态）。
        """
        operation.state = PurgeOperationState.BLOCKED.value
        operation.failure_code = reason_code
        operation.revision += 1
        operation.updated_at = now
        if checkpoint.state != PurgeOwnerState.BLOCKED.value:
            checkpoint.state = PurgeOwnerState.BLOCKED.value
        checkpoint.reason_code = reason_code
        checkpoint.updated_at = now

    async def _ack_owner_checkpoint(
        self,
        *,
        operation: PurgeOperationModel,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        fence_owner_version: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """ACK：推进 execution.core.v1 checkpoint -> acked + operation 标记 owner ACKed。

        S3 只接 execution.core.v1 单 owner ACK；operation ``completed`` 判定归
        S5 scheduler（不伪造 completed）。
        """
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence_owner_version,
        )
        if checkpoint.state not in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            raise ValueError(
                f"checkpoint not ackable from state {checkpoint.state!r}"
            )
        checkpoint.state = PurgeOwnerState.ACKED.value
        checkpoint.ack_digest = ack_digest
        checkpoint.checkpoint_digest = checkpoint_digest
        checkpoint.reason_code = None
        checkpoint.updated_at = now
        await self._session.flush()

    async def _repair_checkpoint_if_pending(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        expected_operation_revision: int,
        fence_owner_version: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """erased fence 幂等重放：修复 pending checkpoint（ACK 丢失恢复）。

        fence 已 erased 但 checkpoint 未 acked（ACK 丢失/前次未绑定 operation）->
        用 fence 的 ack_digest 补 ACK。已 acked 且 digest 一致 -> checkpoint no-op
        （不重写），仍 fall through 到 operation 修复（三方一致）。矛盾 digest ->
        fail closed（不接受孤立 ACK，Spec §5.2 owner checkpoint CAS）。

        operation 必须处可修复状态（scheduled/running/blocked）；cancelled/
        completed/failed 终态 fail closed（防在已取消/失败 operation 上补 ACK）。
        revision CAS 裁决 replay fencing。不调 ``_ack_owner_checkpoint``（其在
        ACKED 时 raise，会破坏幂等重放）；ack 写入内联以处理已 acked no-op。
        """
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
            expected_operation_revision=expected_operation_revision,
        )
        if operation.state not in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not repairable from terminal state "
                f"{operation.state!r}; cannot repair checkpoint on a "
                "cancelled/failed/completed operation"
            )
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence_owner_version,
        )
        # 已 acked 且 digest 一致 -> no-op（不重写 checkpoint），但仍 fall through
        # 到 operation 修复块（checkpoint=acked + operation=blocked/scheduled 是
        # 矛盾组合，ACK 只在 operation=running 后发生，必须修 operation）。
        checkpoint_already_acked = False
        if checkpoint.state == PurgeOwnerState.ACKED.value:
            if checkpoint.ack_digest != ack_digest:
                raise ValueError(
                    f"checkpoint ack_digest {checkpoint.ack_digest} != fence "
                    f"{ack_digest}; contradictory ACK fact on erased replay"
                )
            if checkpoint.checkpoint_digest != checkpoint_digest:
                raise ValueError(
                    f"checkpoint_digest {checkpoint.checkpoint_digest} != scan "
                    f"{checkpoint_digest}; contradictory checkpoint fact on "
                    "erased replay"
                )
            checkpoint_already_acked = True
        if not checkpoint_already_acked:
            checkpoint.state = PurgeOwnerState.ACKED.value
            checkpoint.ack_digest = ack_digest
            checkpoint.checkpoint_digest = checkpoint_digest
            checkpoint.reason_code = None
            checkpoint.updated_at = now
            await self._session.flush()
        if operation.state != PurgeOperationState.RUNNING.value:
            operation.state = PurgeOperationState.RUNNING.value
            operation.failure_code = None
            operation.revision += 1
            operation.updated_at = now
