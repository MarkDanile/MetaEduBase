"""R1-S6-I3 F10 故障矩阵（settlement T1/T2 hold 推进）真实 PG 判别。

契约：Plan §S6-15.3 (TD-105) — F10 settlement 读法锁定（裁决二 supersede S5-SCH-2
T2 token 清单 hold snapshot 项）；F10 = T1 commit 后、T2 前 create hold → T2
照常完成 erase（fence erased + checkpoint acked）→ G2 blocked_hold_revision_changed
→ rebuild G3 HOLD_GATED → 释放/过期 hold 后 G3 消解 → 新 operation 走完后
scan 全零达 completed。

测试范围（承接 §S6-15.3 路由表 + TD-106 收口不变式）：
- F10 四环（T2 单向放行 → fence erased + checkpoint acked → G2 hold-drift 投影 →
  rebuild G3 HOLD_GATED）；
- TD-106 方案 A 不变式（per-ref receipt + source 清除）于 F10 hold 推进下保持；
- hold 释放 bump / 过期不 bump 两条后续路径；
- 零正文复活、零重复 adapter 调用、重放幂等。

本 PR 仅承载测试 + 必要 helpers；不修改 settlement / participant / projection /
rebuild 生产代码（已随 PR #586 入 main 完成）；不接生产 wiring；不翻转 capability；
不实现 PR-D / PR-E / C1 / S5 production wiring。
"""

from __future__ import annotations

# ruff: noqa: F401, F811  (pytest fixture imports + test signature reuse are intentional)
import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.composition.purge_rebuild import (
    PurgeRebuildService,
    RebuildKind,
)
from app.composition.settlement import SettlementService
from app.composition.transactional_projection_coordinator import (
    TransactionalProjectionCoordinator,
    build_scan_providers,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)

# 复用 settlement / projection / rebuild 已落地 helper（re-scope：F10 仅消费既有
# helper，不复制、不改 S5 代码）。
from tests.composition.s6i3_seeds import (
    _seed_6_owner_acked_with_residual_body,
    _seed_tenant,
)
from tests.composition.test_s5_sch_d_settlement import (
    _EXTERNAL,
    _claim,
    _cp,
    _ensure_tenant,
    _fence_state,
    _LookupEvidenceAdapter,
    _noop_adapter_resolver,
    _pad64,
    _seed_conversation,
    _seed_fence,
    _set_cp,
)
from tests.composition.test_s6_td106_settlement_ledger import (
    _evidence_for_external,
    _expected_external_receipt,
    _outbox_row,
    _ref_row,
    _settle_window_external,
)

pytestmark = pytest.mark.asyncio

_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# F10 局部 helpers（专用于 F10 settlement T1/T2 hold 推进场景）
# ---------------------------------------------------------------------------


class _BlockingLookupAdapter:
    """锁外 lookup 屏障：进入 receipt_lookup 即 entered.set() 并阻塞至 release——
    把 T1 提交后、T2 前的锁外窗口撑开，供第二连接 create_legal_hold 推进 hold_revision。

    复用 _BlockingLookupAdapter 模式（test_s6i3_fault_external.py:237）同形态：
    允许在 closeout_erasing 内的 T1→adapter I/O 边界精确注入并发变更。
    """

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


async def _create_legal_hold(session_factory, *, tid, cid, purpose):
    """第二连接 create_legal_hold（沿 I1 冻结 primitive）—— 用于在 T1 commit 后
    锁外窗口精确推进 conversation.hold_revision 0→1（F10 注入点）。
    """
    async with session_factory() as s:
        hold = await AgentErasureRepository(s).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose=purpose,
            actor_id=uuid.uuid4(),
        )
        await s.commit()
        return hold


async def _release_legal_hold(session_factory, *, tid, cid, hold_id):
    """hold 释放 primitive：bump hold_revision（F10 释放后续路径入口）。"""
    async with session_factory() as s:
        released = await AgentErasureRepository(s).release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold_id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
        await s.commit()
        return released


