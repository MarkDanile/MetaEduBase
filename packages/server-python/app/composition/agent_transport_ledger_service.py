"""R1-S4-D-B：transport reconcile ledger 共享 service。

契约事实源：Plan §R1-S4-D 契约细化（PR #541 已合并 `51a12df6`）D-B-1/D-B-2/D-B-3：

- **共享层（D-B-1）**：``_register_issue``/``_recompute_projection`` 从
  ``agent_transport_backfill`` 私有升为本模块公开函数——backfill、consumer
  （S4-C PR-B 已 import backfill 私有）、participant（resolve）**同一投影实现**，
  杜绝两份投影漂移（B4 唯一事实源 + 同事务一致性）。集合锁临界区内调用、owner
  维度绑定（P2-2）、``(id, revision)`` 单 issue CAS、``ON CONFLICT DO NOTHING``
  幂等。
- **resolve（D-B-2）**：``resolve_epoch_unresolvable_issue``——集合锁临界区内
  ``(id, revision)`` CAS ``open/acknowledged -> resolved``（``revision+1`` 不回退，
  0 行命中即并发冲突重读重试，B1(d) CAS 规则）+ ``resolution_digest``（inbox
  ``receipt_tombstone_digest`` 已验证值）+ ``resolved_at``（``ck_..._resolution_
  evidence`` 强制）+ 投影重算（orphan 最高优先级聚合）。**只 resolve
  ``conversation_scope`` 行**；``tenant_scope``/``orphan`` 不 resolve、不改投影
  （留 S5 scheduler/运维闭环）。
- **gate 查询（D-B-3）**：``conversation_scope_gate_hits``（participant 内嵌 fail
  closed，purge 前置查与 S5 同一谓词）+ ``tenant_scope_gate_hits``（共享查询，
  S5 scheduler/canary enable 消费）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

#: resolve 只允许 conversation_scope 行（带 conversation_id，ck_..._class_scope
#: 强制）；tenant_scope/orphan 不 resolve（B4：tenant_scope 由 S5 fail closed、
#: orphan 由运维确认到 resolved 才清零）。
_RESOLVABLE_CLASSES = ("conversation_scope",)


async def register_issue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
    table: str,
    source_row_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    reconcile_class: str,
    issue_code: str,
) -> bool:
    """幂等登记一条 reconcile issue（唯一键 ON CONFLICT DO NOTHING）。返回是否新建。

    从 ``agent_transport_backfill._register_issue`` 提取（D-B-1 共享层）；调用方
    须已在集合锁临界区内。
    """
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_transport_scope_reconcile ("
                "  id, tenant_id, owner_key, source_table, source_row_id, "
                "  conversation_id, reconcile_class, issue_code, state, revision, created_at"
                ") VALUES (:id, :t, :o, :st, :sr, :c, :rc, :ic, 'open', 1, clock_timestamp()) "
                "ON CONFLICT ON CONSTRAINT uq_agent_transport_reconcile_issue DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "o": owner_key,
                "st": table,
                "sr": source_row_id,
                "c": conversation_id,
                "rc": reconcile_class,
                "ic": issue_code,
            },
        ),
    )
    return result.rowcount > 0


async def recompute_projection(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    owner_key: str,
    source_row_id: uuid.UUID,
) -> None:
    """按 ledger 当前 issue 集重算行内 ``scope_reconcile_state`` 投影（同事务）。

    从 ``agent_transport_backfill._recompute_projection`` 提取（D-B-1 共享层）。
    规则（B4）：orphan 类 issue 存在 -> 'orphan'（最高优先级）；任一 issue
    state<>'resolved' -> 'pending'；全部 resolved -> 'reconciled'。owner 维度
    绑定（P2-2）：投影聚合限定同一 owner。
    """
    state = (
        await session.execute(
            text(
                "SELECT CASE "
                "  WHEN count(*) = 0 THEN NULL "
                "  WHEN bool_or(reconcile_class = 'orphan') THEN 'orphan' "
                "  WHEN bool_or(state <> 'resolved') THEN 'pending' "
                "  ELSE 'reconciled' END "
                "FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND owner_key = :o "
                "AND source_table = :st AND source_row_id = :sr"
            ),
            {"t": tenant_id, "o": owner_key, "st": table, "sr": source_row_id},
        )
    ).scalar()
    if state is None:
        return  # 无 issue 行：投影保持 NULL（已带 scope / 无需 reconcile）
    await session.execute(
        text(
            f"UPDATE metaedu.{table} SET scope_reconcile_state = :s "
            f"WHERE tenant_id = :t AND id = :sr"
        ),
        {"s": state, "t": tenant_id, "sr": source_row_id},
    )


async def resolve_epoch_unresolvable_issue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
    table: str,
    source_row_id: uuid.UUID,
    resolution_digest: str,
) -> bool:
    """resolve 一条 ``epoch_unresolvable`` issue（D-B-2，集合锁临界区内调用）。

    **边界**：只 resolve ``conversation_scope`` 行（带 conversation_id）——先按
    (tenant, owner, source_table, source_row_id, issue_code) 定位该行，校验
    ``reconcile_class='conversation_scope'``（tenant_scope/orphan 不 resolve，
    变异：尝试 resolve tenant_scope 行被击杀）；再 ``(id, revision)`` CAS
    ``open/acknowledged -> resolved``（``revision+1`` 不回退，0 行命中即并发冲突
    返回 False 由调用方重读重试，B1(d)）+ ``resolution_digest`` + ``resolved_at``
    （``ck_..._resolution_evidence`` 强制：resolved 必须带证据）。返回是否成功
    （False = 并发冲突或行不存在）。

    ``resolution_digest`` = inbox ``receipt_tombstone_digest``（participant 完成
    tombstone 后取得的已验证 64-hex）；**不得**在未 tombstone 情况下置 resolved
    （B4）。
    """
    now = datetime.now(UTC)
    row = (
        await session.execute(
            text(
                "SELECT id, revision, reconcile_class FROM "
                "metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND owner_key = :o "
                "AND source_table = :st AND source_row_id = :sr "
                "AND issue_code = 'epoch_unresolvable'"
            ),
            {
                "t": tenant_id,
                "o": owner_key,
                "st": table,
                "sr": source_row_id,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        return False  # 无 issue 行（未登记）：调用方决定（no-op 或 fail closed）
    if row["reconcile_class"] not in _RESOLVABLE_CLASSES:
        raise ValueError(
            f"cannot resolve {row['reconcile_class']!r} issue; only "
            "conversation_scope is resolvable by the transport participant"
        )
    # 幂等：已 resolved 且 digest 一致 -> no-op 返回 True（重放）。
    if row["revision"] is not None:  # revision 恒非空；防御性
        current = (
            await session.execute(
                text(
                    "SELECT state, resolution_digest FROM "
                    "metaedu.agent_transport_scope_reconcile WHERE id = :id"
                ),
                {"id": row["id"]},
            )
        ).mappings().one()
        if current["state"] == "resolved":
            if current["resolution_digest"] != resolution_digest:
                raise ValueError(
                    "resolution_digest mismatch on already-resolved issue; "
                    "refusing to overwrite evidence"
                )
            return True
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "UPDATE metaedu.agent_transport_scope_reconcile "
                "SET state = 'resolved', revision = revision + 1, "
                "resolution_digest = :rd, resolved_at = :now "
                "WHERE id = :id AND revision = :rev AND state IN ('open', 'acknowledged')"
            ),
            {"rd": resolution_digest, "now": now, "id": row["id"], "rev": row["revision"]},
        ),
    )
    return result.rowcount > 0


async def conversation_scope_gate_hits(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> bool:
    """conversation_scope gate（D-B-3）：该 Conversation 有未 resolved 的
    ``conversation_scope`` issue 即 True（blocked）。

    S4-D-B participant 内嵌 fail closed（防直接调用绕过 scheduler）；purge 前置查
    与 S5 同一谓词。``conversation_scope AND state <> 'resolved'`` 命中即 blocked。
    """
    result = await session.scalar(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_transport_scope_reconcile "
            "  WHERE tenant_id = :t AND conversation_id = :c "
            "  AND reconcile_class = 'conversation_scope' AND state <> 'resolved'"
            ")"
        ),
        {"t": tenant_id, "c": conversation_id},
    )
    return bool(result)


async def tenant_scope_gate_hits(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> bool:
    """tenant_scope gate（D-B-3）：该 tenant 有未 resolved 的 ``tenant_scope`` issue
    即 True（scheduler/canary enable fail closed）。

    **只提供共享查询/API，由 S5 scheduler 消费**——不让单个 Conversation
    participant 因租户内无法归属的历史行全部阻塞。
    """
    result = await session.scalar(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_transport_scope_reconcile "
            "  WHERE tenant_id = :t AND reconcile_class = 'tenant_scope' "
            "  AND state <> 'resolved'"
            ")"
        ),
        {"t": tenant_id},
    )
    return bool(result)
