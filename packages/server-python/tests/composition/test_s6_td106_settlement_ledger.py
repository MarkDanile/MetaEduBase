"""R1-S6 TD-106 方案 A：settlement SUCCESS ledger/binding 收口真实 PG 验收。

契约：plan §S6-15.5（TD-106 方案 A 裁决，2026-08-25）——settlement 态 1 SUCCESS
同事务逐 ref/binding 落 ledger/binding receipt + 清源 ref（闭合 S5-C-1 态 1 落账列
「ledger/binding erased + receipt」），禁止「checkpoint acked + registered ledger」
假终态。复用唯一清除路径（B2，E-5-2）：external ``write_erased_and_clear_ref`` /
runtime ``write_erased_and_close_binding``——不复制第二清除者。

反例映射：§S6-15.5 方案 A 测试+mutation 证明矩阵（单 ref / 单 binding / 多 ref /
多 binding / 缺 receipt 零假成功 / source 清除原子性 / 双连接单写者 / ACK-lost 回归 /
retry 不重复 / completed 前置完整性 / F10 hold-drift 四环保持）。

边界：真实 PG（fresh head=043）；不新增 schema/migration/enum/CHECK/reason code；
不启用生产 wiring；registry external/runtime 保持 erase_available=False。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.composition.external_object_adapter import (
    external_erase_idempotency_key,
    external_erase_receipt_digest,
    external_ref_identity_digest,
)
from app.composition.external_ref_erasure_participant import (
    ExternalRefRow,
    external_delete_intent_digest,
    write_erased_and_clear_ref,
)
from app.composition.runtime_erasure_participant import (
    runtime_destroy_intent_digest,
)
from app.composition.settlement import SettlementService
from app.composition.transactional_projection_coordinator import (
    build_scan_providers,
)
from tests.composition.test_s5_sch_d_settlement import (
    _EXTERNAL,
    _OWNER_KEYS,
    _RUNTIME,
    _claim,
    _cp,
    _ensure_tenant,
    _fence_state,
    _LookupEvidenceAdapter,
    _noop_adapter_resolver,
    _pad64,
    _seed_conversation,
    _seed_fence,
    _seed_runtime_binding,
    _set_cp,
)

_EXTERNAL_ADAPTER_KEY = "external.object.v1"
_RUNTIME_ADAPTER_KEY = "runtime.session.v1"
_ADAPTER_VERSION = 1


# ---------------------------------------------------------------------------
# 种子 helpers（真实 source 行——source ref 清除须命中真实行）
# ---------------------------------------------------------------------------


async def _seed_external_ref_with_outbox_source(session, tid, cid, *, ref_value):
    """种 agent_workspace_outbox ref-bearing 行 + external ledger registered 行（指向它）。

    返回 (ExternalRefRow, outbox_id)——source 行真实存在，``_clear_source_ref``
    （B2 唯一清除者）须命中并转 suppressed。
    """
    outbox_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) VALUES (:id, :t, 'turn.requested.v1', 1, :c, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', now())"
        ),
        {
            "id": outbox_id,
            "t": tid,
            "c": cid,
            "rv": ref_value,
            "pd": "c" * 64,
            "corr": str(uuid.uuid4()),
        },
    )
    ref = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme="db_local",
        ref_value=ref_value,
        source_table="agent_workspace_outbox",
        source_row_id=outbox_id,
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, created_at, updated_at) "
            "VALUES (:id, :t, :c, 'external.payload.v1', 'db_local', :rv, "
            "'agent_workspace_outbox', :sr, 'registered', now(), now())"
        ),
        {"id": ref.id, "t": tid, "c": cid, "rv": ref_value, "sr": outbox_id},
    )
    await session.flush()
    return ref, outbox_id


async def _seed_external_ref_with_run_event_source(
    session, tid, cid, run_id, run_corr, *, seq, ref_value
):
    """种 agent_run_events ref-bearing 行（共享 Run 父行）+ external ledger registered 行。

    ``_collection_owner('agent_run_events') = 'external.payload.v1'``——与 outbox
    source（transport owner）不同的集合锁 owner，覆盖多态 source 路径。
    返回 (ExternalRefRow, event_id)。
    """
    event_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "correlation_id) VALUES (:id, :t, :c, :run, :seq, 'run.step', 1, now(), "
            "now(), 'internal', 'internal', NULL, :rv, 'external', :pd, 0, "
            "'application/json', :corr)"
        ),
        {
            "id": event_id,
            "t": tid,
            "c": cid,
            "run": run_id,
            "seq": seq,
            "rv": ref_value,
            "pd": "d" * 64,
            "corr": run_corr,
        },
    )
    ref = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme="db_local",
        ref_value=ref_value,
        source_table="agent_run_events",
        source_row_id=event_id,
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, created_at, updated_at) "
            "VALUES (:id, :t, :c, 'external.payload.v1', 'db_local', :rv, "
            "'agent_run_events', :sr, 'registered', now(), now())"
        ),
        {"id": ref.id, "t": tid, "c": cid, "rv": ref_value, "sr": event_id},
    )
    await session.flush()
    return ref, event_id


async def _seed_run(session, tid, cid):
    """种 Run 父行（replica 绕 FK，仅作 RunEvent 的 FK 宿主）。返回 (run_id, run_corr)。"""
    run_id = uuid.uuid4()
    run_corr = str(uuid.uuid4())
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
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
            "t": tid,
            "c": cid,
            "rim": uuid.uuid4(),
            "adv": uuid.uuid4(),
            "rp": uuid.uuid4(),
            "cd": "c" * 64,
            "corr": run_corr,
            "cb": uuid.uuid4(),
        },
    )
    await session.execute(text("SET LOCAL session_replication_role = default"))
    await session.flush()
    return run_id, run_corr


async def _settle_window_external(session, *, ref_values):
    """种子 settlement 窗口（external，真实 source 行）+ erasing checkpoint/fence。

    checkpoint_digest = 冻结窗口 intent digest（Tx1 同源派生）。返回 (tid, cid, op1,
    refs, outbox_ids)。
    """
    tid, cid = await _seed_conversation(session)
    await _ensure_tenant(session, tid)
    out = await _claim(session, tid, cid)
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(session, op1, k, state="pending")
    await _seed_fence(session, tid, cid, _EXTERNAL, state="erasing")
    refs, outbox_ids = [], []
    for rv in ref_values:
        ref, ob = await _seed_external_ref_with_outbox_source(session, tid, cid, ref_value=rv)
        refs.append(ref)
        outbox_ids.append(ob)
    digest = external_delete_intent_digest(refs)
    await _set_cp(session, op1, _EXTERNAL, state="erasing", attempt=1, digest=digest)
    await session.commit()
    return tid, cid, op1, refs, outbox_ids


async def _settle_window_runtime(session, *, binding_refs):
    """种子 settlement 窗口（runtime binding）+ erasing checkpoint/fence。

    返回 (tid, cid, op1, bindings)。"""
    tid, cid = await _seed_conversation(session)
    await _ensure_tenant(session, tid)
    out = await _claim(session, tid, cid)
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(session, op1, k, state="pending")
    await _seed_fence(session, tid, cid, _RUNTIME, state="erasing")
    bindings = [await _seed_runtime_binding(session, tid, cid, ref_value=rv) for rv in binding_refs]
    digest = runtime_destroy_intent_digest(bindings)
    await _set_cp(session, op1, _RUNTIME, state="erasing", attempt=1, digest=digest)
    await session.commit()
    return tid, cid, op1, bindings


async def _ref_row(session, ref_id):
    row = await session.execute(
        text(
            "SELECT erase_state, receipt_digest FROM metaedu.agent_external_object_refs "
            "WHERE id = :id"
        ),
        {"id": ref_id},
    )
    return row.mappings().one()


async def _outbox_row(session, outbox_id):
    row = await session.execute(
        text("SELECT payload_ref, status FROM metaedu.agent_workspace_outbox WHERE id = :id"),
        {"id": outbox_id},
    )
    return row.mappings().one()


async def _run_event_row(session, event_id):
    row = await session.execute(
        text("SELECT payload_ref, payload_state FROM metaedu.agent_run_events WHERE id = :id"),
        {"id": event_id},
    )
    return row.mappings().one()


async def _binding_row(session, binding_id):
    row = await session.execute(
        text(
            "SELECT runtime_session_ref, status, active_stream_id, "
            "stream_lease_expires_at FROM metaedu.agent_runtime_session_bindings "
            "WHERE id = :id"
        ),
        {"id": binding_id},
    )
    return row.mappings().one()


def _expected_external_receipt(ref, evidence):
    return external_erase_receipt_digest(
        adapter_key=_EXTERNAL_ADAPTER_KEY,
        adapter_version=_ADAPTER_VERSION,
        idempotency_key=external_erase_idempotency_key(
            ref_scheme=ref.ref_scheme,
            ref_value=ref.ref_value,
            adapter_key=_EXTERNAL_ADAPTER_KEY,
            adapter_version=_ADAPTER_VERSION,
        ),
        adapter_receipt_evidence=evidence,
        ref_digest=external_ref_identity_digest(
            ref_scheme=ref.ref_scheme,
            ref_value=ref.ref_value,
            source_table=ref.source_table,
            source_row_id=ref.source_row_id,
            conversation_id=ref.conversation_id,
        ),
        erase_outcome="erased",
    )


def _evidence_for_external(ref):
    """``_LookupEvidenceAdapter.receipt_lookup`` 返回的 evidence（同 idempotency key）。"""
    key = external_erase_idempotency_key(
        ref_scheme=ref.ref_scheme,
        ref_value=ref.ref_value,
        adapter_key=_EXTERNAL_ADAPTER_KEY,
        adapter_version=_ADAPTER_VERSION,
    )
    return _pad64(f"ev:{key}")


def _make_service(session_factory, adapter):
    return SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )


# ---------------------------------------------------------------------------
# 核心：单 ref / 单 binding 成功收口
# ---------------------------------------------------------------------------


async def test_external_single_ref_success_closure(db_session, session_factory):
    """方案 A 矩阵行 1：external 单 ref——settlement SUCCESS 同事务落 ledger
    erased + per-ref receipt + 清源 ref + fence erased + checkpoint acked。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        # per-ref receipt 精确落 ledger 行（evidence 重算，非聚合 digest）。
        assert row["receipt_digest"] == _expected_external_receipt(ref, _evidence_for_external(ref))
        # source ref 与 receipt 同一完整性边界（B2 唯一清除者，D5 receipt 后）。
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] is None
        assert ob["status"] == "suppressed"
        assert await _fence_state(v, cid, _EXTERNAL) == "erased"
        assert await _cp(v, op1, _EXTERNAL, "state") == "acked"


