"""R1-S5-I2 projection calculator 纯函数全矩阵测试（无 I/O、无 DB）。

映射 plan §R1-S5-A-2 真值表 / S5-A-3 reason 聚合 / S5-A-8 反例矩阵：
行 1/2/4/5/6/7/8/10/13/15/16/17/18/19/20/22/23。calculator 是纯函数——
任何输入组合都必须有唯一确定结果（全函数），本模块以纯单元测试锁定。

Wished-for API（TDD 先于实现）：
``app.composition.projection_calculator``
- RegistryOwnerFact / CheckpointFact / FenceFact / OwnerScanFact / LineageFact
- ProjectionInput / ProjectionResult
- calculate_projection(inputs) -> ProjectionResult
"""

from __future__ import annotations

import pytest

from app.composition.projection_calculator import (
    CheckpointFact,
    FenceFact,
    LineageFact,
    OwnerScanFact,
    ProjectionInput,
    RegistryOwnerFact,
    calculate_projection,
)

# owner 常量（与 registry 冻结一致）
WS_CORE = "workspace.core.v1"
WS_TRANSPORT = "workspace.transport.v1"
EX_CORE = "execution.core.v1"
EX_TRANSPORT = "execution.transport.v1"
EXTERNAL = "external.payload.v1"
RUNTIME = "runtime.private.v1"

D64 = "a" * 64
E64 = "b" * 64


# ---------------------------------------------------------------------------
# fact builders
# ---------------------------------------------------------------------------


def reg(owner_key: str, version: int = 1) -> RegistryOwnerFact:
    return RegistryOwnerFact(
        owner_key=owner_key, owner_version=version, capability_digest=D64
    )


def cp(
    owner_key: str,
    state: str,
    *,
    reason: str | None = None,
    ack_digest: str | None = None,
    owner_version: int = 1,
    attempt: int = 0,
) -> CheckpointFact:
    return CheckpointFact(
        owner_key=owner_key,
        state=state,
        reason_code=reason,
        attempt=attempt,
        owner_version=owner_version,
        capability_digest=D64,
        ack_digest=ack_digest,
        checkpoint_digest=None,
    )


def fence(
    owner_key: str,
    state: str,
    *,
    purge_revision: int = 1,
    ack_digest: str | None = None,
    owner_version: int = 1,
    ingress_checkpoint: dict | None = None,
) -> FenceFact:
    ic = ingress_checkpoint or {"schema_version": 1, "sources": {}}
    return FenceFact(
        owner_key=owner_key,
        state=state,
        owner_version=owner_version,
        purge_revision=purge_revision,
        ack_digest=ack_digest,
        ingress_digest=ingress_digest_of(ic),
        ingress_checkpoint=ic,
    )


def ingress_digest_of(checkpoint: dict) -> str:
    """与 erasure_repository.empty_ingress_digest 同源 canonical digest。"""
    from app.shared.schemas.canonical_json import canonical_digest

    return canonical_digest(checkpoint)


def lineage(owner_key: str, status: str, kind: str) -> LineageFact:
    return LineageFact(
        owner_key=owner_key, lineage_status=status, expected_obligation_kind=kind
    )


def scan(owner_key: str, total: int) -> OwnerScanFact:
    return OwnerScanFact(owner_key=owner_key, total=total)


def calc(
    *,
    snapshot: list[str] | None = None,
    checkpoints: list[CheckpointFact] | None = None,
    fences: list[FenceFact] | None = None,
    lineage_facts: list[LineageFact] | None = None,
    scans: list[OwnerScanFact] | None = None,
    registry_ok: bool = True,
    hold_drift: bool = False,
    active_hold: bool = False,
    purge_revision: int = 1,
) -> ProjectionInput:
    return ProjectionInput(
        snapshot=tuple(reg(k) for k in (snapshot or [])),
        registry_digest_matches=registry_ok,
        hold_drift=hold_drift,
        active_legal_hold=active_hold,
        operation_purge_revision=purge_revision,
        checkpoints=tuple(checkpoints or []),
        fences=tuple(fences or []),
        lineage=tuple(lineage_facts or []),
        scans=tuple(scans or []),
    )


def result_of(**kwargs) -> tuple[str, str | None, str, bool, bool]:
    r = calculate_projection(calc(**kwargs))
    return (r.state, r.failure_code, r.purge_state, r.completed, r.purged)


