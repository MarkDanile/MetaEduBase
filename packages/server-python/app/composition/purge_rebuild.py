"""R1-S5 SCH-C：PurgeRebuildService（G1/G2 drift → Option D quiesce → rebuild/seeding）。

契约：Plan §R1-S5-B S5-B-1/2/3/5/6——G1/G2 blocked 后进入 Option D quiesce，
quiesce 收敛后 Conversation 锁内分配新 ``purge_revision=current+1`` 并同事务写回
Conversation；新 operation + 完整 checkpoint 集合（seeding）+ case-E active fence
version migration + **rebuild 后 acquire lease 并入同一事务**（禁止新 operation
无租约窗口）；predecessor/owner obligation 全函数矩阵（added/removed/re-added/
version-changed + checkpoint 缺行/fence 四态）；lineage 六项阶段 1 失败整事务
回滚；S5-B-6 幂等（旧 operation 保持 immutable）。

严守 Option D：任一 checkpoint/fence erasing 时只返回 QUIESCE 等待 settlement
port，禁止推进 revision、建新 operation 或迁移 erasing fence token。

边界：不实现 SCH-D concrete settlement、adapter lookup/replay、内部 API；不新增
migration、不改 registry；本服务**不得 commit()**（事务原子性归调用方）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.predecessor_lineage import (
    OwnerSnapshotEntry,
    PredecessorOwnerFact,
    SnapshotDiff,
    compute_lineage,
    diff_snapshots,
)
from app.composition.projection_calculator import LineageFact
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ErasureFenceModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)

_G1_G2_FAILURE_CODES = frozenset(
    {"blocked_registry_changed", "blocked_hold_revision_changed"}
)
_CARRY_REASON_SUFFIXES = (
    "_outcome_unknown",
    "_settlement_deadline_expired",
    "_adapter_unresolvable",
)


class RebuildKind(StrEnum):
    REBUILT = "rebuilt"
    QUIESCE = "quiesce"
    IDEMPOTENT = "idempotent"
    NOT_DUE = "not_due"  # 无 drift（top 非 G1/G2-blocked，非 rebuild 触发条件）


@dataclass(frozen=True, slots=True)
class RebuildOutcome:
    kind: RebuildKind
    purge_operation_id: uuid.UUID | None = None
    purge_revision: int | None = None
    lease_epoch: int | None = None
    lease_expires_at: datetime | None = None


class PurgeRebuildService:
    """G1/G2 drift → quiesce → rebuild/seeding。Conversation-first、不 commit。"""

    _LEASE_TTL_SECONDS = 600

    _ACQUIRE_SQL = text(
        "UPDATE metaedu.agent_conversation_purges SET "
        "lease_epoch = lease_epoch + 1, "
        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "
        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "
        "AND lease_epoch = :expected AND lease_expires_at IS NULL "
        "RETURNING lease_epoch, lease_expires_at"
    )
    _SEED_CHECKPOINT_SQL = text(
        "INSERT INTO metaedu.agent_conversation_purge_owners "
        "(tenant_id, purge_operation_id, owner_key, owner_version, "
        "capability_digest, state, attempt, checkpoint_digest, ack_digest, "
        "reason_code, created_at, updated_at) "
        "VALUES (:tid, :op, :owner, :ov, :cap, :state, :attempt, :cp, :ack, "
        ":reason, now(), now())"
    )
    _MIGRATE_FENCE_SQL = text(
        "UPDATE metaedu.agent_erasure_fences SET owner_version = :new "
        "WHERE tenant_id = :tid AND conversation_id = :cid AND owner_key = :k "
        "AND state = 'active' AND owner_version = :old "
        "RETURNING owner_version"
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AgentErasureRepository(session)

    async def rebuild(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        retention_policy_snapshot: dict,
    ) -> RebuildOutcome:
        """G1/G2 drift → quiesce → rebuild（单事务，不 commit）。

        锁序（S5-B-6）：Conversation 行锁 → 校验 state==DELETED → 读旧 operation
        FOR UPDATE → predecessor checkpoint/fence 只读 → 新 operation INSERT →
        全 checkpoint seed + case-E fence migration + acquire lease + 写回
        conversation.purge_revision。
        """
        conversation = await self._lock_conversation(tenant_id, conversation_id)
        if conversation is None:
            raise ValueError(f"conversation {conversation_id} not found for rebuild")
        # S5-B-6 DELETED 门禁：restore interleave → 零新行 no-op。
        if conversation.state != "deleted":
            return RebuildOutcome(RebuildKind.NOT_DUE)

        top = await self._top_operation(tenant_id, conversation_id)
        if top is None:
            return RebuildOutcome(RebuildKind.NOT_DUE)
        if top.purge_revision != conversation.purge_revision:
            # 旧 revision top（conversation 已推进）——异常形态，fail closed。
            raise ValueError("stale operation revision rejected (rebuild)")
        if top.state != "blocked" or top.failure_code not in _G1_G2_FAILURE_CODES:
            # 无 drift：幂等返回既有 rebuild（S5-B-6）或非触发。
            return RebuildOutcome(
                RebuildKind.IDEMPOTENT,
                purge_operation_id=top.id,
                purge_revision=top.purge_revision,
            )

        predecessor = top
        predecessor_checkpoints = await self._checkpoints_by_owner(
            tenant_id, predecessor.id
        )
        predecessor_fences = await self._fences_by_owner(tenant_id, conversation_id)

        # quiesce 门禁（Option D 核心）：任一 checkpoint/fence erasing → 等待
        # settlement，零推进。
        if self._has_erasing(predecessor_checkpoints, predecessor_fences):
            return RebuildOutcome(RebuildKind.QUIESCE)

        # S5-B-2 removed-owner-unfinished → fail closed（不得静默丢弃旧义务）。
        current_snapshot = self._current_snapshot()
        old_snapshot = self._snapshot_entries(predecessor.registry_snapshot)
        diff = diff_snapshots(old_snapshot, current_snapshot)
        if self._removed_unfinished(diff, predecessor_checkpoints, predecessor_fences):
            raise ValueError(
                "removed owner with unfinished obligation; rebuild fail closed"
            )

        # S5-B-3 阶段 1：lineage 派生（继承 owner 的六项验证，失败整事务回滚）。
        facts = self._predecessor_facts(
            predecessor, predecessor_checkpoints, predecessor_fences
        )
        lineage = compute_lineage(
            snapshot=current_snapshot,
            predecessor_snapshot=old_snapshot,
            predecessor_facts=facts,
            current_revision=predecessor.purge_revision + 1,
            historical_fences=frozenset(predecessor_fences),
        )
        if any(f.lineage_status == "conflict" for f in lineage.values()):
            raise ValueError("lineage stage-1 verification failed; rollback rebuild")

        # 分配新 revision + 建新 operation（同事务写回 Conversation.purge_revision）。
        new_revision = conversation.purge_revision + 1
        operation = await self._repo.create_purge_operation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=new_revision,
            retention_policy_snapshot=retention_policy_snapshot,
            hold_revision_snapshot=conversation.hold_revision,
        )
        for entry in current_snapshot:
            await self._seed_checkpoint(
                tenant_id=tenant_id,
                purge_operation_id=operation.id,
                entry=entry,
                lineage=lineage[entry.owner_key],
                predecessor_fact=facts.get(entry.owner_key),
                diff=diff,
            )
        # case-E version-changed active fence 迁移。
        for key in diff.version_changed:
            await self._migrate_active_fence(
                tenant_id, conversation_id, key,
                self._entry(current_snapshot, key).owner_version,
                self._entry(old_snapshot, key).owner_version,
            )
        await self._session.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = :r "
                "WHERE tenant_id = :tid AND id = :cid"
            ),
            {"r": new_revision, "tid": tenant_id, "cid": conversation_id},
        )
        await self._session.flush()
        token_row = (await self._session.execute(
            self._ACQUIRE_SQL,
            {
                "tid": tenant_id,
                "op": operation.id,
                "cid": conversation_id,
                "expected": 0,
                "ttl": self._LEASE_TTL_SECONDS,
            },
        )).fetchone()
        if token_row is None:
            raise RuntimeError(
                f"lease acquire failed on freshly rebuilt operation {operation.id}"
            )
        self._session.expire_all()
        return RebuildOutcome(
            RebuildKind.REBUILT,
            purge_operation_id=operation.id,
            purge_revision=new_revision,
            lease_epoch=int(token_row[0]),
            lease_expires_at=token_row[1],
        )

    # -- 内部 ---------------------------------------------------------------

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

    async def _checkpoints_by_owner(
        self, tenant_id: uuid.UUID, purge_operation_id: uuid.UUID
    ) -> dict[str, PurgeOwnerCheckpointModel]:
        rows = (
            await self._session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                    PurgeOwnerCheckpointModel.purge_operation_id == purge_operation_id,
                )
            )
        ).scalars().all()
        return {row.owner_key: row for row in rows}

    async def _fences_by_owner(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict[str, ErasureFenceModel]:
        rows = (
            await self._session.execute(
                select(ErasureFenceModel).where(
                    ErasureFenceModel.tenant_id == tenant_id,
                    ErasureFenceModel.conversation_id == conversation_id,
                )
            )
        ).scalars().all()
        return {row.owner_key: row for row in rows}

    @staticmethod
    def _has_erasing(
        checkpoints: dict[str, PurgeOwnerCheckpointModel],
        fences: dict[str, ErasureFenceModel],
    ) -> bool:
        return any(c.state == "erasing" for c in checkpoints.values()) or any(
            f.state == "erasing" for f in fences.values()
        )

    @staticmethod
    def _current_snapshot() -> list[OwnerSnapshotEntry]:
        return [
            OwnerSnapshotEntry(
                owner_key=str(o["owner_key"]),
                owner_version=int(cast(int, o["owner_version"])),
                capability_digest=str(o["capability_digest"]),
            )
            for o in registry_snapshot()
        ]

    @staticmethod
    def _snapshot_entries(snapshot: list) -> list[OwnerSnapshotEntry]:
        return [
            OwnerSnapshotEntry(
                owner_key=str(o["owner_key"]),
                owner_version=int(o["owner_version"]),
                capability_digest=str(o["capability_digest"]),
            )
            for o in snapshot
        ]

    @staticmethod
    def _entry(
        snapshot: list[OwnerSnapshotEntry], owner_key: str
    ) -> OwnerSnapshotEntry:
        return next(e for e in snapshot if e.owner_key == owner_key)

    @staticmethod
    def _removed_unfinished(
        diff: SnapshotDiff,
        checkpoints: dict[str, PurgeOwnerCheckpointModel],
        fences: dict[str, ErasureFenceModel],
    ) -> bool:
        for key in diff.removed:
            cp = checkpoints.get(key)
            fence = fences.get(key)
            if cp is None or cp.state != "acked" or fence is None or fence.state != "erased":
                return True
        return False

    @staticmethod
    def _predecessor_facts(
        predecessor: PurgeOperationModel,
        checkpoints: dict[str, PurgeOwnerCheckpointModel],
        fences: dict[str, ErasureFenceModel],
    ) -> dict[str, PredecessorOwnerFact]:
        facts: dict[str, PredecessorOwnerFact] = {}
        keys = set(checkpoints) | set(fences)
        for key in keys:
            cp = checkpoints.get(key)
            fence = fences.get(key)
            facts[key] = PredecessorOwnerFact(
                checkpoint_state=cp.state if cp else None,
                checkpoint_reason=cp.reason_code if cp else None,
                checkpoint_owner_version=cp.owner_version if cp else None,
                checkpoint_capability_digest=cp.capability_digest if cp else None,
                checkpoint_ack_digest=cp.ack_digest if cp else None,
                fence_state=fence.state if fence else None,
                fence_owner_version=fence.owner_version if fence else None,
                fence_purge_revision=fence.purge_revision if fence else None,
                fence_ack_digest=fence.ack_digest if fence else None,
            )
        return facts

    async def _seed_checkpoint(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        entry: OwnerSnapshotEntry,
        lineage: LineageFact,
        predecessor_fact: PredecessorOwnerFact | None,
        diff: SnapshotDiff,
    ) -> None:
        """按 lineage/obligation kind 建新 checkpoint（pending/acked-seed/
        blocked-carry/failed-carry）。"""
        kind = lineage.expected_obligation_kind
        if kind == "inherited_acked":
            assert predecessor_fact is not None
            state, reason = "acked", None
            cp_digest = predecessor_fact.checkpoint_ack_digest
            ack_digest = predecessor_fact.fence_ack_digest
            attempt = 0
        elif kind == "carried_blocked":
            assert predecessor_fact is not None
            state, reason = "blocked", predecessor_fact.checkpoint_reason
            cp_digest, ack_digest = predecessor_fact.checkpoint_ack_digest, None
            attempt = 0
        elif kind == "carried_failed":
            assert predecessor_fact is not None
            state, reason = "failed", predecessor_fact.checkpoint_reason
            cp_digest, ack_digest = None, None
            attempt = 0
        else:  # native_pending
            state, reason, cp_digest, ack_digest, attempt = "pending", None, None, None, 0
        await self._session.execute(
            self._SEED_CHECKPOINT_SQL,
            {
                "tid": tenant_id,
                "op": purge_operation_id,
                "owner": entry.owner_key,
                "ov": entry.owner_version,
                "cap": entry.capability_digest,
                "state": state,
                "attempt": attempt,
                "cp": cp_digest,
                "ack": ack_digest,
                "reason": reason,
            },
        )

    async def _migrate_active_fence(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        new_version: int,
        old_version: int,
    ) -> None:
        row = (
            await self._session.execute(
                self._MIGRATE_FENCE_SQL,
                {
                    "tid": tenant_id,
                    "cid": conversation_id,
                    "k": owner_key,
                    "new": new_version,
                    "old": old_version,
                },
            )
        ).fetchone()
        if row is None:
            raise ValueError(
                f"case-E fence migration failed for {owner_key!r}; fail closed"
            )


__all__ = ["PurgeRebuildService", "RebuildKind", "RebuildOutcome"]