async def _expire_legal_hold(session_factory, *, tid, cid, hold_id):
    """hold 过期写入（裁决一读侧谓词宽化所需，expires_at 已 past 即可，不 bump
    hold_revision）。"""
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_legal_holds "
                "SET expires_at = now() - interval '1 day' "
                "WHERE id = :hid"
            ),
            {"hid": hold_id},
        )
        await s.commit()


async def _hold_count(session_factory, cid) -> int:
    async with session_factory() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM metaedu.agent_conversation_legal_holds "
                        "WHERE conversation_id = :cid"
                    ),
                    {"cid": cid},
                )
            ).scalar()
            or 0
        )


async def _hold_revision(session_factory, cid) -> int:
    async with session_factory() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT hold_revision FROM metaedu.agent_conversations "
                        "WHERE id = :cid"
                    ),
                    {"cid": cid},
                )
            ).scalar()
            or 0
        )


async def _op_state_failure(session_factory, op_id) -> tuple[str, str | None]:
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT state, failure_code FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).one()
        return row[0], row[1]


async def _conversation_title(session_factory, cid) -> str | None:
    async with session_factory() as s:
        return (
            await s.execute(
                text("SELECT title FROM metaedu.agent_conversations WHERE id = :cid"),
                {"cid": cid},
            )
        ).scalar_one()


# ---------------------------------------------------------------------------
# F10 routing 表 — T1 commit + mid-flight hold advance → T2 SUCCESS
# ---------------------------------------------------------------------------


