"""R1-S4-D-A：workspace/execution transport participant 对称测试矩阵。

契约事实源：Plan §R1-S4-D 契约细化（PR #541 已合并 `51a12df6`）：

- **outbox scan 正文事实谓词**：`payload_inline IS NOT NULL OR payload_ref IS NOT NULL`
  命中即清（**不排除 `cancelled`**——S4-C Tx2 终态化残留、S3-E terminalize 产物），
  统一清正文转 `status='suppressed'` 保留 `payload_digest`；`cancelled` 行保留 S4-C
  终态证据（execution `decision_*` 四元 / workspace `last_error_code` 不得清除或重写）。
- **inbox 状态矩阵**：`processing` -> `rejected`+tombstone（与 S4-C Tx1 对齐）；
  已 `consumed/rejected` 保留原 status 仅补幂等 tombstone；已 tombstone digest 精确
  匹配 no-op / 不匹配 fail closed。
- **final scan 为零才 ACK** + 全套 fencing（conversation/purge revision/lease epoch/
  registry drift/hold revision/operation revision/owner version/capability digest CAS）。
- **锁序**：Guard -> Conversation 行锁 -> transport owner advisory lock -> fence 重验 ->
  transport aggregate 集合 advisory lock（最内层）-> 源 transport 行 FOR UPDATE 投影写。
- **registry 全程保持 `erase_available=False`**：participant 入口 capability gate
  fail closed（`require_capability(transport_owner, "erase")`）是预期、不是缺陷。
- **边界**：不 resolve、不改 ledger 投影、不导入 backfill 私有函数。

两侧对称：workspace（`WorkspaceOutboxModel`/`WorkspaceInboxModel`，owner
`workspace.transport.v1`）与 execution（`ExecutionOutboxModel`/`ExecutionInboxModel`，
owner `execution.transport.v1`）各一套断言，共用本文件参数化。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import (
    OwnerCapabilityUnavailableError,
    registry_digest,
)
from app.contexts.agent_execution.domain.errors import (
    ExecutionIntegrationConflictError,
)
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.domain.errors import (
    WorkspaceIntegrationConflictError,
)
from tests.contexts.agent_control_plane.helpers import TENANT_ID

pytestmark = pytest.mark.asyncio

# 两侧对称定义（owner_key / ORM 表名 / 状态枚举）。scan/erase 用裸 SQL 断言
# 行值（避免 import 对方 context 的 ORM——integration 表经元数据同 schema）。
TRANSPORT_SIDES = {
    "workspace": {
        "owner": "workspace.transport.v1",
        "outbox_table": "agent_workspace_outbox",
        "inbox_table": "agent_workspace_inbox",
        "has_decision": False,
    },
    "execution": {
        "owner": "execution.transport.v1",
        "outbox_table": "agent_execution_outbox",
        "inbox_table": "agent_execution_inbox",
        "has_decision": True,
    },
}


async def _ensure_test_tenant(db_session):
    """确保 ``TENANT_ID`` 存在于 ``metaedu.tenants``（幂等）。

    S4-C batch3 教训：conftest 只种子 ``DEFAULT_TENANT_ID``（``00000000-...``），
    CI fresh 容器库无 ``71000000-...`` 时 ledger FK 违规（``fk_agent_transport_
    reconcile_tenant``）仅 CI 暴露。S4-D-A 真实 PG 反例同样登记 ledger（resolve 不
    做、但 scope/epoch 的 inbox tombstone 路径）——沿用 batch3 fixture 幂等补种。
    """
    from datetime import UTC as _UTC

    now = datetime.now(_UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": TENANT_ID,
            "name": "s4d-tenant",
            "school_name": "s4d school",
            "isolation": "shared",
            "now": now,
        },
    )
    await db_session.flush()


async def _seed_deleted_expired_conversation(
    db_session, *, title: str = "s4d conversation"
) -> tuple[uuid.UUID, int]:
    """建 deleted+expired（恢复窗口已过）会话 + transport fence（active）。

    返回 (conversation_id, purge_revision)。fence 用 transport owner 建立，
    模拟 purge 推进前的 baseline。
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    conv_id = uuid.uuid4()
    # 会话已删除且恢复窗口已过（purge_after 在过去）。actor tombstone 形态：
    # actor_state='redacted' 强制 created_by NULL + creator_identity_digest 64-hex
    # （ck_agent_conv_actor，S2-C）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, creator_identity_digest, "
            "state, title, title_source, "
            "next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            "purge_revision, purged_at, purge_after, deleted_at, created_at, "
            "updated_at, revision, hold_revision, actor_state) "
            "VALUES (:id, :t, NULL, :cd, :cid, 'deleted', :title, 'user', 1, 1, "
            ":now, 'scheduled', 1, NULL, :purge_after, :deleted_at, :now, "
            ":now, 3, 0, 'redacted') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": conv_id,
            "t": TENANT_ID,
            "cd": "a" * 64,
            "cid": "b" * 64,
            "title": title,
            "now": now,
            "purge_after": now - timedelta(days=1),
            "deleted_at": now - timedelta(days=31),
        },
    )
    # transport owner fence：active（purge 未开始）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) "
            "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
            ":empty_digest, 1, :now, :now) "
            "ON CONFLICT (tenant_id, conversation_id, owner_key) DO NOTHING"
        ),
        {
            "t": TENANT_ID,
            "c": conv_id,
            "o": "workspace.transport.v1",
            "empty_digest": _EMPTY_INGRESS_DIGEST,
            "now": now,
        },
    )
    await db_session.flush()
    return conv_id, 1


