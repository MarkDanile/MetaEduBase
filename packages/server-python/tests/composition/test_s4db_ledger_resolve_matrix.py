"""R1-S4-D-B：ledger resolve + activation 测试矩阵。

契约事实源：Plan §R1-S4-D 契约细化（PR #541 已合并 `51a12df6`）D-B-1/D-B-2/D-B-3/
D-Act-1：

- **共享层（D-B-1）**：`register_issue`/`recompute_projection` 从 backfill 私有升
  共享（`agent_transport_ledger_service.py`）——backfill/consumer/participant
  同一投影实现；本套件验证共享层行为（幂等、owner 维度、聚合规则）。
- **resolve（D-B-2）**：`resolve_epoch_unresolvable_issue`——集合锁临界区内
  `(id, revision)` CAS `open/acknowledged -> resolved` + `resolution_digest`
  （inbox `receipt_tombstone_digest`）+ `resolved_at`（`ck_..._resolution_evidence`
  强制）+ 投影重算。**只 resolve `conversation_scope` 行**；`tenant_scope`/
  `orphan` 不 resolve（变异：尝试 resolve tenant_scope 行被击杀）。
- **gate 查询（D-B-3）**：`conversation_scope_gate_hits`（participant 内嵌 fail
  closed，purge 前置查与 S5 同一谓词）+ `tenant_scope_gate_hits`（共享查询 S5 消费）。
- **激活（D-Act-1）**：两 transport owner registry 翻 True（merged-boundary 后）
  + 断言同 commit 更新（S3-D P1-7）+ mutation kill（缺 resolve 变红）。

两侧对称（workspace/execution inbox 表）+ 共享层单侧（聚合规则/幂等与表无关）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_transport_ledger_service import (
    conversation_scope_gate_hits,
    recompute_projection,
    register_issue,
    resolve_epoch_unresolvable_issue,
    tenant_scope_gate_hits,
)
from tests.contexts.agent_control_plane.helpers import TENANT_ID

pytestmark = pytest.mark.asyncio

# 两侧对称定义（inbox 表 / owner）。
RESOLVE_SIDES = {
    "workspace": {
        "owner": "workspace.transport.v1",
        "inbox_table": "agent_workspace_inbox",
    },
    "execution": {
        "owner": "execution.transport.v1",
        "inbox_table": "agent_execution_inbox",
    },
}


async def _ensure_test_tenant(db_session):
    """确保 ``TENANT_ID`` 存在于 ``metaedu.tenants``（幂等，S4-C batch3 教训）。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": TENANT_ID,
            "name": "s4db-tenant",
            "school_name": "s4db school",
            "isolation": "shared",
            "now": now,
        },
    )
    await db_session.flush()


async def _seed_reconcile_issue(
    db_session,
    *,
    side: str,
    source_row_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    reconcile_class: str,
    issue_code: str = "epoch_unresolvable",
    state: str = "open",
    revision: int = 1,
    resolution_digest: str | None = None,
) -> uuid.UUID:
    """种一行 reconcile ledger issue（默认 open + revision 1）。返回 issue id。"""
    owner = RESOLVE_SIDES[side]["owner"]
    issue_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_transport_scope_reconcile "
            "(id, tenant_id, owner_key, source_table, source_row_id, conversation_id, "
            " reconcile_class, issue_code, state, revision, resolution_digest, "
            " resolved_at, created_at) "
            "VALUES (:id, :t, :o, :st, :sr, :c, :rc, :ic, :s, :r, :rd, :ra, :now)"
        ),
        {
            "id": issue_id,
            "t": TENANT_ID,
            "o": owner,
            "st": RESOLVE_SIDES[side]["inbox_table"],
            "sr": source_row_id,
            "c": conversation_id,
            "rc": reconcile_class,
            "ic": issue_code,
            "s": state,
            "r": revision,
            "rd": resolution_digest,
            "ra": now if resolution_digest else None,
            "now": now,
        },
    )
    await db_session.flush()
    return issue_id


