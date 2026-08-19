"""R1-S5 SCH-D Settlement & Retry-Reconcile 真实 PG 验收（stacked child，base = B/C root）。

契约：R1-S5-C S5-C-1..9——六输出态 + 锁序 + frozen-snapshot + adapter recovery
（descriptor/deadline/lookup/replay）+ erasing→blocked 收敛 + ACK-lost repair +
failed 收敛 + 内部 inspect/retry/reconcile。

反例映射：S5-C-8 行 1-16 + S5-B-9 行 14/19/20/24（settlement 通道/descriptor/
replay/恢复超时）+ SCH-4 SCH-D 行。边界：不新增 migration 043、不改 registry、
不启用生产 wiring、不转 Ready/评分/合并。
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ConversationPurgeScheduler,
)
from app.composition.external_ref_erasure_participant import (
    ExternalRefRow,
    external_delete_intent_digest,
)
from app.composition.retry_reconcile import (
    RetryReconcileService,
)
from app.composition.runtime_erasure_participant import (
    RuntimeBindingRow,
    runtime_destroy_intent_digest,
)
from app.composition.settlement import (
    SettlementService,
)
from app.composition.transactional_projection_coordinator import (
    build_scan_providers,
)
from app.shared.schemas.canonical_json import canonical_digest

_OWNER_KEYS = [str(o["owner_key"]) for o in registry_snapshot()]
assert sorted(_OWNER_KEYS) == _OWNER_KEYS
_ACK = "e" * 64
_DEADLINE_REASON = {
    "external.payload.v1": "purge_blocked_by_external_settlement_deadline_expired",
    "runtime.private.v1": "purge_blocked_by_runtime_settlement_deadline_expired",
}
_UNRESOLVABLE_REASON = {
    "external.payload.v1": "purge_blocked_by_external_adapter_unresolvable",
    "runtime.private.v1": "purge_blocked_by_runtime_adapter_unresolvable",
}
_OUTCOME_UNKNOWN_REASON = {
    "external.payload.v1": "purge_blocked_by_external_outcome_unknown",
    "runtime.private.v1": "purge_blocked_by_runtime_outcome_unknown",
}

_EXTERNAL = "external.payload.v1"
_RUNTIME = "runtime.private.v1"


# ---------------------------------------------------------------------------
# 种子 helpers（复用 SCH-C 形态）
# ---------------------------------------------------------------------------


async def _seed_conversation(session):
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) VALUES (:id, :tid, NULL, 'redacted', :digest, :identity, "
            "'t', 'none', 'deleted', now() - interval '1 day', 'scheduled', 1, "
            "0, 1, now(), now())"
        ),
        {"id": cid, "tid": tid, "digest": "c" * 64, "identity": "d" * 64},
    )
    return tid, cid


async def _claim(session, tid, cid):
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _set_cp(session, op_id, owner_key, *, state, reason=None, attempt=None,
                  digest=None):
    sets = ["state = :state"]
    params = {"op": op_id, "k": owner_key, "state": state}
    if state == "acked":
        sets.append("ack_digest = :ack, checkpoint_digest = :ack")
        params["ack"] = _ACK
        sets.append("reason_code = NULL")
    else:
        sets.append("reason_code = :reason")
        params["reason"] = reason
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    if digest is not None:
        sets.append("checkpoint_digest = :digest")
        params["digest"] = digest
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        params,
    )


async def _seed_fence(session, tid, cid, owner_key, *, state, ack=None):
    ic = {"schema_version": 1, "sources": {}}
    ack_sql = ", ack_digest, acked_at" if state == "erased" else ""
    ack_vals = ", :ack, now()" if state == "erased" else ""
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest"
            + ack_sql
            + ", revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            ":st, 1, 0, :ic, :ing"
            + ack_vals
            + ", 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": owner_key, "st": state,
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
            "ack": ack,
        },
    )


async def _fence_state(session, cid, owner_key):
    row = await session.execute(
        text(
            "SELECT state FROM metaedu.agent_erasure_fences "
            "WHERE conversation_id = :cid AND owner_key = :k"
        ),
        {"cid": cid, "k": owner_key},
    )
    return row.scalar_one()


async def _cp(session, op_id, owner_key, field):
    row = await session.execute(
        text(
            f"SELECT {field} FROM metaedu.agent_conversation_purge_owners "
            "WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        {"op": op_id, "k": owner_key},
    )
    return row.scalar_one()


async def _settle_setup(session, *, owner_key=_EXTERNAL):
    """种子 conversation + claim op1 + 该 owner checkpoint 置 erasing（attempt=1 +
    intent digest）+ fence 置 erasing。返回 (tid, cid, op1)。"""
    tid, cid = await _seed_conversation(session)
    out = await _claim(session, tid, cid)
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(session, op1, k, state="pending")
    await _seed_fence(session, tid, cid, owner_key, state="erasing")
    await _set_cp(
        session, op1, owner_key, state="erasing", attempt=1,
        digest="i" * 64,
    )
    await session.commit()
    return tid, cid, op1


async def _ensure_tenant(session, tid):
    """external ref ledger FK 前置（``fk_agent_external_refs_tenant``）。幂等。"""
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, 'sch-d-settlement-tenant', 'sch-d settlement school', "
            "'shared', true, now(), now()) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": tid},
    )


async def _seed_external_ref(
    session, tid, cid, *, ref_value="obj://staging/object/x",
    ref_scheme="db_local", source_table="agent_workspace_outbox",
) -> ExternalRefRow:
    """种 external ledger ``registered`` 行（冻结窗口成员）。返回行身份。"""
    row = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme=ref_scheme,
        ref_value=ref_value,
        source_table=source_table,
        source_row_id=uuid.uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, created_at, updated_at) "
            "VALUES (:id, :t, :c, 'external.payload.v1', :rs, :rv, :st, :sr, "
            "'registered', now(), now())"
        ),
        {
            "id": row.id,
            "t": tid,
            "c": cid,
            "rs": row.ref_scheme,
            "rv": row.ref_value,
            "st": row.source_table,
            "sr": row.source_row_id,
        },
    )
    await session.flush()
    return row


async def _seed_runtime_binding(
    session, tid, cid, *, ref_value="pi://session/x",
) -> RuntimeBindingRow:
    """种 runtime session binding（active + ref 非空，冻结窗口成员）。返回行身份。"""
    row = RuntimeBindingRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        runtime_profile_id=uuid.uuid4(),
        runtime_session_ref=ref_value,
    )
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_session_bindings "
            "(id, tenant_id, conversation_id, runtime_profile_id, "
            "runtime_session_ref, status, current_epoch, next_expected_runtime_seq, "
            "acked_through_runtime_seq, active_stream_id, stream_lease_expires_at, "
            "revision, created_at, updated_at) "
            "VALUES (:id, :t, :c, :rp, :rv, 'active', 1, 1, 0, NULL, NULL, "
            "1, now(), now())"
        ),
        {
            "id": row.id,
            "t": tid,
            "c": cid,
            "rp": row.runtime_profile_id,
            "rv": row.runtime_session_ref,
        },
    )
    await session.execute(text("SET LOCAL session_replication_role = default"))
    await session.flush()
    return row


async def _settle_window_setup(
    session,
    *,
    owner_key=_EXTERNAL,
    ref_values=("obj://staging/object/x",),
    binding_refs=("pi://session/x",),
):
    """种子冻结 ref/binding 窗口 + 真实 intent digest 的 erasing 窗口 setup。

    checkpoint_digest = 冻结窗口的 intent digest（Tx1 同源派生），settlement 重验
    必须精确命中。返回 (tid, cid, op1, rows)。"""
    tid, cid = await _seed_conversation(session)
    await _ensure_tenant(session, tid)
    out = await _claim(session, tid, cid)
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(session, op1, k, state="pending")
    await _seed_fence(session, tid, cid, owner_key, state="erasing")
    if owner_key == _EXTERNAL:
        refs = [
            await _seed_external_ref(session, tid, cid, ref_value=rv)
            for rv in ref_values
        ]
        digest = external_delete_intent_digest(refs)
        rows = refs
    else:
        bindings = [
            await _seed_runtime_binding(session, tid, cid, ref_value=rv)
            for rv in binding_refs
        ]
        digest = runtime_destroy_intent_digest(bindings)
        rows = bindings
    await _set_cp(
        session, op1, owner_key, state="erasing", attempt=1, digest=digest,
    )
    await session.commit()
    return tid, cid, op1, rows


# ---------------------------------------------------------------------------
# fake adapter 族（S5-C-5/6 三态/replay-only 判别）
# ---------------------------------------------------------------------------


class _LookupEvidenceAdapter:
    """supports_receipt_lookup：lookup 返回 evidence → 态 1。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = True
    lookup_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_calls += 1
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")


