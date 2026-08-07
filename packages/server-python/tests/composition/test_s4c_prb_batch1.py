r"""R1-S4-C PR-B 批次1：epoch 读锁序 + claim envelope / 六元 CAS。

契约：Plan §R1-S4-C C3/C4/R1（round-1~10 修订 + PR-A round-1/2 复审记录）。

批次1：
- **epoch 读锁序（PR-A P2 认知落地）**：`fenced_commit_terminal` 内
  `conversation_purge_revision`（Conversation FOR UPDATE）必须前置
  `require_active_fence`（owner/fence）——与 purge eraser
  （Conversation -> owner -> fence）同序；并发判别测试证明 epoch 读自持
  Conversation 锁（另一会话持有该行锁时 epoch 读阻塞）。
- **claim envelope 扩展 + Guard 内六元 CAS（C3）**：`Claimed*Event` 增
  conversation_id / producer_purge_revision；消费事务 `FOR UPDATE` 重读
  outbox 行后六元比对（turn/output 三源 row==envelope==event==Guard Conv）。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
)
from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import RunStatus, TerminalResult
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio


async def _terminal_result() -> TerminalResult:
    return TerminalResult(
        outcome="completed",
        code="success",
        reason="done",
        output_ref="obj-12345",
        output_digest="a" * 64,
        output_size=1,
        output_media_type="text/plain",
        output_classification="public",
        terminal_message_id=uuid.uuid4(),
    )


async def _run_to_running(
    session_factory, conversation_id, identity, launch, worker="prb-worker"
) -> object:
    """submit -> dispatch_turn(create) -> start -> running，返回 run。"""
    async with session_factory() as session, session.begin():
        coordinator = ConversationExecutionCoordinator(session)
        await coordinator.submit_turn(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            command=turn_command(identity, "prb batch1"),
            launch=launch,
        )
    run = await AgentBridgeDispatcher(session_factory, worker_id=worker).dispatch_turn()
    assert run is not None
    async with session_factory() as session, session.begin():
        coordinator = ConversationExecutionCoordinator(session)
        started, _ = await coordinator.start_run(
            tenant_id=TENANT_ID, run_id=run.id, expected_revision=1
        )
        await RunCoordinator(session).transition_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="acquired runtime lease",
        )
    return run


# ---------------------------------------------------------------------------
# epoch 读锁序：conversation_purge_revision 自持 Conversation 锁（R1/PR-A P2）
# ---------------------------------------------------------------------------


async def test_epoch_read_serializes_on_conversation_row_lock(session_factory):
    """epoch 读必须自持 Conversation FOR UPDATE 锁——另一会话持有该行锁时，
    fenced_commit_terminal 的 epoch 读应阻塞到释放（证明锁序 Conversation 在
    owner/fence 之前，与 purge eraser 同序）。
    """
    async with session_factory() as session, session.begin():
        conversation_id, identity, launch = await bootstrap_workspace(session)
    run = await _run_to_running(
        session_factory, conversation_id, identity, launch
    )
    result = await _terminal_result()

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 会话 A：持有 Conversation 行锁（模拟 purge eraser 锁序第一步）。
    held = asyncio.Event()
    release = asyncio.Event()

    async def hold_conversation_lock():
        async with factory() as session:
            row = (
                await session.execute(
                    select(ConversationModel)
                    .where(
                        ConversationModel.tenant_id == TENANT_ID,
                        ConversationModel.id == conversation_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            assert row is not None
            held.set()
            await release.wait()

    # 会话 B：fenced_commit_terminal（不预持 Conversation 锁）——epoch 读应
    # 阻塞在 A 持有的行锁上。
    completed = asyncio.Event()
    outcome: dict[str, object] = {}

    async def commit_terminal_without_prelock():
        try:
            async with factory() as session, session.begin():
                running = await RunCoordinator(session).require_run(
                    tenant_id=TENANT_ID, run_id=run.id
                )
                await FencedExecutionPort(session).fenced_commit_terminal(
                    tenant_id=TENANT_ID,
                    conversation_id=conversation_id,
                    run_id=run.id,
                    queue_seq=run.queue_seq,
                    expected_status=RunStatus.RUNNING,
                    expected_revision=running.status_revision,
                    result=result,
                )
            outcome["ok"] = True
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc
        finally:
            completed.set()

    holder = asyncio.create_task(hold_conversation_lock())
    await held.wait()
    committer = asyncio.create_task(commit_terminal_without_prelock())

    # B 应阻塞（epoch 读等 A 的行锁）；等一小段确认未完成。
    await asyncio.sleep(0.2)
    assert not completed.is_set(), (
        "fenced_commit_terminal completed despite Conversation row lock held — "
        "epoch read did not take the Conversation FOR UPDATE lock"
    )

    # 释放 A 锁 -> B 继续完成。
    release.set()
    await asyncio.wait_for(committer, timeout=10)
    await holder
    assert outcome.get("ok") is True, outcome.get("error")

    # 验证 outbox 带真实 epoch。
    async with factory() as session:
        from app.contexts.agent_execution.infrastructure.models import (
            ExecutionOutboxModel,
        )

        outbox = (
            await session.execute(
                select(ExecutionOutboxModel)
                .where(ExecutionOutboxModel.tenant_id == TENANT_ID)
                .limit(1)
            )
        ).scalar_one()
        conv = await session.get(ConversationModel, conversation_id)
        assert outbox.producer_purge_revision == conv.purge_revision
    await engine.dispose()
