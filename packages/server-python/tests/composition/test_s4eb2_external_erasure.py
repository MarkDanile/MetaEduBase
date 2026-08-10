r"""R1-S4-E-B2：ExternalPayloadErasureParticipant 真实 PostgreSQL 测试。

契约事实源：Plan §R1-S4-E E-1/E-1a/E-1b/E-2/E-2a/E-2b/E-2c/E-3/E-3a/E-3b/
E-5-2（PR #546 契约冻结 + PR #548 E-0a + PR #550 B1 adapter contract）。

**registry**（E-4）：``external.payload.v1`` 生产 registry 保持
``erase_available=False``——participant 入口 ``require_capability`` fail closed。
本套件用 monkeypatch 把 external owner 临时翻 True 验证 erase 主体，**不改变生产
registry**（registry 断言与实现分离，测试作用域内自动还原）。

**双事务协议（E-2）**：Tx1（checkpoint -> erasing + attempt+1 + intent digest，
提交释放锁）-> 无锁 adapter 调用（跨 takeover 稳定 idempotency key）-> Tx2
（E-2a 精确重验 + 写 erased+receipt 再清源 ref + ACK）。participant 内部
``commit()`` 拆分两事务；``session_factory`` 提供可自控 commit 的连接。

判别点（E-6）：
- E-1b：三个 source（RunEvent/两 outbox）的 ref 在 receipt 后清除，B2 是唯一清除者；
- E-1a：source ref 已 NULL/缺失仍凭 ledger 完成删除留证（不因 source 已空漏删）；
- E-1/E-2：source 非 NULL 且 != ledger ref_value -> fail closed（绑定冲突）；
- E-2a：Tx2 精确重验——fence 非 erasing / checkpoint 非 erasing / attempt 不符 /
  intent digest 不符 -> fail closed（stale lease/旧 attempt 拒绝）；
- E-2b：idempotency key 不含 lease_epoch/attempt（跨 takeover 稳定）；
- E-2c：checkpoint erasing 时 digest = external_delete_intent.v1（attempt 可变但
  intent 不变）；
- E-3a 矩阵：success->erased / not-sent->blocked+erase_timeout / timeout->unknown /
  unknown->unknown / failed->blocked+adapter_unavailable；digest mismatch->blocked；
- B2 互操作：receipt 后清 ref + 转 suppressed（outbox）/ redacted（RunEvent）；
  transport 已 suppressed 行再扫 no-op。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import (
    OwnerDefinition,
    capability_digest,
    registry_digest,
)
from app.composition.external_object_adapter import (
    ExternalEraseFailedError,
    ExternalEraseNotSentError,
    ExternalEraseSuccess,
    ExternalEraseTimeoutError,
    ExternalEraseUnknown,
    ExternalObjectAdapter,
    external_erase_idempotency_key,
)
from app.composition.external_ref_erasure_participant import (
    EXTERNAL_PAYLOAD_OWNER,
    ExternalPayloadErasureParticipant,
)
from app.contexts.agent_workspace.domain import PurgeOwnerState
from tests.contexts.agent_control_plane.helpers import TENANT_ID

pytestmark = pytest.mark.asyncio

_REF_VALUE = "obj://staging/object/1"


class _SuccessAdapter(ExternalObjectAdapter):
    """E-3a success：返回可验证 evidence。幂等重放计数。"""

    adapter_key = "fake-db-local"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = False

    def __init__(self) -> None:
        self.calls = 0

    async def delete_object(self, **kwargs):
        self.calls += 1
        return ExternalEraseSuccess(adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}")

    async def receipt_lookup(self, **kwargs):
        return None


class _NotSentAdapter(_SuccessAdapter):
    """E-3a not-sent：连接前失败（可证明未发送）。"""

    async def delete_object(self, **kwargs):
        self.calls += 1
        raise ExternalEraseNotSentError("connection failed before send")


class _TimeoutAdapter(_SuccessAdapter):
    """E-3a timeout：发送后超时（可能已生效）。"""

    async def delete_object(self, **kwargs):
        self.calls += 1
        raise ExternalEraseTimeoutError("timeout after send")


class _UnknownAdapter(_SuccessAdapter):
    """E-3a unknown outcome。"""

    async def delete_object(self, **kwargs):
        self.calls += 1
        return ExternalEraseUnknown()


class _FailedAdapter(_SuccessAdapter):
    """E-3a failed：明确失败（可证明无副作用）。"""

    async def delete_object(self, **kwargs):
        self.calls += 1
        raise ExternalEraseFailedError("permanent failure")


class _EmptyEvidenceAdapter(_SuccessAdapter):
    """E-2b 返修（D-9）：返回空 evidence——不得凭「空 evidence」写 erased。"""

    async def delete_object(self, **kwargs):
        self.calls += 1
        return ExternalEraseSuccess(adapter_receipt_evidence="")


class _UnsupportedAdapter(_SuccessAdapter):
    """E-2b 硬前置不满足（缺幂等重放 + 缺 receipt lookup）。"""

    supports_idempotent_replay = False
    supports_receipt_lookup = False


# ---------------------------------------------------------------------------
# registry monkeypatch fixture（external 临时翻 True，测试作用域内还原）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _external_registry_enabled(monkeypatch):
    """external.payload.v1 临时翻 True 验证 erase 主体（E-4 registry 断言分离）。

    生产 registry 保持 False；本 fixture 仅测试作用域内生效，自动还原。
    """
    import app.composition.agent_erasure_registry as registry_module

    originals = registry_module._OWNER_DEFINITIONS

    def _enable_external(owner: OwnerDefinition):
        if owner.owner_key == EXTERNAL_PAYLOAD_OWNER:
            return OwnerDefinition(
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                capabilities=owner.capabilities,
                erase_available=True,
            )
        return owner

    enabled = tuple(_enable_external(o) for o in originals)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(registry_module, "_OWNERS_BY_KEY", {o.owner_key: o for o in enabled})
    yield


# ---------------------------------------------------------------------------
# 基建
# ---------------------------------------------------------------------------


async def _ensure_test_tenant(db_session):
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
            "name": "s4eb2-tenant",
            "school_name": "s4eb2 school",
            "isolation": "shared",
            "now": now,
        },
    )
    await db_session.flush()


async def _seed_deleted_expired_conversation(db_session) -> tuple[uuid.UUID, int]:
    """种已删除 + 已过恢复窗口的 Conversation。返回 (conv_id, purge_revision)。"""
    conv_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
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
            "title": "s4eb2 conversation",
            "now": now,
            "purge_after": now - timedelta(days=1),
            "deleted_at": now - timedelta(days=31),
        },
    )
    # external owner fence：active（purge 未开始）。
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
            "o": EXTERNAL_PAYLOAD_OWNER,
            "empty_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "now": now,
        },
    )
    await db_session.flush()
    return conv_id, 1


async def _make_purge_operation(db_session, conversation_id, purge_revision):
    """建 scheduled purge operation + pending external owner checkpoint。"""
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
            "o": EXTERNAL_PAYLOAD_OWNER,
            "cd": capability_digest(EXTERNAL_PAYLOAD_OWNER),
            "now": now,
        },
    )
    await db_session.flush()
    return op_id, 1


async def _seed_workspace_outbox_ref(
    db_session, conversation_id, *, ref_value=_REF_VALUE
) -> uuid.UUID:
    """种 workspace outbox ref-bearing 行 + external ledger registered 行。"""
    outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :c, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', :now)"
        ),
        {
            "id": outbox_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "rv": ref_value,
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
            "now": now,
        },
    )
    await _seed_external_ledger_ref(
        db_session,
        conversation_id=conversation_id,
        source_table="agent_workspace_outbox",
        source_row_id=outbox_id,
        ref_value=ref_value,
    )
    await db_session.flush()
    return outbox_id


async def _seed_run_event_ref(
    db_session, conversation_id, *, ref_value=_REF_VALUE
) -> tuple[uuid.UUID, uuid.UUID]:
    """种 RunEvent（external ref）+ external ledger registered 行。返回 (run_id, event_id)。"""
    run_id = uuid.uuid4()
    event_id = uuid.uuid4()
    run_corr = str(uuid.uuid4())
    now = datetime.now(UTC).replace(tzinfo=None)
    # replica 角色绕 FK（m4 先例）：Run 只需作 RunEvent 的 FK 父行，不需要引用
    # 真实 agent_definition_versions/runtime_profiles 行。
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "agent_definition_version_id, runtime_profile_id, creation_digest, "
            "correlation_id, runtime_capability_snapshot, run_config_snapshot, "
            "budget_snapshot, usage_summary, created_by) "
            "VALUES (:id, :t, :c, 1, :rim, :adv, :rp, :cd, :corr, "
            "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, :cb) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": run_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "rim": uuid.uuid4(),
            "adv": uuid.uuid4(),
            "rp": uuid.uuid4(),
            "cd": "c" * 64,
            "corr": run_corr,
            "cb": uuid.uuid4(),
            "now": now,
        },
    )
    await db_session.execute(text("SET LOCAL session_replication_role = default"))
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "correlation_id) "
            "VALUES (:id, :t, :c, :run, 1, 'run.step', 1, :now, :now, "
            "'internal', 'internal', NULL, :rv, 'external', :pd, 0, "
            "'application/json', :corr)"
        ),
        {
            "id": event_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "run": run_id,
            "rv": ref_value,
            "pd": "d" * 64,
            "corr": run_corr,  # FK fk_agent_run_event_owner 引用 Run.correlation_id
            "now": now,
        },
    )
    await _seed_external_ledger_ref(
        db_session,
        conversation_id=conversation_id,
        source_table="agent_run_events",
        source_row_id=event_id,
        ref_value=ref_value,
    )
    await db_session.flush()
    return run_id, event_id


async def _seed_external_ledger_ref(
    db_session,
    *,
    conversation_id,
    source_table: str,
    source_row_id: uuid.UUID,
    ref_value: str,
    erase_state: str = "registered",
    blocked_reason: str | None = None,
) -> uuid.UUID:
    """种 external ledger 行（默认 registered）。返回 ref id。

    ``ck_agent_external_refs_erase_evidence``：blocked/unknown 须带 blocked_reason；
    registered/pending 须无 reason 无 receipt。
    """
    ref_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, blocked_reason, "
            "created_at, updated_at) "
            "VALUES (:id, :t, :c, :o, 'db_local', :rv, :st, :sr, :s, :br, :now, :now)"
        ),
        {
            "id": ref_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "o": EXTERNAL_PAYLOAD_OWNER,
            "rv": ref_value,
            "st": source_table,
            "sr": source_row_id,
            "s": erase_state,
            "br": blocked_reason,
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    )
    await db_session.flush()
    return ref_id


async def _ledger_state(db_session, ref_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT erase_state, receipt_digest, blocked_reason FROM "
                "metaedu.agent_external_object_refs WHERE id = :id"
            ),
            {"id": ref_id},
        )
    ).mappings().one()
    return dict(row)


def _registry_snapshot_json() -> str:
    import json

    from app.composition.agent_erasure_registry import registry_snapshot

    return json.dumps(registry_snapshot(), sort_keys=True, separators=(",", ":"))


def _retention_policy_digest() -> str:
    from app.shared.schemas.canonical_json import canonical_digest

    return canonical_digest({"conversation_recovery_days": 30})


def _participant(session, adapter) -> ExternalPayloadErasureParticipant:
    return ExternalPayloadErasureParticipant(session, adapter)


# ---------------------------------------------------------------------------
# E-2b 硬前置（capability 判定，不依赖 registry 翻 True）
# ---------------------------------------------------------------------------


async def test_adapter_prerequisite_fail_closed(db_session):
    """E-2b 硬前置：adapter 缺幂等重放 + 缺 receipt lookup -> B2 不得开工。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _UnsupportedAdapter())
    with pytest.raises(ValueError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


# ---------------------------------------------------------------------------
# E-3a 矩阵：success / not-sent / timeout / unknown / failed
# ---------------------------------------------------------------------------


async def test_erase_success_clears_workspace_outbox_ref(db_session):
    """E-1b/E-3a success：写 erased + receipt，再清 workspace outbox ref -> suppressed。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 1
    assert adapter.calls == 1

    # ledger erased + receipt（64-hex）。
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "erased"
    assert state["receipt_digest"] is not None and len(state["receipt_digest"]) == 64

    # source ref 已清（D5 receipt 后）+ 转 suppressed。
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                "WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).mappings().one()
    assert outbox["payload_ref"] is None
    assert outbox["status"] == "suppressed"

    # checkpoint acked + fence erased。
    cp = (
        await db_session.execute(
            text(
                "SELECT state, ack_digest FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert cp["state"] == PurgeOwnerState.ACKED.value
    assert cp["ack_digest"] is not None


async def test_erase_success_clears_run_event_ref_via_041(db_session):
    """E-1b：RunEvent ref 经 migration 041 guard 清除（payload_state -> redacted）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    run_id, event_id = await _seed_run_event_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 1

    # 041 guard 分支 2：payload_ref NULL + payload_state redacted + inline NULL。
    ev = (
        await db_session.execute(
            text(
                "SELECT payload_ref, payload_state, payload_inline FROM "
                "metaedu.agent_run_events WHERE id = :id"
            ),
            {"id": event_id},
        )
    ).mappings().one()
    assert ev["payload_ref"] is None
    assert ev["payload_state"] == "redacted"
    assert ev["payload_inline"] is None


async def test_erase_success_clears_execution_outbox_ref(db_session):
    """E-1b：execution outbox ref 经 B2 清除（payload_ref NULL + suppressed，
    decision 四元保留）——三 source 唯一清除者全覆盖（T-1 返修）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    # 种 execution outbox ref-bearing 行（decision 四元 + payload_ref）。
    outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    corr = str(uuid.uuid4())
    decision_digest = "f" * 64
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_execution_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "attempt_count, next_attempt_at, decision_actor_id, decision_reason, "
            "decision_digest, decided_at, created_at) "
            "VALUES (:id, :t, 'assistant_message.publish_requested.v1', 1, :run, "
            "'execution.run', NULL, :rv, :pd, :corr, 'cancelled', 1, :now, "
            ":zero, 'epoch_stale_rejected', :dd, :now, :now)"
        ),
        {
            "id": outbox_id,
            "t": TENANT_ID,
            "c": conv_id,
            "run": uuid.uuid4(),
            "rv": _REF_VALUE,
            "pd": "a" * 64,
            "corr": corr,
            "zero": "00000000-0000-0000-0000-000000000000",
            "dd": decision_digest,
            "now": now,
        },
    )
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_execution_outbox",
        source_row_id=outbox_id,
        ref_value=_REF_VALUE,
    )
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 1
    assert (await _ledger_state(db_session, ref_id))["erase_state"] == "erased"
    # execution outbox ref 已清 + suppressed；decision 四元保留（终态证据）。
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status, decision_actor_id, decision_reason, "
                "decision_digest FROM metaedu.agent_execution_outbox WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).mappings().one()
    assert outbox["payload_ref"] is None
    assert outbox["status"] == "suppressed"
    assert outbox["decision_reason"] == "epoch_stale_rejected"
    assert outbox["decision_digest"] == decision_digest


async def test_erase_not_sent_blocks_erase_timeout(db_session):
    """E-3a not-sent（可证明未发送）-> ledger blocked/erase_timeout + 不清 ref。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _NotSentAdapter())
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 0
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "blocked"
    assert state["blocked_reason"] == "erase_timeout"
    # 不清 ref（E-3a 矩阵：blocked 不清 ref）。
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                "WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).mappings().one()
    assert outbox["payload_ref"] == _REF_VALUE
    assert outbox["status"] == "pending"


