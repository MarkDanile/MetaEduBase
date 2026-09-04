"""R1-S6-I3 故障矩阵 mutation evidence 增强测试（M-F2 conversation lock + M-F8 top-op lock）。

契约：Plan §R1-S6-5 S6-F2 + S6-F8 真实 PG 路径。

本文件包含两个 mutation evidence 增强测试，分别验证两类 row lock：

- M-F2（``test_mf2_lock_conversation_serializes_dual_claim``）：``_lock_conversation``
  跳过 FOR UPDATE → 双连接并发 ``claim`` 都能进入 claim 关键区，破坏单写者。
- M-F8（``test_mf8_top_operation_for_update_locks_existing_row``）：``_top_operation``
  跳过 FOR UPDATE → 第二连接在 existing operation 行锁等待时**不会** lock-timeout。

两个 mutation 影响不同 row lock 但同一业务结论（``agent_conversation_purges`` 表的单写者破缺）。
M-F2 测试用「双连接并发 claim 结果是双 CLAIMED」证明 M-F2 红；M-F8 测试用
「B 调 ``_top_operation`` 在 A 持锁时不 lock-timeout」证明 M-F8 红。两者**不**共享
同一断言。

执行路径真实（双 session 并发 + PG ``SET LOCAL lock_timeout`` + ``pytest.raises``）。
seed 走 ``test_s5_sch_a_claim_lease._seed_conversation`` 跨测试 import 惯例。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.conversation_purge_scheduler import (
    ClaimKind,
    ConversationPurgeScheduler,
)
from tests.composition.s6i3_seeds import _seed_operation
from tests.composition.test_s5_sch_a_claim_lease import _seed_conversation

# ruff: noqa: F401, F811  (pytest fixture imports + test signature reuse are intentional)
pytestmark = pytest.mark.asyncio


async def test_mf2_lock_conversation_serializes_dual_claim(session_factory):
    """M-F2 mutation evidence：``_lock_conversation`` 持锁串行化双连接并发 ``claim``。

    双连接 ``asyncio.gather`` ``ConversationPurgeScheduler.claim`` 同一 conversation
    （state=deleted + purge_after 已过期 + 无 active hold）→ 期望：一方 CLAIMED，
    另一 HELD（``_lock_conversation`` FOR UPDATE 持锁未释放 → 后到者被 claim 谓词
    / 事务锁阻塞为 HELD）。

    **M-F2 注入**（``_lock_conversation`` skip FOR UPDATE）：双连接均能进入
    ``_lock_conversation`` → 各自继续到 ``_top_operation``（仍 FOR UPDATE）→ 双方都
    查到 NULL → 双方各自 INSERT 新 operation 行 → 双 CLAIMED。

    单断言验证 M-F2 单独判别（**不**包括 M-F8）。
    """
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed, actor_state="redacted")

    async def _claim_one() -> ClaimKind:
        async with session_factory() as s:
            outcome = await ConversationPurgeScheduler(s).claim(
                tenant_id=tid,
                conversation_id=cid,
                retention_policy_snapshot={"conversation_recovery_days": 30},
            )
            await s.commit()
            return outcome.kind

    k1, k2 = await asyncio.gather(_claim_one(), _claim_one())
    kinds = {k1, k2}
    assert kinds == {ClaimKind.CLAIMED, ClaimKind.HELD}, (
        f"M-F2 mutation evidence: 双连接并发 claim 应收敛单写者（CLAIMED+HELD）; "
        f"实际 {kinds}。M-F2 注入 `_lock_conversation` 失锁 → 双 CLAIMED 单写者破缺。"
    )


async def test_mf8_top_operation_for_update_locks_existing_row(session_factory, db_session):
    """M-F8 mutation evidence：``_top_operation`` 真 FOR UPDATE 串行化（existing operation 行锁）。

    1. **既有的 existing purge operation**：通过公开 ``claim`` 入口创建并 commit 一条
       operation（真实 PG 路径；**禁止**「零 operation + ``_top_operation`` 返 None」
       作锁载体——锁持有依赖 row 存在）。
    2. **两个真实 PG session**：
       - **Session A** 开启事务 → 调 ``ConversationPurgeScheduler(a)._top_operation(tid, cid)``
         → 断言返回 existing operation → **保持事务不 commit**（持续持 row-level
         ``FOR UPDATE`` 锁）。
       - **Session B** ``SET LOCAL lock_timeout = '1s'`` → 调
         ``ConversationPurgeScheduler(b)._top_operation(tid, cid)``。
    3. **control 期望**：
       - B 因 A 持有的 ``agent_conversation_purges`` 行 FOR UPDATE 锁等待；
       - ``SET LOCAL lock_timeout = '1s'`` 触发 → SQLAlchemy 抛 ``OperationalError``；
       - 异常文本必须包含 ``lock timeout`` 或 SQLSTATE ``55P03``；
       - **不接受**任意异常冒充锁等待（harness 抑制）；
       - A rollback → 释放锁 → fresh session 再调 ``_top_operation`` 正常返回同一 operation。
    4. **mutant 期望**：
       - 删除 ``_top_operation`` 的 ``.with_for_update()`` 后，B **不**发生 lock-timeout；
       - ``pytest.raises`` 因未抛预期锁异常 → assertion failure → 测试转红 → 计 KILLED；
       - **不**宣称 M-F8 mutant 在公开 ``claim`` 路径产生双 INSERT（那是 M-F2 路径）；
       - 结论仅是：M-F8 违反冻结的 ``top_operation`` row-lock 契约。
    """
    # ---- Setup: 既有的 existing purge operation via 公开 claim() + commit
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed, actor_state="redacted")
        seed_out = await ConversationPurgeScheduler(seed).claim(
            tenant_id=tid,
            conversation_id=cid,
            retention_policy_snapshot={"conversation_recovery_days": 30},
        )
        await seed.commit()
        existing_op_id = seed_out.token.purge_operation_id
    assert existing_op_id is not None
    # Setup verify: existing operation is now visible
    async with session_factory() as verify:
        verify_op = await ConversationPurgeScheduler(verify)._top_operation(tid, cid)
        assert verify_op is not None and verify_op.id == existing_op_id
        await verify.rollback()

    # ---- Phase A: session A opens tx → calls _top_operation (holds FOR UPDATE)
    async with session_factory() as a:
        op_a = await ConversationPurgeScheduler(a)._top_operation(tid, cid)
        assert op_a is not None, (
            f"M-F8 control failure: existing operation should be returned by "
            f"_top_operation (existing_op_id={existing_op_id}); got {op_a!r}"
        )
        assert op_a.id == existing_op_id, (
            f"M-F8 control failure: expected op_id={existing_op_id}, got {op_a.id}"
        )

        # ---- Phase B: SET LOCAL lock_timeout='1s' → call _top_operation
        # control: B times out waiting for A's FOR UPDATE lock
        # mutant: B completes immediately (no FOR UPDATE)
        async with session_factory() as b:
            await b.execute(text("SET LOCAL lock_timeout = '1s'"))
            # control: raise DB-API 锁超时 (asyncpg.LockNotAvailableError wrapped as
            # DBAPIError；SQLSTATE 55P03 "lock timeout")；mutant: 无异常
            with pytest.raises(Exception) as exc_info:
                await ConversationPurgeScheduler(b)._top_operation(tid, cid)
            # control verify: 异常文本必须包含 "lock timeout" 或 SQLSTATE 55P03
            error_str = str(exc_info.value).lower()
            assert "lock timeout" in error_str or "55p03" in error_str, (
                f"M-F8 control failure: expected 'lock timeout' or SQLSTATE 55P03 "
                f"(control row-lock blocking); got: "
                f"{type(exc_info.value).__name__}: {exc_info.value}"
            )
        # A rollback to release lock
        await a.rollback()

    # ---- Verify lock released: fresh session can now read
    async with session_factory() as c:
        op_c = await ConversationPurgeScheduler(c)._top_operation(tid, cid)
        assert op_c is not None and op_c.id == existing_op_id, (
            f"M-F8 control failure: lock not released after A rollback; "
            f"fresh session read returned {op_c!r}"
        )
