"""R1-S6-I3 故障矩阵 mutation evidence 增强测试（M-F2/F8 双连接 claim 单写者）。

契约：Plan §R1-S6-5 S6-F2 + S6-F8 真实 PG 路径。

本测试针对 **mutation 注入 production helper 后必须 red** 的两项：
- M-F2：`_lock_conversation` 跳过 FOR UPDATE → 双连接都能进入 claim 关键区 → 单写者失效
- M-F8：`_select_top_purge_operation_for_update` 跳过 FOR UPDATE → 同上（两个
  并发连接均查到 NULL = 无 operation → 各创建新 operation → 双 CLAIMED）

两个 mutation 影响不同 row lock 但同一业务结论（双 CLAIMED = 单写者破缺）。本
测试**单断言**验证「双连接并发 claim 收敛为单写者」（期望 CLAIMED+HELD 组合）；
任一 mutation 注入后结论变成 (CLAIMED, CLAIMED) → 测试 red。

执行路径真实（双连接 asyncio.gather → ``ConversationPurgeScheduler.claim``）。
seed 走 ``test_s5_sch_a_claim_lease._seed_conversation`` 跨测试 import 惯例。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.conversation_purge_scheduler import (
    ClaimKind,
    ConversationPurgeScheduler,
)
from tests.composition.test_s5_sch_a_claim_lease import _seed_conversation

# ruff: noqa: F401, F811  (pytest fixture imports + test signature reuse are intentional)
pytestmark = pytest.mark.asyncio


async def test_f2_f8_dual_connection_claim_collapses_to_single_writer(session_factory):
    """F2 + F8 mutation evidence：双连接并发 claim 必须收敛为单写者。

    双连接 asyncio.gather ``ConversationPurgeScheduler.claim`` 同一 conversation
    （state=deleted + purge_after 已过期 + 无 active hold）→ 期望：一方 CLAIMED，
    另一 HELD（FOR UPDATE 持锁未释放 → 后到者被 claim 谓词/事务锁阻塞为 HELD）。

    **M-F2 注入** (``_lock_conversation` skip FOR UPDATE)：双连接均能进入
    ``_lock_conversation`` → 各自继续到 `_select_top_purge_operation_for_update`
    → 双方都查到 NULL → 双方各自 INSERT 新 operation 行 → 双 CLAIMED。

    **M-F8 注入** (``_select_top_purge_operation_for_update` skip FOR UPDATE)：
    双连接均能在无 FOR UPDATE 下查到 NULL → 同上双 CLAIMED。

    单断言 (期望 {CLAIMED, HELD}) 同时验证两项 mutation。
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
        f"F2/F8 mutation evidence: 双连接并发 claim 应收敛单写者（CLAIMED+HELD）; "
        f"实际 {kinds}。M-F2 注入 `_lock_conversation` 失锁 或 M-F8 注入 "
        f"`_select_top_purge_operation_for_update` 失锁 → 双 CLAIMED 单写者破缺。"
    )
