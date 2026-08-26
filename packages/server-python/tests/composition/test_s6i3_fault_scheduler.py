"""R1-S6-I3 故障矩阵（scheduler / 跨 tenant 族）：F13 + F14。

契约：Plan §R1-S6-5（S6-F13 / S6-F14 行，已随 PR #581 并入 main）。
从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分的一部分；本文件
承载需要真实 scheduler（``ConversationPurgeScheduler``）的两行。

F1-F14 逐行映射（本文件承担的行）：
- F13 → ``test_f13_process_kill_equivalence_lease_expiry_takeover_single_writer``
- F14 → ``test_f14_cross_tenant_claim_takeover_zero_write_fail_closed``

helper 复用 ``test_s5_sch_a_claim_lease``（repo 跨测试 import 惯例）；并发用
composition ``session_factory``（NullPool，保证独立物理连接）。
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.composition.conversation_purge_scheduler import (
    ClaimKind,
    ConversationPurgeScheduler,
    RenewOutcomeKind,
    TakeoverOutcomeKind,
)
from tests.composition.test_s5_sch_a_claim_lease import (
    _assert_token,
    _claim,
    _expire_lease,
    _purge_rows,
    _seed_completed_facts,
    _seed_conversation,
)

pytestmark = pytest.mark.asyncio


async def test_f13_process_kill_equivalence_lease_expiry_takeover_single_writer(
    db_session, session_factory
):
    """F13: 进程级 kill（裁决四等价注入 = 租约过期 + 中途 raise + 双连接）。

    等价性域（限定，Plan §S6-5 F13）：只覆盖 DB 状态转移等价（事务回滚 / 租约
    到期 / token 失效），不覆盖 SIGKILL 独有现象（连接中断、半提交 TCP、会话内
    共享锁残留——登记生产门禁）。证明链：claim（epoch 1）后 holder「进程死」
    （不再 renew，连接弃用），其租约在 DB 层仍阻塞并发 takeover/claim
    （IN_LEASE / HELD，零分叉）；租约到期后新实例 takeover（epoch 2）+ 强制
    聚合完成；已死 holder 的旧 epoch-1 token 重放零写（STALE）。
    """

    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    await db_session.commit()

    # P1: claim（epoch 1），随后「进程死」（连接弃用，不再 renew）。
    async with session_factory() as s:
        first = await _claim(s, tid, cid)
        await s.commit()
    assert first.kind is ClaimKind.CLAIMED
    op_id = first.token.purge_operation_id
    assert first.token.lease_epoch == 1

    # 双连接并发（真实 NullPool 独立连接）：租约活跃期，第二实例 takeover 与
    # 第三实例重复 claim 均被已死 P1 的租约阻塞——零分叉单写者收敛。
    async def _premature_takeover():
        async with session_factory() as s:
            outcome = await ConversationPurgeScheduler(s).takeover(
                tenant_id=tid,
                conversation_id=cid,
                purge_operation_id=op_id,
                expected_lease_epoch=1,
            )
            await s.rollback()
            return outcome.kind

    async def _concurrent_claim():
        async with session_factory() as s:
            outcome = await _claim(s, tid, cid)
            await s.rollback()
            return outcome.kind

    premature_kind, dup_kind = await asyncio.gather(
        _premature_takeover(), _concurrent_claim()
    )
    # 已死 P1 的租约仍占 slot：takeover IN_LEASE、重复 claim HELD（均零写）。
    assert premature_kind is TakeoverOutcomeKind.IN_LEASE
    assert dup_kind is ClaimKind.HELD
    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1  # 零分叉
        assert rows[0]["lease_epoch"] == 1  # 并发尝试零写

    # P1 进程死 → 租约到期；新实例 P2 takeover（epoch 2）+ 强制聚合落库。
    async with session_factory() as s:
        await _seed_completed_facts(s, tid, cid, op_id)
        await _expire_lease(s, op_id)
        await s.commit()
    async with session_factory() as s:
        taken = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op_id,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert taken.kind is TakeoverOutcomeKind.TAKEN
    _assert_token(taken.token, op_id, 2)  # lease_epoch 单调 1→2

    # 已死 P1 旧 epoch-1 token 重放零写（STALE）；强制聚合已完成。
    async with session_factory() as s:
        stale = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op_id,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert stale.kind is RenewOutcomeKind.STALE
    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1, "takeover 不建新行"
        assert rows[0]["lease_epoch"] == 2, "旧 token 重放零写"
        assert rows[0]["state"] == "completed"
        conv = await verify.execute(
            text(
                "SELECT purge_state, purged_at FROM metaedu.agent_conversations "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        purge_state, purged_at = conv.one()
        assert purge_state == "completed"
        assert purged_at is not None


async def test_f14_cross_tenant_claim_takeover_zero_write_fail_closed(
    db_session, session_factory
):
    """F14: 跨 tenant / 伪造 ACK / revision 重放（复用 S4-F F-6 冻结机制）。

    主覆盖（复用，不在此重复实现）= test_s4f_fault_matrix.py F-6 族真实 PG 反例：
      - ``test_cross_tenant_forged_ack_fail_closed``（双 tenant 种子 + 伪造 ACK 重放）
      - ``test_operation_revision_replay_rejected``（revision 重放 CAS 拒绝）
      - ``test_owner_scope_mismatch_capability_gate``（owner scope 失配）
    本测试为 S6-I3 域薄 pin：scheduler claim/takeover 的 tenant 作用域
    （``_lock_conversation`` / ``_takeover_cas`` tenant 谓词）对跨 tenant 访问
    零写 fail-closed——claim 与 takeover 跨 tenant 均 ValueError，tenant A 的
    operation 不被 tenant B 身份触碰。
    """

    tid_a, cid_a = await _seed_conversation(db_session)
    await db_session.commit()
    async with session_factory() as s:
        first = await _claim(s, tid_a, cid_a)
        await s.commit()
    op_a = first.token.purge_operation_id

    tid_b, cid_b = await _seed_conversation(db_session)
    await db_session.commit()
    assert tid_a != tid_b and cid_a != cid_b

    # 跨 tenant claim：tenant B 身份访问 tenant A 的 conversation →
    # tenant-scoped lock miss → ValueError（零写）。
    async with session_factory() as s:
        with pytest.raises(ValueError, match="not found"):
            await ConversationPurgeScheduler(s).claim(
                tenant_id=tid_b,
                conversation_id=cid_a,
                retention_policy_snapshot={"conversation_recovery_days": 30},
            )
        await s.rollback()

    # 跨 tenant takeover：tenant B 作用域 CAS 命中不到 tenant A 的 op →
    # _lease_state_with_state 无匹配行 → ValueError（零写）。
    async with session_factory() as s:
        with pytest.raises(ValueError, match="not found"):
            await ConversationPurgeScheduler(s).takeover(
                tenant_id=tid_b,
                conversation_id=cid_b,
                purge_operation_id=op_a,
                expected_lease_epoch=1,
            )
        await s.rollback()

    # 双方隔离：op_a 仍 epoch 1 未变；tenant B 无新增 operation（零写）。
    async with session_factory() as verify:
        rows_a = await _purge_rows(verify, cid_a)
        assert len(rows_a) == 1 and rows_a[0]["lease_epoch"] == 1
        rows_b = await _purge_rows(verify, cid_b)
        assert rows_b == []