async def _make_purge_operation(
    db_session, conversation_id: uuid.UUID, purge_revision: int, *, owner: str
) -> tuple[uuid.UUID, int]:
    """建 scheduled purge operation + pending transport owner checkpoint。

    返回 (operation_id, operation_revision)。registry_digest 用当前 registry。
    """
    op_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purges "
            "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
            "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
            "hold_revision_snapshot, lease_epoch, scheduled_at, revision, created_at, updated_at) "
            "VALUES (:id, :t, :c, :r, 'scheduled', :rd, :rs, :rps, :rpd, 0, 0, "
            ":now, 1, :now, :now)"
        ),
        {
            "id": op_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "r": purge_revision,
            "rd": registry_digest(),
            "rs": _registry_snapshot_json(),
            "rps": '{"conversation_recovery_days": 30}',
            "rpd": _retention_policy_digest(),
            "now": now,
        },
    )
    cp_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, created_at, updated_at) "
            "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
        ),
        {
            "id": cp_id,
            "t": TENANT_ID,
            "op": op_id,
            "o": owner,
            "cd": _capability_digest(owner),
            "now": now,
        },
    )
    await db_session.flush()
    return op_id, 1


async def _seed_transport_outbox(
    db_session,
    *,
    conversation_id: uuid.UUID,
    side: str,
    status: str = "pending",
    payload_inline: dict | None = None,
    payload_ref: str | None = None,
    decision: dict | None = None,
    last_error_code: str | None = None,
    scope_reconcile_state: str | None = None,
) -> uuid.UUID:
    """种一行 transport outbox（默认 pending + inline 正文）。返回 outbox 行 id。

    ``payload_inline``/``payload_ref`` 恰一非空（满足 `ck_*_outbox_payload` 非
    suppressed 分支）。execution 侧 ``decision`` 非空时写四元（满足
    `ck_agent_exec_outbox_decision` 全有或全无）。
    """
    if payload_inline is None:
        payload_inline = {"body": "sensitive"} if payload_ref is None else None
    assert (payload_inline is not None) != (payload_ref is not None)
    table = TRANSPORT_SIDES[side]["outbox_table"]
    row_id = uuid.uuid4()
    digest = _payload_digest(payload_inline or {"ref": payload_ref})
    now = datetime.now(UTC).replace(tzinfo=None)
    if side == "workspace":
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.{table} "
                "(id, tenant_id, event_type, schema_version, aggregate_id, "
                "aggregate_type, payload_inline, payload_ref, payload_digest, "
                "status, attempt_count, conversation_id, producer_purge_revision, "
                "last_error_code, created_at, next_attempt_at, scope_reconcile_state) "
                "VALUES (:id, :t, 'turn.requested.v1', 1, :agg, 'workspace.message', "
                ":pi, :pr, :d, :s, 0, :c, :r, :lec, :now, :now, :sc)"
            ),
            {
                "id": row_id,
                "t": TENANT_ID,
                "agg": uuid.uuid4(),
                "pi": payload_inline,
                "pr": payload_ref,
                "d": digest,
                "s": status,
                "c": conversation_id,
                "r": 1,
                "lec": last_error_code,
                "now": now,
                "sc": scope_reconcile_state,
            },
        )
    else:
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.{table} "
                "(id, tenant_id, event_type, schema_version, aggregate_id, "
                "aggregate_type, payload_inline, payload_ref, payload_digest, "
                "correlation_id, status, attempt_count, next_attempt_at, "
                "conversation_id, producer_purge_revision, last_error_code, "
                "decision_actor_id, decision_reason, decision_digest, decided_at, "
                "created_at, scope_reconcile_state) "
                "VALUES (:id, :t, 'assistant_message.publish_requested.v1', 1, "
                ":agg, 'execution.run', :pi, :pr, :d, :corr, :s, 0, :now, :c, :r, "
                ":lec, :da, :dr, :dd, :de, :now, :sc)"
            ),
            {
                "id": row_id,
                "t": TENANT_ID,
                "agg": uuid.uuid4(),
                "pi": payload_inline,
                "pr": payload_ref,
                "d": digest,
                "corr": uuid.uuid4(),
                "s": status,
                "c": conversation_id,
                "r": 1,
                "lec": last_error_code,
                "da": (decision or {}).get("decision_actor_id"),
                "dr": (decision or {}).get("decision_reason"),
                "dd": (decision or {}).get("decision_digest"),
                "de": (decision or {}).get("decided_at"),
                "now": now,
                "sc": scope_reconcile_state,
            },
        )
    await db_session.flush()
    return row_id