# ---------------------------------------------------------------------------
# gate 层（G1 > G2 > G3 > G4，任一命中即定，gate reason 独占 failure_code）
# ---------------------------------------------------------------------------


def test_g1_registry_drift_blocks_with_coordinator_level_reason():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE], checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        registry_ok=False,
    )
    assert (state, code, purge_state, completed, purged) == (
        "blocked", "blocked_registry_changed", "blocked", False, False,
    )


def test_g2_hold_drift_blocks_with_coordinator_level_reason():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE], checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        hold_drift=True,
    )
    assert (state, code, purge_state, completed, purged) == (
        "blocked", "blocked_hold_revision_changed", "blocked", False, False,
    )


def test_g3_active_hold_blocks_completed_even_all_acked():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE], checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        active_hold=True,
    )
    assert (state, code, purge_state, completed, purged) == (
        "blocked", "purge_blocked_by_legal_hold", "blocked", False, False,
    )


def test_g4_lineage_conflict_blocks_before_checkpoint_aggregation():
    # partial ACK + lineage conflict：G4 即时浮出，不被优先级 6 掩蔽。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "pending")],
        lineage_facts=[lineage(WS_CORE, "conflict", "native_pending")],
    )
    assert (state, code, completed) == (
        "blocked", "purge_owner_ack_conflict", False,
    )


def test_g4_snapshot_external_checkpoint_row_blocks():
    # snapshot 外 owner 行（DB 篡改/遗留）视同 conflict → G4；checkpoint 零修改
    # 由 coordinator 层保证（calculator 只产出投影）。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64), cp(EX_CORE, "acked")],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
    )
    assert (state, code, completed) == (
        "blocked", "purge_owner_ack_conflict", False,
    )


def test_gate_reason_exclusive_never_severity_max():
    # 同时存在 blocked checkpoint（严重度 5）与 G1 drift：gate 独占，不聚合。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "blocked", reason="purge_blocked_by_unresolved_action")],
        registry_ok=False,
    )
    assert (state, code) == ("blocked", "blocked_registry_changed")


# ---------------------------------------------------------------------------
# checkpoint 聚合层（优先级 7 → 1）
# ---------------------------------------------------------------------------


def test_priority7_zero_checkpoint_rows_is_scheduled():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE, EX_CORE],
    )
    assert (state, code, purge_state, completed, purged) == (
        "scheduled", None, "scheduled", False, False,
    )


def test_priority6_pending_checkpoint_is_running():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE], checkpoints=[cp(WS_CORE, "pending")],
    )
    assert (state, code, purge_state, completed, purged) == (
        "running", None, "running", False, False,
    )


def test_priority6_missing_native_pending_row_treated_as_pending():
    # snapshot owner 缺行 + native_pending 期望 → 视为 pending → running（绝不 completed）。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        lineage_facts=[
            lineage(WS_CORE, "not_applicable", "native_pending"),
            lineage(EX_CORE, "not_applicable", "native_pending"),
        ],
    )
    assert (state, code, completed) == ("running", None, False)


def test_priority6_partial_missing_is_running_not_scheduled():
    state, _, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "pending")],
    )
    assert state == "running"


def test_priority5_failed_aggregates_severity_max():
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "failed", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "failed", reason="purge_blocked_by_legal_hold"),
        ],
    )
    assert (state, code, purge_state, completed, purged) == (
        "failed", "purge_blocked_by_legal_hold", "failed", False, False,
    )


def test_priority5_failed_all_null_reason_has_none_failure_code():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "failed", reason=None)],
    )
    assert (state, code) == ("failed", None)


def test_priority5_failed_is_not_shadowed_by_pending():
    # failed 优先级 5 > 6（pending 存在时仍判 failed？）——按冻结表：优先级 5
    # 先于 6，任何 failed 且无 blocked 即 failed。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "failed", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "pending"),
        ],
    )
    assert (state, code) == ("failed", "purge_blocked_by_runtime_erase_timeout")


def test_priority4_blocked_aggregates_highest_severity():
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "blocked", reason="purge_blocked_by_legal_hold"),
        ],
    )
    assert (state, code, completed) == (
        "blocked", "purge_blocked_by_legal_hold", False,
    )


def test_priority4_all_null_reasons_fall_back_operator_suppressed():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "blocked", reason=None), cp(EX_CORE, "blocked", reason=None)],
    )
    assert (state, code) == ("blocked", "operator_suppressed")