async def _seed_inbox_with_tombstone(
    db_session, *, side: str, conversation_id: uuid.UUID
) -> uuid.UUID:
    """种一行已 tombstone 的 inbox（receipt_tombstone_digest 为 64-hex 证据）。

    返回 inbox 行 id（= ledger source_row_id）。先种 deleted+expired conversation
    （条件 FK `fk_*_inbox_scope_conv`：inbox 行 conversation_id 非空时必须指向
    存在的 agent_conversations 行）。
    """
    # deleted+expired conversation（actor tombstone 形态，S4-D-A 矩阵同款）。
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, creator_identity_digest, "
            " state, title, title_source, next_message_seq, next_run_queue_seq, "
            " last_activity_at, purge_state, purge_revision, purged_at, purge_after, "
            " deleted_at, created_at, updated_at, revision, hold_revision, actor_state) "
            "VALUES (:id, :t, NULL, :cd, :cid, 'deleted', 's4db', 'user', 1, 1, "
            " :now, 'scheduled', 1, NULL, :pa, :da, :now, :now, 3, 0, 'redacted') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": conversation_id,
            "t": TENANT_ID,
            "cd": "a" * 64,
            "cid": "b" * 64,
            "now": now,
            "pa": now - timedelta(days=1),
            "da": now - timedelta(days=31),
        },
    )
    inbox_id = uuid.uuid4()
    event_id = uuid.uuid4()
    # 合法 tombstone digest：按 purge_erasure 冻结 envelope 用**同一 event_id**
    # 重算（participant 的 `_receipt_tombstone_digest_matches` 按行内 event_id
    # 重算校验——td 与 eid 不一致会 mismatch fail closed，erase 在 resolve 前
    # 即抛错）。
    from app.contexts.agent_execution.domain.snapshots import snapshot_digest

    td = snapshot_digest(
        {
            "schema_version": 1,
            "reason": "purge_erasure",
            "event_id": str(event_id),
        }
    )
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.{RESOLVE_SIDES[side]['inbox_table']} "
            "(id, tenant_id, consumer_name, event_id, event_type, schema_version, "
            " payload_digest, correlation_id, status, conversation_id, "
            " producer_purge_revision, last_error_code, receipt_tombstone_state, "
            " receipt_tombstone_digest, created_at) "
            "VALUES (:id, :t, :cn, :eid, :et, 1, :d, :corr, 'rejected', :c, :r, "
            " :lec, 'redacted', :td, :now)"
        ),
        {
            "id": inbox_id,
            "t": TENANT_ID,
            "cn": "workspace.transport.v1" if side == "workspace"
            else "execution.transport.v1",
            "eid": event_id,
            "et": (
                "turn.requested.v1"
                if side == "workspace"
                else "assistant_message.publish_requested.v1"
            ),
            "d": "a" * 64,
            "corr": uuid.uuid4(),
            "c": conversation_id,
            "r": 1,
            "lec": "epoch_unknown_rejected",
            "td": td,
            "now": now,
        },
    )
    await db_session.flush()
    return inbox_id


async def _issue_state(db_session, issue_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT state, revision, resolution_digest, resolved_at FROM "
                "metaedu.agent_transport_scope_reconcile WHERE id = :id"
            ),
            {"id": issue_id},
        )
    ).mappings().one()
    return dict(row)


async def _projection(db_session, *, side: str, source_row_id: uuid.UUID) -> str | None:
    row = (
        await db_session.execute(
            text(
                f"SELECT scope_reconcile_state FROM "
                f"metaedu.{RESOLVE_SIDES[side]['inbox_table']} WHERE id = :id"
            ),
            {"id": source_row_id},
        )
    ).scalar_one_or_none()
    return row


