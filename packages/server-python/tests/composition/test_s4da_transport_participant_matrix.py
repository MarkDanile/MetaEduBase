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
- **registry（S4-D-B merged-boundary 后翻 True）**：participant 入口 capability gate
  放行（`require_capability(transport_owner, "erase")` 不抛）——S4-D-A 阶段该 gate
  fail closed 是预期，S4-D-B 翻 True 后断言同 commit 更新（S3-D P1-7 先例）。
- **边界**：resolve 只处理 `conversation_scope` 行（`tenant_scope`/`orphan` 不
  resolve 留 S5/运维）、不导入 backfill 私有函数。

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
    OwnerRegistryChangedError,
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
    db_session, *, owner: str, title: str = "s4d conversation"
) -> tuple[uuid.UUID, int]:
    """建 deleted+expired（恢复窗口已过）会话 + transport fence（active）。

    返回 (conversation_id, purge_revision)。fence 用 ``owner``（transport owner）
    建立，模拟 purge 推进前的 baseline。
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
            "o": owner,
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
    if status == "suppressed":
        # suppressed 分支：正文必须为 NULL（ck_*_outbox_payload），payload_digest 保留。
        assert payload_inline is None and payload_ref is None
    else:
        # 非 suppressed 分支：payload_inline/payload_ref 恰一非空。
        if payload_inline is None:
            payload_inline = {"body": "sensitive"} if payload_ref is None else None
        assert (payload_inline is not None) != (payload_ref is not None)
    table = TRANSPORT_SIDES[side]["outbox_table"]
    row_id = uuid.uuid4()
    digest = _payload_digest(payload_inline or {"ref": payload_ref})
    now = datetime.now(UTC).replace(tzinfo=None)
    # JSONB 参数经字符串 + CAST(:pi AS jsonb) 显式转换（asyncpg 不编码 dict 参数）。
    # suppressed 分支正文必须为 NULL；ref 分支 inline 传 '{}'（不落正文值）。
    payload_inline_json = (
        _json_dumps(payload_inline) if payload_inline is not None else None
    )
    if side == "workspace":
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.{table} "
                "(id, tenant_id, event_type, schema_version, aggregate_id, "
                "aggregate_type, payload_inline, payload_ref, payload_digest, "
                "correlation_id, status, attempt_count, conversation_id, "
                "producer_purge_revision, last_error_code, created_at, "
                "next_attempt_at, scope_reconcile_state) "
                "VALUES (:id, :t, 'turn.requested.v1', 1, :agg, 'workspace.message', "
                "CAST(:pi AS jsonb), :pr, :d, :corr, :s, 0, :c, :r, :lec, :now, "
                ":now, :sc)"
            ),
            {
                "id": row_id,
                "t": TENANT_ID,
                "agg": uuid.uuid4(),
                "pi": payload_inline_json,
                "pr": payload_ref,
                "d": digest,
                "corr": uuid.uuid4(),
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
                ":agg, 'execution.run', CAST(:pi AS jsonb), :pr, :d, :corr, :s, 0, "
                ":now, :c, :r, :lec, :da, :dr, :dd, :de, :now, :sc)"
            ),
            {
                "id": row_id,
                "t": TENANT_ID,
                "agg": uuid.uuid4(),
                "pi": payload_inline_json,
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


async def _seed_run(
    db_session,
    *,
    conversation_id: uuid.UUID,
    output_publish_state: str = "pending",
) -> uuid.UUID:
    """种一行 execution Run（output_publish_state 指定，默认 pending）。

    满足全部 Run CHECK：definition_version/runtime_profile FK 父行、
    `ck_agent_run_terminal_envelope`（completed 须 ended_at + terminal_result_digest
    + terminal_code/reason）、`ck_agent_run_sequences`（next_event_seq =
    last_event_seq+1 等）、creation_digest 64-hex。
    """
    from app.contexts.agent_execution.domain.snapshots import snapshot_digest

    run_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    def_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    # suppressed = R1 tombstone 分支（终端字段全 NULL，保留 digest/size）；
    # pending/published/dead_letter = completed + 完整 terminal envelope；
    # not_required = 非 completed 终态（failed/cancelled/expired，`ck_agent_run_
    # terminal_output` 分支 2：status<>'completed' + 无终端字段 + not_required）。
    suppressed = output_publish_state == "suppressed"
    not_required = output_publish_state == "not_required"
    run_status = "failed" if not_required else "completed"
    tref = None if (suppressed or not_required) else f"run://{run_id}/terminal"
    tmid = None if (suppressed or not_required) else uuid.uuid4()
    tmedia = None if (suppressed or not_required) else "text/markdown"
    tclass = None if (suppressed or not_required) else "internal"
    # not_required：非 completed 分支要求全部 terminal output 字段 NULL
    # （含 output_digest/size，`ck_agent_run_terminal_output` 分支 2）。
    tod = None if not_required else "3" * 64
    tosize = None if not_required else 10
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            " created_by, created_at) "
            "VALUES (:id, :t, 'k', 1, 'published', :d, :a, :now)"
        ),
        {"id": def_id, "t": TENANT_ID, "d": "4" * 64, "a": uuid.uuid4(), "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            " capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES (:id, :t, 'p', 'compat', 'direct_rag', :d, :d2, true, 1, "
            " :now, :now)"
        ),
        {"id": profile_id, "t": TENANT_ID, "d": "5" * 64, "d2": "5" * 64, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            " agent_definition_version_id, runtime_profile_id, creation_digest, "
            " status, status_revision, next_event_seq, first_available_event_seq, "
            " last_event_seq, event_log_complete, queued_at, ended_at, terminal_code, "
            " terminal_reason, terminal_result_digest, terminal_output_ref, "
            " terminal_output_digest, terminal_output_size, terminal_output_media_type, "
            " terminal_output_classification, terminal_message_id, "
            " output_publish_state, created_by, correlation_id, "
            " runtime_capability_snapshot, run_config_snapshot, budget_snapshot, "
            " usage_summary, created_at, updated_at) "
            "VALUES (:id, :t, :c, 1, :root, :def, :prof, :cd, :run_status, 1, 1, 1, 0, "
            " true, :now, :now, 'failed', 'err', :trd, :tref, :tod, :tosize, "
            " :tmedia, :tclass, :tmid, :s, "
            " :cb, :corr, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
            " :now, :now)"
        ),
        {
            "id": run_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "root": uuid.uuid4(),
            "def": def_id,
            "prof": profile_id,
            "cd": "1" * 64,
            "run_status": run_status,
            "trd": snapshot_digest({"run": str(run_id)}),
            "tref": tref,
            "tod": tod,
            "tosize": tosize,
            "tmedia": tmedia,
            "tclass": tclass,
            "tmid": tmid,
            "s": output_publish_state,
            "cb": uuid.uuid4(),
            "corr": uuid.uuid4(),
            "now": now,
        },
    )
    await db_session.flush()
    return run_id


async def _seed_transport_inbox(
    db_session,
    *,
    conversation_id: uuid.UUID,
    side: str,
    status: str = "processing",
    last_error_code: str | None = None,
    receipt_tombstone_digest: str | None = None,
    event_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """种一行 transport inbox（默认 processing）。返回 inbox 行 id。

    ``receipt_tombstone_digest`` 非空时同写 ``receipt_tombstone_state='redacted'``
    （同生同灭，`ck_*_receipt_tombstone`）。已 tombstone 行的 digest 由**调用方**
    传入：noop 用例须用与 participant 相同的冻结 envelope 计算（
    ``snapshot_digest({schema_version:1, reason:'purge_erasure', event_id})``，
    传入同一 ``event_id``）；mismatch 反例传伪 digest（如 ``'d'*64``）。
    """
    table = TRANSPORT_SIDES[side]["inbox_table"]
    row_id = uuid.uuid4()
    event_id = event_id or uuid.uuid4()
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
            "eid": event_id,
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
async def test_outbox_pending_inline_cleared_to_suppressed(
    db_session, side
):
    """pending + inline 正文 -> scan 命中 -> 转 suppressed 清正文留 digest。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
