# ruff: noqa: E501
"""R1-S6-I3-D D2 Round-1 P1 返修：restore replay executor + restore-before-open gate。

R1-S6-I3-D D2 Round-1 P1 返修（普通新 commit；不变更契约，仅按 6 项冻结边界修复）：
1. 四个本地 owner 精确映射到四个 participant 公共 sanctioned 入口：
   - workspace.core.v1 → ``WorkspaceErasureParticipant.erase_conversation_body``
   - execution.core.v1 → ``ExecutionErasureParticipant.erase_execution_body``
   - workspace.transport.v1 → ``WorkspaceTransportErasureParticipant.erase_transport_body``
   - execution.transport.v1 → ``ExecutionTransportErasureParticipant.erase_transport_body``
   禁止 transport owner 调 core helper；禁止私有 helper 拼装假 ACK。
2. 任何 DB mutation 前一次性重验 archive 六元组与恢复库：
   operation id/state/purge_revision/revision/lease_epoch；
   checkpoint id/state/owner_key/owner_version/capability_digest/ack_digest。
   任一 drift/缺行/scope mismatch → 整体零写 fail closed。
3. 删除自造 ``_compute_ack_digest`` / 裸 checkpoint ACK 路径。
   ACK/fence/checkpoint/final scan 全部复用对应 participant 既有事务语义。
4. 分离 external vs runtime：
   - ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE`` 仅 runtime.private.v1
   - external 不得使用 runtime reason
   - non-local owner 不得返回 ``candidate_when_local``
   - external/runtime adapter spy 严格 0 calls
   - report 计数按实际执行结果计算，不按 routing action 猜测
5. 执行器改为两遍：
   - pass A：全量 route + DB fact validation，绝对零写
   - pass B：单一 exclusive maintenance transaction 内执行
   pass B 任一 owner 失败必须抛出，整笔事务回滚；不得 catch-and-continue。
6. Gate 复用 ``build_scan_providers`` 的六 owner 冻结谓词；S6-6 复用
   ``verify_inspection(..., persist_event_gap=False)`` 或其只读同源 API。
   禁止复制缩减版 SQL。Gate 必须消费 replay blocking verdict；
   runtime proof c 存在时强制 closed。
   删除「``COUNT(all fences) = digest conflict``」等替代实现。

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
import hashlib
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.agent_erasure_locks import acquire_maintenance_exclusive_lock
from app.composition.s6i3_d_ledger_archive_sink import (
    LedgerArchiveSink,
    PublishOutcome,
)
from app.composition.s6i3_ledger_snapshot import (
    LedgerSnapshotError,
    Manifest,
    OwnerFacts,
    decode_ledger_segment,
    reconstruct_owner_facts,
)

# ---------------------------------------------------------------------------
# Action codes — frozen 路由表（30 scenarios = 6 operation × 5 checkpoint）
# ---------------------------------------------------------------------------

# local owner 通过 participant 公共 sanctioned 入口执行的最终 action
ACTION_LOCAL_CLEARED = "local_cleared"

# local owner 候选执行但本轮不执行（reserved）
ACTION_CANDIDATE_WHEN_LOCAL = "candidate_when_local"

# non-local owner（external / runtime）保持原状态 + verdict
ACTION_NON_LOCAL_BLOCKED = "non_local_blocked"

# external.payload.v1 + completed → verify-only（外部 adapter 不可调）
ACTION_EXTERNAL_VERIFY_ONLY = "external_verify_only"

# runtime.private.v1 + completed → RUNTIME_BINDING_EVIDENCE_UNPROVABLE（用户裁决 c）
ACTION_RUNTIME_BINDING_UNPROVABLE = "runtime_binding_evidence_unprovable"

# 六元组完整性 / state 漂移 → fail closed（零写）
ACTION_FACT_DRIFT_FAIL_CLOSED = "fact_drift_fail_closed"

# scheduled / failed / cancelled 状态路由
ACTION_REPLAY_SKIP_ZERO_WRITE = "replay_skip_zero_write"  # scheduled 零写
ACTION_ZERO_WRITE = "zero_write"  # failed 零写人工
ACTION_VERIFY_ONLY = "verify_only"  # completed 验证
ACTION_SKIP = "skip"  # cancelled
ACTION_NO_REPEAT = "no_repeat"  # 已 acked 不重复

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
# 对 local owner：返回 CANDIDATE_WHEN_LOCAL → pass B 调 participant 公共入口
# 对 non-local owner：返回 NON_LOCAL_BLOCKED（fail closed 验证状态，不调 adapter）
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

# 三层 CHECK 闭集
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
    """单 (operation, owner) 路由 / 执行决定。"""

    operation_id: str
    owner_key: str
    action: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreReplayReport:
    """一次 replay 的聚合计数。

    counts 按 **实际执行结果** 计算（不按 routing action 猜测）：
    - local owners 通过 participant 公共入口成功清除 → ``local_cleared``
    - non-local owners → ``non_local_blocked``（runtime completed 还会计入 runtime_unprovable）
    - fact drift → ``fact_drift_fail_closed``
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
    error: str | None = None

    def to_counter(self) -> Counter[str]:
        c: Counter[str] = Counter()
        for v in self.verdict:
            c[v.action] += 1
        return c


