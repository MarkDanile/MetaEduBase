"""R1-S4-D-A：``execution.transport.v1`` erasure participant。

清除范围（Plan §R1-S4-D 契约细化 D-A-1，两侧对称）：

- **outbox**（``agent_execution_outbox``）：正文事实谓词 ``payload_inline IS
  NOT NULL OR payload_ref IS NOT NULL`` 命中即清（**不排除 ``cancelled``**），
  统一清 ``payload_inline``/``payload_ref`` 转 ``status='suppressed'`` 保留
  ``payload_digest``；``cancelled`` 行保留 S4-C 终态证据（``decision_*`` 四元
  ——``ck_agent_exec_outbox_decision`` 全有或全无，不得清除或重写）；同事务把
  对应 Run 置 ``output_publish_state='suppressed'``（S3-E 同模式）。
- **inbox**（``agent_execution_inbox``）状态矩阵：``processing`` ->
  ``rejected``+tombstone；已 ``consumed/rejected`` 保留原 status 仅补幂等
  tombstone；已 tombstone digest 精确匹配 no-op / 不匹配 fail closed
  （``ExecutionIntegrationConflictError``）。
- **scan 显式绑定维度**：WHERE 恒带 ``tenant_id + conversation_id``（+ owner
  隐含），禁止裸谓词全表扫描。
- **receipt tombstone digest**：复用 S4-C Tx1 已提交的 ``snapshot_digest``
  同一 helper + 冻结键名（不得自造）。

锁序 / ACK / fencing 由共享基类 ``TransportErasureParticipantBase`` 承担。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.transport_erasure_participant import (
    TransportBodyScan,
    TransportErasureParticipantBase,
)
from app.contexts.agent_execution.domain.errors import (
    ExecutionIntegrationConflictError,
)

#: 本 participant 持有的 transport owner（registry 固定 key）。
EXECUTION_TRANSPORT_OWNER = "execution.transport.v1"


class ExecutionTransportErasureParticipant(TransportErasureParticipantBase):
    """execution.transport.v1：清 execution outbox/inbox transport 正文 + ACK。

    registry 全程保持 ``erase_available=False``（S4-D-A）：入口
    ``require_capability(owner, "erase")`` fail closed 是预期。
    """

    owner_key = EXECUTION_TRANSPORT_OWNER

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # --- 正文事实谓词 scan（显式绑定 tenant + conversation 维度）--------------

    async def scan_transport_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> TransportBodyScan:
        """final transport scan：outbox 正文残留 + inbox 未决 receipt。

        谓词 = 正文事实（``payload_inline IS NOT NULL OR payload_ref IS NOT
        NULL``，**不排除 ``cancelled``**）+ 显式 ``tenant_id + conversation_id``
        维度（定向复核 P2-1：禁止裸谓词全表扫描）。
        """
        outbox_rows = (
            await self._session.scalar(
                text(
                    "SELECT count(*) FROM metaedu.agent_execution_outbox "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND (payload_inline IS NOT NULL OR payload_ref IS NOT NULL)"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        )
        inbox_rows = (
            await self._session.scalar(
                text(
                    "SELECT count(*) FROM metaedu.agent_execution_inbox "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND receipt_tombstone_state IS NULL "
                    "AND status = 'processing'"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        )
        return TransportBodyScan(
            outbox_payload_rows=int(outbox_rows or 0),
            inbox_unsettled_rows=int(inbox_rows or 0),
        )

    # --- 正文清除（outbox -> suppressed 留 digest；inbox 状态矩阵）------------

    async def erase_transport_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime,
    ) -> None:
        # outbox：正文事实谓词命中 -> 清 payload_inline/payload_ref 转 suppressed
        # 保留 payload_digest（+ decision 四元终态证据，不动）。显式绑定 tenant +
        # conversation 维度；suppressed 分支满足 ck_agent_exec_outbox_payload。
        # 幂等：已 suppressed 行不命中。decision 四元保留仍满足
        # ck_agent_exec_outbox_decision（全有分支）。
        await self._session.execute(
            text(
                "UPDATE metaedu.agent_execution_outbox "
                "SET payload_inline = NULL, payload_ref = NULL, status = 'suppressed' "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND (payload_inline IS NOT NULL OR payload_ref IS NOT NULL) "
                "AND status <> 'suppressed'"
            ),
            {"t": tenant_id, "c": conversation_id},
        )

        # 同事务把对应 Run 置 output_publish_state='suppressed'（S3-E 同模式，
        # 契约 D-A-1：execution 侧 outbox 转 suppressed 时 Run 投影同步）。
        await self._session.execute(
            text(
                "UPDATE metaedu.agent_runs SET output_publish_state = 'suppressed' "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND output_publish_state IN ('pending', 'published', "
                "'dead_letter')"
            ),
            {"t": tenant_id, "c": conversation_id},
        )

        # inbox 状态矩阵（契约 D-A-1 冻结）：
        # - processing -> rejected + tombstone（与 S4-C Tx1 对齐）；
        # - 已 consumed/rejected -> 保留原 status，仅补幂等 tombstone；
        # - 已 tombstone 且 digest 精确匹配 -> no-op（幂等重放）；
        # - 已 tombstone 但 digest 不匹配 -> fail closed（不静默）。
        # receipt tombstone digest = snapshot_digest({schema_version:1, reason,
        # event_id})（S4-C Tx1 冻结键名，同一 helper）。
        from app.contexts.agent_execution.domain.snapshots import snapshot_digest

        rows = (
            await self._session.execute(
                text(
                    "SELECT id, event_id, status, receipt_tombstone_digest "
                    "FROM metaedu.agent_execution_inbox "
                    "WHERE tenant_id = :t AND conversation_id = :c"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).mappings().all()
        for row in rows:
            # 已 tombstone：digest 精确匹配 no-op；不匹配 fail closed。
            if row["receipt_tombstone_digest"] is not None:
                expected = snapshot_digest(
                    {
                        "schema_version": 1,
                        "reason": "purge_erasure",
                        "event_id": str(row["event_id"]),
                    }
                )
                if row["receipt_tombstone_digest"] != expected:
                    raise ExecutionIntegrationConflictError(
                        "execution inbox receipt tombstone digest mismatch on "
                        "purge; refusing to overwrite existing evidence"
                    )
                continue  # no-op（幂等重放，不改 status）
            # 未 tombstone：processing -> rejected+tombstone；已 consumed/rejected
            # 保留原 status 仅补幂等 tombstone。
            digest = snapshot_digest(
                {
                    "schema_version": 1,
                    "reason": "purge_erasure",
                    "event_id": str(row["event_id"]),
                }
            )
            new_status = "rejected" if row["status"] == "processing" else row["status"]
            await self._session.execute(
                text(
                    "UPDATE metaedu.agent_execution_inbox "
                    "SET status = :s, receipt_tombstone_state = 'redacted', "
                    "receipt_tombstone_digest = :d "
                    "WHERE id = :id"
                ),
                {"s": new_status, "d": digest, "id": row["id"]},
            )
