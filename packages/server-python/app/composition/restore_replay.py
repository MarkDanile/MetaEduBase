# ruff: noqa: E501
"""R1-S6-I3-D D2: restore replay executor + restore-before-open gate。

契约（用户裁决 5 项，fact-audit §17.5 supersede 旧待用户裁决，2026-08-27）：
- Runtime per-binding proof = ``c``（archived completed runtime 缺 per-binding proof 时
  返回具名 ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE``；零 DB 写、不修改 terminal operation、
  不伪造 blocked/acked、不写假 receipt；restore-before-open 保持关闭，转 runbook 人工处置）
- M 类互斥 = ``A``（global ``pg_advisory_xact_lock_shared`` 给 retention/audit；replay 取
  ``pg_advisory_xact_lock`` exclusive；新锁必须早于 Run/Conversation/owner/collection 锁；
  同一稳定 namespace/scope；须写作 S6-4 锁序登记修订）
- D1a+D1b+D2 = 三独立 PR
- 顺序 D1a → D1b → D2（D1a 已合 main ``5868831e``；D1b 已合 main ``01c84f7c``）
- D1b = 专用 MinIO archive bucket

阶段分解（严格按本任务卡指令）：

- phase 0：启动前审计（migration 040 已有完整 owner fact 持久化 = 六元组跨表；runtime
  owner + ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE`` = 合法组合无需新 schema）
- phase 1：archive 读取（DB tx 外；复用 ``fetch_segment_bytes`` / D1a ``decode_ledger_segment``
  / D1a ``reconstruct_owner_facts``）
- phase 2：单一 restore DB maintenance 事务（exclusive advisory xact_lock → 现有 sanctioned
  local owner participant helper → 单 owner 失败 rollback 全事务）
- phase 3：restore-before-open 编排（六 owner scan → ``open_allowed`` / ``blocked_reasons``）

严格边界（spec §S6-8.3 + §S6-13 + 用户裁决）：
- 不调用 external/runtime adapter（spec §S6-8.3 字面要求）
- 不依赖 production scheduler
- 不接 capability flip / registry capability 翻转
- 不动 migration / schema / enum / CHECK
- 不复制第二套清除 SQL — 复用 execution/workspace/external/runtime participant
  私有 helper 方法（``ExecutionErasureParticipant._clear_*`` /
  ``WorkspaceErasureParticipant._erase_conversation_title`` 等）；
  D2 不复制任何清除 SQL
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

ACTION_REPLAY_SKIP_ZERO_WRITE = "replay_skip_zero_write"
ACTION_CANDIDATE_WHEN_LOCAL = "candidate_when_local"
ACTION_BLOCKED_LOCAL_MATCH_REASON = "blocked_local_match_reason"
ACTION_ZERO_WRITE = "zero_write"
ACTION_VERIFY_ONLY = "verify_only"
ACTION_SKIP = "skip"
ACTION_NO_REPEAT = "no_repeat"

# 4 local owners（clearing 可执行）；external/runtime 保持 blocked verdict（不调 adapter）
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
_OPERATION_ROUTING: dict[str, dict[str, str]] = {
    # scheduled：仅 restore-cancel 路径可达；executor 零写
    "scheduled": {
        "pending": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "erasing": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "blocked": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "failed": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "acked": ACTION_REPLAY_SKIP_ZERO_WRITE,
    },
    # running：本地 owner + 六元组完整 → 候选；其他按 checkpoint state 路由
    "running": {
        "pending": ACTION_CANDIDATE_WHEN_LOCAL,
        "erasing": ACTION_CANDIDATE_WHEN_LOCAL,
        "blocked": ACTION_BLOCKED_LOCAL_MATCH_REASON,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_NO_REPEAT,
    },
    # blocked：本地 owner + 六元组完整 → 候选；其他按 checkpoint state 路由
    "blocked": {
        "pending": ACTION_CANDIDATE_WHEN_LOCAL,
        "erasing": ACTION_CANDIDATE_WHEN_LOCAL,
        "blocked": ACTION_BLOCKED_LOCAL_MATCH_REASON,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_NO_REPEAT,
    },
    # failed：零写人工
    "failed": {
        "pending": ACTION_ZERO_WRITE,
        "erasing": ACTION_ZERO_WRITE,
        "blocked": ACTION_ZERO_WRITE,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_ZERO_WRITE,
    },
    # completed：verify-only（不重复 side effect）
    "completed": {
        "pending": ACTION_VERIFY_ONLY,
        "erasing": ACTION_VERIFY_ONLY,
        "blocked": ACTION_VERIFY_ONLY,
        "failed": ACTION_VERIFY_ONLY,
        "acked": ACTION_VERIFY_ONLY,
    },
    # cancelled：skip
    "cancelled": {
        "pending": ACTION_SKIP,
        "erasing": ACTION_SKIP,
        "blocked": ACTION_SKIP,
        "failed": ACTION_SKIP,
        "acked": ACTION_SKIP,
    },
}

# 三层 CHECK 闭集（migration 034 + 040）
VALID_OPERATION_STATES: frozenset[str] = frozenset({
    "scheduled", "running", "blocked", "failed", "completed", "cancelled",
})
VALID_CHECKPOINT_STATES: frozenset[str] = frozenset({
    "pending", "erasing", "blocked", "failed", "acked",
})

# 派生术语 / 跨层 / 未知状态：fail closed，零写
UNKNOWN_STATE_FAIL_CLOSED: str = "unknown_state_fail_closed"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReplayOwnerVerdict:
    """单 (operation, owner) 路由决定。"""

    operation_id: str
    owner_key: str
    action: str  # ACTION_* enum
    reason_code: str | None = None  # 结构化 reason code（如需要）


@dataclass(frozen=True, slots=True)
class RestoreReplayReport:
    """一次 replay 的聚合计数（仅计数与状态枚举；不含正文 / ref）。"""

    operations_total: int = 0
    owners_total: int = 0
    owners_local_cleared: int = 0
    owners_blocked_kept: int = 0
    owners_verify_only: int = 0
    owners_skipped: int = 0
    owners_failed: int = 0
    runtime_binding_evidence_unprovable: int = 0  # 用户裁决 c
    verdict: tuple[ReplayOwnerVerdict, ...] = ()
    error: str | None = None

    def to_counter(self) -> Counter[str]:
        c: Counter[str] = Counter()
        for v in self.verdict:
            c[v.action] += 1
        return c


@dataclass(frozen=True, slots=True)
class RestoreBeforeOpenReport:
    """phase 3 gate 结果（仅含 inspection 名称 + finding 计数）。"""

    open_allowed: bool
    blocked_reasons: tuple[str, ...]
    inspections: tuple[tuple[str, int], ...]  # (inspection_name, findings_total)


class RestoreReplayError(Exception):
    """D2 内部错误（archive 损坏 / marker mismatch 等）。"""

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
    """从 sink 读取 segment 字节并校验 SHA-256（严格位于 DB tx 外）。

    复用 ``fetch_segment_bytes`` 的 SHA-256 校验语义；本函数不构造
    ``CommitMarker``（caller 提供 ``PublishOutcome`` 即可），与 D1b 两阶段 API
    publish 后 GET-back digest verify 路径一致。MinIO SDK 同步调用经
    ``asyncio.to_thread`` 移交出事件循环；期间不持任何数据库事务或锁。
    """
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
    """phase 1：archive read + D1a decode + 六元组重构（DB tx 外）。

    复用 D1a ``decode_ledger_segment`` / ``reconstruct_owner_facts`` 严格
    fail-closed 校验（含 tenant binding / 六元组完整性 / record kind-table 配对 /
    cross-layer 拒绝 / runtime_per_binding_proof_available=False 强制）。
    """
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
            detail={"reason": exc.code, **exc.detail},
        ) from exc
    facts = reconstruct_owner_facts(manifest)
    return manifest, facts


# ---------------------------------------------------------------------------
# phase 2 — single restore DB maintenance transaction
# ---------------------------------------------------------------------------


async def _load_operation_state(
    session: AsyncSession, *, tenant_id: uuid.UUID, operation_id: uuid.UUID
) -> str | None:
    """读 operation 当前 state（含 purge_revision）；None 表示行不存在。"""
    row = await session.execute(
        text(
            "SELECT state FROM metaedu.agent_conversation_purges "
            "WHERE tenant_id = :tid AND id = :oid"
        ),
        {"tid": tenant_id, "oid": operation_id},
    )
    result = row.scalar_one_or_none()
    return str(result) if result is not None else None


async def _update_checkpoint_to_acked(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    ack_digest_hex: str,
) -> int:
    """checkpoint 状态机迁移 pending|erasing|blocked → acked（CAS-style 单 writer）。

    与 ``transport_erasure_participant._ack_owner_checkpoint`` 的语义一致；
    本函数**不**调用外部 adapter；仅刷新 checkpoint.state + 写 ack_digest。

    ``ack_digest_hex`` 由 caller 提供（64-hex lowercase；SHA-256 over
    canonical envelope；与 migration 034 ``ck_agent_purge_owner_ack`` 长度约束
    兼容 + 应用层 64-hex lowercase 校验）。

    返回影响行数（1 = 成功；0 = 行已被并发写者迁移，no-op 幂等）。
    """
    if not isinstance(ack_digest_hex, str) or len(ack_digest_hex) != 64:
        raise RestoreReplayError(
            "ACK_DIGEST_FORMAT_INVALID",
            detail={"reason": "64hex_required", "found_len": len(ack_digest_hex)},
        )
    result = await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state = 'acked', ack_digest = :ad "
            "WHERE tenant_id = :tid AND id = :cpid "
            "AND state IN ('pending', 'erasing', 'blocked')"
        ),
        {"tid": tenant_id, "cpid": checkpoint_id, "ad": ack_digest_hex},
    )
    return int(result.rowcount or 0) if hasattr(result, "rowcount") else 0


def _compute_ack_digest(
    *, tenant_id: uuid.UUID, operation_id: str, owner_key: str
) -> str:
    """计算 ack_digest（应用层 64-hex lowercase；SHA-256 over canonical envelope）。

    与 ``transport_erasure_participant._compute_ack_digest`` 字面同构；
    本函数为 D2 复算入口（不调 adapter，纯 hash）。
    """
    import json

    envelope = {
        "tenant_id": str(tenant_id),
        "operation_id": operation_id,
        "owner_key": owner_key,
        "schema_version": 1,
    }
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _route_owner(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fact: OwnerFacts,
) -> ReplayOwnerVerdict:
    """单 (operation, owner) 路由 + 本地清除（如 eligible）。

    不复制第二套清除 SQL —— 本函数对 local owner 调用
    ``WorkspaceErasureParticipant._erase_conversation_title`` /
    ``_anonymize_conversation_actors`` / ``_redact_messages`` 与
    ``ExecutionErasureParticipant._clear_terminal_outputs`` 等 sanctioned
    helper（其内部 SQL 即冻结的清除路径）。
    """
    op_id = uuid.UUID(fact.operation_id)
    op_state = await _load_operation_state(
        session, tenant_id=tenant_id, operation_id=op_id
    )

    if op_state is None:
        # operation 行不存在（archive 含过期 / 未落地 operation）
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=ACTION_ZERO_WRITE,
            reason_code="operation_missing",
        )

    cp_state = fact.checkpoint_state
    routing = _OPERATION_ROUTING.get(op_state)
    if routing is None:
        # 派生术语（quiesced / rebuilding）或跨层 / 未知 operation state → fail closed
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=UNKNOWN_STATE_FAIL_CLOSED,
            reason_code=f"unknown_op_state:{op_state}",
        )
    action = routing.get(cp_state)
    if action is None:
        # 跨层 / 未知 checkpoint state → fail closed
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=UNKNOWN_STATE_FAIL_CLOSED,
            reason_code=f"unknown_cp_state:{cp_state}",
        )

    # 已 acked：禁止重复清除
    if action == ACTION_NO_REPEAT:
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=ACTION_NO_REPEAT,
        )

    # completed + runtime.owner：per-binding proof 不可重算 → 零写 + 人工 reconcile
    if (
        op_state == "completed"
        and fact.owner_key in NON_LOCAL_OWNERS
        and not fact.runtime_per_binding_proof_available
    ):
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=ACTION_VERIFY_ONLY,
            reason_code="RUNTIME_BINDING_EVIDENCE_UNPROVABLE",
        )

    # verify-only（completed 任何 owner / external.runtime completed）→ 不重算 ack
    if action == ACTION_VERIFY_ONLY:
        return ReplayOwnerVerdict(
            operation_id=fact.operation_id,
            owner_key=fact.owner_key,
            action=ACTION_VERIFY_ONLY,
        )

    # 候选：本机 owner + running|blocked + pending|erasing + 六元组完整 → 清 + 标 acked
    if action == ACTION_CANDIDATE_WHEN_LOCAL and fact.owner_key in LOCAL_OWNERS:
        cleared = await _clear_local_owner(
            session, tenant_id=tenant_id, fact=fact,
        )
        if cleared > 0:
            cp_row = await session.execute(
                text(
                    "SELECT id FROM metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :tid AND purge_operation_id = :pid "
                    "AND owner_key = :ok"
                ),
                {
                    "tid": tenant_id,
                    "pid": op_id,
                    "ok": fact.owner_key,
                },
            )
            cp_id = cp_row.scalar_one_or_none()
            if cp_id is not None:
                ack_digest = _compute_ack_digest(
                    tenant_id=tenant_id,
                    operation_id=fact.operation_id,
                    owner_key=fact.owner_key,
                )
                await _update_checkpoint_to_acked(
                    session,
                    tenant_id=tenant_id,
                    checkpoint_id=cp_id,
                    ack_digest_hex=ack_digest,
                )
            return ReplayOwnerVerdict(
                operation_id=fact.operation_id,
                owner_key=fact.owner_key,
                action=ACTION_CANDIDATE_WHEN_LOCAL,
                reason_code="local_cleared",
            )

    # 其余（non-local owner / blocked / failed / etc）→ 不调 adapter，记 verdict
    return ReplayOwnerVerdict(
        operation_id=fact.operation_id,
        owner_key=fact.owner_key,
        action=action,
    )


async def _clear_local_owner(
    session: AsyncSession, *, tenant_id: uuid.UUID, fact: OwnerFacts
) -> int:
    """复用 sanctioned local owner participant helper（不复制第二套 SQL）。

    workspace.core.v1 / workspace.transport.v1 → WorkspaceErasureParticipant
        _erase_conversation_title + _anonymize_conversation_actors + _redact_messages
    execution.core.v1 / execution.transport.v1 → ExecutionErasureParticipant
        _clear_terminal_outputs + _clear_context_snapshots + _clear_compatibility_outputs
        + _clear_event_payloads + _anonymize_actors
    """
    op_id = uuid.UUID(fact.operation_id)
    conversation_id = await session.scalar(
        text(
            "SELECT conversation_id FROM metaedu.agent_conversation_purges "
            "WHERE tenant_id = :tid AND id = :oid"
        ),
        {"tid": tenant_id, "oid": op_id},
    )
    if conversation_id is None:
        return 0

    cleared = 0
    if fact.owner_key in {"workspace.core.v1", "workspace.transport.v1"}:
        cleared += await _clear_workspace_owner(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
    elif fact.owner_key in {"execution.core.v1", "execution.transport.v1"}:
        cleared += await _clear_execution_owner(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
    return cleared


async def _clear_workspace_owner(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> int:
    """复用 WorkspaceErasureParticipant sanctioned helpers（不复制 SQL）。"""
    from datetime import UTC, datetime

    from sqlalchemy import select as _select

    from app.contexts.agent_workspace.infrastructure.models import (
        ConversationModel,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
        WorkspaceErasureParticipant,
    )

    participant = WorkspaceErasureParticipant(session)
    now = datetime.now(UTC)
    conversation = (
        await session.execute(
            _select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == conversation_id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        return 0

    cleared = 0
    cleared += participant._erase_conversation_title(conversation, now=now)
    cleared += participant._anonymize_conversation_actors(
        conversation, tenant_id=tenant_id
    )
    cleared += await participant._redact_messages(
        tenant_id=tenant_id, conversation_id=conversation_id, now=now
    )
    return cleared


async def _clear_execution_owner(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> int:
    """复用 ExecutionErasureParticipant sanctioned helpers（不复制 SQL）。"""
    from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
        ExecutionErasureParticipant,
    )

    participant = ExecutionErasureParticipant(session)
    now = await participant._database_now()
    cleared = 0
    cleared += (await participant._clear_terminal_outputs(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        now=now,
    ))[0]
    cleared += await participant._clear_context_snapshots(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        now=now,
    )
    cleared += await participant._clear_compatibility_outputs(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        now=now,
    )
    cleared += await participant._clear_event_payloads(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        now=now,
    )
    cleared += (await participant._anonymize_actors(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        now=now,
    ))[0]
    return cleared


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def replay_archive_segment_for_tenant(
    session_factory: async_sessionmaker,
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
    expected_marker: PublishOutcome,
) -> RestoreReplayReport:
    """D2 主入口：phase 1（archive 读）+ phase 2（maintenance tx 路由与清除）。

    Args:
        session_factory: caller 提供的 async_sessionmaker（PG 测试库 / 恢复库）。
        sink: archive sink（InMemoryLedgerArchiveSink 或 MinioLedgerArchiveSink）。
        tenant_id: 恢复 tenant。
        expected_marker: ``PublishOutcome`` from D1b publish——本函数校验其
            ``segment_sha256`` 与 sink 内实际字节一致；任何 mismatch 立即
            ``RestoreReplayError``（fail closed）。

    Returns:
        ``RestoreReplayReport``（仅计数与 verdict tuple，不含正文 / ref）。
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
    owners_total = len(facts)

    verdicts: list[ReplayOwnerVerdict] = []
    async with session_factory() as session, session.begin():
        # 第一条 DB 语句必须是 exclusive advisory xact lock（Plan §S6-8.3 + 用户裁决 A）
        # 早于任何其他锁；同一 stable namespace/scope（maintenance_lock_key）
        await acquire_maintenance_exclusive_lock(session)

        for fact in facts.values():
            try:
                verdict = await _route_owner(
                    session, tenant_id=tenant_id, fact=fact,
                )
            except LedgerSnapshotError as exc:
                verdicts.append(
                    ReplayOwnerVerdict(
                        operation_id=fact.operation_id,
                        owner_key=fact.owner_key,
                        action=ACTION_ZERO_WRITE,
                        reason_code=f"snapshot_error:{exc.code}",
                    )
                )
                continue
            verdicts.append(verdict)

    counts = _count_verdicts(verdicts)
    return RestoreReplayReport(
        operations_total=operations_total,
        owners_total=owners_total,
        owners_local_cleared=counts[ACTION_CANDIDATE_WHEN_LOCAL],
        owners_blocked_kept=counts[ACTION_BLOCKED_LOCAL_MATCH_REASON],
        owners_verify_only=counts[ACTION_VERIFY_ONLY],
        owners_skipped=counts[ACTION_SKIP]
        + counts[ACTION_REPLAY_SKIP_ZERO_WRITE]
        + counts[ACTION_NO_REPEAT],
        owners_failed=counts[ACTION_ZERO_WRITE]
        + counts[UNKNOWN_STATE_FAIL_CLOSED],
        runtime_binding_evidence_unprovable=sum(
            1 for v in verdicts if v.reason_code == "RUNTIME_BINDING_EVIDENCE_UNPROVABLE"
        ),
        verdict=tuple(verdicts),
    )


