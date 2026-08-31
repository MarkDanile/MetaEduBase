# ruff: noqa: E501
"""R1-S6-I3-D D2 Round-3 P1 收口：restore replay executor + restore-before-open gate。

R1-S6-I3-D D2 Round-3 P1 收口（普通新 commit；按本任务卡 8 项要求）：

1. **六元组 ACK**：
   - LIVE ack_digest 必须严格 ``lowercase 64-hex``（应用层门禁；与 migration 034
     ``ck_agent_purge_owner_ack`` 长度约束兼容但更严）。
   - archive/live 均为 ``state=acked`` 时必须 ``archive.ack_digest == live.ack_digest``
     （逐值相等；任何 mismatch → ``ACK_DIGEST_MISMATCH`` 整体零写 fail closed）。
   - 新增同 state=acked、两个不同合法 64-hex digest 的真实 PG 负例。
   - M-D2-10 保留编号（purge_revision 对账） + 新增独立 mutation ACK equality（M-D2-12）。

2. **Archive facts 来源严格**：
   - archive operation/checkpoint 路由 + fence 字段**必须**从 ``manifest.records[operation/checkpoint]``
     提取；缺失即具名 ``ARCHIVE_FACTS_MISSING`` fail closed。
   - ``ValidatedFact.archive_*`` **禁止**用 LIVE 值回填——所有 archive_* 来自 archive record / OwnerFacts。
   - pass B 用保存的 archive facts 做 TOCTOU 重验（已存不重新读 archive）。

3. **Atomic rollback 真实断言**：
   - owner A 调真实 participant 完成写入 + owner B 在 pass B 内失败 → 新 session 断言
     A/B checkpoint / fence / 正文全部保持原值。
   - 禁止用 pass-A revision drift 冒充 pass-B rollback——两测试**独立**。

4. **Report / Gate 统一错误接口**：
   - 真实 pass-A drift / pass-B TOCTOU / participant failure 均能形成
     ``RestoreReplayReport.error`` 非空（gate 必消费 fail-closed report）。
   - catch 位于 ``async with session.begin()`` 之外——先确保自动 rollback，再让异常
     冒泡到 caller 转化为 report。
   - 删除恒零计数（has_blocking_finding 需接真实 report）。
   - 新增端到端 replay→report→gate 测试（禁止只测手工 report）。

5. **幂等**：
   - 同一 committed segment 连续执行两次。
   - 第二次 LIVE state 已是 terminal（acked / completed / cancelled / failed）→
     ``NO_REPEAT``，**不**调 participant 公共入口。
   - 仅允许有完整 terminal evidence 的单向推进；其他 archive / live drift 仍 fail closed。

6. **Non-local 路由**：
   - operation/checkpoint **全局冻结矩阵**先于 owner-specific 处理（禁止按 owner
     跳过全局矩阵）。
   - external.payload.v1 和 runtime.private.v1 分别补齐 6×5 判别（30 scenarios × 2 owner）。
   - scheduled / cancelled / failed / acked **不得**统一降级为 non_local_blocked
     （按矩阵返回 REPLAY_SKIP_ZERO_WRITE / SKIP / ZERO_WRITE / NO_REPEAT）。

7. **External verify-only**：
   - 复用既有事实源（archive external_ref + live agent_external_object_refs +
     live final scan）验证 archived receipt/ACK；**不发** adapter 请求、**不发明**新 digest 算法。
   - 区分 ``external_verified``（archive.receipt_digest == live.receipt_digest + state=erased）
     vs ``external_verification_failed``（drift）。
   - 只有 ``external_verification_failed`` 阻断 gate；``runtime_proof_c_present`` 继续强制 closed。

8. **D1a field 表修正**：
   - ``docs/02-delivery-plans/02-plans/2026-08-29-r1-s6-i3-d-d2-r1p0-audit.md`` §1.1 表按
     ``app/composition/s6i3_ledger_snapshot.py`` 实际 SELECT 列白名单修正。
   - 撤销「Round-2 P0/P1 已全部闭合」表述。

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
import re
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

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
    RECORD_KIND_CHECKPOINT,
    RECORD_KIND_EXTERNAL_REF,
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
# local owner participant 返回 blocked=True（真实 outcome，非异常）→ 保留不清除
ACTION_BLOCKED_KEPT = "blocked_kept"

# non-local owner（external / runtime）实际执行结果
ACTION_NON_LOCAL_BLOCKED = "non_local_blocked"  # 阻断，runbook 人工
ACTION_EXTERNAL_VERIFIED = "external_verified"  # external.payload.v1 + completed + receipt match
ACTION_EXTERNAL_VERIFICATION_FAILED = "external_verification_failed"  # drift
ACTION_RUNTIME_BINDING_UNPROVABLE = "runtime_binding_evidence_unprovable"  # runtime + completed
ACTION_RUNTIME_BLOCKED = "runtime_blocked"  # runtime + non-completed（无 adapter）

# external.payload.v1 + completed → 验证 receipt + final scan（待 caller 决断）
ACTION_EXTERNAL_VERIFY_ONLY = "external_verify_only"

# 六元组 / operation fence drift
ACTION_FACT_DRIFT_FAIL_CLOSED = "fact_drift_fail_closed"

# 路由矩阵默认 action（按 6×5 状态）
ACTION_REPLAY_SKIP_ZERO_WRITE = "replay_skip_zero_write"  # scheduled
ACTION_ZERO_WRITE = "zero_write"  # failed
ACTION_VERIFY_ONLY = "verify_only"  # completed（local owner）
ACTION_SKIP = "skip"  # cancelled
ACTION_NO_REPEAT = "no_repeat"  # terminal state 不重复推进

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

VALID_OPERATION_STATES: frozenset[str] = frozenset({
    "scheduled", "running", "blocked", "failed", "completed", "cancelled",
})
VALID_CHECKPOINT_STATES: frozenset[str] = frozenset({
    "pending", "erasing", "blocked", "failed", "acked",
})

# 6 operation × 5 checkpoint = 30 routing scenarios（frozen 全局矩阵）
# 按 owner class 映射：local owner 走 candidate（即使 blocked 也尝试调 participant，
# 失败由 participant 内部 fence 抛错）；non-local owner 走 blocked verdict（无 adapter）。
_OPERATION_ROUTING: dict[str, dict[str, str]] = {
    "scheduled": {
        "pending": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "erasing": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "blocked": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "failed": ACTION_REPLAY_SKIP_ZERO_WRITE,
        "acked": ACTION_REPLAY_SKIP_ZERO_WRITE,
    },
    "running": {
        "pending": ACTION_LOCAL_CLEARED,
        "erasing": ACTION_LOCAL_CLEARED,
        "blocked": ACTION_LOCAL_CLEARED,
        "failed": ACTION_ZERO_WRITE,
        "acked": ACTION_NO_REPEAT,
    },
    "blocked": {
        "pending": ACTION_LOCAL_CLEARED,
        "erasing": ACTION_LOCAL_CLEARED,
        "blocked": ACTION_LOCAL_CLEARED,
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

# 64-hex lowercase 严格校验（应用层门禁；与 migration 034 ck_agent_purge_owner_ack 兼容）
_HEX_LOWER_64_RE = re.compile(r"^[0-9a-f]{64}$")


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
class ValidatedFact:
    """pass A 验证后的 (operation, checkpoint) 行字段。

    archive_* 字段**全部**来自 archive record / OwnerFacts（**禁止**用 LIVE 值回填）。
    """

    operation_id: uuid.UUID
    archive_operation_state: str
    archive_purge_revision: int
    archive_revision: int
    archive_lease_epoch: int
    archive_hold_revision: int
    archive_registry_digest: str
    archive_retention_policy_digest: str
    conversation_id: uuid.UUID
    checkpoint_id: uuid.UUID
    archive_checkpoint_state: str
    archive_owner_key: str
    archive_owner_version: int
    archive_capability_digest: str
    archive_ack_digest: str | None  # state=acked 时必非 NULL 64-hex lowercase


@dataclass(frozen=True, slots=True)
class RestoreReplayReport:
    """一次 replay 的聚合计数（unified error interface for gate）。

    counts 按**实际执行结果**计算（不按 routing action 猜测）。
    Gate 必须从本 report 内部 derive blocking verdict（error / toctou_drift / fact drift
    / runtime unprovable / external verification failed 全部自动阻断）。
    """

    operations_total: int = 0
    owners_total: int = 0
    owners_local_cleared: int = 0
    owners_blocked_kept: int = 0  # local owner participant blocked=True（保留不清除）
    owners_non_local_blocked: int = 0
    owners_verify_only: int = 0
    owners_skipped: int = 0
    owners_fact_drift: int = 0
    owners_no_repeat: int = 0
    runtime_binding_evidence_unprovable: int = 0
    external_verified: int = 0
    external_verification_failed: int = 0
    external_verify_only: int = 0  # legacy alias for backward compat
    verdict: tuple[ReplayOwnerVerdict, ...] = ()
    error: str | None = None  # archive read / pass A / pass B 任何失败 → gate 必消费
    toctou_drift: int = 0
    pass_a_drift: int = 0
    participant_failures: int = 0

    def has_blocking_finding(self) -> bool:
        """Gate 据此判定是否阻断（任何 blocking 项 → closed）。"""
        if self.error is not None:
            return True
        if self.pass_a_drift > 0:
            return True
        if self.toctou_drift > 0:
            return True
        if self.owners_fact_drift > 0:
            return True
        if self.owners_blocked_kept > 0:
            return True
        if self.runtime_binding_evidence_unprovable > 0:
            return True
        if self.external_verification_failed > 0:
            return True
        return self.owners_non_local_blocked > 0


@dataclass(frozen=True, slots=True)
class RestoreBeforeOpenReport:
    """phase 3 gate 结果（**强制**消费 RestoreReplayReport）。"""

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

    入口 = ``asyncio.to_thread(find_committed_tip)`` + ``CommitMarker.from_bytes`` +
    ``fetch_segment_bytes``。无 tip / ForkDetectedError / GenerationRegressionError →
    抛 ``RestoreReplayError``（DB tx 开始前）。
    """
    tenant_str = str(tenant_id)
    tip = await asyncio.to_thread(find_committed_tip, sink, tenant_id=tenant_str)
    if tip is None:
        raise RestoreReplayError(
            "ARCHIVE_TIP_NOT_FOUND", detail={"tenant_id": tenant_str},
        )
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
# pass A — 六元组 + operation fence 全字段对账（DB tx 外；零写）
# ---------------------------------------------------------------------------


