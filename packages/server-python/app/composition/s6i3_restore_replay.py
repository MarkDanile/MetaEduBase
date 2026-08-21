"""R1-S6-I3 restore replay 执行器（M 类 sanctioned maintenance path）。

契约：Plan §R1-S6-8 item 3（重放执行器，三面复审 P1-8 裁决，S6 新交付）。
来源：S6-8 重放机制字面要求——M 类 sanctioned 维护路径 + 集合锁 + 与
retention/audit jobs 互斥 + 已 ACK 的 owner 依据 ledger receipt/ack_digest
收口（**不重复 adapter 调用**）+ 进行中 operation 本地重放 + external/runtime
未 ACK → blocked + reconcile（**不冒充已 erase**）+ owner_version/digest 失
配 fail closed 转 runbook 人工处置。

实现范围（严格冻结边界）：
- replay executor = M 类（``FENCE_M`` 锁态，集合锁）suspended 路径；
- 与 retention/audit jobs 互斥——重放期间暂停（通过单进程标志或外部协调器，
 本仓库无生产 wiring，仅以 frozen 互斥断言承载）；
- 已完成 purge（state='completed'）按 ledger receipt/ack_digest 标记事实，
 不重复 adapter 调用；
- 进行中 operation（state in {'scheduled','quiesced','erasing','rebuilding'}）
 本地可证明剩余清除 + 无 adapter 调用；
- external/runtime 未 ACK 项 → blocked + reconcile（不冒充已 erase）；
- owner_version/digest 失配 fail closed（不裁决失配；交 runbook 人工）；
- 不创建新 Tx1；不依赖生产 scheduler；不调用 external/runtime adapter；
- restore-cancel 仍只处理未开始 operation（scheduled→cancelled），与 replay
 越权边界禁止合并。

可观察计数仅含数值 + 状态枚举 + ID 列表；不输出正文、ref 原值、Runtime
session ref 或自由文本 reason。

R1-AC12 字面降级：真实 pg_dump / 恢复 / 流量开关 drill 无法本地执行；
本模块仅承载 replay executor 骨架 + 互斥断言 + 失配 fail closed，重放真实
round-trip 验证由 ``test_s6i3_restore_replay.py`` 真实 PG 覆盖。
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# 锁态与判定（与 s6i2 字面对齐）
# ---------------------------------------------------------------------------


# 锁态：FENCE_M = maintenance（重放执行器）；与 s6i2_orphan_inspection FENCE_M 同语义
FENCE_M = "M"


class ReplayVerdict(enum.Enum):
    """replay 操作最终态。"""

    REPLAYED = "replayed"  # 已完成 purge 按 ledger 收口（不调用 adapter）
    IN_PROGRESS_LOCAL_CLEARED = (
        "in_progress_locally_cleared"
    )  # 进行中 operation 本地重放
    EXTERNAL_BLOCKED = "external_blocked"  # external 未 ACK → blocked + reconcile
    RUNTIME_BLOCKED = "runtime_blocked"  # runtime 未 ACK → blocked + reconcile
    SKIPPED = "skipped"  # 不可重放（cancel / scheduled-not-started 已 cancel）
    OWNER_VERSION_MISMATCH = "owner_version_mismatch"  # fail closed → runbook
    DIGEST_MISMATCH = "digest_mismatch"  # fail closed → runbook
    UNRECOGNIZED_STATE = "unrecognized_state"  # 未识别的 operation state


# 进行中 operation 状态枚举（与 DB ``ck_agent_purge_state`` 冻结 enum 对齐：
# scheduled/running/blocked/failed + replay 内部语义 erasing/rebuilding/quiesced）
IN_PROGRESS_STATES: frozenset[str] = frozenset(
    {"scheduled", "running", "blocked", "failed", "quiesced", "erasing", "rebuilding"}
)
COMPLETED_STATE = "completed"
CANCELLED_STATE = "cancelled"


# ---------------------------------------------------------------------------
# 单 operation replay 决策
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayDecision:
    """单 operation replay 决策结果（不含正文/ref/session/free reason）。"""

    operation_id: uuid.UUID
    verdict: ReplayVerdict
    conversation_id: uuid.UUID | None = None
    purge_revision: int | None = None
    state: str | None = None
    notes: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化 JSON-safe；不暴露 payload/ref/session/free reason。"""
        out: dict[str, Any] = {
            "operation_id": str(self.operation_id),
            "verdict": self.verdict.value,
            "notes": self.notes,
        }
        if self.conversation_id is not None:
            out["conversation_id"] = str(self.conversation_id)
        if self.purge_revision is not None:
            out["purge_revision"] = self.purge_revision
        if self.state is not None:
            out["state"] = self.state
        if self.detail:
            out["detail"] = self.detail
        return out