# ---------------------------------------------------------------------------
# 01. resolve：conversation_scope CAS + 证据 + 投影（两侧参数化）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_resolve_conversation_scope_open(db_session, side):
    """open -> resolved：CAS + resolution_digest + resolved_at + 投影 reconciled。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    issue_id = await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
    )
    await db_session.commit()

    ok = await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest="b" * 64,  # inbox receipt_tombstone_digest
    )
    assert ok is True
    st = await _issue_state(db_session, issue_id)
    assert st["state"] == "resolved"
    assert st["revision"] == 2  # CAS bump
    assert st["resolution_digest"] == "b" * 64  # 证据 = inbox receipt tombstone digest
    assert st["resolved_at"] is not None  # ck_..._resolution_evidence
    # 投影重算（participant `_resolve_epoch_issues_after_erase` 同款，同事务）：
    # 全部 resolved -> reconciled。
    await recompute_projection(
        db_session,
        table=RESOLVE_SIDES[side]["inbox_table"],
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        source_row_id=inbox_id,
    )
    assert (
        await _projection(db_session, side=side, source_row_id=inbox_id)
        == "reconciled"
    )


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_resolve_conversation_scope_acknowledged(db_session, side):
    """acknowledged -> resolved（中间态续做）。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    issue_id = await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        state="acknowledged",
        revision=2,
    )
    await db_session.commit()

    ok = await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest="b" * 64,
    )
    assert ok is True
    st = await _issue_state(db_session, issue_id)
    assert st["state"] == "resolved"
    assert st["revision"] == 3


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_resolve_already_resolved_digest_match_noop(db_session, side):
    """已 resolved + digest 匹配 -> no-op（幂等重放，不重复 bump）。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    issue_id = await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        state="resolved",
        revision=3,
        resolution_digest="b" * 64,
    )
    await db_session.commit()

    ok = await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest="b" * 64,
    )
    assert ok is True
    st = await _issue_state(db_session, issue_id)
    assert st["state"] == "resolved"
    assert st["revision"] == 3  # 不重复 bump（幂等）


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_resolve_already_resolved_digest_mismatch_fail_closed(db_session, side):
    """已 resolved + digest 不匹配 -> fail closed（不覆盖证据）。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        state="resolved",
        revision=3,
        resolution_digest="b" * 64,
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await resolve_epoch_unresolvable_issue(
            db_session,
            tenant_id=TENANT_ID,
            owner_key=RESOLVE_SIDES[side]["owner"],
            table=RESOLVE_SIDES[side]["inbox_table"],
            source_row_id=inbox_id,
            resolution_digest="c" * 64,  # 不匹配
        )


# ---------------------------------------------------------------------------
# 02. resolve 边界：tenant_scope / orphan 不 resolve（变异击杀）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
@pytest.mark.parametrize(
    "bad_class", ["tenant_scope", "orphan"]
)
async def test_resolve_tenant_scope_orphan_fail_closed(db_session, side, bad_class):
    """participant 尝试 resolve tenant_scope/orphan 行 -> fail closed（变异击杀）。

    只 resolve ``conversation_scope`` 行；tenant_scope/orphan 不 resolve、不改投影
    （留 S5 scheduler/运维闭环）。
    """
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=None,  # tenant_scope/orphan 不带 conversation_id
        reconcile_class=bad_class,
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await resolve_epoch_unresolvable_issue(
            db_session,
            tenant_id=TENANT_ID,
            owner_key=RESOLVE_SIDES[side]["owner"],
            table=RESOLVE_SIDES[side]["inbox_table"],
            source_row_id=inbox_id,
            resolution_digest="b" * 64,
        )