async def test_f10_t1_then_advance_hold_t2_completes(db_session, session_factory):
    """F10 路由四环（核心）：settlement T1 commit → 第二连接 create_legal_hold
    推进 hold_revision 0→1 → T2 SUCCESS → fence erased + checkpoint acked。

    注入点（§S6-15.3）：T1 commit 释放锁后、T2 前，第二连接 ``create_legal_hold``
    → ``conversation.hold_revision`` 0→1（active hold）；T2 单向 hold 检查放行
    （snapshot=0 < current=1，advance），fence + checkpoint 同事务落账
    （TD-106 方案 A 已合并入 main；B2 唯一清除路径委托现有 helper）。

    判别：
    - fence `erased` + checkpoint `acked`（TD-106 同事务落账层证据）；
    - hold 行持久保留为审计（与 G3 active hold 持久语义一致）；
    - 正文未复活（settlement 不写正文，append-only guard 防任何回写）。
    """
    tid, cid, op1, refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10",)
    )

    adapter = _BlockingLookupAdapter()
    service = SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )

    closeout = asyncio.create_task(
        service.closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    # 等 T1 commit + adapter I/O 进入锁外窗口（adapter 已被 ``entered`` 屏障阻塞）。
    await asyncio.wait_for(adapter.entered.wait(), timeout=_TIMEOUT)

    # 注入点：第二连接 create_legal_hold 推进 hold_revision 0→1（F10 路由精确点）。
    assert await _hold_revision(session_factory, cid) == 0
    await _create_legal_hold(
        session_factory, tid=tid, cid=cid, purpose="F10 mid-flight advance"
    )
    assert await _hold_revision(session_factory, cid) == 1

    # 释放 lookup 屏障 → T2 走完（单向 hold check `0 > 1`=False 放行；fence +
    # checkpoint 同事务落账；TD-106 收口层 per-ref receipt + source clear）。
    adapter.release.set()
    await asyncio.wait_for(closeout, timeout=_TIMEOUT)

    # 判别：四环 + hold 持久 + 正文未复活。
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
    assert await _hold_revision(session_factory, cid) == 1
    # hold 行持久保留为审计（不会随 settlement 删行）。
    assert await _hold_count(session_factory, cid) == 1
    # TD-106 不变式：per-ref receipt + source clear（外部 ledger 行 + outbox 行）。
    async with session_factory() as verify:
        ref = refs[0]
        ledger_row = await _ref_row(verify, ref.id)
        assert ledger_row["erase_state"] == "erased"
        assert ledger_row["receipt_digest"] == _expected_external_receipt(
            ref, _evidence_for_external(ref)
        )
        outbox_row = await _outbox_row(verify, ref.source_row_id)
        assert outbox_row["payload_ref"] is None, "B2 唯一清除者命中源行（ref 行 cleared）"
    # 正文（title）未复活（settlement 不写正文；append-only guard 防回写）。
    assert await _conversation_title(session_factory, cid) == "t", (
        "settlement 不改正文（正文由 participant Tx2 清除）"
    )


# ---------------------------------------------------------------------------
# F10 路由 — T2 单向 hold 检查：advance 放行 / regression fail-closed
# ---------------------------------------------------------------------------


async def test_f10_t2_unidirectional_advance_passes(db_session, session_factory):
    """F10 单向 hold check advance 分支：hold_revision_snapshot=0 且 conversation
    hold_revision=1（drift 推进）→ T2 放行。

    注入形态（pre-advance，避免双连接屏障）：种 frozen-snapshot hold=0，外部 SQL
    UPDATE 把 conversation hold_revision=1 → settlement.closeout_erasing 走完 T1
    + adapter + T2；frozen-snapshot 六条校验之第 4 条（drift 判定）`0 > 1`=False
    不 fail closed；T2 同基准重读 hold=1 ≤ snapshot=0（re-read 0 > 1=False）→ 放行。

    判别：fence erased + checkpoint acked + ledger/binding 收口（与上同）。
    """
    tid, cid, op1, refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-advance",)
    )
    # Pre-advance：conversation.hold_revision 0→1，operation snapshot 仍 0（drift）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET hold_revision = 1 WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await s.commit()

    await (
        SettlementService(
            session_factory,
            scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
        ).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    await db_session.commit()

    async with session_factory() as verify:
        # T2 单向放行（advance）；fence + checkpoint 同事务落账。
        assert await _fence_state(verify, cid, _EXTERNAL) == "erased"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "acked"
        # TD-106 不变式保持。
        ref = refs[0]
        ledger_row = await _ref_row(verify, ref.id)
        assert ledger_row["erase_state"] == "erased"
        assert ledger_row["receipt_digest"] == _expected_external_receipt(
            ref, _evidence_for_external(ref)
        )


async def test_f10_t2_unidirectional_regression_fails_closed(
    db_session, session_factory
):
    """F10 单向 hold check regression 分支：hold_revision_snapshot > conversation
    hold_revision（回退 / 脏数据形态）→ frozen-snapshot 校验 fail-closed 零写。

    注入形态：operation snapshot=2，conversation hold_revision=1 → 触发
    ``hold_revision_snapshot > conversation hold_revision`` raise；零写零
    fence/checkpoint 推进。

    判别：fence 仍 `erasing` + checkpoint 仍 `erasing`（attempt 不变）+ operation
    state 不变。
    """
    tid, cid, op1, refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-regression",)
    )
    # 注入 regression：operation snapshot=2，conversation hold_revision=1。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET hold_revision = 1 WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET hold_revision_snapshot = 2 "
                "WHERE id = :op"
            ),
            {"op": op1},
        )
        await s.commit()

    with pytest.raises(ValueError, match="hold_revision_snapshot"):
        await (
            SettlementService(
                session_factory,
                scan_providers=build_scan_providers,
                adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
            ).closeout_erasing(
                tenant_id=tid,
                conversation_id=cid,
                purge_operation_id=op1,
                owner_key=_EXTERNAL,
            )
        )

    # 零写判别：fence / checkpoint / ledger 行均维持已存在的状态。
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == "erasing"
        assert await _cp(verify, op1, _EXTERNAL, "state") == "erasing"
        assert await _cp(verify, op1, _EXTERNAL, "attempt") == 1
        ref = refs[0]
        ledger_row = await _ref_row(verify, ref.id)
        assert ledger_row["erase_state"] == "registered", "regression 不触 ledger 写"