_HEX_LOWER_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _assert_64hex_lowercase(value: Any, *, field: str) -> str:
    """严格 64-hex lowercase 校验。"""
    if not isinstance(value, str) or not _HEX_LOWER_64_RE.match(value):
        raise RestoreReplayError(
            "ACK_DIGEST_FORMAT_INVALID",
            detail={"field": field, "reason": "64hex_lowercase_required", "value": value},
        )
    return value


# ---------------------------------------------------------------------------
# archive facts 严格类型 helpers（Round-6：禁止 str()/int() 隐式转换）
#
# 每种类型一个明确 helper；缺失字段与类型错误分别返回稳定的具名错误码：
# - 缺失 → ``missing_code``（调用方按 operation/checkpoint/external-ref 传
#   ``ARCHIVE_FACTS_FIELD_MISSING`` 等）
# - 类型不符 → ``ARCHIVE_FACTS_TYPE_INVALID``（``field`` 携带 ``operation.revision``
#   等定位符）
# 所有解析异常在此归一化为 ``RestoreReplayError``，**绝不**泄漏 ValueError/TypeError。
# ---------------------------------------------------------------------------


def _require_field(
    record: Mapping[str, Any], key: str, *, missing_code: str
) -> Any:
    """archive record 必需字段存在性检查；缺失/None → 具名 ``missing_code`` fail closed。"""
    if key not in record or record[key] is None:
        raise RestoreReplayError(
            missing_code,
            detail={"missing_field": key},
        )
    return record[key]


def _require_strict_int(
    record: Mapping[str, Any], key: str, *, missing_code: str, field: str
) -> int:
    """strict int（排除 bool；**禁止** ``int()`` 隐式转换）。"""
    raw = _require_field(record, key, missing_code=missing_code)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={"field": field, "expected_type": "int"},
        )
    return raw


def _require_str(
    record: Mapping[str, Any], key: str, *, missing_code: str, field: str
) -> str:
    """严格 string（**禁止** ``str()`` 隐式转换）。"""
    raw = _require_field(record, key, missing_code=missing_code)
    if not isinstance(raw, str):
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={"field": field, "expected_type": "str"},
        )
    return raw


def _require_canonical_uuid(
    record: Mapping[str, Any], key: str, *, missing_code: str, field: str
) -> uuid.UUID:
    """canonical UUID（**严格**：raw 必须本就是 ``str`` 且 ``str(uuid.UUID(raw)) == raw``）。

    逐一 fail closed（具名 ``ARCHIVE_FACTS_TYPE_INVALID``，**不**泄漏 ValueError）：
    - 非 ``str``（含 ``uuid.UUID`` 对象 / bytes / int）→ 拒绝（**禁止** ``str()`` 隐式转换）；
    - 非法字符串（``uuid.UUID`` 解析失败）→ 拒绝；
    - 非 canonical 形态（大写 / 无连字符 / 带花括号等——``str(uuid.UUID(raw)) != raw``）→ 拒绝。
    """
    raw = _require_field(record, key, missing_code=missing_code)
    if not isinstance(raw, str):
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={"field": field, "expected_type": "canonical_uuid_str"},
        )
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, TypeError, AttributeError):
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={"field": field, "expected_type": "canonical_uuid_str"},
        ) from None
    if str(parsed) != raw:
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={
                "field": field,
                "expected_type": "canonical_uuid_str",
                "reason": "not_lowercase_hyphenated_canonical",
            },
        )
    return parsed


def _require_64hex_lower(
    record: Mapping[str, Any], key: str, *, missing_code: str, field: str
) -> str:
    """严格 lowercase 64-hex（应用层门禁）。"""
    raw = _require_str(record, key, missing_code=missing_code, field=field)
    if not _HEX_LOWER_64_RE.match(raw):
        raise RestoreReplayError(
            "ARCHIVE_FACTS_TYPE_INVALID",
            detail={"field": field, "expected_type": "64hex_lowercase"},
        )
    return raw


def _optional_64hex_lower(
    record: Mapping[str, Any], key: str, *, field: str
) -> str | None:
    """可选 lowercase 64-hex（``None`` 允许；非 None 必须严格格式，否则 TYPE_INVALID）。"""
    if key not in record or record[key] is None:
        return None
    return _require_64hex_lower(
        record, key, missing_code="ARCHIVE_FACTS_FIELD_MISSING", field=field
    )


async def _read_operation_archive_facts(
    session: AsyncSession,
    *,
    manifest: Manifest,
    operation_id: str,
) -> Mapping[str, Any]:
    """从 archive manifest 提取 operation 行的 archive facts。

    archive operation **必须**存在；缺失即 ``ARCHIVE_FACTS_MISSING`` fail closed
    （禁止回填 LIVE 值）。
    """
    op_records = manifest.records.get(RECORD_KIND_OPERATION, ())
    for r in op_records:
        if str(r.fields.get("id")) == operation_id:
            return r.fields
    raise RestoreReplayError(
        "ARCHIVE_FACTS_OPERATION_MISSING",
        detail={"operation_id": operation_id},
    )


def _read_checkpoint_archive_facts(
    manifest: Manifest, *, operation_id: str, owner_key: str
) -> Mapping[str, Any] | None:
    """从 archive manifest 提取 checkpoint 行的 archive facts（不查 DB；仅 archive）。"""
    cp_records = manifest.records.get(RECORD_KIND_CHECKPOINT, ())
    for r in cp_records:
        if (
            str(r.fields.get("purge_operation_id")) == operation_id
            and r.fields.get("owner_key") == owner_key
        ):
            return r.fields
    return None


