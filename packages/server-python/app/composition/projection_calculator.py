"""R1-S5-A-2 纯 projection calculator（I2 实现，契约已冻结并入 main）。

无 session / repository / I/O / 副作用——只接收 coordinator 装配的规范化
facts，按 S5-A-2 全函数真值表返回确定性投影
``(operation.state, failure_code, purge_state, completed/purged 标志)``。

输入 facts（全部由 transactional coordinator 在 Conversation 首锁下采集）：
- snapshot：operation.registry_snapshot 持久快照（排序 owner 全集）
- registry_digest_matches / hold_drift / active_legal_hold：G1/G2/G3 判定结果
- checkpoints / fences：全 owner 行事实（owner-scoped，本模块只读）
- lineage：per-owner derived 事实（lineage_status + expected_obligation_kind，
  权威公式见 plan R1-S5-B S5-B-3 阶段 2；I2 无 rebuild，coordinator 装配为
  not_applicable/native_pending；完整 lineage 派生随 scheduler slice 扩展）
- scans：per-owner 最终正文扫描结果（跨 owner 全零、逐 owner 可归属）

判定顺序（冻结）：G1 > G2 > G3 > G4 > 1 > 2 > 3 > 4 > 5 > 6 > 7。
gate 命中时 gate reason 独占 failure_code，不参与 severity-max。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.shared.schemas.canonical_json import canonical_digest

# ---------------------------------------------------------------------------
# 输入 facts（frozen）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryOwnerFact:
    owner_key: str
    owner_version: int
    capability_digest: str


@dataclass(frozen=True, slots=True)
class CheckpointFact:
    owner_key: str
    state: str  # pending / erasing / blocked / failed / acked
    reason_code: str | None
    attempt: int
    owner_version: int
    capability_digest: str
    ack_digest: str | None
    checkpoint_digest: str | None


@dataclass(frozen=True, slots=True)
class FenceFact:
    owner_key: str
    state: str  # active / erasing / erased / blocked
    owner_version: int
    purge_revision: int
    ack_digest: str | None
    ingress_digest: str
    ingress_checkpoint: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class OwnerScanFact:
    owner_key: str
    total: int


@dataclass(frozen=True, slots=True)
class LineageFact:
    """per-owner derived 事实（S5-A-2 输入增补，回填自 S5-B-8 第 2/7 项）。

    lineage_status ∈ {valid, conflict, not_applicable}；
    expected_obligation_kind ∈ {native_pending, inherited_acked,
    carried_blocked, carried_failed}。derived 非持久，重启后重算必须同值。
    """

    owner_key: str
    lineage_status: str  # valid / conflict / not_applicable
    # native_pending / inherited_acked / carried_blocked / carried_failed
    expected_obligation_kind: str


@dataclass(frozen=True, slots=True)
class ProjectionInput:
    snapshot: tuple[RegistryOwnerFact, ...]
    registry_digest_matches: bool
    hold_drift: bool
    active_legal_hold: bool
    operation_purge_revision: int
    checkpoints: tuple[CheckpointFact, ...]
    fences: tuple[FenceFact, ...]
    lineage: tuple[LineageFact, ...]
    scans: tuple[OwnerScanFact, ...]


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    state: str  # scheduled / running / blocked / failed / completed
    failure_code: str | None
    purge_state: str  # 与 state 同值域（Conversation.purge_state 投影）
    completed: bool
    purged: bool  # completed 时 Conversation.purged_at 非空（coordinator 落库）


# ---------------------------------------------------------------------------
# reason 严重度表（冻结，S5-A-0 十二层，1 最高；level 2/3/4 为 coordinator-level）
# ---------------------------------------------------------------------------

REASON_SEVERITY: dict[str, int] = {
    "purge_blocked_by_legal_hold": 1,
    "blocked_registry_changed": 2,
    "blocked_hold_revision_changed": 3,
    "purge_owner_ack_conflict": 4,
    "purge_blocked_by_unresolved_action": 5,
    "purge_blocked_by_conversation_scope_gate": 6,
    "purge_blocked_by_external_outcome_unknown": 7,
    "purge_blocked_by_runtime_outcome_unknown": 7,
    "purge_blocked_by_external_settlement_deadline_expired": 7,
    "purge_blocked_by_runtime_settlement_deadline_expired": 7,
    "purge_blocked_by_external_adapter_unresolvable": 7,
    "purge_blocked_by_runtime_adapter_unresolvable": 7,
    "purge_blocked_by_external_erase_timeout": 8,
    "purge_blocked_by_runtime_erase_timeout": 8,
    "purge_blocked_by_external_adapter_unavailable": 9,
    "purge_blocked_by_runtime_adapter_unavailable": 9,
    "purge_blocked_by_external_ref_scan_nonzero": 10,
    "purge_blocked_by_runtime_binding_scan_nonzero": 10,
    "purge_blocked_by_transport_scan_nonzero": 10,
    "workspace_body_scan_nonzero": 10,
    "execution_body_scan_nonzero": 10,
    "purge_owner_unavailable": 11,
    "operator_suppressed": 12,
}

# 最终扫描逐 owner 归属的 scan reason（S5-A-0 level 10 scan 族）。
SCAN_REASON_BY_OWNER: dict[str, str] = {
    "workspace.core.v1": "workspace_body_scan_nonzero",
    "execution.core.v1": "execution_body_scan_nonzero",
    "workspace.transport.v1": "purge_blocked_by_transport_scan_nonzero",
    "execution.transport.v1": "purge_blocked_by_transport_scan_nonzero",
    "external.payload.v1": "purge_blocked_by_external_ref_scan_nonzero",
    "runtime.private.v1": "purge_blocked_by_runtime_binding_scan_nonzero",
}

# coordinator-level gate reason（S5-A-0 level 2/3/4；participant 不得写 checkpoint）。
COORDINATOR_LEVEL_REASONS = frozenset(
    {
        "blocked_registry_changed",
        "blocked_hold_revision_changed",
        "purge_owner_ack_conflict",
    }
)

# unknown non-NULL reason 的确定性归属层（全函数边界：保留原 reason 作
# failure_code，按 level 12 参与 severity-max——dirty-data 归运维，聚合不停摆）。
UNKNOWN_REASON_SEVERITY = 12


def severity_of(reason: str) -> int:
    """reason 严重度；未知 reason 确定性归 UNKNOWN_REASON_SEVERITY。"""
    return REASON_SEVERITY.get(reason, UNKNOWN_REASON_SEVERITY)


def _severity_max_with_tie_break(
    owner_reasons: list[tuple[str, str]],
) -> str | None:
    """severity-max + owner_key 字典序 tie-break（S5-A-3 冻结）。

    多来源只产生一个 failure_code；同严重度按 owner_key 字典序取最小者
    （禁用先提交者保留 / 最后提交者覆盖）。空集合 → None。
    """
    if not owner_reasons:
        return None
    best_owner, best_reason = min(
        owner_reasons,
        key=lambda pair: (severity_of(pair[1]), pair[0]),
    )
    return best_reason


# ---------------------------------------------------------------------------
# 五方验证（S5-A-2 completed 必要条件 (d)，去 scan 化——S2 拆分裁决）
# ---------------------------------------------------------------------------


def _five_party_validation(
    owner: RegistryOwnerFact,
    checkpoint: CheckpointFact | None,
    fence_row: FenceFact | None,
    operation_purge_revision: int,
    lineage_status: str,
) -> bool:
    """checkpoint=acked + fence=erased + owner/version 匹配 + fence.purge_revision
    双分支（native 等值 / inherited 例外）+ ack_digest 一致 + ingress 证据满足。

    与 scan 结果无关（scan 是独立条件(c)，不参与五方）。任一矛盾 fail closed
    （优先级 2，不先 completed 再等运维 reconcile）。
    """
    if checkpoint is None or checkpoint.state != "acked":
        return False
    if fence_row is None or fence_row.state != "erased":
        return False
    if checkpoint.owner_version != owner.owner_version:
        return False
    if fence_row.owner_version != owner.owner_version:
        return False
    if fence_row.purge_revision == operation_purge_revision:
        # native 等值（S5-A 五方）
        pass
    elif fence_row.purge_revision < operation_purge_revision:
        # inherited 例外（回填自 S5-B-8 第 1 项）：lineage 六项全过（lineage_status
        # == valid）才记入「全 owner acked」；否则矛盾 fail closed。
        if lineage_status != "valid":
            return False
    else:
        # fence.purge_revision > operation.purge_revision → 矛盾 fail closed。
        return False
    if checkpoint.ack_digest != fence_row.ack_digest:
        return False
    if checkpoint.ack_digest is None:
        return False
    # ingress 证据：fence.ingress_digest == canonical_digest(ingress_checkpoint)
    # （S5-B-3 item 5；checkpoint_digest 不参与信任判定）。
    return fence_row.ingress_digest == canonical_digest(
        dict(fence_row.ingress_checkpoint)
    )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def calculate_projection(inputs: ProjectionInput) -> ProjectionResult:
    snapshot_owners = {owner.owner_key: owner for owner in inputs.snapshot}
    snapshot_order = [owner.owner_key for owner in inputs.snapshot]

    checkpoints_by_owner: dict[str, CheckpointFact] = {}
    for checkpoint in inputs.checkpoints:
        checkpoints_by_owner[checkpoint.owner_key] = checkpoint
    fences_by_owner: dict[str, FenceFact] = {}
    for fence_row in inputs.fences:
        fences_by_owner[fence_row.owner_key] = fence_row
    scans_by_owner = {s.owner_key: s.total for s in inputs.scans}
    lineage_by_owner = {lin.owner_key: lin for lin in inputs.lineage}

    def lineage_of(owner_key: str) -> LineageFact:
        """snapshot owner 缺 lineage 事实 → 确定性默认
        not_applicable/native_pending（coordinator 装配缺省，全函数边界）。"""
        return lineage_by_owner.get(
            owner_key,
            LineageFact(
                owner_key=owner_key,
                lineage_status="not_applicable",
                expected_obligation_kind="native_pending",
            ),
        )

    # --- gate 层（G1 > G2 > G3 > G4，任一命中即定；gate reason 独占 failure_code）---

    if not inputs.registry_digest_matches:
        return ProjectionResult(
            state="blocked",
            failure_code="blocked_registry_changed",
            purge_state="blocked",
            completed=False,
            purged=False,
        )
    if inputs.hold_drift:
        return ProjectionResult(
            state="blocked",
            failure_code="blocked_hold_revision_changed",
            purge_state="blocked",
            completed=False,
            purged=False,
        )
    if inputs.active_legal_hold:
        return ProjectionResult(
            state="blocked",
            failure_code="purge_blocked_by_legal_hold",
            purge_state="blocked",
            completed=False,
            purged=False,
        )

    # G4 derived lineage conflict：任一 snapshot owner 的 lineage_status=conflict，
    # 或存在 snapshot 外 owner 的 checkpoint 行（视同 conflict）。
    # 先于 checkpoint 聚合（partial-ACK 状态下即时浮出不被优先级 6 掩蔽）；
    # checkpoint 保持原 owner 事实零修改（coordinator 只写 operation/Conversation）。
    external_rows = [
        owner_key
        for owner_key in checkpoints_by_owner
        if owner_key not in snapshot_owners
    ]
    conflict_owners = [
        owner_key
        for owner_key in snapshot_order
        if lineage_of(owner_key).lineage_status == "conflict"
    ]
    if external_rows or conflict_owners:
        return ProjectionResult(
            state="blocked",
            failure_code="purge_owner_ack_conflict",
            purge_state="blocked",
            completed=False,
            purged=False,
        )

    # --- checkpoint 聚合层（gate 全过后按优先级 1→7 判定）---

    # 缺行处理（S5-A-2 优先级唯一裁决）：
    # - expected_obligation_kind=native_pending 缺行 → 视为 pending（绝不 completed）
    # - inherited_acked / carried_blocked / carried_failed 缺行 → lineage conflict
    #   → G4（seeded/carry 义务丢失 = 事实漂移；禁当 pending 重跑、禁二次 adapter 调用）
    missing_owners = [o for o in snapshot_order if o not in checkpoints_by_owner]
    for owner_key in missing_owners:
        if lineage_of(owner_key).expected_obligation_kind != "native_pending":
            return ProjectionResult(
                state="blocked",
                failure_code="purge_owner_ack_conflict",
                purge_state="blocked",
                completed=False,
                purged=False,
            )

    all_rows = [checkpoints_by_owner[o] for o in snapshot_order
                if o in checkpoints_by_owner]

    def blocked_reason_aggregation(
        rows: list[CheckpointFact],
    ) -> str | None:
        """优先级 4/5 共享的 reason 聚合：severity-max + owner_key tie-break；
        全部 NULL → operator_suppressed（level 12 可达）；unknown 非 NULL reason
        按 level 12 归属并保留原值（全函数边界，见 UNKNOWN_REASON_SEVERITY）。"""
        pairs = [
            (r.owner_key, r.reason_code)
            for r in rows
            if r.state in ("blocked", "failed") and r.reason_code is not None
        ]
        if not pairs:
            return "operator_suppressed"
        return _severity_max_with_tie_break(pairs)

    # 7 scheduled：零 checkpoint 行。
    if not all_rows:
        return ProjectionResult(
            state="scheduled",
            failure_code=None,
            purge_state="scheduled",
            completed=False,
            purged=False,
        )

    # 4 blocked：任一 checkpoint blocked（不得被后到 ACK 重开 running）。
    blocked_rows = [r for r in all_rows if r.state == "blocked"]
    if blocked_rows:
        return ProjectionResult(
            state="blocked",
            failure_code=blocked_reason_aggregation(blocked_rows),
            purge_state="blocked",
            completed=False,
            purged=False,
        )

    # 5 failed：任一 checkpoint failed 且无 blocked（failed 由 S5 scheduler slice
    # 产生；coordinator 只读聚合。全部 reason NULL → None）。
    failed_rows = [r for r in all_rows if r.state == "failed"]
    if failed_rows:
        non_null = [
            (r.owner_key, r.reason_code)
            for r in failed_rows
            if r.reason_code is not None
        ]
        failure = _severity_max_with_tie_break(non_null) if non_null else None
        return ProjectionResult(
            state="failed",
            failure_code=failure,
            purge_state="failed",
            completed=False,
            purged=False,
        )

    # 6 running：任一 pending/erasing，或 snapshot owner 缺行（native_pending 期望）。
    if missing_owners or any(
        r.state in ("pending", "erasing") for r in all_rows
    ):
        return ProjectionResult(
            state="running",
            failure_code=None,
            purge_state="running",
            completed=False,
            purged=False,
        )

    # 全 acked 分支：优先级 1/2/3（partial ACK 已在上方 4/5/6 拦截）。
    five_party_results = {
        owner_key: _five_party_validation(
            snapshot_owners[owner_key],
            checkpoints_by_owner.get(owner_key),
            fences_by_owner.get(owner_key),
            inputs.operation_purge_revision,
            lineage_of(owner_key).lineage_status,
        )
        for owner_key in snapshot_order
    }

    # 2 五方矛盾：全 owner acked + 任一五方矛盾（与 scan 结果无关，扫描零/非零均判）。
    if not all(five_party_results.values()):
        return ProjectionResult(
            state="blocked",
            failure_code="purge_owner_ack_conflict",
            purge_state="blocked",
            completed=False,
            purged=False,
        )

    # 3 scan nonzero：全 acked + 五方全过 + 最终扫描非零 → scan 族聚合。
    nonzero_scans = [
        (owner_key, scans_by_owner.get(owner_key, 0))
        for owner_key in snapshot_order
        if scans_by_owner.get(owner_key, 0) != 0
    ]
    if nonzero_scans:
        scan_reasons = [
            (owner_key, SCAN_REASON_BY_OWNER.get(owner_key, "operator_suppressed"))
            for owner_key, _total in nonzero_scans
        ]
        return ProjectionResult(
            state="blocked",
            failure_code=_severity_max_with_tie_break(scan_reasons),
            purge_state="blocked",
            completed=False,
            purged=False,
        )

    # 1 completed：全 owner acked + 五方全过 + 最终扫描全零（G1/G2/G3 已过）。
    return ProjectionResult(
        state="completed",
        failure_code=None,
        purge_state="completed",
        completed=True,
        purged=True,
    )


__all__ = [
    "COORDINATOR_LEVEL_REASONS",
    "CheckpointFact",
    "FenceFact",
    "LineageFact",
    "OwnerScanFact",
    "ProjectionInput",
    "ProjectionResult",
    "REASON_SEVERITY",
    "SCAN_REASON_BY_OWNER",
    "RegistryOwnerFact",
    "calculate_projection",
    "severity_of",
]