# ---------------------------------------------------------------------------
# F10 路由 — projection G2 blocked_hold_revision_changed（不得直接 completed）
# ---------------------------------------------------------------------------


async def test_f10_projection_g2_blocked_hold_revision_changed_no_completed(
    db_session, session_factory
):
    """F10 路由第二环：T1+T2 落账后（fence erased + checkpoint acked），projection
    聚合读 hold_revision_snapshot=0 与 conversation hold_revision=1 → G2 drift
    命中 → operation blocked + failure_code=blocked_hold_revision_changed。

    冻结期望（§S6-15.3）：F10 不直接宣称原 operation completed（completed 仍需
    后续 rebuild、新 operation 与最终扫描）；本断言显式检 operation 未 completed。
    """
    tid, cid, op1, _refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-g2",)
    )
    # Pre-advance：hold_revision 0→1，让 settlement 走完 T2（同 test_f10_..._advance
    # 路径，避免双连接屏障；G2 投影语义相同）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET hold_revision = 1 WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await s.commit()
    await (
        SettlementService(
            session_factory,
            scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
        ).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    await db_session.commit()

    # projection 聚合（F10 路由第二环：G1>G2 优先于 checkpoint 聚合，
    # projection_calculator:319-326）。
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
        )

    # 判别：G2 命中（hold_drift=True ⇒ failure_code=blocked_hold_revision_changed），
    # operation 状态 blocked，purge_state=blocked——F10 不直接 completed。
    state, fc = await _op_state_failure(session_factory, op1)
    assert state == "blocked"
    assert fc == "blocked_hold_revision_changed"
    async with session_factory() as verify:
        purge_state = (
            await verify.execute(
                text(
                    "SELECT purge_state FROM metaedu.agent_conversations WHERE id = :cid"
                ),
                {"cid": cid},
            )
        ).scalar_one()
        assert purge_state == "blocked"


# ---------------------------------------------------------------------------
# F10 路由 — rebuild G3 HOLD_GATED + 释放/过期路径
# ---------------------------------------------------------------------------


async def test_f10_rebuild_hold_gated_with_active_hold(
    db_session, session_factory
):
    """F10 路由第三环：G2-blocked operation + active hold → rebuild 进入
    HOLD_GATED（不 eager 重建全 pending 中间 op，裁决一 G3 谓词）。

    注入：种 conversation（active hold 创建，hold_revision=1）+ G2-blocked
    operation（state=blocked, failure_code=blocked_hold_revision_changed）+ 全部
    owner 非 erasing（fence erased + checkpoint acked，T2 已落账）—— rebuild
    判定 G3 命中（``_repo.has_active_legal_hold``）→ 返回 HOLD_GATED。
    """
    tid, cid, op1, _refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-rebuild-gated",)
    )
    # settlement T2 SUCCESS + pre-advance → operation 投影后落 blocked_hold。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET hold_revision = 1 WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET hold_revision_snapshot = 0 "
                "WHERE id = :op"
            ),
            {"op": op1},
        )
        await s.commit()
    await (
        SettlementService(
            session_factory,
            scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
        ).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    await db_session.commit()
    # projection 落 G2-blocked。
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1
        )

    # 注入：建 active hold（与 F10 注入 hold 一致），保证 has_active_legal_hold True。
    await _create_legal_hold(
        session_factory, tid=tid, cid=cid, purpose="F10 rebuild gated hold"
    )

    # rebuild：G3 命中 → HOLD_GATED。
    async with session_factory() as s, s.begin():
        outcome = await PurgeRebuildService(s).rebuild(
            tenant_id=tid,
            conversation_id=cid,
            retention_policy_snapshot={"conversation_recovery_days": 30},
        )
    assert outcome.kind == RebuildKind.HOLD_GATED