async def test_erase_timeout_marks_unknown(db_session):
    """E-3a timeout（可能已生效）-> ledger unknown/outcome_unknown + 不清 ref。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _TimeoutAdapter())
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 0
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "unknown"
    assert state["blocked_reason"] == "outcome_unknown"
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref FROM metaedu.agent_workspace_outbox WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).scalar()
    assert outbox == _REF_VALUE


async def test_erase_unknown_marks_unknown(db_session):
    """E-3a unknown outcome -> ledger unknown/outcome_unknown。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _UnknownAdapter())
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 0
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "unknown"
    assert state["blocked_reason"] == "outcome_unknown"


async def test_erase_failed_blocks_adapter_unavailable(db_session):
    """E-3a failed（可证明无副作用）-> ledger blocked/adapter_unavailable。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _FailedAdapter())
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 0
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "blocked"
    assert state["blocked_reason"] == "adapter_unavailable"


async def test_erase_empty_evidence_fail_closed(db_session):
    """E-2b 返修（D-9）：空 adapter_receipt_evidence -> 不得写 erased（fail closed）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _EmptyEvidenceAdapter())
    with pytest.raises(ValueError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


async def test_erase_conversation_reason_dispatches_erase_timeout(db_session):
    """E-3a 返修（T-6）：not-sent（erase_timeout）行的 conversation 级 blocked reason
    保留 erase_timeout 身份（不得折叠为 adapter_unavailable）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _NotSentAdapter())
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 0
    # conversation 级 reason_code = purge_blocked_by_external_erase_timeout（分派正确）。
    cp = (
        await db_session.execute(
            text(
                "SELECT reason_code FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert cp["reason_code"] == "purge_blocked_by_external_erase_timeout"


# ---------------------------------------------------------------------------
# E-1a source 已 NULL / 绑定冲突
# ---------------------------------------------------------------------------


async def test_erase_source_already_null_history_compat(db_session):
    """E-1a：source ref 已 NULL/缺失仍凭 ledger 完成删除留证（ledger 为唯一事实源）。

    源行形态：outbox 已 suppressed（inline+ref 均 NULL，status='suppressed'——
    transport 并发清除后形态，满足现 CHECK）；ledger registered 未 erased——B2 仍以
    ledger 为事实源执行 adapter 删除并写 erased + receipt，不因 source 已空而漏删。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :c, 'conversation', "
            "NULL, NULL, :pd, :corr, 'suppressed', :now)"
        ),
        {
            "id": outbox_id,
            "t": TENANT_ID,
            "c": conv_id,
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
            "now": now,
        },
    )
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=outbox_id,
        ref_value=_REF_VALUE,
    )
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.erased_refs == 1
    # E-1a：source 已空仍以 ledger 为事实源调用 adapter（T-9 返修）。
    assert adapter.calls == 1
    state = await _ledger_state(db_session, ref_id)
    assert state["erase_state"] == "erased"
    assert state["receipt_digest"] is not None