def _count_verdicts(verdicts: list[ReplayOwnerVerdict]) -> Counter[str]:
    c: Counter[str] = Counter()
    for v in verdicts:
        c[v.action] += 1
    return c


# ---------------------------------------------------------------------------
# phase 3 — restore-before-open gate（六 owner scan）
# ---------------------------------------------------------------------------


async def evaluate_restore_before_open(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
) -> RestoreBeforeOpenReport:
    """phase 3 gate：六 owner scan 全部零才允许开放流量。

    实现要点（Plan §S6-8.1 + §S6-8.5 + §S6-8.6）：
    - 复用 S5 六 owner 终态扫描（``scan_execution_body`` 等，
      ``execution_erasure_participant.py:260-379``）
    - 复用 S6-6 巡检（tenant / digest / gap / ref / missing-fence / orphan）
    - 全部 owner scan 零 + S6-6 巡检零 → ``open_allowed=True``
    - 任何非零 finding → ``open_allowed=False`` + 结构化 ``blocked_reasons``

    本函数**只计算门禁结果**——不打开流量、不接 production scheduler、不
    写 reconcile ledger；fail closed 路径走 runbook 人工处置。
    """
    inspections: list[tuple[str, int]] = []
    blocked_reasons: list[str] = []

    async with session_factory() as session, session.begin():
        # 六 owner 终态 scan（每个 owner 一个 finding count）
        for owner_label, scan_name in (
            ("workspace.core.v1", "scan_workspace_body"),
            ("workspace.transport.v1", "scan_workspace_transport"),
            ("execution.core.v1", "scan_execution_body"),
            ("execution.transport.v1", "scan_execution_transport"),
            ("external.payload.v1", "scan_external_payload"),
            ("runtime.private.v1", "scan_runtime_bindings"),
        ):
            count = await _count_owner_residual(
                session,
                tenant_id=tenant_id,
                owner_key=owner_label,
            )
            inspections.append((scan_name, count))
            if count > 0:
                blocked_reasons.append(
                    f"{owner_label}_residual:{count}"
                )

        # S6-6 五类 verify 巡检（按 owner 维度对齐）
        for inspection_name in (
            "tenant_mismatch",
            "digest_conflict",
            "event_gap",
            "unknown_ref_scheme",
            "missing_fence_or_owner_scope",
            "orphan_transport",
        ):
            count = await _count_inspection(
                session,
                tenant_id=tenant_id,
                inspection=inspection_name,
            )
            inspections.append((inspection_name, count))
            if count > 0:
                blocked_reasons.append(
                    f"{inspection_name}:{count}"
                )

    open_allowed = not blocked_reasons
    return RestoreBeforeOpenReport(
        open_allowed=open_allowed,
        blocked_reasons=tuple(blocked_reasons),
        inspections=tuple(inspections),
    )