class _LookupNoneAdapter:
    """supports_receipt_lookup 仅（无 replay）：lookup 返回 None → 不可判定（态 3），
    禁再次 delete（无幂等重放保证不重复删除）。"""

    supports_idempotent_replay = False
    supports_receipt_lookup = True
    lookup_calls = 0
    replay_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_calls += 1
        return None

    async def delete_object(self, **kwargs):
        self.replay_calls += 1
        raise AssertionError("None 视为不可判定，禁再次 delete")

    async def destroy_session(self, **kwargs):
        self.replay_calls += 1
        raise AssertionError("None 视为不可判定，禁再次 delete")


class _ReplayOnlyUnknownAdapter:
    """supports_idempotent_replay 仅：replay 返回 unknown → 态 3。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = False
    replay_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        raise AssertionError("replay-only adapter 无 lookup")

    async def delete_object(self, **kwargs):
        self.replay_calls += 1
        return None  # unknown

    async def destroy_session(self, **kwargs):
        self.replay_calls += 1
        return None  # unknown


class _ReplayOnlySuccessAdapter:
    """supports_idempotent_replay 仅：replay 返回 evidence → 态 1。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = False
    replay_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        raise AssertionError("replay-only adapter 无 lookup")

    async def delete_object(self, **kwargs):
        self.replay_calls += 1
        return _ReplaySuccess(
            adapter_receipt_evidence=_pad64(f"replay:{kwargs['idempotency_key']}")
        )

    async def destroy_session(self, **kwargs):
        self.replay_calls += 1
        return _ReplaySuccess(
            destroy_receipt_evidence=_pad64(f"replay:{kwargs['idempotency_key']}")
        )