def _bind_archive_external_ref(
    manifest: Manifest,
    *,
    conversation_id: uuid.UUID,
    owner_key: str = "external.payload.v1",
) -> Mapping[str, Any]:
    """统一 archive external-ref binder（Round-6）：按 ``conversation_id`` + ``owner_key``
    **精确绑定唯一一条** archive external_ref record 并严格解析。

    - **恰好一条**：0 条 → ``EXTERNAL_ARCHIVE_MISSING``；≥2 条 → ``EXTERNAL_ARCHIVE_DUPLICATE``；
      conversation/owner 不匹配 → ``EXTERNAL_ARCHIVE_MISSING``（无绑定）。
    - **严格解析**（禁止 ``str()``/``int()`` 隐式转换；缺失 → ``ARCHIVE_FACTS_FIELD_MISSING``；
      类型/格式不符 → ``ARCHIVE_FACTS_TYPE_INVALID``）：``id``/``conversation_id``（canonical
      UUID）、``owner_key``（string）、``receipt_digest``（lowercase 64-hex）。
    - **禁止**回退任意 LIVE row 冒充 archive 证据。
    """
    cid_str = str(conversation_id)
    er_records = manifest.records.get(RECORD_KIND_EXTERNAL_REF, ())
    matches: list[Mapping[str, Any]] = []
    for r in er_records:
        rk_raw = r.fields.get("owner_key")
        # 非本 owner → 非候选，跳过（不参与绑定）。
        if rk_raw != owner_key:
            continue
        # 本 owner 的候选 → conversation_id 必须严格 canonical UUID（malformed 候选
        # **禁止**静默跳过冒充"无绑定"/"单条"——fail closed 为 ARCHIVE_FACTS_TYPE_INVALID）。
        rc = _require_canonical_uuid(
            r.fields,
            "conversation_id",
            missing_code="ARCHIVE_FACTS_FIELD_MISSING",
            field="external_ref.conversation_id",
        )
        if str(rc) == cid_str:
            matches.append(r.fields)

    if not matches:
        raise RestoreReplayError(
            "EXTERNAL_ARCHIVE_MISSING",
            detail={
                "conversation_id": cid_str,
                "owner_key": owner_key,
                "reason": "no_archive_external_ref_bound",
            },
        )
    if len(matches) > 1:
        raise RestoreReplayError(
            "EXTERNAL_ARCHIVE_DUPLICATE",
            detail={
                "conversation_id": cid_str,
                "owner_key": owner_key,
                "count": len(matches),
                "reason": "duplicate_archive_external_ref",
            },
        )

    record = matches[0]
    _missing_code = "ARCHIVE_FACTS_FIELD_MISSING"
    # 严格解析必需字段（不此处使用返回值——仅触发 fail-closed 校验；绑定本身已确认）
    parsed_id = _require_canonical_uuid(record, "id", missing_code=_missing_code, field="external_ref.id")
    parsed_cid = _require_canonical_uuid(record, "conversation_id", missing_code=_missing_code, field="external_ref.conversation_id")
    parsed_owner = _require_str(record, "owner_key", missing_code=_missing_code, field="external_ref.owner_key")
    parsed_receipt = _require_64hex_lower(record, "receipt_digest", missing_code=_missing_code, field="external_ref.receipt_digest")
    # 绑定的 record 必须与请求精确一致（防御性二次确认）
    if str(parsed_cid) != cid_str or parsed_owner != owner_key:
        raise RestoreReplayError(
            "EXTERNAL_ARCHIVE_BINDING_MISMATCH",
            detail={
                "conversation_id": cid_str,
                "owner_key": owner_key,
                "record_conversation_id": str(parsed_cid),
                "record_owner_key": parsed_owner,
            },
        )
    return {
        "id": parsed_id,
        "conversation_id": parsed_cid,
        "owner_key": parsed_owner,
        "receipt_digest": parsed_receipt,
    }


