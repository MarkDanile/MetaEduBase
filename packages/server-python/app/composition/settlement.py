"""R1-S5 SCH-D：SettlementService——S5-C Settlement & Retry-Reconcile concrete adapter。

契约：R1-S5-C S5-C-0..9。本服务是 SCH-B ``SettlementPort``（``closeout_erasing`` /
``converge_failed_fence``）的 concrete 实现，只写 owner-scoped 事实（checkpoint /
fence），**禁写 operation/Conversation 投影**（S5-C-2 写域）；不重写 SCH-B/C
状态机。

锁序（S5-C-7 scheduler settlement 行）：Conversation FOR UPDATE → owner advisory
→ fence FOR UPDATE → operation FOR UPDATE → checkpoint FOR UPDATE。

drift 绕过（S5-C-2，settlement 是唯一绕过者）：frozen-snapshot 基准六条校验，
不以已安装 registry / Conversation 当前 hold_revision 等值校验拒 settlement。

输出态（S5-C-1 全函数）：
  1 success（adapter evidence / lookup evidence）→ fence erasing→erased +
    checkpoint→acked
  2 可证明未发送（否定证据 / 已持久 reopenable reason）→ checkpoint blocked +
    fence erasing→blocked
  3 outcome_unknown（lookup None / unknown / 无恢复能力）→ blocked +
    outcome_unknown + fence erasing→blocked
  4 ACK-lost repair（fence erased + ack 存在 + final scan 零）→ checkpoint→acked，
    fence 零修改
  5 恢复超时（deadline 过期，进入点判定）→ blocked + settlement_deadline_expired
    + fence erasing→blocked
  6 adapter 不可解析（resolver 缺失 / 实现不可加载）→ blocked +
    adapter_unresolvable + fence erasing→blocked

生产 wiring 不可达：默认 adapter resolver = ``FailClosedAdapterResolver``（一律输出
态 6），测试经显式注入 fake adapter 覆盖态 1/2/3/5/6。本服务不 commit()（事务
原子性归调用方）。

idempotency key 对齐（R1-S5 root integration）：settlement 重读 participant Tx1 的
冻结 ref/binding 窗口（external ``registered`` refs / runtime active bindings），以
**frozen descriptor** 的 ``adapter_key``/``adapter_version`` 逐 ref 派生
``external_erase_idempotency_key`` / ``runtime_destroy_idempotency_key``，**不含
tenant_id/conversation_id/lease_epoch/attempt**；adapter 调用携带 participant Tx1
所需稳定 ref 输入。E-2a 冻结 intent 重验：重读集合的 intent digest 必须等于
checkpoint 冻结 token，缺失/不一致 fail closed（禁新 Tx1，不 fallback
conversation 级简化 key）。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.adapter_recovery import (
    AdapterImplementationResolver,
    AdapterUnresolvableError,
    FailClosedAdapterResolver,
    RecoveryDescriptor,
    resolve_adapter,
)
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    snapshot_digest,
)
from app.composition.external_object_adapter import external_erase_idempotency_key
from app.composition.external_ref_erasure_participant import (
    ExternalRefRow,
    external_delete_intent_digest,
)
from app.composition.runtime_erasure_adapter import runtime_destroy_idempotency_key
from app.composition.runtime_erasure_participant import (
    RuntimeBindingRow,
    runtime_destroy_intent_digest,
)
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ErasureFenceModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.shared.schemas.canonical_json import canonical_digest

# S5-C-1 输出态 3/5/6 reason（level 7，external/runtime 各一）。已落账 post-window
# blocked 的 reason 归入态 2/3/5/6（按已持久 reason，不覆写）。
_REASON_OUTCOME_UNKNOWN_EXTERNAL = "purge_blocked_by_external_outcome_unknown"
_REASON_OUTCOME_UNKNOWN_RUNTIME = "purge_blocked_by_runtime_outcome_unknown"
_REASON_DEADLINE_EXTERNAL = "purge_blocked_by_external_settlement_deadline_expired"
_REASON_DEADLINE_RUNTIME = "purge_blocked_by_runtime_settlement_deadline_expired"
_REASON_UNRESOLVABLE_EXTERNAL = "purge_blocked_by_external_adapter_unresolvable"
_REASON_UNRESOLVABLE_RUNTIME = "purge_blocked_by_runtime_adapter_unresolvable"
_REASON_ERASE_TIMEOUT_EXTERNAL = "purge_blocked_by_external_erase_timeout"
_REASON_ERASE_TIMEOUT_RUNTIME = "purge_blocked_by_runtime_erase_timeout"

# S5-C-1 输入态 2「4 非 core owner」；core owner 的 scan-nonzero 落账已写 fence。
_NON_CORE_OWNERS = frozenset(
    {"workspace.transport.v1", "execution.transport.v1",
     "external.payload.v1", "runtime.private.v1"}
)
# 窗口态 owner（adapter 窗口）：external/runtime（Tx1 后未收口）。
_WINDOW_OWNERS = frozenset({"external.payload.v1", "runtime.private.v1"})

# 已落账 post-window blocked reason → 输出态归类（S5-C-1 已落账收敛规则）。
_CARRY_REASON_PREFIXES = ("_outcome_unknown", "_settlement_deadline_expired",
                          "_adapter_unresolvable")
_REOPENABLE_REASON_SUFFIXES = ("_erase_timeout", "_adapter_unavailable",
                               "_scan_nonzero")


class _FrozenSnapshot:
    """S5-C-2 frozen-snapshot 基准：operation 冻结 snapshot 中该 owner 的条目。"""

    __slots__ = ("owner_version", "capability_digest", "purge_revision")

    def __init__(self, *, owner_version: int, capability_digest: str,
                 purge_revision: int) -> None:
        self.owner_version = owner_version
        self.capability_digest = capability_digest
        self.purge_revision = purge_revision


class OutputState(StrEnum):
    SUCCESS = "success"
    PROVABLY_NOT_SENT = "not_sent"
    OUTCOME_UNKNOWN = "outcome_unknown"
    ACK_LOST_REPAIRED = "ack_lost_repaired"
    DEADLINE_EXPIRED = "deadline_expired"
    ADAPTER_UNRESOLVABLE = "adapter_unresolvable"


@dataclass(frozen=True, slots=True)
class _WindowOutcome:
    state: OutputState
    reason: str | None = None
    ack_digest: str | None = None
    scan_digest: str | None = None


# settlement 可重放的 adapter 接口（external/runtime Protocol 的窄投影）。
class _RecoverableAdapter(Protocol):
    supports_idempotent_replay: bool
    supports_receipt_lookup: bool

    async def receipt_lookup(self, *, idempotency_key: str) -> str | None: ...

    async def delete_object(self, **kwargs) -> object: ...

    async def destroy_session(self, **kwargs) -> object: ...


class _ScanResult(Protocol):
    """final scan 结果窄投影（total + digest），六 owner scan 对象均满足。"""

    @property
    def total(self) -> int: ...

    def digest(self) -> str: ...


ScanProvider = Callable[..., Awaitable[_ScanResult]]


@dataclass(frozen=True, slots=True)
class _RefOutcome:
    """单个冻结 ref/binding 的恢复结果（窗口重放后逐项判定）。"""

    state: OutputState
    ack_evidence: str | None = None


class SettlementService:
    """S5-C settlement concrete adapter（implements ``SettlementPort``）。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        scan_providers: Mapping[str, ScanProvider],
        adapter_resolver: AdapterImplementationResolver | None = None,
        now: datetime | None = None,
    ) -> None:
        self._session = session
        self._repo = AgentErasureRepository(session)
        self._scan_providers = scan_providers
        self._adapter_resolver = adapter_resolver or FailClosedAdapterResolver()
        self._now = now

    # -- SettlementPort ------------------------------------------------------

    async def closeout_erasing(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> None:
        """S5-C settlement 主入口：锁内重读 → frozen-snapshot 校验 → 输入态分类
        → 输出态落账（fence/checkpoint CAS 单写收敛）。"""
        conversation = await self._lock_conversation(tenant_id, conversation_id)
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for settlement"
            )
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        fence = await self._fence_for_update(tenant_id, conversation_id, owner_key)
        operation = await self._operation_for_update(
            tenant_id, purge_operation_id, conversation_id
        )
        checkpoint = await self._checkpoint_for_update(
            tenant_id, purge_operation_id, owner_key
        )

        # S5-C-2 frozen-snapshot 校验（六条）；失败 fail closed 零写。
        frozen = self._validate_frozen_snapshot(
            conversation, operation, fence, checkpoint, owner_key
        )
        assert operation is not None, "frozen-snapshot 校验保证 operation 存在"

        # 输入态分类（S5-C-1 三类）。
        input_state = self._classify_input(checkpoint, fence)
        if input_state is None:
            return  # 已收敛/无关/缺 fence → 零写幂等

        if input_state == "ack_lost":
            assert fence is not None, "ack_lost 输入态必有 erased fence"
            assert checkpoint is not None, "ack_lost 输入态必有 checkpoint"
            await self._ack_lost_repair(
                tenant_id, conversation_id, operation, checkpoint, fence, frozen,
                owner_key,
            )
            return
        if input_state == "post_window_blocked":
            assert fence is not None, "post_window_blocked 输入态必有 erasing fence"
            # S5-C-1 已落账收敛：只写 fence erasing→blocked，checkpoint 零修改。
            await self._fence_to_blocked(
                tenant_id, conversation_id, fence, frozen, conversation.hold_revision
            )
            return

        # window erasing（checkpoint 或 fence erasing）→ adapter recovery。
        assert fence is not None, "window_erasing 输入态必有 erasing fence"
        outcome = await self._recover_erasing(
            tenant_id, conversation_id, operation, checkpoint, fence, frozen,
            owner_key,
        )
        await self._apply_window_outcome(
            tenant_id, conversation_id, operation, checkpoint, fence, frozen,
            conversation.hold_revision, owner_key, outcome,
        )

    async def converge_failed_fence(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> None:
        """S5-C-1 failed 收敛：checkpoint=failed 且 fence 仍 erasing → 写 fence
        erasing→blocked（checkpoint 零修改，failed 保留）。(failed, blocked)/
        (failed, active) 零写；矛盾组合零写 fail closed。"""
        conversation = await self._lock_conversation(tenant_id, conversation_id)
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for failed convergence"
            )
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        fence = await self._fence_for_update(tenant_id, conversation_id, owner_key)
        operation = await self._operation_for_update(
            tenant_id, purge_operation_id, conversation_id
        )
        checkpoint = await self._checkpoint_for_update(
            tenant_id, purge_operation_id, owner_key
        )
        frozen = self._validate_frozen_snapshot(
            conversation, operation, fence, checkpoint, owner_key
        )
        if checkpoint is None or checkpoint.state != "failed":
            return  # 非 failed → 零写
        if fence is None or fence.state != "erasing":
            return  # (failed, blocked)/(failed, active) 零写；矛盾组合零写
        await self._fence_to_blocked(
            tenant_id, conversation_id, fence, frozen, conversation.hold_revision
        )

    # -- 内部：锁与冻结校验 ------------------------------------------------

    async def _lock_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationModel | None:
        return (
            await self._session.execute(
                select(ConversationModel)
                .where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _operation_for_update(
        self, tenant_id: uuid.UUID, purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> PurgeOperationModel | None:
        return (
            await self._session.execute(
                select(PurgeOperationModel)
                .where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.id == purge_operation_id,
                    PurgeOperationModel.conversation_id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _fence_for_update(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, owner_key: str
    ) -> ErasureFenceModel | None:
        return (
            await self._session.execute(
                select(ErasureFenceModel)
                .where(
                    ErasureFenceModel.tenant_id == tenant_id,
                    ErasureFenceModel.conversation_id == conversation_id,
                    ErasureFenceModel.owner_key == owner_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _checkpoint_for_update(
        self, tenant_id: uuid.UUID, purge_operation_id: uuid.UUID, owner_key: str
    ) -> PurgeOwnerCheckpointModel | None:
        return (
            await self._session.execute(
                select(PurgeOwnerCheckpointModel)
                .where(
                    PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                    PurgeOwnerCheckpointModel.purge_operation_id
                    == purge_operation_id,
                    PurgeOwnerCheckpointModel.owner_key == owner_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _database_now(self) -> datetime:
        if self._now is not None:
            return self._now
        return (
            await self._session.execute(text("SELECT clock_timestamp()"))
        ).scalar_one()

    def _frozen_entry(
        self, operation: PurgeOperationModel, owner_key: str
    ) -> _FrozenSnapshot:
        """S5-C-2 第 1/4/5 条：operation 冻结 snapshot 中该 owner 的条目。"""
        for entry in operation.registry_snapshot:
            if entry["owner_key"] == owner_key:
                return _FrozenSnapshot(
                    owner_version=int(entry["owner_version"]),
                    capability_digest=str(entry["capability_digest"]),
                    purge_revision=operation.purge_revision,
                )
        raise ValueError(
            f"owner {owner_key!r} not in operation frozen snapshot; "
            "settlement fail closed"
        )

    def _validate_frozen_snapshot(
        self,
        conversation: ConversationModel,
        operation: PurgeOperationModel | None,
        fence: ErasureFenceModel | None,
        checkpoint: PurgeOwnerCheckpointModel | None,
        owner_key: str,
    ) -> _FrozenSnapshot:
        """S5-C-2 六条 frozen-snapshot 校验（drift 绕过集，任一失败 fail closed）。"""
        if operation is None:
            raise ValueError("operation not found for settlement; fail closed")
        # 1. 旧 operation 仍为 top revision。
        if operation.purge_revision != conversation.purge_revision:
            raise ValueError(
                "operation purge_revision != conversation purge_revision; "
                "settlement on stale operation rejected"
            )
        # 2. conversation 归属 + 状态域。
        if operation.conversation_id != conversation.id:
            raise ValueError("operation conversation_id mismatch; fail closed")
        if operation.state not in ("scheduled", "running", "blocked"):
            raise ValueError(
                f"operation not settleable from terminal state {operation.state!r}"
            )
        # 3. lease liveness（锁内重读；settlement 由 orchestrator 续租后进入）。
        if operation.lease_epoch < 1 or operation.lease_expires_at is None:
            raise ValueError("operation lease not held; settlement fail closed")
        # 4. frozen-snapshot 自洽 + checkpoint 侧同基准。
        if snapshot_digest(list(operation.registry_snapshot)) != operation.registry_digest:
            raise ValueError(
                "operation registry snapshot/digest mismatch; tampered snapshot, "
                "settlement fail closed"
            )
        if operation.hold_revision_snapshot > conversation.hold_revision:
            raise ValueError(
                "operation hold_revision_snapshot > conversation hold_revision; "
                "hold regression, settlement fail closed"
            )
        frozen = self._frozen_entry(operation, owner_key)
        if checkpoint is not None:
            if checkpoint.owner_version != frozen.owner_version:
                raise ValueError(
                    f"checkpoint owner_version {checkpoint.owner_version} != frozen "
                    f"{frozen.owner_version}; settlement fail closed"
                )
            if checkpoint.capability_digest != frozen.capability_digest:
                raise ValueError(
                    "checkpoint capability_digest != frozen snapshot; settlement "
                    "fail closed"
                )
        # 5. fence 同 revision + owner_version 冻结基准 + checkpoint 精确 token。
        if fence is not None:
            if fence.purge_revision != frozen.purge_revision:
                raise ValueError(
                    f"fence purge_revision {fence.purge_revision} != operation "
                    f"{frozen.purge_revision}; cross-purge-instance settlement "
                    "rejected"
                )
            if fence.owner_version != frozen.owner_version:
                raise ValueError(
                    f"fence owner_version {fence.owner_version} != frozen "
                    f"{frozen.owner_version}; settlement fail closed"
                )
        # E-2a 精确 attempt/intent token：续做同一 invocation 的硬前置（禁新 Tx1）。
        if (
            checkpoint is not None
            and checkpoint.state == "erasing"
            and (checkpoint.attempt < 1 or checkpoint.checkpoint_digest is None)
        ):
            raise ValueError(
                "erasing checkpoint lacks attempt/intent token; new Tx1 "
                "rejected by settlement channel"
            )
        return frozen

    # -- 输入态分类 ---------------------------------------------------------

    def _classify_input(
        self,
        checkpoint: PurgeOwnerCheckpointModel | None,
        fence: ErasureFenceModel | None,
    ) -> str | None:
        """S5-C-1 输入态：ack_lost / post_window_blocked / window_erasing / None。"""
        if fence is None:
            return None  # 无 fence = 无 settlement 输入态
        if fence.state == "erased":
            # ACK-lost：fence erased + checkpoint pending/blocked（同 revision 已
            # 由 frozen 校验保证）。
            if checkpoint is not None and checkpoint.state in ("pending", "blocked"):
                return "ack_lost"
            return None
        if fence.state == "erasing":
            if checkpoint is None:
                # fence erasing + 缺 checkpoint → 按窗口态处理（不可判定）。
                return "window_erasing"
            if checkpoint.state == "blocked":
                return "post_window_blocked"
            if checkpoint.state == "erasing":
                return "window_erasing"
            # pending/failed/acked + fence erasing → 矛盾/已收敛；failed 由
            # converge_failed_fence 处理，其余零写。
            return None
        return None  # active/blocked fence → 无 settlement 输入态

    # -- 落账 ---------------------------------------------------------------

    async def _fence_to_blocked(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        fence: ErasureFenceModel | None,
        frozen: _FrozenSnapshot,
        hold_revision: int,
    ) -> None:
        """S5-C-7 erasing→blocked 边 + S5-C-1 例外条款（settlement 专用 fence 写）。

        fence 写本身无法完成（行缺失 / CAS 永久冲突，经 S5-C-2 校验后仍失败）→
        **不 raise**：checkpoint 已按进入时判定的输出态落账（具名持久 reason），
        fence 保持 erasing——具名 reconcile（可观察、禁止自动重试），零 adapter
        再调用。态 1/4 不适用本条款（态 4 fence 零修改；态 1 同事务失败整事务
        回滚由调用方承担，不在此捕获）。
        """
        if fence is None or fence.state != "erasing":
            return
        try:
            await self._repo.transition_fence_state_settlement(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=fence.owner_key,
                expected_state=ErasureFenceState.ERASING,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.BLOCKED,
                expected_owner_version=frozen.owner_version,
                purge_revision=frozen.purge_revision,
                hold_revision=hold_revision,
                now=await self._database_now(),
            )
        except ValueError:
            # S5-C-1 例外条款：fence 写失败 → 具名 reconcile（checkpoint 已落账
            # 输出态 reason），零自动重试。
            return

    async def _ack_lost_repair(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        operation: PurgeOperationModel,
        checkpoint: PurgeOwnerCheckpointModel,
        fence: ErasureFenceModel,
        frozen: _FrozenSnapshot,
        owner_key: str,
    ) -> None:
        """S5-C-7 ACK-lost repair（第三路径）：只修 checkpoint，fence 零修改，
        不清 operation failure_code、不写 Conversation 投影。"""
        ack_digest = fence.ack_digest
        if not ack_digest:
            raise ValueError(
                f"erased fence {owner_key!r} missing ack_digest; ACK-lost repair "
                "evidence missing, fail closed reconcile"
            )
        scan_provider = self._scan_providers.get(owner_key)
        if scan_provider is None:
            raise ValueError(f"no scan provider for {owner_key!r}; wiring incomplete")
        scan = await scan_provider(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if scan.total != 0:
            raise ValueError(
                f"erased fence {owner_key!r} but final scan non-zero "
                f"(total={scan.total}); body leaked after erase, cannot repair "
                "checkpoint on a non-empty body"
            )
        scan_digest = scan.digest()
        # I2 后只修 checkpoint：state/ack_digest/checkpoint_digest/reason，零
        # operation/Conversation/failure_code 写。
        checkpoint.state = "acked"
        checkpoint.ack_digest = ack_digest
        checkpoint.checkpoint_digest = scan_digest
        checkpoint.reason_code = None
        checkpoint.updated_at = await self._database_now()
        await self._session.flush()

    async def _recover_erasing(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        operation: PurgeOperationModel,
        checkpoint: PurgeOwnerCheckpointModel | None,
        fence: ErasureFenceModel,
        frozen: _FrozenSnapshot,
        owner_key: str,
    ) -> _WindowOutcome:
        """S5-C-3/4/5/6：窗口态 adapter recovery（descriptor → deadline →
        frozen ref/session 重读 + E-2a intent 重验 → 逐 ref lookup/replay）。
        输出态 1/2/3/5/6。"""
        try:
            descriptor = resolve_adapter(owner_key, frozen.owner_version)
        except AdapterUnresolvableError:
            return _WindowOutcome(
                OutputState.ADAPTER_UNRESOLVABLE,
                reason=_unresolvable_reason(owner_key),
            )

        # 仅 external/runtime 窗口态适用 deadline/恢复。
        if owner_key not in _WINDOW_OWNERS:
            # transport/core owner 无 adapter 窗口 → 无恢复能力，落 outcome_unknown
            # 由 fence 收敛（checkpoint 保持 blocked carry 语义）。
            return _WindowOutcome(
                OutputState.OUTCOME_UNKNOWN,
                reason=_outcome_unknown_reason(owner_key),
            )

        # S5-C-4 进入点判定：checkpoint 仍 erasing 且本 settlement 尚未修改
        # checkpoint.updated_at 时才允许 deadline 判定。
        if checkpoint is not None and checkpoint.state == "erasing":
            now = await self._database_now()
            if now > checkpoint.updated_at + descriptor.settlement_deadline:
                return _WindowOutcome(
                    OutputState.DEADLINE_EXPIRED,
                    reason=_deadline_reason(owner_key),
                )

        # E-2a 禁新 Tx1：窗口 owner 必须有冻结 checkpoint intent token；缺失
        # （checkpoint 行缺失）→ fail closed 零 adapter 调用。
        if checkpoint is None:
            raise ValueError(
                "erasing window without frozen checkpoint intent; "
                "new Tx1 rejected by settlement channel"
            )

        try:
            raw_adapter = self._adapter_resolver(
                owner_key=owner_key, owner_version=frozen.owner_version
            )
        except AdapterUnresolvableError:
            return _WindowOutcome(
                OutputState.ADAPTER_UNRESOLVABLE,
                reason=_unresolvable_reason(owner_key),
            )
        adapter = cast(_RecoverableAdapter, raw_adapter)

        # 冻结 ref/session 输入：重读 Tx1 冻结窗口并精确重验 intent digest
        # （缺失/不一致 → fail closed，不 fallback conversation 级简化 key）。
        frozen_inputs = await self._load_frozen_window(
            tenant_id, conversation_id, owner_key
        )
        self._verify_frozen_intent(checkpoint, frozen_inputs, owner_key)

        # S5-C-3/5/6：恢复能力位以 **frozen descriptor** 为准（receipt_lookup
        # 语义版本非空 ⇔ supports_receipt_lookup；adapter 实例只是可调用载体，
        # 其自身标志不参与语义判定——部署新版本后旧 settlement 仍按旧 descriptor）。
        supports_lookup = descriptor.supports_receipt_lookup
        supports_replay = descriptor.supports_idempotent_replay

        ref_outcomes = [
            await self._recover_ref(
                adapter, owner_key, descriptor, ref, supports_lookup, supports_replay
            )
            for ref in frozen_inputs
        ]
        return self._aggregate_window(ref_outcomes, owner_key)

    # -- 冻结 ref/session 输入（E-2a 禁新 Tx1）--------------------------------

    async def _load_frozen_window(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> list[ExternalRefRow] | list[RuntimeBindingRow]:
        """重读 participant Tx1 的冻结 adapter 窗口（与 Tx1 同窗、同序）。

        external：``erase_state='registered'`` 的 ledger 行；runtime：
        ``runtime_session_ref IS NOT NULL AND status NOT IN ('closed','invalid')``
        binding 行。窗口 owner 之外的 owner 无此窗口 → fail closed。
        """
        if owner_key == "external.payload.v1":
            rows = (
                await self._session.execute(
                    text(
                        "SELECT id, conversation_id, ref_scheme, ref_value, "
                        "source_table, source_row_id "
                        "FROM metaedu.agent_external_object_refs "
                        "WHERE tenant_id = :t AND conversation_id = :c "
                        "AND erase_state = 'registered' ORDER BY id"
                    ),
                    {"t": tenant_id, "c": conversation_id},
                )
            ).mappings().all()
            return [
                ExternalRefRow(
                    id=row["id"],
                    tenant_id=tenant_id,
                    conversation_id=row["conversation_id"],
                    ref_scheme=row["ref_scheme"],
                    ref_value=row["ref_value"],
                    source_table=row["source_table"],
                    source_row_id=row["source_row_id"],
                )
                for row in rows
            ]
        if owner_key == "runtime.private.v1":
            rows = (
                await self._session.execute(
                    text(
                        "SELECT id, runtime_profile_id, runtime_session_ref "
                        "FROM metaedu.agent_runtime_session_bindings "
                        "WHERE tenant_id = :t AND conversation_id = :c "
                        "AND runtime_session_ref IS NOT NULL "
                        "AND status NOT IN ('closed', 'invalid') ORDER BY id"
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
        raise ValueError(f"owner {owner_key!r} has no adapter ref window; fail closed")

    def _verify_frozen_intent(
        self,
        checkpoint: PurgeOwnerCheckpointModel,
        frozen_inputs: list[ExternalRefRow] | list[RuntimeBindingRow],
        owner_key: str,
    ) -> None:
        """E-2a：重读冻结集合的 intent digest 与 checkpoint 冻结 token 精确一致。

        任一 ref 缺失/新增/状态迁移导致集合变化 → intent 不匹配 → fail closed
        零 adapter 调用（**禁新 Tx1**，不 fallback conversation 级简化 key）。
        """
        if owner_key == "external.payload.v1":
            intent = external_delete_intent_digest(
                cast(list[ExternalRefRow], frozen_inputs)
            )
        elif owner_key == "runtime.private.v1":
            intent = runtime_destroy_intent_digest(
                cast(list[RuntimeBindingRow], frozen_inputs)
            )
        else:
            raise ValueError(f"owner {owner_key!r} has no frozen intent domain")
        if checkpoint.checkpoint_digest != intent:
            raise ValueError(
                f"frozen {owner_key!r} intent digest mismatch: checkpoint "
                f"{checkpoint.checkpoint_digest} != re-derived {intent}; "
                "ref/session inputs missing or inconsistent, settlement fail closed"
            )

    def _frozen_ref_key(
        self,
        owner_key: str,
        descriptor: RecoveryDescriptor,
        ref: ExternalRefRow | RuntimeBindingRow,
    ) -> str:
        """E-2b：单 ref/binding 的跨 takeover 稳定 idempotency key。

        **只含冻结 ref 身份 + frozen descriptor 协议身份**（不含 tenant_id/
        conversation_id/lease_epoch/attempt），与 participant Tx1 派生输入完全一致。
        """
        if owner_key == "runtime.private.v1":
            assert isinstance(ref, RuntimeBindingRow), "runtime window must be bindings"
            return runtime_destroy_idempotency_key(
                runtime_session_ref=ref.runtime_session_ref,
                adapter_key=descriptor.adapter_key,
                adapter_version=descriptor.adapter_version,
            )
        assert isinstance(ref, ExternalRefRow), "external window must be refs"
        return external_erase_idempotency_key(
            ref_scheme=ref.ref_scheme,
            ref_value=ref.ref_value,
            adapter_key=descriptor.adapter_key,
            adapter_version=descriptor.adapter_version,
        )

    async def _recover_ref(
        self,
        adapter: _RecoverableAdapter,
        owner_key: str,
        descriptor: RecoveryDescriptor,
        ref: ExternalRefRow | RuntimeBindingRow,
        supports_lookup: bool,
        supports_replay: bool,
    ) -> _RefOutcome:
        """单个冻结 ref 的恢复：S5-C-5 lookup 三态 + S5-C-6 replay（同 key）。"""
        key = self._frozen_ref_key(owner_key, descriptor, ref)
        if supports_lookup:
            # S5-C-5：evidence → success；None → 不可判定，仅当 replay 能力 + 去重
            # 窗口充足才 replay；否定证据（明确「未发送」）→ 态 2（当前
            # receipt_lookup 仅 evidence/None，否定证据需 Protocol 扩展后落地）。
            evidence = await adapter.receipt_lookup(idempotency_key=key)
            if evidence is not None:
                return _RefOutcome(OutputState.SUCCESS, ack_evidence=str(evidence))
            if (
                supports_replay
                and descriptor.dedup_window >= descriptor.settlement_deadline
            ):
                replayed = await self._replay_ref(adapter, owner_key, ref, key)
                if replayed is not None:
                    return _RefOutcome(OutputState.SUCCESS, ack_evidence=replayed)
            return _RefOutcome(OutputState.OUTCOME_UNKNOWN)
        if supports_replay:
            # S5-C-6 replay-only：去重窗口 ≥ deadline 才 replay；窗口不足 → 态 3。
            if descriptor.dedup_window >= descriptor.settlement_deadline:
                replayed = await self._replay_ref(adapter, owner_key, ref, key)
                if replayed is not None:
                    return _RefOutcome(OutputState.SUCCESS, ack_evidence=replayed)
            return _RefOutcome(OutputState.OUTCOME_UNKNOWN)
        # 无恢复能力 → 态 3（reconcile-only）。
        return _RefOutcome(OutputState.OUTCOME_UNKNOWN)

    async def _replay_ref(
        self,
        adapter: _RecoverableAdapter,
        owner_key: str,
        ref: ExternalRefRow | RuntimeBindingRow,
        idempotency_key: str,
    ) -> str | None:
        """S5-C-6 replay：adapter 调用必须携带 participant Tx1 所需稳定 ref 输入
        （不得只传 key）；成功 evidence → 返回，unknown/异常 → None。"""
        try:
            if owner_key == "runtime.private.v1":
                assert isinstance(ref, RuntimeBindingRow), "runtime window must be bindings"
                result = await adapter.destroy_session(
                    runtime_session_ref=ref.runtime_session_ref,
                    idempotency_key=idempotency_key,
                )
            else:
                assert isinstance(ref, ExternalRefRow), "external window must be refs"
                result = await adapter.delete_object(
                    ref_scheme=ref.ref_scheme,
                    ref_value=ref.ref_value,
                    idempotency_key=idempotency_key,
                )
        except Exception:
            return None
        evidence = getattr(result, "adapter_receipt_evidence", None) or getattr(
            result, "destroy_receipt_evidence", None
        )
        return str(evidence) if evidence else None

    def _aggregate_window(
        self,
        ref_outcomes: list[_RefOutcome],
        owner_key: str,
    ) -> _WindowOutcome:
        """owner 级聚合：任一 ref 不可判定 → 态 3；全部确认 → 态 1。

        单 ref 的 ack evidence 原样承载；多 ref 合并为确定性 canonical digest
        （与 lookup/replay 同一 per-ref key 派生链）。
        """
        if any(o.state is OutputState.OUTCOME_UNKNOWN for o in ref_outcomes):
            return _WindowOutcome(
                OutputState.OUTCOME_UNKNOWN,
                reason=_outcome_unknown_reason(owner_key),
            )
        evidences = [o.ack_evidence for o in ref_outcomes if o.ack_evidence]
        if len(evidences) == 1:
            ack = evidences[0]
        else:
            ack = canonical_digest(
                {
                    "schema_version": 1,
                    "kind": "settlement:ack",
                    "receipts": sorted(evidences),
                }
            )
        return _WindowOutcome(OutputState.SUCCESS, ack_digest=ack)

    async def _apply_window_outcome(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        operation: PurgeOperationModel,
        checkpoint: PurgeOwnerCheckpointModel | None,
        fence: ErasureFenceModel,
        frozen: _FrozenSnapshot,
        hold_revision: int,
        owner_key: str,
        outcome: _WindowOutcome,
    ) -> None:
        """S5-C-1 输出态落账：fence + checkpoint CAS 单写收敛。"""
        now = await self._database_now()
        if outcome.state is OutputState.SUCCESS:
            # 态 1：fence erasing→erased（ack_digest）+ checkpoint→acked。
            ack = outcome.ack_digest
            if not ack:
                raise ValueError("success outcome missing ack evidence")
            if fence.state == "erasing":
                await self._repo.transition_fence_state_settlement(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    owner_key=owner_key,
                    expected_state=ErasureFenceState.ERASING,
                    expected_revision=fence.revision,
                    new_state=ErasureFenceState.ERASED,
                    expected_owner_version=frozen.owner_version,
                    purge_revision=frozen.purge_revision,
                    hold_revision=hold_revision,
                    ack_digest=ack,
                    now=now,
                )
            if checkpoint is not None and checkpoint.state != "acked":
                checkpoint.state = "acked"
                checkpoint.ack_digest = ack
                checkpoint.checkpoint_digest = (
                    outcome.scan_digest
                    or await self._scan_digest_for(
                        tenant_id, conversation_id, owner_key
                    )
                )
                checkpoint.reason_code = None
                checkpoint.updated_at = now
                await self._session.flush()
            return
        if outcome.state in (
            OutputState.PROVABLY_NOT_SENT,
            OutputState.OUTCOME_UNKNOWN,
            OutputState.DEADLINE_EXPIRED,
            OutputState.ADAPTER_UNRESOLVABLE,
        ):
            # 态 2/3/5/6：checkpoint → blocked + 具名 reason（若尚未 blocked）+
            # fence erasing→blocked。
            reason = outcome.reason
            if checkpoint is not None and checkpoint.state not in ("blocked", "acked"):
                checkpoint.state = "blocked"
                checkpoint.reason_code = reason
                checkpoint.updated_at = now
                await self._session.flush()
            if fence.state == "erasing":
                await self._fence_to_blocked(
                    tenant_id, conversation_id, fence, frozen, hold_revision
                )
            return
        raise ValueError(f"unhandled settlement outcome state {outcome.state}")

    async def _scan_digest_for(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, owner_key: str
    ) -> str:
        scan_provider = self._scan_providers.get(owner_key)
        if scan_provider is None:
            return _EMPTY_SCAN_DIGEST
        scan = await scan_provider(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        return scan.digest()


_EMPTY_SCAN_DIGEST = canonical_digest({})


def _outcome_unknown_reason(owner_key: str) -> str:
    return (
        _REASON_OUTCOME_UNKNOWN_EXTERNAL
        if owner_key == "external.payload.v1"
        else _REASON_OUTCOME_UNKNOWN_RUNTIME
    )


def _deadline_reason(owner_key: str) -> str:
    return (
        _REASON_DEADLINE_EXTERNAL
        if owner_key == "external.payload.v1"
        else _REASON_DEADLINE_RUNTIME
    )


def _unresolvable_reason(owner_key: str) -> str:
    return (
        _REASON_UNRESOLVABLE_EXTERNAL
        if owner_key == "external.payload.v1"
        else _REASON_UNRESOLVABLE_RUNTIME
    )


__all__ = ["SettlementService", "OutputState"]