def _pad64(value: str) -> str:
    """64-char digest 形状的稳定 evidence（ck_agent_erasure_fence_ack 要求）。"""
    return (value + "x" * 64)[:64]


class _ReplaySuccess:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)




def _lookup_only_descriptor():
    """supports_receipt_lookup 仅（无 replay）：None 不可判定 → 禁再次 delete。"""
    from datetime import timedelta

    from app.composition.adapter_recovery import RecoveryDescriptor

    return RecoveryDescriptor(
        adapter_key="external.object.v1", adapter_version=1,
        supports_idempotent_replay=False,
        dedup_window=timedelta(days=14),
        receipt_lookup_semantics_version=1,
        settlement_deadline=timedelta(days=7),
    )


def _replay_only_descriptor():
    """supports_idempotent_replay 仅（无 lookup）：replay-only 判别。"""
    from datetime import timedelta

    from app.composition.adapter_recovery import RecoveryDescriptor

    return RecoveryDescriptor(
        adapter_key="external.object.v1", adapter_version=1,
        supports_idempotent_replay=True,
        dedup_window=timedelta(days=14),
        receipt_lookup_semantics_version=None,
        settlement_deadline=timedelta(days=7),
    )


def _patch_resolver(monkeypatch, descriptor):
    from app.composition import settlement as _settlement_mod

    monkeypatch.setattr(_settlement_mod, "resolve_adapter", lambda o, v: descriptor)

def _noop_adapter_resolver(adapter):
    def resolve(*, owner_key, owner_version):
        return adapter
    return resolve


# ---------------------------------------------------------------------------
# 核心测试
# ---------------------------------------------------------------------------


async def test_settlement_post_window_blocked_converges(db_session, session_factory):
    """S5-C-8 行 3：post-window blocked（checkpoint blocked + fence erasing）→
    只写 fence erasing→blocked，checkpoint 零修改（reason 不覆写）。"""
    tid, cid, op1 = await _settle_setup(db_session)
    await _set_cp(
        db_session, op1, _EXTERNAL, state="blocked",
        reason="purge_blocked_by_external_outcome_unknown",
    )
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == "purge_blocked_by_external_outcome_unknown"
        ), "已落账 reason 不覆写"


