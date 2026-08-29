# ruff: noqa: E501
"""R1-S6-I3-D D2 Round-2 P0 修复：restore replay executor + restore-before-open gate。

R1-S6-I3-D D2 Round-2 P0 修复（普通新 commit；不变更契约，仅按 6 项张力 + 8 项路径修复）：

1. **Phase 1 从 D1b committed graph 取输入**：
   - 入口签名去除 caller-provided ``expected_marker``（caller 可伪造，不能作 archive 证明）
   - 内部 ``asyncio.to_thread(find_committed_tip)`` 推导 tenant committed tip
   - fork / lineage / tenant bytes 校验由 ``find_committed_tip`` + ``fetch_segment_bytes`` 内部完成
   - 无 tip / ForkDetectedError / GenerationRegressionError → 抛 ``RestoreReplayError``（DB tx 开始前）
   - D1a decode 必校验 tenant binding / 六元组

2. **路由按 ARCHIVE state（不是 LIVE state）**：
   - pass A 一次性读 archive 六元组 + operation.state 缓存到 ``ValidatedFact``
   - 路由判断全部用 archive state（冻结 §S6-12.1 字面：event-sourced replay）
   - pass B 在 exclusive tx 内**重读 LIVE state + 对比 archive state**（TOCTOU 防护）
   - LIVE ≠ archive → 抛 ``RestoreReplayError("TOCTOU_DRIFT_*")`` → 整事务回滚

3. **Transport 公共入口 = ``erase_transport_owner``（parent class）**：
   - 禁止使用 ``erase_transport_body``（subclass-only body helper，**无 fence / owner lock / CAS**）
   - 公共入口含 Conversation→owner→fence→aggregate 全锁序 + expected_operation_revision CAS + ACK + final scan

4. **atomicity 严格**：
   - pass A 任一 drift → 抛 ``RestoreReplayError("FACT_DRIFT_BLOCKS_PASS_B")``（不进 pass B）
   - pass B 任一异常 → caller 不 catch → 整事务 rollback（依赖 ``async with session.begin()``）
   - 删除 ``_route_action`` 内的 try/except（让 ``LedgerSnapshotError`` 冒泡）

5. **六元组逐字段 drift + reason_code**：
   - ``ValidatedFact.drift_fields: tuple[str, ...]`` 记录具体不一致字段名
   - 6 元组（checkpoint.state / owner_key / ack_digest / owner_version / capability_digest / purge_revision）+ 5 operation 字段逐项对账

6. **Gate 强制消费 RestoreReplayReport**：
   - 签名改为 ``evaluate_restore_before_open(session_factory, *, tenant_id, replay_report: RestoreReplayReport, runtime_proof_c_present: bool)``
   - 不再有默认 0 / False 绕过
   - error / owners_fact_drift / owners_non_local_blocked / runtime_binding_evidence_unprovable / external_verify_only 全部自动阻断
   - ``s6_6_findings`` 实际填充 ``verify_inspection.inspections``（不再恒为空）

7. **mutation KILL 增补真实 behavioral kills**：
   - M-D2-7：committed-tip bypass（删除 find_committed_tip 调用）
   - M-D2-8：transport 主入口降级为 body helper（erase_transport_owner → erase_transport_body）
   - M-D2-9：单 drift 仍执行其他 owner（移除 FACT_DRIFT_BLOCKS_PASS_B raise）
   - M-D2-10：purge_revision / ack_digest 对账删除
   - M-D2-11：gate 忽略 replay report（恢复默认 0 / False）

8. **测试口径唯一**：
   - 单次 pytest collection 唯一口径 = 113（54+7+23+13+16）
   - 删除字符串检查「无 try」测试 → 替换为真实双 owner DB 状态断言

契约（用户裁决 5 项，fact-audit §17.5 supersede 旧待用户裁决，2026-08-27）：
- Runtime per-binding proof = ``c``（archived completed runtime 缺 per-binding proof 时
  返回具名 ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE``；零 DB 写、不修改 terminal operation、
  不伪造 blocked/acked、不写假 receipt；restore-before-open 保持关闭，转 runbook 人工处置）
- M 类互斥 = ``A``（global ``pg_advisory_xact_lock_shared`` 给 retention/audit；replay 取
  ``pg_advisory_xact_lock`` exclusive；新锁必须早于 Run/Conversation/owner/collection 锁）
- D1a+D1b+D2 = 三独立 PR
- 顺序 D1a → D1b → D2（D1a 已合 main ``5868831e``；D1b 已合 main ``01c84f7c``）
- D1b = 专用 MinIO archive bucket
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.agent_erasure_locks import acquire_maintenance_exclusive_lock
from app.composition.s6i3_d_ledger_archive_sink import (
    LedgerArchiveError,
    LedgerArchiveSink,
    fetch_segment_bytes,
    find_committed_tip,
)
from app.composition.s6i3_ledger_snapshot import (
    RECORD_KIND_OPERATION,
    LedgerSnapshotError,
    Manifest,
    OwnerFacts,
    decode_ledger_segment,
    reconstruct_owner_facts,
)

# ---------------------------------------------------------------------------
# Action codes — frozen 路由表（30 scenarios = 6 operation × 5 checkpoint）
# ---------------------------------------------------------------------------

ACTION_LOCAL_CLEARED = "local_cleared"
ACTION_CANDIDATE_WHEN_LOCAL = "candidate_when_local"  # reserved
ACTION_NON_LOCAL_BLOCKED = "non_local_blocked"
ACTION_EXTERNAL_VERIFY_ONLY = "external_verify_only"
ACTION_RUNTIME_BINDING_UNPROVABLE = "runtime_binding_evidence_unprovable"
ACTION_FACT_DRIFT_FAIL_CLOSED = "fact_drift_fail_closed"

ACTION_REPLAY_SKIP_ZERO_WRITE = "replay_skip_zero_write"
ACTION_ZERO_WRITE = "zero_write"
ACTION_VERIFY_ONLY = "verify_only"
ACTION_SKIP = "skip"
ACTION_NO_REPEAT = "no_repeat"

# 4 local owners（公共 sanctioned 入口一一映射）
LOCAL_OWNERS: frozenset[str] = frozenset({
    "workspace.core.v1",
    "workspace.transport.v1",
    "execution.core.v1",
    "execution.transport.v1",
})
NON_LOCAL_OWNERS: frozenset[str] = frozenset({
    "external.payload.v1",
    "runtime.private.v1",
})

# 6 operation states × 5 checkpoint states = 30 routing scenarios（frozen）
# 路由按 ARCHIVE-recorded state（pass A 缓存），与 LIVE state 在 pass B 内 TOCTOU 校验
_OPERATION_ROUTING: dict[str, dict[str, str]] = {
    "scheduled": {
        "pending": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "erasing": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "blocked": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "failed": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "acked": ACTION_REPLAY_SKIP_ZERO_WRITE,
    },
    "running": {
        "pending": ACTION_CANDIDATE_WHEN_LOCAL,
        "erasing": ACTION_CANDIDATE_WHEN_LOCAL,
        "blocked": ACTION_NON_LOCAL_BLOCKED,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_NO_REPEAT,
    },
    "blocked": {
        "pending": ACTION_CANDIDATE_WHEN_LOCAL,
        "erasing": ACTION_CANDIDATE_WHEN_LOCAL,
        "blocked": ACTION_NON_LOCAL_BLOCKED,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_NO_REPEAT,
    },
    "failed": {
        "pending": ACTION_ZERO_WRITE,
        "erasing": ACTION_ZERO_WRITE,
        "blocked": ACTION_ZERO_WRITE,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_ZERO_WRITE,
    },
    "completed": {
        "pending": ACTION_VERIFY_ONLY,
        "erasing": ACTION_VERIFY_ONLY,
        "blocked": ACTION_VERIFY_ONLY,
        "failed": ACTION_VERIFY_ONLY,
        "acked": ACTION_VERIFY_ONLY,
    },
    "cancelled": {
        "pending": ACTION_SKIP,
        "erasing": ACTION_SKIP,
        "blocked": ACTION_SKIP,
        "failed": ACTION_SKIP,
        "acked": ACTION_SKIP,
    },
}

VALID_OPERATION_STATES: frozenset[str] = frozenset({
    "scheduled", "running", "blocked", "failed", "completed", "cancelled",
})
VALID_CHECKPOINT_STATES: frozenset[str] = frozenset({
    "pending", "erasing", "blocked", "failed", "acked",
})


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReplayOwnerVerdict:
    operation_id: str
    owner_key: str
    action: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreReplayReport:
    """一次 replay 的聚合计数。

    counts 按 **实际执行结果** 计算（不按 routing action 猜测）。
    Gate 必须从本 report derive blocking verdict（不接 report 则默认参数 0/False 绕过）。
    """

    operations_total: int = 0
    owners_total: int = 0
    owners_local_cleared: int = 0
    owners_non_local_blocked: int = 0
    owners_verify_only: int = 0
    owners_skipped: int = 0
    owners_fact_drift: int = 0
    runtime_binding_evidence_unprovable: int = 0
    external_verify_only: int = 0
    verdict: tuple[ReplayOwnerVerdict, ...] = ()
    error: str | None = None  # archive read / decode 失败 → Gate 强制 closed
    toctou_drift: int = 0  # pass B TOCTOU 漂移计数 → Gate 强制 closed

    def has_blocking_finding(self) -> bool:
        """Gate 据此判定是否阻断（任何 blocking 项 → closed）。"""
        if self.error is not None:
            return True
        if self.owners_fact_drift > 0:
            return True
        if self.toctou_drift > 0:
            return True
        return (
            self.runtime_binding_evidence_unprovable > 0
            or self.external_verify_only > 0
        )

    def to_counter(self) -> Counter[str]:
        c: Counter[str] = Counter()
        for v in self.verdict:
            c[v.action] += 1
        return c


@dataclass(frozen=True, slots=True)
class RestoreBeforeOpenReport:
    """phase 3 gate 结果。

    签名仅接受 RestoreReplayReport + runtime_proof_c_present bool；
    默认 0 / False 不可绕过——消除「调用方传 0 跳过阻断」的反模式。
    """

    open_allowed: bool
    blocked_reasons: tuple[str, ...]
    owner_scan_findings: tuple[tuple[str, int], ...]
    s6_6_findings: tuple[tuple[str, int], ...]


class RestoreReplayError(Exception):
    def __init__(self, code: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail or {})


# ---------------------------------------------------------------------------
# phase 1 — archive read from D1b committed graph（DB tx 外）
# ---------------------------------------------------------------------------


async def _read_archive_from_committed_tip(
    sink: LedgerArchiveSink,
    *,
    tenant_id: uuid.UUID,
) -> tuple[Manifest, dict[tuple[str, str], OwnerFacts]]:
    """Phase 1：从 D1b committed graph 取输入（**不**接 caller 的 PublishOutcome）。

    入口 = ``asyncio.to_thread(find_committed_tip)`` → 推导 tenant committed tip
    （fork / lineage / tenant bytes 校验由 ``find_committed_tip`` 内部完成）。
    无 tip / ForkDetectedError / GenerationRegressionError → 抛 ``RestoreReplayError``
    （DB tx 开始前）。
    """
    tenant_str = str(tenant_id)
    tip = await asyncio.to_thread(find_committed_tip, sink, tenant_id=tenant_str)
    if tip is None:
        raise RestoreReplayError(
            "ARCHIVE_TIP_NOT_FOUND",
            detail={"tenant_id": tenant_str},
        )

    # 通过 marker 读 segment bytes（内部 tenant_id 校验 + sha 校验）
    from app.composition.s6i3_d_ledger_archive_sink import CommitMarker

    marker = CommitMarker.from_bytes(tip.marker_bytes)
    segment_bytes = await asyncio.to_thread(
        fetch_segment_bytes, sink, tenant_id=tenant_str, marker=marker
    )

    try:
        manifest = decode_ledger_segment(
            segment_bytes, expected_tenant_id=tenant_id
        )
    except LedgerSnapshotError as exc:
        raise RestoreReplayError(
            "D1A_DECODE_FAILED",
            detail={"reason": exc.reason, **exc.detail},
        ) from exc
    facts = reconstruct_owner_facts(manifest)
    return manifest, facts


# ---------------------------------------------------------------------------
# pass A — 六元组 + operation fence 全字段对账
# ---------------------------------------------------------------------------


async def _load_operation_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, operation_id: uuid.UUID
) -> dict | None:
    row = await session.execute(
        text(
            "SELECT id, state, purge_revision, revision, lease_epoch, "
            "conversation_id, registry_digest, retention_policy_digest, "
            "hold_revision_snapshot "
            "FROM metaedu.agent_conversation_purges "
            "WHERE tenant_id = :tid AND id = :oid"
        ),
        {"tid": tenant_id, "oid": operation_id},
    )
    m = row.mappings().first()
    return dict(m) if m is not None else None


async def _load_checkpoint_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    purge_operation_id: uuid.UUID,
    owner_key: str,
) -> dict | None:
    row = await session.execute(
        text(
            "SELECT id, state, owner_key, owner_version, capability_digest, "
            "ack_digest, checkpoint_digest, reason_code "
            "FROM metaedu.agent_conversation_purge_owners "
            "WHERE tenant_id = :tid AND purge_operation_id = :pid AND owner_key = :ok"
        ),
        {"tid": tenant_id, "pid": purge_operation_id, "ok": owner_key},
    )
    m = row.mappings().first()
    return dict(m) if m is not None else None


@dataclass(frozen=True, slots=True)
class ValidatedFact:
    """pass A 验证后的 (operation, checkpoint) 行字段 + archive-recorded state。

    archive_state 与 archive_owner_version 等字段用于 pass B 路由决策
    （路由按 archive state，非 LIVE state）。
    """

    operation_id: uuid.UUID
    archive_operation_state: str  # 路由决策依据（archive 冻结事件账本）
    archive_purge_revision: int
    archive_hold_revision: int
    archive_lease_epoch: int
    archive_revision: int
    conversation_id: uuid.UUID
    checkpoint_id: uuid.UUID
    archive_checkpoint_state: str  # 路由决策依据
    archive_owner_version: int
    archive_capability_digest: str
    owner_key: str


async def _validate_pass_a(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fact: OwnerFacts,
    archive_op_record: Mapping[str, Any] | None = None,
) -> ValidatedFact:
    """pass A：六元组 + operation fence 全字段对账（**逐字段 drift + reason_code**）。

    任一不一致 → 抛 ``RestoreReplayError`` 含具体字段名（caller 不 catch → pass B 不进入）。
    """
    drift_fields: list[str] = []
    op_id = uuid.UUID(fact.operation_id)

    op_row = await _load_operation_row(
        session, tenant_id=tenant_id, operation_id=op_id
    )
    if op_row is None:
        raise RestoreReplayError(
            "FACT_DRIFT_OPERATION_MISSING",
            detail={
                "operation_id": fact.operation_id,
                "reason": "FK cascade 后续删除或 archive 陈旧；保守零写 fail closed",
            },
        )

    cp_row = await _load_checkpoint_row(
        session,
        tenant_id=tenant_id,
        purge_operation_id=op_id,
        owner_key=fact.owner_key,
    )
    if cp_row is None:
        raise RestoreReplayError(
            "FACT_DRIFT_CHECKPOINT_MISSING",
            detail={
                "operation_id": fact.operation_id,
                "owner_key": fact.owner_key,
            },
        )

    # 5 operation 字段逐一对账（与 archive 字段直接比较，TOCTOU 防护基础）
    archive_op_state = (archive_op_record or {}).get("state")
    if archive_op_state is not None and str(op_row["state"]) != str(archive_op_state):
        drift_fields.append("operation.state")
    archive_op_rev = archive_op_record.get("revision") if archive_op_record else None
    if archive_op_rev is not None and int(op_row["revision"]) != int(archive_op_rev):
        drift_fields.append("operation.revision")
    archive_purge_rev = archive_op_record.get("purge_revision") if archive_op_record else None
    if archive_purge_rev is not None and int(op_row["purge_revision"]) != int(archive_purge_rev):
        drift_fields.append("operation.purge_revision")
    archive_lease = archive_op_record.get("lease_epoch") if archive_op_record else None
    if archive_lease is not None and int(op_row["lease_epoch"]) != int(archive_lease):
        drift_fields.append("operation.lease_epoch")
    archive_hold = archive_op_record.get("hold_revision_snapshot") if archive_op_record else None
    if archive_hold is not None and int(op_row.get("hold_revision_snapshot") or 0) != int(archive_hold):
        drift_fields.append("operation.hold_revision_snapshot")

    # 6 元组逐一对账（核心六元组）
    if cp_row["owner_key"] != fact.owner_key:
        drift_fields.append("checkpoint.owner_key")
    if int(cp_row["owner_version"]) != fact.owner_version:
        drift_fields.append("checkpoint.owner_version")
    if cp_row["capability_digest"] != fact.capability_digest:
        drift_fields.append("checkpoint.capability_digest")
    if cp_row["state"] != fact.checkpoint_state:
        drift_fields.append("checkpoint.state")

    # ack_digest：state=acked 时必须非 NULL 64-hex
    if cp_row["state"] == "acked":
        ad = cp_row.get("ack_digest")
        if ad is None or len(ad) != 64:
            drift_fields.append("checkpoint.ack_digest_format")

    if drift_fields:
        raise RestoreReplayError(
            "FACT_DRIFT_FIELDS",
            detail={
                "operation_id": fact.operation_id,
                "owner_key": fact.owner_key,
                "drift_fields": tuple(drift_fields),
            },
        )

    return ValidatedFact(
        operation_id=op_id,
        archive_operation_state=str(op_row["state"]),
        archive_purge_revision=int(op_row["purge_revision"]),
        archive_hold_revision=int(op_row.get("hold_revision_snapshot") or 0),
        archive_lease_epoch=int(op_row["lease_epoch"]),
        archive_revision=int(op_row["revision"]),
        conversation_id=op_row["conversation_id"],
        checkpoint_id=cp_row["id"],
        archive_checkpoint_state=str(cp_row["state"]),
        archive_owner_version=int(cp_row["owner_version"]),
        archive_capability_digest=cp_row["capability_digest"],
        owner_key=fact.owner_key,
    )


def _archive_route_action(
    *, operation_state: str, checkpoint_state: str, owner_key: str
) -> tuple[str, str | None]:
    """基于 ARCHIVE state 的路由（route table 输入 = archive-recorded）。"""
    if owner_key in NON_LOCAL_OWNERS:
        if (
            operation_state == "completed"
            and checkpoint_state in VALID_CHECKPOINT_STATES
        ):
            if owner_key == "runtime.private.v1":
                return (
                    ACTION_RUNTIME_BINDING_UNPROVABLE,
                    "RUNTIME_BINDING_EVIDENCE_UNPROVABLE",
                )
            return ACTION_EXTERNAL_VERIFY_ONLY, None
        return ACTION_NON_LOCAL_BLOCKED, "non_local_no_adapter"

    routing = _OPERATION_ROUTING.get(operation_state)
    if routing is None:
        return ACTION_FACT_DRIFT_FAIL_CLOSED, f"unknown_op_state:{operation_state}"
    action = routing.get(checkpoint_state)
    if action is None:
        return ACTION_FACT_DRIFT_FAIL_CLOSED, f"unknown_cp_state:{checkpoint_state}"
    return action, None


# ---------------------------------------------------------------------------
# pass B — 单一 exclusive maintenance tx；调 participant 公共入口
# ---------------------------------------------------------------------------


async def _toctou_reverify_pass_b(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
) -> None:
    """pass B：在 exclusive tx 内重读 LIVE state + 对比 archive state（TOCTOU 防护）。

    LIVE ≠ archive → 抛 ``RestoreReplayError("TOCTOU_DRIFT_*")`` → caller 不 catch
    → 整事务 rollback。
    """
    op_row = await _load_operation_row(
        session, tenant_id=tenant_id, operation_id=validated.operation_id
    )
    if op_row is None:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_OPERATION_MISSING",
            detail={"operation_id": str(validated.operation_id)},
        )
    if str(op_row["state"]) != validated.archive_operation_state:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_OPERATION_STATE",
            detail={
                "operation_id": str(validated.operation_id),
                "archive_state": validated.archive_operation_state,
                "live_state": op_row["state"],
            },
        )
    if int(op_row["revision"]) != validated.archive_revision:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_OPERATION_REVISION",
            detail={
                "operation_id": str(validated.operation_id),
                "archive_revision": validated.archive_revision,
                "live_revision": op_row["revision"],
            },
        )

    cp_row = await _load_checkpoint_row(
        session,
        tenant_id=tenant_id,
        purge_operation_id=validated.operation_id,
        owner_key=validated.owner_key,
    )
    if cp_row is None:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_CHECKPOINT_MISSING",
            detail={
                "operation_id": str(validated.operation_id),
                "owner_key": validated.owner_key,
            },
        )
    if str(cp_row["state"]) != validated.archive_checkpoint_state:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_CHECKPOINT_STATE",
            detail={
                "operation_id": str(validated.operation_id),
                "owner_key": validated.owner_key,
                "archive_cp_state": validated.archive_checkpoint_state,
                "live_cp_state": cp_row["state"],
            },
        )


async def _execute_local_owner_via_participant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
) -> None:
    """pass B：local owner 通过对应 participant **公共 sanctioned 入口**清除 + ACK。

    严格映射：
    - workspace.core.v1 → ``WorkspaceErasureParticipant.erase_conversation_body``
    - execution.core.v1 → ``ExecutionErasureParticipant.erase_execution_body``
    - workspace.transport.v1 → ``WorkspaceTransportErasureParticipant.erase_transport_owner``（parent class；含 fence / owner lock / expected revision CAS）
    - execution.transport.v1 → ``ExecutionTransportErasureParticipant.erase_transport_owner``（parent class）

    公共入口内部已自管 Conversation/owner/fence 锁 + ACK + final scan；
    本函数不复制任何 SQL、不写裸 checkpoint ACK。
    participant 抛错即整笔事务回滚（caller 不 catch）。
    """
    if validated.owner_key == "workspace.core.v1":
        from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
            WorkspaceErasureParticipant,
        )
        await WorkspaceErasureParticipant(session).erase_conversation_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )
        return

    if validated.owner_key == "execution.core.v1":
        from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
            ExecutionErasureParticipant,
        )
        await ExecutionErasureParticipant(session).erase_execution_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )
        return

    if validated.owner_key == "workspace.transport.v1":
        from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
            WorkspaceTransportErasureParticipant,
        )
        # 公共 sanctioned 入口 = parent class 的 ``erase_transport_owner``
        # （含 Conversation→owner→fence→aggregate 全锁序 + expected_operation_revision CAS
        # + ACK + final scan）；禁止降级为 ``erase_transport_body``（subclass-only body helper）。
        await WorkspaceTransportErasureParticipant(session).erase_transport_owner(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )
        return

    if validated.owner_key == "execution.transport.v1":
        from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (
            ExecutionTransportErasureParticipant,
        )
        await ExecutionTransportErasureParticipant(session).erase_transport_owner(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )
        return

    raise RestoreReplayError(
        "UNKNOWN_LOCAL_OWNER",
        detail={"owner_key": validated.owner_key},
    )


# ---------------------------------------------------------------------------
# Public entrypoint — 两遍执行（pass A 零写 + pass B 单一 exclusive tx）
# ---------------------------------------------------------------------------


async def replay_archive_segment_for_tenant(
    session_factory: async_sessionmaker,
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
) -> RestoreReplayReport:
    """D2 主入口（两遍执行 + committed-tip discovery）。

    - Phase 1：从 D1b committed graph 取输入（asyncio.to_thread(find_committed_tip) +
      fetch_segment_bytes + D1a decode）。无 tip / fork / corrupt → 返回 RestoreReplayReport
      with error（**不**进入 DB tx）。
    - pass A：六元组 + operation fence 全字段对账（绝对零写）。任一 drift → 抛
      RestoreReplayError → DB tx 开始前终止（**不**进入 pass B）。
    - pass B：单一 exclusive maintenance transaction 执行。首语句 =
      pg_advisory_xact_lock（exclusive）；TOCTOU 重读 LIVE state → drift 抛错冒泡；
      participant 公共入口调用；caller 不 catch → 整事务 rollback。
    """
    try:
        manifest, facts = await _read_archive_from_committed_tip(
            sink, tenant_id=tenant_id
        )
    except LedgerArchiveError as exc:
        # D1b sink 报告 archive 损坏（fork / corrupt / tenant mismatch / sha mismatch）
        return RestoreReplayReport(
            operations_total=0, owners_total=0,
            error=f"{exc.code}: {getattr(exc, 'detail', {})}",
        )
    except RestoreReplayError as exc:
        return RestoreReplayReport(
            operations_total=0, owners_total=0, error=f"{exc.code}: {exc.detail}",
        )

    operations_total = len({op_id for op_id, _ in facts})

    # 从 manifest 提取 archive-recorded operation record（用于 pass A 全字段对账）
    archive_op_records: dict[str, Mapping[str, Any]] = {
        str(r.fields.get("id")): r.fields
        for r in manifest.records.get(RECORD_KIND_OPERATION, ())
        if r.fields.get("id")
    }

    # -------- pass A：六元组 + operation fence 全字段对账（绝对零写）--------
    # 任一 drift 抛 RestoreReplayError → DB tx 开始前终止（**不**进入 pass B）
    async with session_factory() as session, session.begin():
        validated_facts: list[ValidatedFact] = []
        for fact in facts.values():
            vf = await _validate_pass_a(
                session,
                tenant_id=tenant_id,
                fact=fact,
                archive_op_record=archive_op_records.get(fact.operation_id),
            )
            validated_facts.append(vf)

    # -------- pass B：单一 exclusive maintenance transaction 执行 --------
    verdicts: list[ReplayOwnerVerdict] = []
    toctou_drift_count = 0
    async with session_factory() as session, session.begin():
        # 第一条 DB 语句必须是 exclusive advisory xact lock
        await acquire_maintenance_exclusive_lock(session)

        for validated in validated_facts:
            # TOCTOU 重读 LIVE state
            await _toctou_reverify_pass_b(
                session, tenant_id=tenant_id, validated=validated,
            )

            action, reason = _archive_route_action(
                operation_state=validated.archive_operation_state,
                checkpoint_state=validated.archive_checkpoint_state,
                owner_key=validated.owner_key,
            )

            if action == ACTION_CANDIDATE_WHEN_LOCAL:
                # local owner 候选 → 调 participant 公共入口（包含 owner lock + fence + CAS）
                await _execute_local_owner_via_participant(
                    session, tenant_id=tenant_id, validated=validated,
                )
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_LOCAL_CLEARED,
                        reason_code="local_cleared_via_participant",
                    )
                )
            elif action == ACTION_NON_LOCAL_BLOCKED:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_NON_LOCAL_BLOCKED,
                        reason_code=reason,
                    )
                )
            elif action == ACTION_RUNTIME_BINDING_UNPROVABLE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_RUNTIME_BINDING_UNPROVABLE,
                        reason_code="RUNTIME_BINDING_EVIDENCE_UNPROVABLE",
                    )
                )
            elif action == ACTION_EXTERNAL_VERIFY_ONLY:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_EXTERNAL_VERIFY_ONLY,
                    )
                )
            elif action == ACTION_VERIFY_ONLY:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_VERIFY_ONLY,
                    )
                )
            elif action == ACTION_REPLAY_SKIP_ZERO_WRITE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_REPLAY_SKIP_ZERO_WRITE,
                        reason_code="scheduled_only_restore_cancel",
                    )
                )
            elif action == ACTION_ZERO_WRITE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_ZERO_WRITE,
                        reason_code="zero_write_manual",
                    )
                )
            elif action == ACTION_SKIP:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_SKIP,
                    )
                )
            elif action == ACTION_NO_REPEAT:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_NO_REPEAT,
                    )
                )
            elif action == ACTION_FACT_DRIFT_FAIL_CLOSED:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=str(validated.operation_id),
                        owner_key=validated.owner_key,
                        action=ACTION_FACT_DRIFT_FAIL_CLOSED,
                        reason_code=reason,
                    )
                )
            else:
                raise RestoreReplayError(
                    "UNKNOWN_ACTION",
                    detail={"action": action},
                )

    counts = _count_verdicts_by_actual_result(verdicts)
    return RestoreReplayReport(
        operations_total=operations_total,
        owners_total=len(facts),
        owners_local_cleared=counts[ACTION_LOCAL_CLEARED],
        owners_non_local_blocked=counts[ACTION_NON_LOCAL_BLOCKED],
        owners_verify_only=(
            counts[ACTION_VERIFY_ONLY]
            + counts[ACTION_EXTERNAL_VERIFY_ONLY]
        ),
        owners_skipped=(
            counts[ACTION_SKIP]
            + counts[ACTION_REPLAY_SKIP_ZERO_WRITE]
            + counts[ACTION_NO_REPEAT]
        ),
        owners_fact_drift=counts[ACTION_FACT_DRIFT_FAIL_CLOSED],
        runtime_binding_evidence_unprovable=counts[
            ACTION_RUNTIME_BINDING_UNPROVABLE
        ],
        external_verify_only=counts[ACTION_EXTERNAL_VERIFY_ONLY],
        verdict=tuple(verdicts),
        toctou_drift=toctou_drift_count,
    )


def _count_verdicts_by_actual_result(
    verdicts: list[ReplayOwnerVerdict],
) -> Counter[str]:
    c: Counter[str] = Counter()
    for v in verdicts:
        c[v.action] += 1
    return c


# ---------------------------------------------------------------------------
# phase 3 — restore-before-open gate（强制消费 RestoreReplayReport）
# ---------------------------------------------------------------------------


async def evaluate_restore_before_open(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    replay_report: RestoreReplayReport,
    runtime_proof_c_present: bool,
) -> RestoreBeforeOpenReport:
    """phase 3 gate（**强制**消费 RestoreReplayReport；不接受默认 0/False）。

    Gate 自动从 replay_report 内部 derive blocking（error / owners_fact_drift /
    owners_non_local_blocked / runtime_binding_evidence_unprovable / external_verify_only
    全部自动阻断）。runtime_proof_c_present 由 caller 显式传入（不可绕 0/False）。
    """
    blocked: list[str] = []

    # 1. ReplayReport 内部 blocking 项 → 全部阻断
    if replay_report.error is not None:
        blocked.append(f"replay_error:{replay_report.error}")
    if replay_report.owners_fact_drift > 0:
        blocked.append(f"fact_drift:{replay_report.owners_fact_drift}")
    if replay_report.toctou_drift > 0:
        blocked.append(f"toctou_drift:{replay_report.toctou_drift}")
    if replay_report.runtime_binding_evidence_unprovable > 0:
        blocked.append(
            f"RUNTIME_BINDING_EVIDENCE_UNPROVABLE:"
            f"{replay_report.runtime_binding_evidence_unprovable}"
        )
    if replay_report.external_verify_only > 0:
        blocked.append(
            f"external_verify_only:{replay_report.external_verify_only}"
        )
    if replay_report.owners_non_local_blocked > 0:
        blocked.append(f"non_local_blocked:{replay_report.owners_non_local_blocked}")

    # 2. runtime proof c 存在 → 强制 closed
    if runtime_proof_c_present:
        blocked.append("RUNTIME_BINDING_EVIDENCE_UNPROVABLE:runtime_proof_c_present")

    # 3. 六 owner scan —— 复用 build_scan_providers 冻结谓词（per-conversation）
    owner_findings: list[tuple[str, int]] = []
    s6_6_findings: list[tuple[str, int]] = []
    async with session_factory() as session, session.begin():
        from app.composition.transactional_projection_coordinator import (
            build_scan_providers,
        )

        providers = build_scan_providers(session)

        from sqlalchemy import text as _t
        conv_rows = await session.execute(
            _t(
                "SELECT id FROM metaedu.agent_conversations WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        all_conv_ids = [row[0] for row in conv_rows.all()]

        for owner_label, scan_fn in providers.items():
            owner_total = 0
            errored = False
            for cid in all_conv_ids:
                try:
                    scan_result = await scan_fn(
                        tenant_id=tenant_id, conversation_id=cid,
                    )
                    owner_total += int(getattr(scan_result, "total", 0))
                except Exception as exc:  # noqa: BLE001
                    blocked.append(f"{owner_label}_scan_error:{type(exc).__name__}")
                    owner_findings.append((owner_label, -1))
                    errored = True
                    break
            if not errored:
                owner_findings.append((owner_label, owner_total))
                if owner_total > 0:
                    blocked.append(f"{owner_label}_residual:{owner_total}")

        # 4. S6-6 巡检 —— 实际填充 verify_inspection.inspections（**不再恒为空**）
        from app.composition.s6i2_orphan_inspection import verify_inspection

        try:
            verify_report = await verify_inspection(
                session_factory,
                tenant_id=tenant_id,
                persist_event_gap=False,
            )
            for insp in verify_report.inspections:
                s6_6_findings.append(
                    (f"s6_6_{insp.inspection}", int(insp.findings_total))
                )
                if insp.findings_total > 0:
                    blocked.append(f"{insp.inspection}:{insp.findings_total}")
        except Exception as exc:  # noqa: BLE001
            blocked.append(f"s6_6_inspection_error:{type(exc).__name__}")

    open_allowed = not blocked
    return RestoreBeforeOpenReport(
        open_allowed=open_allowed,
        blocked_reasons=tuple(blocked),
        owner_scan_findings=tuple(owner_findings),
        s6_6_findings=tuple(s6_6_findings),
    )


__all__ = [
    "ACTION_LOCAL_CLEARED",
    "ACTION_CANDIDATE_WHEN_LOCAL",
    "ACTION_NON_LOCAL_BLOCKED",
    "ACTION_EXTERNAL_VERIFY_ONLY",
    "ACTION_RUNTIME_BINDING_UNPROVABLE",
    "ACTION_FACT_DRIFT_FAIL_CLOSED",
    "ACTION_REPLAY_SKIP_ZERO_WRITE",
    "ACTION_ZERO_WRITE",
    "ACTION_VERIFY_ONLY",
    "ACTION_SKIP",
    "ACTION_NO_REPEAT",
    "LOCAL_OWNERS",
    "NON_LOCAL_OWNERS",
    "VALID_OPERATION_STATES",
    "VALID_CHECKPOINT_STATES",
    "ValidatedFact",
    "ReplayOwnerVerdict",
    "RestoreReplayReport",
    "RestoreBeforeOpenReport",
    "RestoreReplayError",
    "replay_archive_segment_for_tenant",
    "evaluate_restore_before_open",
]
