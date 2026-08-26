"""R1-S6-I3 故障矩阵（external owner 族）：F4 + F11。

契约：Plan §R1-S6-5（S6-F4 / S6-F11 行，已随 PR #581 并入 main）。
从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分的一部分；本文件承载
external.payload.v1 owner 的两类故障。

F1-F14 逐行映射（本文件承担的行）：
- F4  → ``test_f4_single_owner_stepwise_ack_partial_ref_crash_replay``
        （单 owner 内分步 ACK：部分 ref 先 ACK、部分失败 + 同窗口重放）
- F11 → ``test_f11_mutate_checkpoint_state_during_lookup_fail_closed``
        （checkpoint.state 篡改 = S5 代码修改点 #2 判别载体，settlement.py:703 已落地）
        + ``test_f11_mutate_source_ref_during_lookup_fail_closed``
        （源行篡改 → frozen intent 重验失败，settlement.py:1006）

F4 载体复用 ``test_s4eb2_external_erasure``（participant 双事务）；F11 载体复用
``test_s5_sch_d_settlement``（settlement T1/T2）。两处 helper 均无命名冲突。
"""

from __future__ import annotations

# ruff: noqa: F401, F811  (pytest fixture imports + test signature reuse are intentional)
import asyncio

import pytest
from sqlalchemy import text

from app.composition.external_object_adapter import (
    ExternalEraseSuccess,
    ExternalObjectAdapter,
)
from app.composition.settlement import SettlementService
from app.composition.transactional_projection_coordinator import build_scan_providers
from app.contexts.agent_workspace.domain import PurgeOwnerState
from tests.composition.test_s4eb2_external_erasure import (
    _ensure_test_tenant,
    _external_registry_enabled,  # noqa: F401  (pytest fixture; F811 ruff误判)
    _ledger_state,
    _make_purge_operation,
    _participant,
    _seed_deleted_expired_conversation,
    _seed_run_event_ref,
    _seed_workspace_outbox_ref,
)
from tests.composition.test_s5_sch_d_settlement import (
    _EXTERNAL,
    _cp,
    _fence_state,
    _noop_adapter_resolver,
    _pad64,
    _settle_window_setup,
)
from tests.contexts.agent_control_plane.helpers import TENANT_ID

pytestmark = pytest.mark.asyncio

_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# S6-F4：单 owner 内分步 ACK（部分 ref 先 ACK、部分失败）
# ---------------------------------------------------------------------------


class _PartialCrashDedupAdapter(ExternalObjectAdapter):
    """F4 注入：per-ref 分步——首个 distinct ref 的 delete 成功（外部副作用已发生），
    第二个 distinct ref 的 delete 抛非 ``ExternalEraseError``（Tx1 提交后、Tx2 前
    进程崩溃，异常在 Tx2 写 erased 前逃逸）。

    dedup store 按 idempotency key 缓存 evidence：同 key 重放命中缓存（**distinct
    副作用恰 1/ref**，E-6「无重复副作用」判别点）——「已 ACK ref 保持」由
    ``distinct_deletes`` 对 ref1 恰为 1 证明。
    """

    adapter_key = "fake-db-local"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = False

    def __init__(self) -> None:
        self.calls = 0
        self._store: dict[str, str] = {}
        self.distinct_deletes = 0
        self._crashed = False

    async def delete_object(self, **kwargs):
        self.calls += 1
        key = kwargs["idempotency_key"]
        if key in self._store:  # 已 ACK ref 重放：幂等命中，零二次副作用
            return ExternalEraseSuccess(adapter_receipt_evidence=self._store[key])
        if self.distinct_deletes >= 1 and not self._crashed:
            self._crashed = True
            raise RuntimeError("simulated crash: ref1 ACK 后、ref2/Tx2 前")
        self._store[key] = f"ev:{key[:16]}"
        self.distinct_deletes += 1
        return ExternalEraseSuccess(adapter_receipt_evidence=self._store[key])

    async def receipt_lookup(self, **kwargs):
        return None