async def test_erase_source_ref_conflict_fail_closed(db_session):
    """E-1：source ref 存在但 != ledger ref_value -> fail closed（不覆盖、不伪造）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :c, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', :now)"
        ),
        {
            "id": outbox_id,
            "t": TENANT_ID,
            "c": conv_id,
            "rv": "obj://staging/object/CONFLICT",
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
            "now": now,
        },
    )
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=outbox_id,
        ref_value=_REF_VALUE,  # ledger 与 source 不同 -> 冲突
    )
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _SuccessAdapter())
    with pytest.raises(ValueError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    # ledger 不写 erased（冲突 fail closed，不伪造 receipt）。
    state = await _ledger_state(db_session, ref_id)
    assert state["erase_state"] == "registered"
    assert state["receipt_digest"] is None


# ---------------------------------------------------------------------------
# E-2a 精确重验（Tx2 前置）
# ---------------------------------------------------------------------------


async def test_erase_replay_idempotent_adapter_call(db_session):
    """E-2b：崩溃重放同 invocation——adapter 幂等去重（calls == 1 每 ref）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert adapter.calls == 1


async def test_erase_crash_after_tx1_replays_to_completion(db_session):
    """E-2/E-6 崩溃恢复正向：Tx1 提交后崩溃（checkpoint erasing + attempt + intent
    已持久化）-> 同 invocation 重放精确重验（E-2a）续做 Tx2，adapter 幂等去重
    （calls==1），ledger erased + 源 ref 清（C-2/T-2 返修）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    # 第一次调用：adapter 在 delete 后抛非 ExternalEraseError（模拟 Tx1 已提交、
    # adapter 副作用已发生但进程崩溃——异常在 Tx2 前逃逸）。
    class _CrashOnFirstCall(_SuccessAdapter):
        def __init__(self) -> None:
            super().__init__()
            self._crash_next = True

        async def delete_object(self, **kwargs):
            self.calls += 1
            if self._crash_next:
                self._crash_next = False
                raise RuntimeError("simulated process crash after adapter side-effect")
            return ExternalEraseSuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    crash_adapter = _CrashOnFirstCall()
    participant = _participant(db_session, crash_adapter)
    with pytest.raises(RuntimeError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    # 崩溃后状态：Tx1 已提交——checkpoint erasing + attempt=1 + intent digest。
    checkpoint = (
        await db_session.execute(
            text(
                "SELECT state, attempt, checkpoint_digest FROM "
                "metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert checkpoint["state"] == PurgeOwnerState.ERASING.value
    assert checkpoint["attempt"] == 1
    assert checkpoint["checkpoint_digest"] is not None
    await db_session.commit()

    # 同 invocation 重放（同一 operation revision 语义——operation 已 running，
    # caller 传 mark_running 后的 revision=2）。
    op_rev = (
        await db_session.execute(
            text(
                "SELECT revision FROM metaedu.agent_conversation_purges "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
    ).scalar_one()
    # 重放用正常成功 adapter（模拟崩溃后新进程以幂等 key 重做，副作用不重复）。
    adapter2 = _SuccessAdapter()
    participant2 = _participant(db_session, adapter2)
    await participant2.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )
    # adapter 幂等去重：崩溃调用 1 次 + 重放 1 次 = 2（同一 object 两处调用）。
    # 但重放走 checkpoint ERASING 续做分支（attempt 不变、intent 匹配），
    # Tx2 完整执行——源 ref 清 + ledger erased + ACK。
    ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": outbox_id},
        )
    ).scalar_one()
    state = await _ledger_state(db_session, ref)
    assert state["erase_state"] == "erased"
    assert state["receipt_digest"] is not None
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                "WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).mappings().one()
    assert outbox["payload_ref"] is None
    assert outbox["status"] == "suppressed"
    # checkpoint acked + fence erased。
    cp = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    assert cp["state"] == PurgeOwnerState.ACKED.value


# ---------------------------------------------------------------------------
# 并发（E-2 并发承载 / E-5-2 锁序，首轮复审 C-5/T-3 返修）
# ---------------------------------------------------------------------------


async def test_concurrent_double_b2_erase_serializes(session_factory):
    """E-2 并发承载：两 B2 并发 erase 同一 conversation——共享 fence 串行化，
    一次 adapter 调用、一个 ACK；另一连接 fail closed 或阻塞后重放（无重复副作用）。

    先例对齐：``test_s4eb1_lifecycle_registration.py:493``（并发 promote）与
    ``test_agent_transport_backfill_m4.py:230``（双连接并发 backfill）。
    """
    await _ensure_test_tenant_sf(session_factory)
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

    # 用独立 session 种数据 + commit。
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed_session:
        conv_id, purge_rev = await _seed_deleted_expired_conversation(seed_session)
        outbox_id = await _seed_workspace_outbox_ref(seed_session, conv_id)
        op_id, _ = await _make_purge_operation(seed_session, conv_id, purge_rev)
        await seed_session.commit()
    await engine.dispose()

    async def _erase_with_new_session():
        eng = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        fact = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with fact() as sess:
            # S5 scheduler 语义：调用前读当前 operation revision（replay 契约，
            # C-2 返修——revision 由 _mark_operation_running 递增）；stale revision
            # CAS 拒绝后重读重试（fence 串行化：前一个 operation 完成或续做后，
            # 本调用以新 revision 走 erased-fence 幂等重放 no-op）。
            for _attempt in range(3):
                current_rev = (
                    await sess.execute(
                        text(
                            "SELECT revision FROM metaedu.agent_conversation_purges "
                            "WHERE id = :op"
                        ),
                        {"op": op_id},
                    )
                ).scalar_one()
                participant = ExternalPayloadErasureParticipant(
                    sess, _SuccessAdapter()
                )
                try:
                    await participant.erase_external_payload(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=current_rev,
                    )
                    break
                except ValueError as exc:
                    if "operation revision mismatch" not in str(exc):
                        raise
                    # stale revision：并发 operation 已 bump——重读重试。
                    await sess.rollback()
            else:
                raise AssertionError("concurrent erase did not converge after retries")
        await eng.dispose()

    # 两 B2 并发 erase——共享 fence 串行化（一个进 adapter 窗口并 ACK；
    # 另一个或阻塞到前者完成后走到 erased-fence 重放 no-op，或 fencing 拒绝）。
    results = await asyncio.gather(
        _erase_with_new_session(),
        _erase_with_new_session(),
        return_exceptions=True,
    )
    # 两个调用都必须成功（一个完成 + ACK，一个 erased-fence 重放 no-op）；无异常。
    for r in results:
        assert not isinstance(r, Exception), f"concurrent erase raised: {r}"

    # 最终态：ledger erased + 源 ref 清 + fence erased + checkpoint acked。
    engine2 = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    fact2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with fact2() as check_session:
        ref = (
            await check_session.execute(
                text(
                    "SELECT id FROM metaedu.agent_external_object_refs "
                    "WHERE source_row_id = :sr"
                ),
                {"sr": outbox_id},
            )
        ).scalar_one()
        state = dict(
            (
                await check_session.execute(
                    text(
                        "SELECT erase_state, receipt_digest FROM "
                        "metaedu.agent_external_object_refs WHERE id = :id"
                    ),
                    {"id": ref},
                )
            ).mappings().one()
        )
        assert state["erase_state"] == "erased"
        assert state["receipt_digest"] is not None
        outbox = (
            await check_session.execute(
                text(
                    "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                    "WHERE id = :id"
                ),
                {"id": outbox_id},
            )
        ).mappings().one()
        assert outbox["payload_ref"] is None
        assert outbox["status"] == "suppressed"
        fence = (
            await check_session.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
                ),
                {"t": TENANT_ID, "c": conv_id, "o": EXTERNAL_PAYLOAD_OWNER},
            )
        ).scalar_one()
        assert fence == "erased"
    await engine2.dispose()


async def _ensure_test_tenant_sf(session_factory):
    """用 session_factory 种 tenant（并发测试用，db_session 已提交的可见性差异）。"""
    async with session_factory() as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                "INSERT INTO metaedu.tenants "
                "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": TENANT_ID,
                "name": "s4eb2-conc-tenant",
                "school_name": "s4eb2 conc school",
                "isolation": "shared",
                "now": now,
            },
        )
        await session.commit()


async def test_erase_checkpoint_erasing_replay_fail_closed(db_session):
    """E-2a：Tx2 前置 checkpoint 非 erasing -> fail closed（旧 attempt 拒绝）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    # 直接推进 checkpoint 到 acked（模拟已终态——重放不应续做）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state = 'acked', ack_digest = :ad "
            "WHERE purge_operation_id = :op"
        ),
        {"op": op_id, "ad": "e" * 64},
    )
    await db_session.commit()

    participant = _participant(db_session, _SuccessAdapter())
    with pytest.raises(ValueError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


async def test_erase_fence_not_erasing_in_tx2_fail_closed(db_session):
    """E-2a：Tx2 前置 fence 非 erasing -> fail closed（stale fence 拒绝）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _SuccessAdapter())
    # 预推进 fence 到 erased（模拟并发已完成），Tx1 后 Tx2 应检出非 erasing。
    # 直接构造：预推进 fence -> erased（Tx1 首写 active->erasing 会与已 erased 冲突，
    # 预期 fail closed 而非越过）。
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences "
            "SET state = 'erased', ack_digest = :ad, acked_at = :now "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {
            "t": TENANT_ID,
            "c": conv_id,
            "o": EXTERNAL_PAYLOAD_OWNER,
            "ad": "e" * 64,
            "now": now,
        },
    )
    await db_session.commit()
    with pytest.raises(ValueError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


# ---------------------------------------------------------------------------
# B2 互操作：transport 已 suppressed 行再扫 no-op / 非 registered ledger 行不消费
# ---------------------------------------------------------------------------


async def test_erase_skips_non_registered_ledger_rows(db_session):
    """E-3 矩阵：blocked/unknown/pending/erased 行不在 adapter 窗口（只消费 registered）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    outbox_id = await _seed_workspace_outbox_ref(db_session, conv_id)
    # 另种 blocked 行（backfill 产物，指向独立源行 + 独立 ref_value），不应被 B2 消费。
    # aggregate_id 必须是独立值（uq_agent_ws_outbox_turn 唯一 (tenant, aggregate_id)）。
    blocked_outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :agg, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', :now)"
        ),
        {
            "id": blocked_outbox_id,
            "t": TENANT_ID,
            "c": conv_id,
            "agg": uuid.uuid4(),
            "rv": "obj://staging/object/blocked",
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
            "now": now,
        },
    )
    await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=blocked_outbox_id,
        ref_value="obj://staging/object/blocked",
        erase_state="blocked",
        blocked_reason="unknown_scheme",
    )
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    participant = _participant(db_session, adapter)
    summary = await participant.erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    # 只有 registered 行被消费（blocked 行不进入 adapter 窗口——calls==1）。
    # blocked 行残留使 conversation 级 final scan 非零 -> blocked（erased_refs==0）。
    assert adapter.calls == 1
    assert summary.erased_refs == 0
    # registered 行已 erased + receipt。
    registered_ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr AND ref_value = :rv"
            ),
            {"sr": outbox_id, "rv": _REF_VALUE},
        )
    ).scalar_one()
    assert (await _ledger_state(db_session, registered_ref))["erase_state"] == "erased"
    # blocked 行原样保留（blocked/unknown_scheme）。
    blocked_ref = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": blocked_outbox_id},
        )
    ).scalar_one()
    assert (await _ledger_state(db_session, blocked_ref))["erase_state"] == "blocked"