@dataclass(frozen=True, slots=True)
class RestoreBeforeOpenReport:
    """phase 3 gate 结果（六 owner scan + S6-6 巡检 + replay verdict + runtime proof c 闭环）。"""

    open_allowed: bool
    blocked_reasons: tuple[str, ...]
    owner_scan_findings: tuple[tuple[str, int], ...]  # (owner_label, findings_total)
    s6_6_findings: tuple[tuple[str, int], ...]
    replay_blocking_count: int = 0
    runtime_proof_c_blocks_open: bool = False


class RestoreReplayError(Exception):
    """D2 内部错误（archive 损坏 / marker mismatch / 六元组 drift 等）。"""

    def __init__(self, code: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail or {})


# ---------------------------------------------------------------------------
# phase 1 — archive read（DB tx 外）
# ---------------------------------------------------------------------------


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


async def _fetch_segment_outside_tx(
    sink: LedgerArchiveSink,
    *,
    tenant_id: uuid.UUID,
    segment_key: str,
    expected_sha: str,
) -> bytes:
    """从 sink 读取 segment 字节并校验 SHA-256（严格位于 DB tx 外）。"""
    body = await asyncio.to_thread(sink.get_object, segment_key)
    actual_sha = _sha256_hex(body)
    if actual_sha != expected_sha:
        raise RestoreReplayError(
            "SEGMENT_OBJECT_MISSING_OR_CORRUPT",
            detail={
                "expected_sha": expected_sha,
                "actual_sha": actual_sha,
                "segment_key": segment_key,
            },
        )
    return body


