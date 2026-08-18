"""R1-S5 SCH-D：RetryReconcileService——内部 inspect/retry/reconcile 服务边界。

契约：R1-S5-C S5-C-1/2 + R1-S5-A S5-A-3（族 B 封闭白名单）。本服务只实现
**服务边界**（scheduler 内部 API 形状），不实现 HTTP/CLI；只写 owner-scoped 事实，
禁 force-skip ACK、无证据写 erased/acked/completed。

- ``inspect``：只读返回 operation + 逐 owner checkpoint/fence 摘要（无副作用）。
- ``retry``：显式重试——reason 白名单（S5-B-2 reopenable 域：erase_timeout /
  adapter_unavailable / scan 族 + pre-window gate）批准才重开 pending；**明确排除
  输出态 3/5/6**（outcome_unknown / settlement_deadline_expired /
  adapter_unresolvable，零 adapter 调用、零状态推进）。
- ``reconcile``：证据型显式收口——经 settlement adapter recovery 以 evidence
  落账（owner-scoped）；lookup None = 不可判定，不据此写 erased/acked。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.settlement import SettlementService

# S5-B-2 reopenable 域（与 SCH-B 编排器白名单同源；本地镜像避免循环导入）。
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
# S5-C 输出态 3/5/6（禁重试）。
_REJECT_SUFFIXES = (
    "_outcome_unknown",
    "_settlement_deadline_expired",
    "_adapter_unresolvable",
)


def _is_retryable_reason(reason: str | None) -> bool:
    if reason is None:
        return False
    return reason in _PRE_WINDOW_GATE_REASONS or reason.endswith(_RETRYABLE_SUFFIXES)


def _is_reject_reason(reason: str | None) -> bool:
    if reason is None:
        return False
    return reason.endswith(_REJECT_SUFFIXES)


@dataclass(frozen=True, slots=True)
class RetryVerdict:
    allowed: bool
    reason: str | None = None  # 拒绝原因（allowed=False 时）


@dataclass(frozen=True, slots=True)
class ReconcileVerdict:
    applied: bool
    detail: str


class RetryReconcileService:
    """内部 inspect/retry/reconcile 服务边界（无 HTTP/CLI，无生产 wiring）。"""

    def __init__(
        self, session: AsyncSession, *, settlement: SettlementService
    ) -> None:
        self._session = session
        self._settlement = settlement

    # -- inspect ------------------------------------------------------------

    async def inspect(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> dict[str, object]:
        """只读返回 operation + 逐 owner checkpoint/fence 摘要（零副作用）。"""
        op = (
            await self._session.execute(
                text(
                    "SELECT id, purge_revision, state, failure_code, lease_epoch "
                    "FROM metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :t AND id = :op AND conversation_id = :c"
                ),
                {"t": tenant_id, "op": purge_operation_id, "c": conversation_id},
            )
        ).mappings().one_or_none()
        if op is None:
            raise ValueError(
                f"purge operation {purge_operation_id} not found for inspect"
            )
        owners = (
            await self._session.execute(
                text(
                    "SELECT cp.owner_key, cp.state AS cp_state, cp.reason_code, "
                    "cp.attempt, f.state AS fence_state "
                    "FROM metaedu.agent_conversation_purge_owners cp "
                    "LEFT JOIN metaedu.agent_erasure_fences f "
                    "ON f.tenant_id = cp.tenant_id "
                    "AND f.conversation_id = :c AND f.owner_key = cp.owner_key "
                    "WHERE cp.tenant_id = :t AND cp.purge_operation_id = :op "
                    "ORDER BY cp.owner_key"
                ),
                {"t": tenant_id, "c": conversation_id, "op": purge_operation_id},
            )
        ).mappings().all()
        return {
            "operation": dict(op),
            "owners": [dict(row) for row in owners],
        }

    # -- retry --------------------------------------------------------------

    async def retry(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> RetryVerdict:
        """S5-A-3 显式重试：白名单批准才重开 pending；3/5/6 / NULL / dirty 拒绝
        零写。operation 必须仍为 top revision（G1/G2 走 rebuild，不适用显式重试）。"""
        # Conversation-first 锁序（S5-A-4 S1 全局互斥；禁 operation→Conversation 逆序）。
        conv = (
            await self._session.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_conversations "
                    "WHERE tenant_id = :t AND id = :c FOR UPDATE"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).scalar_one_or_none()
        if conv is None:
            raise ValueError(f"conversation {conversation_id} not found for retry")
        op = (
            await self._session.execute(
                text(
                    "SELECT purge_revision, state FROM "
                    "metaedu.agent_conversation_purges "
                    "WHERE tenant_id = :t AND id = :op AND conversation_id = :c "
                    "FOR UPDATE"
                ),
                {"t": tenant_id, "op": purge_operation_id, "c": conversation_id},
            )
        ).mappings().one_or_none()
        if op is None:
            raise ValueError(f"purge operation {purge_operation_id} not found for retry")
        if op["purge_revision"] != conv:
            raise ValueError(
                "operation not top revision; G1/G2 drift must go through rebuild, "
                "not explicit retry"
            )
        cp = (
            await self._session.execute(
                text(
                    "SELECT state, reason_code FROM "
                    "metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :t AND purge_operation_id = :op "
                    "AND owner_key = :k FOR UPDATE"
                ),
                {"t": tenant_id, "op": purge_operation_id, "k": owner_key},
            )
        ).mappings().one_or_none()
        if cp is None or cp["state"] != "blocked":
            return RetryVerdict(allowed=False, reason="checkpoint not blocked")
        reason = cp["reason_code"]
        if _is_reject_reason(reason):
            return RetryVerdict(
                allowed=False, reason="3/5/6 reconcile-only，禁止重试（零写）"
            )
        if not _is_retryable_reason(reason):
            return RetryVerdict(
                allowed=False, reason="reason 不在重试白名单（dirty/未知），零写"
            )
        # 白名单批准：blocked → pending，清 reason + attempt 归零（重跑义务）。
        await self._session.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "state = 'pending', reason_code = NULL, attempt = 0 "
                "WHERE tenant_id = :t AND purge_operation_id = :op AND owner_key = :k"
            ),
            {"t": tenant_id, "op": purge_operation_id, "k": owner_key},
        )
        await self._session.flush()
        return RetryVerdict(allowed=True)

    # -- reconcile ----------------------------------------------------------

    async def reconcile(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> ReconcileVerdict:
        """证据型显式 reconcile：经 settlement 以 evidence 收口（owner-scoped）。
        禁止 force-skip ACK——无证据不写 erased/acked/completed。"""
        # 复用 settlement 主入口：对窗口态/已落账/ACK-lost 均以同一 state machine
        # 收口；reconcile 语义 = 显式触发一次 settlement（同 token 重验 + CAS 收敛）。
        await self._settlement.closeout_erasing(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_operation_id=purge_operation_id,
            owner_key=owner_key,
        )
        return ReconcileVerdict(applied=True, detail="settlement 收口已执行（CAS 幂等）")


__all__ = ["RetryReconcileService", "RetryVerdict", "ReconcileVerdict"]
