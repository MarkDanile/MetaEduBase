"""R1-S5 B/C/D 联合组合根（S5-SCH-3 组合根启用门禁，联合 merged-boundary）。

契约：Plan §R1-S5-D S5-SCH-3「组合根启用门禁（冻结）」——SCH-B 的 erase 入口生产
可达性翻转不得早于 SCH-C（quiesce+rebuild）与 SCH-D（settlement 进入点，含
failed 收敛）同窗口交付；启用时 drift/窗口崩溃的收口路径必须已在网。B/C/D 三
slice 联合 merged-boundary 之前，erase 入口保持不可达。

本模块是 scheduler 组合根的**唯一生产装配点**（``test_s5i2_production_wiring_
boundary`` 对 ``scheduler_composition.py`` 放行六 owner erase 入口引用，条件是本
模块同时包含组合根启用门禁）。``build_scheduler_composition`` 在 B/C/D 全部元素齐备
且依赖完整时才返回可执行组合；任一 slice 缺失 / settlement / rebuild / coordinator
/ claim 任一依赖缺失 → ``CompositionNotReadyError`` fail closed。

**本批次不接线生产调用方**（不新增后台循环/HTTP/CLI/API/migration/registry
capability）：``build_scheduler_composition`` 只由测试驱动。external/runtime
adapter 槽位 = ``FailClosedAdapter``（能力位恒 False + registry 保持 False）——
不伪造生产能力，任何 external/runtime erase 仍在 capability 门禁 fail closed。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.conversation_purge_scheduler import ConversationPurgeScheduler
from app.composition.external_ref_erasure_participant import (
    ExternalPayloadErasureParticipant,
)
from app.composition.owner_execution_orchestrator import (
    OwnerEntryOutcome,
    OwnerEntryPort,
    OwnerEntryRequest,
    OwnerExecutionOrchestrator,
    SettlementPort,
)
from app.composition.purge_rebuild import PurgeRebuildService
from app.composition.runtime_erasure_participant import RuntimeErasureParticipant
from app.composition.settlement import SettlementService
from app.composition.transactional_projection_coordinator import (
    ScanProvider,
    build_scan_providers,
)
from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    ExecutionErasureParticipant,
)
from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (
    ExecutionTransportErasureParticipant,
)
from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
    WorkspaceErasureParticipant,
)
from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
    WorkspaceTransportErasureParticipant,
)

# 六 owner 固定键（S5-A-1 registry，S5-SCH-0）。
_ALL_OWNER_KEYS = (
    "workspace.core.v1",
    "execution.core.v1",
    "workspace.transport.v1",
    "execution.transport.v1",
    "external.payload.v1",
    "runtime.private.v1",
)


class CompositionNotReadyError(RuntimeError):
    """B/C/D 联合门禁未满足 → 生产调用方不得进入 owner execution（fail closed）。"""


class FailClosedAdapter:
    """external/runtime adapter 槽位（无生产 adapter，不伪造生产能力）。

    能力位恒 False（不宣称幂等重放/receipt lookup）；registry 保持
    ``erase_available=False``——即使组合完整，external/runtime erase 仍在
    capability 门禁 fail closed。
    """

    adapter_key = "unwired.fail-closed.v0"
    adapter_version = 1
    supports_idempotent_replay = False
    supports_receipt_lookup = False

    async def delete_object(self, **kwargs):  # pragma: no cover - 不可达
        raise AssertionError("no production external adapter wired; fail closed")

    async def destroy_session(self, **kwargs):  # pragma: no cover - 不可达
        raise AssertionError("no production runtime adapter wired; fail closed")

    async def receipt_lookup(self, **kwargs):  # pragma: no cover - 不可达
        raise AssertionError("no production adapter receipt lookup; fail closed")


def _owner_entry(
    participant_cls,
    erase_method: str,
    *,
    adapter=None,
    acked: Callable[[Any], bool],
) -> OwnerEntryPort:
    """以 ``OwnerEntryRequest`` 驱动 participant erase 的统一 entry port。

    ``erase_method`` 名显式引用六 owner erase 入口（静态守卫对本模块放行，
    条件 = 本模块含组合根启用门禁）。
    """

    async def entry(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        if adapter is None:
            participant = participant_cls(request.session)
        else:
            participant = participant_cls(request.session, adapter)
        summary = await getattr(participant, erase_method)(
            tenant_id=request.tenant_id,
            conversation_id=request.conversation_id,
            purge_revision=request.purge_revision,
            purge_operation_id=request.purge_operation_id,
            expected_operation_revision=request.expected_operation_revision,
            expected_lease_epoch=request.expected_lease_epoch,
        )
        return OwnerEntryOutcome(acked=acked(summary), blocked_reason=None)

    return entry


def build_owner_entries(
    *,
    external_adapter: object = FailClosedAdapter(),
    runtime_adapter: object = FailClosedAdapter(),
) -> Mapping[str, OwnerEntryPort]:
    """六 owner participant map（同一联合边界装配）。

    external/runtime 槽位 = ``FailClosedAdapter`` + registry ``erase_available``
    保持 False——capability 门禁 fail closed（不伪造生产能力）；其余四 owner 为
    真实 participant 入口。
    """
    return {
        "workspace.core.v1": _owner_entry(
            WorkspaceErasureParticipant,
            "erase_conversation_body",
            acked=lambda s: bool(s.erased),
        ),
        "execution.core.v1": _owner_entry(
            ExecutionErasureParticipant,
            "erase_execution_body",
            acked=lambda s: bool(s.erased),
        ),
        "workspace.transport.v1": _owner_entry(
            WorkspaceTransportErasureParticipant,
            "erase_transport_owner",
            acked=lambda s: bool(s.erased),
        ),
        "execution.transport.v1": _owner_entry(
            ExecutionTransportErasureParticipant,
            "erase_transport_owner",
            acked=lambda s: bool(s.erased),
        ),
        "external.payload.v1": _owner_entry(
            ExternalPayloadErasureParticipant,
            "erase_external_payload",
            adapter=external_adapter,
            acked=lambda s: bool(s.scan.total == 0),
        ),
        "runtime.private.v1": _owner_entry(
            RuntimeErasureParticipant,
            "erase_runtime_session",
            adapter=runtime_adapter,
            acked=lambda s: bool(s.scan.total == 0),
        ),
    }


def coordinator_scan_providers(
    session: AsyncSession,
) -> Mapping[str, ScanProvider]:
    """coordinator 扫描提供者（orchestrator 每 owner 后以之构造
    ``TransactionalProjectionCoordinator`` 聚合，S5-SCH-1.3「每 entry 后
    coordinator」）。"""
    return build_scan_providers(session)


def build_settlement_port(
    *,
    adapter_resolver=None,
) -> SettlementPort:
    """SCH-D concrete SettlementPort（entry 事务内收口）。

    以编排方传入的 ``session`` 构造 ``SettlementService``（同一事务、同一
    Conversation-first 锁上下文），不自建会话——否则与 entry 事务持有的行锁
    死锁。默认 adapter resolver = ``FailClosedAdapterResolver``（态 6 fail
    closed）。
    """

    class _ConcreteSettlementPort:
        async def closeout_erasing(
            self,
            *,
            session: AsyncSession,
            tenant_id: uuid.UUID,
            conversation_id: uuid.UUID,
            purge_operation_id: uuid.UUID,
            owner_key: str,
        ) -> None:
            service = SettlementService(
                session,
                scan_providers=build_scan_providers(session),
                adapter_resolver=adapter_resolver,
            )
            await service.closeout_erasing(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_operation_id=purge_operation_id,
                owner_key=owner_key,
            )

        async def converge_failed_fence(
            self,
            *,
            session: AsyncSession,
            tenant_id: uuid.UUID,
            conversation_id: uuid.UUID,
            purge_operation_id: uuid.UUID,
            owner_key: str,
        ) -> None:
            service = SettlementService(
                session,
                scan_providers=build_scan_providers(session),
                adapter_resolver=adapter_resolver,
            )
            await service.converge_failed_fence(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_operation_id=purge_operation_id,
                owner_key=owner_key,
            )

    return _ConcreteSettlementPort()


@dataclass(frozen=True, slots=True)
class SchedulerComposition:
    """B/C/D 联合组合根装配产物（本批次无生产调用方）。

    - ``orchestrator``：SCH-B owner 顺序执行编排器（含每 owner 后 coordinator）。
    - ``owner_entries``：六 owner participant map（external/runtime 槽位 fail
      closed）。
    - ``settlement``：SCH-D concrete SettlementPort（entry 事务内收口）。
    - ``claim``/``rebuild``：SCH-A claim/lease 与 SCH-C rebuild 独立事务入口。
    """

    session_factory: async_sessionmaker
    orchestrator: OwnerExecutionOrchestrator
    owner_entries: Mapping[str, OwnerEntryPort]
    settlement: SettlementPort

    async def run_cycle(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ):
        return await self.orchestrator.run_cycle(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_operation_id=purge_operation_id,
        )

    async def tick(self) -> int:
        return await self.orchestrator.tick()

    async def claim(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        retention_policy_snapshot: dict,
    ):
        """SCH-A claim/lease（短事务，Conversation-first）。"""
        async with self.session_factory() as session, session.begin():
            return await ConversationPurgeScheduler(session).claim(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                retention_policy_snapshot=retention_policy_snapshot,
            )

    async def rebuild(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        retention_policy_snapshot: dict,
    ):
        """SCH-C G1/G2 drift → quiesce → rebuild/seeding（单事务原子）。"""
        async with self.session_factory() as session, session.begin():
            return await PurgeRebuildService(session).rebuild(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                retention_policy_snapshot=retention_policy_snapshot,
            )


def _require_joint_wiring(
    *,
    owner_entries: Mapping[str, OwnerEntryPort],
    settlement: object,
    rebuild: object,
    claim: object,
) -> None:
    """S5-SCH-3 组合根门禁：B/C/D 全部元素 + settlement/rebuild/claim 依赖齐备。

    任一缺失 → ``CompositionNotReadyError`` fail closed；coordinator 经
    ``coordinator_scan_providers`` 随 orchestrator 接线（缺 coordinator →
    orchestrator 无扫描提供者，聚合路径 fail closed）。
    """
    missing_owners = set(_ALL_OWNER_KEYS) - set(owner_entries)
    if missing_owners:
        raise CompositionNotReadyError(
            f"owner entries missing: {sorted(missing_owners)}; SCH-B partial wiring"
        )
    if settlement is None:
        raise CompositionNotReadyError(
            "concrete SettlementPort (SCH-D) missing; fail closed"
        )
    if rebuild is None:
        raise CompositionNotReadyError(
            "PurgeRebuildService (SCH-C) missing; fail closed"
        )
    if claim is None:
        raise CompositionNotReadyError(
            "claim/lease scheduler (SCH-A) missing; fail closed"
        )


def build_scheduler_composition(
    *,
    session_factory: async_sessionmaker,
    owner_entries: Mapping[str, OwnerEntryPort] | None = None,
    settlement: SettlementPort | None = None,
    rebuild: type[PurgeRebuildService] = PurgeRebuildService,
    claim: type[ConversationPurgeScheduler] = ConversationPurgeScheduler,
    external_adapter: object = FailClosedAdapter(),
    runtime_adapter: object = FailClosedAdapter(),
) -> SchedulerComposition:
    """B/C/D 联合装配（S5-SCH-3 组合根启用门禁）。

    默认 owner_entries = 六 owner participant map（external/runtime 槽位 Fail
    Closed）；默认 settlement = concrete SettlementPort（FailClosedAdapter
    resolver）。任一 slice/依赖缺失 → ``CompositionNotReadyError``。
    """
    if owner_entries is None:
        owner_entries = build_owner_entries(
            external_adapter=external_adapter,
            runtime_adapter=runtime_adapter,
        )
    if settlement is None:
        settlement = build_settlement_port(adapter_resolver=None)
    _require_joint_wiring(
        owner_entries=owner_entries,
        settlement=settlement,
        rebuild=rebuild,
        claim=claim,
    )
    orchestrator = OwnerExecutionOrchestrator(
        session_factory,
        owner_entries=owner_entries,
        settlement_port=settlement,
        scan_providers=coordinator_scan_providers,
    )
    return SchedulerComposition(
        session_factory=session_factory,
        orchestrator=orchestrator,
        owner_entries=owner_entries,
        settlement=settlement,
    )


__all__ = [
    "CompositionNotReadyError",
    "FailClosedAdapter",
    "SchedulerComposition",
    "build_owner_entries",
    "build_scheduler_composition",
    "build_settlement_port",
    "coordinator_scan_providers",
]