def test_priority4_unknown_reason_attributed_level12():
    # 纠偏 P1-3 语义迁移：未知非 NULL reason 不再归 level 12——dirty reason 使
    # 整个 blocked 聚合 fail closed 为 conflict（任意 owner dirty 即定，不混入
    # 合法 reason 的 severity-max）。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="mystery_reason"),
            cp(EX_CORE, "blocked", reason="purge_blocked_by_legal_hold"),
        ],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority4_blocked_not_reopened_by_later_ack():
    # 反例矩阵行 1：owner A blocked 后 owner B acked——不重开 running、不清 failure_code。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_unresolved_action"),
            cp(EX_CORE, "acked", ack_digest=E64),
        ],
        fences=[fence(EX_CORE, "erased", ack_digest=E64)],
    )
    assert (state, code, completed) == (
        "blocked", "purge_blocked_by_unresolved_action", False,
    )


def test_priority4_mixed_blocked_and_failed_excludes_failed_reason():
    # S5-A-3「failure_code 取当前 blocked checkpoint 集合」：优先级 4 只聚合
    # blocked 行；同存 failed（严重度更高）也不得混入（failed 仅在无 blocked 时
    # 经优先级 5 聚合）。变异「blocked 聚合混入 failed 行」→ 红。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "failed", reason="purge_blocked_by_legal_hold"),
        ],
    )
    assert (state, code) == ("blocked", "purge_blocked_by_runtime_erase_timeout")


def test_all_acked_missing_scan_fact_fail_closed():
    # completed 必要条件 (c) 逐 owner 可归属：任一 snapshot owner 缺 scan fact
    # 即证据缺口 → fail closed（不得默认 0 达成 completed）。变异「缺 scan 默认 0」→红。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "acked", ack_digest=E64),
            cp(EX_CORE, "acked", ack_digest=E64),
        ],
        fences=[
            fence(WS_CORE, "erased", ack_digest=E64),
            fence(EX_CORE, "erased", ack_digest=E64),
        ],
        scans=[scan(WS_CORE, 0)],  # EX_CORE 缺 scan fact
    )
    assert (state, code, completed) == (
        "blocked", "purge_owner_ack_conflict", False,
    )


def test_priority2_ack_digest_both_null_fail_closed():
    # acked 需 ack_digest 非空（CHECK）；双 NULL 显式拦截路径无测试锁定（三面 P3-5）。
    null_ack = FenceFact(
        owner_key=WS_CORE,
        state="erased",
        owner_version=1,
        purge_revision=1,
        ack_digest=None,  # 与 checkpoint 双 NULL
        ingress_digest=ingress_digest_of({"schema_version": 1, "sources": {}}),
        ingress_checkpoint={"schema_version": 1, "sources": {}},
    )
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=None)],
        fences=[null_ack],
        scans=[scan(WS_CORE, 0)],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority3_scan_tie_break_across_different_scan_codes():
    # 三面 P3-6：scan 族双 owner 非零、同严重度（level 10）但不同 scan reason 码
    # → owner_key 字典序取最小者（execution.transport.v1 < workspace.core.v1）。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_TRANSPORT],
        checkpoints=[
            cp(WS_CORE, "acked", ack_digest=E64),
            cp(EX_TRANSPORT, "acked", ack_digest=E64),
        ],
        fences=[
            fence(WS_CORE, "erased", ack_digest=E64),
            fence(EX_TRANSPORT, "erased", ack_digest=E64),
        ],
        scans=[scan(WS_CORE, 2), scan(EX_TRANSPORT, 1)],
    )
    assert (state, code) == ("blocked", "purge_blocked_by_transport_scan_nonzero")


def test_priority4_tie_break_owner_key_dict_order():
    # 同严重度（level 10 scan 族双 owner）：owner_key 字典序取最小。
    state, code, _, _, _ = result_of(
        snapshot=[WS_TRANSPORT, WS_CORE],
        checkpoints=[
            cp(WS_TRANSPORT, "blocked", reason="purge_blocked_by_transport_scan_nonzero"),
            cp(WS_CORE, "blocked", reason="workspace_body_scan_nonzero"),
        ],
    )
    assert (state, code) == ("blocked", "workspace_body_scan_nonzero")


def test_priority4_severity_beats_tie_break_regardless_of_order():
    # 反例矩阵行 6：execution.core.v1 severity 5 最高；同严重度 10 变体取字典序小者。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE, WS_TRANSPORT],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="workspace_body_scan_nonzero"),
            cp(EX_CORE, "blocked", reason="purge_blocked_by_unresolved_action"),
            cp(WS_TRANSPORT, "blocked", reason="purge_blocked_by_transport_scan_nonzero"),
        ],
    )
    assert (state, code) == ("blocked", "purge_blocked_by_unresolved_action")