async def _validate_pass_a(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fact: OwnerFacts,
    archive_op_record: Mapping[str, Any],
    archive_cp_record: Mapping[str, Any] | None,
) -> ValidatedFact:
    """pass A：六元组 + operation fence 全字段对账（**绝对零写**；DB tx 外）。

    archive_* 字段**全部**从 archive record / OwnerFacts 提取（禁止 LIVE 值回填）。
    任一 drift / missing → 抛 ``RestoreReplayError``（caller 不 catch → pass B 不进入）。
    """
    op_id = uuid.UUID(fact.operation_id)

    # 1. operation archive facts 必须存在（禁止 LIVE 回填）
    if not archive_op_record:
        raise RestoreReplayError(
            "ARCHIVE_FACTS_OPERATION_MISSING",
            detail={"operation_id": fact.operation_id},
        )
    # 严格 6 元组 / 5 operation 字段对账（**全部**使用 archive facts；禁止 str()/int()
    # 隐式转换——经明确类型 helper；缺失 → ARCHIVE_FACTS_FIELD_MISSING；类型不符 →
    # ARCHIVE_FACTS_TYPE_INVALID）
    _missing_code = "ARCHIVE_FACTS_FIELD_MISSING"
    archive_op_state = _require_str(
        archive_op_record, "state", missing_code=_missing_code, field="operation.state"
    )
    archive_op_rev = _require_strict_int(
        archive_op_record, "revision", missing_code=_missing_code, field="operation.revision"
    )
    archive_purge_rev = _require_strict_int(
        archive_op_record, "purge_revision", missing_code=_missing_code, field="operation.purge_revision"
    )
    archive_lease = _require_strict_int(
        archive_op_record, "lease_epoch", missing_code=_missing_code, field="operation.lease_epoch"
    )
    archive_hold = _require_strict_int(
        archive_op_record, "hold_revision_snapshot", missing_code=_missing_code, field="operation.hold_revision_snapshot"
    )
    archive_registry = _require_str(
        archive_op_record, "registry_digest", missing_code=_missing_code, field="operation.registry_digest"
    )
    archive_rpd = _require_str(
        archive_op_record, "retention_policy_digest", missing_code=_missing_code, field="operation.retention_policy_digest"
    )
    conversation_id = _require_canonical_uuid(
        archive_op_record, "conversation_id", missing_code=_missing_code, field="operation.conversation_id"
    )

    # 2. checkpoint archive facts 必须存在
    if not archive_cp_record:
        raise RestoreReplayError(
            "ARCHIVE_FACTS_CHECKPOINT_MISSING",
            detail={
                "operation_id": fact.operation_id,
                "owner_key": fact.owner_key,
            },
        )
    archive_cp_state = _require_str(
        archive_cp_record, "state", missing_code=_missing_code, field="checkpoint.state"
    )
    archive_cp_owner_key = _require_str(
        archive_cp_record, "owner_key", missing_code=_missing_code, field="checkpoint.owner_key"
    )
    archive_owner_version = _require_strict_int(
        archive_cp_record, "owner_version", missing_code=_missing_code, field="checkpoint.owner_version"
    )
    archive_capability = _require_str(
        archive_cp_record, "capability_digest", missing_code=_missing_code, field="checkpoint.capability_digest"
    )
    archive_ack = _optional_64hex_lower(archive_cp_record, "ack_digest", field="checkpoint.ack_digest")
    archive_checkpoint_id = _require_canonical_uuid(
        archive_cp_record, "id", missing_code=_missing_code, field="checkpoint.id"
    )

    # 3. LIVE 读 operation / checkpoint 用于 drift 检测（不写入任何 archive_*）
    op_row = await _load_operation_row(
        session, tenant_id=tenant_id, operation_id=op_id
    )
    if op_row is None:
        raise RestoreReplayError(
            "FACT_DRIFT_OPERATION_MISSING",
            detail={"operation_id": fact.operation_id},
        )
    cp_row = await _load_checkpoint_row(
        session,
        tenant_id=tenant_id,
        purge_operation_id=op_id,
        owner_key=archive_cp_owner_key,
    )
    if cp_row is None:
        raise RestoreReplayError(
            "FACT_DRIFT_CHECKPOINT_MISSING",
            detail={
                "operation_id": fact.operation_id,
                "owner_key": archive_cp_owner_key,
            },
        )

    drift_fields: list[str] = []

    # 4. 5 operation 字段逐一对账（**禁止**用 LIVE 值回填 archive_*；反向检查）
    if str(op_row["state"]) != archive_op_state:
        drift_fields.append("operation.state")
    if int(op_row["revision"]) != archive_op_rev:
        drift_fields.append("operation.revision")
    if int(op_row["purge_revision"]) != archive_purge_rev:
        drift_fields.append("operation.purge_revision")
    if int(op_row["lease_epoch"]) != archive_lease:
        drift_fields.append("operation.lease_epoch")
    if int(op_row.get("hold_revision_snapshot") or 0) != archive_hold:
        drift_fields.append("operation.hold_revision_snapshot")

    # 5. 6 元组 + ack_digest 严格 lowercase 64-hex 校验
    if cp_row["owner_key"] != archive_cp_owner_key:
        drift_fields.append("checkpoint.owner_key")
    if cp_row["capability_digest"] != archive_capability:
        drift_fields.append("checkpoint.capability_digest")
    if int(cp_row["owner_version"]) != archive_owner_version:
        drift_fields.append("checkpoint.owner_version")
    # checkpoint.state 单向终态转换特例：archive=erasing/pending + LIVE=acked
    # 是完整 terminal evidence 单向推进，**禁止**判定为 drift。
    # 其他 drift（**任何**其他无证据 cp_state mismatch / owner_version / 等）仍 fail closed。
    is_terminal_single_direction = (
        archive_cp_state in ("erasing", "pending")
        and cp_row["state"] == "acked"
    )
    if cp_row["state"] != archive_cp_state and not is_terminal_single_direction:
        drift_fields.append("checkpoint.state")

    # 6. ack_digest：state=acked 时必须严格 64-hex lowercase（应用层门禁；与 migration 034
    #    ck_agent_purge_owner_ack 长度约束兼容但更严）
    if archive_cp_state == "acked":
        if archive_ack is None:
            drift_fields.append("checkpoint.ack_digest_missing")
        else:
            try:
                _assert_64hex_lowercase(archive_ack, field="checkpoint.ack_digest")
            except RestoreReplayError as exc:
                drift_fields.append(f"archive.{exc.code}")
        if cp_row["state"] == "acked":
            live_ack = cp_row.get("ack_digest")
            if live_ack is None:
                drift_fields.append("checkpoint.live_ack_digest_missing")
            else:
                try:
                    _assert_64hex_lowercase(live_ack, field="checkpoint.live_ack_digest")
                except RestoreReplayError as exc:
                    drift_fields.append(f"live.{exc.code}")
            # archive == live ack_digest 严格相等
            if (
                archive_ack is not None
                and live_ack is not None
                and archive_ack == live_ack
                and archive_cp_state == "acked"
            ):
                pass  # 严格相等 → OK
            elif (
                archive_ack is not None
                and live_ack is not None
                and archive_ack != live_ack
                and archive_cp_state == "acked"
            ):
                drift_fields.append("checkpoint.ack_digest_archive_live_mismatch")

    if drift_fields:
        raise RestoreReplayError(
            "FACT_DRIFT_FIELDS",
            detail={
                "operation_id": fact.operation_id,
                "owner_key": archive_cp_owner_key,
                "drift_fields": tuple(drift_fields),
            },
        )

    return ValidatedFact(
        operation_id=op_id,
        archive_operation_state=archive_op_state,
        archive_purge_revision=archive_purge_rev,
        archive_revision=archive_op_rev,
        archive_lease_epoch=archive_lease,
        archive_hold_revision=archive_hold,
        archive_registry_digest=archive_registry,
        archive_retention_policy_digest=archive_rpd,
        conversation_id=conversation_id,
        checkpoint_id=archive_checkpoint_id,
        archive_checkpoint_state=archive_cp_state,
        archive_owner_key=archive_cp_owner_key,
        archive_owner_version=archive_owner_version,
        archive_capability_digest=archive_capability,
        archive_ack_digest=archive_ack,
    )


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


# ---------------------------------------------------------------------------
# 路由决策（6×5 全局矩阵先；owner-specific 后）
# ---------------------------------------------------------------------------


def _route_global_matrix(
    *, operation_state: str, checkpoint_state: str
) -> tuple[str, str | None]:
    """6×5 全局冻结矩阵（先于 owner-specific 处理）。

    任何 scheduled / failed / cancelled 状态 → REPLAY_SKIP_ZERO_WRITE / ZERO_WRITE / SKIP
    （**禁止**按 owner 统一降级为 non_local_blocked）。
    """
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


def _route_non_local(
    *, owner_key: str, operation_state: str, checkpoint_state: str
) -> tuple[str, str | None]:
    """non-local owner 特定路由（在 6×5 全局矩阵之后）。"""
    if owner_key == "runtime.private.v1":
        if operation_state == "completed":
            return (
                ACTION_RUNTIME_BINDING_UNPROVABLE,
                "RUNTIME_BINDING_EVIDENCE_UNPROVABLE",
            )
        # runtime + 非 completed → blocked verdict（无 adapter）
        return (
            ACTION_RUNTIME_BLOCKED,
            "runtime_no_adapter",
        )
    # external.payload.v1
    if operation_state == "completed":
        # external payload verify-only：不在此处做 receipt 验证（由 caller 调
        # _verify_external_receipt_and_scan 决定 verified vs failed）
        return (
            ACTION_EXTERNAL_VERIFY_ONLY,
            "external_verify_only_awaiting_receipt_check",
        )
    return (
        ACTION_NON_LOCAL_BLOCKED,
        "non_local_no_adapter",
    )


# ---------------------------------------------------------------------------
# external.payload.v1 验证：archive receipt + LIVE final scan（不发 adapter；不算新 digest）
# ---------------------------------------------------------------------------


async def _verify_external_receipt(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
    manifest: Manifest,
) -> bool:
    """external.payload.v1 verify-only：统一 binder 绑定唯一 archive record + receipt
    精确匹配 + LIVE state=erased + **final scan**（复用 ``build_scan_providers`` 的
    external.payload.v1 谓词，要求该 conversation residual total == 0）。

    - **实际调用统一 binder** ``_bind_archive_external_ref``（恰好一条 + 严格解析）；
      binder 失败（0 条 / ≥2 条 / 错 conversation/owner / 解析失败）→ 转换为
      ``EXTERNAL_VERIFICATION_FAILED``（reason 携带具体 binder code）。
    - **禁止**回退任意 LIVE row 冒充 archive 证据（必须按 archive ``id`` 精确匹配 LIVE 行）。
    - **禁止**发 adapter 请求；**不**发明新 digest 算法。
    - 返回 ``True`` = 绑定 + receipt 匹配 + state=erased + final scan total==0；
      否则抛 ``RestoreReplayError("EXTERNAL_VERIFICATION_FAILED", reason=...)``（具名）。
    """
    cid = validated.conversation_id

    def _fail(reason: str) -> RestoreReplayError:
        return RestoreReplayError(
            "EXTERNAL_VERIFICATION_FAILED",
            detail={
                "operation_id": str(validated.operation_id),
                "owner_key": validated.archive_owner_key,
                "conversation_id": str(cid),
                "reason": reason,
            },
        )

    # 统一 binder：恰好一条 + 严格解析（id / conversation_id / owner_key / receipt_digest）。
    # binder 抛具名错（EXTERNAL_ARCHIVE_MISSING / EXTERNAL_ARCHIVE_DUPLICATE /
    # ARCHIVE_FACTS_*）→ 转换为 EXTERNAL_VERIFICATION_FAILED（reason=具体 code）。
    try:
        archive_external_record = _bind_archive_external_ref(
            manifest,
            conversation_id=cid,
            owner_key="external.payload.v1",
        )
    except RestoreReplayError as exc:
        raise _fail(exc.code) from exc

    # archive 端严格字段（binder 已校验；此处取用对账）
    archive_eid = archive_external_record["id"]
    archive_receipt = archive_external_record["receipt_digest"]

    # 按 archive id + conversation_id + owner_key 精确绑定 LIVE 行（**禁止**任意 LIVE row）
    row = await session.execute(
        text(
            "SELECT receipt_digest, erase_state "
            "FROM metaedu.agent_external_object_refs "
            "WHERE tenant_id = :tid AND owner_key = 'external.payload.v1' "
            "AND conversation_id = :cid AND id = :eid"
        ),
        {"tid": tenant_id, "cid": str(cid), "eid": str(archive_eid)},
    )
    m = row.mappings().first()
    if m is None:
        raise _fail("external_live_row_missing")

    # receipt 精确匹配 + LIVE erase_state == erased
    if m["receipt_digest"] != archive_receipt:
        raise _fail("external_receipt_mismatch")
    if m["erase_state"] != "erased":
        raise _fail("external_state_not_erased")

    # final scan：复用 build_scan_providers 冻结谓词；该 conversation external residual
    # 必须 total == 0（registered 残留 → 证据不完整 → fail closed）
    from app.composition.transactional_projection_coordinator import (
        build_scan_providers,
    )

    scan_fn = build_scan_providers(session).get("external.payload.v1")
    if scan_fn is None:
        raise _fail("external_scan_provider_missing")
    scan_result = await scan_fn(tenant_id=tenant_id, conversation_id=cid)
    # scan result 必须严格携带非负 int ``total``——缺失 / 类型错误（含 bool）/ 负数
    # 一律 fail closed（**禁止** ``getattr(..., 0)`` / ``int()`` 默认化冒充 clean）。
    scan_total = getattr(scan_result, "total", None)
    if not isinstance(scan_total, int) or isinstance(scan_total, bool) or scan_total < 0:
        raise _fail("external_scan_total_invalid")
    if scan_total != 0:
        raise _fail(f"external_final_scan_residual:{scan_total}")

    return True


