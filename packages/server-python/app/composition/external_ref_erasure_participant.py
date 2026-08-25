"""R1-S4-E-B2：``external.payload.v1`` erasure participant。

契约事实源：Plan §R1-S4-E E-1/E-1a/E-1b/E-2/E-2a/E-2b/E-2c/E-3/E-3a/E-3b/
E-5-2（PR #546 契约冻结 + PR #548 E-0a + PR #550 B1 adapter contract）。

B2 是 **3 个 source 的 DB ref 唯一清除者**（E-1b）：``agent_run_events.payload_ref``
（经 migration 041 guard）、``agent_workspace_outbox.payload_ref``、
``agent_execution_outbox.payload_ref``——均在 **external receipt 后**统一清除
（清 ref 与 inline 并转 ``suppressed``，满足现 outbox CHECK；D5「先删 external
object 取 receipt，再清 transport DB ref」）。

**双事务协议（E-2，镜像 S4-C Tx1/Tx2）**：
- **Tx1（短事务）**：Conversation 行锁 -> owner advisory lock -> fence FOR UPDATE ->
  集合锁 -> checkpoint ``pending/blocked -> erasing`` + ``attempt += 1`` +
  ``checkpoint_digest = external_delete_intent.v1 digest``（E-2c 状态相关语义）+
  operation ``lease_epoch`` 验证 + external ledger 确认 ``registered``；**提交释放
  全部数据库锁**。
- **adapter 调用（无锁）**：释放锁后调用 adapter 删除 object，携带跨 takeover
  稳定 idempotency key（E-2b，不含 lease_epoch/attempt）。
- **Tx2（第二独立事务）**：**精确重验（E-2a）** 后写 ``erased`` + ``receipt_digest``
  **再清对应 DB ref**（RunEvent 经 041 guard / outbox 清 ref 并转 suppressed）；
  成功则 ACK fence+checkpoint，任一行未 erased 则 conversation 级 blocked。

**锁序（E-5-2/D8）**：与 backfill 同源——集合锁 owner 按 ``_collection_owner``
（outbox→transport owner、run_events→external owner），同一源行的 ledger 写与
backfill 的 scope/ref 处理互斥；源行 UPDATE 在集合锁临界区内。

**E-3a timeout/unknown 矩阵**（classify_adapter_outcome 消费）：success→``erased``；
not-sent（可证明未发送）→``blocked/erase_timeout``；timeout（可能已生效）→
``unknown/outcome_unknown``；unknown→``unknown/outcome_unknown``；failed（可证明无
副作用）→``blocked/adapter_unavailable``；digest mismatch→``blocked/digest_mismatch``。

**E-1a source 已 NULL 历史兼容**：source ref 已 NULL/缺失时仍凭已验证 ledger 完成
删除留证（不因 source 已空而漏删）；不同非 NULL ref / 绑定冲突 -> fail closed。

**registry**：``external.payload.v1`` 保持 ``erase_available=False``（E-4）——入口
``require_capability(owner, "erase")`` fail closed 是预期；测试用 monkeypatch 临时
翻 True 验证主体（registry 断言与实现分离）。

**边界**：不实现 S4-E-C（Runtime conformance）、S4-F、S5 scheduler、S6；不修改
migration 040/041；不激活 external/runtime registry；不实现真实云对象存储/Pi
Worker adapter。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import (
    acquire_owner_lock,
    acquire_transport_aggregate_lock,
)
from app.composition.agent_erasure_registry import require_capability
from app.composition.agent_transport_ledger_service import (
    conversation_scope_gate_hits,
)
from app.composition.external_object_adapter import (
    ExternalEraseError,
    ExternalEraseSuccess,
    ExternalEraseUnknown,
    ExternalObjectAdapter,
    adapter_satisfies_prerequisite,
    classify_adapter_outcome,
    external_erase_idempotency_key,
    external_erase_receipt_digest,
    external_ref_identity_digest,
)
from app.composition.external_ref_lifecycle import _collection_owner
from app.composition.transport_erasure_participant import (
    REASON_CONVERSATION_SCOPE_GATE,
    REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
    TransportBodyScan,
    TransportErasureParticipantBase,
)
from app.contexts.agent_execution.domain.snapshots import snapshot_digest
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel

#: 本 participant 持有的 external owner（registry 固定 key）。
EXTERNAL_PAYLOAD_OWNER = "external.payload.v1"

# conversation 级 blocked reason（E-3a 矩阵 + 残留判定）。
REASON_EXTERNAL_REF_SCAN_NONZERO = "purge_blocked_by_external_ref_scan_nonzero"
REASON_EXTERNAL_ADAPTER_UNAVAILABLE = "purge_blocked_by_external_adapter_unavailable"
REASON_EXTERNAL_OUTCOME_UNKNOWN = "purge_blocked_by_external_outcome_unknown"
REASON_EXTERNAL_ERASE_TIMEOUT = "purge_blocked_by_external_erase_timeout"
# E-3a「digest mismatch -> blocked/digest_mismatch」：在 B2 设计下为 **vacuous**——
# Tx2 的 ``receipt_digest`` 由 adapter evidence 现算现写（无已持久化值可比），
# reconcile 同样现算现写；不存在「已持久化 digest 与重算不匹配」的比对点。重放/
# reconcile 的 evidence 缺失走保持原状态（E-3b）而非 digest_mismatch。E-2b 的
# 「重放比对」在 B2 无持久化 receipt 可比（Tx2 原子写），归 S5/运维 reconcile 的
# receipt lookup evidence 存在性判定。故 **不定义 REASON_EXTERNAL_DIGEST_MISMATCH
# 常量**（避免死代码），CHECK 枚举 `digest_mismatch` 保留给未来需要持久化比对
# 的路径。


@dataclass(frozen=True, slots=True)
class ExternalRefScan:
    """B2 的 external ref 扫描结果（owner checkpoint digest 的 canonical 输入）。

    ``total`` 为该 Conversation 未 erased 的 external ref 行数（``registered`` +
    ``blocked`` + ``unknown``）——final scan 非零 -> blocked（E-3 矩阵：非 erased
    即未完成，object 可能仍存在）。``blocked_reasons`` 携带 blocked 行的
    ``blocked_reason`` 分布（首轮复审 C-7/D-10/T-6：conversation 级 reason 归并
    须保留 erase_timeout 等可诊断身份，不得一律折叠为 adapter_unavailable）。
    """

    registered_refs: int
    blocked_refs: int
    unknown_refs: int
    blocked_reasons: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.registered_refs + self.blocked_refs + self.unknown_refs

    def digest(self) -> str:
        return snapshot_digest(
            {
                "schema_version": 1,
                "registered_refs": self.registered_refs,
                "blocked_refs": self.blocked_refs,
                "unknown_refs": self.unknown_refs,
                "blocked_reasons": sorted(self.blocked_reasons),
            }
        )


@dataclass(frozen=True, slots=True)
class ExternalErasureSummary:
    """单 owner 清除 + ACK 摘要（ACK digest 的 canonical 输入，不含正文/receipt）。"""

    owner_key: str
    owner_version: int
    purge_revision: int
    erased_refs: int
    scan: ExternalRefScan

    def ack_digest(self) -> str:
        return snapshot_digest(
            {
                "schema_version": 1,
                "owner_key": self.owner_key,
                "owner_version": self.owner_version,
                "purge_revision": self.purge_revision,
                "erased_refs": self.erased_refs,
                "scan": {
                    "registered_refs": self.scan.registered_refs,
                    "blocked_refs": self.scan.blocked_refs,
                    "unknown_refs": self.scan.unknown_refs,
                },
            }
        )


@dataclass(frozen=True, slots=True)
class ExternalRefRow:
    """external ledger 行（registered 窗口内快照，Tx2 重验用）。"""

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID | None
    ref_scheme: str
    ref_value: str
    source_table: str
    source_row_id: uuid.UUID


def external_delete_intent_digest(refs: list[ExternalRefRow]) -> str:
    """E-2c：``external_delete_intent.v1`` intent digest——完整稳定 ledger 身份集合的
    canonical digest（跨 takeover 不变；attempt 可变但 intent 不变）。
    """
    identities = sorted(
        external_ref_identity_digest(
            ref_scheme=ref.ref_scheme,
            ref_value=ref.ref_value,
            source_table=ref.source_table,
            source_row_id=ref.source_row_id,
            conversation_id=ref.conversation_id,
        )
        for ref in refs
    )
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "external_delete_intent",
            "refs": identities,
        }
    )


def external_source_table_ref_sql(source_table: str) -> str:
    """source 表名 -> 查询 SQL 片段（只允许 3 个合法 source，防注入）。"""
    if source_table == "agent_run_events":
        return "metaedu.agent_run_events"
    if source_table == "agent_workspace_outbox":
        return "metaedu.agent_workspace_outbox"
    if source_table == "agent_execution_outbox":
        return "metaedu.agent_execution_outbox"
    raise ValueError(f"unexpected external ref source table: {source_table!r}")


async def clear_external_source_ref(
    session: AsyncSession, *, tenant_id: uuid.UUID, ref: ExternalRefRow
) -> None:
    """清对应 DB ref（E-1b：B2 是 3 source ref 唯一清除者）。

    - ``agent_run_events``：``payload_ref=NULL + payload_state='redacted'``（041
      guard 分支 2 放行——OLD/NEW inline 均 NULL、ref 被清、转 redacted、其余
      envelope 列不变；**不得** SET updated_at）。
    - 两 outbox：``payload_ref=NULL + status='suppressed'``（ref-bearing 行 inline
      本已 NULL，满足现 outbox CHECK suppressed 分支；无 updated_at 列）。

    校验 rowcount（首轮复审 C-6/D-13）：调用方已确认 ``source payload_ref ==
    ledger ref_value``（E-1 绑定匹配），UPDATE 必须命中 1 行——0 行命中说明
    041 guard 拒行或并发已清，fail closed（ledger 已写 erased + receipt，源 ref
    未清 -> 必须由事务回滚保持原子一致，不得静默继续）。
    """
    if ref.source_table == "agent_run_events":
        result = await session.execute(
            text(
                "UPDATE metaedu.agent_run_events "
                "SET payload_ref = NULL, payload_state = 'redacted' "
                "WHERE tenant_id = :t AND id = :id AND payload_ref = :rv"
            ),
            {"t": tenant_id, "id": ref.source_row_id, "rv": ref.ref_value},
        )
    else:
        table = (
            "metaedu.agent_workspace_outbox"
            if ref.source_table == "agent_workspace_outbox"
            else "metaedu.agent_execution_outbox"
        )
        result = cast(
            CursorResult,
            await session.execute(
                text(
                    f"UPDATE {table} "
                    "SET payload_ref = NULL, status = 'suppressed' "
                    "WHERE tenant_id = :t AND id = :id AND payload_ref = :rv "
                    "AND payload_inline IS NULL"
                ),
                {"t": tenant_id, "id": ref.source_row_id, "rv": ref.ref_value},
            ),
        )
    cleared = cast(CursorResult, result).rowcount
    if cleared != 1:
        raise ValueError(
            f"external ref {ref.id} source ref clear hit {cleared} row(s); "
            "expected 1 (matched ref_value). 041 guard rejection or concurrent "
            "clear -> fail closed to keep ledger-erased + source-ref-removed atomic"
        )


async def write_erased_and_clear_ref(
    session: AsyncSession,
    *,
    ref: ExternalRefRow,
    receipt_digest: str,
    tenant_id: uuid.UUID,
) -> None:
    """E-1 source identity 重验 -> 写 ``erased`` + receipt -> 清源 ref（D5 顺序）。

    **唯一 source-ref 清除路径（B2，E-5-2）**——participant Tx2 与 settlement
    ledger 收口（TD-106 方案 A）共用本函数，**不复制第二清除者**。调用方负责在
    D8 锁序内先取集合锁（``acquire_transport_aggregate_lock``）再调本函数。

    - source identity 重验（E-1/E-1a）：source ref 与 ledger ``ref_value`` 匹配
      才清；source 已 NULL/缺失可跳过清除（历史兼容，ledger 为唯一事实源）；
      非 NULL 且不匹配 -> **先 fail closed**（不写 erased、不伪造 receipt）。
    - 写 ``erased`` + receipt（窗口不变量：registered + receipt_digest NULL）。
      0 行命中 -> 并发推进/证据已写 -> fail closed。
    - 清源 ref（D5「先删 external object 取 receipt，再清 transport DB ref」）。
    """
    # E-1 source identity 重验必须在写 erased 之前（绑定冲突 -> 不写证据）。
    current = (
        await session.execute(
            text(
                "SELECT payload_ref FROM "
                + external_source_table_ref_sql(ref.source_table)
                + " WHERE tenant_id = :t AND id = :id"
            ),
            {"t": tenant_id, "id": ref.source_row_id},
        )
    ).scalar_one_or_none()
    if current is not None and current != ref.ref_value:
        raise ValueError(
            f"external ref {ref.id} source payload_ref {current!r} != "
            f"ledger ref_value {ref.ref_value!r}; binding conflict, "
            "refusing to write erased receipt"
        )

    result = await session.execute(
        text(
            "UPDATE metaedu.agent_external_object_refs "
            "SET erase_state = 'erased', receipt_digest = :d, "
            "  blocked_reason = NULL, updated_at = clock_timestamp() "
            "WHERE tenant_id = :t AND id = :id "
            "AND erase_state = 'registered' AND receipt_digest IS NULL"
        ),
        {"t": tenant_id, "id": ref.id, "d": receipt_digest},
    )
    if cast(CursorResult, result).rowcount != 1:
        raise ValueError(
            f"external ref {ref.id} not registered with NULL receipt in Tx2; "
            "concurrent erase/evidence already written"
        )
    # source ref 仍存在且匹配 -> 清除（E-1b：B2 是唯一清除者，D5 receipt 后）。
    if current == ref.ref_value:
        await clear_external_source_ref(session, tenant_id=tenant_id, ref=ref)


class ExternalPayloadErasureParticipant(TransportErasureParticipantBase):
    """``external.payload.v1``：擦除 external object + 清 3 source DB ref + ACK。

    registry 全程保持 ``erase_available=False``（E-4）：入口
    ``require_capability(owner, "erase")`` fail closed 是预期；测试用 monkeypatch
    临时翻 True 验证主体。
    """

    owner_key = EXTERNAL_PAYLOAD_OWNER

    def __init__(self, session: AsyncSession, adapter: ExternalObjectAdapter) -> None:
        super().__init__(session)
        self._adapter = adapter

    # --- 抽象方法实现（external 无 transport body/inbox；scan 反映 external 残留）----

    async def scan_transport_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> TransportBodyScan:
        """final external ref scan：该 Conversation 未 erased 的 external ref 计数。

        复用 ``TransportBodyScan`` 形状接入基类 ACK/fencing（``outbox_payload_rows``
        承载 registered 残留；``inbox_unsettled_rows``/``run_unsettled_rows`` 恒 0）。
        """
        registered = await self._session.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :t AND conversation_id = :c "
                "AND erase_state = 'registered'"
            ),
            {"t": tenant_id, "c": conversation_id},
        )
        return TransportBodyScan(
            outbox_payload_rows=int(registered or 0),
            inbox_unsettled_rows=0,
            run_unsettled_rows=0,
        )

    async def count_ref_bearing_outbox_rows(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """external 无此前置（ref-bearing outbox 前置归 transport participant 的
        ``purge_owner_unavailable`` blocked）。B2 是 ref **清除者**，不是检查者。
        """
        return 0

    async def erase_transport_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime,
    ) -> None:
        """external 不在此路径清除——源 ref 清除在双事务协议的 Tx2（receipt 后）。"""

    async def _acquire_inbox_aggregate_locks(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """该 Conversation 全部 external ledger 源行的集合锁（E-5-2/D8）。

        ledger 行源行多态（3 张 source 表），按 ``_collection_owner(source_table)``
        与 backfill 同源取集合锁（outbox→transport owner、run_events→external
        owner）——同一源行的 B2 ledger 写与 backfill scope/ref 处理互斥。源行
        UPDATE（清 ref）必须在集合锁临界区内（D8「集合锁 -> 源行 FOR UPDATE」）。
        """
        refs = await self._load_registered_refs(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        for ref in refs:
            await acquire_transport_aggregate_lock(
                self._session,
                tenant_id=tenant_id,
                owner_key=_collection_owner(ref.source_table),
                source_table=ref.source_table,
                source_row_id=ref.source_row_id,
            )

    async def _resolve_epoch_issues_after_erase(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        """external 不 resolve transport epoch issue（D-B-2 归 transport participant）。"""

    # --- B2 专用：registered 窗口加载 ------------------------------------------

    async def _load_registered_refs(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[ExternalRefRow]:
        """加载该 Conversation 的 ``registered`` external ledger 行（adapter 窗口）。

        显式绑定 tenant + conversation 维度（定向复核 P2-1：禁裸谓词全表扫描）。
        **S5-A-7 ⑤（I2 落地）**：确定性 ``ORDER BY id``——行序驱动 adapter 删除与
        集合锁获取顺序，不得静默依赖自然序。
        """
        rows = (
            await self._session.execute(
                text(
                    "SELECT id, conversation_id, ref_scheme, ref_value, "
                    "source_table, source_row_id "
                    "FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND erase_state = 'registered' "
                    "ORDER BY id"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).mappings().all()
        return [
            ExternalRefRow(
                id=row["id"],
                tenant_id=tenant_id,
                conversation_id=row["conversation_id"],
                ref_scheme=row["ref_scheme"],
                ref_value=row["ref_value"],
                source_table=row["source_table"],
                source_row_id=row["source_row_id"],
            )
            for row in rows
        ]

    async def _scan_external_refs(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ExternalRefScan:
        """该 Conversation 的 external ref 残留计数（final scan 判定用）。

        blocked 行同时收集 ``blocked_reason`` 分布（供 conversation 级 reason
        归并分派，首轮复审 C-7/D-10/T-6）。
        """
        counts = (
            await self._session.execute(
                text(
                    "SELECT erase_state, count(*), "
                    "  (CASE WHEN erase_state = 'blocked' THEN blocked_reason END) "
                    "  AS reason FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "GROUP BY erase_state, reason"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).all()
        by_state: dict[str, int] = {}
        blocked_reasons: set[str] = set()
        for state, count, reason in counts:
            by_state[state] = by_state.get(state, 0) + int(count)
            if state == "blocked" and reason is not None:
                blocked_reasons.add(reason)
        return ExternalRefScan(
            registered_refs=by_state.get("registered", 0),
            blocked_refs=by_state.get("blocked", 0),
            unknown_refs=by_state.get("unknown", 0),
            blocked_reasons=tuple(sorted(blocked_reasons)),
        )

    async def _load_conversation_for_update(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationModel:
        conversation = (
            (
                await self._session.execute(
                    select(ConversationModel)
                    .where(
                        ConversationModel.tenant_id == tenant_id,
                        ConversationModel.id == conversation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for external erasure"
            )
        return conversation

    # --- 主入口（E-2 双事务协议）------------------------------------------------

    async def erase_external_payload(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        purge_operation_id: uuid.UUID,
        expected_operation_revision: int,
        expected_lease_epoch: int = 0,
    ) -> ExternalErasureSummary:
        """external owner 擦除主入口（B2，E-2 双事务协议）。

        锁序：Conversation 行锁 -> owner advisory lock -> fence FOR UPDATE -> 集合
        advisory lock（最内层）-> 源行 FOR UPDATE。E-2b 硬前置（adapter 幂等重放或
        receipt lookup）由 B1 promote 判定；本入口再次断言（fail closed）。
        """
        # capability gate（S2-D P1-1 模式）：registry False 时 fail closed。
        require_capability(self.owner_key, "erase")
        if not adapter_satisfies_prerequisite(self._adapter):
            raise ValueError(
                f"adapter {self._adapter.adapter_key!r} v"
                f"{self._adapter.adapter_version} supports neither idempotent "
                "replay nor receipt lookup; external erasure cannot start (E-2b)"
            )

        # ===== Tx1（短事务，提交释放全部锁）=====
        conversation = await self._load_conversation_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        effective_now = await self._database_now()

        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        fence = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        if fence is None:
            fence, _ = await self._erasure.ensure_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
            )

        # erased fence 幂等重放先于 purge 前置（ACK 丢失恢复）。
        if fence.state is ErasureFenceState.ERASED:
            # S4-F 族 B（F-6「跨 purge 实例 erased-fence 重放」）：erased-fence 修复
            # 必须限定**同一 purge_revision**——否则同 conversation 新 purge（rev 2）
            # 会拿 purge 1 的 fence ack_digest 把 op2 的 pending checkpoint 置 ACKED
            # （跨 purge 实例的 ack 摘要污染）。scan 非零 guard 只拦 session 泄漏，
            # 拦不住 ack 摘要不一致——此处补门禁（runtime 侧同修复，E-C C-4）。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"erased fence {self.owner_key!r} under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; "
                    "cross-purge-instance ACK repair rejected (E-2a)"
                )
            fence_ack_digest = fence.ack_digest
            assert fence_ack_digest is not None, "erased fence must carry ack_digest"
            scan = await self._scan_external_refs(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            if scan.total != 0:
                raise ValueError(
                    f"erased fence {self.owner_key!r} but external ref scan non-zero "
                    f"(total={scan.total}); external object leaked after erase"
                )
            # checkpoint_digest 必须用 final scan digest（ExternalRefScan 形式）——
            # 正常 ACK 持久化的也是该形式（``_ack_owner_checkpoint`` 处
            # ``checkpoint_digest=final_scan.digest()``）。**不得**包
            # ``TransportBodyScan``（其 digest 键域不同，sha256 必不匹配 ->
            # ``_repair_checkpoint_if_pending`` 的 digest 一致性校验必 fail closed，
            # 幂等重放失效——首轮复审 D-1）。
            await self._repair_checkpoint_if_pending(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                expected_operation_revision=expected_operation_revision,
                fence_owner_version=fence.owner_version,
                ack_digest=fence_ack_digest,
                checkpoint_digest=scan.digest(),
                conversation=conversation,
                now=effective_now,
            )
            return self._summary_from_fence(
                fence=fence,
                purge_revision=purge_revision,
                erased_refs=scan.total - scan.registered_refs,
                scan=scan,
            )

        # purge 前置（仅非 erased fence = 新 purge 强制）。
        self._require_purgeable(conversation, now=effective_now)

        # active legal hold -> blocked 正常返回。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            scan = await self._scan_external_refs(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            body_scan = self._to_transport_scan(scan)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=body_scan,
                conversation=conversation,
                now=effective_now,
                expected_revision=expected_operation_revision,
            )
            return self._blocked_summary(
                fence=fence,
                purge_revision=purge_revision,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=scan,
            )

        # conversation_scope gate（D-B-3）：未 resolved issue -> blocked。
        if await conversation_scope_gate_hits(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        ):
            scan = await self._scan_external_refs(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            body_scan = self._to_transport_scan(scan)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                fence_owner_version=fence.owner_version,
                reason=REASON_CONVERSATION_SCOPE_GATE,
                scan=body_scan,
                conversation=conversation,
                now=effective_now,
                # 本 gate 在 _mark_operation_running（bump revision）**之前**检查，
                # 与同位置 legal-hold 分支对齐——operation revision 尚未 bump，传
                # expected_operation_revision 做 revision CAS（首轮复审 D-4：不得
                # 用基类 transport 的 None——那是 gate 在 mark_running 之后才有的
                # N->N+1 依据，此处不成立）。
                expected_revision=expected_operation_revision,
            )
            return self._blocked_summary(
                fence=fence,
                purge_revision=purge_revision,
                reason=REASON_CONVERSATION_SCOPE_GATE,
                scan=scan,
            )

        # 推进 fence -> erasing（首写 active->erasing；重试 blocked->erasing）。
        if fence.state is ErasureFenceState.ACTIVE:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
                expected_state=ErasureFenceState.ACTIVE,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
        elif fence.state is ErasureFenceState.BLOCKED:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=self.owner_key,
                expected_state=ErasureFenceState.BLOCKED,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
        elif fence.state is ErasureFenceState.ERASING:
            # S4-F 族 A（并发面 P1-1）：E-2a 同一 purge 实例门禁（镜像 runtime
            # ``:594-606``）。fence 已 erasing 时必须是**同一 purge_revision**（本
            # operation 的崩溃后重放，checkpoint ERASING 续做分支继续）——不同
            # purge_revision 的第二 purge 实例在 fence erasing 下**不得**进入 adapter
            # 窗口（否则两 operation 同时 destroy，E-6「重复删除」串行化契约）。
            if fence.purge_revision != purge_revision:
                raise ValueError(
                    f"fence {self.owner_key!r} already erasing under purge_revision "
                    f"{fence.purge_revision}, requested {purge_revision}; concurrent "
                    "purge instance rejected (E-2a same-instance gate)"
                )
        else:
            raise ValueError(
                f"fence {self.owner_key!r} in state {fence.state.value}; "
                "cannot erase external payload"
            )

        # operation scheduled/blocked -> running（revision CAS）。
        await self._mark_operation_running(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            expected_operation_revision=expected_operation_revision,
            conversation=conversation,
            now=effective_now,
        )

        # 集合锁（源行 UPDATE 之前，D8 同序）+ 加载 registered 窗口。
        refs = await self._load_registered_refs(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await self._acquire_inbox_aggregate_locks(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

        # checkpoint -> erasing + attempt += 1 + intent digest（E-2c）。
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence.owner_version,
        )
        intent_digest = external_delete_intent_digest(refs)
        if checkpoint.state in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            checkpoint.state = PurgeOwnerState.ERASING.value
            checkpoint.attempt = checkpoint.attempt + 1
            checkpoint.checkpoint_digest = intent_digest
            checkpoint.reason_code = None
            checkpoint.updated_at = effective_now
        elif checkpoint.state == PurgeOwnerState.ERASING.value:
            # 崩溃后重放（同 invocation）：attempt 不变、intent digest 精确相等
            # 才续做；已推进到别的 intent -> fail closed（并发身份不符）。
            if checkpoint.attempt == 0 or checkpoint.checkpoint_digest != intent_digest:
                raise ValueError(
                    "external checkpoint already erasing with mismatched intent "
                    "digest/attempt; concurrent erasure takeover rejected"
                )
        else:
            raise ValueError(
                f"external checkpoint not erasable from state {checkpoint.state!r}"
            )
        # commit 前捕获 Tx1 身份（attempt/intent），避免 commit 后 ORM 过期
        # （expire_on_commit 场景）影响 Tx2 精确重验比对。
        tx1_attempt = int(checkpoint.attempt)
        await self._session.flush()
        # Tx1 提交释放全部锁（adapter 调用不得持锁做外部 I/O，E-2）。
        await self._session.commit()

        # ===== adapter 调用（无锁，E-2b idempotency key）=====
        adapter_outcome_union = (
            ExternalEraseSuccess | ExternalEraseUnknown | ExternalEraseError
        )
        outcomes: list[tuple[ExternalRefRow, adapter_outcome_union]] = []
        for ref in refs:
            idempotency_key = external_erase_idempotency_key(
                ref_scheme=ref.ref_scheme,
                ref_value=ref.ref_value,
                adapter_key=self._adapter.adapter_key,
                adapter_version=self._adapter.adapter_version,
            )
            try:
                outcome: adapter_outcome_union = await self._adapter.delete_object(
                    ref_scheme=ref.ref_scheme,
                    ref_value=ref.ref_value,
                    idempotency_key=idempotency_key,
                )
            except ExternalEraseError as exc:
                outcome = exc
            outcomes.append((ref, outcome))

        # ===== Tx2（第二独立事务：E-2a 精确重验 + 写结果 + 清 ref + ACK）=====
        # S4-F 族 B（F-6「external 跨进程 takeover」）：E-2a 精确重验必须观察**已提交
        # 状态**——Tx2 是第二独立事务，但 ORM identity map 会把 Tx1 时期的
        # checkpoint/operation 对象按 PK 复用，`_load_verified_checkpoint`/
        # `_load_verified_operation` 的 SELECT 返回**未过期实例**（expire_on_commit
        # =False），并发 takeover（另一进程 bump attempt/lease_epoch/intent）无法被
        # Tx2 重验观测——防双删失效（runtime 侧同修复，E-C C-1/T-1）。此处
        # ``expire_all`` 使后续重验按已提交行重读（fence 是 domain 重建不受影响）。
        # 先 expire（清 Tx1 时代 ORM 缓存），**再**重载 Conversation FOR UPDATE
        # （避免 expire_all 后 conversation2 的属性惰性读走无锁 SELECT）。
        self._session.expire_all()
        conversation2 = await self._load_conversation_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        tx2_now = await self._database_now()
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        fence2 = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
        )
        if fence2 is None or fence2.state is not ErasureFenceState.ERASING:
            raise ValueError(
                "external fence no longer erasing in Tx2; "
                "stale fence rejected (E-2a)"
            )
        if fence2.purge_revision != purge_revision:
            raise ValueError(
                f"fence purge_revision {fence2.purge_revision} != "
                f"operation {purge_revision}; stale purge instance rejected"
            )
        checkpoint2 = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence2.owner_version,
        )
        if checkpoint2.state != PurgeOwnerState.ERASING.value:
            raise ValueError(
                f"external checkpoint not erasing in Tx2: {checkpoint2.state!r}"
            )
        if checkpoint2.attempt != tx1_attempt:
            raise ValueError(
                f"checkpoint attempt {checkpoint2.attempt} != Tx1 "
                f"{tx1_attempt}; stale attempt rejected (E-2a)"
            )
        if checkpoint2.checkpoint_digest != intent_digest:
            raise ValueError(
                "checkpoint intent digest no longer matches Tx1; "
                "stale intent rejected (E-2a)"
            )
        await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            conversation_purge_revision=conversation2.purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation2.hold_revision,
        )

        # 集合锁临界区内写 ledger + 清源 ref（D8 同序）。
        await self._acquire_inbox_aggregate_locks(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

        erased_count = 0
        for ref, outcome in outcomes:
            classification = classify_adapter_outcome(outcome)
            state = classification.erase_state
            if state == "erased":
                if not isinstance(outcome, ExternalEraseSuccess):
                    raise ValueError(
                        "classify_adapter_outcome erased without success evidence"
                    )
                # E-2b「可验证 evidence」：空/空白 evidence 视为无 evidence，fail
                # closed（首轮复审 D-9：不得凭空 evidence 写 erased）。
                if not outcome.adapter_receipt_evidence.strip():
                    raise ValueError(
                        "external erase success without non-empty "
                        "adapter_receipt_evidence; cannot forge erased receipt"
                    )
                idempotency_key = external_erase_idempotency_key(
                    ref_scheme=ref.ref_scheme,
                    ref_value=ref.ref_value,
                    adapter_key=self._adapter.adapter_key,
                    adapter_version=self._adapter.adapter_version,
                )
                receipt_digest = external_erase_receipt_digest(
                    adapter_key=self._adapter.adapter_key,
                    adapter_version=self._adapter.adapter_version,
                    idempotency_key=idempotency_key,
                    adapter_receipt_evidence=outcome.adapter_receipt_evidence,
                    ref_digest=external_ref_identity_digest(
                        ref_scheme=ref.ref_scheme,
                        ref_value=ref.ref_value,
                        source_table=ref.source_table,
                        source_row_id=ref.source_row_id,
                        conversation_id=ref.conversation_id,
                    ),
                    erase_outcome="erased",
                )
                await self._write_erased_and_clear_ref(
                    ref=ref,
                    receipt_digest=receipt_digest,
                    tenant_id=tenant_id,
                )
                erased_count += 1
            else:
                # blocked/unknown：写 ledger 状态 + reason，不清 ref（E-3a 矩阵；
                # E-3b reconcile/查询在 S5，本 Slice 只写状态）。
                await self._write_ledger_failure(
                    ref=ref,
                    erase_state=state,
                    blocked_reason=classification.blocked_reason,
                    tenant_id=tenant_id,
                )

        # final scan：未 erased 残留 -> conversation 级 blocked；否则 ACK
        # （E-2c acked=final scan digest）。
        final_scan = await self._scan_external_refs(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if final_scan.total != 0:
            body_scan = self._to_transport_scan(final_scan)
            reason = self._owner_blocked_reason(final_scan)
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation2.hold_revision,
                fence_owner_version=fence2.owner_version,
                reason=reason,
                scan=body_scan,
                conversation=conversation2,
                now=tx2_now,
            )
            await self._session.commit()
            return self._blocked_summary(
                fence=fence2,
                purge_revision=purge_revision,
                reason=reason,
                scan=final_scan,
            )

        # ACK：fence erasing->erased + checkpoint acked。
        summary = ExternalErasureSummary(
            owner_key=self.owner_key,
            owner_version=fence2.owner_version,
            purge_revision=purge_revision,
            erased_refs=erased_count,
            scan=final_scan,
        )
        ack_digest = summary.ack_digest()
        fence3 = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.owner_key,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence2.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation2.hold_revision,
            ack_digest=ack_digest,
            now=tx2_now,
        )
        await self._ack_owner_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            conversation_purge_revision=conversation2.purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation2.hold_revision,
            fence_owner_version=fence3.owner_version,
            ack_digest=ack_digest,
            checkpoint_digest=final_scan.digest(),
            now=tx2_now,
        )
        await self._session.commit()
        return summary

    # --- 源 ref 清除（receipt 后，D5）------------------------------------------

    async def _write_erased_and_clear_ref(
        self, *, ref: ExternalRefRow, receipt_digest: str, tenant_id: uuid.UUID
    ) -> None:
        """Tx2：委托唯一 source-ref 清除路径（模块级 ``write_erased_and_clear_ref``，

        与 settlement TD-106 方案 A ledger 收口共用同一实现，不复制第二清除者）。
        集合锁已由 Tx2 主流程在锁序内先取（``_acquire_inbox_aggregate_locks``，D8）。
        """
        await write_erased_and_clear_ref(
            self._session, ref=ref, receipt_digest=receipt_digest, tenant_id=tenant_id
        )


    async def _write_ledger_failure(
        self,
        *,
        ref: ExternalRefRow,
        erase_state: str,
        blocked_reason: str | None,
        tenant_id: uuid.UUID,
    ) -> None:
        """Tx2：写 ``blocked``/``unknown`` + reason（E-3a 矩阵），不清 ref。"""
        result = await self._session.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs "
                "SET erase_state = :s, blocked_reason = :r, "
                "  updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND id = :id "
                "AND erase_state = 'registered'"
            ),
            {"t": tenant_id, "id": ref.id, "s": erase_state, "r": blocked_reason},
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ValueError(
                f"external ref {ref.id} not registered in Tx2 failure write"
            )

    @staticmethod
    def _source_table_ref_sql(source_table: str) -> str:
        """委托模块级 ``external_source_table_ref_sql``（单一实现）。"""
        return external_source_table_ref_sql(source_table)


    async def _clear_source_ref(self, *, tenant_id: uuid.UUID, ref: ExternalRefRow) -> None:
        """委托唯一 source-ref 清除路径（模块级 ``clear_external_source_ref``）。"""
        await clear_external_source_ref(self._session, tenant_id=tenant_id, ref=ref)


    @staticmethod
    def _to_transport_scan(scan: ExternalRefScan) -> TransportBodyScan:
        return TransportBodyScan(
            outbox_payload_rows=scan.registered_refs,
            inbox_unsettled_rows=0,
            run_unsettled_rows=0,
        )

    # --- E-3b blocked/unknown 查询与有证据 reconcile（运维可观察性）------------

    async def list_blocked_unknown_refs(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        erase_state: str | None = None,
    ) -> list[dict]:
        """E-3b：blocked/unknown 行查询（``agent_external_object_refs`` 过滤）。

        按 ``erase_state``（blocked/unknown）+ 可选 ``blocked_reason`` + 可选
        Conversation 维度过滤；HTTP/CLI 接线归 S5，本 Slice 只提供查询能力与测试。
        """
        if erase_state not in (None, "blocked", "unknown"):
            raise ValueError(
                f"erase_state filter must be 'blocked' or 'unknown', got {erase_state!r}"
            )
        sql = (
            "SELECT id, conversation_id, ref_scheme, ref_value, source_table, "
            "  source_row_id, erase_state, blocked_reason "
            "FROM metaedu.agent_external_object_refs "
            "WHERE tenant_id = :t AND erase_state IN ('blocked', 'unknown')"
        )
        params: dict = {"t": tenant_id}
        if conversation_id is not None:
            sql += " AND conversation_id = :c"
            params["c"] = conversation_id
        if erase_state is not None:
            sql += " AND erase_state = :s"
            params["s"] = erase_state
        rows = (
            await self._session.execute(text(sql + " ORDER BY updated_at"), params)
        ).mappings().all()
        return [dict(row) for row in rows]

    async def reconcile_external_ref(
        self,
        *,
        tenant_id: uuid.UUID,
        ref_id: uuid.UUID,
    ) -> str:
        """E-3b：有证据 reconcile——仅当 adapter ``receipt lookup`` 返回可验证
        evidence 时补写 ``erased`` + receipt；**禁止无 receipt 强制 ``erased``**。

        返回补写后的 ledger ``erase_state``：receipt 可得 -> ``erased``；无 receipt
        -> 保持原状态（blocked/unknown 不动，交运维/人工确认）。收场（冻结）：
        Tx2 fail closed 但 adapter 副作用已发生时，若 receipt 可得则补写 erased，
        否则保持 blocked/unknown（E-3a）。

        **锁序（首轮复审 C-3/D-5 返修）**：写 ledger + 清源 ref 前按源行取集合
        advisory lock（``_collection_owner(source_table)`` 与 backfill 同源，
        E-5-2/D8）——与 B1/backfill 对同源行的 ledger 写互斥，防「行锁->集合锁」
        与「集合锁->行锁」AB-BA。**持锁期间不执行外部 I/O**：receipt lookup 在
        取锁前无锁调用（evidence 是幂等 key 查询，不依赖锁内状态）。

        **清源 ref（首轮复审 D-3/T-7 返修）**：补写 ``erased`` + receipt 后按
        E-1/E-1a 绑定校验清对应 DB ref（E-1b：B2 是 3 source ref 唯一清除者）——
        source 已 NULL/缺失跳过（历史兼容）、非 NULL 且 != ledger ``ref_value``
        fail closed、匹配则清。否则 conversation 永久 blocked（B2 不再消费
        reconciled-erased 行、transport 对 ref-bearing 行永久 ``purge_owner_
        unavailable``）。
        """
        # 先无锁查 evidence（receipt lookup 是外部 I/O，E-2「禁持锁做外部 I/O」）。
        row = (
            await self._session.execute(
                text(
                    "SELECT id, conversation_id, ref_scheme, ref_value, "
                    "source_table, source_row_id, erase_state, receipt_digest "
                    "FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": ref_id},
            )
        ).mappings().one_or_none()
        if row is None:
            raise ValueError(f"external ref {ref_id} not found for reconcile")
        if row["erase_state"] == "erased":
            return "erased"  # 已终态 no-op
        if not self._adapter.supports_receipt_lookup:
            return row["erase_state"]
        idempotency_key = external_erase_idempotency_key(
            ref_scheme=row["ref_scheme"],
            ref_value=row["ref_value"],
            adapter_key=self._adapter.adapter_key,
            adapter_version=self._adapter.adapter_version,
        )
        evidence = await self._adapter.receipt_lookup(
            idempotency_key=idempotency_key
        )
        if evidence is None or not evidence.strip():
            return row["erase_state"]  # 无 receipt / 空 evidence，禁止强制 erased
        # 有证据：取集合锁（与 backfill 同源，D8）+ 锁内校验 + 补写 + 清 ref。
        await acquire_transport_aggregate_lock(
            self._session,
            tenant_id=tenant_id,
            owner_key=_collection_owner(row["source_table"]),
            source_table=row["source_table"],
            source_row_id=row["source_row_id"],
        )
        locked = (
            await self._session.execute(
                text(
                    "SELECT erase_state, blocked_reason FROM "
                    "metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND id = :id FOR UPDATE"
                ),
                {"t": tenant_id, "id": ref_id},
            )
        ).mappings().one_or_none()
        if locked is None:
            raise ValueError(f"external ref {ref_id} not found for reconcile")
        if locked["erase_state"] == "erased":
            return "erased"  # 并发已 reconcile，no-op
        # 按冻结 envelope 重算 receipt_digest（E-2b，禁自造）。
        receipt_digest = external_erase_receipt_digest(
            adapter_key=self._adapter.adapter_key,
            adapter_version=self._adapter.adapter_version,
            idempotency_key=idempotency_key,
            adapter_receipt_evidence=evidence,
            ref_digest=external_ref_identity_digest(
                ref_scheme=row["ref_scheme"],
                ref_value=row["ref_value"],
                source_table=row["source_table"],
                source_row_id=row["source_row_id"],
                conversation_id=row["conversation_id"],
            ),
            erase_outcome="erased",
        )
        result = await self._session.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs "
                "SET erase_state = 'erased', receipt_digest = :d, "
                "  blocked_reason = NULL, updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND id = :id "
                "AND erase_state IN ('blocked', 'unknown')"
            ),
            {"t": tenant_id, "id": ref_id, "d": receipt_digest},
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ValueError(
                f"external ref {ref_id} not blocked/unknown for reconcile; "
                "concurrent state change"
            )
        # 补清源 ref（E-1/E-1a 绑定校验；source 已 NULL/缺失跳过）。
        ref = ExternalRefRow(
            id=row["id"],
            tenant_id=tenant_id,
            conversation_id=row["conversation_id"],
            ref_scheme=row["ref_scheme"],
            ref_value=row["ref_value"],
            source_table=row["source_table"],
            source_row_id=row["source_row_id"],
        )
        current = (
            await self._session.execute(
                text(
                    "SELECT payload_ref FROM "
                    + self._source_table_ref_sql(ref.source_table)
                    + " WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": ref.source_row_id},
            )
        ).scalar_one_or_none()
        if current is not None and current != ref.ref_value:
            raise ValueError(
                f"external ref {ref.id} source payload_ref {current!r} != "
                f"ledger ref_value {ref.ref_value!r}; binding conflict, "
                "refusing to clear after reconcile"
            )
        if current == ref.ref_value:
            await self._clear_source_ref(tenant_id=tenant_id, ref=ref)
        return "erased"

    def _owner_blocked_reason(self, scan: ExternalRefScan) -> str:
        """E-3a 矩阵 -> conversation 级 blocked reason（purge 无法完成）。

        reason 归并按**具体 blocked_reason 分派**（首轮复审 C-7/D-10/T-6）——不
        得一律折叠为 ``adapter_unavailable``：erase_timeout 是「可证明未发送、可
        重试」、adapter_unavailable 是「可证明无副作用、可重试」、outcome_unknown
        是「可能已生效、不自动重试」——三者运维语义不同，future S5 须据此判断
        重试策略。优先级：unknown（最严重，不自动重试）> erase_timeout >
        adapter_unavailable > registered 残留 > 兜底。
        """
        if scan.unknown_refs:
            return REASON_EXTERNAL_OUTCOME_UNKNOWN
        if "erase_timeout" in scan.blocked_reasons:
            return REASON_EXTERNAL_ERASE_TIMEOUT
        if scan.blocked_refs:
            return REASON_EXTERNAL_ADAPTER_UNAVAILABLE
        if scan.registered_refs:
            return REASON_EXTERNAL_REF_SCAN_NONZERO
        return REASON_EXTERNAL_ADAPTER_UNAVAILABLE

    @staticmethod
    def _summary_from_fence(
        *,
        fence,
        purge_revision: int,
        erased_refs: int,
        scan: ExternalRefScan,
    ) -> ExternalErasureSummary:
        return ExternalErasureSummary(
            owner_key=EXTERNAL_PAYLOAD_OWNER,
            owner_version=fence.owner_version,
            purge_revision=purge_revision,
            erased_refs=erased_refs,
            scan=scan,
        )

    @staticmethod
    def _blocked_summary(
        *,
        fence,
        purge_revision: int,
        reason: str,
        scan: ExternalRefScan,
    ) -> ExternalErasureSummary:
        """blocked 返回（fence 保持 erasing，summary 的 erased_refs=0）。"""
        return ExternalErasureSummary(
            owner_key=EXTERNAL_PAYLOAD_OWNER,
            owner_version=fence.owner_version,
            purge_revision=purge_revision,
            erased_refs=0,
            scan=scan,
        )
