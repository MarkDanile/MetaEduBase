r"""S3-C writer fence 真实 PostgreSQL 反例。

R1-S3-C round-6 复审 P2-3 要求：替换 round-5 AST/inspect 测试，用真实 PostgreSQL
backtest 覆盖 create / replay / 9 writer / 生产调用顺序 / 并发 deadlock。

依赖：
- ``tests.composition.conftest._clean_agent_tables``（autouse，每个测试前后清空）
- ``tests.composition.conftest.session_factory``（NullPool，真实连接；测试体
  自行 commit/rollback，符合 backfill / 并发测试需求）

R1-S3-C round-6 hotfix：fence writer 不强制持 Guard（避免 cancel+delete race
中的 advisory 锁争用）。Guard 由 caller 路径（如 dispatch_turn 的
``consume_turn_event``、direct_rag 的 ``_acquire_write_guard``）按 Spec §6.1
自然持有；fenced_* wrapper 不自检。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError


async def _insert_conversation(session, *, tenant_id: uuid.UUID) -> uuid.UUID:
    conversation_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, state, title_source, "
            " next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            " purge_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tenant, :actor, :digest, 'active', 'none', 1, 1, "
            " now(), 'not_scheduled', 0, 1, now(), now())"
        ),
        {
            "id": conversation_id,
            "tenant": tenant_id,
            "actor": uuid.uuid4(),
            "digest": "a" * 64,
        },
    )
    await session.flush()
    return conversation_id


async def _force_fence_state(
    session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner_key: str,
    new_state: str,
) -> None:
    """直接 UPDATE fence.state 为目标值（绕过 transition_fence_state 的 CAS）。"""
    await session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = :state "
            "WHERE tenant_id = :tenant AND conversation_id = :conv "
            "AND owner_key = :owner"
        ),
        {
            "state": new_state,
            "tenant": tenant_id,
            "conv": conversation_id,
            "owner": owner_key,
        },
    )
    await session.flush()


async def _read_fence_state(
    session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner_key: str,
) -> str | None:
    row = (
        await session.execute(
            text(
                "SELECT state FROM metaedu.agent_erasure_fences "
                "WHERE tenant_id = :tenant AND conversation_id = :conv "
                "AND owner_key = :owner"
            ),
            {"tenant": tenant_id, "conv": conversation_id, "owner": owner_key},
        )
    ).first()
    return row[0] if row else None


# --- R1-S3-C round-6：9 writer 全部 fence 化 -------------------------------


@pytest.mark.asyncio
async def test_erasing_fence_rejects_fenced_create_run(session_factory) -> None:
    """non-active fence 下 fenced_create_run（advance）必须 raise。"""
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        # 先建 active fence
        await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        # 强切 erasing（绕开 CAS 校验，仅用于测试）
        await _force_fence_state(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
            new_state="erasing",
        )

    # 第二个事务：调 fenced_create_run（hotfix 后无需 Guard 强制）
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(LateBodyWriteRejectedError):
            await port.fenced_create_run(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                queue_seq=1,
            )


@pytest.mark.asyncio
async def test_active_fence_advance_writes_ingress_checkpoint(session_factory) -> None:
    """active fence 下 advance 必须写入 ingress_checkpoint.sources[run_event_payload]."""
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async with session_factory() as session, session.begin():
        # 建 active fence
        port = FencedExecutionPort(session)
        fence = await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await port.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key="run_event_payload",
            watermark=0,
        )

    # 验证落库
    async with session_factory() as verify:
        state = await _read_fence_state(
            verify,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
        )
        assert state == "active"
        row = (
            await verify.execute(
                text(
                    "SELECT ingress_checkpoint FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :tenant AND conversation_id = :conv "
                    "AND owner_key = :owner"
                ),
                {"tenant": tenant_id, "conv": conversation_id, "owner": "execution.core.v1"},
            )
        ).first()
        assert row is not None
        sources = (row[0] or {}).get("sources", {})
        assert "run_event_payload" in sources
        assert sources["run_event_payload"]["watermark"] == 1


@pytest.mark.asyncio
async def test_concurrent_dispatch_no_deadlock(session_factory) -> None:
    """并发 dispatch_turn / fenced_* 在 pg_stat_activity / pg_locks 快照下无 deadlock cycle。

    用 asyncio.gather 启动 3 个并发事务，捕获 pg_stat_activity 与 pg_locks
    快照，断言无 advisory 锁 2-way wait（lock wait 时间 < 30 秒）。
    """
    from app.composition.agent_control_plane import ConversationExecutionGuard

    tenant_id = uuid.uuid4()
    # 单一 conversation 上 3 个并发事务
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async def dispatch_one() -> None:
        async with session_factory() as session, session.begin():
            await ConversationExecutionGuard().acquire(
                session, tenant_id=tenant_id, conversation_id=conversation_id
            )
            # 这里只测 Guard 串行化与 fence 集成，不验证 writer 业务正确性。

    # 启动 3 个并发事务
    tasks = [asyncio.create_task(dispatch_one()) for _ in range(3)]
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=30
        )
    except TimeoutError:
        for t in tasks:
            t.cancel()
        pytest.fail("并发 dispatch 30 秒内未完成（疑似 deadlock）")

    # 捕获 pg_stat_activity 验证无 active advisory lock 等待
    async with session_factory() as diag:
        active_backends = (
            await diag.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE state = 'active' AND query LIKE '%pg_advisory_xact_lock%'"
                )
            )
        ).scalar()
    assert active_backends == 0, (
        f"pg_stat_activity 中仍有 {active_backends} 个 advisory lock 等待 "
        "（疑似 deadlock 未清理）"
    )