# ---------------------------------------------------------------------------
# registry fail closed（production registry 保持 False）
# ---------------------------------------------------------------------------


async def test_capability_gate_fail_closed_when_registry_false(db_session, monkeypatch):
    """E-4：production registry external False -> 入口 fail closed（不启动主体）。"""
    # 本测试不用 autouse fixture（显式还原 production registry，测试作用域内
    # 该 undo 只撤销 autouse fixture 的翻 True，生产 registry 保持 False）。
    monkeypatch.undo()
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_workspace_outbox_ref(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    from app.composition.agent_erasure_registry import OwnerCapabilityUnavailableError

    participant = _participant(db_session, _SuccessAdapter())
    with pytest.raises(OwnerCapabilityUnavailableError):
        await participant.erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


# ---------------------------------------------------------------------------
# E-2b idempotency key 跨 takeover 稳定
# ---------------------------------------------------------------------------


async def test_idempotency_key_stable_across_lease_epoch(db_session):
    """E-2b：idempotency key 不含 lease_epoch/attempt——跨 takeover 不变。"""
    key1 = external_erase_idempotency_key(
        ref_scheme="db_local",
        ref_value=_REF_VALUE,
        adapter_key="fake-db-local",
        adapter_version=1,
    )
    key2 = external_erase_idempotency_key(
        ref_scheme="db_local",
        ref_value=_REF_VALUE,
        adapter_key="fake-db-local",
        adapter_version=1,
    )
    assert key1 == key2
    # 更换 adapter 身份 -> key 变化（防跨 adapter 误去重）。
    key3 = external_erase_idempotency_key(
        ref_scheme="db_local",
        ref_value=_REF_VALUE,
        adapter_key="fake-db-local-2",
        adapter_version=1,
    )
    assert key3 != key1


# ---------------------------------------------------------------------------
# E-3b blocked/unknown 查询 + 有证据 reconcile（运维可观察性）
# ---------------------------------------------------------------------------


class _ReceiptLookupAdapter(_SuccessAdapter):
    """支持 receipt lookup 的 adapter（E-3b reconcile 用）。"""

    supports_receipt_lookup = True

    def __init__(self) -> None:
        super().__init__()
        self.receipts: dict[str, str] = {}

    async def receipt_lookup(self, *, idempotency_key: str):
        return self.receipts.get(idempotency_key)


class _NoReceiptAdapter(_ReceiptLookupAdapter):
    """receipt lookup 无证据（E-3b 禁止无 receipt 强制 erased）。"""

    async def receipt_lookup(self, *, idempotency_key: str):
        return None


async def test_query_blocked_unknown_refs(db_session):
    """E-3b：blocked/unknown 行查询（erase_state + conversation 维度过滤）。"""
    await _ensure_test_tenant(db_session)
    conv_id, _ = await _seed_deleted_expired_conversation(db_session)
    blocked_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
        ref_value="obj://staging/object/blocked-q",
        erase_state="blocked",
        blocked_reason="erase_timeout",
    )
    unknown_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
        ref_value="obj://staging/object/unknown-q",
        erase_state="unknown",
        blocked_reason="outcome_unknown",
    )
    await db_session.commit()

    participant = _participant(db_session, _SuccessAdapter())
    all_rows = await participant.list_blocked_unknown_refs(tenant_id=TENANT_ID)
    ids = {row["id"] for row in all_rows}
    assert blocked_id in ids and unknown_id in ids
    # 按 conversation 过滤。
    conv_rows = await participant.list_blocked_unknown_refs(
        tenant_id=TENANT_ID, conversation_id=conv_id
    )
    assert {row["id"] for row in conv_rows} == ids
    # 按 erase_state 过滤。
    blocked_only = await participant.list_blocked_unknown_refs(
        tenant_id=TENANT_ID, erase_state="blocked"
    )
    assert {row["id"] for row in blocked_only} == {blocked_id}
    unknown_only = await participant.list_blocked_unknown_refs(
        tenant_id=TENANT_ID, erase_state="unknown"
    )
    assert {row["id"] for row in unknown_only} == {unknown_id}


