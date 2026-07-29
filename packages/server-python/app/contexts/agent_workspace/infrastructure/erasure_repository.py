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

from sqlalchemy import exists, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
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
from app.contexts.agent_workspace.domain.errors import (
    ConversationPurgeInProgressError,
    LateBodyWriteRejectedError,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationLegalHoldModel,
    ConversationModel,
    ErasureFenceModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.shared.schemas.canonical_json import canonical_digest


def _utcnow() -> datetime:
    return datetime.now(UTC)


# 规范空 ingress checkpoint（Spec §5.1，S2-C P1-5 复审）：baseline fence（新建/
# backfill）的 ``ingress_checkpoint`` 与 ``ingress_digest`` 必须同源——digest 始终
# 等于 ``canonical_digest(ingress_checkpoint)``。统一常量避免「存 ``{}`` 却 hash
# 另一对象形状」的天生不一致。schema 与 ``_advance_ingress`` 产出一致
# （``schema_version=1`` + ``sources`` dict）。
EMPTY_INGRESS_CHECKPOINT: dict = {"schema_version": 1, "sources": {}}

# workspace.core.v1 受管正文 ingress 的 canonical source key（S2-C 契约注记）：
# 只允许这两个受控类别，任意 key fail closed（防止脱离能力模型的 checkpoint 写入）。
INGRESS_SOURCE_KEYS: frozenset[str] = frozenset({"body_messages", "title"})


def empty_ingress_digest() -> str:
    """规范空 checkpoint 的 digest（与 ``EMPTY_INGRESS_CHECKPOINT`` 严格同源）。"""
    return canonical_digest(EMPTY_INGRESS_CHECKPOINT)


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

    async def create_fence_under_owner_lock(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> ErasureFence:
        """受控建立/补齐 fence 的**唯一公开入口**（backfill / 测试基线）。

        锁序（Spec §6.1）：先持 Conversation 行锁（与正文 writer 一致，
        Conversation row -> owner lock -> fence FOR UPDATE），再取 owner
        advisory lock，最后在锁内调私有 primitive。若跳过 Conversation 行锁
        直接取 owner lock，会与「Conversation 行锁 -> owner lock」的正文
        writer 形成 AB-BA 死锁（writer 持 Conversation 行锁等 owner lock，
        backfill 持 owner lock 等 fence/Conversation）。get-then-create 与
        惰性 writer / 其他 backfill 并发时由此串行（§10.3 幂等）。调用方
        不得绕过本入口直调私有 primitive。
        """
        # Conversation 行锁（锁序第一步）：与正文 writer 对齐，防 AB-BA 死锁。
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
            raise LateBodyWriteRejectedError(
                f"conversation {conversation_id} not found for fence backfill"
            )
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        return await self._create_fence(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            now=now,
        )

    async def ensure_fence_under_owner_lock(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> tuple[ErasureFence, bool]:
        """受控 ensure（backfill 用）：与 ``create_fence_under_owner_lock`` 同锁序，
        额外返回 ``(fence, created)``——``created=True`` 表示本调用新建，``False``
        表示既有 active 行幂等返回。

        S2-C P1-2 复审：backfill 不得「先 ``get_fence_for_update`` 锁 fence、再进
        本方法锁 Conversation」——那会对已有 fence 形成 fence->Conversation 反向
        锁序，与 writer 的 Conversation->owner->fence 构成真实 AB-BA 死锁。探测
        必须在锁内（``_create_fence`` 的 get-then-create 已持 Conversation 行锁 +
        owner lock），由本方法统一返回 created 标志，禁止锁前探测。
        """
        # 锁序第一步：Conversation 行锁（与 writer 一致）。
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
            raise LateBodyWriteRejectedError(
                f"conversation {conversation_id} not found for fence backfill"
            )
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        # 锁内探测（此时已持 Conversation 行锁 + owner lock，无反向锁序）。
        existing = await self.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        created = existing is None
        fence = await self._create_fence(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            now=now,
        )
        return fence, created

    async def _create_fence(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> ErasureFence:
        """按 registry 建立 ``active`` fence；owner key 必须已登记（fail closed）。

        幂等（Spec §4.2 backfill / §10.3）：fence 已存在且为同 owner_version 的
        ``active`` 时直接返回既有行——正文 writer 首次写已惰性建 fence，backfill
        补齐不得与其 PK 冲突。版本漂移或非 active（清除路径上的状态）仍 fail
        closed，不把既有行当作可安全重建。

        私有 primitive：get-then-create 的竞态安全依赖调用方已持 owner
        advisory lock。唯一合法调用方是本类的
        ``create_fence_under_owner_lock`` / ``get_or_create_fence_for_update``
        （均先取 owner lock）。不得外部直调。
        """
        owner = require_owner(owner_key)
        existing = await self.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        if existing is not None:
            if (
                existing.owner_version == owner.owner_version
                and existing.state is ErasureFenceState.ACTIVE
            ):
                return existing
            raise OwnerRegistryChangedError(
                f"fence {owner_key!r} already exists with version "
                f"{existing.owner_version}/state {existing.state.value}; "
                "refusing to recreate over a non-baseline row"
            )
        effective_now = now or _utcnow()
        model = ErasureFenceModel(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner.owner_key,
            owner_version=owner.owner_version,
            state=ErasureFenceState.ACTIVE.value,
            ingress_checkpoint=dict(EMPTY_INGRESS_CHECKPOINT),
            ingress_digest=empty_ingress_digest(),
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
        return await self._create_fence(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            now=now,
        )

    async def require_body_write_fence_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        now: datetime | None = None,
    ) -> ErasureFence:
        """正文 writer fence 裁决（Spec §6.2 第 1-5 步）：owner lock -> fence
        FOR UPDATE（缺失按 registry 建 active fence）-> 校验 state/token ->
        仅 active 且 token 新鲜才允许写正文。

        **本方法只做裁决（verdict）**：不推进 ``last_body_write_at``、fence
        ``revision`` 或 ``ingress_checkpoint``——推进独占归属
        ``advance_ingress_checkpoint_for_update``（S2-C P2-6 复审），仅在有真实
        正文/checkpoint 推进时发生。否则幂等 replay（经本裁决放行但不写新正文）
        会空推进 checkpoint/revision，把「裁决」误当「正文写」。

        锁序（模块 docstring）：调用方已持 Conversation 行锁 -> 本方法取
        owner advisory lock -> fence FOR UPDATE -> 同事务内更新 fence 行。

        校验（Spec §6.2 第 3 步，fail closed -> LateBodyWriteRejectedError）：
        - owner_version 漂移：registry 已升级，不基于过期能力视图写正文。
        - state 非 active（erasing/blocked/erased）：purge 进行中/已完成。
        - 既有 active fence 的 purge/hold_revision 与 Conversation 当前 fencing
          token 不一致（stale）：restore/purge 已推进 Conversation token 而本
          fence 未对齐，不得基于过期 token 放行正文。

        token 语义（Spec §5.1 fencing token）：
        - **新 fence（惰性首写，revision=1）**：同步到 Conversation 当前 token。
          delete 推进 Conversation purge_revision 且不留 active fence 同步点；
          新 fence 必须携带当前 token，否则恢复/删除后的会话永远无法写正文。
        - **既有 active fence**：只校验相等、不推进 token——writer 无权改写
          fencing token（那是 purge/restore/delete 的职责）。
        """
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )
        # Conversation 行锁已由调用方持有；读取当前 fencing token。hold 无
        # 正文 writer 写路径（hold 由独立 lifecycle 管理），不存在竞争写。
        conversation = await self._session.get(ConversationModel, conversation_id)
        if conversation is None:
            raise LateBodyWriteRejectedError(
                f"conversation {conversation_id} not found for body write fence"
            )
        fence = await self.get_or_create_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            now=now,
        )
        # owner_version 漂移 fail closed（归为「拒绝写正文」domain 语义）。
        try:
            require_owner_version(owner_key, fence.owner_version)
        except OwnerRegistryChangedError as exc:
            raise LateBodyWriteRejectedError(
                f"owner fence {owner_key!r} version {fence.owner_version} does not "
                "match installed registry; body write rejected"
            ) from exc
        if fence.state is not ErasureFenceState.ACTIVE:
            raise LateBodyWriteRejectedError(
                f"owner fence {owner_key!r} is {fence.state.value}; "
                "body write rejected because purge is in progress or complete"
            )
        # fencing token 校验/同步。get_or_create 返回的 domain 是创建时快照；
        # 需要行锁内的 model 以原子更新。active fence 的 purge_revision 只增
        # 不减（单调）：落后于 Conversation 说明 fence 不在 purge 路径上
        # （purge 会在 CAS 时把 fence token 盖到 >= Conversation），安全单调
        # 对齐——涵盖惰性首写（fence=0）与 delete 推进后的 stale active fence
        # （deleted 会话的迟到投影/幂等重放需放行）。fence token 高于
        # Conversation 是矛盾状态（fence 有 purge token 但 state 仍 active 且
        # Conversation 无对应 purge），fail closed。
        fence_model = await self._session.get(
            ErasureFenceModel,
            (fence.tenant_id, fence.conversation_id, fence.owner_key),
        )
        if fence_model is None:  # pragma: no cover - get_or_create 刚保证存在
            raise LateBodyWriteRejectedError("erasure fence vanished during write")
        if fence_model.purge_revision > conversation.purge_revision:
            raise LateBodyWriteRejectedError(
                f"owner fence {owner_key!r} purge_revision "
                f"{fence_model.purge_revision} exceeds conversation "
                f"{conversation.purge_revision} while still active; body write "
                "rejected on contradictory fencing token"
            )
        if (
            fence_model.purge_revision < conversation.purge_revision
            or fence_model.hold_revision != conversation.hold_revision
        ):
            # 单调对齐到 Conversation 当前 token（含惰性首写与 deleted stale）。
            fence_model.purge_revision = conversation.purge_revision
            fence_model.hold_revision = conversation.hold_revision
            await self._session.flush()
        # S2-C P2-6 复审：本方法只做裁决（verdict），不推进
        # last_body_write_at/revision/checkpoint——推进归属
        # ``advance_ingress_checkpoint_for_update``，仅在有真实正文/checkpoint
        # 推进时发生。否则幂等 replay（经本裁决放行但不写新正文）会空推进
        # last_body_write_at/revision，把「裁决」误当「正文写」。
        return _fence_to_domain(fence_model)

    # --- ingress checkpoint（Spec §5.1/§6.2，S2-C）-------------------------

    @staticmethod
    def _advance_ingress(
        checkpoint: dict,
        *,
        source_key: str,
        watermark: int,
        epoch: int,
    ) -> dict:
        """返回推进了 ``source_key`` 水位的新 checkpoint（不就地改入参）。

        只记录真实 source 序号/epoch 的连续水位，不保存正文、prompt、自由文本
        或原始 payload。``watermark`` 必须真实反映本写分配到的 source 序号
        （body=message seq / title=Conversation revision），``epoch`` 为
        Conversation 当前 purge_revision。水位只增不减（单调）：回退或重复
        写同一序号保持既有水位。
        """
        sources = dict(checkpoint.get("sources") or {})
        existing = sources.get(source_key)
        new_watermark = watermark
        if existing is not None:
            new_watermark = max(int(existing.get("watermark", 0)), watermark)
        sources[source_key] = {"watermark": new_watermark, "epoch": epoch}
        return {"schema_version": 1, "sources": sources}

    async def advance_ingress_checkpoint_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        source_key: str,
        watermark: int,
        epoch: int,
        now: datetime | None = None,
    ) -> ErasureFence:
        """在已裁决的 fence 行上推进 ``source_key`` 的 ingress checkpoint。

        前置：调用方已在同一事务内经 ``require_body_write_fence_for_update``
        裁决放行（state=active、token 已对齐），并已分配本写的真实 source 序号
        （body=seq / title=revision CAS 后值）。本方法与正文写同一事务 commit，
        实现「正文写 + checkpoint + receipt 一起 commit」。

        S2-C P2-6/P2-7 复审：本方法**独占** checkpoint + ``last_body_write_at`` +
        fence ``revision`` 的推进（verdict 不再推进），并自校验输入、自取 fence
        行锁，不靠调用约定保证安全：
        - ``source_key`` 必须是受控类别（``INGRESS_SOURCE_KEYS``），任意 key fail
          closed（``ValueError``）。
        - ``watermark`` 必须为正（真实 source 序号）。
        - ``epoch`` 必须等于 Conversation 当前 ``purge_revision``（stale epoch fail
          closed，不把旧 purge epoch 的写记到新 epoch）。
        - fence 非 active（裁决后被并发 purge 接管）拒绝推进（writer-win race
          原子兜底），不在清除路径上为已拒正文补 checkpoint。
        """
        if source_key not in INGRESS_SOURCE_KEYS:
            raise ValueError(
                f"unknown ingress source_key {source_key!r}; must be one of "
                f"{sorted(INGRESS_SOURCE_KEYS)}"
            )
        if watermark < 1:
            raise ValueError(f"ingress watermark must be >= 1, got {watermark}")
        # 自取 Conversation（读 purge_revision 校验 epoch）+ fence 行锁。
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
            raise LateBodyWriteRejectedError(
                f"conversation {conversation_id} not found for ingress advance"
            )
        if epoch != conversation.purge_revision:
            raise ValueError(
                f"ingress epoch {epoch} does not match conversation purge_revision "
                f"{conversation.purge_revision}; refusing to record a stale-epoch write"
            )
        fence_model = (
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
        if fence_model is None:
            raise LateBodyWriteRejectedError(
                f"erasure fence {owner_key!r} missing during ingress advance"
            )
        if fence_model.state != ErasureFenceState.ACTIVE.value:
            raise LateBodyWriteRejectedError(
                f"owner fence {owner_key!r} is {fence_model.state}; cannot advance "
                "ingress checkpoint on a non-active (purge-path) fence"
            )
        effective_now = now or _utcnow()
        fence_model.ingress_checkpoint = self._advance_ingress(
            dict(fence_model.ingress_checkpoint),
            source_key=source_key,
            watermark=watermark,
            epoch=epoch,
        )
        fence_model.ingress_digest = canonical_digest(fence_model.ingress_checkpoint)
        # 推进归属本方法（P2-6）：last_body_write_at + fence revision CAS 随真实
        # 正文/checkpoint 写推进，与正文写同事务 commit。
        fence_model.last_body_write_at = effective_now
        fence_model.revision = fence_model.revision + 1
        fence_model.updated_at = effective_now
        await self._session.flush()
        return _fence_to_domain(fence_model)

    async def list_fences(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[ErasureFence]:
        """普通读（不加行锁）：供只读查询/报告路径使用。

        restore/purge 等状态裁决路径必须用 ``list_fences_for_update``，
        在 owner lock 之后对 fence 行加 FOR UPDATE（模块 docstring 锁序）。
        """
        result = await self._session.execute(
            select(ErasureFenceModel)
            .where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
            )
            .order_by(ErasureFenceModel.owner_key)
        )
        return [_fence_to_domain(row) for row in result.scalars().all()]

    async def list_fences_for_update(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[ErasureFence]:
        """状态裁决路径的 fence 行锁读取（FOR UPDATE）。

        锁序（模块 docstring）：调用方必须先持 Guard -> Conversation row ->
        owner advisory lock，再取本行锁；按 owner_key 字典序返回。
        """
        result = await self._session.execute(
            select(ErasureFenceModel)
            .where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
            )
            .order_by(ErasureFenceModel.owner_key)
            .with_for_update()
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

    async def cancel_scheduled_operations_for_restore(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        now: datetime,
    ) -> list[PurgeOperation]:
        """restore CAS（Spec §3-3）：把尚未开始的 purge operation 置 cancelled
        终态（保留审计行、清 next_retry_at、推进 revision），返回被取消行。

        scheduled operation 若已有 owner checkpoint 进入 erasing/blocked/acked，
        说明清除实际已开始（状态自相矛盾）-> fail closed，不得恢复也不得改写
        operation。operation 行锁 + state 谓词构成 CAS；调用方必须先持
        Conversation 行锁，保证取消与 Conversation 状态恢复原子提交。now 为
        锁后采样的数据库时钟（必传），updated_at 不落应用时钟。
        """
        effective_now = now
        result = await self._session.execute(
            select(PurgeOperationModel)
            .where(
                PurgeOperationModel.tenant_id == tenant_id,
                PurgeOperationModel.conversation_id == conversation_id,
                PurgeOperationModel.state == PurgeOperationState.SCHEDULED.value,
            )
            .with_for_update()
        )
        operations = list(result.scalars().all())
        # 尚未开始的 operation 只允许 pending checkpoint；出现 failed 即代表
        # 已发生过一次擦除尝试（pending->erasing->failed），与
        # erasing/blocked/acked 一样属「清除实际已开始」-> fail closed。
        safe_checkpoint_states = frozenset({PurgeOwnerState.PENDING.value})
        for operation in operations:
            checkpoint_states = (
                (
                    await self._session.execute(
                        select(PurgeOwnerCheckpointModel.state).where(
                            PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                            PurgeOwnerCheckpointModel.purge_operation_id
                            == operation.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if any(
                state not in safe_checkpoint_states for state in checkpoint_states
            ):
                raise ConversationPurgeInProgressError(
                    "scheduled purge operation has a started owner checkpoint; "
                    "restore would resurrect a body whose erasure already began"
                )
        cancelled: list[PurgeOperation] = []
        for operation in operations:
            update_result = await self._session.execute(
                update(PurgeOperationModel)
                .where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.id == operation.id,
                    PurgeOperationModel.state == PurgeOperationState.SCHEDULED.value,
                )
                .values(
                    state=PurgeOperationState.CANCELLED.value,
                    next_retry_at=None,
                    revision=operation.revision + 1,
                    updated_at=effective_now,
                )
                .execution_options(synchronize_session=False)
            )
            if not isinstance(update_result, CursorResult) or update_result.rowcount != 1:
                raise ValueError(
                    "purge operation cancel CAS conflict during restore"
                )
            await self._session.refresh(operation)
            cancelled.append(_purge_to_domain(operation))
        return cancelled

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