async def test_runtime_single_binding_success_closure(db_session, session_factory):
    """方案 A 矩阵行 2：runtime 单 binding——settlement SUCCESS 同事务关 binding
    （ref NULL + status closed + 清流租约）+ fence erased + checkpoint acked。"""
    tid, cid, op1, bindings = await _settle_window_runtime(
        db_session, binding_refs=("pi://session/x",)
    )
    binding = bindings[0]
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_RUNTIME,
    )
    await db_session.commit()

    async with session_factory() as v:
        b = await _binding_row(v, binding.id)
        assert b["runtime_session_ref"] is None
        assert b["status"] == "closed"
        assert b["active_stream_id"] is None
        assert b["stream_lease_expires_at"] is None
        assert await _fence_state(v, cid, _RUNTIME) == "erased"
        assert await _cp(v, op1, _RUNTIME, "state") == "acked"


# ---------------------------------------------------------------------------
# 核心：多 ref / 多 binding 逐项 receipt（禁聚合丢失 per-ref receipt）
# ---------------------------------------------------------------------------


async def test_external_multi_ref_per_ref_receipt(db_session, session_factory):
    """方案 A 矩阵行 3：external 多 ref（混合 source：outbox + run_event，覆盖
    ``_collection_owner`` 多态集合锁）——逐 ref 落独立 receipt_digest（互不相同、
    均非聚合 digest），逐 ref 清源 ref（outbox suppressed / run_event redacted）。"""
    tid, cid = await _seed_conversation(db_session)
    await _ensure_tenant(db_session, tid)
    out = await _claim(db_session, tid, cid)
    op1 = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="pending")
    await _seed_fence(db_session, tid, cid, _EXTERNAL, state="erasing")
    ref1, outbox_id = await _seed_external_ref_with_outbox_source(
        db_session, tid, cid, ref_value="obj://staging/object/a"
    )
    run_id, run_corr = await _seed_run(db_session, tid, cid)
    ref2, event_id = await _seed_external_ref_with_run_event_source(
        db_session,
        tid,
        cid,
        run_id,
        run_corr,
        seq=1,
        ref_value="obj://staging/object/b",
    )
    refs = [ref1, ref2]
    digest = external_delete_intent_digest(refs)
    await _set_cp(db_session, op1, _EXTERNAL, state="erasing", attempt=1, digest=digest)
    await db_session.commit()

    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        digests = []
        for ref in refs:
            row = await _ref_row(v, ref.id)
            assert row["erase_state"] == "erased"
            expected = _expected_external_receipt(ref, _evidence_for_external(ref))
            assert row["receipt_digest"] == expected
            digests.append(row["receipt_digest"])
        # per-ref receipt 粒度：两 ref 的 receipt_digest 互不相同（非同一聚合值）。
        assert len(set(digests)) == 2
        # 逐 ref 清源 ref（B2 唯一清除者）：outbox suppressed / run_event redacted。
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] is None
        assert ob["status"] == "suppressed"
        ev = await _run_event_row(v, event_id)
        assert ev["payload_ref"] is None
        assert ev["payload_state"] == "redacted"
        assert await _fence_state(v, cid, _EXTERNAL) == "erased"
        assert await _cp(v, op1, _EXTERNAL, "state") == "acked"