async def _seed_transport_inbox(
    db_session,
    *,
    conversation_id: uuid.UUID,
    side: str,
    status: str = "processing",
    last_error_code: str | None = None,
    receipt_tombstone_digest: str | None = None,
) -> uuid.UUID:
    """种一行 transport inbox（默认 processing）。返回 inbox 行 id。

    ``receipt_tombstone_digest`` 非空时同写 ``receipt_tombstone_state='redacted'``
    （同生同灭，`ck_*_receipt_tombstone`）。
    """
    table = TRANSPORT_SIDES[side]["inbox_table"]
    row_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.{table} "
            "(id, tenant_id, consumer_name, event_id, event_type, schema_version, "
            "payload_digest, correlation_id, status, conversation_id, "
            "producer_purge_revision, last_error_code, receipt_tombstone_state, "
            "receipt_tombstone_digest, created_at) "
            "VALUES (:id, :t, :cn, :eid, :et, 1, :d, :corr, :s, :c, :r, :lec, "
            ":ts, :td, :now)"
        ),
        {
            "id": row_id,
            "t": TENANT_ID,
            "cn": "workspace.transport.v1" if side == "workspace"
            else "execution.transport.v1",
            "eid": uuid.uuid4(),
            "et": (
                "turn.requested.v1"
                if side == "workspace"
                else "assistant_message.publish_requested.v1"
            ),
            "d": "a" * 64,
            "corr": uuid.uuid4(),
            "s": status,
            "c": conversation_id,
            "r": 1,
            "lec": last_error_code,
            "ts": "redacted" if receipt_tombstone_digest else None,
            "td": receipt_tombstone_digest,
            "now": now,
        },
    )
    await db_session.flush()
    return row_id


async def _fence_state(db_session, conversation_id: uuid.UUID, owner: str) -> str:
    row = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_erasure_fences "
                "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
            ),
            {"t": TENANT_ID, "c": conversation_id, "o": owner},
        )
    ).scalar_one_or_none()
    assert row is not None, f"fence for {owner} missing"
    return row


async def _checkpoint_state(db_session, operation_id: uuid.UUID) -> str:
    row = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": operation_id},
        )
    ).scalar_one()
    return row


async def _outbox_row(db_session, table: str, row_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(f"SELECT * FROM metaedu.{table} WHERE id = :id"), {"id": row_id}
        )
    ).mappings().one()
    return dict(row)


async def _inbox_row(db_session, table: str, row_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(f"SELECT * FROM metaedu.{table} WHERE id = :id"), {"id": row_id}
        )
    ).mappings().one()
    return dict(row)