def test_priority4_double_order_equivalence():
    # 反例矩阵行 4/5：提交顺序不改变结果（calculator 只看集合，天然顺序无关）。
    a = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "blocked", reason="purge_blocked_by_legal_hold"),
        ],
    )
    b = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(EX_CORE, "blocked", reason="purge_blocked_by_legal_hold"),
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_erase_timeout"),
        ],
    )
    assert a == b == (
        "blocked", "purge_blocked_by_legal_hold", "blocked", False, False,
    )


def test_priority3_all_acked_scan_nonzero_blocks_with_scan_reason():
    # 反例矩阵行 13：全 acked + 五方全过 + 扫描非零 → scan 族 failure_code（不 completed）。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        scans=[scan(WS_CORE, 2)],
    )
    assert (state, code, completed) == (
        "blocked", "workspace_body_scan_nonzero", False,
    )


def test_priority3_scan_reason_severity_and_tie_break_across_owners():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "acked", ack_digest=E64),
            cp(EX_CORE, "acked", ack_digest=E64),
        ],
        fences=[
            fence(WS_CORE, "erased", ack_digest=E64),
            fence(EX_CORE, "erased", ack_digest=E64),
        ],
        scans=[scan(WS_CORE, 0), scan(EX_CORE, 1)],
    )
    assert (state, code) == ("blocked", "execution_body_scan_nonzero")


def test_priority2_five_party_contradiction_fail_closed():
    # 反例矩阵行 16 参数化四类矛盾：fence 非 erased / ack_digest 不一致 /
    # owner_version 不匹配 / fence.purge_revision 矛盾——均 blocked + conflict，与 scan 无关。
    cases = [
        # fence 非 erased
        ([fence(WS_CORE, "active")], [scan(WS_CORE, 0)]),
        # ack_digest 不一致
        ([fence(WS_CORE, "erased", ack_digest="c" * 64)], [scan(WS_CORE, 0)]),
        # fence owner_version 不匹配
        ([fence(WS_CORE, "erased", ack_digest=E64, owner_version=2)], [scan(WS_CORE, 0)]),
        # fence.purge_revision > operation（矛盾）
        ([fence(WS_CORE, "erased", ack_digest=E64, purge_revision=2)], [scan(WS_CORE, 0)]),
    ]
    for fences, scans in cases:
        state, code, _, completed, _ = result_of(
            snapshot=[WS_CORE],
            checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
            fences=fences,
            scans=scans,
        )
        assert (state, code, completed) == (
            "blocked", "purge_owner_ack_conflict", False,
        )


def test_priority2_scan_independent_contradiction_with_nonzero_scan():
    # 「与 scan 结果无关」：扫描非零时五方矛盾仍判优先级 2（不落 scan 族）。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "active")],
        scans=[scan(WS_CORE, 3)],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority2_missing_fence_for_acked_owner_fail_closed():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        scans=[scan(WS_CORE, 0)],  # scan 证据齐备，判别五方缺 fence
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority2_ingress_digest_mismatch_fail_closed():
    tampered = FenceFact(
        owner_key=WS_CORE,
        state="erased",
        owner_version=1,
        purge_revision=1,
        ack_digest=E64,
        ingress_digest="f" * 64,  # 与 ingress_checkpoint 不符
        ingress_checkpoint={"schema_version": 1, "sources": {}},
    )
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[tampered],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority2_checkpoint_owner_version_mismatch_fail_closed():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64, owner_version=2)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_priority1_completed_positive_five_conditions():
    # 反例矩阵行 8 正向：全 acked + 五方全过 + 扫描全零 + G1/G2/G3 全过。
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "acked", ack_digest=E64),
            cp(EX_CORE, "acked", ack_digest=E64),
        ],
        fences=[
            fence(WS_CORE, "erased", ack_digest=E64),
            fence(EX_CORE, "erased", ack_digest=E64),
        ],
        scans=[scan(WS_CORE, 0), scan(EX_CORE, 0)],
    )
    assert (state, code, purge_state, completed, purged) == (
        "completed", None, "completed", True, True,
    )