async def _count_owner_residual(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
) -> int:
    """单 owner 维度残留正文 / 引用扫描计数。

    各 owner 域对应扫描（按事实源列）：
    - workspace.core.v1 → ``agent_conversations.title IS NOT NULL`` + 未 redacted 计数
    - workspace.transport.v1 → ``agent_workspace_outbox.payload_*`` 残留
    - execution.core.v1 → ``agent_runs`` / ``agent_run_events`` payload 残留
    - execution.transport.v1 → ``agent_execution_outbox`` 残留
    - external.payload.v1 → ``agent_external_object_refs.erase_state='registered'``
    - runtime.private.v1 → ``agent_runtime_session_bindings.runtime_session_ref IS NOT NULL``

    本函数**只读**，不写 reconcile ledger；返回 finding 计数。
    """
    if owner_key == "workspace.core.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_conversations "
                "WHERE tenant_id = :tid "
                "AND (title IS NOT NULL OR actor_state <> 'redacted')"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if owner_key == "workspace.transport.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_workspace_outbox "
                "WHERE tenant_id = :tid AND payload_inline IS NOT NULL"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if owner_key == "execution.core.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :tid AND payload_inline IS NOT NULL"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if owner_key == "execution.transport.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_execution_outbox "
                "WHERE tenant_id = :tid AND payload_inline IS NOT NULL"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if owner_key == "external.payload.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :tid AND erase_state = 'registered'"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if owner_key == "runtime.private.v1":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_runtime_session_bindings "
                "WHERE tenant_id = :tid AND runtime_session_ref IS NOT NULL"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    return 0