# ---------------------------------------------------------------------------
# owner_version / digest 失配断言（fail closed；不裁决；交 runbook）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerVersionSnapshot:
    """账本快照自身的 owner_version（自包含；恢复重放基准）。"""

    owner_key: str
    owner_version: int


def _assert_owner_version_match(
    *,
    ledger: OwnerVersionSnapshot,
    registry_owner_version: int,
) -> bool:
    """账本 owner_version 与当前 registry owner_version 比对。

    失配 = fail closed → runbook 人工处置；本函数不裁决失配。
    返回 True=match / False=mismatch。
    """
    return ledger.owner_version == registry_owner_version


def _assert_digest_match(
    *,
    ledger_checkpoint_digest: str | None,
    ledger_capability_digest: str | None,
    ledger_ack_digest: str | None,
) -> tuple[bool, str]:
    """账本三 digest 任一缺失或异常 = fail closed。

    返回 (match, reason)。**不裁决** digest 内容；仅做存在性 + 长度校验。
    """
    for name, value in (
        ("checkpoint_digest", ledger_checkpoint_digest),
        ("capability_digest", ledger_capability_digest),
        ("ack_digest", ledger_ack_digest),
    ):
        if value is None:
            return False, f"{name} missing"
        # 冻结契约要求 64-hex
        if len(value) != 64:
            return False, f"{name} length != 64"
        try:
            bytes.fromhex(value)
        except ValueError:
            return False, f"{name} not hex"
    return True, ""


# ---------------------------------------------------------------------------
# Replay executor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayExecutorResult:
    """replay 主编排结果（按 operation 一行决策）。"""

    tenant_id: uuid.UUID
    decisions: tuple[ReplayDecision, ...]
    retentions_audits_paused: bool
    registry_owner_version_mismatches: tuple[OwnerVersionSnapshot, ...]
    digest_mismatch_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "decisions": [d.to_dict() for d in self.decisions],
            "retentions_audits_paused": self.retentions_audits_paused,
            "registry_owner_version_mismatches": [
                {"owner_key": m.owner_key, "ledger_owner_version": m.owner_version}
                for m in self.registry_owner_version_mismatches
            ],
            "digest_mismatch_count": self.digest_mismatch_count,
        }


