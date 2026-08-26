"""R1-S6 TD-106 方案 A 补：P1 闭合专项——空窗口防混淆守卫 + 集合锁哨兵 + stale-CAS。

契约：plan §S6-15.5（TD-106 方案 A 裁决，2026-08-25）+ 方案 A 测试+mutation 证明
矩阵第 (5) 项具名 mutation「缺集合锁（M8）/ 败者 raise（M9）」。

- **P1-A 防混淆守卫**：非空计划缺 closure / 空计划携带 stray closure → fail
  closed 整体零写（粒度丢失/不变量破坏不得冒充空窗口 no-op）。
- **M8（缺集合锁）**：lock-acquisition sentinel 替换
  ``acquire_transport_aggregate_lock``，断言正常源码在任何 ledger/source/fence/
  checkpoint 写之前调用集合锁（同事务内读校验零写）。证明 D8 锁协议被强制调用；
  **不冒充**「两 settlement 因集合锁串行」的并发结论。
- **M9（败者 raise）**：真实 PG stale-CAS——helper identity read 完成后、实际
  UPDATE 前由第二连接提交同一 ref/binding 的合法收口，第一连接 UPDATE 真实
  rowcount=0 → raise + 整事务回滚（无 partial ledger/fence/checkpoint ACK）。

边界：真实 PG（fresh head=043）；不新增 schema/migration/enum/CHECK/reason code。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.composition import settlement as settlement_mod
from app.composition.external_ref_erasure_participant import (
    ExternalRefRow,
    write_erased_and_clear_ref,
)
from app.composition.external_ref_lifecycle import _collection_owner
from app.composition.runtime_erasure_participant import (
    RUNTIME_PRIVATE_OWNER,
    write_erased_and_close_binding,
)
from app.composition.settlement import (
    OutputState,
    SettlementService,
    _RefClosure,
    _WindowOutcome,
)
from tests.composition.test_s5_sch_d_settlement import (
    _EXTERNAL,
    _RUNTIME,
    _cp,
    _fence_state,
    _LookupEvidenceAdapter,
    _pad64,
)
from tests.composition.test_s6_td106_settlement_ledger import (
    _binding_row,
    _evidence_for_external,
    _expected_external_receipt,
    _make_service,
    _outbox_row,
    _ref_row,
    _settle_empty_window,
    _settle_window_external,
    _settle_window_runtime,
)

# ---------------------------------------------------------------------------
# P1-A 防混淆守卫：粒度丢失 / 不变量破坏 → fail closed 整体零写
# ---------------------------------------------------------------------------


async def test_non_empty_plan_missing_closure_fail_closed(
    db_session, session_factory, monkeypatch
):
    """非空冻结计划但 SUCCESS 缺 per-ref closure（粒度丢失，等价 M3 聚合冒充）→
    `_close_window_ledger` fail closed 抛错 + 整体回滚零写（ledger 仍
    registered、source 未清、fence/checkpoint 仍 erasing）。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    original = SettlementService._aggregate_window

    def _drop_closures(self, ref_outcomes, owner_key, plan):
        out = original(self, ref_outcomes, owner_key, plan)
        if out.state is OutputState.SUCCESS:
            # 丢 per-ref closure 清单（聚合 receipt 冒充 per-ref）。
            return _WindowOutcome(OutputState.SUCCESS, ack_digest=out.ack_digest)
        return out

    monkeypatch.setattr(SettlementService, "_aggregate_window", _drop_closures)
    with pytest.raises(ValueError, match="per-ref"):
        await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_EXTERNAL,
        )
    await db_session.rollback()

    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "registered", "缺 closure 须整体回滚，不写 erased"
        assert row["receipt_digest"] is None
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] == ref.ref_value, "缺 closure 不得清源 ref"
        assert await _fence_state(v, cid, _EXTERNAL) == "erasing"
        assert await _cp(v, op1, _EXTERNAL, "state") == "erasing"


async def test_empty_plan_stray_closure_fail_closed(
    db_session, session_factory, monkeypatch
):
    """空冻结计划但 SUCCESS 携带 stray per-ref closure（不变量破坏）→ fail closed
    抛错 + 整体回滚（fence/checkpoint 仍 erasing，不落假 ACK）。"""
    tid, cid, op1 = await _settle_empty_window(db_session, owner_key=_EXTERNAL)
    stray_ref = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme="db_local",
        ref_value="obj://staging/object/stray",
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
    )
    original = SettlementService._aggregate_window

    def _inject_stray(self, ref_outcomes, owner_key, plan):
        out = original(self, ref_outcomes, owner_key, plan)
        if out.state is OutputState.SUCCESS:
            stray = _RefClosure(ref=stray_ref, idempotency_key="k", ack_evidence="e" * 64)
            return _WindowOutcome(
                OutputState.SUCCESS, ack_digest=out.ack_digest, ref_closures=(stray,)
            )
        return out

    monkeypatch.setattr(SettlementService, "_aggregate_window", _inject_stray)
    with pytest.raises(ValueError, match="per-ref"):
        await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_EXTERNAL,
        )
    await db_session.rollback()

    async with session_factory() as v:
        assert await _fence_state(v, cid, _EXTERNAL) == "erasing"
        assert await _cp(v, op1, _EXTERNAL, "state") == "erasing"