# ---------------------------------------------------------------------------
# pass B — 单一 exclusive maintenance tx；调 participant 公共入口
# ---------------------------------------------------------------------------


async def _toctou_reverify_pass_b(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
) -> bool:
    """pass B：在 exclusive tx 内逐字段重读 LIVE state + 对比 archive facts（TOCTOU 防护）。

    **所有**路径（含 NO_REPEAT）都必须调用本函数——**禁止**只读 ``checkpoint.state``
    后直接 continue。

    全字段对账（operation 8 字段 + checkpoint 6 元组）；每个字段 drift 使用稳定、可
    定位的错误码/字段名。LIVE ≠ archive → 抛 ``RestoreReplayError("TOCTOU_DRIFT_*")``
    → caller 不 catch → 整事务 rollback。

    **单一快照语义（Round-7）**：checkpoint.state 只在本函数内读取**一次**（同一
    ``cp_row`` 快照）。terminal evidence（``archive_checkpoint_state ∈ {pending, erasing}``
    + LIVE ``acked`` 的合法单向终态推进）在**该同一快照**上判定并作为返回值交给 caller——
    caller 据此决定 NO_REPEAT，**禁止**在调用本函数前再单独读一次 checkpoint.state
    （消除双读 TOCTOU 窗口）。

    Returns:
        ``True`` ⟺ 本次为合法单向终态推进（terminal evidence，且**无任何**字段 drift）——
        caller 应据此登记 ``NO_REPEAT``（**不**调 participant）。``False`` = 非终态推进
        （正常走矩阵路由）。任何字段 drift → 抛错（**不**返回）。

    terminal evidence 生效时**必须** LIVE ``ack_digest`` 为 lowercase 64-hex（否则仍 drift）；
    其余**所有**字段（operation 8 字段 + checkpoint 其余 5 字段）任何 drift 均失败。
    """
    op_row = await _load_operation_row(
        session, tenant_id=tenant_id, operation_id=validated.operation_id
    )
    if op_row is None:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_OPERATION_MISSING",
            detail={"operation_id": str(validated.operation_id)},
        )

    drift_fields: list[str] = []

    # operation fence 全字段对账（**禁止**用 LIVE 值回填 archive_*；反向检查）
    if str(op_row["state"]) != validated.archive_operation_state:
        drift_fields.append("operation.state")
    if int(op_row["revision"]) != validated.archive_revision:
        drift_fields.append("operation.revision")
    if int(op_row["purge_revision"]) != validated.archive_purge_revision:
        drift_fields.append("operation.purge_revision")
    if int(op_row["lease_epoch"]) != validated.archive_lease_epoch:
        drift_fields.append("operation.lease_epoch")
    if int(op_row.get("hold_revision_snapshot") or 0) != validated.archive_hold_revision:
        drift_fields.append("operation.hold_revision_snapshot")
    if str(op_row.get("registry_digest") or "") != validated.archive_registry_digest:
        drift_fields.append("operation.registry_digest")
    if str(op_row.get("retention_policy_digest") or "") != validated.archive_retention_policy_digest:
        drift_fields.append("operation.retention_policy_digest")
    if str(op_row.get("conversation_id") or "") != str(validated.conversation_id):
        drift_fields.append("operation.conversation_id")

    # checkpoint 六元组对账
    cp_row = await _load_checkpoint_row(
        session,
        tenant_id=tenant_id,
        purge_operation_id=validated.operation_id,
        owner_key=validated.archive_owner_key,
    )
    if cp_row is None:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_CHECKPOINT_MISSING",
            detail={
                "operation_id": str(validated.operation_id),
                "owner_key": validated.archive_owner_key,
            },
        )

    # checkpoint.state：唯一例外 = archive ∈ {pending, erasing} + LIVE = acked
    # （单向终态推进），在**同一 cp_row 快照**上判定；其余 state mismatch 均 drift。
    live_cp_state = str(cp_row["state"])
    is_terminal_single_direction = (
        validated.archive_checkpoint_state in ("erasing", "pending")
        and live_cp_state == "acked"
    )
    if live_cp_state != validated.archive_checkpoint_state and not is_terminal_single_direction:
        drift_fields.append("checkpoint.state")

    if str(cp_row["owner_key"]) != validated.archive_owner_key:
        drift_fields.append("checkpoint.owner_key")
    if int(cp_row["owner_version"]) != validated.archive_owner_version:
        drift_fields.append("checkpoint.owner_version")
    if str(cp_row["capability_digest"] or "") != validated.archive_capability_digest:
        drift_fields.append("checkpoint.capability_digest")
    if str(cp_row["id"]) != str(validated.checkpoint_id):
        drift_fields.append("checkpoint.id")

    # ack_digest：LIVE acked → live ack_digest **必须**为 lowercase 64-hex。
    live_ack = cp_row.get("ack_digest")
    archive_ack = validated.archive_ack_digest
    if live_cp_state == "acked":
        if live_ack is None:
            drift_fields.append("checkpoint.live_ack_digest_missing")
        else:
            try:
                _assert_64hex_lowercase(live_ack, field="checkpoint.live_ack_digest")
            except RestoreReplayError as exc:
                drift_fields.append(f"live.{exc.code}")
    # 严格相等比较：**仅当** archive 端也是 acked（archive_ack 非 None）时比较。
    # 单向终态推进（archive erasing/pending → LIVE acked）时 archive_ack=None，
    # LIVE ack_digest 是 participant 新写的合法值，**不**与 archive 比较。
    if (
        validated.archive_checkpoint_state == "acked"
        and archive_ack is not None
        and live_ack is not None
        and archive_ack != live_ack
    ):
        drift_fields.append("checkpoint.ack_digest_archive_live_mismatch")

    if drift_fields:
        raise RestoreReplayError(
            "TOCTOU_DRIFT_FIELDS",
            detail={
                "operation_id": str(validated.operation_id),
                "owner_key": validated.archive_owner_key,
                "drift_fields": tuple(drift_fields),
            },
        )

    # 无 drift → 返回同一 cp_row 快照上的 terminal evidence（caller 据此决定 NO_REPEAT）。
    return is_terminal_single_direction


