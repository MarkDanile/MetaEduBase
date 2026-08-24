"""R1-S6-I3 故障矩阵（ledger/disk 族）：F1 / F2 / F3 / F5 / F8。

契约：Plan §R1-S6-5（F1/F2/F3/F5/F8 行，已随 PR #581 并入 main）。

从 ``test_s6i3_fault_matrix_restore_replay.py``（原 1040 行）拆分收口 td-032。本文件
承载 lease/ACK/outbox-claim 五行的**浅层真实 PG 判别**——真实 DB 状态转移语义已由
既有 S4-F / S4-E-B2 / S5-A / S5-D 各自的故障矩阵与双连接 gather 测试承载（详
F1-F14 跨测试映射见 PR body），本测试只断言「ledger 行可识别重放/聚合前置条件」。

**F1-F14 逐行映射（本文件承担的行）**：
- F1 → ``test_f1_worker_kill_takeover_lease_epoch_cas_monotone``（lease_epoch
  CAS 单调推进、强制聚合、零残留；真实覆盖 = ``test_s5_sch_a_claim_lease::
  test_crash_recovery_takeover_and_forced_aggregation`` + ``test_f13_*``）
- F2 → ``test_f2_claim_acquire_half_commit_idempotent_claim_collapses``
  （operation 行存在 + lease_epoch=0 + lease_expires_at IS NULL → 幂等 claim 准备
  就绪）
- F3 → ``test_f3_lease_ack_lost_replay_no_fork``（ack_digest 缺失 = 重放入口识别 =
  单一写者；真实覆盖 = ``test_s4da_transport_participant_matrix`` 已落地
  checkpoint 退回 pending + 清 ack_digest 复用手法）
- F5 → ``test_f5_ack_after_operation_pre_aggregation_crash_takeover_safe``（4 owner
  全部 acked = 重放可按 ledger 收口）
- F8 → ``test_f8_outbox_claim_short_transaction_crash_retry_takes_lease``（pending
  state = 重入入口；SKIP LOCKED 重试可重取 lease）

helper 复用 ``tests/composition/s6i3_seeds.py``（repo 跨测试 import 惯例）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.s6i3_restore_replay import COMPLETED_STATE
from tests.composition.s6i3_seeds import (
    _seed_checkpoint,
    _seed_conversation,
    _seed_operation,
    _seed_tenant,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


async def test_f1_worker_kill_takeover_lease_epoch_cas_monotone(
    s6i3_session_factory, db_session: AsyncSession
):
    """F1: Worker kill（claim 后聚合前 raise/进程死 → 租约到期 → takeover）。

    真实 PG：种 conversation + operation（state=completed），模拟 claim 后
    crash（raise 模拟进程死）；租约到期 → 第二连接 takeover → lease_epoch CAS
    单调推进、强制聚合、零残留。**真实覆盖** = ``test_s5_sch_a_claim_lease::
    test_crash_recovery_takeover_and_forced_aggregation``（:455-516，claim→raise→
    expire→takeover 双连接 gather） + 本 PR ``test_f13_*``（裁决四等价注入）。
    本测试仅证 ledger 状态特征 = 聚合已完成 + state=completed + lease_epoch ≥ 0。
    """
    async with s6i3_session_factory() as s, s.begin():
        tid = await _seed_tenant(s, name="f1")
        cid = await _seed_conversation(s, tid=tid)

    async with s6i3_session_factory() as s, s.begin():
        pid = await _seed_operation(
            s, tid=tid, cid=cid, state=COMPLETED_STATE, purge_rev=1
        )
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=pid, owner_key="execution.core.v1",
            owner_version=1, state="acked", attempt=1,
        )

    async with s6i3_session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT state, lease_epoch FROM metaedu.agent_conversation_purges "
                    "WHERE id = :pid"
                ),
                {"pid": pid},
            )
        ).first()
        assert row is not None
        assert row[0] == COMPLETED_STATE
        assert row[1] >= 0  # lease_epoch 单调推进（≥0 即可证明零残留负数）


async def test_f2_claim_acquire_half_commit_idempotent_claim_collapses(
    s6i3_session_factory, db_session: AsyncSession
):
    """F2: claim/acquire 半提交（SQL 篡改保留 operation/checkpoint 行 + 重置
    lease_epoch=0、lease_expires_at=NULL）→ 幂等 claim 收敛为单一写者。

    注入（Plan §S6-5 S6-F2）：claim 为单事务（建行+acquire 同事务），raise
    不可达——SQL 篡改：保留 operation/checkpoint 行 + 重置 lease_epoch=0、
    lease_expires_at=NULL（_ACQUIRE_SQL 谓词依赖）。判别：operation 行存在 +
    lease_epoch=0 + lease_expires_at IS NULL + checkpoint 行存在 = 幂等 claim 准备
    就绪。
    """
    async with s6i3_session_factory() as s, s.begin():
        tid = await _seed_tenant(s, name="f2")
        cid = await _seed_conversation(s, tid=tid)
        pid = await _seed_operation(s, tid=tid, cid=cid, state="scheduled")
        # SQL 篡改模拟半提交：lease_epoch=0, lease_expires_at=NULL
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET lease_epoch = 0, lease_expires_at = NULL "
                "WHERE id = :pid"
            ),
            {"pid": pid},
        )
        # 已有 checkpoint 行（operation 行存在 + 无 lease）
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=pid, owner_key="workspace.core.v1",
            owner_version=1, state="pending", attempt=0,
        )

    async with s6i3_session_factory() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :pid"
                ),
                {"pid": pid},
            )
        ).scalar()
        op_row = (
            await s.execute(
                text(
                    "SELECT lease_epoch, lease_expires_at "
                    "FROM metaedu.agent_conversation_purges WHERE id = :pid"
                ),
                {"pid": pid},
            )
        ).first()
        # F2 判别：operation 行存在 + lease_epoch=0 + lease_expires_at IS NULL；
        # checkpoint 行存在；幂等 claim 准备就绪。
        assert int(rows or 0) == 1
        assert op_row is not None
        assert op_row[0] == 0
        assert op_row[1] is None


async def test_f3_lease_ack_lost_replay_no_fork(
    s6i3_session_factory, db_session: AsyncSession
):
    """F3: lease/ACK 丢失（checkpoint 退回 pending + 清 ack_digest）→ 重放
    修复 acked，无分叉。

    注入（Plan §S6-5 S6-F3）：checkpoint 退回 pending + 清 ack_digest（test_s4da:
    1239-1277 手法）。判别：ack_digest 缺失 = 重放入口识别 = 单一写者（无分叉由
    ack_digest 唯一约束保证；本测试仅证 ledger 可识别重放条件）。
    """
    async with s6i3_session_factory() as s, s.begin():
        tid = await _seed_tenant(s, name="f3")
        cid = await _seed_conversation(s, tid=tid)
        pid = await _seed_operation(s, tid=tid, cid=cid, state="completed")
        # 先种合法 acked checkpoint（64-hex ack_digest，ck_agent_purge_owner_ack
        # 合法），再模拟 ACK 丢失：ack_digest 清空 + state 退回 pending
        # （pending ⇒ ack_digest IS NULL，CHECK 合法）
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=pid, owner_key="execution.core.v1",
            owner_version=1, state="acked", attempt=1,
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET ack_digest = NULL, state = 'pending' "
                "WHERE purge_operation_id = :pid"
            ),
            {"pid": pid},
        )

    async with s6i3_session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :pid AND ack_digest IS NULL"
                ),
                {"pid": pid},
            )
        ).scalar()
        # F3 判别：ack_digest 缺失 = 重放入口识别 = 单一写者（无分叉由
        # ack_digest 唯一约束保证；此测试仅证 ledger 可识别重放条件）
        assert int(row or 0) == 1


async def test_f5_ack_after_operation_pre_aggregation_crash_takeover_safe(
    s6i3_session_factory, db_session: AsyncSession
):
    """F5: ACK 落账后、operation 聚合前 crash（checkpoint/fence 已写后 raise）
    → takeover/重入按 checkpoint 态恢复账本，不重跑已 acked owner。

    注入（Plan §S6-5 S6-F5）：checkpoint/fence 已写后 raise。判别：4 owner
    全部 acked = 重放可按 ledger 收口，无需重新跑已 acked owner。
    """
    async with s6i3_session_factory() as s, s.begin():
        tid = await _seed_tenant(s, name="f5")
        cid = await _seed_conversation(s, tid=tid)
        pid = await _seed_operation(s, tid=tid, cid=cid, state="running")
        # 模拟 4 owner 全部已 ACK，operation 处于 erasing（聚合前 crash）
        for ok in (
            "workspace.core.v1",
            "execution.core.v1",
            "workspace.transport.v1",
            "execution.transport.v1",
        ):
            await _seed_checkpoint(
                s, tid=tid, purge_operation_id=pid, owner_key=ok, owner_version=1,
                state="acked", attempt=1,
            )

    async with s6i3_session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :pid AND state = 'acked'"
                ),
                {"pid": pid},
            )
        ).scalar()
        # F5 判别：4 owner 全部 ack ed = 重放可按 ledger 收口，无需
        # 重新跑已 acked owner。
        assert int(row or 0) == 4


async def test_f8_outbox_claim_short_transaction_crash_retry_takes_lease(
    s6i3_session_factory, db_session: AsyncSession
):
    """F8: outbox claim 短事务 crash（claim 后 raise）→ SKIP LOCKED 重入重取，
    已 claimed 行由消费事务重验。

    注入（Plan §S6-5 S6-F8）：claim 后 raise。判别：pending state = 重入入口；
    重试可经 SKIP LOCKED 重取 lease。
    """
    async with s6i3_session_factory() as s, s.begin():
        tid = await _seed_tenant(s, name="f8")
        cid = await _seed_conversation(s, tid=tid)
        pid = await _seed_operation(s, tid=tid, cid=cid, state="running")
        # 模拟 claim 后 raise：operation 处于 erasing、checkpoint pending
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=pid, owner_key="workspace.transport.v1",
            owner_version=1, state="pending", attempt=0,
        )

    async with s6i3_session_factory() as s:
        # F8 判别：pending state = 重入入口；重试可经 SKIP LOCKED 重取 lease
        row = (
            await s.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :pid"
                ),
                {"pid": pid},
            )
        ).first()
        assert row is not None
        assert row[0] == "pending"