def test_priority1_partial_ack_never_completed():
    # 反例矩阵行 7：部分 acked + 部分 pending → 不得 completed、purged_at 不写。
    state, code, _, completed, purged = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64), cp(EX_CORE, "pending")],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
    )
    assert (state, code, completed, purged) == ("running", None, False, False)


def test_priority1_each_completed_condition_negative():
    # 反例矩阵行 8 参数化负向：去除任一必要条件 → 不写 completed/purged_at。
    base_snapshot = [WS_CORE, EX_CORE]
    base_cps = [cp(WS_CORE, "acked", ack_digest=E64), cp(EX_CORE, "acked", ack_digest=E64)]
    base_fences = [
        fence(WS_CORE, "erased", ack_digest=E64),
        fence(EX_CORE, "erased", ack_digest=E64),
    ]
    base_scans = [scan(WS_CORE, 0), scan(EX_CORE, 0)]
    negatives = [
        # (b) pending owner
        dict(checkpoints=[cp(WS_CORE, "acked", ack_digest=E64), cp(EX_CORE, "pending")]),
        # (c) scan 非零
        dict(scans=[scan(WS_CORE, 1), scan(EX_CORE, 0)]),
        # (d) digest 不一致
        dict(fences=[fence(WS_CORE, "erased", ack_digest="c" * 64), base_fences[1]]),
        # (e) active hold（G3）
        dict(active_hold=True),
        # (a) registry drift（G1）
        dict(registry_ok=False),
        # (a) hold drift（G2）
        dict(hold_drift=True),
    ]
    for overrides in negatives:
        kwargs = dict(
            snapshot=base_snapshot,
            checkpoints=base_cps,
            fences=base_fences,
            scans=base_scans,
        )
        kwargs.update(overrides)
        state, _, _, completed, purged = result_of(**kwargs)
        assert completed is False and purged is False, f"negative case violated: {overrides}"
        assert state != "completed"


# ---------------------------------------------------------------------------
# lineage / derived conflict（S5-A-2 G4 + S5-A-8 行 20/22/23）
# ---------------------------------------------------------------------------


def test_missing_inherited_acked_row_is_g4_conflict():
    # 反例矩阵行 23：seeded（inherited_acked）缺行 = 义务丢失 → G4，绝不当 pending 重跑。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        lineage_facts=[
            lineage(WS_CORE, "valid", "inherited_acked"),
            lineage(EX_CORE, "not_applicable", "inherited_acked"),
        ],
    )
    assert (state, code, completed) == (
        "blocked", "purge_owner_ack_conflict", False,
    )


def test_missing_carried_blocked_row_is_g4_conflict():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        lineage_facts=[
            lineage(WS_CORE, "not_applicable", "native_pending"),
            lineage(EX_CORE, "not_applicable", "carried_blocked"),
        ],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_inherited_ack_valid_counts_as_acked_and_completed_reachable():
    # 反例矩阵行 22 正向：inherited ACK（fence.purge_revision < operation.purge_revision
    # + lineage valid）计入「全 owner acked」，completed 可达。
    state, code, _, completed, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64, purge_revision=0)],
        lineage_facts=[lineage(WS_CORE, "valid", "inherited_acked")],
        scans=[scan(WS_CORE, 0)],
        purge_revision=1,
    )
    assert (state, code, completed) == ("completed", None, True)


def test_inherited_fence_old_revision_without_valid_lineage_is_conflict():
    # fence.purge_revision < operation.purge_revision 但 lineage 非 valid → 五方矛盾。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "acked", ack_digest=E64)],
        fences=[fence(WS_CORE, "erased", ack_digest=E64, purge_revision=0)],
        lineage_facts=[lineage(WS_CORE, "not_applicable", "native_pending")],
        purge_revision=1,
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_carried_blocked_row_keeps_blocked_not_reopened():
    # carried_blocked 行存在：checkpoint=blocked 普通参与优先级 4（I2 无重开路径）。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_outcome_unknown")
        ],
        lineage_facts=[lineage(WS_CORE, "not_applicable", "carried_blocked")],
    )
    assert (state, code) == ("blocked", "purge_blocked_by_runtime_outcome_unknown")


def test_carried_failed_row_keeps_failed():
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "failed", reason="purge_blocked_by_runtime_erase_timeout")],
        lineage_facts=[lineage(WS_CORE, "not_applicable", "carried_failed")],
    )
    assert (state, code) == ("failed", "purge_blocked_by_runtime_erase_timeout")


