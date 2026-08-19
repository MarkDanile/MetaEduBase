"""R1-S5 SCH-A：ConversationPurgeScheduler claim/lease 服务（无后台循环）。

契约：Plan §R1-S5-D（S5-SCH-1.1/1.3b-i/2）+ §R1-S5-D-A（S5-SCH-8/9）——

- **claim 谓词**（全部锁内判定、tenant 限定）：``state=deleted`` +
  ``purged_at IS NULL`` + ``purge_after`` 已过 + 无 active hold + quiesce
  门禁（任一 owner checkpoint/fence 仍 ``erasing``）+ 无在租 claim
  （``lease_expires_at`` 未到期）。首 claim 幂等判别：top operation
  不存在或旧 ``purge_revision`` → 建行（当前 ``conversation.purge_revision``）
  + 全 owner checkpoint 建行 + lease acquire，**同事务**；存在同 revision 行
  → 幂等返回既有 operation（在租 HELD / 过期 takeover / NULL acquire）。
- **租约三态 × 四转移**：全部 Conversation-first 短事务 + SQL 侧
  expected-epoch CAS（WHERE 内 ``clock_timestamp()`` 语句级求值），成功
  恰好 ``lease_epoch + 1``；预期不匹配 → 零写退避。acquire/renew/takeover
  写 DB clock expiry；release 清 expiry 并推进 epoch。
- **tenant 上限**：advisory 4（跨 conversation 计数为快照读；单 claim 自身
  「计数与 acquire 同事务、计数在前」）；未认领（NULL）与已过期行不占 slot。
- **退避**：``next_retry_at = clock_timestamp() + min(5s × 2^attempt, 5m)``，
  attempt 取 per-owner checkpoint 锁内最小值（最早者仲裁），随
  claim/renew/takeover 短事务锁内重算，不依赖持久 jitter。
- **takeover 后强制聚合**：1.3b-i——同事务调用 coordinator
  ``aggregate_projection``，再返回新内存 lease token。
- **updated_at** 只作审计：本服务所有租约判定只读 ``lease_epoch`` +
  ``lease_expires_at``，不读不写 ``updated_at``。

边界（S5-SCH-9）：不启动后台循环；不实现 owner execution/tick/rebuild/
seeding/settlement/retry API；六 participant 擦除入口不参与（组合根静态
守卫：本模块不得引用这些入口名）；本服务**不得 commit()**，事务原子性归
调用方。

生产唯一调用方预计为 scheduler claim 循环（后续 slice 接线）；当前无生产
调用方（S5-A-5 组合根不可达门禁保持）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.transactional_projection_coordinator import (
    TransactionalProjectionCoordinator,
    build_scan_providers,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
)


class ClaimKind(StrEnum):
    """claim 结果类别。"""

    CLAIMED = "claimed"
    HELD = "held"
    DEFERRED = "deferred"


class DeferReason(StrEnum):
    """claim 谓词拒绝原因（全部零写零建行）。"""

    NOT_DELETED = "not_deleted"
    PURGE_NOT_DUE = "purge_not_due"
    ALREADY_PURGED = "already_purged"
    ACTIVE_HOLD = "active_hold"
    QUIESCE = "quiesce"
    TENANT_CAP = "tenant_cap"


class RenewOutcomeKind(StrEnum):
    RENEWED = "renewed"
    STALE = "stale"
    EXPIRED = "expired"


class TakeoverOutcomeKind(StrEnum):
    TAKEN = "taken"
    IN_LEASE = "in_lease"
    STALE = "stale"
    TERMINAL = "terminal"


class ReleaseOutcomeKind(StrEnum):
    RELEASED = "released"
    ALREADY_RELEASED = "already_released"
    STALE = "stale"


@dataclass(frozen=True)
class LeaseToken:
    """acquire/renew/takeover 成功后的内存 lease token。"""

    purge_operation_id: uuid.UUID
    lease_epoch: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class ClaimOutcome:
    kind: ClaimKind
    token: LeaseToken | None = None
    purge_operation_id: uuid.UUID | None = None
    existing_lease_epoch: int | None = None
    existing_lease_expires_at: datetime | None = None
    defer_reason: DeferReason | None = None


@dataclass(frozen=True)
class RenewOutcome:
    kind: RenewOutcomeKind
    token: LeaseToken | None = None


@dataclass(frozen=True)
class TakeoverOutcome:
    kind: TakeoverOutcomeKind
    token: LeaseToken | None = None


@dataclass(frozen=True)
class ReleaseOutcome:
    kind: ReleaseOutcomeKind
    lease_epoch: int | None = None


class ConversationPurgeScheduler:
    """claim/lease 服务。所有方法 Conversation-first、不 commit。"""

    _LEASE_TTL_SECONDS = 600
    _BACKOFF_BASE_SECONDS = 5
    _BACKOFF_CAP_SECONDS = 300
    _TENANT_CLAIM_CAP = 4

    _ACQUIRE_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "lease_epoch = lease_epoch + 1, "
        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "
        "AND lease_epoch = :expected AND lease_expires_at IS NULL "
        "RETURNING lease_epoch, lease_expires_at"
    )
    _RENEW_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "lease_epoch = lease_epoch + 1, "
        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "
        "AND lease_epoch = :expected "
        "AND lease_expires_at > clock_timestamp() "
        "RETURNING lease_epoch, lease_expires_at"
    )
    _TAKEOVER_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "lease_epoch = lease_epoch + 1, "
        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "
        "AND lease_epoch = :expected "
        # 终态行禁止 takeover（SCH-13 判别点）：公共 takeover() 直调路径无
        # conversation 级谓词先行排除，op 级终态 guard 为兜底。
        "AND state NOT IN ('completed', 'cancelled') "
        "AND (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp()) "
        "RETURNING lease_epoch, lease_expires_at"
    )
    _RELEASE_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "lease_epoch = lease_epoch + 1, lease_expires_at = NULL "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "
        "AND lease_epoch = :expected AND lease_expires_at IS NOT NULL "
        "RETURNING lease_epoch"
    )
    _BACKOFF_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "next_retry_at = clock_timestamp() + make_interval(secs => :backoff) "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AgentErasureRepository(session)

    # -- claim -------------------------------------------------------------

    async def claim(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        retention_policy_snapshot: dict,
    ) -> ClaimOutcome:
        """claim 谓词判定 + 建行/幂等返回/租约推进（单事务，不 commit）。

        锁序：Conversation 行锁 → top operation 行锁（三键）→ SQL CAS。
        谓词拒绝与 CAS 失败一律零写。
        """
        conversation = await self._lock_conversation(tenant_id, conversation_id)
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for purge claim"
            )
        now = await self._db_now()

        if conversation.purged_at is not None:
            return ClaimOutcome(ClaimKind.DEFERRED, defer_reason=DeferReason.ALREADY_PURGED)
        if conversation.state != "deleted":
            return ClaimOutcome(
                ClaimKind.DEFERRED, defer_reason=DeferReason.NOT_DELETED
            )
        if conversation.purge_after is None or conversation.purge_after > now:
            return ClaimOutcome(
                ClaimKind.DEFERRED, defer_reason=DeferReason.PURGE_NOT_DUE
            )
        if await self._has_active_hold(tenant_id, conversation_id):
            return ClaimOutcome(
                ClaimKind.DEFERRED, defer_reason=DeferReason.ACTIVE_HOLD
            )
        if await self._has_erasing_activity(tenant_id, conversation_id):
            return ClaimOutcome(ClaimKind.DEFERRED, defer_reason=DeferReason.QUIESCE)

        top = await self._top_operation(tenant_id, conversation_id)
        if top is not None and top.purge_revision > conversation.purge_revision:
            raise ValueError(
                f"operation purge_revision {top.purge_revision} exceeds "
                f"conversation {conversation.purge_revision}; claim fail closed"
            )
        if top is not None and top.purge_revision == conversation.purge_revision:
            return await self._claim_existing(
                tenant_id, conversation_id, top, now
            )
        # 建行判据 (i) 的「无在租 claim」谓词同样约束旧 revision top：
        # restore 后旧 worker 的租约未清（≤TTL）时不得建新行——否则同
        # conversation 双活租约。旧行过期/NULL 则建新行（旧租约已不占 slot，
        # 终态收尾由原 holder 的终态观察 release 承担）。
        if (
            top is not None
            and top.lease_expires_at is not None
            and top.lease_expires_at > now
        ):
            return ClaimOutcome(
                ClaimKind.HELD,
                purge_operation_id=top.id,
                existing_lease_epoch=top.lease_epoch,
                existing_lease_expires_at=top.lease_expires_at,
            )
        return await self._claim_fresh(
            tenant_id, conversation_id, conversation, retention_policy_snapshot
        )

    async def _claim_existing(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        top: PurgeOperationModel,
        now: datetime,
    ) -> ClaimOutcome:
        """同 revision 已有 operation：在租 HELD / 过期 takeover / NULL acquire。"""
        # CAS 成功后 expire_all 会使 top 过期——先捕获局部值，禁止 post-expire
        # 属性访问（异步会话下过期属性触发同步 lazy refresh）。
        op_id = top.id
        epoch = top.lease_epoch
        expires_at = top.lease_expires_at
        if expires_at is not None and expires_at > now:
            return ClaimOutcome(
                ClaimKind.HELD,
                purge_operation_id=op_id,
                existing_lease_epoch=epoch,
                existing_lease_expires_at=expires_at,
            )
        if expires_at is not None:
            # 已过期：claim 走 takeover（含强制聚合）。
            # 计数豁免（三面返修裁决固化）：expired 行此前不占 slot（S5-SCH-8
            # 计数谓词），claim-takeover 是恢复语义而非新占 slot——不查 cap，
            # 与公开 takeover() 一致（否则「4 active + 1 expired」的 tenant
            # 会因 cap 锁死该 expired 行的恢复，liveness 洞）。顺序与公开
            # takeover() 一致：先退避后聚合（终态行不写 next_retry_at）。
            taken = await self._takeover_cas(
                tenant_id, conversation_id, op_id, epoch
            )
            if taken is None:
                # CAS 失败分类（与公开 takeover 同语义）：在 Conversation
                # 锁下唯一可达失败 = 终态 guard（completed/cancelled）——
                # conversation 级谓词（purged_at/state=deleted）本应先行排除，
                # 此处为防御纵深，fail closed。
                epoch_now, expiry_now, state_now = (
                    await self._lease_state_with_state(
                        tenant_id, op_id, conversation_id
                    )
                )
                if state_now in ("completed", "cancelled"):
                    raise ValueError(
                        f"purge operation {op_id} is terminal "
                        f"({state_now}); claim fail closed"
                    )
                return ClaimOutcome(
                    ClaimKind.HELD,
                    purge_operation_id=op_id,
                    existing_lease_epoch=epoch_now,
                    existing_lease_expires_at=expiry_now,
                )
            await self._recompute_backoff(tenant_id, op_id, conversation_id)
            await self._force_aggregation(tenant_id, conversation_id, op_id)
            return ClaimOutcome(
                ClaimKind.CLAIMED, token=taken, purge_operation_id=op_id
            )
        # NULL 态再 claim = acquire（占用新 slot，先计数）。
        if await self._active_lease_count(tenant_id) >= self._TENANT_CLAIM_CAP:
            return ClaimOutcome(
                ClaimKind.DEFERRED, defer_reason=DeferReason.TENANT_CAP
            )
        token = await self._acquire_cas(
            tenant_id, conversation_id, op_id, epoch
        )
        if token is None:
            return ClaimOutcome(
                ClaimKind.HELD,
                purge_operation_id=op_id,
                existing_lease_epoch=epoch,
            )
        await self._recompute_backoff(tenant_id, op_id, conversation_id)
        return ClaimOutcome(
            ClaimKind.CLAIMED, token=token, purge_operation_id=op_id
        )

    async def _claim_fresh(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        conversation: ConversationModel,
        retention_policy_snapshot: dict,
    ) -> ClaimOutcome:
        """建行判据 (i)：无行/旧 revision → 建 operation + 全 owner checkpoint
        + acquire 同事务。"""
        if await self._active_lease_count(tenant_id) >= self._TENANT_CLAIM_CAP:
            return ClaimOutcome(
                ClaimKind.DEFERRED, defer_reason=DeferReason.TENANT_CAP
            )
        operation = await self._repo.create_purge_operation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=conversation.purge_revision,
            retention_policy_snapshot=retention_policy_snapshot,
            hold_revision_snapshot=conversation.hold_revision,
        )
        for owner in operation.registry_snapshot:
            await self._repo.create_owner_checkpoint(
                tenant_id=tenant_id,
                purge_operation_id=operation.id,
                owner_key=str(owner["owner_key"]),
            )
        await self._session.flush()
        token = await self._acquire_cas(
            tenant_id, conversation_id, operation.id, 0
        )
        if token is None:
            # 同事务内刚建行，acquire 谓词（epoch 0 + NULL）必然命中；失败属
            # 状态异常，fail closed（整事务由调用方回滚）。
            raise RuntimeError(
                f"lease acquire failed on freshly created operation "
                f"{operation.id}"
            )
        await self._recompute_backoff(tenant_id, operation.id, conversation_id)
        return ClaimOutcome(
            ClaimKind.CLAIMED, token=token, purge_operation_id=operation.id
        )

    # -- renew / takeover / release -----------------------------------------

    async def renew(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        expected_lease_epoch: int,
    ) -> RenewOutcome:
        """续期心跳：current-epoch + 未到期才可 renew，成功恰好 epoch+1、
        重写 expiry；过期/旧 epoch 零写。Conversation 首锁不可省。"""
        await self._require_conversation(tenant_id, conversation_id)
        result = (
            await self._session.execute(
                self._RENEW_SQL,
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                    "expected": expected_lease_epoch,
                    "ttl": self._LEASE_TTL_SECONDS,
                },
            )
        ).fetchone()
        if result is None:
            epoch, expiry = await self._lease_state(
                tenant_id, purge_operation_id, conversation_id
            )
            if epoch != expected_lease_epoch:
                return RenewOutcome(RenewOutcomeKind.STALE)
            now = await self._db_now()
            # NULL 视为已失效：renew 谓词要求 expiry > clock，未认领行
            # （expiry NULL）不满足——分类归 EXPIRED（未持有有效租约）。
            if expiry is None or expiry <= now:
                return RenewOutcome(RenewOutcomeKind.EXPIRED)
            return RenewOutcome(RenewOutcomeKind.STALE)
        self._session.expire_all()
        token = LeaseToken(
            purge_operation_id=purge_operation_id,
            lease_epoch=int(result[0]),
            lease_expires_at=result[1],
        )
        await self._recompute_backoff(
            tenant_id, purge_operation_id, conversation_id
        )
        return RenewOutcome(RenewOutcomeKind.RENEWED, token=token)

    async def takeover(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        expected_lease_epoch: int,
    ) -> TakeoverOutcome:
        """过期/释放后接管：成功 epoch+1、写 expiry，随后**强制 coordinator
        聚合**（1.3b-i），返回新 token；在租/终态/旧 epoch 零写。"""
        await self._require_conversation(tenant_id, conversation_id)
        taken = await self._takeover_cas(
            tenant_id, conversation_id, purge_operation_id, expected_lease_epoch
        )
        if taken is not None:
            await self._recompute_backoff(
                tenant_id, purge_operation_id, conversation_id
            )
            await self._force_aggregation(
                tenant_id, conversation_id, purge_operation_id
            )
            return TakeoverOutcome(TakeoverOutcomeKind.TAKEN, token=taken)

        epoch, expiry, state = await self._lease_state_with_state(
            tenant_id, purge_operation_id, conversation_id
        )
        if state in ("completed", "cancelled"):
            return TakeoverOutcome(TakeoverOutcomeKind.TERMINAL)
        if epoch != expected_lease_epoch:
            return TakeoverOutcome(TakeoverOutcomeKind.STALE)
        if expiry is not None and expiry > await self._db_now():
            return TakeoverOutcome(TakeoverOutcomeKind.IN_LEASE)
        return TakeoverOutcome(TakeoverOutcomeKind.STALE)

    async def release(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        expected_lease_epoch: int,
    ) -> ReleaseOutcome:
        """release/yield/终态观察统一 CAS：epoch+1 并清 expiry；NULL 态视为
        已释放（零写成功返回）；旧 epoch 零写 STALE。"""
        await self._require_conversation(tenant_id, conversation_id)
        result = (
            await self._session.execute(
                self._RELEASE_SQL,
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                    "expected": expected_lease_epoch,
                },
            )
        ).fetchone()
        if result is None:
            epoch, expiry = await self._lease_state(
                tenant_id, purge_operation_id, conversation_id
            )
            if epoch != expected_lease_epoch:
                return ReleaseOutcome(ReleaseOutcomeKind.STALE)
            if expiry is None:
                return ReleaseOutcome(ReleaseOutcomeKind.ALREADY_RELEASED)
            return ReleaseOutcome(ReleaseOutcomeKind.STALE)
        self._session.expire_all()
        return ReleaseOutcome(ReleaseOutcomeKind.RELEASED, lease_epoch=int(result[0]))

    # -- 内部：锁 / 谓词 / CAS / 退避 ------------------------------------------

    async def _require_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        if await self._lock_conversation(tenant_id, conversation_id) is None:
            raise ValueError(
                f"conversation {conversation_id} not found for lease operation"
            )

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

    async def _db_now(self) -> datetime:
        return (
            await self._session.execute(text("SELECT clock_timestamp()"))
        ).scalar_one()

    async def _top_operation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> PurgeOperationModel | None:
        return (
            await self._session.execute(
                select(PurgeOperationModel)
                .where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.conversation_id == conversation_id,
                )
                .order_by(PurgeOperationModel.purge_revision.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _has_active_hold(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        """R1-S6 S6-1 裁决一（S5 代码修改点 #1）：active 判定宽化——过期
        ``expires_at`` 的 hold 不再是 active（``clock_timestamp()`` DB 时钟），
        R1-AC7 缺口（过期 hold 永久阻塞 purge）；``expires_at NULL`` 仍 active。
        """
        return (
            await self._session.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM "
                    "metaedu.agent_conversation_legal_holds "
                    "WHERE tenant_id = :tid AND conversation_id = :cid "
                    "AND state = 'active' "
                    "AND (expires_at IS NULL OR expires_at > clock_timestamp()))"
                ),
                {"tid": tenant_id, "cid": conversation_id},
            )
        ).scalar_one()

    async def _has_erasing_activity(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        checkpoint_erasing = (
            await self._session.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM "
                    "metaedu.agent_conversation_purges op "
                    "JOIN metaedu.agent_conversation_purge_owners cp "
                    "ON cp.tenant_id = op.tenant_id "
                    "AND cp.purge_operation_id = op.id "
                    "WHERE op.tenant_id = :tid AND op.conversation_id = :cid "
                    "AND cp.state = 'erasing')"
                ),
                {"tid": tenant_id, "cid": conversation_id},
            )
        ).scalar_one()
        fence_erasing = (
            await self._session.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :tid AND conversation_id = :cid "
                    "AND state = 'erasing')"
                ),
                {"tid": tenant_id, "cid": conversation_id},
            )
        ).scalar_one()
        return checkpoint_erasing or fence_erasing

    async def _active_lease_count(self, tenant_id: uuid.UUID) -> int:
        return (
            await self._session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid "
                    "AND state NOT IN ('completed', 'cancelled') "
                    "AND lease_expires_at IS NOT NULL "
                    "AND lease_expires_at > clock_timestamp()"
                ),
                {"tid": tenant_id},
            )
        ).scalar_one()

    async def _acquire_cas(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        expected_lease_epoch: int,
    ) -> LeaseToken | None:
        result = (
            await self._session.execute(
                self._ACQUIRE_SQL,
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                    "expected": expected_lease_epoch,
                    "ttl": self._LEASE_TTL_SECONDS,
                },
            )
        ).fetchone()
        if result is None:
            return None
        self._session.expire_all()
        return LeaseToken(
            purge_operation_id=purge_operation_id,
            lease_epoch=int(result[0]),
            lease_expires_at=result[1],
        )

    async def _takeover_cas(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        expected_lease_epoch: int,
    ) -> LeaseToken | None:
        result = (
            await self._session.execute(
                self._TAKEOVER_SQL,
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                    "expected": expected_lease_epoch,
                    "ttl": self._LEASE_TTL_SECONDS,
                },
            )
        ).fetchone()
        if result is None:
            return None
        self._session.expire_all()
        return LeaseToken(
            purge_operation_id=purge_operation_id,
            lease_epoch=int(result[0]),
            lease_expires_at=result[1],
        )

    async def _lease_state(
        self,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> tuple[int, datetime | None]:
        """CAS 失败后的锁内分类重读（三键，零写）；无行 fail closed。"""
        row = (
            await self._session.execute(
                text(
                    "SELECT lease_epoch, lease_expires_at FROM "
                    "metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op "
                    "AND conversation_id = :cid"
                ),
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                },
            )
        ).fetchone()
        if row is None:
            raise ValueError(
                f"purge operation {purge_operation_id} not found for lease "
                "classification"
            )
        return int(row[0]), row[1]

    async def _lease_state_with_state(
        self,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> tuple[int, datetime | None, str]:
        row = (
            await self._session.execute(
                text(
                    "SELECT lease_epoch, lease_expires_at, state FROM "
                    "metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op "
                    "AND conversation_id = :cid"
                ),
                {
                    "tid": tenant_id,
                    "op": purge_operation_id,
                    "cid": conversation_id,
                },
            )
        ).fetchone()
        if row is None:
            raise ValueError(
                f"purge operation {purge_operation_id} not found for "
                "takeover classification"
            )
        return int(row[0]), row[1], row[2]

    async def _recompute_backoff(
        self,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """退避锁内重算：min(5s × 2^min_attempt, 5m)，随 claim/renew/
        takeover 短事务写 next_retry_at（最早者仲裁，不依赖持久 jitter）。"""
        # min(attempt) 只读查询按 purge_operation_id（全局唯一 UUID）+ tenant
        # 限定；checkpoint 表无 conversation_id 列，三键收窄惯例不适用于该
        # 查询（与 coordinator 的 checkpoint 查询形态一致）。
        min_attempt = (
            await self._session.execute(
                text(
                    "SELECT min(attempt) FROM "
                    "metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :tid AND purge_operation_id = :op"
                ),
                {"tid": tenant_id, "op": purge_operation_id},
            )
        ).scalar()
        if min_attempt is None:
            min_attempt = 0
        backoff = min(
            self._BACKOFF_BASE_SECONDS * (2**int(min_attempt)),
            self._BACKOFF_CAP_SECONDS,
        )
        await self._session.execute(
            self._BACKOFF_SQL,
            {
                "tid": tenant_id,
                "op": purge_operation_id,
                "cid": conversation_id,
                "backoff": backoff,
            },
        )
        # raw 写后 expire：后续任何 ORM 访问不得命中陈旧 next_retry_at。
        self._session.expire_all()

    async def _force_aggregation(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> None:
        """1.3b-i：takeover 成功后强制一次 coordinator 聚合（同事务）。"""
        coordinator = TransactionalProjectionCoordinator(
            self._session, scan_providers=build_scan_providers(self._session)
        )
        await coordinator.aggregate_projection(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_operation_id=purge_operation_id,
        )


__all__ = [
    "ClaimKind",
    "ClaimOutcome",
    "ConversationPurgeScheduler",
    "DeferReason",
    "LeaseToken",
    "ReleaseOutcome",
    "ReleaseOutcomeKind",
    "RenewOutcome",
    "RenewOutcomeKind",
    "TakeoverOutcome",
    "TakeoverOutcomeKind",
]