# ---------------------------------------------------------------------------
# 01. outbox scan 正文事实谓词 + 转 suppressed + 终态证据保留
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_pending_inline_cleared_to_suppressed(db_session, side):
    """pending + inline 正文 -> scan 命中 -> 转 suppressed 清正文留 digest。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_transport_outbox(
        db_session, conversation_id=conv_id, side=side, status="pending"
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "suppressed"
    assert row["payload_inline"] is None
    assert row["payload_ref"] is None
    assert row["payload_digest"] is not None  # digest 保留
    assert row["conversation_id"] == conv_id  # scope 保留


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_cancelled_cleared_evidence_retained(db_session, side):
    """S4-C Tx2 终态化残留：cancelled + 保留 payload -> 仍 scan 命中清正文。

    `cancelled` 是 S4-C 消费侧终态（payload 必经保留），**不是清除免除依据**；
    execution 侧 decision 四元、workspace 侧 last_error_code 终态证据不得清除。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    decision = None
    last_error_code = None
    if side == "execution":
        decision = {
            "decision_actor_id": uuid.UUID(int=0),
            "decision_reason": "epoch_unknown_rejected",
            "decision_digest": "b" * 64,
            "decided_at": datetime.now(UTC).replace(tzinfo=None),
        }
    else:
        last_error_code = "epoch_unknown_rejected"
    outbox_id = await _seed_transport_outbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="cancelled",
        decision=decision,
        last_error_code=last_error_code,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "suppressed"
    assert row["payload_inline"] is None
    assert row["payload_ref"] is None
    assert row["payload_digest"] is not None
    if side == "execution":
        # 终态证据完整保留（ck_agent_exec_outbox_decision 全有分支仍满足）。
        assert row["decision_actor_id"] == uuid.UUID(int=0)
        assert row["decision_reason"] == "epoch_unknown_rejected"
        assert row["decision_digest"] == "b" * 64
        assert row["decided_at"] is not None
    else:
        assert row["last_error_code"] == "epoch_unknown_rejected"


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_claimed_published_dead_letter_cleared(db_session, side):
    """claimed/published/dead_letter 行同样被正文事实谓词命中清除。"""
    await _ensure_test_tenant(db_session)
    for status in ("claimed", "published", "dead_letter"):
        conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
        outbox_id = await _seed_transport_outbox(
            db_session, conversation_id=conv_id, side=side, status=status
        )
        op_id, _ = await _make_purge_operation(
            db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
        )
        await db_session.commit()

        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

        row = await _outbox_row(
            db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id
        )
        assert row["status"] == "suppressed"
        assert row["payload_inline"] is None


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_suppressed_skipped(db_session, side):
    """已 suppressed（无正文）行不命中 scan，无状态变化。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_transport_outbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="suppressed",
        payload_inline={"body": "x"},
        payload_ref=None,
    )
    # suppressed 分支要求正文为 NULL——先造 suppressed 空正文行。
    table = TRANSPORT_SIDES[side]["outbox_table"]
    await db_session.execute(
        text(
            f"UPDATE metaedu.{table} SET payload_inline = NULL "
            f"WHERE id = :id"
        ),
        {"id": outbox_id},
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "suppressed"
    assert row["payload_inline"] is None


# ---------------------------------------------------------------------------
# 02. inbox 状态矩阵
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_processing_rejected_tombstone(db_session, side):
    """processing -> rejected + tombstone（与 S4-C Tx1 对齐）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    inbox_id = await _seed_transport_inbox(
        db_session, conversation_id=conv_id, side=side, status="processing"
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _inbox_row(db_session, TRANSPORT_SIDES[side]["inbox_table"], inbox_id)
    assert row["status"] == "rejected"
    assert row["receipt_tombstone_state"] == "redacted"
    assert row["receipt_tombstone_digest"] is not None
    assert len(row["receipt_tombstone_digest"]) == 64


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_consumed_rejected_idempotent_tombstone(db_session, side):
    """已 consumed/rejected 保留原 status 仅补幂等 tombstone。"""
    await _ensure_test_tenant(db_session)
    for status in ("consumed", "rejected"):
        conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
        inbox_id = await _seed_transport_inbox(
            db_session, conversation_id=conv_id, side=side, status=status
        )
        op_id, _ = await _make_purge_operation(
            db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
        )
        await db_session.commit()

        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

        row = await _inbox_row(
            db_session, TRANSPORT_SIDES[side]["inbox_table"], inbox_id
        )
        assert row["status"] == status  # 原 status 保留
        assert row["receipt_tombstone_state"] == "redacted"
        assert row["receipt_tombstone_digest"] is not None


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_already_tombstoned_digest_match_noop(db_session, side):
    """已 tombstone + digest 精确匹配 -> no-op（幂等重放，不改 status）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    existing_digest = "c" * 64
    inbox_id = await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        receipt_tombstone_digest=existing_digest,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _inbox_row(db_session, TRANSPORT_SIDES[side]["inbox_table"], inbox_id)
    assert row["status"] == "rejected"
    assert row["receipt_tombstone_state"] == "redacted"
    assert row["receipt_tombstone_digest"] == existing_digest  # 不重写


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_tombstone_digest_mismatch_fail_closed(db_session, side):
    """已 tombstone + digest 不匹配 -> fail closed（*IntegrationConflictError 不静默）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        receipt_tombstone_digest="d" * 64,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 具体异常类型断言（判别力：NotImplementedError/ValueError 均不得通过）。
    conflict_error = (
        WorkspaceIntegrationConflictError
        if side == "workspace"
        else ExecutionIntegrationConflictError
    )
    with pytest.raises(conflict_error):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)