async def test_outbox_cancelled_cleared_evidence_retained(
    db_session, side
):
    """S4-C Tx2 终态化残留：cancelled + 保留 payload -> 仍 scan 命中清正文。

    `cancelled` 是 S4-C 消费侧终态（payload 必经保留），**不是清除免除依据**；
    execution 侧 decision 四元、workspace 侧 last_error_code 终态证据不得清除。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
async def test_outbox_payload_ref_only_cleared(
    db_session, side
):
    """族 3：payload_ref only 行（inline NULL）被正文事实谓词命中清除。

    谓词是 ``payload_inline IS NOT NULL OR payload_ref IS NOT NULL``——ref-only
    变异（谓词退化只查 inline）被此用例击杀。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    outbox_id = await _seed_transport_outbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        payload_inline=None,
        payload_ref="s3://bucket/sensitive-object",
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "suppressed"
    assert row["payload_inline"] is None
    assert row["payload_ref"] is None  # ref 也被清
    assert row["payload_digest"] is not None  # digest 保留


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_claimed_published_dead_letter_cleared(
    db_session, side
):
    """claimed/published/dead_letter/cancelled 行同样被正文事实谓词命中清除。

    **族 3**：cancelled 并入循环（S4-C Tx2 终态残留），断言清除值而非依赖 DB
    CHECK 偶然拦截。
    """
    await _ensure_test_tenant(db_session)
    for status in ("claimed", "published", "dead_letter", "cancelled"):
        conv_id, purge_rev = await _seed_deleted_expired_conversation(
            db_session, owner=TRANSPORT_SIDES[side]["owner"]
        )
        decision = None
        last_error_code = None
        if status == "cancelled":
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
            status=status,
            decision=decision,
            last_error_code=last_error_code,
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
        assert row["payload_digest"] is not None  # digest 保留（全部状态分支）
        # P3-3：全部状态分支都断言 claim 列不被 participant 改写（DB 无 CHECK 兜底）。
        assert row["claimed_by"] is None
        assert row["claimed_at"] is None
        if status == "cancelled":
            # 族 3：终态证据保留（Tx2 已清，participant 保持 NULL）。
            if side == "execution":
                assert row["decision_actor_id"] == uuid.UUID(int=0)
                assert row["decision_reason"] == "epoch_unknown_rejected"
            else:
                assert row["last_error_code"] == "epoch_unknown_rejected"


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_suppressed_skipped(
    db_session, side
):
    """已 suppressed（无正文）行不命中 scan，无状态变化。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    outbox_id = await _seed_transport_outbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="suppressed",
    )
    # suppressed 分支：正文 NULL + digest 保留（种子已满足 ck_*_outbox_payload）。
    table = TRANSPORT_SIDES[side]["outbox_table"]
    row = await _outbox_row(db_session, table, outbox_id)
    assert row["status"] == "suppressed"
    assert row["payload_inline"] is None
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
async def test_inbox_processing_rejected_tombstone(
    db_session, side
):
    """processing -> rejected + tombstone（与 S4-C Tx1 对齐）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