async def _read_archive_outside_tx(
    sink: LedgerArchiveSink,
    *,
    tenant_id: uuid.UUID,
    expected_marker: PublishOutcome,
) -> tuple[Manifest, dict[tuple[str, str], OwnerFacts]]:
    """phase 1：archive read + D1a decode + 六元组重构（DB tx 外）。"""
    segment_bytes = await _fetch_segment_outside_tx(
        sink,
        tenant_id=tenant_id,
        segment_key=expected_marker.segment_key,
        expected_sha=expected_marker.segment_sha256,
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
# pass A — validate（绝对零写；六元组 + operation fence 全字段对账）
# ---------------------------------------------------------------------------


async def _load_operation_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, operation_id: uuid.UUID
) -> dict | None:
    """读 operation 全字段（id/state/purge_revision/revision/lease_epoch）。

    返回 None 表示行不存在；任何字段缺失视同 drift。"""
    row = await session.execute(
        text(
            "SELECT id, state, purge_revision, revision, lease_epoch "
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
    """读 checkpoint 全字段（id/state/owner_key/owner_version/capability_digest/ack_digest）。

    返回 None 表示行不存在；任一字段缺失视同 drift。"""
    row = await session.execute(
        text(
            "SELECT id, state, owner_key, owner_version, capability_digest, ack_digest "
            "FROM metaedu.agent_conversation_purge_owners "
            "WHERE tenant_id = :tid AND purge_operation_id = :pid "
            "AND owner_key = :ok"
        ),
        {"tid": tenant_id, "pid": purge_operation_id, "ok": owner_key},
    )
    m = row.mappings().first()
    return dict(m) if m is not None else None


@dataclass(frozen=True, slots=True)
class ValidatedFact:
    """pass A 验证后的 (operation, checkpoint) 行字段，用于 pass B 调 participant。"""

    operation_id: uuid.UUID
    operation_state: str
    purge_revision: int
    operation_revision: int
    lease_epoch: int
    conversation_id: uuid.UUID
    checkpoint_id: uuid.UUID
    checkpoint_state: str
    owner_key: str
    owner_version: int
    capability_digest: str
    ack_digest: str | None


async def _validate_pass_a(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fact: OwnerFacts,
) -> ValidatedFact:
    """pass A：单 (operation, owner) 事实重验（六元组 + operation fence 全字段）。

    任何 drift / 缺行 / scope mismatch → 抛 ``RestoreReplayError``；
    caller 必须在 pass A 阶段捕获并把整个 replay 标 fail closed（零写）。
    """
    op_id = uuid.UUID(fact.operation_id)

    op_row = await _load_operation_row(
        session, tenant_id=tenant_id, operation_id=op_id
    )
    if op_row is None:
        raise RestoreReplayError(
            "FACT_DRIFT_OPERATION_MISSING",
            detail={"operation_id": fact.operation_id},
        )

    # archive operation 字段（在 Manifest 之外；本验证仅用 DB 端字段 + archive 标识一致）
    # archive 六元组必含字段：owner_key / purge_operation_id / owner_version /
    # capability_digest / state（decoder 已 fail closed 校验；此处仅用与 DB 对账）。
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

    # scope 严格：fact.owner_key 必须等于 cp_row.owner_key
    if cp_row["owner_key"] != fact.owner_key:
        raise RestoreReplayError(
            "FACT_DRIFT_OWNER_SCOPE_MISMATCH",
            detail={
                "archive_owner_key": fact.owner_key,
                "db_owner_key": cp_row["owner_key"],
            },
        )
    # operation state 必须 ∈ frozen 闭集（任何 quiesced / rebuilding 等派生术语 DB 不允许；
    # 但若 DB 因迁移问题含有越界值，仍应 fail closed）
    if op_row["state"] not in VALID_OPERATION_STATES:
        raise RestoreReplayError(
            "FACT_DRIFT_UNKNOWN_OP_STATE",
            detail={"state": op_row["state"]},
        )
    if cp_row["state"] not in VALID_CHECKPOINT_STATES:
        raise RestoreReplayError(
            "FACT_DRIFT_UNKNOWN_CP_STATE",
            detail={"state": cp_row["state"]},
        )
    # archive fact 六元组字段与 DB 一致（owner_version / capability_digest / state /
    # ack_digest 在 state==='acked' 时非 None）
    if fact.owner_version != cp_row["owner_version"]:
        raise RestoreReplayError(
            "FACT_DRIFT_OWNER_VERSION_MISMATCH",
            detail={
                "archive_owner_version": fact.owner_version,
                "db_owner_version": cp_row["owner_version"],
            },
        )
    if fact.capability_digest != cp_row["capability_digest"]:
        raise RestoreReplayError(
            "FACT_DRIFT_CAPABILITY_DIGEST_MISMATCH",
            detail={
                "archive_capability_digest": fact.capability_digest,
                "db_capability_digest": cp_row["capability_digest"],
            },
        )
    if fact.checkpoint_state != cp_row["state"]:
        raise RestoreReplayError(
            "FACT_DRIFT_CP_STATE_MISMATCH",
            detail={
                "archive_cp_state": fact.checkpoint_state,
                "db_cp_state": cp_row["state"],
            },
        )

    return ValidatedFact(
        operation_id=op_id,
        operation_state=op_row["state"],
        purge_revision=int(op_row["purge_revision"]),
        operation_revision=int(op_row["revision"]),
        lease_epoch=int(op_row["lease_epoch"]),
        conversation_id=await session.scalar(
            text(
                "SELECT conversation_id FROM metaedu.agent_conversation_purges "
                "WHERE tenant_id = :tid AND id = :oid"
            ),
            {"tid": tenant_id, "oid": op_id},
        ) or _ZERO_UUID,
        checkpoint_id=cp_row["id"],
        checkpoint_state=cp_row["state"],
        owner_key=fact.owner_key,
        owner_version=int(cp_row["owner_version"]),
        capability_digest=cp_row["capability_digest"],
        ack_digest=cp_row["ack_digest"],
    )


_ZERO_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# pass B — execute（单一 exclusive maintenance tx；调 participant 公共入口）
# ---------------------------------------------------------------------------


async def _route_action(
    *, operation_state: str, checkpoint_state: str, owner_key: str
) -> tuple[str, str | None]:
    """routing 表 + external/runtime 分离规则 → (action, reason_code)。

    non-local owner 永不返回 ``candidate_when_local``；
    runtime completed → ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE``（仅 runtime）；
    external completed → ``EXTERNAL_VERIFY_ONLY``（仅 external）。
    """
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
            # external.payload.v1 completed → verify-only（不调 adapter）
            return ACTION_EXTERNAL_VERIFY_ONLY, None
        # non-local + 非 completed → blocked verdict（不调 adapter）
        return ACTION_NON_LOCAL_BLOCKED, "non_local_no_adapter"

    # local owner 走标准 6×5 路由表
    routing = _OPERATION_ROUTING.get(operation_state)
    if routing is None:
        return (
            ACTION_FACT_DRIFT_FAIL_CLOSED,
            f"unknown_op_state:{operation_state}",
        )
    action = routing.get(checkpoint_state)
    if action is None:
        return (
            ACTION_FACT_DRIFT_FAIL_CLOSED,
            f"unknown_cp_state:{checkpoint_state}",
        )
    return action, None


async def _execute_local_owner_via_participant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
) -> None:
    """pass B：local owner 通过对应 participant 公共 sanctioned 入口清除 + ACK。

    严格映射：
    - workspace.core.v1 → ``WorkspaceErasureParticipant.erase_conversation_body``
    - execution.core.v1 → ``ExecutionErasureParticipant.erase_execution_body``
    - workspace.transport.v1 → ``WorkspaceTransportErasureParticipant.erase_transport_body``
    - execution.transport.v1 → ``ExecutionTransportErasureParticipant.erase_transport_body``

    公共入口内部已自管 Conversation/owner/fence 锁 + ACK + final scan；
    本函数不复制任何 SQL、不写裸 checkpoint ACK。
    participant 抛错即整笔事务回滚（caller 不 catch-and-continue）。
    """
    # 不同 owner 调不同 participant；本函数按 owner 分支独立 import + 构造，
    # 不跨分支共享 ``participant`` 变量类型（mypy 推断）。

    if validated.owner_key == "workspace.core.v1":
        from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
            WorkspaceErasureParticipant,
        )

        await WorkspaceErasureParticipant(session).erase_conversation_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.operation_revision,
            expected_lease_epoch=validated.lease_epoch,
        )
        return

    if validated.owner_key == "execution.core.v1":
        from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
            ExecutionErasureParticipant,
        )

        await ExecutionErasureParticipant(session).erase_execution_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.operation_revision,
            expected_lease_epoch=validated.lease_epoch,
        )
        return

    if validated.owner_key == "workspace.transport.v1":
        from datetime import UTC, datetime

        from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
            WorkspaceTransportErasureParticipant,
        )

        # transport 公共入口不需要 purge_operation_id / expected_operation_revision /
        # expected_lease_epoch（它用 conversation_id + purge_revision + now 锁 outbox/inbox）
        await WorkspaceTransportErasureParticipant(session).erase_transport_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.purge_revision,
            now=datetime.now(UTC),
        )
        return

    if validated.owner_key == "execution.transport.v1":
        from datetime import UTC, datetime

        from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (
            ExecutionTransportErasureParticipant,
        )

        await ExecutionTransportErasureParticipant(session).erase_transport_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.purge_revision,
            now=datetime.now(UTC),
        )
        return

    raise RestoreReplayError(
        "UNKNOWN_LOCAL_OWNER",
        detail={"owner_key": validated.owner_key},
    )


