"""R1-S4-D：transport erasure participant 共享基类。

``workspace.transport.v1`` / ``execution.transport.v1`` 的 purge eraser 共用本
基类的 ACK/fencing 管道（S2-D/S3-D 各复制了一份 320-400 行 plumbing，S4-D-A 是
第三处使用——抽取共享基类消除重复，不动既有 workspace/execution participant）。

契约事实源：Plan §R1-S4-D 契约细化（PR #541 已合并 `51a12df6`）D-A-1/D-B-2/D-B-3：

- 锁序固定：``Guard -> Conversation 行锁 -> owner advisory lock（transport
  owner）-> fence 重验 -> transport aggregate 集合 advisory lock（最内层）->
  源 transport 行 FOR UPDATE 投影写``；禁止在 Guard/Conversation/owner/fence
  之前取集合锁（防 AB-BA）。
- final scan 以**正文事实**为核心：``payload_inline IS NOT NULL OR
  payload_ref IS NOT NULL`` 命中即残留（不排除 ``cancelled``）。**清除只针对
  inline-only 行**（``payload_ref IS NULL``）转 ``status='suppressed'`` 保留
  ``payload_digest``；``cancelled`` 行保留 S4-C 终态证据（execution ``decision_*``
  四元 / workspace ``last_error_code``）。
- **S4-E-A E-0a ref-bearing blocked**：outbox 存在 ``payload_ref IS NOT NULL`` 行
  -> transport 零修改并 blocked（``purge_owner_unavailable``），fence 保持 active
  ——external object 未取得 receipt 前不得清 ref（D5），ref 归 external.payload.v1
  （S4-E-B2）清除。
- inbox 状态矩阵：``processing`` -> ``rejected``+tombstone；已
  ``consumed/rejected`` 保留原 status 仅补幂等 tombstone；已 tombstone digest
  精确匹配 no-op / 不匹配 fail closed（``*IntegrationConflictError``）。
- final scan 为零才 ACK + 全套 fencing（conversation/purge revision/lease
  epoch/registry drift/hold revision/operation revision/owner version/
  capability digest CAS）；scan 非零 -> blocked 三方一致；erased fence 幂等
  重放修复 pending checkpoint（ACK 丢失恢复）。
- **D-B-3 conversation_scope gate**（S4-D-B）：该 Conversation 有未 resolved 的
  conversation_scope issue 即 blocked（purge 前置查与 S5 同一谓词，防直接调用
  绕过 scheduler）。
- **D-B-2 resolve**（S4-D-B）：inbox tombstone 后对 conversation_scope
  `epoch_unresolvable` issue 置 resolved（集合锁临界区内，以 inbox
  `receipt_tombstone_digest` 为 `resolution_digest`）；`tenant_scope`/`orphan`
  不 resolve（留 S5/运维）。
- registry：S4-D-A 保持 ``erase_available=False``；**S4-D-B merged-boundary 后
  两 transport owner 翻 True**（capability gate 放行）。
- 边界：不导入 backfill 私有函数、不实现 ExternalPayloadErasureParticipant、
  不启用 S5。

子类只实现两侧差异：``scan_transport_body`` / ``count_ref_bearing_outbox_rows``
/ ``erase_transport_body`` / ``_resolve_epoch_issues_after_erase``（outbox + inbox
的清除动作与 scan 谓词，表结构两侧对称）。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    capability_digest,
    registry_digest,
    require_capability,
)
from app.composition.agent_transport_ledger_service import (
    conversation_scope_gate_hits,
)
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    PurgeOperationState,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.domain.erasure import ErasureFence
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)

# blocked reason（与 S2-D/S3-D 同域受控枚举，plan §R1-S4-D D-A-1）。
REASON_TRANSPORT_SCAN_NONZERO = "purge_blocked_by_transport_scan_nonzero"
REASON_PURGE_BLOCKED_BY_LEGAL_HOLD = "purge_blocked_by_legal_hold"
#: D-B-3 conversation_scope gate 命中（该 Conversation 有未 resolved 的
#: conversation_scope issue——purge 前置查与 S5 同一谓词）。
REASON_CONVERSATION_SCOPE_GATE = "purge_blocked_by_conversation_scope_gate"
#: S4-E-A E-0a：outbox 存在 ref-bearing 行（payload_ref IS NOT NULL）——external
#: object 未取得 receipt 前，transport 不得清 ref（D5「先删 external object 取
#: receipt，再清 transport DB ref」）。ref-bearing 行零修改并 blocked，fence 保持
#: active（external receipt 后由 ExternalPayloadErasureParticipant 清 ref）。镜像
#: execution.core.v1 的 external-ref 前置守卫（execution_erasure_participant.py
#: REASON_PURGE_OWNER_UNAVAILABLE，Plan §R1-S4-E E-0a 冻结 reason）。
REASON_PURGE_OWNER_UNAVAILABLE = "purge_owner_unavailable"

# receipt tombstone digest 的 reason 键值（族 5：plan 冻结，禁 participant 自造）。
# Tx1 消费侧用具名 code（epoch_unknown_rejected/epoch_stale_rejected）；purge 侧
# 清 receipt 用本值——冻结于 plan §R1-S4-D D-A-1；S4-D-B resolve 重放按
# **已验证的 receipt digest 留证**（含 purge_erasure + S4-C 两 epoch code）比对。
RECEIPT_TOMBSTONE_REASON = "purge_erasure"

# S4-C Tx1 消费侧合法写入的具名 reason code（互操作：purge 侧须接受并保留证据，
# 否则含 Tx1 epoch-rejected receipt 的 conversation purge 永久 fail closed）。
S4C_EPOCH_TOMBSTONE_REASONS = (
    "epoch_unknown_rejected",
    "epoch_stale_rejected",
)

# ---------------------------------------------------------------------------
# F-2a 多 owner 聚合架构裁决（Option A，冻结）：`operation.state`/`failure_code` 与
# `Conversation.purge_state` 的最终聚合归 **S5 scheduler**（从全部 owner checkpoint
# 计算，严重度优先级 + owner_key 字典序 tie-break，见 plan F-2a）。本 participant
# 是 owner-scoped eraser，只写自己的 checkpoint/fence/ledger/binding；`_record_blocked`
# /`_mark_operation_running`/`_repair_checkpoint_if_pending` 对 operation/Conversation
# 的写入是 **S5 未实现期间的临时投影**（last-writer-wins 占位），**不构成最终聚合
# 事实源**——S5 reducer 实现后由独立 contract-first PR 替换。
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransportBodyScan:
    """transport 正文扫描结果（outbox 正文残留 + inbox 未决 receipt + Run 投影）。

    ``total`` 为 0 才允许 ACK（final scan 为零）；digest 为扫描摘要的 canonical
    digest（证据绑定，不承载正文）。``run_unsettled_rows`` 仅 execution 侧非零
    （Run ``output_publish_state IN ('pending','dead_letter')`` 计数；
    ``not_required``/``published``/``suppressed`` 为终态不计）；workspace 侧恒 0。
    """

    outbox_payload_rows: int
    inbox_unsettled_rows: int
    run_unsettled_rows: int = 0

    @property
    def total(self) -> int:
        return self.outbox_payload_rows + self.inbox_unsettled_rows + self.run_unsettled_rows

    def digest(self) -> str:
        from app.contexts.agent_execution.domain.snapshots import snapshot_digest

        return snapshot_digest(
            {
                "schema_version": 1,
                "outbox_payload_rows": self.outbox_payload_rows,
                "inbox_unsettled_rows": self.inbox_unsettled_rows,
                "run_unsettled_rows": self.run_unsettled_rows,
            }
        )


@dataclass(frozen=True, slots=True)
class TransportErasureOutcome:
    """transport participant erase 结果（blocked 为正常返回，不抛异常）。"""

    fence: ErasureFence
    body_scan: TransportBodyScan
    blocked: bool
    block_reason: str | None
    ack_digest: str | None

    @property
    def erased(self) -> bool:
        return self.ack_digest is not None and not self.blocked


class TransportErasureParticipantBase(ABC):
    """transport owner eraser 共享管道（ACK/fencing/锁序），子类实现正文动作。

    锁序（Spec §6.1 / plan D8）：Conversation row -> owner advisory lock ->
    ErasureFence FOR UPDATE -> 集合 advisory lock（最内层，仅对需写 inbox 投影
    的路径）-> 源 transport 行 FOR UPDATE。调用方负责先取得 Guard（若有）——
    purge 执行单元（scheduler S5 将调用）与 S2-D 同，从 Conversation 行锁开始。
    """

    #: 本 participant 持有的 transport owner key（子类冻结）。
    owner_key: str

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)

    # --- 子类正文动作 ------------------------------------------------------

    @abstractmethod
    async def scan_transport_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> TransportBodyScan:
        """final transport scan（两侧对称，见子类）。"""

    @abstractmethod
    async def count_ref_bearing_outbox_rows(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """ref-bearing outbox 行计数（S4-E-A E-0a，两侧对称）。

        统计 ``payload_ref IS NOT NULL`` 的 outbox 行数。**ref-bearing 行 transport
        零修改并 blocked（`purge_owner_unavailable`）**——external object 未取得
        receipt 前不得清 ref（D5「先删 external object 取 receipt，再清 transport
        DB ref」），ref 归 external.payload.v1（S4-E-B2）清除。仅 inline-only 行
        可被 transport 清除。
        """

    @abstractmethod
    async def erase_transport_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime,
    ) -> None:
        """清除 transport 正文（outbox -> suppressed 留 digest；inbox -> rejected
        + tombstone）。幂等。Run ``output_publish_state`` 由 execution 侧
        scan 只读判定（不在此清除——归 S3-D execution.core.v1）。"""

    @abstractmethod
    async def _acquire_inbox_aggregate_locks(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """**源行 UPDATE 之前**取该 Conversation 全部 inbox 行的集合锁（三面 P0-1）。

        锁序修正：集合锁必须在源行 UPDATE 之前取（D8 冻结「集合锁 -> 源行 FOR
        UPDATE」）——否则 participant「行锁->集合锁」与 backfill「集合锁->行锁」
        构成 AB-BA 死锁。子类按两侧 inbox 表实现（先查该 Conversation 的 inbox
        行 id，逐行 `acquire_transport_aggregate_lock`）。"""

    @abstractmethod
    async def _resolve_epoch_issues_after_erase(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """inbox tombstone 后 resolve（D-B-2）：对目标 Conversation 的
        ``conversation_scope`` `epoch_unresolvable` issue 置 resolved。

        集合锁临界区内（写 ledger 证据 + 投影重算，D-A-1 免取条件不再适用），
        以 inbox ``receipt_tombstone_digest`` 为 ``resolution_digest``；只 resolve
        ``conversation_scope`` 行（``tenant_scope``/``orphan`` 不 resolve 留
        S5/运维）。子类按两侧 inbox 表实现。"""

    # --- 共享管道（从 S2-D/S3-D plumbing 收敛，owner 参数化）-----------------

    def _receipt_tombstone_digest_matches(self, row: RowMapping) -> bool:
        """判定已 tombstone inbox 行的 digest 是否为本 purge 的合法证据。

        互操作（终态/证据互操作批次）：接受两类精确匹配——
        (a) purge 侧自写：reason=`purge_erasure`（RECEIPT_TOMBSTONE_REASON）重算匹配；
        (b) S4-C Tx1 消费侧合法证据：`status='rejected'` + `last_error_code` 为
        `epoch_unknown_rejected`/`epoch_stale_rejected` 之一，且按该 code 重算
        digest 精确匹配——保留原证据（no-op），不得因 purge 重算差异 fail closed
        卡死含 Tx1 epoch-rejected receipt 的 conversation。
        其余不匹配 -> fail closed（调用方 raise）。
        """
        from app.contexts.agent_execution.domain.snapshots import snapshot_digest

        event_id = str(row["event_id"])
        if row["receipt_tombstone_digest"] == snapshot_digest(
            {
                "schema_version": 1,
                "reason": RECEIPT_TOMBSTONE_REASON,
                "event_id": event_id,
            }
        ):
            return True
        return (
            row["status"] == "rejected"
            and row["last_error_code"] in S4C_EPOCH_TOMBSTONE_REASONS
            and row["receipt_tombstone_digest"]
            == snapshot_digest(
                {
                    "schema_version": 1,
                    "reason": row["last_error_code"],
                    "event_id": event_id,
                }
            )
        )

    async def _database_now(self) -> datetime:
        """purge 截止用 PostgreSQL ``clock_timestamp()``（S2-D P2-3 冻结）。"""
        result = await self._session.scalar(func.clock_timestamp())
        assert result is not None, "clock_timestamp() must return a value"
        return result

    async def _load_verified_operation(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        expected_revision: int | None = None,
    ) -> PurgeOperationModel:
        """加载 operation FOR UPDATE + 完整 fencing（S2-D P1-3 收敛）。

        校验 conversation_id / purge_revision / lease_epoch / registry_digest /
        hold_revision_snapshot；``expected_revision`` 非 None 时校验 operation
        revision CAS（replay fencing）。任一不符 fail closed。
        """
        operation = (
            (
                await self._session.execute(
                    select(PurgeOperationModel)
                    .where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.id == purge_operation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if operation is None:
            raise ValueError(f"purge operation {purge_operation_id} not found")
        if operation.conversation_id != conversation_id:
            raise ValueError(
                f"operation conversation_id {operation.conversation_id} != "
                f"erase target {conversation_id}; cross-conversation ACK rejected"
            )
        if operation.purge_revision != purge_revision:
            raise ValueError(
                f"purge_revision mismatch: operation={operation.purge_revision} "
                f"request={purge_revision}"
            )
        if operation.lease_epoch != expected_lease_epoch:
            raise ValueError(
                f"lease_epoch mismatch: operation={operation.lease_epoch} "
                f"expected={expected_lease_epoch}; stale lease rejected"
            )
        if operation.registry_digest != registry_digest():
            raise OwnerRegistryChangedError(
                "purge operation registry digest no longer matches installed "
                "registry; cannot proceed on stale capability view"
            )
        if operation.hold_revision_snapshot != hold_revision:
            raise ValueError(
                f"hold_revision drift: operation snapshot "
                f"{operation.hold_revision_snapshot} != conversation "
                f"{hold_revision}; operation stale, create new purge_revision"
            )
        if expected_revision is not None and operation.revision != expected_revision:
            raise ValueError(
                f"operation revision mismatch: operation={operation.revision} "
                f"expected={expected_revision}; stale operation replay rejected"
            )
        return operation

    async def _load_verified_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        fence_owner_version: int,
    ) -> PurgeOwnerCheckpointModel:
        """加载 owner checkpoint FOR UPDATE + 校验 owner_version/capability_digest
        （owner 参数化；owner_version 取自 fence，不硬编码）。"""
        checkpoint = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                        PurgeOwnerCheckpointModel.owner_key == self.owner_key,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if checkpoint is None:
            raise ValueError(
                f"{self.owner_key} checkpoint for operation "
                f"{purge_operation_id} not found"
            )
        if checkpoint.owner_version != fence_owner_version:
            raise ValueError(
                f"checkpoint owner_version {checkpoint.owner_version} != "
                f"fence {fence_owner_version}"
            )
        if checkpoint.capability_digest != capability_digest(self.owner_key):
            raise ValueError(
                f"checkpoint capability_digest does not match installed "
                f"{self.owner_key} capability"
            )
        return checkpoint

    async def _mark_operation_running(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        expected_operation_revision: int,
        conversation: ConversationModel,
        now: datetime,
    ) -> None:
        """operation scheduled/blocked -> running（清 failure_code + bump revision）
        + Conversation.purge_state 投影 running（三方一致）。revision CAS 在此裁决。

        **F-2a 临时投影**：此处清 failure_code / 写 Conversation.purge_state 是 S5
        未实现期间的 last-writer-wins 占位，**不构成最终聚合事实源**——S5 reducer
        （独立 contract-first PR）从 blocked checkpoint 集合确定性聚合后替换本投影。
        """
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
            expected_revision=expected_operation_revision,
        )
        if operation.state not in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in runnable state: {operation.state!r}"
            )
        if operation.state in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.BLOCKED.value,
        ):
            operation.state = PurgeOperationState.RUNNING.value
            operation.failure_code = None
            if operation.started_at is None:
                operation.started_at = now
            operation.revision = operation.revision + 1
            operation.updated_at = now
        conversation.purge_state = PurgeOperationState.RUNNING.value
        conversation.updated_at = now
        await self._session.flush()

    async def _record_blocked(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        fence_owner_version: int,
        reason: str,
        scan: TransportBodyScan,
        conversation: ConversationModel,
        now: datetime,
        expected_revision: int | None = None,
    ) -> None:
        """记 blocked：operation + owner checkpoint 经 CAS 推进 blocked + 稳定
        reason code + scan digest + Conversation.purge_state 投影 blocked
        （三方一致，S2-D round-4 P1-2 收敛）。

        裁决先行（S3-D round-1 P1）：先完成全部实体状态裁决，再改任何实体——
        raise 时三方零变更（原子 fail closed）。
        """
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
            expected_revision=expected_revision,
        )
        if operation.state not in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in blockable state: {operation.state!r}"
            )
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
                f"checkpoint not blockable from state {checkpoint.state!r}"
            )
        # 裁决通过后才落变更。**F-2a 临时投影**：operation.failure_code 与
        # Conversation.purge_state 是 S5 未实现期间的 last-writer-wins 占位（S5
        # reducer 实现后由独立 PR 替换为从 blocked checkpoint 集合确定性聚合 +
        # owner_key tie-break；见 plan F-2a）。
        if operation.state != PurgeOperationState.BLOCKED.value:
            operation.state = PurgeOperationState.BLOCKED.value
            operation.failure_code = reason
            operation.revision = operation.revision + 1
            operation.updated_at = now
        elif operation.failure_code != reason:
            operation.failure_code = reason
            operation.revision = operation.revision + 1
            operation.updated_at = now
        cp_changed = checkpoint.state != PurgeOwnerState.BLOCKED.value
        checkpoint.state = PurgeOwnerState.BLOCKED.value
        if checkpoint.reason_code != reason:
            checkpoint.reason_code = reason
            cp_changed = True
        if checkpoint.checkpoint_digest != scan.digest():
            checkpoint.checkpoint_digest = scan.digest()
            cp_changed = True
        if cp_changed:
            checkpoint.updated_at = now
        conversation.purge_state = PurgeOperationState.BLOCKED.value
        conversation.updated_at = now
        await self._session.flush()

    async def _ack_owner_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        fence_owner_version: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """ACK：checkpoint -> acked + ack_digest/checkpoint_digest（CAS）。operation
        状态已由 _mark_operation_running 推进到 running，ACK 不再改 operation 状态。"""
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
        )
        if operation.state not in (
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in ackable state: {operation.state!r}"
            )
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
        conversation: ConversationModel,
        now: datetime,
    ) -> None:
        """erased fence 幂等重放：修复 pending checkpoint（ACK 丢失恢复）。

        fence 已 erased 但 checkpoint 未 acked -> 用 fence 的 ack_digest 补 ACK；
        已 acked 且 digest 一致 -> no-op（不重写），仍 fall through 到 operation
        修复（三方一致）；矛盾 digest -> fail closed。operation 必须处可修复状态
        （scheduled/running/blocked）；终态 fail closed。
        """
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
            expected_revision=expected_operation_revision,
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
        elif checkpoint.state not in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            raise ValueError(
                f"checkpoint not repairable from state {checkpoint.state!r}"
            )
        if not checkpoint_already_acked:
            checkpoint.state = PurgeOwnerState.ACKED.value
            checkpoint.ack_digest = ack_digest
            checkpoint.checkpoint_digest = checkpoint_digest
            checkpoint.reason_code = None
            checkpoint.updated_at = now
        changed = False
        if operation.state in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.BLOCKED.value,
        ):
            operation.state = PurgeOperationState.RUNNING.value
            if operation.started_at is None:
                operation.started_at = now
            changed = True
        # F-2a 临时投影：清 failure_code / 写 Conversation.purge_state 是 S5 未实现
        # 期间的 last-writer-wins 占位（S5 reducer 实现后替换）。**invariant-1 风险
        # 提示**：本 owner erased-fence 重放会重开 RUNNING + 清他 owner 已 blocked 的
        # failure_code（F-2a 六不变量 1「blocked 不得被后到 ACK 重开 running」在 S5
        # 前可观测违反）——归「owner-scoped 重构 + S5 reducer」独立 PR 闭环。
        if operation.failure_code is not None:
            operation.failure_code = None
            changed = True
        if changed:
            operation.revision = operation.revision + 1
            operation.updated_at = now
        conversation.purge_state = PurgeOperationState.RUNNING.value
        conversation.updated_at = now
        await self._session.flush()

    # --- 主入口（子类复用）--------------------------------------------------

    async def erase_transport_owner(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        purge_operation_id: uuid.UUID,
        expected_operation_revision: int,
        expected_lease_epoch: int = 0,
    ) -> TransportErasureOutcome:
        """transport owner 清除主入口（S2-D 同签名形状，owner 参数化）。

        锁序：Conversation 行锁 -> owner advisory lock -> fence FOR UPDATE ->
        集合 advisory lock（最内层）-> 源 transport 行 FOR UPDATE 投影写。
        """
        # capability gate（S2-D P1-1 模式）：registry 全程 False 时 fail closed。
        require_capability(self.owner_key, "erase")

        conversation = (
            (
                await self._session.execute(
                    select(ConversationModel)
                    .where(
                        ConversationModel.tenant_id == tenant_id,
                        ConversationModel.id == conversation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for transport erasure"
            )
        effective_now = await self._database_now()

        # 锁序第二步：transport owner advisory lock。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )

        # 锁内探测 fence：缺失 -> owner lock 下建立（Spec §4.2）。
        fence = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        if fence is None:
            fence, _ = await self._erasure.ensure_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
            )

        # erased fence 幂等重放先于 purge 前置（ACK 丢失恢复）。
        if fence.state is ErasureFenceState.ERASED:
            # S4-F 族 B（F-6「跨 purge 实例 erased-fence 重放」）：erased-fence 修复
            # 必须限定**同一 purge_revision**——否则同 conversation 新 purge（rev 2）
            # 会拿 purge 1 的 fence ack_digest 把 op2 的 pending checkpoint 置 ACKED
            # （跨 purge 实例的 ack 摘要污染）。scan 非零 guard 只拦 session 泄漏，
            # 拦不住 ack 摘要不一致——此处补门禁（runtime/external 侧同修复，
            # E-C C-4 / S4-F 族 B）。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"erased fence {self.owner_key!r} under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; "
                    "cross-purge-instance ACK repair rejected (E-2a)"
                )
            fence_ack_digest = fence.ack_digest
            assert fence_ack_digest is not None, "erased fence must carry ack_digest"
            scan = await self.scan_transport_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            if scan.total != 0:
                raise ValueError(
                    f"erased fence {self.owner_key!r} but body scan non-zero "
                    f"(total={scan.total}); body leaked after erase, cannot "
                    "repair checkpoint on a non-empty body"
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
                conversation=conversation,
                now=effective_now,
            )
            return TransportErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=False,
                block_reason=None,
                ack_digest=fence_ack_digest,
            )

        # purge 前置（仅非 erased fence = 新 purge 强制）。
        self._require_purgeable(conversation, now=effective_now)

        # active legal hold -> blocked 正常返回。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            scan = await self.scan_transport_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=scan,
                conversation=conversation,
                now=effective_now,
                expected_revision=expected_operation_revision,
            )
            return TransportErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                ack_digest=None,
            )

        # S4-E-A E-0a：ref-bearing outbox 行 -> purge_owner_unavailable blocked
        # （零修改，fence 保持 active）。external object 未取得 receipt 前不得清
        # ref（D5「先删 external object 取 receipt，再清 transport DB ref」）；ref
        # 归 external.payload.v1（S4-E-B2）清除。镜像 execution.core.v1 的
        # external-ref 前置守卫（execution_erasure_participant.py:583+）。检查在
        # fence -> erasing 推进**之前**，blocked 后 fence 仍 active、源行全未动。
        ref_bearing_count = await self.count_ref_bearing_outbox_rows(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        if ref_bearing_count:
            scan = await self.scan_transport_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_PURGE_OWNER_UNAVAILABLE,
                scan=scan,
                conversation=conversation,
                now=effective_now,
                # 本 pre-check 在 _mark_operation_running 之前（revision 未 bump），
                # 传 expected_operation_revision 与 legal-hold 分支对齐。
                expected_revision=expected_operation_revision,
            )
            return TransportErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_OWNER_UNAVAILABLE,
                ack_digest=None,
            )

        # 推进 fence -> erasing（首写 active->erasing；重试 blocked->erasing；
        # crash 恢复 erasing 继续）。
        if fence.state is ErasureFenceState.ACTIVE:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
                expected_state=ErasureFenceState.ACTIVE,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
        elif fence.state is ErasureFenceState.BLOCKED:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
                expected_state=ErasureFenceState.BLOCKED,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
        elif fence.state is ErasureFenceState.ERASING:
            # S4-F 族 A（并发面 P1-1）：E-2a 同一 purge 实例门禁（镜像 runtime
            # ``:594-606`` + external 同修复）。transport 单事务下 fence=erasing 不
            # 单独提交（仅同 session 崩溃重放触达），但为跨族一致仍须校验——不同
            # purge_revision 的第二 purge 实例不得进入 adapter 窗口（E-6 串行化）。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"fence {self.owner_key!r} already erasing under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; concurrent "
                    "purge instance rejected (E-2a same-instance gate)"
                )
        else:
            raise ValueError(
                f"fence {self.owner_key!r} in state {fence.state.value}; "
                "cannot erase transport body"
            )

        # operation scheduled/blocked -> running（revision CAS）。
        await self._mark_operation_running(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            expected_operation_revision=expected_operation_revision,
            conversation=conversation,
            now=effective_now,
        )

        # conversation_scope gate（D-B-3）：purge 前置查与 S5 同一谓词——该
        # Conversation 有未 resolved 的 conversation_scope issue 即 blocked
        # （防直接调用绕过 scheduler；S4-D-B participant 内嵌 fail closed）。
        if await conversation_scope_gate_hits(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        ):
            scan = await self.scan_transport_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_CONVERSATION_SCOPE_GATE,
                scan=scan,
                conversation=conversation,
                now=effective_now,
                # revision CAS 已由 _mark_operation_running 裁决并 bump（N->N+1）；
                # 此处传 None（与同位置 final-scan 分支对齐）——传 N 会与
                # 已 bump 的 N+1 恒不匹配导致 gate 命中必 raise（三面 P1-1）。
                expected_revision=None,
            )
            return TransportErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_CONVERSATION_SCOPE_GATE,
                ack_digest=None,
            )

        # 集合 advisory lock（最内层）——**免取条件（plan §R1-S4-D D-A-1 冻结）**：
        # 纯 outbox/inbox metadata 写 + transport scan **不写 ledger/投影**时可免取。
        # **S4-D-B 起**：participant 在 inbox tombstone 后 resolve（写 reconcile
        # issue 证据 + 重算投影）——写 ledger/投影，必须按全局锁序取集合锁
        # （Guard -> Conversation -> owner -> fence -> 集合锁最内层），禁止在此链前取。
        #
        # **锁序修正（三面 P0-1）**：集合锁必须在**源行 UPDATE 之前**取——否则
        # participant「行锁->集合锁」与 backfill「集合锁->行锁」构成 AB-BA 死锁
        # （真实 PG 双连接实验复现 DeadlockDetectedError）。本基类在 erase 前取
        # 该 Conversation 所有 inbox 行的集合锁（`_acquire_inbox_aggregate_locks`），
        # erase + resolve 全在临界区内——全链路「集合锁->行锁」与 backfill/consumer
        # 同序。源 transport 行 UPDATE 隐式取得行锁（S3-D P3-3 对齐）。
        await self._acquire_inbox_aggregate_locks(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

        # 正文清除（outbox -> suppressed 留 digest；inbox -> rejected+tombstone）。
        await self.erase_transport_body(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            now=effective_now,
        )

        # resolve（D-B-2）：inbox tombstone 已取得证据后，对目标 Conversation 的
        # conversation_scope `epoch_unresolvable` issue 置 resolved（集合锁临界区内，
        # 以 inbox receipt_tombstone_digest 为 resolution_digest，投影重算同事务）。
        await self._resolve_epoch_issues_after_erase(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

        # final scan 为零才 ACK；非零 -> blocked（三方一致）。
        final_scan = await self.scan_transport_body(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if final_scan.total != 0:
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_TRANSPORT_SCAN_NONZERO,
                scan=final_scan,
                conversation=conversation,
                now=effective_now,
            )
            return TransportErasureOutcome(
                fence=fence,
                body_scan=final_scan,
                blocked=True,
                block_reason=REASON_TRANSPORT_SCAN_NONZERO,
                ack_digest=None,
            )

        # ACK：fence erasing->erased（ack_digest）+ checkpoint pending->acked。
        ack_digest = self._compute_ack_digest(
            scan=final_scan, now=effective_now
        )
        fence = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation.hold_revision,
            ack_digest=ack_digest,
            now=effective_now,
        )
        await self._ack_owner_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            fence_owner_version=fence.owner_version,
            ack_digest=ack_digest,
            checkpoint_digest=final_scan.digest(),
            now=effective_now,
        )
        return TransportErasureOutcome(
            fence=fence,
            body_scan=final_scan,
            blocked=False,
            block_reason=None,
            ack_digest=ack_digest,
        )

    @staticmethod
    def _require_purgeable(
        conversation: ConversationModel, *, now: datetime
    ) -> None:
        """purge 前置：state=deleted + now>=purge_after + purged_at IS NULL。"""
        from app.contexts.agent_workspace.domain import (
            ConversationNotPurgeableError,
            ConversationState,
        )

        if conversation.state != ConversationState.DELETED.value:
            raise ConversationNotPurgeableError(
                f"conversation state is {conversation.state!r}; "
                "only deleted conversations can be purged"
            )
        if conversation.purged_at is not None:
            raise ConversationNotPurgeableError(
                "conversation is already purged; cannot re-purge"
            )
        if conversation.purge_after is None or now < conversation.purge_after:
            raise ConversationNotPurgeableError(
                "recovery window has not expired; cannot purge before purge_after"
            )

    def _compute_ack_digest(
        self, *, scan: TransportBodyScan, now: datetime
    ) -> str:
        """ACK digest：排序 canonical digest（owner/scan/时间戳），不含正文。"""
        from app.contexts.agent_execution.domain.snapshots import snapshot_digest

        return snapshot_digest(
            {
                "schema_version": 1,
                "owner_key": self.owner_key,
                "outbox_payload_rows": scan.outbox_payload_rows,
                "inbox_unsettled_rows": scan.inbox_unsettled_rows,
            }
        )