# ---------------------------------------------------------------------------
# 03. final scan + ACK 重放 + fencing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_erase_acks_checkpoint_and_fence(db_session, side):
    """正文全清 + scan 为零 -> fence erasing->erased + checkpoint pending->acked。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    assert await _fence_state(
        db_session, conv_id, TRANSPORT_SIDES[side]["owner"]
    ) == ErasureFenceState.ERASED.value
    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.ACKED.value


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_ack_lost_erased_fence_repairs_pending_checkpoint(db_session, side):
    """ACK 丢失恢复：fence 已 erased 但 checkpoint 仍 pending -> 幂等重放补 ACK。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 首次 erase 成功（fence erased + checkpoint acked）。
    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)
    # 模拟 ACK 丢失：把 checkpoint 退回 pending（fence 保持 erased）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET state = 'pending', "
            "ack_digest = NULL, checkpoint_digest = NULL "
            "WHERE purge_operation_id = :op"
        ),
        {"op": op_id},
    )
    await db_session.commit()

    # 重放：erased fence 先于 purge 前置 -> 修复 pending checkpoint 到 acked。
    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.ACKED.value


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_erase_fencing_full(db_session, side):
    """fencing 全套：registry drift / lease_epoch / hold_revision 任一不符 fail closed。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_transport_outbox(
        db_session, conversation_id=conv_id, side=side
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 篡改 operation lease_epoch -> stale lease fail closed（S2-D/E 同款 ValueError）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET lease_epoch = 99 "
            "WHERE id = :op"
        ),
        {"op": op_id},
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # 零变更：outbox 正文仍在、checkpoint 仍 pending。
    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "pending"
    assert row["payload_inline"] is not None
    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.PENDING.value


# ---------------------------------------------------------------------------
# 04. capability gate（registry 全程 False）+ 锁序
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_capability_gate_fail_closed_when_registry_false(db_session, side):
    """registry 全程 False：participant 入口 require_capability(transport_owner, "erase")
    必须 fail closed（S2-D P1-1 模式）——S4-D-A 不得因缺 gate 而放行。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 直接调用 participant erase 入口（绕过任何编排）——registry 仍 False 时
    # 必须先 capability gate 拒绝（OwnerCapabilityUnavailableError），不得静默。
    with pytest.raises(OwnerCapabilityUnavailableError):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)


# ---------------------------------------------------------------------------
# helper：调用 participant erase（与实现签名对齐后调整）
# ---------------------------------------------------------------------------


async def _run_participant_erase(
    db_session, conversation_id: uuid.UUID, purge_revision: int, op_id: uuid.UUID, side: str
) -> None:
    """调用 transport participant erase 主入口（与 S2-D/S3-D 同签名形状）。

    TODO(实现时替换)：capability gate 前置后，registry False 会在此 fail closed——
    故上述 capability gate 测试依赖实现先做 gate；正文清除类测试在实现内
    gate 前调用（或经测试内绕过 gate 的辅助入口）。本 helper 先占位。
    """
    raise NotImplementedError("transport participant erase 待实现")


# ---------------------------------------------------------------------------
# 固定值 helpers（与 erasure_repository / registry 同源）
# ---------------------------------------------------------------------------

_EMPTY_INGRESS_DIGEST = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


def _registry_snapshot_json() -> str:
    """registry snapshot 的 canonical JSON 字符串（与 snapshot_digest 同源）。"""
    import json

    from app.composition.agent_erasure_registry import registry_snapshot

    return json.dumps(registry_snapshot(), sort_keys=True, separators=(",", ":"))


def _retention_policy_digest() -> str:
    from app.shared.schemas.canonical_json import canonical_digest

    return canonical_digest({"conversation_recovery_days": 30})


def _capability_digest(owner: str) -> str:
    from app.composition.agent_erasure_registry import capability_digest

    return capability_digest(owner)


def _payload_digest(payload: dict) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