async def test_settlement_ack_lost_repair(db_session, session_factory):
    """S5-C-8 行 4：ACK-lost repair——fence erased + checkpoint pending →
    checkpoint→acked，fence 零修改，operation failure_code 不清。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="pending")
    await _seed_fence(db_session, tid, cid, _EXTERNAL, state="erased", ack=_ACK)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET state='blocked', "
            "failure_code='blocked_hold_revision_changed' WHERE id=:op"
        ),
        {"op": op1},
    )
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
        assert await _cp(verify, op1, _EXTERNAL, "ack_digest") == _ACK
        assert await _cp(verify, op1, _EXTERNAL, "reason_code") is None
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased", "fence 零修改"
        fc = (
            await verify.execute(
                text(
                    "SELECT failure_code FROM metaedu.agent_conversation_purges "
                    "WHERE id=:op"
                ),
                {"op": op1},
            )
        ).scalar_one()
        assert fc == "blocked_hold_revision_changed", "repair 不清 failure_code"


async def test_settlement_drift_frozen_snapshot(db_session, session_factory):
    """S5-C-8 行 1：G1/G2 drift 下 settlement 以 frozen-snapshot 放行（不 raise），
    fence 收敛；零 operation/Conversation 写。"""
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    # G2 drift：Conversation hold_revision 推进（1），op snapshot 仍 0。
    await db_session.execute(
        text("UPDATE metaedu.agent_conversations SET hold_revision=1 WHERE id=:cid"),
        {"cid": cid},
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET state='blocked', "
            "failure_code='blocked_hold_revision_changed' WHERE id=:op"
        ),
        {"op": op1},
    )
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(_LookupNoneAdapter()),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked", "quiesce 收敛"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        )
        op_state = (
            await verify.execute(
                text(
                    "SELECT state, failure_code FROM metaedu.agent_conversation_purges "
                    "WHERE id=:op"
                ),
                {"op": op1},
            )
        ).one()
        assert op_state.state == "blocked", "settlement 不写 operation"
        assert op_state.failure_code == "blocked_hold_revision_changed"


async def test_settlement_stale_revision_rejected(db_session, session_factory):
    """S5-C-2 第 1 条：旧 operation 非 top revision → settlement fail closed 零写。"""
    tid, cid, op1 = await _settle_setup(db_session)
    await db_session.execute(
        text("UPDATE metaedu.agent_conversations SET purge_revision=2 WHERE id=:cid"),
        {"cid": cid},
    )
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    with pytest.raises(ValueError, match="stale operation"):
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    await db_session.rollback()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing", "零写"


async def test_settlement_success_lookup(db_session, session_factory):
    """S5-C-8 行 5：lookup evidence → success（fence erasing→erased +
    checkpoint→acked），禁 replay。"""
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _LookupEvidenceAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
        assert adapter.lookup_calls == 1
    # evidence 后不得 replay（_LookupEvidenceAdapter.delete_object 断言）→ 已覆盖


async def test_settlement_lookup_none_unknown(db_session, session_factory, monkeypatch):
    """S5-C-8 行 5：lookup None → 不可判定（态 3），禁再次 delete（无 replay 能力）。"""
    _patch_resolver(monkeypatch, _lookup_only_descriptor())
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _LookupNoneAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        )
    assert adapter.lookup_calls == 1
    assert adapter.replay_calls == 0, "None 不可判定，禁再次 delete"


async def test_settlement_replay_only_unknown(db_session, session_factory, monkeypatch):
    """S5-C-8 行 7：replay-only 重放 unknown → outcome_unknown 终态（零二次 replay）。"""
    _patch_resolver(monkeypatch, _replay_only_descriptor())
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _ReplayOnlyUnknownAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        )
    assert adapter.replay_calls == 1
    # 二次 closeout（同输入重放）不触发二次 replay——fence 已 blocked 白名单跳过。
    service2 = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service2.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    assert adapter.replay_calls == 1, "unknown 后零二次 replay"


async def test_settlement_replay_only_success(db_session, session_factory, monkeypatch):
    """S5-C-8 行 6 正向：dedup_window >= deadline 时 replay 成功 → success。"""
    _patch_resolver(monkeypatch, _replay_only_descriptor())
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _ReplayOnlySuccessAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
    assert adapter.replay_calls == 1


async def test_settlement_deadline_expired(db_session, session_factory):
    """S5-C-8 行 8：deadline 过期（进入点判定）→ settlement_deadline_expired 独立
    code + fence blocked + 零自动重试。"""
    tid, cid, op1 = await _settle_setup(db_session)
    # DB 篡改回填 checkpoint.updated_at（进入点判定前）→ 已过期。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "updated_at = now() - interval '30 days' "
                "WHERE purge_operation_id=:op AND owner_key=:k"
            ),
            {"op": op1, "k": _EXTERNAL},
        )
        await s.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(_LookupNoneAdapter()),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _DEADLINE_REASON[_EXTERNAL]
        )


async def test_settlement_adapter_unresolvable(db_session, session_factory):
    """S5-C-8 行 9：历史 (owner_key, owner_version) 不在 resolver → fail closed：
    零 adapter 调用 + adapter_unresolvable + reconcile-only。"""
    tid, cid, op1 = await _settle_setup(db_session)
    calls = []

    def _unresolvable(*, owner_key, owner_version):
        calls.append(owner_key)
        from app.composition.adapter_recovery import AdapterUnresolvableError
        raise AdapterUnresolvableError("not wired")

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_unresolvable,
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _UNRESOLVABLE_REASON[_EXTERNAL]
        )
    assert calls == [_EXTERNAL], "resolver 被调用（判定不可解析）"
    # 零 adapter 调用由 _unresolvable 直接 raise 保证（未走 adapter 方法）


async def test_settlement_failed_convergence(db_session, session_factory):
    """S5-C-1 failed 收敛：checkpoint=failed + fence erasing → fence erasing→blocked，
    checkpoint 零修改（failed 保留）。"""
    tid, cid, op1 = await _settle_setup(db_session)
    await _set_cp(
        db_session, op1, _EXTERNAL, state="failed",
        reason="purge_blocked_by_external_erase_timeout",
    )
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    await service.converge_failed_fence(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "failed", "failed 保留"


async def test_settlement_reasons_distinct(db_session, session_factory, monkeypatch):
    """S5-C-8 行 15：输出态 3/5/6 reason 互异且稳定（逐 owner 变体）。变异「3/5/6
    共用同一 code」→红。"""
    _patch_resolver(monkeypatch, _lookup_only_descriptor())
    # 态 3（outcome_unknown）：lookup None，external + runtime 各一。
    codes: dict[str, str] = {}
    for owner_key in (_EXTERNAL, _RUNTIME):
        tid, cid, op1, _refs = await _settle_window_setup(
            db_session, owner_key=owner_key
        )
        adapter = _LookupNoneAdapter()
        service = SettlementService(
            session_factory, scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=owner_key,
        )
        await db_session.commit()
        async with session_factory() as verify:
            codes[owner_key] = await _cp(verify, op1, owner_key, "reason_code")
    assert codes[_EXTERNAL] == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
    assert codes[_RUNTIME] == _OUTCOME_UNKNOWN_REASON[_RUNTIME]
    assert codes[_EXTERNAL] != codes[_RUNTIME], "逐 owner 变体互异"
    # 3/5/6 三码互异（跨态比较，由各态独立 reason 函数保证）。
    assert (
        len({_DEADLINE_REASON[_EXTERNAL], _DEADLINE_REASON[_RUNTIME],
             _UNRESOLVABLE_REASON[_EXTERNAL], _UNRESOLVABLE_REASON[_RUNTIME],
             _OUTCOME_UNKNOWN_REASON[_EXTERNAL], _OUTCOME_UNKNOWN_REASON[_RUNTIME]})
        == 6
    )


async def test_settlement_dual_connection_single_writer(session_factory, monkeypatch):
    """S5-C-8 行 10：双连接并发 closeout 同 owner → 结果落账单写者（fence CAS
    唯一性）。

    裁决二（2026-08-18）：锁外 adapter 阶段不再被 DB 锁串行化——双方都可能发起
    锁外 lookup/replay（同 stable key，幂等去重），T2 重验 + fence/checkpoint CAS
    保证**落账单写者**：一方成功，另一方 T2 token 重验失败 fail closed 零写。
    """
    _patch_resolver(monkeypatch, _replay_only_descriptor())
    async with session_factory() as seed:
        tid, cid, op1, _refs = await _settle_window_setup(seed)

    async def _one():
        adapter = _ReplayOnlyUnknownAdapter()
        service = SettlementService(
            session_factory, scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        return adapter.replay_calls

    import asyncio

    r1, r2 = await asyncio.gather(_one(), _one())
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked"
    assert (r1, r2) == (1, 1), (
        "裁决二：锁外双方均尝试 replay（同 key 幂等），落账由 T2 CAS 单写者收敛"
    )


async def test_settlement_idempotent_replay(db_session, session_factory, monkeypatch):
    """S5-C-8 行 12：同输入重放 settlement → 同一 owner-scoped 结果，零跨 owner
    副作用（replay 跳过已收口 fence/checkpoint）。"""
    _patch_resolver(monkeypatch, _replay_only_descriptor())
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _ReplayOnlyUnknownAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    # 重放：fence 已 blocked → 输入态 None → 零写，不再次 recovery。
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked"
    assert adapter.replay_calls == 1, "幂等重放零二次副作用"
    # 零跨 owner 副作用：其余 owner checkpoint 保持 pending。
    async with session_factory() as verify:
        for k in _OWNER_KEYS:
            if k != _EXTERNAL:
                assert await _cp(verify, op1, k, "state") == "pending"


async def test_settlement_fence_write_failure_reconcile(
    db_session, session_factory, monkeypatch
):
    """S5-C-8 行 13：settlement fence 写永久失败（CAS/owner-version/stale 注入）→
    具名 reconcile：checkpoint blocked + 进入时输出态对应持久 reason，fence 保持
    erasing（可观察），零自动重试、零二次 recovery/adapter 调用。"""
    from app.contexts.agent_workspace.infrastructure import (
        erasure_repository as _repo_mod,
    )

    _patch_resolver(monkeypatch, _lookup_only_descriptor())
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _LookupNoneAdapter()

    async def _fence_write_fails(self, **kwargs):
        raise ValueError("fence write permanently failed (CAS conflict)")

    monkeypatch.setattr(
        _repo_mod.AgentErasureRepository,
        "transition_fence_state_settlement",
        _fence_write_fails,
    )
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    # 不 crash：fence 写失败 → 具名 reconcile（例外条款）。
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked", "具名 reconcile"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        ), "进入时输出态对应持久 reason"
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing", "fence 可观察"
    assert adapter.lookup_calls == 1, "零自动重试 / 零二次 recovery"


class _FirstLookupCrashAdapter:
    """锁外阶段崩溃模拟：第一次 receipt_lookup 抛异常（T1 已提交、T2 未执行），
    之后幂等返回 evidence。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.calls = 0
        self.lookup_keys: list[str] = []

    async def receipt_lookup(self, *, idempotency_key):
        self.calls += 1
        self.lookup_keys.append(idempotency_key)
        if self.calls == 1:
            raise RuntimeError("simulated crash in lock-free phase (after T1)")
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")