async def test_runtime_multi_binding_per_ref_close(db_session, session_factory):
    """方案 A 矩阵行 3 镜像：runtime 多 binding——逐 binding 关（ref NULL + closed）。"""
    tid, cid, op1, bindings = await _settle_window_runtime(
        db_session, binding_refs=("pi://session/a", "pi://session/b")
    )
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_RUNTIME,
    )
    await db_session.commit()

    async with session_factory() as v:
        for binding in bindings:
            b = await _binding_row(v, binding.id)
            assert b["runtime_session_ref"] is None
            assert b["status"] == "closed"
        assert await _fence_state(v, cid, _RUNTIME) == "erased"
        assert await _cp(v, op1, _RUNTIME, "state") == "acked"


# ---------------------------------------------------------------------------
# 缺 receipt / 部分落账 → 零假成功（fail closed，禁假终态）
# ---------------------------------------------------------------------------


class _EmptyEvidenceAdapter:
    """lookup 返回空 evidence（E-2b 不可验证）→ 不得写 erased/receipt，态 3 fail closed。"""

    supports_idempotent_replay = False
    supports_receipt_lookup = True
    lookup_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_calls += 1
        return ""  # 空 evidence

    async def delete_object(self, **kwargs):
        raise AssertionError("空 evidence 禁 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("空 evidence 禁 replay")


async def test_missing_evidence_no_false_success_external(db_session, session_factory):
    """方案 A 矩阵行 4：receipt 缺失（空 evidence）→ 零假成功——ledger 仍
    registered、source 未清、fence 非 erased、checkpoint 非 acked。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    await _make_service(session_factory, _EmptyEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "registered", "缺 receipt 不得写 erased"
        assert row["receipt_digest"] is None
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] == ref.ref_value, "缺 receipt 不得清源 ref"
        assert ob["status"] == "pending"
        # 假终态禁令：fence/checkpoint 不得 acked/erased（态 3 blocked）。
        assert await _fence_state(v, cid, _EXTERNAL) == "blocked"
        assert await _cp(v, op1, _EXTERNAL, "state") == "blocked"


async def test_source_mismatch_atomic_rollback_external(db_session, session_factory):
    """方案 A 矩阵行 5：source ref 与 ledger ref_value 不匹配（E-1 绑定冲突）→
    整事务回滚零写——ledger 仍 registered、fence 非 erased、checkpoint 非 acked。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    # DB 篡改：source payload_ref 改为与 ledger ref_value 不同 → E-1 绑定冲突。
    async with session_factory() as s:
        await s.execute(
            text("UPDATE metaedu.agent_workspace_outbox SET payload_ref = :other WHERE id = :id"),
            {"other": "obj://staging/object/TAMPERED", "id": outbox_id},
        )
        await s.commit()

    with pytest.raises(ValueError, match="binding conflict"):
        await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    await db_session.rollback()

    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "registered", "冲突须整体回滚，不得写 erased"
        assert row["receipt_digest"] is None
        assert await _fence_state(v, cid, _EXTERNAL) == "erasing", (
            "回滚后 fence 保持 erasing（未落 erased）"
        )
        assert await _cp(v, op1, _EXTERNAL, "state") == "erasing"


# ---------------------------------------------------------------------------
# 双连接并发单写者 + 幂等败者
# ---------------------------------------------------------------------------


async def test_concurrent_settlement_single_writer_external(db_session, session_factory):
    """方案 A 矩阵行 6：双连接并发 closeout——单一完整写者落 ledger，败者幂等零写
    （fence 已非 erasing 幂等返回），无部分写、无重复 source 清除。"""
    import asyncio

    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]

    async def run():
        await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )

    # 双连接并发（NullPool session_factory 各自独立连接）。
    await asyncio.gather(run(), run())
    await db_session.commit()

    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert row["receipt_digest"] == _expected_external_receipt(ref, _evidence_for_external(ref))
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] is None
        assert ob["status"] == "suppressed"
        assert await _fence_state(v, cid, _EXTERNAL) == "erased"
        assert await _cp(v, op1, _EXTERNAL, "state") == "acked"