async def test_inbox_consumed_rejected_idempotent_tombstone(
    db_session, side
):
    """已 consumed/rejected 保留原 status 仅补幂等 tombstone。"""
    await _ensure_test_tenant(db_session)
    for status in ("consumed", "rejected"):
        conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
async def test_inbox_already_tombstoned_digest_match_noop(
    db_session, side
):
    """已 tombstone + digest 精确匹配 -> no-op（幂等重放，不改 status）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    # 用与 participant 相同的冻结 envelope 计算真实 digest（同一 event_id）。
    from app.contexts.agent_execution.domain.snapshots import snapshot_digest

    event_id = uuid.uuid4()
    existing_digest = snapshot_digest(
        {
            "schema_version": 1,
            "reason": "purge_erasure",
            "event_id": str(event_id),
        }
    )
    inbox_id = await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        receipt_tombstone_digest=existing_digest,
        event_id=event_id,
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
async def test_inbox_tombstone_digest_mismatch_fail_closed(
    db_session, side
):
    """已 tombstone + digest 不匹配 -> fail closed（*IntegrationConflictError 不静默）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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


@pytest.mark.parametrize("side", ["workspace", "execution"])
@pytest.mark.parametrize("epoch_code", ["epoch_unknown_rejected", "epoch_stale_rejected"])
async def test_inbox_s4c_tx1_tombstone_interop_noop(
    db_session, side, epoch_code
):
    """互操作（终态/证据互操作批次）：S4-C Tx1 合法 tombstone 证据 -> no-op 保留。

    含 Tx1 epoch-rejected receipt 的 conversation purge 不得因 digest 重算差异
    fail closed 卡死——`status='rejected'` + `last_error_code` 为 epoch code +
    按该 code 重算 digest 精确匹配 -> no-op（保留原证据，不重写、不改 status）。
    两侧 × 两个 epoch code 参数化。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    # 用 S4-C Tx1 冻结 envelope（reason=epoch code）计算真实 digest。
    from app.contexts.agent_execution.domain.snapshots import snapshot_digest

    event_id = uuid.uuid4()
    tx1_digest = snapshot_digest(
        {
            "schema_version": 1,
            "reason": epoch_code,
            "event_id": str(event_id),
        }
    )
    inbox_id = await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        last_error_code=epoch_code,
        receipt_tombstone_digest=tx1_digest,
        event_id=event_id,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # no-op：原证据完整保留（不重写、不改 status）。
    row = await _inbox_row(db_session, TRANSPORT_SIDES[side]["inbox_table"], inbox_id)
    assert row["status"] == "rejected"
    assert row["receipt_tombstone_state"] == "redacted"
    assert row["receipt_tombstone_digest"] == tx1_digest  # 原 digest 保留
    assert row["last_error_code"] == epoch_code


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_s4c_tx1_wrong_code_fail_closed(
    db_session, side
):
    """互操作反例：rejected + last_error_code 非 epoch code -> 仍 fail closed。

    ``last_error_code`` 为未知 code（如 'other_reason'）时，即便 status='rejected'
    也不得放行（不能把任意 rejected 行当 S4-C 证据）。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        last_error_code="some_other_reason",
        receipt_tombstone_digest="e" * 64,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    conflict_error = (
        WorkspaceIntegrationConflictError
        if side == "workspace"
        else ExecutionIntegrationConflictError
    )
    with pytest.raises(conflict_error):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)