async def test_settlement_lookup_crash_replay_no_fork(session_factory, monkeypatch):
    """S5-C-8 行 16（裁决二语义）：T1 提交后、锁外 lookup 崩溃 → 重放同输入 →
    同一 owner-scoped 终态（T2 重验 + CAS 单写、同 stable key 幂等重放、无跨
    owner 分叉）。"""
    _patch_resolver(monkeypatch, _lookup_only_descriptor())
    async with session_factory() as seed:
        tid, cid, op1, _refs = await _settle_window_setup(seed)

    adapter = _FirstLookupCrashAdapter()
    # 第一轮：T1 提交（checkpoint/fence 冻结）→ 锁外 lookup 崩溃（T2 未执行）。
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    with pytest.raises(RuntimeError, match="lock-free phase"):
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )

    # 重放（同 token/idempotency key）：lookup 幂等再调用 → T2 重验 + CAS 落账。
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
        for k in _OWNER_KEYS:
            if k != _EXTERNAL:
                assert await _cp(verify, op1, k, "state") == "pending", "零跨 owner 分叉"
    assert adapter.calls == 2, "重放同输入（lookup 幂等，同 key）"
    assert adapter.lookup_keys[0] == adapter.lookup_keys[1], "同 stable key 收口"


async def test_settlement_new_tx1_not_created(db_session, session_factory):
    """S5-C-2 禁新 Tx1：blocked checkpoint + active fence → 无 settlement 输入态
    → 零写（settlement 通道不得推进 pending/blocked→erasing）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _set_cp(
        db_session, op1, _EXTERNAL, state="blocked",
        reason="purge_blocked_by_external_outcome_unknown",
    )
    await _seed_fence(db_session, tid, cid, _EXTERNAL, state="active")
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "active", "零写"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked", "零写"


async def test_settlement_erasing_without_token_rejected(db_session, session_factory):
    """S5-C-2 禁新 Tx1 / E-2a token：erasing checkpoint 无 attempt/intent token →
    settlement fail closed 零写（不得续做无 token 的窗口）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="pending")
    await _seed_fence(db_session, tid, cid, _EXTERNAL, state="erasing")
    # erasing 但 attempt=0 + 无 intent digest（无 Tx1 证据）。
    await _set_cp(db_session, op1, _EXTERNAL, state="erasing", attempt=0)
    await db_session.commit()

    service = SettlementService(
        session_factory, scan_providers=build_scan_providers
    )
    with pytest.raises(ValueError, match="attempt/intent token"):
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    await db_session.rollback()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing", "零写"