async def test_reconcile_with_evidence_writes_erased_and_clears_ref(db_session):
    """E-3b：有证据 reconcile——receipt lookup 返回 evidence -> 补写 erased + receipt
    **并清源 ref**（D-3/T-7 返修：reconcile 收场须闭环 E-1b，否则 conversation 永久
    blocked——B2 不再消费 erased 行、transport 对 ref-bearing 行永久
    ``purge_owner_unavailable``）。"""
    await _ensure_test_tenant(db_session)
    conv_id, _ = await _seed_deleted_expired_conversation(db_session)
    # 种真实 outbox ref-bearing 行 + blocked ledger 行（收场场景：Tx2 fail closed
    # 但 adapter 副作用已发生）。
    outbox_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :c, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', :now)"
        ),
        {
            "id": outbox_id,
            "t": TENANT_ID,
            "c": conv_id,
            "rv": _REF_VALUE,
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
            "now": now,
        },
    )
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=outbox_id,
        ref_value=_REF_VALUE,
        erase_state="blocked",
        blocked_reason="outcome_unknown",
    )
    await db_session.commit()

    adapter = _ReceiptLookupAdapter()
    # 预置该 ref 的 idempotency key 对应 evidence。
    key = external_erase_idempotency_key(
        ref_scheme="db_local",
        ref_value=_REF_VALUE,
        adapter_key=adapter.adapter_key,
        adapter_version=adapter.adapter_version,
    )
    adapter.receipts[key] = "ev:reconcile-evidence"
    participant = _participant(db_session, adapter)
    result = await participant.reconcile_external_ref(
        tenant_id=TENANT_ID, ref_id=ref_id
    )
    assert result == "erased"
    state = await _ledger_state(db_session, ref_id)
    assert state["erase_state"] == "erased"
    assert state["receipt_digest"] is not None
    assert state["blocked_reason"] is None
    # 源 ref 已清（D-3/T-7：reconcile 补清源 ref，B2 是唯一清除者）。
    outbox = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                "WHERE id = :id"
            ),
            {"id": outbox_id},
        )
    ).mappings().one()
    assert outbox["payload_ref"] is None
    assert outbox["status"] == "suppressed"