async def _op_checkpoint(db_session, op_id):
    row = (
        await db_session.execute(
            text(
                "SELECT state, attempt, checkpoint_digest FROM "
                "metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    return dict(row)


async def _ref_id_for_source(db_session, source_row_id):
    return (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_external_object_refs "
                "WHERE source_row_id = :sr"
            ),
            {"sr": source_row_id},
        )
    ).scalar_one()


async def test_f4_single_owner_stepwise_ack_partial_ref_crash_replay(
    db_session, _external_registry_enabled  # noqa: F811  (pytest fixture; F401+F811 ruff误判)
):
    """F4：单 owner 内分步 ACK（部分 ref 先 ACK、部分失败）。

    冻结期望（Plan §S6-5 S6-F4）：已 ACK ref 保持、失败 ref 重放继续收口、
    attempt 不重复推进。注入 = 多 ref adapter 逐 ref 故障（首个 ref delete 成功后、
    第二 ref delete 崩溃）。

    - **部分 ref 先 ACK、部分失败**：Run 1 Tx1 提交（checkpoint erasing + attempt=1
      + 双 ref intent digest），锁外 adapter 逐 ref——ref1 delete 成功（外部副作用
      已发生）、ref2 delete 崩溃 → Tx2 未跑，双 ref 停留 registered。
    - **attempt 不重复推进**：Run 2 同 invocation 重放（checkpoint erasing + 同
      intent）走 :632-639 续做分支——attempt 保持 1（不 bump）。
    - **已 ACK ref 保持**：ref1 重放命中 dedup store（distinct 副作用恰 1，零二次
      删除）；**失败 ref 重放继续收口**：ref2 重做成功 → 双 ref erased + ACK。
    """
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    # 两个 ref（分步 ACK 载体；不同 source_table，规避 outbox 一会话一 turn 唯一约束）。
    outbox_a = await _seed_workspace_outbox_ref(
        db_session, conv_id, ref_value="obj://staging/object/a"
    )
    _, event_b = await _seed_run_event_ref(
        db_session, conv_id, ref_value="obj://staging/object/b"
    )
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _PartialCrashDedupAdapter()
    # Run 1：Tx1 提交后，锁外逐 ref adapter——ref1 成功、ref2 崩溃（Tx2 未跑）。
    with pytest.raises(RuntimeError, match="simulated crash"):
        await _participant(db_session, adapter).erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    # Run 1 崩溃后：attempt=1（首推进），双 ref 仍 registered（Tx2 未写），仅一个
    # ref 的外部副作用已发生（distinct==1）。
    cp = await _op_checkpoint(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ERASING.value
    assert cp["attempt"] == 1
    assert cp["checkpoint_digest"] is not None
    assert adapter.distinct_deletes == 1, "部分 ref 先 ACK（仅 ref1 副作用）"
    for source_row_id in (outbox_a, event_b):
        state = await _ledger_state(db_session, await _ref_id_for_source(db_session, source_row_id))
        assert state["erase_state"] == "registered", "Tx2 未跑，双 ref 停留 registered"
        assert state["receipt_digest"] is None
    await db_session.commit()

    # Run 2（同 invocation 重放）：operation 已 running，caller 传 mark_running 后的
    # revision。复用同一 dedup adapter（证明 ref1 幂等保持）。
    op_rev = (
        await db_session.execute(
            text("SELECT revision FROM metaedu.agent_conversation_purges WHERE id = :op"),
            {"op": op_id},
        )
    ).scalar_one()
    await _participant(db_session, adapter).erase_external_payload(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )

    # attempt 不重复推进（续做分支不 bump）+ 双 ref erased + ACK。
    cp = await _op_checkpoint(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value
    assert cp["attempt"] == 1, "attempt 不重复推进（同窗口重放零 bump）"
    assert adapter.distinct_deletes == 2, "已 ACK ref 保持（ref1 恰 1）+ 失败 ref 收口"
    for source_row_id in (outbox_a, event_b):
        state = await _ledger_state(db_session, await _ref_id_for_source(db_session, source_row_id))
        assert state["erase_state"] == "erased"
        assert state["receipt_digest"] is not None

    # source ref 清零断言（mutation M-F4 注入点观察：B2 是 source ref 唯一清除者——
    # outbox `payload_ref=NULL + status='suppressed'`；RunEvent `payload_ref=NULL +
    # payload_state='redacted'`）。mutation 跳过 `_clear_source_ref` 后断言失败 → red。
    outbox_row = (
        await db_session.execute(
            text(
                "SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                "WHERE id = :id"
            ),
            {"id": outbox_a},
        )
    ).mappings().one()
    assert outbox_row["payload_ref"] is None, "outbox source ref 必须清零（B2 唯一）"
    assert outbox_row["status"] == "suppressed"
    event_row = (
        await db_session.execute(
            text(
                "SELECT payload_ref, payload_state FROM metaedu.agent_run_events "
                "WHERE id = :id"
            ),
            {"id": event_b},
        )
    ).mappings().one()
    assert event_row["payload_ref"] is None, "RunEvent source ref 必须清零（B2 唯一）"
    assert event_row["payload_state"] == "redacted"


# ---------------------------------------------------------------------------
# S6-F11：mutate-during-lookup（锁外窗口第二连接篡改 → T2 重验 fail closed 零写）
# ---------------------------------------------------------------------------


class _BlockingLookupAdapter:
    """锁外 lookup 屏障：进入 receipt_lookup 即 ``entered.set()`` 并阻塞至
    ``release``——把 T1 提交后、T2 前的锁外窗口撑开，供第二连接篡改。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.lookup_calls = 0

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_calls += 1
        self.entered.set()
        await self.release.wait()
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")


async def test_f11_mutate_checkpoint_state_during_lookup_fail_closed(
    db_session, session_factory
):
    """F11（checkpoint.state 篡改 = S5 代码修改点 #2 判别载体）。

    冻结期望（Plan §S6-5 S6-F11 + 裁决二）：锁外 lookup 时第二连接篡改
    checkpoint.state → T2 重验 ``checkpoint.state == 'erasing'``（settlement.py:703，
    S6 实现阶段已补）→ fail closed 零写。

    注入：``_BlockingLookupAdapter`` 撑开锁外窗口（T1 已提交释放全部锁），第二连接
    把 checkpoint.state 由 erasing 改 pending → T2 ``_verify_t2_tokens`` 重读已提交
    行，:703 状态重验失败 fail closed；settlement 零写（checkpoint 停留被篡改的
    pending、fence 停留 erasing、attempt 不变）。
    """
    tid, cid, op1, _refs = await _settle_window_setup(db_session)
    adapter = _BlockingLookupAdapter()
    service = SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    closeout = asyncio.create_task(
        service.closeout_erasing(
            tenant_id=tid, conversation_id=cid,
            purge_operation_id=op1, owner_key=_EXTERNAL,
        )
    )
    # 等 T1 提交 + 进入锁外 lookup（锁已释放）。
    await asyncio.wait_for(adapter.entered.wait(), timeout=_TIMEOUT)
    # 锁外窗口：第二连接篡改 checkpoint.state erasing→pending。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET state='pending', "
                "updated_at=now() WHERE purge_operation_id=:op AND owner_key=:k"
            ),
            {"op": op1, "k": _EXTERNAL},
        )
        await s.commit()
    adapter.release.set()
    # T2 重验 checkpoint.state != erasing → fail closed 零写。
    with pytest.raises(ValueError, match="checkpoint state"):
        await asyncio.wait_for(closeout, timeout=_TIMEOUT)
    # 零写判别：settlement 未覆写（checkpoint 停留 pending、fence 停留 erasing、attempt 1）。
    async with session_factory() as verify:
        assert await _cp(verify, op1, _EXTERNAL, "state") == "pending"
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing"
        assert await _cp(verify, op1, _EXTERNAL, "attempt") == 1


async def test_f11_mutate_source_ref_during_lookup_fail_closed(
    db_session, session_factory
):
    """F11（源行篡改）：锁外 lookup 时第二连接把 registered ref 改 erased →
    T2 ``_load_frozen_window`` 重读集合变化 → ``_verify_frozen_intent``
    （settlement.py:1006）intent digest 不符 → fail closed 零写。

    判别载体：mutate-during-lookup 的「源行」维度——T1 冻结窗口（1 registered ref）
    与 T2 重读窗口（0 registered ref）不一致，checkpoint 冻结 intent token 与重导出
    intent 不符。
    """
    tid, cid, op1, refs = await _settle_window_setup(db_session)
    assert len(refs) == 1
    adapter = _BlockingLookupAdapter()
    service = SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )
    closeout = asyncio.create_task(
        service.closeout_erasing(
            tenant_id=tid, conversation_id=cid,
            purge_operation_id=op1, owner_key=_EXTERNAL,
        )
    )
    await asyncio.wait_for(adapter.entered.wait(), timeout=_TIMEOUT)
    # 锁外窗口：第二连接篡改唯一 registered ref 的 ref_value（CHECK 不拒；集合不变
    # 但 digest 内容变化 → ``_verify_frozen_intent`` 重新派生与 T1 冻结 token 不符）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs SET "
                "ref_value='obj://staging/object/tampered', updated_at=now() "
                "WHERE tenant_id=:t AND conversation_id=:c AND erase_state='registered'"
            ),
            {"t": tid, "c": cid},
        )
        await s.commit()
    adapter.release.set()
    # T2 frozen intent 重验失败 → fail closed 零写。
    with pytest.raises(ValueError, match="intent digest mismatch"):
        await asyncio.wait_for(closeout, timeout=_TIMEOUT)
    # 零写判别：checkpoint 停留 erasing（settlement 未落账）、fence 停留 erasing、attempt 1。
    async with session_factory() as verify:
        assert await _cp(verify, op1, _EXTERNAL, "state") == "erasing"
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing"
        assert await _cp(verify, op1, _EXTERNAL, "attempt") == 1