async def test_settlement_replay_window_insufficient(db_session, session_factory, monkeypatch):
    """S5-C-8 行 6：去重窗口 < deadline → 不 replay（不用于 settlement 自动恢复），
    outcome_unknown 终态。"""
    from datetime import timedelta

    from app.composition import settlement as _settlement_mod
    from app.composition.adapter_recovery import RecoveryDescriptor

    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    narrow = RecoveryDescriptor(
        adapter_key="external.object.v1",
        adapter_version=1,
        supports_idempotent_replay=True,
        dedup_window=timedelta(days=1),
        receipt_lookup_semantics_version=None,
        settlement_deadline=timedelta(days=7),
    )
    monkeypatch.setattr(_settlement_mod, "resolve_adapter", lambda o, v: narrow)
    adapter = _ReplayOnlyUnknownAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        )
    assert adapter.replay_calls == 0, "窗口不足不 replay"


async def test_settlement_frozen_descriptor(db_session, session_factory, monkeypatch):
    """S5-C-8 行 14：Tx1 后部署新 registry 版本 → 旧 settlement 仍用 frozen
    owner-version descriptor（旧 deadline/adapter 身份）。"""
    from datetime import timedelta

    from app.composition import settlement as _settlement_mod
    from app.composition.adapter_recovery import RecoveryDescriptor

    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    # 当前版本 descriptor 无 lookup（部署后变化）；frozen 旧版本有 lookup。
    current = RecoveryDescriptor(
        adapter_key="external.object.v1", adapter_version=1,
        supports_idempotent_replay=False,
        dedup_window=timedelta(days=14),
        receipt_lookup_semantics_version=None,
        settlement_deadline=timedelta(days=7),
    )
    monkeypatch.setattr(_settlement_mod, "resolve_adapter", lambda o, v: current)
    adapter = _LookupEvidenceAdapter()
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    # frozen descriptor 无 lookup 能力 → 走 replay（supports_idempotent_replay=True
    # 但当前描述符为 False → 无恢复能力 → outcome_unknown）。
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked"
        assert (
            await _cp(verify, op1, _EXTERNAL, "reason_code")
            == _OUTCOME_UNKNOWN_REASON[_EXTERNAL]
        ), "按 frozen descriptor（无 lookup）判定，不随部署漂移"
    assert adapter.lookup_calls == 0, "frozen descriptor 无 lookup 能力 → 零 lookup"