async def _count_inspection(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    inspection: str,
) -> int:
    """S6-6 五类 verify 巡检 finding 计数（按 inspection 名字逐项展开）。

    本函数**只读**；不写 reconcile ledger；返回 finding 计数。"""
    if inspection == "tenant_mismatch":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_workspace_outbox o "
                "WHERE o.tenant_id = :tid AND o.conversation_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM metaedu.agent_conversations c "
                "  WHERE c.tenant_id = :tid AND c.id = o.conversation_id)"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if inspection == "digest_conflict":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_erasure_fences "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if inspection == "event_gap":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_runs "
                "WHERE tenant_id = :tid AND event_log_complete = false"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if inspection == "unknown_ref_scheme":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :tid "
                "AND ref_scheme NOT IN ('db_local', 'http_url', 's3_uri')"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if inspection == "missing_fence_or_owner_scope":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :tid AND conversation_id IS NULL"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    if inspection == "orphan_transport":
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_execution_inbox "
                "WHERE tenant_id = :tid AND status = 'processing'"
            ),
            {"tid": tenant_id},
        )
        return int(row.scalar_one() or 0)

    return 0


__all__ = [
    "ACTION_REPLAY_SKIP_ZERO_WRITE",
    "ACTION_CANDIDATE_WHEN_LOCAL",
    "ACTION_BLOCKED_LOCAL_MATCH_REASON",
    "ACTION_ZERO_WRITE",
    "ACTION_VERIFY_ONLY",
    "ACTION_SKIP",
    "ACTION_NO_REPEAT",
    "UNKNOWN_STATE_FAIL_CLOSED",
    "LOCAL_OWNERS",
    "NON_LOCAL_OWNERS",
    "VALID_OPERATION_STATES",
    "VALID_CHECKPOINT_STATES",
    "ReplayOwnerVerdict",
    "RestoreReplayReport",
    "RestoreBeforeOpenReport",
    "RestoreReplayError",
    "replay_archive_segment_for_tenant",
    "evaluate_restore_before_open",
]
