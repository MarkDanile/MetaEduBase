"""R1-S4-E-C：``runtime.private.v1`` RuntimeErasureParticipant conformance fake。

契约事实源：Plan §R1-S4-E E-5 第 4 项（S4-E-C）+ spec §10.3（conformance suite：
session destroy + 旧 epoch event + 迟到 seq + unknown outcome + ACK 重放）+
D7（Runtime fake 只证明协议，不变量 7）。

本 fake **只证明协议一致性**，不得宣称真实 Pi Worker、runtime spool 或生产
adapter 已删除（spec §10.2「fake 只证明契约」）：``runtime.private.v1`` 的
``erase_available`` 全程保持 **False**——入口 ``require_capability(owner, "erase")``
fail closed 是预期；测试用 monkeypatch 临时翻 True 验证主体（registry 断言与
实现分离）。``runtime_spool`` capability 当前**无实现、无清除路径**（spool 不在
R1 源码范围，spec §8），conformance 只覆盖 ``runtime_session_ref``。

**清除语义（spec §7.2 / E-5-C）**：
- ``RuntimeSessionBinding.runtime_session_ref`` 归 ``runtime.private.v1``——清除
  ref（置 NULL）+ 关 binding（``status -> closed``）。execution.core.v1 在 ACK
  前置已把含活跃 ref 的 conversation 判 ``purge_owner_unavailable`` blocked
  （S3-D，execution_erasure_participant.py:633），runtime.private.v1 ACK 后
  execution.core.v1 清本地 ref + 关 binding（S4 接力，本 fake 承担 runtime 侧）。
- 迟到 write 协议（spec §6.2 第 4 步）：fence erasing/erased 下旧 Runtime event
  只能写无正文 tombstone/receipt，**不重建正文**。Runtime binding 的 epoch/seq
  late-write 由 ``evaluate_runtime_ingest`` 裁决（旧 epoch -> RuntimeEpochMismatch
  / seq gap -> RuntimeSequenceGapError / 重放 -> IDEMPOTENT_REPLAY 不推进）；
  写侧 fence 裁决由 ``FencedExecutionPort.require_active_fence`` 承担
  （LateBodyWriteRejectedError）。conformance 验证这些裁决在 purge 窗口内一致。

**状态表达（无独立 ledger，无新增 schema）**：binding 行自身是事实源——
``runtime_session_ref IS NOT NULL`` 即外部 session 仍存在（fail-closed 残留
判据），与 ``status`` 解耦；``status='closed'`` + ref NULL = erased；
``status='invalid'`` + ref 保留 = blocked/unknown（E-3a 矩阵镜像，供运维识别，
不清 ref）。扫描与 retry 窗口一律按 ``runtime_session_ref IS NOT NULL`` 判定。

**双事务协议（镜像 B2 E-2）**：
- **Tx1（短事务）**：Conversation 行锁 -> owner advisory lock -> fence FOR
  UPDATE -> 集合锁（binding 源行）-> checkpoint ``pending/blocked -> erasing`` +
  ``attempt += 1`` + ``checkpoint_digest = runtime_destroy_intent.v1 digest``
  （binding 身份集合）+ operation fencing；**提交释放全部数据库锁**。
- **adapter 调用（无锁）**：释放锁后调用 adapter destroy session，携带跨
  takeover 稳定 idempotency key（E-2b，不含 lease_epoch/attempt）。
- **Tx2（第二独立事务）**：**精确重验（E-2a 镜像）** 后写 erased + receipt
  （adapter evidence 重算，evidence 承载于 ACK/checkpoint digest）**再清 binding
  ref + 关 binding**；成功则 ACK fence+checkpoint，未 erased 残留 -> conversation
  级 blocked（reason 从本次 outcomes 聚合，E-3a 矩阵镜像）。

**E-3a 矩阵（conformance 消费 classify_destroy_outcome）**：success->``erased``；
not-sent->``blocked/erase_timeout``；timeout->``unknown/outcome_unknown``；
unknown->``unknown/outcome_unknown``；failed->``blocked/adapter_unavailable``。
conversation 级 reason 归并（B2 C-7/D-10/T-6 同构）：unknown/timeout 优先
``outcome_unknown``，其次 not-sent ``erase_timeout``、failed ``adapter_unavailable``，
残留一律 ``purge_blocked_by_runtime_binding_scan_nonzero`` 兜底。

**边界（E-7）**：不实现真实 Pi Worker/spool 删除；不激活 runtime.private.v1
registry；不改 migration 040/041；不实现 S4-F/S5/S6。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import (
    acquire_owner_lock,
    acquire_transport_aggregate_lock,
)
from app.composition.agent_erasure_registry import require_capability
from app.composition.agent_transport_ledger_service import (
    conversation_scope_gate_hits,
)
from app.composition.runtime_erasure_adapter import (
    RuntimeDestroyError,
    RuntimeDestroyNotSentError,
    RuntimeDestroySuccess,
    RuntimeDestroyTimeoutError,
    RuntimeDestroyUnknown,
    RuntimeSessionDestroyAdapter,
    adapter_satisfies_prerequisite,
    classify_destroy_outcome,
    runtime_destroy_idempotency_key,
    runtime_destroy_receipt_digest,
    runtime_session_identity_digest,
)
from app.composition.transport_erasure_participant import (
    REASON_CONVERSATION_SCOPE_GATE,
    REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
    TransportBodyScan,
    TransportErasureParticipantBase,
)
from app.contexts.agent_execution.domain.snapshots import snapshot_digest
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel

#: adapter destroy 结果联合（成功 / unknown / 失败异常），outcome 聚合用。
destroy_outcome_union = (
    RuntimeDestroySuccess | RuntimeDestroyUnknown | RuntimeDestroyError
)

#: 本 participant 持有的 runtime owner（registry 固定 key）。
RUNTIME_PRIVATE_OWNER = "runtime.private.v1"

# conversation 级 blocked reason（E-3a 矩阵镜像 + 残留判定）。
REASON_RUNTIME_BINDING_SCAN_NONZERO = "purge_blocked_by_runtime_binding_scan_nonzero"
REASON_RUNTIME_ADAPTER_UNAVAILABLE = "purge_blocked_by_runtime_adapter_unavailable"
REASON_RUNTIME_OUTCOME_UNKNOWN = "purge_blocked_by_runtime_outcome_unknown"
REASON_RUNTIME_ERASE_TIMEOUT = "purge_blocked_by_runtime_erase_timeout"
# E-3a「digest mismatch -> blocked/digest_mismatch」在 conformance 下 vacuous——
# Tx2 的 receipt_digest 由 adapter evidence 现算现写（无已持久化值可比），与 B2
# 同源。reconcile 的 evidence 缺失走保持原状态（E-3b）而非 digest_mismatch。

#: binding status 的终态集合（ref 已清/已关）。其余 status（creating/active/
#: resume_required/invalid）只要 ref 非空即残留。
_BINDING_TERMINAL_STATUSES = ("closed",)


@dataclass(frozen=True, slots=True)
class RuntimeBindingScan:
    """runtime.private.v1 的 binding 残留扫描结果。

    ``total`` 为该 Conversation **ref 仍非空**的 binding 数（fail-closed 判据：
    ``runtime_session_ref IS NOT NULL``，与 status 解耦——invalid 行持 ref 仍为
    残留，不得 ACK）。``destroyed_bindings`` 为 ref 已清（NULL）的 binding 计数
    （final scan 为零时才等于总 binding 数）。
    """

    active_bindings: int
    destroyed_bindings: int

    @property
    def total(self) -> int:
        return self.active_bindings

    def digest(self) -> str:
        return snapshot_digest(
            {
                "schema_version": 1,
                "active_bindings": self.active_bindings,
                "destroyed_bindings": self.destroyed_bindings,
            }
        )


@dataclass(frozen=True, slots=True)
class RuntimeErasureSummary:
    """单 owner 清除 + ACK 摘要（ACK digest 的 canonical 输入，不含正文）。

    ``receipt_digests``：本批 destroyed binding 的 adapter-evidence 派生
    receipt digest（E-2b 证据链，D-2 返修）——折进 ACK digest，使 ACK 可证明
    「凭何 evidence 清除」（非本地自造，reconcile/运维可用同 envelope 重算比对）。
    """

    owner_key: str
    owner_version: int
    purge_revision: int
    destroyed_bindings: int
    scan: RuntimeBindingScan
    receipt_digests: tuple[str, ...] = ()

    def ack_digest(self) -> str:
        return snapshot_digest(
            {
                "schema_version": 1,
                "owner_key": self.owner_key,
                "owner_version": self.owner_version,
                "purge_revision": self.purge_revision,
                "destroyed_bindings": self.destroyed_bindings,
                "receipt_digests": sorted(self.receipt_digests),
                "scan": {
                    "active_bindings": self.scan.active_bindings,
                    "destroyed_bindings": self.scan.destroyed_bindings,
                },
            }
        )


@dataclass(frozen=True, slots=True)
class RuntimeBindingRow:
    """runtime binding 行（adapter 窗口内快照，Tx2 重验用）。"""

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_session_ref: str


def runtime_destroy_intent_digest(bindings: list[RuntimeBindingRow]) -> str:
    """E-2c 镜像：``runtime_destroy_intent.v1`` intent digest——完整稳定 binding
    身份集合的 canonical digest（跨 takeover 不变；attempt 可变但 intent 不变）。
    """
    identities = sorted(
        runtime_session_identity_digest(
            binding_id=binding.id,
            tenant_id=binding.tenant_id,
            conversation_id=binding.conversation_id,
            runtime_profile_id=binding.runtime_profile_id,
            runtime_session_ref=binding.runtime_session_ref,
        )
        for binding in bindings
    )
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "runtime_destroy_intent",
            "bindings": identities,
        }
    )


class RuntimeErasureParticipant(TransportErasureParticipantBase):
    """``runtime.private.v1``：conformance fake——擦除 runtime session ref + ACK。

    registry 全程保持 ``erase_available=False``（E-4）：入口
    ``require_capability(owner, "erase")`` fail closed 是预期；测试用 monkeypatch
    临时翻 True 验证主体。fake 不冒充真实 Pi Worker/spool 已完成（D7）。
    """

    owner_key = RUNTIME_PRIVATE_OWNER

    def __init__(
        self, session: AsyncSession, adapter: RuntimeSessionDestroyAdapter
    ) -> None:
        super().__init__(session)
        self._adapter = adapter

    # --- 抽象方法实现（runtime 无 transport body/inbox；scan 反映 binding 残留）----

    async def scan_transport_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> TransportBodyScan:
        """final runtime binding scan：该 Conversation 未 erased 的 binding 计数。

        复用 ``TransportBodyScan`` 形状接入基类 ACK/fencing（``outbox_payload_rows``
        承载残留；``inbox_unsettled_rows``/``run_unsettled_rows`` 恒 0）。残留判据
        = ``runtime_session_ref IS NOT NULL``（fail-closed，与 status 解耦）。
        """
        active = await self._session.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_runtime_session_bindings "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND runtime_session_ref IS NOT NULL"
            ),
            {"t": tenant_id, "c": conversation_id},
        )
        return TransportBodyScan(
            outbox_payload_rows=int(active or 0),
            inbox_unsettled_rows=0,
            run_unsettled_rows=0,
        )

    async def count_ref_bearing_outbox_rows(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """runtime 无此前置（ref-bearing 前置归 transport participant 的
        ``purge_owner_unavailable`` blocked / execution.core.v1 的 runtime-binding
        blocked）。本 participant 是 binding ref **清除者**，不是检查者。
        """
        return 0

    async def erase_transport_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime,
    ) -> None:
        """runtime 不在此路径清除——binding ref 清除在双事务协议的 Tx2（receipt 后）。"""

    async def _acquire_inbox_aggregate_locks(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        bindings: list[RuntimeBindingRow] | None = None,
    ) -> None:
        """该 Conversation 全部 runtime binding 源行的集合锁（E-5-2/D8）。

        binding 源行是 ``agent_runtime_session_bindings`` 自身，集合锁 owner 用
        ``runtime.private.v1``（该 owner 是 binding 行的唯一 erase 写者）。源行
        UPDATE（清 ref + 关 binding）必须在集合锁临界区内（D8「集合锁 -> 源行
        FOR UPDATE」）。

        ``bindings`` 复用调用方已加载的 adapter 窗口（Tx1 主流程
        ``_load_active_bindings`` 的结果）——**不重复读窗口**（并发面 D-6：两读间
        并发插入 binding 会让锁集含之而窗口不含，adapter 窗口/集合锁发散）。None
        时回退自身加载（满足基类抽象签名兼容）。
        """
        if bindings is None:
            bindings = await self._load_active_bindings(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
        for binding in bindings:
            await acquire_transport_aggregate_lock(
                self._session,
                tenant_id=tenant_id,
                owner_key=RUNTIME_PRIVATE_OWNER,
                source_table="agent_runtime_session_bindings",
                source_row_id=binding.id,
            )

    async def _resolve_epoch_issues_after_erase(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """runtime 不 resolve transport epoch issue（D-B-2 归 transport participant）。"""

    # --- conformance 专用：活跃 binding 窗口加载 ----------------------------------

    async def _load_active_bindings(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[RuntimeBindingRow]:
        """加载该 Conversation 的 binding 行（adapter 窗口）。

        窗口 = ``runtime_session_ref IS NOT NULL AND status NOT IN ('closed',
        'invalid')``（**B2 registered-only 窗口镜像**：blocked/unknown 行——status
        'invalid'——**不**进入 adapter 窗口，不自动重试 destroy；恢复只经
        ``reconcile_runtime_binding``（E-3b）。closed 行 ref 已 NULL 自然排除）。
        显式绑定 tenant + conversation 维度。
        """
        rows = (
            await self._session.execute(
                text(
                    "SELECT id, runtime_profile_id, runtime_session_ref "
                    "FROM metaedu.agent_runtime_session_bindings "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND runtime_session_ref IS NOT NULL "
                    "AND status NOT IN ('closed', 'invalid')"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).mappings().all()
        return [
            RuntimeBindingRow(
                id=row["id"],
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                runtime_profile_id=row["runtime_profile_id"],
                runtime_session_ref=row["runtime_session_ref"],
            )
            for row in rows
        ]

    async def _scan_runtime_bindings(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> RuntimeBindingScan:
        """该 Conversation 的 runtime binding 残留计数（final scan 判定用）。

        残留判据 = ``runtime_session_ref IS NOT NULL``（fail-closed）；ref 已 NULL
        计 destroyed。
        """
        active = await self._session.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_runtime_session_bindings "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND runtime_session_ref IS NOT NULL"
            ),
            {"t": tenant_id, "c": conversation_id},
        )
        destroyed = await self._session.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_runtime_session_bindings "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND runtime_session_ref IS NULL"
            ),
            {"t": tenant_id, "c": conversation_id},
        )
        return RuntimeBindingScan(
            active_bindings=int(active or 0),
            destroyed_bindings=int(destroyed or 0),
        )

    async def _load_conversation_for_update(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationModel:
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
                f"conversation {conversation_id} not found for runtime erasure"
            )
        return conversation

    # --- 主入口（E-2 双事务协议镜像）-----------------------------------------------

    async def erase_runtime_session(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        purge_operation_id: uuid.UUID,
        expected_operation_revision: int,
        expected_lease_epoch: int = 0,
    ) -> RuntimeErasureSummary:
        """runtime.private.v1 owner 擦除主入口（S4-E-C conformance）。

        锁序：Conversation 行锁 -> owner advisory lock -> fence FOR UPDATE -> 集合
        advisory lock（最内层）-> 源行 FOR UPDATE。E-2b 硬前置（adapter 幂等重放或
        receipt lookup）在入口断言（fail closed）。
        """
        # capability gate（S2-D P1-1 模式）：registry False 时 fail closed。
        require_capability(self.owner_key, "erase")
        if not adapter_satisfies_prerequisite(self._adapter):
            raise ValueError(
                f"adapter {self._adapter.adapter_key!r} v"
                f"{self._adapter.adapter_version} supports neither idempotent "
                "replay nor receipt lookup; runtime conformance cannot start (E-2b)"
            )

        # ===== Tx1（短事务，提交释放全部锁）=====
        conversation = await self._load_conversation_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        effective_now = await self._database_now()

        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
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
            # 并发面 P1 C-4：erased-fence 修复必须限定**同一 purge_revision**——
            # 否则同 conversation 新 purge（rev 2）会拿 purge 1 的 fence ack_digest
            # 把 op2 的 pending checkpoint 置 ACKED（跨 purge 实例的 ack 摘要污染）。
            # scan 非零 guard 只拦 session 泄漏，拦不住 ack 摘要不一致——此处补门禁。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"erased fence {self.owner_key!r} under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; "
                    "cross-purge-instance ACK repair rejected (E-2a)"
                )
            fence_ack_digest = fence.ack_digest
            assert fence_ack_digest is not None, "erased fence must carry ack_digest"
            scan = await self._scan_runtime_bindings(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            if scan.total != 0:
                raise ValueError(
                    f"erased fence {self.owner_key!r} but runtime binding scan "
                    f"non-zero (total={scan.total}); session leaked after erase"
                )
            # checkpoint_digest 必须用 final scan digest（RuntimeBindingScan 形式）——
            # 正常 ACK 持久化的也是该形式（B2 D-1 教训，不得包 TransportBodyScan）。
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
            return self._summary_from_fence(
                fence=fence,
                purge_revision=purge_revision,
                # 重放返回摘要的 destroyed_bindings = scan 全量已关（含历史 closed）；
                # 与持久化 ACK 的 destroyed_count（本次 Tx2）仅在**返回值**上可能不同
                # （D-10，不落库——持久化事实是 fence.ack_digest，已由 repair 复用）。
                destroyed_bindings=scan.destroyed_bindings,
                scan=scan,
            )

        # purge 前置（仅非 erased fence = 新 purge 强制）。
        self._require_purgeable(conversation, now=effective_now)

        # active legal hold -> blocked 正常返回。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            scan = await self._scan_runtime_bindings(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            body_scan = self._to_transport_scan(scan)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=body_scan,
                conversation=conversation,
                now=effective_now,
                expected_revision=expected_operation_revision,
            )
            return self._blocked_summary(
                fence=fence,
                purge_revision=purge_revision,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=scan,
            )

        # conversation_scope gate（D-B-3）：未 resolved issue -> blocked。
        if await conversation_scope_gate_hits(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        ):
            scan = await self._scan_runtime_bindings(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            body_scan = self._to_transport_scan(scan)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_CONVERSATION_SCOPE_GATE,
                scan=body_scan,
                conversation=conversation,
                now=effective_now,
                # 本 gate 在 _mark_operation_running（bump revision）**之前**检查，
                # 与 B2 同位置 legal-hold 分支对齐——operation revision 尚未 bump，
                # 传 expected_operation_revision 做 revision CAS（B2 D-4 教训）。
                expected_revision=expected_operation_revision,
            )
            return self._blocked_summary(
                fence=fence,
                purge_revision=purge_revision,
                reason=REASON_CONVERSATION_SCOPE_GATE,
                scan=scan,
            )

        # 推进 fence -> erasing（首写 active->erasing；重试 blocked->erasing）。
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
            # E-2a 同一 purge 实例门禁（并发面 P1 C-1）：fence 已 erasing 时必须是
            # **同一 purge_revision**（本 operation 的崩溃后重放，checkpoint ERASING
            # 续做分支继续）——不同 purge_revision 的第二 purge 实例在 fence erasing
            # 下**不得**进入 adapter 窗口（否则两 operation 同时 destroy，E-6「重复
            # 删除」串行化契约）。fence.purge_revision 由 transition_fence_state 写入
            # 推进的 purge_revision，与 operation.purge_revision 对齐校验。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"fence {self.owner_key!r} already erasing under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; concurrent "
                    "purge instance rejected (E-2a same-instance gate)"
                )
        else:
            raise ValueError(
                f"fence {self.owner_key!r} in state {fence.state.value}; "
                "cannot erase runtime session"
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

        # 集合锁（源行 UPDATE 之前，D8 同序）+ 加载 binding 窗口。
        bindings = await self._load_active_bindings(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await self._acquire_inbox_aggregate_locks(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            bindings=bindings,
        )

        # checkpoint -> erasing + attempt += 1 + intent digest（E-2c 镜像）。
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence.owner_version,
        )
        intent_digest = runtime_destroy_intent_digest(bindings)
        if checkpoint.state in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            checkpoint.state = PurgeOwnerState.ERASING.value
            checkpoint.attempt = checkpoint.attempt + 1
            checkpoint.checkpoint_digest = intent_digest
            checkpoint.reason_code = None
            checkpoint.updated_at = effective_now
        elif checkpoint.state == PurgeOwnerState.ERASING.value:
            # 崩溃后重放（同 invocation）：attempt 不变、intent digest 精确相等
            # 才续做；已推进到别的 intent -> fail closed（并发身份不符）。
            if checkpoint.attempt == 0 or checkpoint.checkpoint_digest != intent_digest:
                raise ValueError(
                    "runtime checkpoint already erasing with mismatched intent "
                    "digest/attempt; concurrent erasure takeover rejected"
                )
        else:
            raise ValueError(
                f"runtime checkpoint not erasable from state {checkpoint.state!r}"
            )
        # commit 前捕获 Tx1 身份（attempt），避免 commit 后 ORM 过期影响 Tx2
        # 精确重验比对。
        tx1_attempt = int(checkpoint.attempt)
        await self._session.flush()
        # Tx1 提交释放全部锁（adapter 调用不得持锁做外部 I/O，E-2）。
        await self._session.commit()

        # ===== adapter 调用（无锁，E-2b idempotency key）=====
        outcomes: list[tuple[RuntimeBindingRow, destroy_outcome_union]] = []
        for binding in bindings:
            idempotency_key = runtime_destroy_idempotency_key(
                runtime_session_ref=binding.runtime_session_ref,
                adapter_key=self._adapter.adapter_key,
                adapter_version=self._adapter.adapter_version,
            )
            try:
                outcome: destroy_outcome_union = await self._adapter.destroy_session(
                    runtime_session_ref=binding.runtime_session_ref,
                    idempotency_key=idempotency_key,
                )
            except RuntimeDestroyError as exc:
                outcome = exc
            outcomes.append((binding, outcome))

        # ===== Tx2（第二独立事务：E-2a 精确重验 + 写结果 + 清 ref + ACK）=====
        # E-2a 精确重验必须观察**已提交状态**（并发面 C-1/T-1 返修）：Tx2 是第二独立
        # 事务，但 ORM identity map 会把 Tx1 时期的 checkpoint/operation 对象按 PK
        # 复用，`_load_verified_checkpoint`/`_load_verified_operation` 的 SELECT 返回
        # **未过期实例**（expire_on_commit=False），并发 takeover（另一进程 bump
        # attempt/lease_epoch/intent）无法被 Tx2 重验观测——防双删失效。此处
        # ``expire_all`` 使后续重验按已提交行重读（fence 是 domain 重建不受影响）。
        # 先 expire（清 Tx1 时代 ORM 缓存），**再**重载 Conversation FOR UPDATE
        # （避免 expire_all 后 conversation2 的属性惰性读走无锁 SELECT）。
        self._session.expire_all()
        conversation2 = await self._load_conversation_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        tx2_now = await self._database_now()
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        fence2 = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        if fence2 is None or fence2.state is not ErasureFenceState.ERASING:
            raise ValueError(
                "runtime fence no longer erasing in Tx2; "
                "stale fence rejected (E-2a)"
            )
        if fence2.purge_revision != purge_revision:
            raise ValueError(
                f"fence purge_revision {fence2.purge_revision} != "
                f"operation {purge_revision}; stale purge instance rejected"
            )
        checkpoint2 = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence2.owner_version,
        )
        if checkpoint2.state != PurgeOwnerState.ERASING.value:
            raise ValueError(
                f"runtime checkpoint not erasing in Tx2: {checkpoint2.state!r}"
            )
        if checkpoint2.attempt != tx1_attempt:
            raise ValueError(
                f"checkpoint attempt {checkpoint2.attempt} != Tx1 "
                f"{tx1_attempt}; stale attempt rejected (E-2a)"
            )
        if checkpoint2.checkpoint_digest != intent_digest:
            raise ValueError(
                "checkpoint intent digest no longer matches Tx1; "
                "stale intent rejected (E-2a)"
            )
        await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            conversation_purge_revision=conversation2.purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation2.hold_revision,
        )

        # 集合锁临界区内写 binding + 清 ref（D8 同序）。Tx2 的窗口 = outcomes 的
        # binding 集合（Tx1 已加载、adapter 已调用）——不重复读窗口。
        await self._acquire_inbox_aggregate_locks(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            bindings=[binding for binding, _ in outcomes],
        )

        destroyed_count = 0
        receipt_digests: list[str] = []
        for binding, outcome in outcomes:
            classification = classify_destroy_outcome(outcome)
            state = classification.erase_state
            if state == "erased":
                if not isinstance(outcome, RuntimeDestroySuccess):
                    raise ValueError(
                        "classify_destroy_outcome erased without success evidence"
                    )
                # E-2b「可验证 evidence」：空/空白 evidence 视为无 evidence，fail
                # closed（B2 D-9 教训：不得凭空 evidence 写 erased）。
                if not outcome.adapter_receipt_evidence.strip():
                    raise ValueError(
                        "runtime destroy success without non-empty "
                        "adapter_receipt_evidence; cannot forge erased receipt"
                    )
                idempotency_key = runtime_destroy_idempotency_key(
                    runtime_session_ref=binding.runtime_session_ref,
                    adapter_key=self._adapter.adapter_key,
                    adapter_version=self._adapter.adapter_version,
                )
                receipt_digest = runtime_destroy_receipt_digest(
                    adapter_key=self._adapter.adapter_key,
                    adapter_version=self._adapter.adapter_version,
                    idempotency_key=idempotency_key,
                    adapter_receipt_evidence=outcome.adapter_receipt_evidence,
                    session_digest=runtime_session_identity_digest(
                        binding_id=binding.id,
                        tenant_id=binding.tenant_id,
                        conversation_id=binding.conversation_id,
                        runtime_profile_id=binding.runtime_profile_id,
                        runtime_session_ref=binding.runtime_session_ref,
                    ),
                    destroy_outcome="erased",
                )
                await self._write_erased_and_close_binding(
                    binding=binding,
                    receipt_digest=receipt_digest,
                    tenant_id=tenant_id,
                )
                destroyed_count += 1
                receipt_digests.append(receipt_digest)
            else:
                # blocked/unknown：写 binding 状态（invalid，ref 保留）+ reason 聚合，
                # 不清 ref（E-3a 矩阵镜像；E-3b reconcile/查询在 S5，本 Slice 只写
                # 状态）。
                await self._write_binding_failure(
                    binding=binding,
                    erase_state=state,
                    blocked_reason=classification.blocked_reason,
                    tenant_id=tenant_id,
                )

        # final scan：未 erased 残留 -> conversation 级 blocked；否则 ACK
        # （acked = final scan digest）。
        final_scan = await self._scan_runtime_bindings(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if final_scan.total != 0:
            body_scan = self._to_transport_scan(final_scan)
            reason = self._owner_blocked_reason(outcomes)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation2.hold_revision,
                fence_owner_version=fence2.owner_version,
                reason=reason,
                scan=body_scan,
                conversation=conversation2,
                now=tx2_now,
            )
            await self._session.commit()
            return self._blocked_summary(
                fence=fence2,
                purge_revision=purge_revision,
                reason=reason,
                scan=final_scan,
            )

        # ACK：fence erasing->erased + checkpoint acked。
        summary = RuntimeErasureSummary(
            owner_key=self.owner_key,
            owner_version=fence2.owner_version,
            purge_revision=purge_revision,
            destroyed_bindings=destroyed_count,
            scan=final_scan,
            receipt_digests=tuple(receipt_digests),
        )
        ack_digest = summary.ack_digest()
        fence3 = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence2.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation2.hold_revision,
            ack_digest=ack_digest,
            now=tx2_now,
        )
        await self._ack_owner_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            conversation_purge_revision=conversation2.purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation2.hold_revision,
            fence_owner_version=fence3.owner_version,
            ack_digest=ack_digest,
            checkpoint_digest=final_scan.digest(),
            now=tx2_now,
        )
        await self._session.commit()
        return summary

    # --- binding ref 清除（receipt 后，D5 镜像）------------------------------------

    async def _write_erased_and_close_binding(
        self,
        *,
        binding: RuntimeBindingRow,
        receipt_digest: str,
        tenant_id: uuid.UUID,
    ) -> bool:
        """Tx2：binding identity 重验 -> 清 ref + 关 binding。返回是否实际 close。

        runtime 无独立 erased ledger——binding 行自身即事实源：
        - binding ref 重验：``runtime_session_ref`` 仍为窗口内快照值才清（ref 已
          NULL/缺失可跳过清除，历史兼容——binding 已关但 purge 尚未 ACK 的崩溃恢复）；
          非 NULL 且不匹配 -> **先 fail closed**（不关 binding、不伪造 receipt）。
        - **C-6（并发面返修）**：binding 行**缺失**（`current is None`）是异常态
          （binding 行只由本 participant 关、执行侧不删），fail closed——不得
          no-op 跳过并仍计 destroyed（无本 invocation 可验证 evidence 却计入）。
        - 清 ref + 关 binding（``runtime_session_ref = NULL, status = 'closed'``）+
          **同时清流租约（``active_stream_id = NULL, stream_lease_expires_at =
          NULL``，D-4 返修）**：closed 行不得残留「活跃流租约」外观；两列同 NULL
          满足现 binding CHECK（``ck_agent_runtime_binding_stream_lease``）。
          满足 ``ck_agent_runtime_binding_status``（closed）/ ref NULL 合法。
          **不看 status 前置**——invalid 行（前次 blocked/unknown）重试成功时同样
          可关（blocked -> erased 迁移）。0 行命中 -> 并发推进 -> fail closed。
        """
        # identity 重验必须在写 erased 之前（ref 冲突 -> 不关 binding）。
        current = (
            await self._session.execute(
                text(
                    "SELECT runtime_session_ref FROM "
                    "metaedu.agent_runtime_session_bindings "
                    "WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": binding.id},
            )
        ).scalar_one_or_none()
        if current is None:
            raise ValueError(
                f"runtime binding {binding.id} row missing in Tx2; "
                "binding deleted mid-window (abnormal) -> fail closed"
            )
        if current != binding.runtime_session_ref:
            raise ValueError(
                f"runtime binding {binding.id} runtime_session_ref {current!r} != "
                f"window ref {binding.runtime_session_ref!r}; binding conflict, "
                "refusing to close binding"
            )

        # binding 无 receipt_digest 列（无独立 ledger）——receipt evidence 承载于
        # ACK digest（RuntimeErasureSummary.receipt_digests）+ Tx2 后 final scan
        # digest（checkpoint.checkpoint_digest）。
        result = await self._session.execute(
            text(
                "UPDATE metaedu.agent_runtime_session_bindings "
                "SET runtime_session_ref = NULL, status = 'closed', "
                "  active_stream_id = NULL, stream_lease_expires_at = NULL, "
                "  revision = revision + 1, updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND id = :id "
                "AND runtime_session_ref = :rv"
            ),
            {
                "t": tenant_id,
                "id": binding.id,
                "rv": binding.runtime_session_ref,
            },
        )
        cleared = cast(CursorResult, result).rowcount
        if cleared != 1:
            raise ValueError(
                f"runtime binding {binding.id} close hit {cleared} row(s); "
                "expected 1 (matched ref_value). Concurrent close or ref "
                "clear -> fail closed to keep erased + closed atomic"
            )
        return True

    async def _write_binding_failure(
        self,
        *,
        binding: RuntimeBindingRow,
        erase_state: str,
        blocked_reason: str | None,
        tenant_id: uuid.UUID,
    ) -> None:
        """Tx2：写 ``blocked``/``unknown`` 的 binding 状态（E-3a 矩阵镜像），不清 ref。

        runtime 无独立 ledger 状态列——用 binding 自身 ``status='invalid'`` 表达
        conformance 结果（ref 保留供运维/重试识别）。幂等：已 invalid 行再写
        blocked/unknown 允许（重试路径），仅要求 ref 非空（closed 行不重写）。
        """
        result = await self._session.execute(
            text(
                "UPDATE metaedu.agent_runtime_session_bindings "
                "SET status = 'invalid', revision = revision + 1, "
                "  updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND id = :id "
                "AND runtime_session_ref IS NOT NULL"
            ),
            {"t": tenant_id, "id": binding.id},
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ValueError(
                f"runtime binding {binding.id} not ref-bearing in Tx2 failure write"
            )

    @staticmethod
    def _to_transport_scan(scan: RuntimeBindingScan) -> TransportBodyScan:
        return TransportBodyScan(
            outbox_payload_rows=scan.active_bindings,
            inbox_unsettled_rows=0,
            run_unsettled_rows=0,
        )

    @staticmethod
    def _owner_blocked_reason(
        outcomes: list[tuple[RuntimeBindingRow, destroy_outcome_union]],
    ) -> str:
        """conversation 级 blocked reason 归并（B2 C-7/D-10/T-6 同构）。

        runtime 无 per-binding 持久化 reason 列——从本次 invocation 的 adapter
        outcomes 聚合（E-3a 矩阵）：unknown/timeout 优先 ``outcome_unknown``（请求
        可能已生效，不自动重试）；其次 not-sent ``erase_timeout``（可重试）；再次
        failed ``adapter_unavailable``；纯残留（无本批 outcome 但 scan 非零，如
        并发新 binding）兜底 ``scan_nonzero``。
        """
        has_unknown = any(
            isinstance(outcome, (RuntimeDestroyUnknown, RuntimeDestroyTimeoutError))
            for _, outcome in outcomes
        )
        if has_unknown:
            return REASON_RUNTIME_OUTCOME_UNKNOWN
        has_not_sent = any(
            isinstance(outcome, RuntimeDestroyNotSentError)
            for _, outcome in outcomes
        )
        if has_not_sent:
            return REASON_RUNTIME_ERASE_TIMEOUT
        has_failed = any(
            isinstance(outcome, RuntimeDestroyError)
            for _, outcome in outcomes
        )
        if has_failed:
            return REASON_RUNTIME_ADAPTER_UNAVAILABLE
        return REASON_RUNTIME_BINDING_SCAN_NONZERO

    async def list_blocked_unknown_bindings(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """E-3b 镜像：blocked/unknown binding 查询（``agent_runtime_session_bindings``）。

        返回 ``status='invalid'`` 且 ``runtime_session_ref IS NOT NULL`` 的 binding
        行（ref 保留、外部 session 未确认清除，交运维/人工确认）。HTTP/CLI 接线归
        S5，本 Slice 只提供查询能力与测试。
        """
        sql = (
            "SELECT id, conversation_id, runtime_profile_id, runtime_session_ref, "
            "  status, current_epoch, next_expected_runtime_seq, "
            "  acked_through_runtime_seq "
            "FROM metaedu.agent_runtime_session_bindings "
            "WHERE tenant_id = :t AND status = 'invalid' "
            "  AND runtime_session_ref IS NOT NULL"
        )
        params: dict = {"t": tenant_id}
        if conversation_id is not None:
            sql += " AND conversation_id = :c"
            params["c"] = conversation_id
        rows = (
            await self._session.execute(text(sql + " ORDER BY updated_at"), params)
        ).mappings().all()
        return [dict(row) for row in rows]

    async def reconcile_runtime_binding(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
    ) -> str:
        """E-3b 镜像：有证据 reconcile——仅当 adapter ``receipt lookup`` 返回可验证
        evidence 时补写 erased（清 ref + 关 binding）；**禁止无 receipt 强制 erased**。

        返回补写后的 binding ``status``：receipt 可得 -> ``closed``（ref 已清）；无
        receipt -> 保持原状态（invalid 不动，交运维/人工确认）。锁序：写 binding +
        清 ref 前按源行取集合 advisory lock（``runtime.private.v1``，D8 同序）；
        **持锁期间不执行外部 I/O**——receipt lookup 在取锁前无锁调用。
        """
        # 先无锁查 evidence（receipt lookup 是外部 I/O，E-2「禁持锁做外部 I/O」）。
        row = (
            await self._session.execute(
                text(
                    "SELECT id, conversation_id, runtime_profile_id, "
                    "runtime_session_ref, status "
                    "FROM metaedu.agent_runtime_session_bindings "
                    "WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": binding_id},
            )
        ).mappings().one_or_none()
        if row is None:
            raise ValueError(f"runtime binding {binding_id} not found for reconcile")
        ref = row["runtime_session_ref"]
        if ref is None or row["status"] == "closed":
            return row["status"]  # 已终态 no-op
        if not self._adapter.supports_receipt_lookup:
            return row["status"]
        idempotency_key = runtime_destroy_idempotency_key(
            runtime_session_ref=ref,
            adapter_key=self._adapter.adapter_key,
            adapter_version=self._adapter.adapter_version,
        )
        evidence = await self._adapter.receipt_lookup(
            idempotency_key=idempotency_key
        )
        if evidence is None or not evidence.strip():
            return row["status"]  # 无 receipt / 空 evidence，禁止强制 erased
        # 有证据：取集合锁（D8）+ 锁内校验 + 补写（清 ref + 关 binding）。
        await acquire_transport_aggregate_lock(
            self._session,
            tenant_id=tenant_id,
            owner_key=RUNTIME_PRIVATE_OWNER,
            source_table="agent_runtime_session_bindings",
            source_row_id=binding_id,
        )
        result = await self._session.execute(
            text(
                "UPDATE metaedu.agent_runtime_session_bindings "
                "SET runtime_session_ref = NULL, status = 'closed', "
                "  revision = revision + 1, updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND id = :id "
                "AND runtime_session_ref = :rv"
            ),
            {"t": tenant_id, "id": binding_id, "rv": ref},
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ValueError(
                f"runtime binding {binding_id} reconcile close hit "
                f"{cast(CursorResult, result).rowcount} row(s); concurrent close "
                "or ref change -> fail closed"
            )
        return "closed"

    def _blocked_summary(
        self,
        *,
        fence,
        purge_revision: int,
        reason: str,
        scan: RuntimeBindingScan,
    ) -> RuntimeErasureSummary:
        return RuntimeErasureSummary(
            owner_key=self.owner_key,
            owner_version=fence.owner_version,
            purge_revision=purge_revision,
            destroyed_bindings=0,
            scan=scan,
        )

    def _summary_from_fence(
        self,
        *,
        fence,
        purge_revision: int,
        destroyed_bindings: int,
        scan: RuntimeBindingScan,
    ) -> RuntimeErasureSummary:
        return RuntimeErasureSummary(
            owner_key=self.owner_key,
            owner_version=fence.owner_version,
            purge_revision=purge_revision,
            destroyed_bindings=destroyed_bindings,
            scan=scan,
        )