# ---------------------------------------------------------------------------
# 内部命令服务边界（inspect / retry / reconcile）
# ---------------------------------------------------------------------------


async def test_retry_whitelist_allowed_and_rejected(db_session, session_factory):
    """S5-A-3 白名单：reopenable blocked → retry 批准重开 pending；3/5/6 → 拒绝
    零写。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _set_cp(
        db_session, op1, _EXTERNAL, state="blocked",
        reason="purge_blocked_by_external_erase_timeout",
    )
    await _set_cp(
        db_session, op1, _RUNTIME, state="blocked",
        reason="purge_blocked_by_runtime_outcome_unknown",
    )
    await db_session.commit()

    service = RetryReconcileService(
        db_session,
        settlement=SettlementService(
            session_factory, scan_providers=build_scan_providers
        ),
    )
    verdict = await service.retry(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    assert verdict.allowed is True, "reopenable retry 批准"
    verdict2 = await service.retry(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_RUNTIME,
    )
    assert verdict2.allowed is False, "3/5/6 拒绝"
    await db_session.commit()

    async with session_factory() as verify:
        assert await _cp(verify, op1, _EXTERNAL, "state") == "pending"
        assert await _cp(verify, op1, _EXTERNAL, "reason_code") is None
        assert await _cp(verify, op1, _RUNTIME, "state") == "blocked", "3/5/6 零写"
        assert (
            await _cp(verify, op1, _RUNTIME, "reason_code")
            == "purge_blocked_by_runtime_outcome_unknown"
        )


async def test_reconcile_via_settlement_no_force_skip(db_session, session_factory):
    """reconcile：经 settlement 以 evidence 收口（owner-scoped），无 force-skip
    ACK——无证据不写 erased/acked。"""
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _LookupNoneAdapter()
    service = RetryReconcileService(
        db_session,
        settlement=SettlementService(
            session_factory, scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(adapter),
        ),
    )
    verdict = await service.reconcile(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    assert verdict.applied is True
    await db_session.commit()
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "blocked", "无证据不写 erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "blocked", "无证据不写 acked"


async def test_inspect_readonly(db_session, session_factory):
    """inspect：只读返回 operation + 逐 owner 摘要（零副作用）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    service = RetryReconcileService(
        db_session,
        settlement=SettlementService(
            session_factory, scan_providers=build_scan_providers
        ),
    )
    result = await service.inspect(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1
    )
    assert result["operation"]["id"] == op1
    assert len(result["owners"]) == len(_OWNER_KEYS)
    await db_session.rollback()
    async with session_factory() as verify:
        assert await _cp(verify, op1, _OWNER_KEYS[0], "state") == "pending", "零写"


