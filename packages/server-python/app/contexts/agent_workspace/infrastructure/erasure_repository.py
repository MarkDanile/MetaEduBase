"""R1-S1 coordination repository：fence / purge / checkpoint / legal hold。

这些表属于 control-plane coordination infrastructure（Spec §5），ORM 落在
``agent_workspace``（Conversation/lifecycle owner）。``agent_execution`` 与
composition 经 port 使用，不 import 这些 ORM。R1-S1 只提供状态/CAS/fail-closed
原语，不启动 scheduler、不清除正文。

锁序（Spec §6.1 / §6.2）：调用方必须先取得 ConversationExecutionGuard 与
Conversation row，再取 owner advisory lock（``agent_erasure_locks``），然后
``SELECT ... FOR UPDATE`` fence。本 repository 不承担 Guard/owner lock，只提供
fence 行锁与 CAS。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    UnknownOwnerError,
    registry_snapshot,
    require_owner,
    require_owner_version,
    snapshot_digest,
)
from app.contexts.agent_workspace.domain.erasure import (
    ConversationLegalHold,
    ErasureFence,
    ErasureFenceState,
    LegalHoldState,
    PurgeOperation,
    PurgeOperationState,
    PurgeOwnerCheckpoint,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationLegalHoldModel,
    ErasureFenceModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.shared.schemas.canonical_json import canonical_digest


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _empty_ingress_digest() -> str:
    return canonical_digest({"ingress": {}, "schema_version": 1})


# fence 状态机显式转移表（Spec §5.1/§6.2）：只允许下列 (from → to) 边。
# - active→erasing：开始 purge fencing；token 由调用方从合法 operation revision 提供。
# - erasing→erased：owner ACK 完成；erasing→blocked：owner 暂停（external/hold）。
# - blocked→erasing：解除暂停后继续。
# 禁止：任何 →active（owner 一旦离开 active，普通 restore 即不允许，不存在回到
# active 的 fence 路径）；erased 为终态；blocked 不得直达 erased（须经 erasing 完成 ACK）。
_FENCE_ALLOWED_TRANSITIONS: frozenset[tuple[ErasureFenceState, ErasureFenceState]] = (
    frozenset(
        {
            (ErasureFenceState.ACTIVE, ErasureFenceState.ERASING),
            (ErasureFenceState.ERASING, ErasureFenceState.ERASED),
            (ErasureFenceState.ERASING, ErasureFenceState.BLOCKED),
            (ErasureFenceState.BLOCKED, ErasureFenceState.ERASING),
        }
    )
)


def _fence_to_domain(model: ErasureFenceModel) -> ErasureFence:
    return ErasureFence(
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        owner_key=model.owner_key,
        owner_version=model.owner_version,
        state=ErasureFenceState(model.state),
        purge_revision=model.purge_revision,
        hold_revision=model.hold_revision,
        ingress_checkpoint=dict(model.ingress_checkpoint),
        ingress_digest=model.ingress_digest,
        last_body_write_at=model.last_body_write_at,
        ack_digest=model.ack_digest,
        acked_at=model.acked_at,
        revision=model.revision,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _purge_to_domain(model: PurgeOperationModel) -> PurgeOperation:
    return PurgeOperation(
        id=model.id,
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        purge_revision=model.purge_revision,
        state=PurgeOperationState(model.state),
        registry_digest=model.registry_digest,
        registry_snapshot=list(model.registry_snapshot),
        retention_policy_snapshot=dict(model.retention_policy_snapshot),
        retention_policy_digest=model.retention_policy_digest,
        hold_revision_snapshot=model.hold_revision_snapshot,
        lease_epoch=model.lease_epoch,
        scheduled_at=model.scheduled_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        failure_code=model.failure_code,
        next_retry_at=model.next_retry_at,
        revision=model.revision,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _owner_to_domain(model: PurgeOwnerCheckpointModel) -> PurgeOwnerCheckpoint:
    return PurgeOwnerCheckpoint(
        id=model.id,
        tenant_id=model.tenant_id,
        purge_operation_id=model.purge_operation_id,
        owner_key=model.owner_key,
        owner_version=model.owner_version,
        capability_digest=model.capability_digest,
        state=PurgeOwnerState(model.state),
        attempt=model.attempt,
        checkpoint_digest=model.checkpoint_digest,
        ack_digest=model.ack_digest,
        reason_code=model.reason_code,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _hold_to_domain(model: ConversationLegalHoldModel) -> ConversationLegalHold:
    return ConversationLegalHold(
        id=model.id,
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        reason_code=model.reason_code,
        purpose=model.purpose,
        actor_id=model.actor_id,
        state=LegalHoldState(model.state),
        expires_at=model.expires_at,
        revision=model.revision,
        created_at=model.created_at,
        updated_at=model.updated_at,
        released_at=model.released_at,
        released_by=model.released_by,
    )


class AgentErasureRepository:
    """Tenant-scoped adapter for R1 coordination facts."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # --- ErasureFence ---------------------------------------------------

    async def get_fence_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> ErasureFence | None:
        """在 owner lock 内对 fence 加 FOR UPDATE；不存在返回 None（由调用方建立）。"""
        result = await self._session.execute(
            select(ErasureFenceModel)
            .where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == owner_key,
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return _fence_to_domain(model) if model is not None else None

    async def create_fence(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> ErasureFence:
        """按 registry 建立 ``active`` fence；owner key 必须已登记（fail closed）。"""
        owner = require_owner(owner_key)
        effective_now = now or _utcnow()
        model = ErasureFenceModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner.owner_key,
            owner_version=owner.owner_version,
            state=ErasureFenceState.ACTIVE.value,
            ingress_checkpoint={},
            ingress_digest=_empty_ingress_digest(),
            revision=1,
            created_at=effective_now,
            updated_at=effective_now,
        )
        self._session.add(model)
        await self._session.flush()
        return _fence_to_domain(model)

    async def get_or_create_fence_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> ErasureFence:
        """owner lock 内 fence 不存在则建立；缺行不得被解释为安全。"""
        fence = await self.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        if fence is not None:
            return fence
        return await self.create_fence(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            now=now,
        )

    async def list_fences(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[ErasureFence]:
        result = await self._session.execute(
            select(ErasureFenceModel)
            .where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
            )
            .order_by(ErasureFenceModel.owner_key)
        )
        return [_fence_to_domain(row) for row in result.scalars().all()]

    async def transition_fence_state(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        expected_state: ErasureFenceState,
        expected_revision: int,
        new_state: ErasureFenceState,
        purge_revision: int,
        hold_revision: int,
        ack_digest: str | None = None,
        now: datetime | None = None,
    ) -> ErasureFence:
        """CAS 迁移 fence 状态。erased 必须带 ack_digest；版本变化 fail closed。"""
        require_owner(owner_key)
        effective_now = now or _utcnow()
        result = await self._session.execute(
            select(ErasureFenceModel)
            .where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == owner_key,
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("erasure fence missing; cannot transition")
        # 版本守卫：fence 行记录的 owner_version 必须仍匹配已安装 registry，
        # 否则 registry 已升级 -> fail closed，不推进旧版本 fence（Spec §4）。
        require_owner_version(owner_key, model.owner_version)
        if model.state != expected_state.value or model.revision != expected_revision:
            raise ValueError("erasure fence CAS conflict")
        # 状态机显式转移表：非法边（如 erasing/erased→active 重新开放 writer、
        # active→erased 绕过 erasing fencing、erased→任意、blocked→active）一律
        # fail closed，不依赖调用方自觉（Spec §5.1/§6.2，R1-AC3）。owner 一旦离开
        # active，普通 restore 即不允许；不存在「删除并重建 fence 回到 active」的路径。
        current_state = ErasureFenceState(model.state)
        if (current_state, new_state) not in _FENCE_ALLOWED_TRANSITIONS:
            raise ValueError(
                f"illegal erasure fence transition {current_state} -> {new_state}"
            )
        # 合法推进（→erasing/erased/blocked）必须带 purge fencing token（>=1）：
        # purge_revision=0 表示「无 purge operation」，绕过 erasing fencing。
        if purge_revision < 1:
            raise ValueError(
                f"erasure fence transition {current_state} -> {new_state} requires "
                f"purge_revision >= 1, got {purge_revision}"
            )
        # fencing token 单调守卫（Spec §5.1/§6.2）：purge_revision/hold_revision 只增
        # 不减，等值合法（重试复用同 token）。回退会重新放行持有旧 revision 的暂停
        # writer（R1-AC3），fail closed。
        if purge_revision < model.purge_revision or hold_revision < model.hold_revision:
            raise ValueError(
                "erasure fence fencing token regression: purge_revision/hold_revision "
                "must be monotonically non-decreasing"
            )
        if new_state is ErasureFenceState.ERASED and not ack_digest:
            raise ValueError("erased fence requires ack_digest")
        # ACK 只属于 erased：非 erased 边携带 ack_digest 说明调用方把「提交 ACK」与
        # 「状态推进」混用，ACK 会被静默丢弃——durable purge saga 必须 fail closed。
        if new_state is not ErasureFenceState.ERASED and ack_digest is not None:
            raise ValueError(
                f"ack_digest only allowed on erased transition, got non-erased "
                f"{current_state} -> {new_state}"
            )
        model.state = new_state.value
        model.purge_revision = purge_revision
        model.hold_revision = hold_revision
        if new_state is ErasureFenceState.ERASED:
            model.ack_digest = ack_digest
            model.acked_at = effective_now
        model.revision = model.revision + 1
        model.updated_at = effective_now
        await self._session.flush()
        return _fence_to_domain(model)

    # --- PurgeOperation / owner checkpoint -------------------------------

    async def create_purge_operation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        retention_policy_snapshot: dict,
        hold_revision_snapshot: int,
        expected_registry_digest: str | None = None,
        now: datetime | None = None,
    ) -> PurgeOperation:
        effective_now = now or _utcnow()
        # 单一事实源：生成一次 snapshot，digest 由该同一 snapshot 计算（不二次
        # 调用 registry_snapshot()），保证 snapshot 与 digest 严格同源绑定。
        snapshot = registry_snapshot()
        digest = snapshot_digest(snapshot)
        # 可选乐观并发：调用方若声明 expected digest，必须与当前一致，否则
        # registry 已变化 -> fail closed，不持久化不一致的 operation（Spec §4）。
        if expected_registry_digest is not None and expected_registry_digest != digest:
            raise OwnerRegistryChangedError(
                "expected registry digest does not match installed registry"
            )
        # purge_revision/hold_revision_snapshot 是单调 fencing token，应用层 fail
        # closed（与 DB ck_agent_purge_revisions 同深度，不漏到 IntegrityError）。
        if purge_revision < 1:
            raise ValueError(f"purge_revision must be >= 1, got {purge_revision}")
        if hold_revision_snapshot < 0:
            raise ValueError(
                f"hold_revision_snapshot must be >= 0, got {hold_revision_snapshot}"
            )
        model = PurgeOperationModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            state=PurgeOperationState.SCHEDULED.value,
            registry_digest=digest,
            # 持久化排序 owner 列表（不只是 digest），代码升级后可重建该次
            # operation 对应的 owner capability（Spec §4 / §5）。
            registry_snapshot=snapshot,
            retention_policy_snapshot=retention_policy_snapshot,
            retention_policy_digest=canonical_digest(
                {"policy": retention_policy_snapshot, "schema_version": 1}
            ),
            hold_revision_snapshot=hold_revision_snapshot,
            scheduled_at=effective_now,
            revision=1,
            created_at=effective_now,
            updated_at=effective_now,
        )
        self._session.add(model)
        await self._session.flush()
        return _purge_to_domain(model)

    async def get_purge_operation_for_update(
        self, *, tenant_id: uuid.UUID, purge_operation_id: uuid.UUID
    ) -> PurgeOperation | None:
        result = await self._session.execute(
            select(PurgeOperationModel)
            .where(
                PurgeOperationModel.tenant_id == tenant_id,
                PurgeOperationModel.id == purge_operation_id,
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return _purge_to_domain(model) if model is not None else None

    async def create_owner_checkpoint(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> PurgeOwnerCheckpoint:
        require_owner(owner_key)
        effective_now = now or _utcnow()
        # 从该 operation 持久化的 registry_snapshot 取 owner_version/capability_digest
        # （与 registry_digest 同源），而非重新读取当前 registry——保证代码升级后
        # 该次 ACK 仍对应 operation 冻结的能力视图（Spec §4）。
        purge_result = await self._session.execute(
            select(
                PurgeOperationModel.registry_snapshot,
                PurgeOperationModel.registry_digest,
            ).where(
                PurgeOperationModel.tenant_id == tenant_id,
                PurgeOperationModel.id == purge_operation_id,
            )
        )
        row = purge_result.one_or_none()
        if row is None:
            raise ValueError(
                f"purge operation {purge_operation_id} missing; cannot checkpoint"
            )
        snapshot, stored_digest = row
        # 内部一致性：持久化 snapshot 的 digest 必须等于持久化 registry_digest，
        # 否则 snapshot 被篡改 -> fail closed。
        if snapshot_digest(list(snapshot)) != stored_digest:
            raise OwnerRegistryChangedError(
                "purge operation registry snapshot/digest mismatch; fail closed"
            )
        # registry drift：operation 的 digest 必须仍匹配当前已安装 registry，
        # 否则 registry 已升级 -> fail closed，不基于过期能力视图建 checkpoint
        # （Spec §4.2 / R1-AC2）。
        if stored_digest != snapshot_digest(registry_snapshot()):
            raise OwnerRegistryChangedError(
                "purge operation registry digest no longer matches installed registry"
            )
        entry = next(
            (item for item in snapshot if item.get("owner_key") == owner_key),
            None,
        )
        if entry is None:
            raise UnknownOwnerError(
                f"owner {owner_key!r} not present in operation registry snapshot"
            )
        model = PurgeOwnerCheckpointModel(
            tenant_id=tenant_id,
            purge_operation_id=purge_operation_id,
            owner_key=owner_key,
            owner_version=int(entry["owner_version"]),
            capability_digest=str(entry["capability_digest"]),
            state=PurgeOwnerState.PENDING.value,
            attempt=0,
            created_at=effective_now,
            updated_at=effective_now,
        )
        self._session.add(model)
        await self._session.flush()
        return _owner_to_domain(model)

    # --- LegalHold --------------------------------------------------------

    async def create_legal_hold(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reason_code: str,
        purpose: str,
        actor_id: uuid.UUID,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> ConversationLegalHold:
        effective_now = now or _utcnow()
        model = ConversationLegalHoldModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason_code=reason_code,
            purpose=purpose,
            actor_id=actor_id,
            state=LegalHoldState.ACTIVE.value,
            expires_at=expires_at,
            revision=1,
            created_at=effective_now,
            updated_at=effective_now,
        )
        self._session.add(model)
        await self._session.flush()
        return _hold_to_domain(model)

    async def has_active_legal_hold(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        """是否存在任一 active hold。同一 Conversation 允许多个 active hold，
        用 EXISTS 语义而非 scalar_one_or_none（多行不得抛 MultipleResultsFound）。"""
        result = await self._session.execute(
            select(
                exists(
                    select(ConversationLegalHoldModel.id).where(
                        ConversationLegalHoldModel.tenant_id == tenant_id,
                        ConversationLegalHoldModel.conversation_id == conversation_id,
                        ConversationLegalHoldModel.state == LegalHoldState.ACTIVE.value,
                    )
                )
            )
        )
        return bool(result.scalar_one())


__all__ = ["AgentErasureRepository"]