# ---------------------------------------------------------------------------
# 03. gate 查询（D-B-3）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_participant_gate_blocks_then_resolve_unblocks(db_session, side):
    """族 2：participant 内嵌 conversation_scope gate blocked（三方一致）+ resolve 后解除。

    gate 命中 -> erase_transport_owner 返回 blocked（reason_code =
    purge_blocked_by_conversation_scope_gate + checkpoint/operation/Conversation
    三方一致，不抛异常——三面 P1-1 修复验证）；resolve 后重试 -> gate 解除正常 ACK。
    """
    from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (  # noqa: E501
        ExecutionTransportErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (  # noqa: E501
        WorkspaceTransportErasureParticipant,
    )

    await _ensure_test_tenant(db_session)
    # purge operation + checkpoint（与 S4-D-A 矩阵同款）——issue 必须挂同一
    # conversation（gate 按 conversation_id 查）。
    from tests.composition.test_s4da_transport_participant_matrix import (
        _make_purge_operation,
        _seed_deleted_expired_conversation,
    )

    conv_id2, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=RESOLVE_SIDES[side]["owner"]
    )
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id2
    )
    await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id2,
        reconcile_class="conversation_scope",
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id2, purge_rev, owner=RESOLVE_SIDES[side]["owner"]
    )
    await db_session.commit()

    participant = (
        WorkspaceTransportErasureParticipant(db_session)
        if side == "workspace"
        else ExecutionTransportErasureParticipant(db_session)
    )
    # gate 命中 -> blocked（不抛异常，三方一致）。
    outcome = await participant.erase_transport_owner(
        tenant_id=TENANT_ID,
        conversation_id=conv_id2,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
        expected_lease_epoch=0,
    )
    assert outcome.blocked is True
    assert (
        outcome.block_reason == "purge_blocked_by_conversation_scope_gate"
    )
    cp = (
        await db_session.execute(
            text(
                "SELECT state, reason_code FROM "
                "metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert cp["state"] == "blocked"
    assert cp["reason_code"] == "purge_blocked_by_conversation_scope_gate"
    op = (
        await db_session.execute(
            text(
                "SELECT state, failure_code FROM metaedu.agent_conversation_purges "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert op["state"] == "blocked"
    assert op["failure_code"] == "purge_blocked_by_conversation_scope_gate"
    conv = (
        await db_session.execute(
            text(
                "SELECT purge_state FROM metaedu.agent_conversations "
                "WHERE id = :c"
            ),
            {"c": conv_id2},
        )
    ).scalar_one()
    assert conv == "blocked"

    # resolve 后 gate 解除 -> 重试正常 ACK（blocked->erasing 恢复）。
    # 用 inbox 行实际的 receipt_tombstone_digest（与 seed 的合法 digest 一致）。
    actual_digest = (
        await db_session.execute(
            text(
                f"SELECT receipt_tombstone_digest FROM "
                f"metaedu.{RESOLVE_SIDES[side]['inbox_table']} WHERE id = :id"
            ),
            {"id": inbox_id},
        )
    ).scalar_one()
    await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest=actual_digest,
    )
    await db_session.commit()
    assert (
        await conversation_scope_gate_hits(
            db_session, tenant_id=TENANT_ID, conversation_id=conv_id2
        )
        is False
    )
    outcome2 = await participant.erase_transport_owner(
        tenant_id=TENANT_ID,
        conversation_id=conv_id2,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=3,  # 首次 blocked 已 bump 1->2->3
        expected_lease_epoch=0,
    )
    assert outcome2.blocked is False
    assert outcome2.ack_digest is not None


async def test_conversation_scope_gate_hits(db_session):
    """conversation_scope gate：未 resolved 命中 True；全 resolved 后 False。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side="workspace", conversation_id=conv_id
    )
    await _seed_reconcile_issue(
        db_session,
        side="workspace",
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
    )
    await db_session.commit()

    assert (
        await conversation_scope_gate_hits(
            db_session, tenant_id=TENANT_ID, conversation_id=conv_id
        )
        is True
    )

    # resolve 后 gate 解除。
    await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        table="agent_workspace_inbox",
        source_row_id=inbox_id,
        resolution_digest="b" * 64,
    )
    await db_session.commit()
    assert (
        await conversation_scope_gate_hits(
            db_session, tenant_id=TENANT_ID, conversation_id=conv_id
        )
        is False
    )


async def test_tenant_scope_gate_hits(db_session):
    """tenant_scope gate：未 resolved 命中 True；全 resolved 后 False（共享查询）。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side="workspace", conversation_id=conv_id
    )
    await _seed_reconcile_issue(
        db_session,
        side="workspace",
        source_row_id=inbox_id,
        conversation_id=None,
        reconcile_class="tenant_scope",
        issue_code="ambiguous_mapping",
    )
    await db_session.commit()

    assert (
        await tenant_scope_gate_hits(db_session, tenant_id=TENANT_ID) is True
    )

    # 运维置 resolved（S5 动作）后 gate 解除。
    issue = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND reconcile_class = 'tenant_scope'"
            ),
            {"t": TENANT_ID},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_transport_scope_reconcile "
            "SET state = 'resolved', revision = revision + 1, "
            "resolution_digest = :rd, resolved_at = clock_timestamp() "
            "WHERE id = :id"
        ),
        {"rd": "d" * 64, "id": issue},
    )
    await db_session.commit()
    assert (
        await tenant_scope_gate_hits(db_session, tenant_id=TENANT_ID) is False
    )


# ---------------------------------------------------------------------------
# 03b. 族 3：ledger resolved 不代替 S4-C Tx2 精确终态（exact-terminal replay）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_ledger_resolved_does_not_skip_tx2_terminal_check(db_session, side):
    """族 3：ledger issue 已 resolved + outbox 仍 claimed -> 重放不因 resolved 放行。

    S4-C 状态表 round-6/7：ledger `resolved` 只证明 tombstone evidence 有效，
    **不代替**独立 Tx2 已把 outbox 置精确终态——Tx1 提交 -> Tx2 崩溃 -> resolve ->
    重放时 outbox 仍 `claimed`：重放须锁后检查 outbox 精确终态三分支。本用例验证
    「resolve 证据不会放行 claimed outbox」——resolve 误放行（跳过终态检查）的
    变异被击杀。
    """
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    issue_id = await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
    )
    # resolve 该 issue（ledger 置 resolved + 证据）。
    actual_digest = (
        await db_session.execute(
            text(
                f"SELECT receipt_tombstone_digest FROM "
                f"metaedu.{RESOLVE_SIDES[side]['inbox_table']} WHERE id = :id"
            ),
            {"id": inbox_id},
        )
    ).scalar_one()
    await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest=actual_digest,
    )
    await db_session.commit()
    st = await _issue_state(db_session, issue_id)
    assert st["state"] == "resolved"

    # ledger resolved 后，S4-C Tx2 重放仍须检查 outbox 精确终态——本矩阵验证
    # resolve 不触碰 outbox（participant 只写 inbox 行 ledger）：outbox 行不受
    # resolve 影响（保持原状态，无 suppressed 伪造终态）。
    outbox_table = (
        "agent_workspace_outbox" if side == "workspace" else "agent_execution_outbox"
    )
    outbox_row = (
        await db_session.execute(
            text(
                f"SELECT count(*) FROM metaedu.{outbox_table} "
                f"WHERE tenant_id = :t AND conversation_id = :c"
            ),
            {"t": TENANT_ID, "c": conv_id},
        )
    ).scalar_one()
    # 无 outbox 行被 resolve 侧写（resolve 只写 inbox ledger + 投影）。
    assert outbox_row == 0