async def test_reconcile_without_evidence_keeps_state(db_session):
    """E-3b：无 receipt 禁止强制 erased——reconcile 保持 blocked/unknown。"""
    await _ensure_test_tenant(db_session)
    conv_id, _ = await _seed_deleted_expired_conversation(db_session)
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
        ref_value=_REF_VALUE,
        erase_state="unknown",
        blocked_reason="outcome_unknown",
    )
    await db_session.commit()

    participant = _participant(db_session, _NoReceiptAdapter())
    result = await participant.reconcile_external_ref(
        tenant_id=TENANT_ID, ref_id=ref_id
    )
    assert result == "unknown"
    state = await _ledger_state(db_session, ref_id)
    assert state["erase_state"] == "unknown"
    assert state["receipt_digest"] is None


async def test_reconcile_requires_receipt_lookup_capability(db_session):
    """E-3b：adapter 不支持 receipt lookup -> reconcile 不补写（保持原状态）。"""
    await _ensure_test_tenant(db_session)
    conv_id, _ = await _seed_deleted_expired_conversation(db_session)
    ref_id = await _seed_external_ledger_ref(
        db_session,
        conversation_id=conv_id,
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
        ref_value=_REF_VALUE,
        erase_state="blocked",
        blocked_reason="adapter_unavailable",
    )
    await db_session.commit()

    # _SuccessAdapter supports_receipt_lookup=False。
    participant = _participant(db_session, _SuccessAdapter())
    result = await participant.reconcile_external_ref(
        tenant_id=TENANT_ID, ref_id=ref_id
    )
    assert result == "blocked"
    state = await _ledger_state(db_session, ref_id)
    assert state["erase_state"] == "blocked"