# ---------------------------------------------------------------------------
# participant 真实 outcome 分类（Round-7：接住 outcome，不得凭空调 LOCAL_CLEARED）
# ---------------------------------------------------------------------------


class _ParticipantOutcome(Protocol):
    """participant 公共入口返回的 outcome 最小结构契约（结构化校验，不导入具体类）。

    四个 participant 入口（workspace/execution core + 两 transport）均返回承载
    ``blocked`` / ``block_reason`` / ``ack_digest`` / ``erased`` 的 frozen dataclass。
    以只读 ``@property`` 声明（frozen dataclass 暴露只读属性；Protocol 数据成员默认
    要求可写，会与 frozen 属性不兼容）。
    """

    @property
    def blocked(self) -> bool: ...

    @property
    def block_reason(self) -> str | None: ...

    @property
    def ack_digest(self) -> str | None: ...

    @property
    def erased(self) -> bool: ...


# participant outcome 分类结果
_OUTCOME_CLEARED = "cleared"
_OUTCOME_BLOCKED = "blocked"


def _classify_participant_outcome(
    outcome: Any,
    *,
    owner_key: str,
    operation_id: uuid.UUID,
) -> str:
    """把 participant 真实 outcome 分类为 ``_OUTCOME_CLEARED`` / ``_OUTCOME_BLOCKED``；
    非法 shape → ``RestoreReplayError("PARTICIPANT_OUTCOME_INVALID")`` fail closed。

    - ``blocked=True`` → ``_OUTCOME_BLOCKED``：**必须**携带稳定非空 ``block_reason``、
      ``ack_digest is None``、``erased is False``（blocked 与 erased 互斥）。
    - ``blocked=False`` → 必须 ``erased=True`` 且 ``ack_digest`` 为 lowercase 64-hex
      → ``_OUTCOME_CLEARED``（erased/ack 证据成立才允许登记 LOCAL_CLEARED）。
    - 其它任何形态（None / 缺字段 / 类型错误 / blocked 无 reason / blocked 带 ack /
      非 blocked 非 erased / erased 无合法 ack）→ fail closed。
    """

    def _illegal(reason: str) -> RestoreReplayError:
        return RestoreReplayError(
            "PARTICIPANT_OUTCOME_INVALID",
            detail={
                "owner_key": owner_key,
                "operation_id": str(operation_id),
                "reason": reason,
            },
        )

    if outcome is None:
        raise _illegal("outcome_none")
    try:
        blocked = outcome.blocked
        block_reason = outcome.block_reason
        ack_digest = outcome.ack_digest
        erased = outcome.erased
    except AttributeError as exc:
        raise _illegal(f"missing_field:{exc}") from exc
    if not isinstance(blocked, bool):
        raise _illegal("blocked_not_bool")
    if not isinstance(erased, bool):
        raise _illegal("erased_not_bool")
    if blocked:
        if not isinstance(block_reason, str) or not block_reason:
            raise _illegal("blocked_without_reason")
        if ack_digest is not None:
            raise _illegal("blocked_with_ack_digest")
        if erased:
            raise _illegal("blocked_and_erased_inconsistent")
        return _OUTCOME_BLOCKED
    # blocked=False → 必须 erased + 合法 ack 证据
    if not erased:
        raise _illegal("neither_blocked_nor_erased")
    if not isinstance(ack_digest, str) or not _HEX_LOWER_64_RE.match(ack_digest):
        raise _illegal("cleared_without_valid_ack_digest")
    return _OUTCOME_CLEARED


async def _execute_local_owner_via_participant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    validated: ValidatedFact,
) -> _ParticipantOutcome:
    """pass B：local owner 通过对应 participant 公共 sanctioned 入口清除 + ACK。

    严格映射（**禁止** transport owner 调 core helper；**禁止**私有 helper 拼装假 ACK）：
    - workspace.core.v1 → WorkspaceErasureParticipant.erase_conversation_body
    - execution.core.v1 → ExecutionErasureParticipant.erase_execution_body
    - workspace.transport.v1 → WorkspaceTransportErasureParticipant.erase_transport_owner
    - execution.transport.v1 → ExecutionTransportErasureParticipant.erase_transport_owner

    返回 participant 的**真实 outcome**（caller 据此分类 LOCAL_CLEARED / BLOCKED_KEPT，
    **禁止**凭空登记 cleared）。
    """
    if validated.archive_owner_key == "workspace.core.v1":
        from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
            WorkspaceErasureParticipant,
        )
        return await WorkspaceErasureParticipant(session).erase_conversation_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )

    if validated.archive_owner_key == "execution.core.v1":
        from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
            ExecutionErasureParticipant,
        )
        return await ExecutionErasureParticipant(session).erase_execution_body(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )

    if validated.archive_owner_key == "workspace.transport.v1":
        from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
            WorkspaceTransportErasureParticipant,
        )
        return await WorkspaceTransportErasureParticipant(session).erase_transport_owner(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )

    if validated.archive_owner_key == "execution.transport.v1":
        from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (
            ExecutionTransportErasureParticipant,
        )
        return await ExecutionTransportErasureParticipant(session).erase_transport_owner(
            tenant_id=tenant_id,
            conversation_id=validated.conversation_id,
            purge_revision=validated.archive_purge_revision,
            purge_operation_id=validated.operation_id,
            expected_operation_revision=validated.archive_revision,
            expected_lease_epoch=validated.archive_lease_epoch,
        )

    raise RestoreReplayError(
        "UNKNOWN_LOCAL_OWNER",
        detail={"owner_key": validated.archive_owner_key},
    )


# ---------------------------------------------------------------------------
# Public entrypoint（两遍执行）
# ---------------------------------------------------------------------------