# ---------------------------------------------------------------------------
# 全函数性 / 确定性
# ---------------------------------------------------------------------------


def test_total_function_no_unhandled_combinations():
    # 全 owner 状态枚举 × 缺 fence/缺行 的抽样组合都必须有唯一结果且不抛异常。
    states = ["pending", "erasing", "blocked", "failed", "acked"]
    for s1 in states:
        for s2 in states:
            r = calculate_projection(
                calc(
                    snapshot=[WS_CORE, EX_CORE],
                    checkpoints=[
                        cp(WS_CORE, s1, reason="purge_blocked_by_runtime_erase_timeout"),
                        cp(EX_CORE, s2, reason="purge_blocked_by_legal_hold"),
                    ],
                    fences=[
                        fence(WS_CORE, "erased", ack_digest=E64),
                        fence(EX_CORE, "erased", ack_digest=E64),
                    ],
                    scans=[scan(WS_CORE, 0), scan(EX_CORE, 0)],
                )
            )
            assert r.state in {"scheduled", "running", "blocked", "failed", "completed"}
            assert r.purge_state in {
                "scheduled", "running", "blocked", "failed", "completed",
            }


def test_deterministic_same_input_same_output():
    kwargs = dict(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[
            cp(WS_CORE, "blocked", reason="purge_blocked_by_runtime_erase_timeout"),
            cp(EX_CORE, "blocked", reason="purge_blocked_by_legal_hold"),
        ],
    )
    assert result_of(**kwargs) == result_of(**kwargs)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------------------
# Ready 前纠偏（本轮 P1×4 失败反例，先于生产修正）
# ---------------------------------------------------------------------------


def test_blocked_unknown_reason_fail_closed_conflict():
    # 纠偏 P1-3：unknown non-NULL reason 不得原样进入 failure_code（无 level-12
    # 归属）——稳定 fail closed 为 blocked + purge_owner_ack_conflict。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "blocked", reason="mystery_reason")],
    )
    assert (state, code) == ("blocked", "purge_owner_ack_conflict")


def test_blocked_coordinator_only_reason_fail_closed_conflict():
    # 纠偏 P1-3：checkpoint 写入 level 2/3/4 coordinator-only reason（participant
    # 越域写的脏形态）→ 不得原样进入 failure_code → blocked + conflict。
    for dirty_reason in (
        "blocked_registry_changed",
        "blocked_hold_revision_changed",
        "purge_owner_ack_conflict",
    ):
        state, code, _, _, _ = result_of(
            snapshot=[WS_CORE],
            checkpoints=[cp(WS_CORE, "blocked", reason=dirty_reason)],
        )
        assert (state, code) == ("blocked", "purge_owner_ack_conflict"), dirty_reason


def test_null_blocked_reason_operator_suppressed_unchanged():
    # 纠偏 P1-3 边界保持：NULL blocked reason → operator_suppressed 冻结语义不变。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE, EX_CORE],
        checkpoints=[cp(WS_CORE, "blocked", reason=None), cp(EX_CORE, "blocked", reason=None)],
    )
    assert (state, code) == ("blocked", "operator_suppressed")


def test_failed_all_null_reason_none_unchanged():
    # 纠偏 P1-3 边界保持：failed 全 NULL → failure_code=None 冻结语义不变。
    state, code, _, _, _ = result_of(
        snapshot=[WS_CORE],
        checkpoints=[cp(WS_CORE, "failed", reason=None)],
    )
    assert (state, code) == ("failed", None)


def test_capability_digest_mismatch_blocks_completed():
    # 纠偏 P1-4：checkpoint.capability_digest != snapshot capability_digest——
    # 即使全 acked、fence erased、scan 全零，也不得 completed；blocked +
    # purge_owner_ack_conflict。变异「删除 capability 校验」→ 红。
    mismatched = CheckpointFact(
        owner_key=WS_CORE,
        state="acked",
        reason_code=None,
        attempt=0,
        owner_version=1,
        capability_digest="c" * 64,  # != snapshot D64
        ack_digest=E64,
        checkpoint_digest=None,
    )
    state, code, purge_state, completed, purged = result_of(
        snapshot=[WS_CORE],
        checkpoints=[mismatched],
        fences=[fence(WS_CORE, "erased", ack_digest=E64)],
        scans=[scan(WS_CORE, 0)],
    )
    assert (state, code, purge_state, completed, purged) == (
        "blocked", "purge_owner_ack_conflict", "blocked", False, False,
    )
