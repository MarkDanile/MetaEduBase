"""R1-S5 SCH-C：registry snapshot diff 与 predecessor lineage 派生（纯函数核心）。

契约：Plan §R1-S5-B S5-B-2/3/4——owner obligation 全函数矩阵、schema-free
predecessor evidence lineage（六项）、`expected_obligation_kind` 权威公式。

本模块是 **stage-1（seeding）与 stage-2（coordinator 聚合）共用的纯派生逻辑**：
- ``diff_snapshots``：predecessor.registry_snapshot ⊕ current.registry_snapshot
  的逐 owner change 分类（unchanged/added/removed/re-added/version-changed）。
  两端均为**持久快照**，不得用 live installed registry（live drift 只归 G1）。
- ``compute_lineage``：对每个 current snapshot owner 派生
  ``(lineage_status, expected_obligation_kind)``，输入 = current snapshot +
  predecessor operation/checkpoint/fence 持久事实（S5-C terminal facts 编码于
  predecessor checkpoint.state × reason_code × fence.state），**不读当前待判定
  checkpoint**（无循环依赖）。

derived 非持久、重启后重算同值；信任锚点唯一 = ``fence.ack_digest``（原生终态
锚点），``checkpoint_digest`` 仅审计副本不参与信任判定（S5-B-3）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.composition.projection_calculator import LineageFact
from app.shared.schemas.canonical_json import canonical_digest

# G1/G2 coordinator-level gate failure_code（predecessor 必须是其中之一 blocked）。
_G1_G2_FAILURE_CODES = frozenset(
    {"blocked_registry_changed", "blocked_hold_revision_changed"}
)

# S5-B-2 重开义务域（与 orchestrator 白名单同源，本地镜像避免循环导入）：
# erase_timeout / adapter_unavailable / scan 族 + pre-window gate。
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
# S5-C 输出态 3/5/6（terminal facts，禁重开、禁二次 adapter 调用）。
_CARRY_REASON_SUFFIXES = (
    "_outcome_unknown",
    "_settlement_deadline_expired",
    "_adapter_unresolvable",
)


def _is_retryable_reason(reason: str) -> bool:
    return reason in _PRE_WINDOW_GATE_REASONS or reason.endswith(_RETRYABLE_SUFFIXES)


def _is_carry_reason(reason: str) -> bool:
    return reason.endswith(_CARRY_REASON_SUFFIXES)


@dataclass(frozen=True, slots=True)
class OwnerSnapshotEntry:
    owner_key: str
    owner_version: int
    capability_digest: str


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """predecessor ⊕ current 的逐 owner change 分类。

    ``added`` = current 有、predecessor snapshot 无（是否 re-added 由调用方按
    历史 fence 行存在性区分——fence PK 跨 revision 存活）。``removed`` =
    predecessor 有、current 无。
    """

    added: frozenset[str]
    removed: frozenset[str]
    version_changed: frozenset[str]  # owner_key 不变、version/capability 变
    unchanged: frozenset[str]


def _index(snapshot: list[OwnerSnapshotEntry]) -> dict[str, OwnerSnapshotEntry]:
    return {entry.owner_key: entry for entry in snapshot}


def diff_snapshots(
    predecessor: list[OwnerSnapshotEntry],
    current: list[OwnerSnapshotEntry],
) -> SnapshotDiff:
    """逐 owner diff（两端持久快照，排序输入）。"""
    old = _index(predecessor)
    new = _index(current)
    added = frozenset(k for k in new if k not in old)
    removed = frozenset(k for k in old if k not in new)
    version_changed = frozenset(
        k
        for k in new
        if k in old
        and (
            new[k].owner_version != old[k].owner_version
            or new[k].capability_digest != old[k].capability_digest
        )
    )
    unchanged = frozenset(
        k for k in new if k in old and k not in version_changed
    )
    return SnapshotDiff(
        added=added,
        removed=removed,
        version_changed=version_changed,
        unchanged=unchanged,
    )


@dataclass(frozen=True, slots=True)
class PredecessorOwnerFact:
    """predecessor 某 owner 的持久事实（checkpoint 状态 × fence 状态）。"""

    checkpoint_state: str | None  # None = 缺行
    checkpoint_reason: str | None
    checkpoint_owner_version: int | None
    checkpoint_capability_digest: str | None
    checkpoint_ack_digest: str | None
    fence_state: str | None  # None = 缺 fence 行
    fence_owner_version: int | None
    fence_purge_revision: int | None
    fence_ack_digest: str | None
    fence_ingress_digest: str | None
    fence_ingress_checkpoint: dict | None


def _six_item_lineage(
    *,
    fact: PredecessorOwnerFact,
    current_entry: OwnerSnapshotEntry,
    current_revision: int,
) -> bool:
    """S5-B-3 继承证据六项（缺一不可）——用于 inherited ACK 判定。

    仅验证 unchanged/identical owner 的合法继承；版本/capability 变化不在
    此路径（case E 另行处理）。
    """
    if fact.checkpoint_state != "acked":
        return False  # 六项 2
    if fact.fence_state != "erased":
        return False  # 六项 3
    if (
        fact.checkpoint_owner_version != current_entry.owner_version
        or fact.fence_owner_version != current_entry.owner_version
        or fact.checkpoint_capability_digest != current_entry.capability_digest
    ):
        return False  # 六项 4
    if (
        fact.checkpoint_ack_digest is None
        or fact.fence_ack_digest is None
        or fact.checkpoint_ack_digest != fact.fence_ack_digest
    ):
        return False  # 六项 5a（信任锚点一致）
    if (
        fact.fence_ingress_digest is None
        or fact.fence_ingress_checkpoint is None
        or fact.fence_ingress_digest
        != canonical_digest(fact.fence_ingress_checkpoint)
    ):
        return False  # 六项 5b（ingress 证据自洽）
    # 六项 6（inherited：fence.purge_revision < operation.purge_revision）。
    return not (
        fact.fence_purge_revision is None
        or fact.fence_purge_revision >= current_revision
    )

def compute_lineage(
    *,
    snapshot: list[OwnerSnapshotEntry],
    predecessor_snapshot: list[OwnerSnapshotEntry] | None,
    predecessor_facts: dict[str, PredecessorOwnerFact],
    current_revision: int,
    historical_fences: frozenset[str] | None = None,
) -> dict[str, LineageFact]:
    """对 current snapshot 逐 owner 派生 LineageFact。

    ``predecessor_snapshot=None`` = 无 predecessor（原生路径：全 not_applicable/
    native_pending）。``historical_fences`` = 历史 fence owner_key 集合（区分
    added vs re-added——added 无历史 fence，re-added 有）。
    """
    historical = historical_fences or frozenset()
    if predecessor_snapshot is None:
        return {
            entry.owner_key: LineageFact(
                owner_key=entry.owner_key,
                lineage_status="not_applicable",
                expected_obligation_kind="native_pending",
            )
            for entry in snapshot
        }

    diff = diff_snapshots(predecessor_snapshot, snapshot)
    result: dict[str, LineageFact] = {}

    for entry in snapshot:
        key = entry.owner_key
        fact = predecessor_facts.get(key)
        if key in diff.added:
            # 新增 owner（无历史 fence）→ 新义务；re-added（有历史 fence）另行分派。
            if key in historical:
                # re-added：按历史 checkpoint/fence 全函数分派（S5-B-2 case C）。
                result[key] = _re_added_lineage(entry, fact, current_revision)
            else:
                result[key] = LineageFact(
                    owner_key=key,
                    lineage_status="not_applicable",
                    expected_obligation_kind="native_pending",
                )
        elif key in diff.unchanged:
            result[key] = _unchanged_lineage(entry, fact, current_revision)
        elif key in diff.version_changed:
            result[key] = _version_changed_lineage(entry, fact, current_revision)
        else:  # removed：不在 current snapshot，不产出（rebuild 层处理 fail closed）
            continue
    return result


def _unchanged_lineage(
    entry: OwnerSnapshotEntry,
    fact: PredecessorOwnerFact | None,
    current_revision: int,
) -> LineageFact:
    if fact is None:
        # predecessor 缺该 owner checkpoint/fence → 矛盾（S5-B-2 缺行 fail closed）。
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    cp = fact.checkpoint_state
    fence = fact.fence_state
    if cp == "acked" and fence == "erased":
        if _six_item_lineage(
            fact=fact, current_entry=entry, current_revision=current_revision
        ):
            return LineageFact(entry.owner_key, "valid", "inherited_acked")
        return LineageFact(entry.owner_key, "conflict", "inherited_acked")
    if cp == "acked":  # acked 但 fence 非 erased → 矛盾
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    if cp == "failed" and fence != "erased":
        return LineageFact(entry.owner_key, "not_applicable", "carried_failed")
    if cp == "failed":  # failed × erased → dirty-data
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    if cp == "blocked":
        reason = fact.checkpoint_reason
        if fence == "erased":
            # blocked × erased = S5-C-1 ACK-lost 输入态，非 rebuild 可判义务，dirty-data。
            return LineageFact(entry.owner_key, "conflict", "native_pending")
        if reason is None:
            # NULL reason 不得落入通用 pending 分支（S5-B-2 硬约束④）。
            return LineageFact(entry.owner_key, "conflict", "native_pending")
        if _is_carry_reason(reason):
            return LineageFact(entry.owner_key, "not_applicable", "carried_blocked")
        if not _is_retryable_reason(reason):
            # 非白名单 reason → dirty-data（S5-B-2 兜底）。
            return LineageFact(entry.owner_key, "conflict", "native_pending")
        # reopenable（erase_timeout/adapter_unavailable/scan 族 + pre-window gate）
        # → 义务重开。
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    if cp == "pending":
        if fence == "erased":
            return LineageFact(entry.owner_key, "conflict", "native_pending")
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    if cp == "erasing":
        # quiesce 门禁应在 rebuild 层拦截；若漏入则 fail closed。
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    # 缺行（checkpoint_state None）但 fact 存在（不可能——fact 即 checkpoint 聚合）
    return LineageFact(entry.owner_key, "conflict", "native_pending")


def _re_added_lineage(
    entry: OwnerSnapshotEntry,
    fact: PredecessorOwnerFact | None,
    current_revision: int,
) -> LineageFact:
    """S5-B-2 case C：re-added（有历史 fence）按历史 checkpoint × fence 分派。

    历史事实来自 predecessor（若 predecessor 无该 owner 行，则 re-added 的
    历史在更早 revision——SCH-C 用 predecessor_facts 里的 fence 态判定）。
    """
    if fact is None:
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    if fact.checkpoint_state is None:
        if fact.fence_state == "erased":
            # 历史 fence erased 但 predecessor 缺 checkpoint：无法验证「历史 acked」
            # （item 2），锚点缺失 → fail closed（S5-B-2 case C 锚点缺失回滚）。
            return LineageFact(entry.owner_key, "conflict", "native_pending")
        # 缺 cp 且 fence 非 erased → 义务重开 pending（缺行不视为已完成）。
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    return _unchanged_lineage(entry, fact, current_revision)


def _version_changed_lineage(
    entry: OwnerSnapshotEntry,
    fact: PredecessorOwnerFact | None,
    current_revision: int,
) -> LineageFact:
    """S5-B-2 case E：version/capability 变化。

    - active fence → 义务重开 + versioned fence migration（native_pending）。
    - erased fence → fail closed（旧 capability 清除不可继承/重跑）。
    - erasing/blocked → 按 settlement fact（blocked carry 或重开）。
    """
    if fact is None or fact.fence_state is None:
        # 无历史 fence → 视同新 owner（实际上 version-changed 必有历史 fence）。
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    if fact.fence_state == "active":
        return LineageFact(entry.owner_key, "not_applicable", "native_pending")
    if fact.fence_state == "erased":
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    # erasing/blocked：按 checkpoint reason 分态（S5-C terminal facts）。
    reason = fact.checkpoint_reason
    if reason is None:
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    if _is_carry_reason(reason):
        return LineageFact(entry.owner_key, "not_applicable", "carried_blocked")
    if not _is_retryable_reason(reason):
        return LineageFact(entry.owner_key, "conflict", "native_pending")
    return LineageFact(entry.owner_key, "not_applicable", "native_pending")


__all__ = [
    "OwnerSnapshotEntry",
    "PredecessorOwnerFact",
    "SnapshotDiff",
    "compute_lineage",
    "diff_snapshots",
]