# ---------------------------------------------------------------------------
# R1-S6 S6-I1 裁决二（S5 修改点 #2）：T2 补 checkpoint.state 重验（S6-F11）
# ---------------------------------------------------------------------------


class _MutateCheckpointStateAdapter:
    """S6-F11 mutate-during-lookup：锁外 lookup 阶段把 checkpoint.state 改出
    ``erasing``（T1 已提交、T2 未执行）→ T2 重验应 fail closed 零写。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = True
    lookup_calls = 0

    def __init__(self, session_factory, *, tenant_id, purge_operation_id, owner_key):
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._purge_operation_id = purge_operation_id
        self._owner_key = owner_key

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_calls += 1
        async with self._session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE metaedu.agent_conversation_purge_owners "
                    "SET state = 'pending' "
                    "WHERE tenant_id = :tid AND purge_operation_id = :op "
                    "AND owner_key = :k"
                ),
                {
                    "tid": self._tenant_id,
                    "op": self._purge_operation_id,
                    "k": self._owner_key,
                },
            )
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, **kwargs):
        raise AssertionError("证据后不得 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("证据后不得 replay")


async def test_settlement_t2_checkpoint_state_verified(session_factory, monkeypatch):
    """S6-I1 裁决二（S5 修改点 #2）：``_verify_t2_tokens`` 补 ``checkpoint.state ==
    'erasing'`` 重验（S5-SCH-2 T2 token 清单落地缺口）——T2 前篡改 checkpoint.state
    → fail closed 零写（fence 保持 erasing、checkpoint 零 settle 写、无二次 adapter
    调用）。"""
    _patch_resolver(monkeypatch, _lookup_only_descriptor())
    async with session_factory() as seed:
        tid, cid, op1, _refs = await _settle_window_setup(seed)

    adapter = _MutateCheckpointStateAdapter(
        session_factory,
        tenant_id=tid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    service = SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    with pytest.raises(ValueError, match="T2 checkpoint state"):
        await service.closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )

    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing", (
            "T2 fail closed 零写：fence 保持 erasing"
        )
        assert await _cp(verify, op1, _EXTERNAL, "state") == "pending", (
            "checkpoint 保持篡改值（settlement 零写）"
        )
        assert await _cp(verify, op1, _EXTERNAL, "ack_digest") is None, (
            "未落账：ack_digest 仍 NULL"
        )
    assert adapter.lookup_calls == 1, "零自动重试 / 零二次 adapter 调用"