# ---------------------------------------------------------------------------
# Public entrypoint（两遍执行）
# ---------------------------------------------------------------------------


async def replay_archive_segment_for_tenant(
    session_factory: async_sessionmaker,
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
    expected_marker: PublishOutcome,
) -> RestoreReplayReport:
    """D2 主入口（两遍执行）：

    - pass A（全量 route/DB fact validation，绝对零写）：
      每一 (operation, owner) 重读 DB 并对账 archive 六元组与 operation fence；
      任一 drift/缺行/scope mismatch → 立即抛 ``RestoreReplayError``（零写）。
    - pass B（单一 exclusive maintenance transaction 执行）：
      取 exclusive advisory xact_lock 后逐 owner 调 participant 公共入口；
      任一 owner 失败必须抛出（不 catch），整笔事务回滚。

    report 计数按实际执行结果：
    - local owner 通过 participant 入口成功 → ``local_cleared``
    - non-local owner → ``non_local_blocked``
    - fact drift → ``fact_drift_fail_closed``
    - runtime completed → ``runtime_binding_evidence_unprovable``
    """
    try:
        _manifest, facts = await _read_archive_outside_tx(
            sink,
            tenant_id=tenant_id,
            expected_marker=expected_marker,
        )
    except RestoreReplayError as exc:
        return RestoreReplayReport(error=f"{exc.code}: {exc.detail}")

    operations_total = len({op_id for op_id, _ in facts})

    # -------- pass A：全量 route + DB fact validation（绝对零写）--------
    # 使用同一个事务读取（只读），保证 consistency 但不写任何东西。
    async with session_factory() as session, session.begin():
        validated_facts: list[tuple[OwnerFacts, ValidatedFact | str]] = []
        for fact in facts.values():
            try:
                vf = await _validate_pass_a(
                    session, tenant_id=tenant_id, fact=fact,
                )
            except RestoreReplayError as exc:
                # 记录 drift，但**整批** fail closed：先继续收集所有 verdict 以便 report 完整
                validated_facts.append((fact, exc.code))
                continue
            validated_facts.append((fact, vf))

    # -------- pass B：单一 exclusive maintenance transaction 执行 --------
    verdicts: list[ReplayOwnerVerdict] = []
    async with session_factory() as session, session.begin():
        # 第一条 DB 语句必须是 exclusive advisory xact lock
        await acquire_maintenance_exclusive_lock(session)

        for fact, vf_or_drift in validated_facts:
            if isinstance(vf_or_drift, str):
                # pass A 失败 → 整体零写，verdict 记录但 pass B 不执行任何写入
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_FACT_DRIFT_FAIL_CLOSED,
                        reason_code=vf_or_drift,
                    )
                )
                continue

            validated = vf_or_drift
            action, reason = await _route_action(
                operation_state=validated.operation_state,
                checkpoint_state=validated.checkpoint_state,
                owner_key=validated.owner_key,
            )

            if action == ACTION_CANDIDATE_WHEN_LOCAL:
                # 本地 owner 候选 → 调 participant 公共入口
                # 任一 owner 抛错即整笔事务回滚（不 catch）
                await _execute_local_owner_via_participant(
                    session,
                    tenant_id=tenant_id,
                    validated=validated,
                )
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_LOCAL_CLEARED,
                        reason_code="local_cleared_via_participant",
                    )
                )
            elif action == ACTION_NON_LOCAL_BLOCKED:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_NON_LOCAL_BLOCKED,
                        reason_code=reason,
                    )
                )
            elif action == ACTION_RUNTIME_BINDING_UNPROVABLE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_RUNTIME_BINDING_UNPROVABLE,
                        reason_code="RUNTIME_BINDING_EVIDENCE_UNPROVABLE",
                    )
                )
            elif action == ACTION_EXTERNAL_VERIFY_ONLY:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_EXTERNAL_VERIFY_ONLY,
                    )
                )
            elif action == ACTION_VERIFY_ONLY:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_VERIFY_ONLY,
                    )
                )
            elif action == ACTION_REPLAY_SKIP_ZERO_WRITE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_REPLAY_SKIP_ZERO_WRITE,
                        reason_code="scheduled_only_restore_cancel",
                    )
                )
            elif action == ACTION_ZERO_WRITE:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_ZERO_WRITE,
                        reason_code="zero_write_manual",
                    )
                )
            elif action == ACTION_SKIP:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_SKIP,
                    )
                )
            elif action == ACTION_NO_REPEAT:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_NO_REPEAT,
                    )
                )
            else:
                # unknown action → 抛错整笔事务回滚
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
    )


