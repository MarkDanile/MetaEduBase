"""R1-S6-I3 故障矩阵（legal-hold × participant entry 交互）：F9。

契约：Plan §R1-S6-5（S6-F9 行，已随 PR #581 并入 main）。
从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分的一部分；本文件
承载 legal-hold × participant entry 交互。

F1-F14 逐行映射（本文件承担的行）：
- F9  → ``test_f9_create_before_entry_blocks_entry_fail_closed``
        + ``test_f9_entry_before_create_completes_then_create_lands``
- F10 → 已迁出至 ``test_s6i3_fault_f10.py``（settlement T1/T2 hold 推进路由表判别，
        TD-105 承接实现；本文件保留 F9 + 不再持有 F10 占位）。

helper 复用 ``test_s5i1_hold_revision_fencing``（repo 跨测试 import 惯例）；并发用
composition ``session_factory``（NullPool，独立物理连接）。
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.contexts.agent_workspace.domain.erasure import ErasureFenceState
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from tests.composition.test_s5i1_hold_revision_fencing import (
    _checkpoint_state,
    _conversation,
    _fence_state,
    _hold_revision,
    _operation_state,
    _participant,
    _seed_conversation,
    _seed_operation_and_checkpoint,
    _seed_workspace_fence,
)

pytestmark = pytest.mark.asyncio

_TIMEOUT = 15.0


async def test_f9_create_before_entry_blocks_entry_fail_closed(
    db_session, session_factory
):
    """F9（create-first leg）：hold create 先于 participant entry 提交 →
    entry 经 hold 快照校验 fail-closed（零写）。

    真实双连接锁阻塞并发（非 drift 预置）：连接 B 先 ``create_legal_hold`` 并
    **持有 Conversation 行锁不提交**，连接 A 的 entry 在 Conversation FOR UPDATE
    上真实阻塞；B 提交（hold_revision 0→1）后 A 的 entry 重读 drift →
    ``ValueError(hold_revision)``，正文/fence/checkpoint/operation 零变化。
    """
    tid, cid = await _seed_conversation(
        db_session, state="deleted", purge_revision=1, purge_state="scheduled"
    )
    await _seed_workspace_fence(db_session, tid, cid)
    operation_id, op_revision = await _seed_operation_and_checkpoint(
        db_session, tid, cid, purge_revision=1, hold_revision_snapshot=0
    )
    await db_session.commit()
    title_before = (await _conversation(db_session, cid)).title

    # 连接 B：create hold（持有 Conversation 锁，**不提交**）。
    b_session = session_factory()
    repo_b = AgentErasureRepository(b_session)
    await repo_b.create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="F9 create-first",
        actor_id=db_session.info.get("actor") or __import__("uuid").uuid4(),
    )
    # B 的事务现在持有 Conversation FOR UPDATE 锁（create_legal_hold 锁序首位）。

    entry_error: list[str] = []

    async def _entry():
        # 连接 A：entry 在 Conversation FOR UPDATE 上阻塞，直至 B 提交。
        async with session_factory() as a:
            participant = await _participant(a)
            try:
                await participant.erase_conversation_body(
                    tenant_id=tid,
                    conversation_id=cid,
                    purge_revision=1,
                    purge_operation_id=operation_id,
                    expected_operation_revision=op_revision,
                )
                await a.commit()
            except ValueError as exc:  # hold_revision drift fail-closed
                entry_error.append(str(exc))
                await a.rollback()

    entry_task = asyncio.create_task(_entry())
    # 给 entry 一个进入锁等待的窗口；确认其因 B 持锁而未立即完成。
    await asyncio.sleep(0.5)
    assert not entry_task.done(), "entry 应在 B 持锁期间阻塞（create-first）"
    # B 提交：hold_revision 0→1 落库，释放 Conversation 锁 → entry 继续。
    await b_session.commit()
    await asyncio.wait_for(entry_task, timeout=_TIMEOUT)
    await b_session.close()

    # entry 被 hold 快照校验 fail-closed 拒绝（drift raise），零写。
    assert entry_error and "hold_revision" in entry_error[0]
    async with session_factory() as verify:
        conv = await _conversation(verify, cid)
        assert conv.title == title_before  # 正文零复活/零清除
        assert conv.purged_at is None
        assert await _hold_revision(verify, cid) == 1
        assert await _fence_state(verify, cid) == ErasureFenceState.ACTIVE.value
        assert await _checkpoint_state(verify, operation_id) == "pending"
        assert await _operation_state(verify, operation_id) == "scheduled"


async def test_f9_entry_before_create_completes_then_create_lands(
    db_session, session_factory
):
    """F9（entry-first leg）：participant entry 先于 hold create 完成 →
    erase 完成（fence erased + checkpoint acked），随后 create 被放行并成功落库。

    确定性并发：连接 A 显式先取 Conversation FOR UPDATE（占锁，模拟 entry 先到达），
    连接 B 的 create 在锁上真实阻塞；A 完成 erase 并提交后 B 才被放行。

    语义边界（S5 真实行为，不冒充 settlement）：participant ``erase_conversation_body``
    只做正文清除 + fence erased + checkpoint acked，**不置** ``purged_at``（settlement
    归 coordinator）。故 entry 完成后 conversation 仍未 purge，create_legal_hold
    （守卫仅 ``purged_at IS NULL``，erasure_repository.py:1080）合法成功，
    hold_revision 0→1。冻结 F9 行仅约束 entry 结果（"entry 在 create 前 → 完成"），
    不要求 create 被拒——本测试断言 entry 完成 + create 串行化后成功落库。
    """
    tid, cid = await _seed_conversation(
        db_session, state="deleted", purge_revision=1, purge_state="scheduled"
    )
    await _seed_workspace_fence(db_session, tid, cid)
    operation_id, op_revision = await _seed_operation_and_checkpoint(
        db_session, tid, cid, purge_revision=1, hold_revision_snapshot=0
    )
    await db_session.commit()

    # 连接 A：显式先占 Conversation FOR UPDATE 锁（模拟 entry 先到达）。
    a_session = session_factory()
    await a_session.execute(
        text(
            "SELECT id FROM metaedu.agent_conversations "
            "WHERE tenant_id = :tid AND id = :cid FOR UPDATE"
        ),
        {"tid": tid, "cid": cid},
    )

    create_error: list[str] = []

    async def _create():
        # 连接 B：create 在 Conversation FOR UPDATE 上阻塞，直至 A 提交。
        async with session_factory() as b:
            repo = AgentErasureRepository(b)
            try:
                await repo.create_legal_hold(
                    tenant_id=tid,
                    conversation_id=cid,
                    reason_code="litigation",
                    purpose="F9 entry-first",
                    actor_id=__import__("uuid").uuid4(),
                )
                await b.commit()
            except ValueError as exc:  # 不应触发（entry-first 下 conversation 未 purge）
                create_error.append(str(exc))
                await b.rollback()

    create_task = asyncio.create_task(_create())
    await asyncio.sleep(0.5)
    assert not create_task.done(), "create 应在 A 占锁期间阻塞（entry-first）"

    # 连接 A：在同一事务内完成 erase（复用已占的 Conversation 锁），随后提交。
    participant = await _participant(a_session)
    outcome = await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    assert outcome.blocked is False
    await a_session.commit()  # 释放锁 → create 放行 → already-purged
    await asyncio.wait_for(create_task, timeout=_TIMEOUT)
    await a_session.close()

    # entry 完成（对照 create-first leg：本 leg entry 先完成，零 fail-closed）。
    async with session_factory() as verify:
        conv = await _conversation(verify, cid)
        assert conv.purged_at is None  # participant erase 不含 settlement purge
        assert await _fence_state(verify, cid) == ErasureFenceState.ERASED.value
        assert await _checkpoint_state(verify, operation_id) == "acked"
    # create 串行化后放行并成功落库：无错误、hold_revision 0→1（合法审计标记）。
    assert create_error == [], f"entry-first 下 create 不应报错: {create_error}"
    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 1