async def test_ledger_write_cas_idempotent_guard_external(db_session, session_factory):
    """方案 A 矩阵行 6 补（unit 级）：单写 CAS（``erase_state='registered' AND
    receipt_digest IS NULL``）是 ledger 写的幂等护栏——直接对唯一清除路径
    ``write_erased_and_clear_ref`` 二次调用须 fail closed（rowcount 0 → raise），
    不得重复写 erased/receipt。

    具名 mutation「移除单写 CAS」的判别载体。settlement 并发路径的单写主保证是
    Conversation FOR UPDATE 行锁 + fence-not-erasing 幂等早退（两者先收敛，见
    ``test_concurrent_settlement_single_writer_external``）；本用例在 unit 级直接
    验证 CAS 本身的护栏作用（ref 已 erased 后重复写被拒绝）。
    """
    tid, cid = await _seed_conversation(db_session)
    await _ensure_tenant(db_session, tid)
    ref, _outbox_id = await _seed_external_ref_with_outbox_source(
        db_session, tid, cid, ref_value="obj://staging/object/cas"
    )
    await db_session.commit()
    receipt = _expected_external_receipt(ref, _evidence_for_external(ref))

    # 首次：registered + receipt NULL → 写 erased + receipt + 清源 ref（CAS rowcount 1）。
    async with session_factory() as s:
        await write_erased_and_clear_ref(s, ref=ref, receipt_digest=receipt, tenant_id=tid)
        await s.commit()

    # 二次：ref 已 erased + receipt 已写 → CAS 不命中（rowcount 0）→ fail closed raise。
    async with session_factory() as s:
        with pytest.raises(ValueError, match="not registered with NULL receipt"):
            await write_erased_and_clear_ref(s, ref=ref, receipt_digest=receipt, tenant_id=tid)
        await s.rollback()