async def replay_archive_segment_for_tenant(
    session_factory: async_sessionmaker,
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
) -> RestoreReplayReport:
    """D2 主入口（两遍执行 + committed-tip discovery + 幂等）。

    - Phase 1：从 D1b committed graph 取输入。无 tip / fork / corrupt →
      ``RestoreReplayReport.error`` 非空（**DB tx 开始前**）。
    - pass A：六元组 + operation fence 全字段对账（**DB tx 外**；零写）。
      任一 drift → 抛 ``RestoreReplayError`` → ``RestoreReplayReport.pass_a_drift>0``。
    - pass B：单一 exclusive maintenance transaction 执行。
      TOCTOU 重读 LIVE state + 调 participant 公共入口；任一异常 → caller 不
      catch → ``async with session.begin()`` 自动 rollback → 异常冒泡转化为
      ``RestoreReplayReport.error``。
    - 幂等：同一 committed segment 连续执行两次；第二次 LIVE state 已 terminal
      → ``NO_REPEAT``，**不**调 participant。

    Returns:
        ``RestoreReplayReport``（含 pass_a_drift / toctou_drift / participant_failures
        等 unified error interface）。Gate 必须从本 report 内部 derive blocking。
    """
    try:
        manifest, facts = await _read_archive_from_committed_tip(
            sink, tenant_id=tenant_id
        )
    except LedgerArchiveError as exc:
        return RestoreReplayReport(
            operations_total=0, owners_total=0,
            error=f"{exc.code}: {getattr(exc, 'detail', {})}",
        )
    except RestoreReplayError as exc:
        return RestoreReplayReport(
            operations_total=0, owners_total=0, error=f"{exc.code}: {exc.detail}",
        )

    operations_total = len({op_id for op_id, _ in facts})
    verdicts: list[ReplayOwnerVerdict] = []
    pass_a_drift_count = 0
    toctou_drift_count = 0
    participant_failure_count = 0
    # archive external_ref 严格 per-fact 绑定（在 pass A 段按 conversation_id 精确匹配）；
    # 不再使用全局 archive_external_record 变量（**禁止**任意 LIVE row 冒充）。

    # -------- pass A：DB tx 外（async session.begin() 之外）；任何 drift 抛错
    validated_facts: list[tuple[OwnerFacts, ValidatedFact]] = []
    try:
        async with session_factory() as session, session.begin():
            for fact in facts.values():
                op_id = fact.operation_id
                archive_op_record = await _read_operation_archive_facts(
                    session, manifest=manifest, operation_id=op_id,
                )
                archive_cp_record = _read_checkpoint_archive_facts(
                    manifest, operation_id=op_id, owner_key=fact.owner_key,
                )
                vf = await _validate_pass_a(
                    session,
                    tenant_id=tenant_id,
                    fact=fact,
                    archive_op_record=archive_op_record,
                    archive_cp_record=archive_cp_record,
                )
                validated_facts.append((fact, vf))
    except RestoreReplayError as exc:
        # pass A 失败 → 报告 pass_a_drift；caller 不需 catch，异常已冒泡到本函数
        return RestoreReplayReport(
            operations_total=operations_total,
            owners_total=len(facts),
            pass_a_drift=1,
            owners_fact_drift=1,
            verdict=(ReplayOwnerVerdict(
                operation_id="(pass_a)",
                owner_key="(pass_a)",
                action=ACTION_FACT_DRIFT_FAIL_CLOSED,
                reason_code=f"{exc.code}: {exc.detail}",
            ),),
            error=f"pass_a_drift:{exc.code}",
        )

    # -------- owner_key 预验证（Round-7 Req2）：进入 pass B（任何写入）**之前**，
    # 一次性验证全部 owner_key ∈ LOCAL_OWNERS ∪ NON_LOCAL_OWNERS。任何未知 owner →
    # 在进入 pass B 前 fail closed（不开启写事务 → 零 partial commit）。
    for _fact, validated in validated_facts:
        if validated.archive_owner_key not in (LOCAL_OWNERS | NON_LOCAL_OWNERS):
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                owners_fact_drift=1,
                verdict=(ReplayOwnerVerdict(
                    operation_id=str(validated.operation_id),
                    owner_key=validated.archive_owner_key,
                    action=ACTION_FACT_DRIFT_FAIL_CLOSED,
                    reason_code=f"unknown_owner_pre_pass_b:{validated.archive_owner_key}",
                ),),
                error=f"unknown_owner:{validated.archive_owner_key}",
            )

    # -------- pass B：单一 exclusive maintenance transaction
    external_verified_count = 0
    external_verification_failed_count = 0
    try:
        async with session_factory() as session, session.begin():
            # 第一条 DB 语句必须是 exclusive advisory xact lock
            await acquire_maintenance_exclusive_lock(session)

            for _fact, validated in validated_facts:
                # **所有路径**（含 NO_REPEAT）都经同一 ``_toctou_reverify_pass_b`` 完整重验
                # ValidatedFact 全字段（**禁止**只读 checkpoint.state 后直接 continue）。
                # reverify 在其**同一 cp_row 快照**上判定 terminal evidence（archive cp ∈
                # {pending,erasing} + LIVE acked 的单向终态推进）并作为返回值交给本循环——
                # 最终 action **只消费该返回结果**，**禁止**在调用前再单独读一次
                # checkpoint.state（消除双读 TOCTOU 窗口）。
                terminal_evidence = await _toctou_reverify_pass_b(
                    session,
                    tenant_id=tenant_id,
                    validated=validated,
                )
                if terminal_evidence:
                    # 完整 terminal evidence 单向终态推进 → NO_REPEAT（**不**调 participant）
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=ACTION_NO_REPEAT,
                            reason_code="live_already_acked_terminal_evidence",
                        )
                    )
                    continue

                # 6×5 全局矩阵先（**禁止**按 owner 跳过）——scheduled/cancelled/
                # failed/acked 等 terminal / 特殊状态**必须**按矩阵返回
                global_action, global_reason = _route_global_matrix(
                    operation_state=validated.archive_operation_state,
                    checkpoint_state=validated.archive_checkpoint_state,
                )

                # 矩阵首先决定 terminal 状态（no_repeat / zero_write / skip / replay_skip）→
                # local 与 non-local owner 同样适用（**禁止**统一降级为 non_local_blocked）
                if global_action in (
                    ACTION_REPLAY_SKIP_ZERO_WRITE,
                    ACTION_ZERO_WRITE,
                    ACTION_SKIP,
                    ACTION_NO_REPEAT,
                ):
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=global_action,
                            reason_code=global_reason or "global_matrix_terminal",
                        )
                    )
                    continue

                # completed + acked → verify-only（local owner 不调 participant）
                if global_action == ACTION_VERIFY_ONLY:
                    if validated.archive_owner_key in NON_LOCAL_OWNERS:
                        # non-local owner → 走 _route_non_local（runtime / external）
                        nl_action, nl_reason = _route_non_local(
                            owner_key=validated.archive_owner_key,
                            operation_state=validated.archive_operation_state,
                            checkpoint_state=validated.archive_checkpoint_state,
                        )
                        if nl_action == ACTION_EXTERNAL_VERIFY_ONLY:
                            # 必须按 archive operation.conversation_id + owner_key 经统一
                            # binder 精确绑定 external_ref record；0 条 / ≥2 条 / 错 conversation/
                            # owner / receipt mismatch / final-scan residual → 具名
                            # EXTERNAL_VERIFICATION_FAILED（函数内部 raise，失败即退出事务）
                            await _verify_external_receipt(
                                session,
                                tenant_id=tenant_id,
                                validated=validated,
                                manifest=manifest,
                            )
                            external_verified_count += 1
                            verdicts.append(
                                ReplayOwnerVerdict(
                                    operation_id=str(validated.operation_id),
                                    owner_key=validated.archive_owner_key,
                                    action=ACTION_EXTERNAL_VERIFIED,
                                    reason_code="external_receipt_match_and_erased",
                                )
                            )
                            continue
                        else:
                            # runtime + completed → RUNTIME_BINDING_UNPROVABLE
                            verdicts.append(
                                ReplayOwnerVerdict(
                                    operation_id=str(validated.operation_id),
                                    owner_key=validated.archive_owner_key,
                                    action=nl_action,
                                    reason_code=nl_reason,
                                )
                            )
                        continue
                    # local owner + completed → verify-only
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=ACTION_VERIFY_ONLY,
                            reason_code="completed_verify_only",
                        )
                    )
                    continue

                if global_action == ACTION_FACT_DRIFT_FAIL_CLOSED:
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=ACTION_FACT_DRIFT_FAIL_CLOSED,
                            reason_code=global_reason,
                        )
                    )
                    continue

                # global_action == ACTION_LOCAL_CLEARED → owner-specific 路由
                if validated.archive_owner_key in NON_LOCAL_OWNERS:
                    # non-local owner 走 _route_non_local
                    nl_action, nl_reason = _route_non_local(
                        owner_key=validated.archive_owner_key,
                        operation_state=validated.archive_operation_state,
                        checkpoint_state=validated.archive_checkpoint_state,
                    )
                    if nl_action == ACTION_EXTERNAL_VERIFY_ONLY:
                        # completed → 已走 verify-only 分支
                        raise RestoreReplayError(
                            "ROUTING_BUG",
                            detail={"owner_key": validated.archive_owner_key},
                        )
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=nl_action,
                            reason_code=nl_reason,
                        )
                    )
                    continue
                if validated.archive_owner_key in LOCAL_OWNERS:
                    # local owner 候选 → 调 participant 公共入口（**接住真实 outcome**）
                    # **participant 抛错必 raise 退出事务**（caller 不 catch）
                    try:
                        outcome = await _execute_local_owner_via_participant(
                            session, tenant_id=tenant_id, validated=validated,
                        )
                    except Exception as exc:
                        participant_failure_count += 1
                        raise RestoreReplayError(
                            "PARTICIPANT_FAILURE",
                            detail={
                                "owner_key": validated.archive_owner_key,
                                "operation_id": str(validated.operation_id),
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                        ) from exc
                    # 接住真实 outcome：非法 shape → fail closed（raise → rollback）；
                    # blocked=True → BLOCKED_KEPT（保留不清除 + 稳定 reason）；
                    # erased/ack 证据成立 → LOCAL_CLEARED（**禁止**凭空登记 cleared）。
                    classification = _classify_participant_outcome(
                        outcome,
                        owner_key=validated.archive_owner_key,
                        operation_id=validated.operation_id,
                    )
                    if classification == _OUTCOME_BLOCKED:
                        verdicts.append(
                            ReplayOwnerVerdict(
                                operation_id=str(validated.operation_id),
                                owner_key=validated.archive_owner_key,
                                action=ACTION_BLOCKED_KEPT,
                                reason_code=outcome.block_reason,
                            )
                        )
                        continue
                    verdicts.append(
                        ReplayOwnerVerdict(
                            operation_id=str(validated.operation_id),
                            owner_key=validated.archive_owner_key,
                            action=ACTION_LOCAL_CLEARED,
                            reason_code="local_cleared_via_participant",
                        )
                    )
                    continue
                # 未知 owner → 防御分支：**必须 raise 并 rollback**（Round-7 Req2；
                # 正常路径已被 pass B 前的 owner_key 一次性预验证拦截，此处仅防御，
                # 不得以 verdict 静默默认后继续提交 → 零 partial commit）。
                raise RestoreReplayError(
                    "UNKNOWN_OWNER",
                    detail={
                        "operation_id": str(validated.operation_id),
                        "owner_key": validated.archive_owner_key,
                    },
                )
    except RestoreReplayError as exc:
        # 异常已通过 async with session.begin() 自动 rollback；冒泡到 caller →
        # 在本函数内转化为 report.error
        if exc.code == "PARTICIPANT_FAILURE":
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                owners_fact_drift=participant_failure_count,
                participant_failures=participant_failure_count,
                verdict=tuple(verdicts),
                error=f"participant_failure:{exc.detail.get('owner_key', '?')}",
            )
        if exc.code == "PARTICIPANT_OUTCOME_INVALID":
            # participant 返回非法 outcome shape → fail closed（已 rollback）
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                owners_fact_drift=1,
                participant_failures=participant_failure_count + 1,
                verdict=tuple(verdicts),
                error=(
                    f"participant_outcome_invalid:{exc.detail.get('owner_key', '?')}"
                    f":{exc.detail.get('reason', '?')}"
                ),
            )
        if exc.code == "UNKNOWN_OWNER":
            # pass B 未知 owner 防御分支 raise（预验证已拦截；此处 fail closed + rollback）
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                owners_fact_drift=1,
                verdict=tuple(verdicts),
                error=f"unknown_owner:{exc.detail.get('owner_key', '?')}",
            )
        if exc.code == "EXTERNAL_VERIFICATION_FAILED":
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                external_verification_failed=1,
                verdict=tuple(verdicts),
                error=(
                    f"external_verification_failed:{exc.detail.get('owner_key', '?')}"
                    f":{exc.detail.get('reason', '?')}"
                ),
            )
        if exc.code.startswith("TOCTOU_DRIFT"):
            # pass B exclusive tx 内的 TOCTOU drift → toctou_drift **真实递增**（不恒 0）
            return RestoreReplayReport(
                operations_total=operations_total,
                owners_total=len(facts),
                owners_fact_drift=1,
                toctou_drift=1,
                verdict=tuple(verdicts),
                error=f"{exc.code}:{exc.detail}",
            )
        return RestoreReplayReport(
            operations_total=operations_total,
            owners_total=len(facts),
            owners_fact_drift=toctou_drift_count,
            toctou_drift=toctou_drift_count,
            verdict=tuple(verdicts),
            error=f"{exc.code}:{exc.detail}",
        )

    counts = _count_verdicts_by_actual_result(verdicts)
    return RestoreReplayReport(
        operations_total=operations_total,
        owners_total=len(facts),
        owners_local_cleared=counts[ACTION_LOCAL_CLEARED],
        owners_blocked_kept=counts[ACTION_BLOCKED_KEPT],
        owners_non_local_blocked=(
            counts[ACTION_NON_LOCAL_BLOCKED]
            + counts[ACTION_RUNTIME_BLOCKED]
        ),
        owners_verify_only=(
            counts[ACTION_VERIFY_ONLY]
            + counts[ACTION_EXTERNAL_VERIFIED]
        ),
        owners_skipped=(
            counts[ACTION_SKIP]
            + counts[ACTION_REPLAY_SKIP_ZERO_WRITE]
        ),
        owners_fact_drift=counts[ACTION_FACT_DRIFT_FAIL_CLOSED],
        owners_no_repeat=counts[ACTION_NO_REPEAT],
        runtime_binding_evidence_unprovable=counts[
            ACTION_RUNTIME_BINDING_UNPROVABLE
        ],
        external_verified=external_verified_count,
        external_verification_failed=external_verification_failed_count,
        external_verify_only=counts[ACTION_EXTERNAL_VERIFY_ONLY],
        verdict=tuple(verdicts),
        toctou_drift=toctou_drift_count,
        pass_a_drift=pass_a_drift_count,
        participant_failures=participant_failure_count,
    )


