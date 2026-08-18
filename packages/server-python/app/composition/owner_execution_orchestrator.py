"""R1-S5 SCH-B：OwnerExecutionOrchestrator（B/C/D 联合交付 stack root）。

契约：Plan §R1-S5-D S5-SCH-1.3/1.3b/1.4/2 + SCH-B 范围（S5-SCH-3）——
owner 字典序循环、每 entry 前 renew lease、周期级 token 重验、owner 级
checkpoint/fence 态重读、participant 返回后独立事务 coordinator、takeover
后账本恢复（acked 不重跑）、显式 ``tick()`` 周期全量重算、retry 预算 3 +
pre-window 豁免 + 预算耗尽写 failed。

边界（S5-SCH-9）：
- owner participant 经显式 port（``OwnerEntryPort``）注入，本模块不 import
  任何 participant，**六 owner 的 erase 入口静态守卫保持不可达**；
- SCH-B 不直接写 fence——erasing 收口（``closeout_erasing``）与 failed-fence
  收敛（``converge_failed_fence``）由窄 ``SettlementPort`` 承担（生产 concrete
  port 留给 SCH-D，B 测试用判别力 fake）；
- 不实现 SCH-C rebuild/seeding、SCH-D settlement、完整 API、指标日志、
  participant 三键收窄；无后台循环（``tick()`` 由调用方显式驱动）。

实现注记：
- renew 为 operation 级心跳，先于 owner 级 checkpoint/fence 态重读——跳过
  路径（acked/failed/erasing/拒绝域）仍会写 lease（S5-SCH-1.3(b)「零副作用」
  字面放宽为「零 owner 副作用」：lease 心跳为 1.1 所需）。
- attempt 统一 retry 计数：scan 族 owner 由编排方 entry 前推进，external/
  runtime（Tx1 双事务）在 entry 内部自行推进（``_TX1_OWNERS``），避免
  double-count。
- next_retry_at 由 cycle 末 ``_arbitrate_retry`` 统一仲裁（min over 仍 blocked
  的 owner，无则 NULL），收敛 renew 每 entry 重写的中间态。
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

# Tx1 双事务 participant 在 entry 内部（pending/blocked→erasing）推进 attempt；
# 编排方对这两 owner 不重复推进（否则 double-count）。其余 scan 族 owner 无
# Tx1，attempt 推进由编排方承担（SCH-B 返修裁决：S5-SCH-1.4「participant
# 承担」在 scan 族不成立，编排方补齐统一 retry 计数）。
_TX1_OWNERS = frozenset({"external.payload.v1", "runtime.private.v1"})


class OrchestrationDriftError(ValueError):
    """编排 drift/租约失效/行缺失统一信号（fail-closed，重入 claim 判定）。"""

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


def is_pre_window_gate(reason: str | None) -> bool:
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
    """窄 settlement port（SCH-D 依赖边界；SCH-B 只定义接口，不实现收口）。

    裁决二（2026-08-18）：settlement 自管事务（T1 锁内读 → 锁外 adapter I/O →
    T2 重验落账），**不得在调用方事务内执行**——编排方在 entry 事务提交（释放
    全部 DB 锁）后才调用本 port；adapter I/O 永不处于持锁事务中。
    """

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

    _TERMINAL_STATES = frozenset({"completed", "cancelled", "failed"})

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
        # cycle 末统一仲裁 next_retry_at（min over 仍 blocked 的 owner；无则清
        # NULL——renew 每 entry 重写 next_retry_at 的中间态在此被收敛）。
        await self._arbitrate_retry(tenant_id, purge_operation_id, conversation_id)
        return CycleOutcome(
            aggregation_count=aggregations,
            owners_entered=tuple(entered),
            owners_skipped=tuple(skipped),
        )

    async def tick(self) -> int:
        """1.3b-ii：对 claim 候选集（非终态 + 在租 + 退避已到）全量聚合
        （无后台循环）。单候选聚合异常不中止整个 tick。"""
        candidates = await self._candidate_operations()
        aggregated = 0
        for op_id, tid, cid in candidates:
            try:
                await self._aggregate(tid, cid, op_id)
            except ValueError:
                continue
            aggregated += 1
        return aggregated

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
                raise OrchestrationDriftError(
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
                raise OrchestrationDriftError(
                    f"purge operation {purge_operation_id} not found for "
                    "orchestration"
                )
            if operation.purge_revision != conversation.purge_revision:
                raise OrchestrationDriftError(
                    "stale operation revision rejected (I2 gate)"
                )
            if operation.hold_revision_snapshot != conversation.hold_revision:
                raise OrchestrationDriftError("hold_revision drift; cycle fail closed")
            if operation.registry_digest != registry_digest():
                raise OrchestrationDriftError("registry drift; cycle fail closed")
            if operation.state in self._TERMINAL_STATES:
                if operation.state == "failed":
                    raise OrchestrationDriftError(
                        "operation failed; awaiting SCH-C rebuild"
                    )
                raise OrchestrationDriftError(
                    f"operation {operation.state!r} is terminal; nothing to "
                    "orchestrate"
                )
            now = await self._db_now(session)
            if operation.lease_expires_at is None or operation.lease_expires_at <= now:
                raise OrchestrationDriftError(
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
        """单个 owner 的 entry 事务：renew → 重读 → 决策 → entry。返回动作。

        裁决二（2026-08-18）：settlement 调用（closeout_erasing /
        converge_failed_fence）在 entry 事务**提交（释放全部 DB 锁）之后**执行
        ——settlement 自管事务（T1 锁内读 → 锁外 adapter I/O → T2 重验落账），
        adapter I/O 永不处于持锁事务中。
        """
        erasing = False
        budget_written = False
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
                raise OrchestrationDriftError(
                    f"lease renew failed ({renewed.kind.value}); re-enter claim"
                )
            assert renewed.token is not None  # RENEWED 必带 token
            renewed_epoch = renewed.token.lease_epoch

            checkpoint = await self._checkpoint(
                session, tenant_id, purge_operation_id, owner_key
            )
            if checkpoint is None:
                raise OrchestrationDriftError(
                    f"checkpoint missing for owner {owner_key!r}; fail closed"
                )
            state = checkpoint.state
            reason = checkpoint.reason_code
            attempt = checkpoint.attempt

            if state in ("acked", "failed"):
                return "skipped"
            if state == "erasing":
                # 交 settlement 收口：entry 事务先提交（释放锁），事务外调用。
                erasing = True
            elif state == "blocked":
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
                    # fence 收敛经 settlement：entry 事务先提交（raw failed 落库 +
                    # 释放锁），事务外调用 converge。
                    budget_written = True
                # 白名单 / pre-window：重试（走 entry）。

            if not erasing and not budget_written:
                if entry_port is None:
                    raise OrchestrationDriftError(
                        f"no entry port for owner {owner_key!r}; fail closed"
                    )
                # 统一 retry 计数：scan 族 owner 的 attempt 由编排方推进（Tx1 owner
                # 在 entry 内自行推进，见 _TX1_OWNERS）。**pre-window gate reason
                # 不计入重试预算**（S5-SCH-1.4 冻结）——gate 期重入不推进 attempt，
                # 避免长期 gate 解除后首个真实失败即触发预算耗尽落 failed。
                if owner_key not in _TX1_OWNERS and not is_pre_window_gate(reason):
                    await session.execute(
                        text(
                            "UPDATE metaedu.agent_conversation_purge_owners SET "
                            "attempt = attempt + 1 "
                            "WHERE tenant_id = :tid AND purge_operation_id = :op "
                            "AND owner_key = :k"
                        ),
                        {"tid": tenant_id, "op": purge_operation_id, "k": owner_key},
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
                # outcome 仅用于 entry 副作用（participant 自记 blocked/acked），
                # 编排方不据此写 checkpoint；blocked 态由下轮 cycle 锁内重读裁决。
                _ = outcome
                return "entered"
            # erasing / budget_written：事务提交（不 return），走事务外阶段。
        # ---- entry 事务已提交（全部 DB 锁已释放）：settlement 阶段 ----
        if erasing:
            await self._settlement.closeout_erasing(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_operation_id=purge_operation_id,
                owner_key=owner_key,
            )
            return "skipped"
        if budget_written:
            await self._settlement.converge_failed_fence(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_operation_id=purge_operation_id,
                owner_key=owner_key,
            )
            return "skipped"
        raise AssertionError("unreachable: settlement 阶段必须有 erasing/budget 标志")

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
                    "AND lease_expires_at > clock_timestamp() "
                    "AND (next_retry_at IS NULL OR next_retry_at <= clock_timestamp())"
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

    async def _arbitrate_retry(
        self,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """cycle 末仲裁 next_retry_at：min over 仍 blocked 的 owner（不依赖
        持久 jitter）；无 blocked owner 则清 NULL（acked/failed 不参与排程）。"""
        async with self._session_factory() as session, session.begin():
            min_attempt = (
                await session.execute(
                    text(
                        "SELECT min(attempt) FROM "
                        "metaedu.agent_conversation_purge_owners "
                        "WHERE tenant_id = :tid AND purge_operation_id = :op "
                        "AND state = 'blocked'"
                    ),
                    {"tid": tenant_id, "op": purge_operation_id},
                )
            ).scalar()
            if min_attempt is None:
                await session.execute(
                    text(
                        "UPDATE metaedu.agent_conversation_purges SET "
                        "next_retry_at = NULL "
                        "WHERE tenant_id = :tid AND id = :op "
                        "AND conversation_id = :cid"
                    ),
                    {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id},
                )
                return
            backoff = min(5 * (2 ** int(min_attempt)), 300)
            await session.execute(
                text(
                    "UPDATE metaedu.agent_conversation_purges SET "
                    "next_retry_at = clock_timestamp() + "
                    "make_interval(secs => :b) "
                    "WHERE tenant_id = :tid AND id = :op "
                    "AND conversation_id = :cid"
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
        row = (
            await session.execute(
                text(
                    "SELECT lease_epoch FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
                ),
                {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id},
            )
        ).scalar_one_or_none()
        if row is None:
            raise OrchestrationDriftError(
                f"purge operation {purge_operation_id} not found (lease epoch)"
            )
        return row

    async def _operation_revision(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> int:
        row = (
            await session.execute(
                text(
                    "SELECT revision FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid"
                ),
                {"tid": tenant_id, "op": purge_operation_id, "cid": conversation_id},
            )
        ).scalar_one_or_none()
        if row is None:
            raise OrchestrationDriftError(
                f"purge operation {purge_operation_id} not found (revision)"
            )
        return row

    async def _conversation_purge_revision(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> int:
        row = (
            await session.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_conversations "
                    "WHERE tenant_id = :tid AND id = :cid"
                ),
                {"tid": tenant_id, "cid": conversation_id},
            )
        ).scalar_one_or_none()
        if row is None:
            raise OrchestrationDriftError(
                f"conversation {conversation_id} not found (purge revision)"
            )
        return row

    async def _db_now(self, session: AsyncSession) -> datetime:
        return (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()


__all__ = [
    "CycleOutcome",
    "OrchestrationDriftError",
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