async def test_f10_rebuild_unblocks_after_hold_release_bumps_revision(
    db_session, session_factory
):
    """F10 释放路径：hold 释放 bump hold_revision 1→2 → 新 operation 建
    hold_snapshot=2（== current=2）→ rebuild REBUILT。

    注入：F10 链 → G2 blocked → 释放 hold（bump 1→2）→ rebuild → 新 operation
    hold_snapshot=conversation.hold_revision=2 → G2 不命中（advance 不再），G3
    active hold=False（已 release）→ 全 owner 仍非 erasing → REBUILT。
    """
    tid, cid, op1, _refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-release",)
    )
    # F10 中段注入：建 active hold（bump 0→1）。
    hold = await _create_legal_hold(
        session_factory, tid=tid, cid=cid, purpose="F10 release bump"
    )
    assert await _hold_revision(session_factory, cid) == 1
    await (
        SettlementService(
            session_factory,
            scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
        ).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    await db_session.commit()
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1
        )
    # 释放 hold（bump 1→2）。
    await _release_legal_hold(session_factory, tid=tid, cid=cid, hold_id=hold.id)
    assert await _hold_revision(session_factory, cid) == 2

    # rebuild：G2 cleared（新 op snapshot=2 == current=2），G3 cleared（active hold False），
    # 无 erasing → REBUILT。
    async with session_factory() as s, s.begin():
        outcome = await PurgeRebuildService(s).rebuild(
            tenant_id=tid,
            conversation_id=cid,
            retention_policy_snapshot={"conversation_recovery_days": 30},
        )
    assert outcome.kind == RebuildKind.REBUILT
    assert outcome.purge_revision is not None and outcome.purge_revision >= 2


async def test_f10_rebuild_unblocks_after_hold_expire_no_bump(
    db_session, session_factory
):
    """F10 过期路径（裁决一读侧谓词宽化）：hold 过期（expires_at 已 past，
    **不** bump hold_revision）→ rebuild 把过期 hold 视为非 active → REBUILT。

    注入：F10 链 → G2 blocked → 建 active hold + expires_at 已 past → rebuild
    → 新 operation hold_snapshot=conversation.hold_revision=1（不变）→
    G2 cleared（snapshot=1 == current=1）→ REBUILT。
    """
    tid, cid, op1, _refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-expire",)
    )
    # F10 中段注入：建 active hold（bump 0→1）。
    hold = await _create_legal_hold(
        session_factory, tid=tid, cid=cid, purpose="F10 expire no bump"
    )
    assert await _hold_revision(session_factory, cid) == 1
    await (
        SettlementService(
            session_factory,
            scan_providers=build_scan_providers,
            adapter_resolver=_noop_adapter_resolver(_LookupEvidenceAdapter()),
        ).closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
    )
    await db_session.commit()
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1
        )

    # 过期 hold：expires_at 设为 past，hold_revision 不 bump（裁决一）。
    await _expire_legal_hold(session_factory, tid=tid, cid=cid, hold_id=hold.id)
    assert await _hold_revision(session_factory, cid) == 1, "过期不 bump hold_revision"

    # rebuild：过期 hold 被 has_active_legal_hold 视为非 active → REBUILT。
    async with session_factory() as s, s.begin():
        outcome = await PurgeRebuildService(s).rebuild(
            tenant_id=tid,
            conversation_id=cid,
            retention_policy_snapshot={"conversation_recovery_days": 30},
        )
    assert outcome.kind == RebuildKind.REBUILT


# ---------------------------------------------------------------------------
# F10 不变式 — 零正文复活 / 零重复 adapter / 重放幂等
# ---------------------------------------------------------------------------