@pytest.mark.parametrize("side", ["workspace", "execution"])
@pytest.mark.parametrize("epoch_code", ["epoch_unknown_rejected", "epoch_stale_rejected"])
async def test_inbox_s4c_tx1_code_ok_wrong_digest_fail_closed(
    db_session, side, epoch_code
):
    """判别力反例：合法 epoch code + 错误 digest -> fail closed。

    若实现退化为只检查 code 不检查 digest，本用例变红——精确三元条件
    （status + last_error_code + digest 重算）逐项都必须成立。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="rejected",
        last_error_code=epoch_code,
        receipt_tombstone_digest="f" * 64,  # 合法 code 但错误 digest
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    conflict_error = (
        WorkspaceIntegrationConflictError
        if side == "workspace"
        else ExecutionIntegrationConflictError
    )
    with pytest.raises(conflict_error):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)


@pytest.mark.parametrize("side", ["workspace", "execution"])
@pytest.mark.parametrize("epoch_code", ["epoch_unknown_rejected", "epoch_stale_rejected"])
async def test_inbox_s4c_tx1_code_ok_non_rejected_fail_closed(
    db_session, side, epoch_code
):
    """判别力反例：合法 epoch code + 正确 digest 但 status != 'rejected' -> fail closed。

    若实现忽略 ``status='rejected'`` 条件（把任意 status 的 epoch-code 行当证据），
    本用例变红。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    from app.contexts.agent_execution.domain.snapshots import snapshot_digest

    event_id = uuid.uuid4()
    tx1_digest = snapshot_digest(
        {
            "schema_version": 1,
            "reason": epoch_code,
            "event_id": str(event_id),
        }
    )
    await _seed_transport_inbox(
        db_session,
        conversation_id=conv_id,
        side=side,
        status="consumed",  # 非 rejected：不是 S4-C Tx1 证据形态
        last_error_code=epoch_code,
        receipt_tombstone_digest=tx1_digest,
        event_id=event_id,
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    conflict_error = (
        WorkspaceIntegrationConflictError
        if side == "workspace"
        else ExecutionIntegrationConflictError
    )
    with pytest.raises(conflict_error):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_erase_acks_checkpoint_and_fence(
    db_session, side
):
    """正文全清 + scan 为零 -> fence erasing->erased + checkpoint pending->acked。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
async def test_ack_lost_erased_fence_repairs_pending_checkpoint(
    db_session, side
):
    """ACK 丢失恢复：fence 已 erased 但 checkpoint 仍 pending -> 幂等重放补 ACK。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
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
    # 重放须传当前 operation revision（首次 erase 已 bump 1->2，S2-D _op_revision
    # 追踪模式）。
    await _run_participant_erase(
        db_session,
        conv_id,
        purge_rev,
        op_id,
        side,
        expected_operation_revision=2,
    )

    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.ACKED.value


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_erase_fencing_full(
    db_session, monkeypatch, side
):
    """fencing 全套：lease_epoch / registry drift（operation 后 registry 变化）fail closed。

    registry drift 子用例（用户要求 6）：operation 在激活 registry 下建立（持久化
    snapshot/digest 与测试期 registry 一致）后**再改变测试 registry**，验证
    snapshot/digest fencing 检出漂移（``OwnerRegistryChangedError``）。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    outbox_id = await _seed_transport_outbox(
        db_session, conversation_id=conv_id, side=side
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 子用例 1：篡改 operation lease_epoch -> stale lease fail closed（S2-D/E 同款
    # ValueError），零变更。
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
    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "pending"
    assert row["payload_inline"] is not None
    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.PENDING.value

    # 还原 lease_epoch（子用例 2 只验证 registry drift，不受 stale lease 干扰）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET lease_epoch = 0 "
            "WHERE id = :op"
        ),
        {"op": op_id},
    )
    await db_session.commit()

    # 子用例 2：operation 建立后 registry 变化（drift）-> snapshot/digest fencing
    # 检出（OwnerRegistryChangedError），零变更。用 monkeypatch 覆盖当前激活
    # registry（fixture 作用域内自动还原，不污染其他用例）。
    from dataclasses import replace

    import app.composition.agent_erasure_registry as registry_module

    def _bump_owner_version(owner: registry_module.OwnerDefinition):
        if owner.owner_key == TRANSPORT_SIDES[side]["owner"]:
            return replace(owner, owner_version=owner.owner_version + 1)
        return owner

    drifted = tuple(_bump_owner_version(o) for o in registry_module._OWNER_DEFINITIONS)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", drifted)
    monkeypatch.setattr(
        registry_module,
        "_OWNERS_BY_KEY",
        {o.owner_key: o for o in drifted},
    )
    with pytest.raises(OwnerRegistryChangedError):
        await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # 零变更（drift 拒绝后）。
    row = await _outbox_row(db_session, TRANSPORT_SIDES[side]["outbox_table"], outbox_id)
    assert row["status"] == "pending"
    assert row["payload_inline"] is not None
    assert await _checkpoint_state(db_session, op_id) == PurgeOwnerState.PENDING.value


# ---------------------------------------------------------------------------
# 03b. 族 1/族 2：Run 维度只读判定 + 残留正文 -> blocked（反向判别）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("run_state", ["pending", "dead_letter"])
async def test_execution_run_unsettled_blocks(
    db_session, run_state
):
    """族 1 + 终态互操作：Run output_publish_state IN ('pending','dead_letter') -> blocked。

    pending/dead_letter 是未决/失败投影的合法中间态，S3-D 会清除——transport
    scan 计入残留必须 blocked（reason_code + checkpoint/operation 三方一致）。
    两者参数化（谓词退化为只保留 pending 的变异被击杀）。
    participant 只读判定——Run 行本身不被改写（正文清除归 S3-D）。
    """
    side = "execution"
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    run_id = await _seed_run(
        db_session, conversation_id=conv_id, output_publish_state=run_state
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # final scan 非零（Run pending）-> blocked 正常返回（不抛异常），三方一致。
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
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_transport_scan_nonzero"
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
    assert op["failure_code"] == "purge_blocked_by_transport_scan_nonzero"
    conv = (
        await db_session.execute(
            text(
                "SELECT purge_state FROM metaedu.agent_conversations "
                "WHERE id = :c"
            ),
            {"c": conv_id},
        )
    ).scalar_one()
    assert conv == "blocked"
    # Run 行未被 participant 改写（只读判定，正文清除归 S3-D）。
    row = (
        await db_session.execute(
            text(
                "SELECT output_publish_state FROM metaedu.agent_runs WHERE id = :id"
            ),
            {"id": run_id},
        )
    ).scalar_one()
    assert row == run_state


async def test_execution_run_suppressed_passes(db_session):
    """族 1 反例：Run 已 suppressed -> scan 不计残留，erase 正常 ACK。"""
    side = "execution"
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_run(
        db_session, conversation_id=conv_id, output_publish_state="suppressed"
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    assert (
        await _checkpoint_state(db_session, op_id)
        == PurgeOwnerState.ACKED.value
    )


@pytest.mark.parametrize(
    "terminal_state", ["not_required", "published", "suppressed"]
)
async def test_execution_run_terminal_states_pass(
    db_session, terminal_state
):
    """终态互操作：not_required/published/suppressed 均为终态 -> pass（不 blocked）。

    ``not_required`` 是 failed/cancelled/expired Run 的合法终态（S3-D 不会改写成
    suppressed）——若计入残留则 purge 永久 blocked；published/suppressed 同理。
    """
    side = "execution"
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_run(
        db_session, conversation_id=conv_id, output_publish_state=terminal_state
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    assert (
        await _checkpoint_state(db_session, op_id)
        == PurgeOwnerState.ACKED.value
    )


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_outbox_erased_replay_fail_closed(db_session, side):
    """erased replay fail-closed（P1-3 改名）：ACK 后 late-write -> erased + 非零 scan。

    首次 erase 清两行 -> ACK；再插入一行（late-write）重放 -> erased fence 幂等
    重放先于 purge 前置 -> erased + 非零 scan = 正文泄漏 -> fail closed ValueError
    （不可在非空正文上补 ACK）。**这是 erased-replay 路径，不是首次 erase 的
    blocked 路径**——真 blocked 路径见 `test_execution_run_unsettled_blocks`。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_transport_outbox(db_session, conversation_id=conv_id, side=side)
    await _seed_transport_outbox(db_session, conversation_id=conv_id, side=side)
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 首次 erase：两行都被清 -> scan 为零 -> ACK。
    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # 再插入一行（模拟 late-write），重放 -> erased + 非零 scan -> fail closed。
    await _seed_transport_outbox(db_session, conversation_id=conv_id, side=side)
    await db_session.commit()

    with pytest.raises(ValueError):
        await _run_participant_erase(
            db_session,
            conv_id,
            purge_rev,
            op_id,
            side,
            expected_operation_revision=2,
        )


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_scan_detects_injected_residual(
    db_session, side
):
    """scan 反向判别（P1-3）：erase body 后注入残留 -> scan 非零（不返回 0）。

    participant 的 UPDATE 清除一切 scan 计数的行（同一事实谓词），故 outbox/inbox
    的首次-erase-blocked 路径在构造上不可达（唯一真 blocked 触发是 Run pending，
    见 `test_execution_run_unsettled_blocks`）；本用例直接验证「scan 检测注入残留
    」——击杀「scan 恒零」变异（erase body 后插行，scan 必须非零）。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_transport_outbox(db_session, conversation_id=conv_id, side=side)
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    participant = _participant_for_side(db_session, side)
    # erase body（清掉已有行）后、final scan 前注入残留（模拟 late-write 窗口）。
    await participant.erase_transport_body(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        now=datetime.now(UTC).replace(tzinfo=None),
    )
    await _seed_transport_outbox(db_session, conversation_id=conv_id, side=side)
    scan = await participant.scan_transport_body(
        tenant_id=TENANT_ID, conversation_id=conv_id
    )
    # 注入残留必须被 scan 检测（scan 恒零变异被击杀）。
    assert scan.outbox_payload_rows == 1
    assert scan.total == 1


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_inbox_erased_replay_fail_closed(db_session, side):
    """erased replay fail-closed（P1-3 改名，inbox 维度）：迟到 receipt -> ValueError。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await _seed_transport_inbox(
        db_session, conversation_id=conv_id, side=side, status="processing"
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # 迟到 receipt（processing）-> 重放 -> erased + 非零 scan -> fail closed。
    await _seed_transport_inbox(
        db_session, conversation_id=conv_id, side=side, status="processing"
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await _run_participant_erase(
            db_session,
            conv_id,
            purge_rev,
            op_id,
            side,
            expected_operation_revision=2,
        )


# ---------------------------------------------------------------------------
# 04. capability gate（registry S4-D-B 已翻 True）+ 锁序
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", ["workspace", "execution"])
async def test_capability_gate_passes_when_registry_true(db_session, side):
    """registry S4-D-B 已翻 True：participant 入口 require_capability(transport_owner,
    "erase") **放行**（S2-D P1-1 模式反向——缺 gate 时此测试仍绿但 erase 主体
    被其他用例覆盖）。

    S4-D-A 阶段该测试断言 fail-closed（registry False）；S4-D-B merged-boundary
    后 registry 翻 True，本测试翻转为断言放行——断言与翻 True 同 commit 更新
    （S3-D P1-7 先例：registry 断言测试须与翻 True 同 commit，否则全量 CI 红被
    误判为回归）。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(
        db_session, owner=TRANSPORT_SIDES[side]["owner"]
    )
    op_id, _ = await _make_purge_operation(
        db_session, conv_id, purge_rev, owner=TRANSPORT_SIDES[side]["owner"]
    )
    await db_session.commit()

    # 直接调用 participant erase 入口——registry True 时 gate 放行（不抛）。
    await _run_participant_erase(db_session, conv_id, purge_rev, op_id, side)

    # erase 正常推进：fence erased + checkpoint acked。
    assert (
        await _fence_state(db_session, conv_id, TRANSPORT_SIDES[side]["owner"])
        == ErasureFenceState.ERASED.value
    )
    assert (
        await _checkpoint_state(db_session, op_id)
        == PurgeOwnerState.ACKED.value
    )


# ---------------------------------------------------------------------------
# helper：调用 participant erase（与实现签名对齐后调整）
# ---------------------------------------------------------------------------


def _participant_for_side(db_session, side: str):
    """构造侧 participant（scan/erase 直接调用用，绕过 erase_transport_owner 编排）。"""
    from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (  # noqa: E501
        ExecutionTransportErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (  # noqa: E501
        WorkspaceTransportErasureParticipant,
    )

    if side == "workspace":
        return WorkspaceTransportErasureParticipant(db_session)
    return ExecutionTransportErasureParticipant(db_session)


async def _run_participant_erase(
    db_session,
    conversation_id: uuid.UUID,
    purge_revision: int,
    op_id: uuid.UUID,
    side: str,
    *,
    expected_operation_revision: int = 1,
) -> None:
    """调用 transport participant erase 主入口（S2-D/S3-D 同签名形状）。

    ``expected_operation_revision`` 默认 1（operation 刚建）；重放/多次 erase 的
    测试须传入当前 revision（S2-D `_op_revision` 追踪模式）。
    """
    from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (  # noqa: E501
        ExecutionTransportErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (  # noqa: E501
        WorkspaceTransportErasureParticipant,
    )

    participant = (
        WorkspaceTransportErasureParticipant(db_session)
        if side == "workspace"
        else ExecutionTransportErasureParticipant(db_session)
    )
    await participant.erase_transport_owner(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=op_id,
        expected_operation_revision=expected_operation_revision,
        expected_lease_epoch=0,
    )


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


def _json_dumps(value: dict) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))