# ---------------------------------------------------------------------------
# retry / 二次 closeout 幂等（不重复副作用）
# ---------------------------------------------------------------------------


async def test_second_closeout_idempotent_no_repeat_external(db_session, session_factory):
    """方案 A 矩阵行 7：首次收口后二次 closeout 幂等零写——fence 已 erased →
    幂等返回，不重复 adapter 调用、不重复 ledger/source 写。"""
    tid, cid, op1, refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref = refs[0]
    adapter = _LookupEvidenceAdapter()
    service = _make_service(session_factory, adapter)
    await service.closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    assert adapter.lookup_calls == 1

    # 二次 closeout：fence 已 erased + checkpoint acked → _classify_input None →
    # 零写幂等返回，不再 lookup。
    await _make_service(session_factory, adapter).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        assert adapter.lookup_calls == 1, "二次 closeout 不得重复 adapter 调用"
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert row["receipt_digest"] == _expected_external_receipt(ref, _evidence_for_external(ref))


# ---------------------------------------------------------------------------
# ACK-lost 回归：不重复 adapter、不重写 ledger
# ---------------------------------------------------------------------------


async def test_ack_lost_repair_unaffected_external(db_session, session_factory):
    """方案 A 矩阵行 8：ACK-lost（fence 已 erased + ledger 已 erased + checkpoint
    pending）→ 只修 checkpoint acked，零 adapter 调用、ledger 不被重写。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    # 构造 ACK-lost：participant 已收口（ledger erased + source 清 + fence erased）
    # 但 checkpoint 仍 pending（ACK 丢失）。直接 SQL 置终态。
    receipt = _expected_external_receipt(ref, _evidence_for_external(ref))
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs SET erase_state='erased', "
                "receipt_digest=:d, updated_at=clock_timestamp() WHERE id=:id"
            ),
            {"d": receipt, "id": ref.id},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_workspace_outbox SET payload_ref=NULL, "
                "status='suppressed' WHERE id=:id"
            ),
            {"id": outbox_id},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_erasure_fences SET state='erased', "
                "ack_digest=:ack, acked_at=now() WHERE conversation_id=:c "
                "AND owner_key=:k"
            ),
            {"ack": "e" * 64, "c": cid, "k": _EXTERNAL},
        )
        # checkpoint 回 pending（ACK 丢失）。
        await _set_cp(s, op1, _EXTERNAL, state="pending", digest=None)
        await s.commit()

    adapter = _LookupEvidenceAdapter()
    await _make_service(session_factory, adapter).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        assert adapter.lookup_calls == 0, "ACK-lost repair 零 adapter 调用"
        assert await _cp(v, op1, _EXTERNAL, "state") == "acked"
        # ledger 已 erased，不被重写（receipt 保持原值）。
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert row["receipt_digest"] == receipt


# ---------------------------------------------------------------------------
# completed 前置完整性：external 收口后 scan 归零，但不直接宣称 operation completed
# ---------------------------------------------------------------------------


async def test_external_closure_zeroes_scan_not_completed(db_session, session_factory):
    """方案 A 矩阵行 9：external 收口后该 owner final scan（registered 计数）归零——
    消除 TD-106 死锁根因；但 operation completed 仍取决于全部 owner，不由本修复
    直接宣称。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        # external final scan（registered 计数）归零 = TD-106 缺口闭合的直接证据。
        registered = await v.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id=:t AND conversation_id=:c AND erase_state='registered'"
            ),
            {"t": tid, "c": cid},
        )
        assert int(registered or 0) == 0
        # 其余 owner checkpoint 仍 pending（非 acked）→ operation 不得 completed。
        op_state = await v.scalar(
            text("SELECT state FROM metaedu.agent_conversation_purges WHERE id=:op"),
            {"op": op1},
        )
        assert op_state != "completed", "单 owner 收口不得直接宣称 operation completed"


# ---------------------------------------------------------------------------
# F10 hold-drift 四环保持：hold 推进（单向放行）下 ledger 仍收口 + G2 blocked
# ---------------------------------------------------------------------------


async def test_hold_drift_f10_external_closure(db_session, session_factory):
    """方案 A 矩阵行 10（F10 四环保持）：operation hold_revision_snapshot=0、
    conversation.hold_revision=1（hold 推进）→ settlement 单向检查放行，ledger
    仍收口（fence erased + checkpoint acked + ledger erased）。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref = refs[0]
    # 模拟 F10：conversation.hold_revision 0→1（hold 推进），operation snapshot 仍 0。
    async with session_factory() as s:
        await s.execute(
            text("UPDATE metaedu.agent_conversations SET hold_revision=1 WHERE id=:c"),
            {"c": cid},
        )
        await s.commit()

    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    async with session_factory() as v:
        # 单向放行：hold 推进不阻断已 erasing 收口——ledger/fence/checkpoint 全落。
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert row["receipt_digest"] == _expected_external_receipt(ref, _evidence_for_external(ref))
        assert await _fence_state(v, cid, _EXTERNAL) == "erased"
        assert await _cp(v, op1, _EXTERNAL, "state") == "acked"
