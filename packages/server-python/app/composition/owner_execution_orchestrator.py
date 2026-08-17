"""R1-S5 SCH-B：OwnerExecutionOrchestrator（B/C/D 联合交付 stack root）。

契约：Plan §R1-S5-D S5-SCH-1.3/1.3b/1.4/2 + SCH-B 范围（S5-SCH-3）——
owner 字典序循环、每 entry 前 renew lease、周期级 token 重验、owner 级
checkpoint/fence 态重读、participant 返回后独立事务 coordinator、takeover
后账本恢复（acked 不重跑）、显式 ``tick()`` 周期全量重算、retry 预算 3 +
pre-window 豁免 + 预算耗尽写 failed。

边界（S5-SCH-9）：
- owner participant 经显式 port（``OwnerEntryPort``）注入，本模块不 import
  任何 participant，**六 erase 入口静态守卫保持不可达**；
- SCH-B 不直接写 fence——erasing 收口（``closeout_erasing``）与 failed-fence
  收敛（``converge_failed_fence``）由窄 ``SettlementPort`` 承担（生产 concrete
  port 留给 SCH-D，B 测试用判别力 fake）；
- 不实现 SCH-C rebuild/seeding、SCH-D settlement、完整 API、指标日志、
  participant 三键收窄；无后台循环（``tick()`` 由调用方显式驱动）。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.agent_erasure_registry import registry_digest, registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ConversationPurgeScheduler,
    RenewOutcomeKind,
)
from app.composition.transactional_projection_coordinator import (
    ScanProvider,
    TransactionalProjectionCoordinator,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)

RETRY_BUDGET = 3

# S5-A-3 族 B 封闭白名单：erase_timeout / adapter_unavailable / scan 族 + pre-window gate。
_RETRYABLE_SUFFIXES = ("_erase_timeout", "_adapter_unavailable", "_scan_nonzero")
_PRE_WINDOW_GATE_REASONS = frozenset(
    {
        "purge_blocked_by_legal_hold",
        "purge_blocked_by_unresolved_action",
        "purge_blocked_by_conversation_scope_gate",
        "purge_owner_unavailable",
        "operator_suppressed",
    }
)
# 禁止重开：outcome_unknown / settlement_deadline_expired / adapter_unresolvable。
# purge_owner_ack_conflict 与 G1/G2-blocked 为 coordinator-level，participant 不写。
_REJECT_SUFFIXES = (
    "_outcome_unknown",
    "_settlement_deadline_expired",
    "_adapter_unresolvable",
)


def is_pre_window_gate(reason: str) -> bool:
    return reason in _PRE_WINDOW_GATE_REASONS


def is_retryable_reason(reason: str) -> bool:
    return is_pre_window_gate(reason) or reason.endswith(_RETRYABLE_SUFFIXES)


def is_reject_reason(reason: str) -> bool:
    return reason.endswith(_REJECT_SUFFIXES)


@dataclass(frozen=True, slots=True)
class OwnerEntryRequest:
    """一次 owner entry 的 fencing 参数（token 重验后的锁内值）。

    ``session`` 是 orchestrator 本次 entry 事务的 session（entry port 用其
    构造 participant，同事务观察 renew 后的 lease epoch）。
    """

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    purge_operation_id: uuid.UUID
    purge_revision: int
    expected_operation_revision: int
    expected_lease_epoch: int
    owner_key: str
    session: AsyncSession


@dataclass(frozen=True, slots=True)
class OwnerEntryOutcome:
    """entry port 返回的规范化结果（participant 已自记 blocked / 抛 drift）。"""

    acked: bool
    blocked_reason: str | None


OwnerEntryPort = Callable[[OwnerEntryRequest], Awaitable[OwnerEntryOutcome]]


class SettlementPort(Protocol):
    """窄 settlement port（SCH-D 依赖边界；SCH-B 只定义接口，不实现收口）。"""

    async def closeout_erasing(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> None: ...

    async def converge_failed_fence(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CycleOutcome:
    """一次 run_cycle 的可观测结果。"""

    aggregation_count: int
    owners_entered: tuple[str, ...]
    owners_skipped: tuple[str, ...]


class OwnerExecutionOrchestrator:
    """owner 顺序执行编排器。全部短事务、不 commit 外层（事务归各短事务）。"""

    _TERMINAL_STATES = frozenset({"completed", "cancelled"})

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        owner_entries: Mapping[str, OwnerEntryPort],
        settlement_port: SettlementPort,
        scan_providers: Callable[[AsyncSession], Mapping[str, ScanProvider]],
    ) -> None:
        self._session_factory = session_factory
        self._owner_entries = owner_entries
        self._settlement = settlement_port
        self._scan_providers = scan_providers

    # -- 主入口 ------------------------------------------------------------

    async def run_cycle(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> CycleOutcome:
        """跑一轮 owner 顺序执行（无后台循环；调用方驱动）。

        周期级 token 重验通过后，逐 owner：renew lease → checkpoint/fence
        重读 → 跳过/交 settlement/entry → 每 entry 后独立事务 coordinator。
        drift 或租约失效 → fail closed（raise，零 entry）。
        """
        await self._verify_cycle_token(
            tenant_id, conversation_id, purge_operation_id
        )
        entered: list[str] = []
        skipped: list[str] = []
        aggregations = 0
        for owner_key in (str(o["owner_key"]) for o in registry_snapshot()):
            entry_port = self._owner_entries.get(owner_key)
            action = await self._run_owner(
                tenant_id,
                conversation_id,
                purge_operation_id,
                owner_key,
                entry_port,
            )
            if action == "entered":
                entered.append(owner_key)
                await self._aggregate(tenant_id, conversation_id, purge_operation_id)
                aggregations += 1
            elif action == "skipped":
                skipped.append(owner_key)
        return CycleOutcome(
            aggregation_count=aggregations,
            owners_entered=tuple(entered),
            owners_skipped=tuple(skipped),
        )

    async def tick(self) -> int:
        """1.3b-ii：对 claim 候选集（非终态 + 在租）全量聚合（无后台循环）。"""
        candidates = await self._candidate_operations()
        for op_id, tid, cid in candidates:
            await self._aggregate(tid, cid, op_id)
        return len(candidates)

    # -- 周期级 token 重验 --------------------------------------------------

    async def _verify_cycle_token(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            conversation = (
                await session.execute(
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
                    f"conversation {conversation_id} not found for orchestration"
                )
            operation = (
                await session.execute(
                    select(PurgeOperationModel)
                    .where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.id == purge_operation_id,
                        PurgeOperationModel.conversation_id == conversation_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if operation is None:
                raise ValueError(
                    f"purge operation {purge_operation_id} not found for "
                    "orchestration"
                )
            if operation.purge_revision != conversation.purge_revision:
                raise ValueError("stale operation revision rejected (I2 gate)")
            if operation.hold_revision_snapshot != conversation.hold_revision:
                raise ValueError("hold_revision drift; cycle fail closed")
            if operation.registry_digest != registry_digest():
                raise ValueError("registry drift; cycle fail closed")
            if operation.state in self._TERMINAL_STATES:
                raise ValueError(
                    f"operation {operation.state!r} is terminal; nothing to "
                    "orchestrate"
                )
            now = await self._db_now(session)
            if operation.lease_expires_at is None or operation.lease_expires_at <= now:
                raise ValueError(
                    "lease expired or not held; re-enter claim (fail closed)"
                )

    # -- 单 owner -----------------------------------------------------------

    async def _run_owner(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
        entry_port: OwnerEntryPort | None,
    ) -> str:
        """单个 owner 的 entry 事务：renew → 重读 → 决策 → entry。返回动作。"""
        async with self._session_factory() as session, session.begin():
            # renew lease（每 entry 前心跳，Conversation-first 短事务）。
            renewed = await ConversationPurgeScheduler(session).renew(
                tenant_id=tenant_id,
                purge_operation_id=purge_operation_id,
                conversation_id=conversation_id,
                expected_lease_epoch=await self._lease_epoch(
                    session, tenant_id, purge_operation_id, conversation_id
                ),
            )
            if renewed.kind is not RenewOutcomeKind.RENEWED:
                raise ValueError(
                    f"lease renew failed ({renewed.kind.value}); re-enter claim"
                )
            assert renewed.token is not None  # RENEWED 必带 token
            renewed_epoch = renewed.token.lease_epoch

            checkpoint = await self._checkpoint(
                session, tenant_id, purge_operation_id, owner_key
            )
            if checkpoint is None:
                raise ValueError(
                    f"checkpoint missing for owner {owner_key!r}; fail closed"
                )
            state = checkpoint.state
            reason = checkpoint.reason_code
            attempt = checkpoint.attempt

            if state in ("acked", "failed"):
                return "skipped"
            if state == "erasing":
                await self._settlement.closeout_erasing(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    purge_operation_id=purge_operation_id,
                    owner_key=owner_key,
                )
                return "skipped"
            if state == "blocked":
                if reason is not None and not is_retryable_reason(reason):
                    return "skipped"  # 拒绝域：reconcile-only，不重开
                if (
                    reason is not None
                    and not is_pre_window_gate(reason)
                    and attempt >= RETRY_BUDGET
                ):
                    await self._write_failed(
                        session, tenant_id, purge_operation_id, owner_key, reason
                    )
                    await self._settlement.converge_failed_fence(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        purge_operation_id=purge_operation_id,
                        owner_key=owner_key,
                    )
                    return "skipped"
                # 白名单 / pre-window：重试。

            if entry_port is None:
                raise ValueError(
                    f"no entry port for owner {owner_key!r}; fail closed"
                )
            operation_revision = await self._operation_revision(
                session, tenant_id, purge_operation_id, conversation_id
            )
            outcome = await entry_port(
                OwnerEntryRequest(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    purge_operation_id=purge_operation_id,
                    purge_revision=await self._conversation_purge_revision(
                        session, tenant_id, conversation_id
                    ),
                    expected_operation_revision=operation_revision,
                    expected_lease_epoch=renewed_epoch,
                    owner_key=owner_key,
                    session=session,
                )
            )
            if not outcome.acked and outcome.blocked_reason is not None:
                await self._schedule_retry(
                    session, tenant_id, purge_operation_id, conversation_id
                )
            return "entered"

    # -- 辅助 ---------------------------------------------------------------

    async def _aggregate(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            coordinator = TransactionalProjectionCoordinator(
                session, scan_providers=self._scan_providers(session)
            )
            await coordinator.aggregate_projection(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_operation_id=purge_operation_id,
            )

    async def _candidate_operations(self) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
        async with self._session_factory() as session:
            rows = await session.execute(
                text(
                    "SELECT id, tenant_id, conversation_id FROM "
                    "metaedu.agent_conversation_purges "
                    "WHERE state NOT IN ('completed', 'cancelled') "
                    "AND lease_expires_at IS NOT NULL "
                    "AND lease_expires_at > clock_timestamp()"
                )
            )
            return [(r[0], r[1], r[2]) for r in rows]

    async def _write_failed(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
        reason: str,
    ) -> None:
        await session.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "state = 'failed', reason_code = :reason "
                "WHERE tenant_id = :tid AND purge_operation_id = :op "
                "AND owner_key = :k"
            ),
            {"tid": tenant_id, "op": purge_operation_id, "k": owner_key, "reason": reason},
        )

    async def _schedule_retry(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """blocked 后重算 next_retry_at（min 仲裁，不依赖持久 jitter）。"""
        min_attempt = (
            await session.execute(
                text(
                    "SELECT min(attempt) FROM "
                    "metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :tid AND purge_operation_id = :op"
                ),
                {"tid": tenant_id, "op": purge_operation_id},
            )
        ).scalar()
        backoff = min(5 * (2 ** int(min_attempt or 0)), 300)
        await session.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET "
                "next_retry_at = clock_timestamp() + make_interval(secs => :b) "
                "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
            ),
            {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id, "b": backoff},
        )

    async def _checkpoint(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> PurgeOwnerCheckpointModel | None:
        return (
            await session.execute(
                select(PurgeOwnerCheckpointModel)
                .where(
                    PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                    PurgeOwnerCheckpointModel.purge_operation_id == purge_operation_id,
                    PurgeOwnerCheckpointModel.owner_key == owner_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _lease_epoch(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> int:
        return (
            await session.execute(
                text(
                    "SELECT lease_epoch FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
                ),
                {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id},
            )
        ).scalar_one()

    async def _operation_revision(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> int:
        return (
            await session.execute(
                text(
                    "SELECT revision FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
                ),
                {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id},
            )
        ).scalar_one()

    async def _conversation_purge_revision(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> int:
        return (
            await session.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_conversations "
                    "WHERE tenant_id = :tid AND id = :cid"
                ),
                {"tid": tenant_id, "cid": conversation_id},
            )
        ).scalar_one()

    async def _db_now(self, session: AsyncSession) -> datetime:
        return (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()


__all__ = [
    "CycleOutcome",
    "OwnerEntryOutcome",
    "OwnerEntryPort",
    "OwnerEntryRequest",
    "OwnerExecutionOrchestrator",
    "RETRY_BUDGET",
    "SettlementPort",
    "is_pre_window_gate",
    "is_reject_reason",
    "is_retryable_reason",
]