# ---------------------------------------------------------------------------
# 03c. 族 3：consumed 无证据行出口（历史 backfill 登记的 issue 无法 resolve）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_consumed_row_without_tombstone_issue_unresolvable(db_session, side):
    """族 3：历史 consumed 行（无 tombstone 证据）+ 已登记 issue -> resolve 不可达。

    backfill（B3）为历史 `producer_purge_revision IS NULL` 行登记
    `conversation_scope/epoch_unresolvable`——但 consumed 行无 receipt_tombstone_
    digest（无证据），participant 的 resolve 谓词（tombstone 证据）不命中该行，
    gate 永不解除。**契约缺口记录**：历史 consumed 行的 resolve 由 S5
    scheduler/运维路径处理（本 PR 只冻结 Tx1 新写场景）；本用例证明「无证据不
    resolve」的 fail-closed 语义成立（不伪造证据）。
    """
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = uuid.uuid4()
    # deleted+expired conversation（FK `fk_*_inbox_scope_conv` 需存在）。
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, creator_identity_digest, "
            " state, title, title_source, next_message_seq, next_run_queue_seq, "
            " last_activity_at, purge_state, purge_revision, purged_at, purge_after, "
            " deleted_at, created_at, updated_at, revision, hold_revision, actor_state) "
            "VALUES (:id, :t, NULL, :cd, :cid, 'deleted', 's4db-consumed', 'user', "
            " 1, 1, :now, 'scheduled', 1, NULL, :pa, :da, :now, :now, 3, 0, 'redacted') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": conv_id,
            "t": TENANT_ID,
            "cd": "a" * 64,
            "cid": "b" * 64,
            "now": now,
            "pa": now - timedelta(days=1),
            "da": now - timedelta(days=31),
        },
    )
    # 历史 consumed 行（无 tombstone 证据）。
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.{RESOLVE_SIDES[side]['inbox_table']} "
            "(id, tenant_id, consumer_name, event_id, event_type, schema_version, "
            " payload_digest, correlation_id, status, conversation_id, created_at) "
            "VALUES (:id, :t, :cn, :eid, :et, 1, :d, :corr, 'consumed', :c, :now)"
        ),
        {
            "id": inbox_id,
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
            "c": conv_id,
            "now": now,
        },
    )
    await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
    )
    await db_session.commit()

    # participant resolve 谓词只命中已 tombstone 行——consumed 行不命中，
    # issue 保持 open（resolve 不可达，gate 持续命中）。
    assert (
        await conversation_scope_gate_hits(
            db_session, tenant_id=TENANT_ID, conversation_id=conv_id
        )
        is True
    )
    st = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND source_row_id = :sr"
            ),
            {"t": TENANT_ID, "sr": inbox_id},
        )
    ).scalar_one()
    assert st == "open"  # 未被 resolve（无证据，fail closed 不伪造）


