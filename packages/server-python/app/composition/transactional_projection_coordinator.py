"""R1-S5-A-4 transactional projection coordinator（I2 实现，契约已冻结）。

operation/Conversation 聚合投影的唯一写者。锁序（冻结，S1 拆分裁决）：
Conversation 行锁 FOR UPDATE → operation 行 FOR UPDATE → 全 owner checkpoint
FOR UPDATE（owner_key 字典序）→ 全 owner fence 只读（owner_key 字典序，不加
FOR UPDATE）→ 最终扫描 / registry / hold facts → calculator → CAS 写 operation
+ Conversation。不取 owner advisory lock、fence 不加行锁。

CAS 基线 = 锁内读到的当前 operation.revision/lease_epoch（不用外部传入的
expected 值）。聚合结果与存储投影元组一致时零写（不 bump revision）——零写
比较集 = 完整投影元组 (operation.state, failure_code, started_at, completed_at,
Conversation.purge_state, purged_at)。终态覆盖禁令强化为 CAS 层不变量：
cancelled/failed/completed 存储态一律不得被重开（failed/completed 仅允许
零写幂等返回）。

调用点（冻结，S5-A-5）：独立事务、participant 提交之后；由编排调用方在每次
participant 入口返回后触发。S5 scheduler 仅增加定时/claim 全量重算与单 owner
重试，不改此触发点。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_registry import registry_digest, snapshot_digest
from app.composition.predecessor_lineage import (
    OwnerSnapshotEntry,
    PredecessorOwnerFact,
    compute_lineage,
)
from app.composition.projection_calculator import (
    CheckpointFact,
    FenceFact,
    LineageFact,
    OwnerScanFact,
    ProjectionInput,
    ProjectionResult,
    RegistryOwnerFact,
    calculate_projection,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ErasureFenceModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)

# purge_state 聚合投影值域（coordinator 写）；not_scheduled/scheduled 归
# delete/restore 生命周期写者（S5-A-1），coordinator 不触碰。
_COORDINATOR_PURGE_STATES = frozenset(
    {"running", "blocked", "failed", "completed"}
)


class ScanResultLike(Protocol):
    """scan 提供者返回形状（WorkspaceBodyScan / ExecutionBodyScan /
    TransportBodyScan 均满足——``total`` 为只读 property）。"""

    @property
    def total(self) -> int: ...


# 三份 scan 实现均 keyword-only 签名；``Callable[..., Awaitable[...]]`` 只约束
# 返回可等待性与结果形状，不约束参数形状（避免 mypy 对 bound async method 与
# callable Protocol 的匹配失败）。
ScanProvider = Callable[..., Awaitable[ScanResultLike]]


# ---------------------------------------------------------------------------
# 默认 scan 提供者装配（六 owner 复用 participant 的冻结扫描谓词，单一事实源）
# ---------------------------------------------------------------------------


class _ScanOnlyExternalAdapter:
    """scan-only external adapter 桩（满足 ExternalObjectAdapter Protocol）。

    仅用于装配 ExternalPayloadErasureParticipant 的 scan_transport_body——scan
    是纯 DB 谓词、绝不调用 adapter；任何误调用 loud fail。
    """

    adapter_key = "scan-only-stub"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    async def delete_object(self, *, ref_scheme, ref_value, idempotency_key):
        raise NotImplementedError("scan-only stub: delete_object must not be called")

    async def receipt_lookup(self, *, idempotency_key):
        raise NotImplementedError("scan-only stub: receipt_lookup must not be called")


class _ScanOnlyRuntimeAdapter:
    """scan-only runtime adapter 桩（满足 RuntimeSessionDestroyAdapter Protocol）。"""

    adapter_key = "scan-only-stub"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    async def destroy_session(self, *, runtime_session_ref, idempotency_key):
        raise NotImplementedError("scan-only stub: destroy_session must not be called")

    async def receipt_lookup(self, *, idempotency_key):
        raise NotImplementedError("scan-only stub: receipt_lookup must not be called")


def build_scan_providers(session: AsyncSession) -> dict[str, ScanProvider]:
    """六 owner 默认 scan 装配——复用 participant 冻结扫描谓词，不复制第二份。

    - workspace/execution core：各自 participant.scan_*（S2-D/S3-D 冻结谓词）
    - transport 两 owner：各自 TransportErasureParticipant 子类 scan（S4-D-A 冻结）
    - external/runtime：scan-only adapter 桩装配 participant（scan 纯 DB 谓词，
      不触 adapter；谓词与 S4-E-B2/S4-E-C 冻结实现同源）
    """
    from app.composition.external_ref_erasure_participant import (
        ExternalPayloadErasureParticipant,
    )
    from app.composition.runtime_erasure_participant import (
        RuntimeErasureParticipant,
    )
    from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (  # noqa: E501
        ExecutionErasureParticipant,
    )
    from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (  # noqa: E501
        ExecutionTransportErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (  # noqa: E501
        WorkspaceErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (  # noqa: E501
        WorkspaceTransportErasureParticipant,
    )

    workspace = WorkspaceErasureParticipant(session)
    execution = ExecutionErasureParticipant(session)
    ws_transport = WorkspaceTransportErasureParticipant(session)
    ex_transport = ExecutionTransportErasureParticipant(session)
    external = ExternalPayloadErasureParticipant(session, _ScanOnlyExternalAdapter())
    runtime = RuntimeErasureParticipant(session, _ScanOnlyRuntimeAdapter())
    return {
        "workspace.core.v1": workspace.scan_body,
        "execution.core.v1": execution.scan_execution_body,
        "workspace.transport.v1": ws_transport.scan_transport_body,
        "execution.transport.v1": ex_transport.scan_transport_body,
        "external.payload.v1": external.scan_transport_body,
        "runtime.private.v1": runtime.scan_transport_body,
    }


# ---------------------------------------------------------------------------
# coordinator
# ---------------------------------------------------------------------------


class TransactionalProjectionCoordinator:
    """transactional projection coordinator：facts 采集 → calculator → CAS 落库。

    I2 边界：lineage 派生为「无 predecessor → 全 owner
    not_applicable/native_pending」（rebuild/seeding 未实现，不存在继承义务）；
    snapshot 外 owner 行由 calculator G4 直接裁决。完整 predecessor lineage
    派生随 scheduler slice 扩展（权威公式 R1-S5-B S5-B-3 阶段 2）。
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        scan_providers: Mapping[str, ScanProvider],
    ) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)
        self._scan_providers = scan_providers

    async def aggregate_projection(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        now: datetime | None = None,
    ) -> ProjectionResult | None:
        """聚合一次 operation 投影并 CAS 落库。

        返回 None = 零写（计算投影与存储投影元组完全一致，未 bump revision）。
        cancelled 存储态 fail closed；failed/completed 存储态仅允许零写幂等
        返回，任何差异 fail closed（终态覆盖禁令，CAS 层不变量）。

        ``now`` 仅测试注入；生产为 Conversation 锁后 DB clock_timestamp()
        （不落应用时钟，与 participant「Conversation 锁后采样」惯例一致——
        三面 P2-1：锁前采样会使 completed_at/purged_at 早于最后 owner checkpoint
        的 updated_at，审计顺序反转）。
        """
        # 锁序第一步：Conversation 行锁（必取——coordinator 写 purge_state/
        # purged_at 须与 delete/restore/participant 串行；否则 operation→
        # Conversation 逆序与 participant 的 Conversation→operation 构成 AB-BA）。
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
            raise ValueError(
                f"conversation {conversation_id} not found for projection"
            )
        effective_now = now or await self._database_now()

        # 锁序第二步：operation 行 FOR UPDATE。三键限定 tenant+id+conversation_id
        # （纠偏 P1-1）：跨 Conversation 的 operation 查询必须 fail closed 且
        # **不等待**目标 operation 行锁（裸 tenant+id 查询会先阻塞在被持行锁上，
        # 再后验 conversation_id 失败——有界 fail-closed 要求查询谓词内限定 scope，
        # missing-or-scope-mismatch 统一报 not found，无外租户/外 Conversation
        # 信息泄露）。
        operation = (
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
        if operation is None:
            raise ValueError(
                f"purge operation {purge_operation_id} not found for projection"
            )
        if operation.conversation_id != conversation_id:
            raise ValueError(
                f"operation conversation_id {operation.conversation_id} != "
                f"{conversation_id}; cross-conversation projection rejected"
            )
        # I2 门禁增补（S5-A-4，回填自 S5-B-8 第 8 项「含 …/coordinator CAS」）：
        # operation 必须是 Conversation 当前 purge 周期的 operation——restore/
        # 再次 delete 已推进 purge_revision 后，旧 operation 的 facts 聚合结果
        # 不得写回当前 Conversation（跨 purge 实例投影污染；participant 侧同
        # 门禁已拒绝旧 op 的一切写，coordinator 是旧 op 唯一残余写通道）。
        if operation.purge_revision != conversation.purge_revision:
            raise ValueError(
                f"operation purge_revision {operation.purge_revision} != "
                f"conversation {conversation.purge_revision}; stale operation "
                "revision rejected (I2 gate)"
            )

        # 锁序第三/四步：全 owner checkpoint FOR UPDATE（owner_key 排序）→
        # 全 owner fence 只读（owner_key 排序，不加 FOR UPDATE）。Conversation
        # 首锁 = 本 coordination 域全局互斥（S1 不变量），fence 写全部发生在
        # participant 取 operation 行锁之后，coordinator 持 operation 行锁期间
        # fence 读集一致。
        checkpoint_rows = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                    )
                    .order_by(PurgeOwnerCheckpointModel.owner_key)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        fence_rows = (
            (
                await self._session.execute(
                    select(ErasureFenceModel)
                    .where(
                        ErasureFenceModel.tenant_id == tenant_id,
                        ErasureFenceModel.conversation_id == conversation_id,
                    )
                    .order_by(ErasureFenceModel.owner_key)
                )
            )
            .scalars()
            .all()
        )
        # 注（三面 P3-3）：fence 读取不按 purge_revision 过滤——多 cycle 残留 fence
        # 全量进入 calculator，五方验证按 fence.purge_revision 双分支（native 等值 /
        # inherited 例外 / > 矛盾）裁决。I2 无 rebuild，单 cycle 下等价；scheduler
        # slice 引入多 cycle 后由五方与 G4 兜底。

        snapshot = tuple(
            RegistryOwnerFact(
                owner_key=str(entry["owner_key"]),
                owner_version=int(entry["owner_version"]),
                capability_digest=str(entry["capability_digest"]),
            )
            for entry in operation.registry_snapshot
        )
        snapshot_owners = [entry.owner_key for entry in snapshot]

        # snapshot↔digest 内部自洽（与 create_owner_checkpoint 同源校验）：
        # 持久化 snapshot 被篡改而 digest 未同步 → fail closed，不在错误 owner
        # 全集上聚合。
        if snapshot_digest(list(operation.registry_snapshot)) != operation.registry_digest:
            raise ValueError(
                f"purge operation {purge_operation_id} registry snapshot/digest "
                "mismatch; tampered snapshot, fail closed"
            )

        # G1：operation.registry_digest 与已安装 registry 一致。
        registry_matches = operation.registry_digest == registry_digest()
        # G2：hold_revision_snapshot < Conversation 当前 hold_revision。
        # hold_revision 单调无回退写者（I1），`>` 为脏数据形态——契约仅冻结
        # `<` 漂移判定；`>` 按无漂移处理（G1/snapshot 自洽已兜底篡改形态，
        # 三面 P3-2 记录）。
        hold_drift = operation.hold_revision_snapshot < conversation.hold_revision
        # G3：live active hold 查询（I1 落地后无 TOCTOU 语义由 I2 门禁承接）。
        active_hold = await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

        # 最终扫描：per-owner，逐 owner 可归属（S5-A-2 输入契约）。六次独立
        # SELECT 在 READ COMMITTED 下各取新快照，跨 owner 撕裂窗口未定义——
        # conversation 已 deleted 时正文写者被应用层阻断，且正确性不依赖投影
        # 新鲜度（三面 P2-2 记录，后续 slice 可单语句收口）。
        scans: list[OwnerScanFact] = []
        for owner_key in snapshot_owners:
            provider = self._scan_providers.get(owner_key)
            if provider is None:
                raise ValueError(
                    f"no scan provider for snapshot owner {owner_key!r}; "
                    "coordinator wiring incomplete, fail closed"
                )
            scan_result = await provider(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            scans.append(OwnerScanFact(owner_key=owner_key, total=scan_result.total))

        # lineage（S5-B-3 阶段 2）：真实 predecessor 定位 + lineage 派生——
        # 替换 I2 的「无 predecessor → 全 not_applicable/native_pending」临时
        # 路径。predecessor/fence 在 Conversation 首锁窗口内只读（S5-B-3 阶段 2
        # 读集一致性）。
        lineage_facts = await self._assemble_lineage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            operation=operation,
            fence_rows=fence_rows,
        )

        result = calculate_projection(
            ProjectionInput(
                snapshot=snapshot,
                registry_digest_matches=registry_matches,
                hold_drift=hold_drift,
                active_legal_hold=active_hold,
                operation_purge_revision=operation.purge_revision,
                checkpoints=tuple(
                    CheckpointFact(
                        owner_key=row.owner_key,
                        state=row.state,
                        reason_code=row.reason_code,
                        attempt=row.attempt,
                        owner_version=row.owner_version,
                        capability_digest=row.capability_digest,
                        ack_digest=row.ack_digest,
                        checkpoint_digest=row.checkpoint_digest,
                    )
                    for row in checkpoint_rows
                ),
                fences=tuple(
                    FenceFact(
                        owner_key=row.owner_key,
                        state=row.state,
                        owner_version=row.owner_version,
                        purge_revision=row.purge_revision,
                        ack_digest=row.ack_digest,
                        ingress_digest=row.ingress_digest,
                        ingress_checkpoint=row.ingress_checkpoint,
                    )
                    for row in fence_rows
                ),
                lineage=lineage_facts,
                scans=tuple(scans),
            )
        )

        # --- CAS 落库（锁内当前值基线，不用外部 expected 值）---
        return await self._apply_projection(
            operation=operation,
            conversation=conversation,
            result=result,
            now=effective_now,
        )

    async def _assemble_lineage(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        operation: PurgeOperationModel,
        fence_rows: Sequence[ErasureFenceModel],
    ) -> tuple[LineageFact, ...]:
        """S5-B-3 阶段 2：定位 immediate predecessor 并派生 per-owner lineage。

        predecessor = 同一 (tenant, conversation) 下 purge_revision = MAX(< 当前)
        且 state=blocked + failure_code ∈ G1/G2 的行；无 predecessor 或非
        G1/G2-blocked → 全 not_applicable/native_pending（原生路径）。
        """
        predecessor = (
            await self._session.execute(
                select(PurgeOperationModel)
                .where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.conversation_id == conversation_id,
                    PurgeOperationModel.purge_revision < operation.purge_revision,
                )
                .order_by(PurgeOperationModel.purge_revision.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        snapshot = self._snapshot_entries(operation.registry_snapshot)
        if (
            predecessor is None
            or predecessor.state != "blocked"
            or predecessor.failure_code
            not in ("blocked_registry_changed", "blocked_hold_revision_changed")
        ):
            return tuple(
                LineageFact(
                    owner_key=e.owner_key,
                    lineage_status="not_applicable",
                    expected_obligation_kind="native_pending",
                )
                for e in snapshot
            )

        predecessor_checkpoints = (
            await self._session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                    PurgeOwnerCheckpointModel.purge_operation_id == predecessor.id,
                )
            )
        ).scalars().all()
        cp_by_owner = {row.owner_key: row for row in predecessor_checkpoints}
        fence_by_owner = {row.owner_key: row for row in fence_rows}

        def _fact(key: str) -> PredecessorOwnerFact:
            cp = cp_by_owner.get(key)
            f = fence_by_owner.get(key)
            return PredecessorOwnerFact(
                checkpoint_state=cp.state if cp else None,
                checkpoint_reason=cp.reason_code if cp else None,
                checkpoint_owner_version=cp.owner_version if cp else None,
                checkpoint_capability_digest=cp.capability_digest if cp else None,
                checkpoint_ack_digest=cp.ack_digest if cp else None,
                fence_state=f.state if f else None,
                fence_owner_version=f.owner_version if f else None,
                fence_purge_revision=f.purge_revision if f else None,
                fence_ack_digest=f.ack_digest if f else None,
            )

        facts = {key: _fact(key) for key in set(cp_by_owner) | set(fence_by_owner)}
        lineage = compute_lineage(
            snapshot=snapshot,
            predecessor_snapshot=self._snapshot_entries(predecessor.registry_snapshot),
            predecessor_facts=facts,
            current_revision=operation.purge_revision,
            historical_fences=frozenset(fence_by_owner),
        )
        return tuple(lineage[e.owner_key] for e in snapshot)

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

    async def _database_now(self) -> datetime:
        from sqlalchemy import func

        value = await self._session.scalar(select(func.clock_timestamp()))
        assert value is not None, "clock_timestamp() must return a value"
        return value

    async def _apply_projection(
        self,
        *,
        operation: PurgeOperationModel,
        conversation: ConversationModel,
        result: ProjectionResult,
        now: datetime,
    ) -> ProjectionResult | None:
        """CAS 写 operation + Conversation 投影；元组一致时零写返回 None。

        终态覆盖禁令（CAS 层不变量）：cancelled 一律 fail closed；
        failed/completed 只允许零写幂等返回，任何差异 fail closed。
        """
        # 目标投影元组（零写比较集 = 完整投影元组）。
        target_state = result.state
        target_failure_code = result.failure_code
        if result.state == "running" and operation.started_at is None:
            target_started_at: datetime | None = now
        else:
            target_started_at = operation.started_at
        # 纠偏 P1-2：终态时间归一化——completed 取既有值或 DB now；**非 completed
        # 一律清 NULL**（旧投影污染预置的 completed_at/purged_at 不得残留，
        # 六元组随聚合归一）。
        if result.state == "completed":
            target_completed_at: datetime | None = operation.completed_at or now
        else:
            target_completed_at = None
        # purge_state：聚合投影值域由 coordinator 写；scheduled 保持生命周期
        # 写者既有值（not_scheduled/scheduled 归 delete/restore，S5-A-1）。
        if result.purge_state in _COORDINATOR_PURGE_STATES:
            target_purge_state = result.purge_state
        else:
            target_purge_state = conversation.purge_state
        if result.state == "completed":
            target_purged_at: datetime | None = conversation.purged_at or now
        else:
            target_purged_at = None

        stored = (
            operation.state,
            operation.failure_code,
            operation.started_at,
            operation.completed_at,
            conversation.purge_state,
            conversation.purged_at,
        )
        target = (
            target_state,
            target_failure_code,
            target_started_at,
            target_completed_at,
            target_purge_state,
            target_purged_at,
        )
        if stored == target:
            # 零写：不 bump revision，保护 Tx1 _mark_operation_running/
            # _record_blocked revision CAS 与编排方逐 entry 记账（S5-A-4）。
            return None

        # 终态覆盖禁令：终态存储值不得被任何非零写覆盖。
        if operation.state == "cancelled":
            raise ValueError(
                f"purge operation {operation.id} is cancelled (restore-owned "
                "terminal); coordinator must not overwrite"
            )
        if operation.state in ("failed", "completed"):
            raise ValueError(
                f"purge operation {operation.id} is terminal "
                f"({operation.state!r}); coordinator must not reopen to "
                f"{result.state!r}"
            )

        operation.state = target_state
        operation.failure_code = target_failure_code
        operation.started_at = target_started_at
        operation.completed_at = target_completed_at
        operation.revision = operation.revision + 1
        operation.updated_at = now
        conversation.purge_state = target_purge_state
        conversation.purged_at = target_purged_at
        conversation.updated_at = now
        await self._session.flush()
        return result


__all__ = [
    "ScanProvider",
    "TransactionalProjectionCoordinator",
    "build_scan_providers",
]