def _count_verdicts_by_actual_result(
    verdicts: list[ReplayOwnerVerdict],
) -> Counter[str]:
    c: Counter[str] = Counter()
    for v in verdicts:
        c[v.action] += 1
    return c


# ---------------------------------------------------------------------------
# phase 3 — restore-before-open gate（**强制**消费 RestoreReplayReport）
# ---------------------------------------------------------------------------


async def evaluate_restore_before_open(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    replay_report: RestoreReplayReport,
    runtime_proof_c_present: bool,
) -> RestoreBeforeOpenReport:
    """phase 3 gate（**强制**消费 RestoreReplayReport；不接受默认 0/False）。

    Gate 自动从 replay_report 内部 derive blocking（error / pass_a_drift / toctou_drift /
    owners_fact_drift / owners_blocked_kept / runtime_binding_evidence_unprovable /
    external_verification_failed 全部自动阻断）。runtime_proof_c_present 由 caller 显式传入
    （**不可**绕 0/False）。
    """
    blocked: list[str] = []

    # 1. ReplayReport 内部 blocking 项 → 全部阻断
    if replay_report.error is not None:
        blocked.append(f"replay_error:{replay_report.error}")
    if replay_report.pass_a_drift > 0:
        blocked.append(f"pass_a_drift:{replay_report.pass_a_drift}")
    if replay_report.toctou_drift > 0:
        blocked.append(f"toctou_drift:{replay_report.toctou_drift}")
    if replay_report.participant_failures > 0:
        blocked.append(f"participant_failure:{replay_report.participant_failures}")
    if replay_report.owners_fact_drift > 0:
        blocked.append(f"fact_drift:{replay_report.owners_fact_drift}")
    if replay_report.owners_blocked_kept > 0:
        # local owner participant blocked=True（保留不清除）→ 仍有未清残留 → 保持关闭
        blocked.append(f"blocked_kept:{replay_report.owners_blocked_kept}")
    if replay_report.runtime_binding_evidence_unprovable > 0:
        blocked.append(
            f"RUNTIME_BINDING_EVIDENCE_UNPROVABLE:"
            f"{replay_report.runtime_binding_evidence_unprovable}"
        )
    if replay_report.external_verification_failed > 0:
        blocked.append(
            f"external_verification_failed:"
            f"{replay_report.external_verification_failed}"
        )
    if replay_report.owners_non_local_blocked > 0:
        blocked.append(
            f"non_local_blocked:{replay_report.owners_non_local_blocked}"
        )

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

        # 4. S6-6 巡检 —— 实际填充 verify_inspection.inspections
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
    "ACTION_BLOCKED_KEPT",
    "ACTION_CANDIDATE_WHEN_LOCAL",
    "ACTION_NON_LOCAL_BLOCKED",
    "ACTION_EXTERNAL_VERIFIED",
    "ACTION_EXTERNAL_VERIFICATION_FAILED",
    "ACTION_EXTERNAL_VERIFY_ONLY",
    "ACTION_RUNTIME_BINDING_UNPROVABLE",
    "ACTION_RUNTIME_BLOCKED",
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