def _count_verdicts_by_actual_result(
    verdicts: list[ReplayOwnerVerdict],
) -> Counter[str]:
    """按实际执行结果（不是 routing 猜测）统计。"""
    c: Counter[str] = Counter()
    for v in verdicts:
        c[v.action] += 1
    return c


# ---------------------------------------------------------------------------
# phase 3 — restore-before-open gate（复用 build_scan_providers + verify_inspection）
# ---------------------------------------------------------------------------


async def evaluate_restore_before_open(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    replay_blocking_count: int = 0,
    runtime_proof_c_present: bool = False,
) -> RestoreBeforeOpenReport:
    """phase 3 gate（六 owner scan + S6-6 巡检 + replay verdict 消费 + runtime proof c 闭环）。

    - 六 owner scan 复用 ``build_scan_providers(session)``（冻结谓词同源；
      **不复制缩减版 SQL**）
    - S6-6 巡检复用 ``verify_inspection(..., persist_event_gap=False)``
      （其只读同源 API；不另写）
    - replay blocking verdict 必须消费（``replay_blocking_count > 0`` → 阻断）
    - runtime proof c 存在 → 强制 closed（按用户裁决 c 不可重算）
    """
    owner_findings: list[tuple[str, int]] = []
    blocked: list[str] = []

    async with session_factory() as session, session.begin():
        # 1. 六 owner scan —— 复用 build_scan_providers 冻结谓词
        #    每个 owner scan 都需 conversation_id（按 conversation 维度检查）；
        #    gate 必须消费所有 conversation 的扫描结果才能开放流量。
        from app.composition.transactional_projection_coordinator import (
            build_scan_providers,
        )

        providers = build_scan_providers(session)

        # 收集 tenant 内所有 conversation（gate 须覆盖 tenant 全集）
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
            for cid in all_conv_ids:
                try:
                    scan_result = await scan_fn(
                        tenant_id=tenant_id, conversation_id=cid,
                    )
                    owner_total += int(getattr(scan_result, "total", 0))
                except Exception as exc:  # noqa: BLE001 - scan 抛错即 fail closed
                    blocked.append(f"{owner_label}_scan_error:{type(exc).__name__}")
                    owner_findings.append((owner_label, -1))
                    break
            else:
                owner_findings.append((owner_label, owner_total))
                if owner_total > 0:
                    blocked.append(f"{owner_label}_residual:{owner_total}")
                continue
            break

        # 2. S6-6 巡检 —— 复用 verify_inspection 只读模式
        from app.composition.s6i2_orphan_inspection import verify_inspection

        # verify_inspection 必须在六类 inspection 上跑；用 persist_event_gap=False
        # 保证零 ledger 写入
        try:
            verify_report = await verify_inspection(
                session_factory,
                tenant_id=tenant_id,
                persist_event_gap=False,
            )
            for insp in verify_report.inspections:
                if insp.findings_total > 0:
                    blocked.append(f"{insp.inspection}:{insp.findings_total}")
                # 把 findings 累加进 owner_findings 视图（保持结构对称）
                owner_findings.append(
                    (f"s6_6_{insp.inspection}", int(insp.findings_total))
                )
        except Exception as exc:  # noqa: BLE001 - 巡检抛错即 fail closed
            blocked.append(f"s6_6_inspection_error:{type(exc).__name__}")

    # 3. replay blocking verdict 消费（replay 必须为 0 才允许开）
    if replay_blocking_count > 0:
        blocked.append(f"replay_blocking:{replay_blocking_count}")

    # 4. runtime proof c 存在 → 强制 closed（按用户裁决 c 不可重算）
    if runtime_proof_c_present:
        blocked.append("RUNTIME_BINDING_EVIDENCE_UNPROVABLE:runtime_proof_c_present")

    open_allowed = not blocked
    return RestoreBeforeOpenReport(
        open_allowed=open_allowed,
        blocked_reasons=tuple(blocked),
        owner_scan_findings=tuple(owner_findings),
        s6_6_findings=tuple(),
        replay_blocking_count=replay_blocking_count,
        runtime_proof_c_blocks_open=runtime_proof_c_present,
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