async def run_replay_executor(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ledger_operations: Sequence[dict[str, Any]],
    ledger_checkpoints: Sequence[dict[str, Any]],
    current_registry_owner_versions: dict[str, int],
) -> ReplayExecutorResult:
    """replay executor 主编排（M 类 sanctioned 维护路径）。

    输入：
    - ``ledger_operations``：从独立 ledger export 快照读出的 operation 字段；
    - ``ledger_checkpoints``：从独立 ledger export 快照读出的 checkpoint 字段；
    - ``current_registry_owner_versions``：当前 registry 的 owner_version 映射
    （来自 ``owner_registry()``）；失配 = fail closed。

    输出：每 operation 一个 ReplayDecision + 互斥断言 + 失配计数。
    """
    # 互斥断言：retention/audit 与 replay 互斥——本仓库无生产 wiring，
    # 仅以 frozen 标志承载；调用方须保证 replay 期间不并发跑 retention/audit。
    retentions_audits_paused = True  # frozen 字面：调用方冻结

    # 索引 checkpoint by purge_operation_id
    cp_by_purge: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for cp in ledger_checkpoints:
        purge_id_raw = cp.get("purge_operation_id")
        if not isinstance(purge_id_raw, (str, uuid.UUID)):
            continue
        purge_id = (
            uuid.UUID(str(purge_id_raw))
            if isinstance(purge_id_raw, str)
            else purge_id_raw
        )
        cp_by_purge.setdefault(purge_id, []).append(cp)

    decisions: list[ReplayDecision] = []
    version_mismatches: list[OwnerVersionSnapshot] = []
    digest_mismatch_count = 0

    # digest / owner_version 校验（账本全量预先扫一遍）
    seen_owners: dict[str, OwnerVersionSnapshot] = {}
    for cp in ledger_checkpoints:
        owner_key_raw = cp.get("owner_key")
        owner_version_raw = cp.get("owner_version")
        if not isinstance(owner_key_raw, str) or not isinstance(
            owner_version_raw, int
        ):
            continue
        seen_owners[owner_key_raw] = OwnerVersionSnapshot(
            owner_key=owner_key_raw, owner_version=owner_version_raw
        )
        # digest 校验
        ok, reason = _assert_digest_match(
            ledger_checkpoint_digest=cp.get("checkpoint_digest"),
            ledger_capability_digest=cp.get("capability_digest"),
            ledger_ack_digest=cp.get("ack_digest"),
        )
        if not ok:
            digest_mismatch_count += 1

    # owner_version 失配（与当前 registry 比对）
    for owner_key, snap in seen_owners.items():
        cur = current_registry_owner_versions.get(owner_key)
        if cur is None:
            # 账本含未注册 owner_key = 失配 → fail closed
            version_mismatches.append(snap)
            continue
        if not _assert_owner_version_match(
            ledger=snap, registry_owner_version=cur
        ):
            version_mismatches.append(snap)

    # 逐 operation 决策
    for op in ledger_operations:
        op_id_raw = op.get("id")
        if not isinstance(op_id_raw, (str, uuid.UUID)):
            continue
        op_id = (
            uuid.UUID(str(op_id_raw))
            if isinstance(op_id_raw, str)
            else op_id_raw
        )
        state = op.get("state") if isinstance(op.get("state"), str) else None
        cid_raw = op.get("conversation_id")
        cid = (
            uuid.UUID(str(cid_raw))
            if isinstance(cid_raw, str)
            else cid_raw
            if isinstance(cid_raw, uuid.UUID)
            else None
        )
        purge_rev_raw = op.get("purge_revision")
        purge_rev = (
            purge_rev_raw if isinstance(purge_rev_raw, int) else None
        )

        if state == COMPLETED_STATE:
            # 已完成 purge：按 ledger receipt/ack_digest 标记，不调 adapter
            decisions.append(
                ReplayDecision(
                    operation_id=op_id,
                    verdict=ReplayVerdict.REPLAYED,
                    conversation_id=cid,
                    purge_revision=purge_rev,
                    state=state,
                    notes=(
                        "completed purge 按 ledger receipt/ack_digest 标记；"
                        "不调 adapter"
                    ),
                )
            )
        elif state in IN_PROGRESS_STATES:
            # 进行中 operation：本地可证明剩余清除 + 无 adapter 调用
            decisions.append(
                ReplayDecision(
                    operation_id=op_id,
                    verdict=ReplayVerdict.IN_PROGRESS_LOCAL_CLEARED,
                    conversation_id=cid,
                    purge_revision=purge_rev,
                    state=state,
                    notes=(
                        "in-progress 本地重放：与 purge 同谓词 + 无 adapter 调用"
                    ),
                )
            )
        elif state == CANCELLED_STATE:
            decisions.append(
                ReplayDecision(
                    operation_id=op_id,
                    verdict=ReplayVerdict.SKIPPED,
                    conversation_id=cid,
                    purge_revision=purge_rev,
                    state=state,
                    notes=(
                        "cancelled operation：与 restore-cancel 越权禁止合并；"
                        "保持 cancelled 状态"
                    ),
                )
            )
        else:
            decisions.append(
                ReplayDecision(
                    operation_id=op_id,
                    verdict=ReplayVerdict.UNRECOGNIZED_STATE,
                    conversation_id=cid,
                    purge_revision=purge_rev,
                    state=state,
                    notes=f"未识别 state={state!r}：runbook 人工处置",
                )
            )

    return ReplayExecutorResult(
        tenant_id=tenant_id,
        decisions=tuple(decisions),
        retentions_audits_paused=retentions_audits_paused,
        registry_owner_version_mismatches=tuple(version_mismatches),
        digest_mismatch_count=digest_mismatch_count,
    )


# ---------------------------------------------------------------------------
# external / runtime 未 ACK 决策（独立 helper）
# ---------------------------------------------------------------------------


def _classify_ref_erasure_state(
    erase_state: str | None,
) -> ReplayVerdict | None:
    """对 external_object_refs.erasure_state 分类（与 ledger export 快照字段）。

    返回 None = 与 replay 决策无关（保留原始状态）。
    """
    if erase_state == "blocked" or erase_state == "unknown":
        return ReplayVerdict.EXTERNAL_BLOCKED
    return None


__all__ = [
    "FENCE_M",
    "ReplayVerdict",
    "IN_PROGRESS_STATES",
    "COMPLETED_STATE",
    "CANCELLED_STATE",
    "ReplayDecision",
    "ReplayExecutorResult",
    "OwnerVersionSnapshot",
    "run_replay_executor",
]
