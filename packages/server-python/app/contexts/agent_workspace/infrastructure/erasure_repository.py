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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_registry import require_owner
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
        if model.state != expected_state.value or model.revision != expected_revision:
            raise ValueError("erasure fence CAS conflict")
        if new_state is ErasureFenceState.ERASED and not ack_digest:
            raise ValueError("erased fence requires ack_digest")
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
        registry_digest: str,
        retention_policy_snapshot: dict,
        hold_revision_snapshot: int,
        now: datetime | None = None,
    ) -> PurgeOperation:
        effective_now = now or _utcnow()
        model = PurgeOperationModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            state=PurgeOperationState.SCHEDULED.value,
            registry_digest=registry_digest,
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
        model = PurgeOwnerCheckpointModel(
            tenant_id=tenant_id,
            purge_operation_id=purge_operation_id,
            owner_key=owner_key,
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
        result = await self._session.execute(
            select(ConversationLegalHoldModel.id).where(
                ConversationLegalHoldModel.tenant_id == tenant_id,
                ConversationLegalHoldModel.conversation_id == conversation_id,
                ConversationLegalHoldModel.state == LegalHoldState.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none() is not None


__all__ = ["AgentErasureRepository"]