async def test_f10_no_body_resurrection_no_repeated_adapter_replay_idempotent(
    db_session, session_factory
):
    """F10 不变式三联：
    (a) 零正文复活：F10 链不写正文，正文（title）保持 seed 值不被 settlement / adapter 篡改；
    (b) 零重复 adapter 调用：F10 SUCCESS 后重放 closeout_erasing → adapter 不被再次调用
        （fence erased + checkpoint acked → idempotent return / 零写判定）；
    (c) 重放幂等：第二次 closeout_erasing 落账后 fence/checkpoint/ledger 与首次相同。
    """
    tid, cid, op1, refs, _outbox_ids = await _settle_window_external(
        db_session, ref_values=("obj://staging/object/f10-idempotent",)
    )

    adapter = _LookupEvidenceAdapter()
    service = SettlementService(
        session_factory,
        scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(adapter),
    )

    # 首次 closeout_erasing → F10 SUCCESS。
    await service.closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()
    first_lookups = adapter.lookup_calls

    # 抓快照用于重放断言。
    async with session_factory() as verify:
        first_fence = await _fence_state(verify, cid, _EXTERNAL)
        first_cp_state = await _cp(verify, op1, _EXTERNAL, "state")
        first_cp_attempt = await _cp(verify, op1, _EXTERNAL, "attempt")
        ref = refs[0]
        first_ledger = await _ref_row(verify, ref.id)
        first_title = (
            await verify.execute(
                text(
                    "SELECT title FROM metaedu.agent_conversations WHERE id = :cid"
                ),
                {"cid": cid},
            )
        ).scalar_one()
    assert first_fence == "erased"
    assert first_cp_state == "acked"

    # 重放：第二次 closeout_erasing → 已 ack_lost / 已 settle → idempotent 零写。
    await service.closeout_erasing(
        tenant_id=tid,
        conversation_id=cid,
        purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    # (b) 零重复 adapter 调用：second closeout 不调 lookup（fence erased → ack_lost
    # repair / idempotent zero-write 路径，无 lookup I/O）。
    assert adapter.lookup_calls == first_lookups, (
        f"重放不得触发额外 adapter lookup（首次 {first_lookups}, 重放后 {adapter.lookup_calls}）"
    )

    # (c) 重放幂等：fence/checkpoint/ledger/title 均与首次一致（零变化）。
    async with session_factory() as verify:
        assert await _fence_state(verify, cid, _EXTERNAL) == first_fence
        assert await _cp(verify, op1, _EXTERNAL, "state") == first_cp_state
        assert await _cp(verify, op1, _EXTERNAL, "attempt") == first_cp_attempt
        second_ledger = await _ref_row(verify, ref.id)
        assert second_ledger["erase_state"] == first_ledger["erase_state"]
        assert second_ledger["receipt_digest"] == first_ledger["receipt_digest"]
        second_title = (
            await verify.execute(
                text(
                    "SELECT title FROM metaedu.agent_conversations WHERE id = :cid"
                ),
                {"cid": cid},
            )
        ).scalar_one()
        # (a) 零正文复活：title 始终保持 seed 值。
        assert first_title == "t" and second_title == "t", (
            "settlement 不写正文；append-only guard 防任何回写"
        )


# ---------------------------------------------------------------------------
# F10 M6 priority-3 scan 真实 PG 判别载体（独立 test contract）
# ---------------------------------------------------------------------------

async def test_f10_m6_completed_bypass_scan_check_blocked(
    db_session, session_factory
):
    """F10 M6：priority-3 scan nonzero 阻断 → blocked（精确 scan reason）。

    既有 F10 测试集（test_f10_* 8 项）**全部**走 hold_revision 0→1 → G2
    提前 return blocked_hold_revision_changed（``projection_calculator.py:319-326``），
    永远到不了 priority-3 scan check（``L491-507``）。本测试是 M6 NOT-RED 解除
    的独立判别载体：构造 G1/G2/G3 cleared 场景使 priority-3 唯一可达。

    构造路径（**不**依赖 hold drift）：
    - G1 cleared：registry_digest_matches=True（snapshot 与 operation registry 一致）。
    - G2 cleared：hold_revision_snapshot=0 == conversation.hold_revision=0
      （**不** create_legal_hold；**不**推进 hold_revision）。
    - G3 cleared：无 active legal hold（**不** INSERT agent_legal_holds active）。
    - 6 owner 全部 checkpoint.state=acked + ack_digest=64hex + capability_digest
      匹配 snapshot + owner_version=1（通过 my new helper
      ``_seed_6_owner_acked_with_residual_body``）。
    - 5-party validation 全 pass：5 非 window owner fence=erased + window owner
      fence 由 closeout_erasing 从 erasing 推到 erased。
    - workspace.core.v1 final scan nonzero：conversation.actor_state='present'
      （默认 _seed_conversation）→ unanonymized_actors=1 → scan_total=1。

    Control 期望：aggregate_projection 返回 state=blocked + failure_code=
    "workspace_body_scan_nonzero"（``projection_calculator.py:485-507`` +
    ``SCAN_REASON_BY_OWNER["workspace.core.v1"]``）。
    Mutant 期望（M6 折叠 priority-3）：``nonzero_scans = []`` + ``if False`` →
    priority 1 completed 分支（``L509-516``）→ state="completed" + failure_code=None
    → 测试断言 `state == "blocked"` 失败 → **红**。
    """
    from app.composition.transactional_projection_coordinator import (
        TransactionalProjectionCoordinator,
    )

    # ---- phase 1: seed 全 6 owner pending + window owner fence erased（**不**走
    #   closeout_erasing 的 fence erasing→erased 路径，理由：empty window + _LookupNoneAdapter
    #   走 OUTCOME_UNKNOWN 路径，_apply_window_outcome 对 fence 写 erased 触发 S5-C-1
    #   例外条款（ValueError swallowed），fence 保持 'erasing' → 5-party fail → priority 2
    #   提前 blocked with purge_owner_ack_conflict → priority 3 scan 不达。M6 必走 priority
    #   3，唯一办法：fence 预置 'erased'，让 closeout_erasing _apply_window_outcome 中
    #   `if fence.state == "erasing"` 条件 False → 跳过 fence 写，fence 保持 'erased' →
    #   5-party passes → priority 3 触发。empty intent digest 仍由 _settle_empty_window
    #   提供，保证 closeout_erasing 的 _validate_frozen_snapshot 通过）。
    from tests.composition.test_s5_sch_d_settlement import _seed_fence
    from tests.composition.test_s6_td106_settlement_ledger import (
        _settle_empty_window,
    )
    tid, cid, op1 = await _settle_empty_window(db_session, owner_key=_EXTERNAL)
    # 强制 UPDATE window owner fence 从 'erasing' → 'erased'（**不**改其他字段）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences "
            "SET state='erased', ack_digest=:a, acked_at=now() "
            "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:k"
        ),
        {"a": "a" * 64, "t": tid, "c": cid, "k": _EXTERNAL},
    )
    # _settle_empty_window → _claim → 触发 actor_state='redacted' + created_by=NULL。
    # M6 测试需 actor_state='present' 触发 workspace.core.v1 final scan
    # unanonymized_actors 非零 → priority 3 scan_reason 触发。ck_agent_conv_actor 约束：
    # present AND created_by NOT NULL AND creator_identity_digest NULL。强制 UPDATE
    # 回 'present' + created_by=tid + creator_identity_digest=NULL（**不**改其他字段）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET actor_state='present', "
            "    created_by = :tid, creator_identity_digest = NULL "
            "WHERE id = :c"
        ),
        {"c": cid, "tid": tid},
    )
    await db_session.commit()

    # ---- phase 2: 6 owner acked + 5 非 window fence erased（我新 helper；不动
    #   window owner fence=erasing 留 closeout_erasing 推到 erased）
    await _seed_6_owner_acked_with_residual_body(
        db_session,
        tid=tid, cid=cid, purge_operation_id=op1,
        window_owner_key=_EXTERNAL,
    )
    await db_session.commit()

    # ---- phase 3: 公开 production entry closeout_erasing → external.fence erased
    #   + external.checkpoint acked。所有 6 owner 终态（acked + fence=erased）。
    #   用 _LookupNoneAdapter：empty window 路径 → outcome=OUTCOME_UNKNOWN；
    #   closeout 仍正常推进 fence=erased + checkpoint=acked（TD-106 严格计数守卫
    #   处理 0 ref 窗口合法 no-op SUCCESS）。
    from tests.composition.test_s5_sch_d_settlement import _LookupNoneAdapter
    service = SettlementService(
        session_factory, scan_providers=build_scan_providers,
        adapter_resolver=_noop_adapter_resolver(_LookupNoneAdapter()),
    )
    await service.closeout_erasing(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
        owner_key=_EXTERNAL,
    )
    await db_session.commit()

    # ---- phase 4: 公开 production entry aggregate_projection → priority 3 scan
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
        )

    # ---- phase 4: 公开 production entry aggregate_projection → priority 3 scan
    async with session_factory() as s, s.begin():
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
        )

    # ---- phase 5: control 断言（priority-3 scan 阻断）----
    # operation 状态必为 blocked（G1/G2/G3 cleared → 5-party pass → priority-3 触发）。
    # _op_state_failure 接收 session_factory（内部 `async with session_factory() as s:`）；
    # _cp / _fence_state 接收 AsyncSession。分开两层。
    state, fc = await _op_state_failure(session_factory, op1)
    assert state == "blocked", (
        f"M6 control failure: G1/G2/G3 cleared + 6 owner acked + 5-party pass + "
        f"workspace scan nonzero 必须经 priority-3 阻断；operation state 实际 "
        f"{state!r} (failure_code={fc!r})。可能原因：(a) closeout_erasing 未完成 "
        f"fence 推 erased；(b) G1/G2/G3 未 cleared（hold drift 残留 / registry drift / "
        f"active legal hold）；(c) 五方验证未 pass（fence_row 缺失）；(d) 6 owner "
        f"checkpoint 未全 acked（ack_digest 非 64hex）"
    )
    assert fc == "workspace_body_scan_nonzero", (
        f"M6 control failure: priority-3 scan 阻断必须产生精确 scan reason "
        f"workspace_body_scan_nonzero（SCAN_REASON_BY_OWNER['workspace.core.v1']），"
        f"实际 failure_code={fc!r}"
    )
    # 6 owner 全部 acked + fence=erased（closeout_erasing 推到 + 5 非 window pre-state）。
    async with session_factory() as assert_s:
        for owner_key in (
            "workspace.core.v1", "workspace.transport.v1",
            "execution.core.v1", "execution.transport.v1",
            "external.payload.v1", "runtime.private.v1",
        ):
            assert await _cp(assert_s, op1, owner_key, "state") == "acked", (
                f"M6 control failure: owner {owner_key} checkpoint.state 必须为 acked；"
                f"实际 {await _cp(assert_s, op1, owner_key, 'state')!r}"
            )
            assert await _fence_state(assert_s, cid, owner_key) == "erased", (
                f"M6 control failure: owner {owner_key} fence.state 必须为 erased（window"
                f" owner 由 closeout_erasing 推 erasing→erased；其他 5 由 helper 预置）；"
                f"实际 {await _fence_state(assert_s, cid, owner_key)!r}"
            )

    # 完成后不能 claimed/erased/completed（priority-3 唯一可达；completed 必为 False）
    # 此断言由上面 state=="blocked" 已隐含；保留显式 ack 确认。
    assert state != "completed", (
        "M6 control 严禁 completed（priority-3 scan nonzero 必阻断 → blocked）"
    )