# ---------------------------------------------------------------------------
# M8：缺集合锁——lock-acquisition sentinel（D8 集合锁协议被强制调用）
# ---------------------------------------------------------------------------


async def test_collection_lock_sentinel_external(db_session, session_factory, monkeypatch):
    """M8 载体（external）：settlement closure 须在任何 ledger/source/fence/
    checkpoint 写之前调用 ``acquire_transport_aggregate_lock``（D8 集合锁）。

    sentinel 在调用点（同事务内）断言 ledger/source/fence/checkpoint 均未写，并
    记录锁身份。mutation 删集合锁调用后 sentinel 不再出现 → 转红。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/x",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    calls = []
    real = settlement_mod.acquire_transport_aggregate_lock

    async def sentinel(session, *, tenant_id, owner_key, source_table, source_row_id):
        # 同事务内读：集合锁调用点之前不得有任何 ledger/source/fence/checkpoint 写。
        row = (
            await session.execute(
                text(
                    "SELECT erase_state, receipt_digest FROM "
                    "metaedu.agent_external_object_refs WHERE id = :i"
                ),
                {"i": ref.id},
            )
        ).mappings().one()
        assert row["erase_state"] == "registered" and row["receipt_digest"] is None
        src = (
            await session.execute(
                text(
                    "SELECT payload_ref FROM metaedu.agent_workspace_outbox "
                    "WHERE id = :i"
                ),
                {"i": outbox_id},
            )
        ).scalar_one()
        assert src == ref.ref_value
        assert await _fence_state(session, cid, _EXTERNAL) == "erasing"
        assert await _cp(session, op1, _EXTERNAL, "state") == "erasing"
        calls.append((owner_key, source_table, source_row_id))
        return await real(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            source_table=source_table,
            source_row_id=source_row_id,
        )

    monkeypatch.setattr(settlement_mod, "acquire_transport_aggregate_lock", sentinel)
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_EXTERNAL,
    )
    await db_session.commit()

    assert calls == [
        (_collection_owner(ref.source_table), ref.source_table, ref.source_row_id)
    ], "集合锁必须以正确 owner/source 身份被调用恰好一次"
    # sentinel 透传真实锁，收口仍成功。
    async with session_factory() as v:
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert await _fence_state(v, cid, _EXTERNAL) == "erased"


async def test_collection_lock_sentinel_runtime(db_session, session_factory, monkeypatch):
    """M8 载体（runtime）：settlement closure 须在任何 binding/fence/checkpoint 写
    之前取集合锁（RUNTIME_PRIVATE_OWNER / agent_runtime_session_bindings）。"""
    tid, cid, op1, bindings = await _settle_window_runtime(
        db_session, binding_refs=("pi://session/x",)
    )
    binding = bindings[0]
    calls = []
    real = settlement_mod.acquire_transport_aggregate_lock

    async def sentinel(session, *, tenant_id, owner_key, source_table, source_row_id):
        b = (
            await session.execute(
                text(
                    "SELECT runtime_session_ref, status FROM "
                    "metaedu.agent_runtime_session_bindings WHERE id = :i"
                ),
                {"i": binding.id},
            )
        ).mappings().one()
        assert b["runtime_session_ref"] == binding.runtime_session_ref
        assert b["status"] == "active"
        assert await _fence_state(session, cid, _RUNTIME) == "erasing"
        assert await _cp(session, op1, _RUNTIME, "state") == "erasing"
        calls.append((owner_key, source_table, source_row_id))
        return await real(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            source_table=source_table,
            source_row_id=source_row_id,
        )

    monkeypatch.setattr(settlement_mod, "acquire_transport_aggregate_lock", sentinel)
    await _make_service(session_factory, _LookupEvidenceAdapter()).closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_RUNTIME,
    )
    await db_session.commit()

    assert calls == [
        (RUNTIME_PRIVATE_OWNER, "agent_runtime_session_bindings", binding.id)
    ], "runtime 集合锁必须以正确身份被调用恰好一次"
    async with session_factory() as v:
        b = await _binding_row(v, binding.id)
        assert b["runtime_session_ref"] is None
        assert b["status"] == "closed"


# ---------------------------------------------------------------------------
# M9：CAS 败者 raise——真实 PG stale-CAS（identity read 后、UPDATE 前并发收口）
# ---------------------------------------------------------------------------


class _CasInjectFactory:
    """session_factory 包装：在指定 CAS UPDATE 前触发并发收口 hook（真实 PG）。

    正常源码路径不受影响（``execute`` 透传）；仅当执行到匹配的 ledger/binding
    CAS UPDATE 时，先让第二连接提交合法收口，再让第一连接的 UPDATE 真实命中
    rowcount=0（stale-CAS）。mutation 把 ``rowcount != 1`` 的 raise 改为静默
    return 后，映射测试转红。
    """

    def __init__(self, inner_factory, match_substr, fire):
        self._inner = inner_factory
        self._match = match_substr
        self._fire = fire
        self._fired = False

    def __call__(self):
        inner_cm = self._inner()
        outer = self

        class _Session:
            def __init__(self, session):
                self._s = session

            async def execute(self, stmt, params=None, *args, **kwargs):
                if not outer._fired and outer._match in str(stmt):
                    outer._fired = True
                    await outer._fire()
                return await self._s.execute(stmt, params, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._s, name)

        class _CM:
            async def __aenter__(self):
                return _Session(await inner_cm.__aenter__())

            async def __aexit__(self, *args):
                return await inner_cm.__aexit__(*args)

        return _CM()


async def test_stale_cas_loser_rollback_external(db_session, session_factory):
    """M9 载体（external）：shared B2 写路径 stale-CAS——helper identity read 完成
    后、实际 ledger UPDATE 前，第二连接并发合法收口同一 ref（真实 PG committed）。
    第一连接 UPDATE 真实 rowcount=0 → raise + T2 整事务回滚：无 partial
    ledger/fence/checkpoint ACK（fence/checkpoint 保持 erasing），ledger 反映并发
    方收口（非本连接 partial 写）、source 恰好清一次。"""
    tid, cid, op1, refs, outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/m9",)
    )
    ref, outbox_id = refs[0], outbox_ids[0]
    receipt_mine = _expected_external_receipt(ref, _evidence_for_external(ref))
    receipt_peer = "b" * 64  # 并发收口的合法 64-hex receipt（与本连接不同值）

    async def _concurrent_close():
        # 第二连接：合法收口同一 ref（shared B2 路径，rowcount=1）并提交。
        async with session_factory() as s2:
            await write_erased_and_clear_ref(
                s2, ref=ref, receipt_digest=receipt_peer, tenant_id=tid
            )
            await s2.commit()

    factory = _CasInjectFactory(
        session_factory, "UPDATE metaedu.agent_external_object_refs", _concurrent_close
    )
    with pytest.raises(ValueError, match="not registered with NULL receipt"):
        await _make_service(factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_EXTERNAL,
        )
    await db_session.rollback()

    async with session_factory() as v:
        # 无 partial fence/checkpoint ACK（整事务回滚）。
        assert await _fence_state(v, cid, _EXTERNAL) == "erasing"
        assert await _cp(v, op1, _EXTERNAL, "state") == "erasing"
        # ledger 反映并发方收口（receipt_peer），非本连接 partial 写（receipt_mine）。
        row = await _ref_row(v, ref.id)
        assert row["erase_state"] == "erased"
        assert row["receipt_digest"] == receipt_peer
        assert row["receipt_digest"] != receipt_mine
        # source 恰好清一次（并发方）；本连接未重复清。
        ob = await _outbox_row(v, outbox_id)
        assert ob["payload_ref"] is None
        assert ob["status"] == "suppressed"


async def test_stale_cas_loser_rollback_runtime(db_session, session_factory):
    """M9 载体（runtime）：shared B2 写路径 stale-CAS——identity read 后、binding
    UPDATE 前，第二连接并发合法关同一 binding。第一连接 UPDATE rowcount=0 →
    raise + 整事务回滚：fence/checkpoint 保持 erasing，binding 反映并发方收口
    （ref NULL + closed，revision 恰好 +1，非双重收口）。"""
    tid, cid, op1, bindings = await _settle_window_runtime(
        db_session, binding_refs=("pi://session/m9",)
    )
    binding = bindings[0]

    async def _concurrent_close():
        async with session_factory() as s2:
            await write_erased_and_close_binding(
                s2, binding=binding, receipt_digest=_pad64("peer"), tenant_id=tid
            )
            await s2.commit()

    factory = _CasInjectFactory(
        session_factory,
        "UPDATE metaedu.agent_runtime_session_bindings",
        _concurrent_close,
    )
    with pytest.raises(ValueError, match="close hit 0 row"):
        await _make_service(factory, _LookupEvidenceAdapter()).closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1, owner_key=_RUNTIME,
        )
    await db_session.rollback()

    async with session_factory() as v:
        assert await _fence_state(v, cid, _RUNTIME) == "erasing"
        assert await _cp(v, op1, _RUNTIME, "state") == "erasing"
        b = await _binding_row(v, binding.id)
        assert b["runtime_session_ref"] is None
        assert b["status"] == "closed"
        rev = await v.scalar(
            text(
                "SELECT revision FROM metaedu.agent_runtime_session_bindings "
                "WHERE id = :i"
            ),
            {"i": binding.id},
        )
        assert int(rev) == 2, "并发方恰好收口一次（revision 1→2），本连接零写"