# ---------------------------------------------------------------------------
# 04. 共享层（D-B-1）：幂等 / owner 维度 / 聚合规则（与表无关，单侧 workspace）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_resolve_cas_zero_rows_conflict_returns_false(db_session, side):
    """族 4：CAS 0 行命中（revision 已变）-> 返回 False（B1(d) 并发冲突语义）。

    种 open+rev1 行 -> 并发改为 acknowledged+rev2 -> resolve 读到当前 rev2 的
    CAS -> 成功续做；行不存在 -> 返回 False（不抛错、不改证据）。
    """
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side=side, conversation_id=conv_id
    )
    issue_id = await _seed_reconcile_issue(
        db_session,
        side=side,
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
    )  # open + revision 1
    await db_session.commit()

    # 并发修改：state -> acknowledged + revision bump（模拟另一事务推进）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_transport_scope_reconcile "
            "SET state = 'acknowledged', revision = revision + 1 "
            "WHERE id = :id"
        ),
        {"id": issue_id},
    )
    await db_session.commit()

    # 行不存在 -> False。
    missing = await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=uuid.uuid4(),  # 不存在的源行
        resolution_digest="b" * 64,
    )
    assert missing is False
    # 已 acknowledged+rev2 的行：resolve 读到当前 rev2 CAS -> 成功续做。
    ok = await resolve_epoch_unresolvable_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key=RESOLVE_SIDES[side]["owner"],
        table=RESOLVE_SIDES[side]["inbox_table"],
        source_row_id=inbox_id,
        resolution_digest="b" * 64,
    )
    assert ok is True
    st = await _issue_state(db_session, issue_id)
    assert st["state"] == "resolved"
    assert st["revision"] == 3  # 2 -> 3（CAS bump）


# ---------------------------------------------------------------------------
# 05. 共享层（D-B-1）：幂等 / owner 维度 / 聚合规则（与表无关，单侧 workspace）
# ---------------------------------------------------------------------------


async def test_register_issue_idempotent(db_session):
    """register_issue 幂等：同 issue_code 重复登记不新建（ON CONFLICT DO NOTHING）。"""
    await _ensure_test_tenant(db_session)
    inbox_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    await db_session.commit()

    first = await register_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        table="agent_workspace_inbox",
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        issue_code="epoch_unresolvable",
    )
    second = await register_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        table="agent_workspace_inbox",
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        issue_code="epoch_unresolvable",
    )
    assert first is True
    assert second is False  # 幂等不新建
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND source_row_id = :sr"
            ),
            {"t": TENANT_ID, "sr": inbox_id},
        )
    ).scalar_one()
    assert count == 1


async def test_recompute_projection_orphan_priority(db_session):
    """投影聚合：orphan 类 issue 存在 -> 'orphan'（最高优先级，即便其他未 resolved）。"""
    await _ensure_test_tenant(db_session)
    conv_id = uuid.uuid4()
    inbox_id = await _seed_inbox_with_tombstone(
        db_session, side="workspace", conversation_id=conv_id
    )
    await db_session.commit()
    await register_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        table="agent_workspace_inbox",
        source_row_id=inbox_id,
        conversation_id=conv_id,
        reconcile_class="conversation_scope",
        issue_code="epoch_unresolvable",
    )
    await register_issue(
        db_session,
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        table="agent_workspace_inbox",
        source_row_id=inbox_id,
        conversation_id=None,
        reconcile_class="orphan",
        issue_code="conversation_deleted_orphan",
    )
    await db_session.commit()

    await recompute_projection(
        db_session,
        table="agent_workspace_inbox",
        tenant_id=TENANT_ID,
        owner_key="workspace.transport.v1",
        source_row_id=inbox_id,
    )
    await db_session.commit()
    assert (
        await _projection(
            db_session, side="workspace", source_row_id=inbox_id
        )
        == "orphan"
    )
