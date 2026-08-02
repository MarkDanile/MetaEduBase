r"""S3-C writer fence 真实 PostgreSQL 反例。

R1-S3-C round-7 commit-19（P2-2 修正）：复审要求 e2e 覆盖真实路径。
- 不只取得 Guard 退出（round-6 hotfix-3 残留）。
- 不只用 mock（round-5 残留）。
- 不用 raw SQL INSERT agent_runs（commit-15 残留，schema 列不匹配）。
- 用真实 ``FencedExecutionPort`` + ``ConversationExecutionGuard`` +
  ``RunCoordinator.create_run``（完整 catalog setup）。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_execution.application.dto import RuntimeEventCommand
from app.contexts.agent_execution.domain import (
    RunConversationMismatchError,
    RunNotFoundError,
    RuntimeIngestIdentityMismatchError,
)
from app.contexts.agent_execution.domain.runtime_ingest import (
    RuntimeEventProvenance,
    RuntimeIngestFrame,
)
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


# ---------------------------------------------------------------------------
# P1-4：fenced_ingest_runtime_event frame 身份 fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fenced_ingest_runtime_event_rejects_outer_tenant_mismatch(
    session_factory,
) -> None:
    """outer ``tenant_id`` 与 ``frame.tenant_id`` 不一致 raise
    ``RuntimeIngestIdentityMismatchError``（P1-4 防 Runtime 通道跨 tenant 写）。
    """
    tenant_outer = uuid.uuid4()
    tenant_frame = uuid.uuid4()
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    frame = RuntimeIngestFrame(
        tenant_id=tenant_frame,  # 故意不一致
        conversation_id=conversation_id,
        run_id=run_id,
        runtime_profile_id=profile_id,
        provenance=RuntimeEventProvenance(
            binding_id=binding_id,
            runtime_epoch=1,
            runtime_seq=1,
            runtime_event_id=uuid.uuid4(),
        ),
        event_digest="a" * 64,
    )
    command = RuntimeEventCommand(
        frame=frame,
        stream_id=uuid.uuid4(),
        event=None,
    )
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RuntimeIngestIdentityMismatchError):
            await port.fenced_ingest_runtime_event(
                tenant_id=tenant_outer,
                conversation_id=conversation_id,
                run_id=run_id,
                command=command,
            )


# ---------------------------------------------------------------------------
# P2-2：真实 AgentBridgeDispatcher.dispatch_turn 走 fenced port（run_context_body 落库）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_turn_real_path_writes_run_context_checkpoint(
    db_session, session_factory
) -> None:
    """真实 ``AgentBridgeDispatcher.dispatch_turn`` 经 consume_turn_event 内建
    verdict + fenced_create_run advance，验证 fence.ingress_checkpoint 落库
    ``run_context_body`` watermark == run.queue_seq。

    R1-S3-C round-7 commit-20（P2-3）：复审要求覆盖生产 dispatch_turn 入口
    （不只 Guard + port 直调）。用 ``bootstrap_workspace`` + ``submit_turn``
    + ``AgentBridgeDispatcher.dispatch_turn`` 完整链路。
    """
    from app.composition.agent_control_plane import (
        AgentBridgeDispatcher,
        ConversationExecutionCoordinator,
    )
    from tests.contexts.agent_control_plane.helpers import (
        ACTOR_ID,
        TENANT_ID,
        bootstrap_workspace,
        turn_command,
    )

    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "trigger"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="s3c-e2e-dispatch"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None

    # 验证 fence.ingress_checkpoint 落库 run_context_body watermark == queue_seq
    async with session_factory() as verify:
        row = (
            await verify.execute(
                text(
                    "SELECT ingress_checkpoint FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND owner_key = :o"
                ),
                {
                    "t": TENANT_ID,
                    "c": conversation_id,
                    "o": "execution.core.v1",
                },
            )
        ).first()
        assert row is not None
        sources = (row[0] or {}).get("sources", {})
        assert "run_context_body" in sources
        assert sources["run_context_body"]["watermark"] == run.queue_seq


# ---------------------------------------------------------------------------
# P2-2：同 key 并发 Guard + fenced_* 不死锁（real port，same conversation）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_same_key_guard_completes_within_60s(
    session_factory,
) -> None:
    """3 个并发 ``ConversationExecutionGuard`` + ``FencedExecutionPort`` 任务
    在**同一** (tenant, conv) 上 60s 内完成（无死锁）。Guard 串行化同 key
    调用；advance_checkpoint 推进 run_event_payload watermark 1->2->3。

    R1-S3-C round-7 commit-20（P2-3）：复审要求同 key 竞争（非 3 个不同 Conv）。
    """
    from app.composition.agent_control_plane import ConversationExecutionGuard

    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async def advance_one() -> None:
        async with session_factory() as session, session.begin():
            await ConversationExecutionGuard().acquire(
                session, tenant_id=tenant_id, conversation_id=conversation_id
            )
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

    tasks = [asyncio.create_task(advance_one()) for _ in range(3)]
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=60
        )
    except TimeoutError:
        for t in tasks:
            t.cancel()
        pytest.fail("同 key 并发 60 秒内未完成（疑似 deadlock）")

    # 验证 watermark == 3（3 次串行 advance）
    async with session_factory() as verify:
        row = (
            await verify.execute(
                text(
                    "SELECT ingress_checkpoint FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND owner_key = :o"
                ),
                {"t": tenant_id, "c": conversation_id, "o": "execution.core.v1"},
            )
        ).first()
        assert row is not None
        sources = (row[0] or {}).get("sources", {})
        assert sources.get("run_event_payload", {}).get("watermark") == 3


# ---------------------------------------------------------------------------
# P2-2：erasing fence 拒 create（真实 PG 反例）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erasing_fence_rejects_fenced_create_run(session_factory) -> None:
    """non-active fence 下 ``require_active_fence`` 必须 raise
    ``LateBodyWriteRejectedError``（verdict unconditional）。"""
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await _force_fence_state(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
            new_state="erasing",
        )

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(LateBodyWriteRejectedError):
            await port.require_active_fence(
                tenant_id=tenant_id, conversation_id=conversation_id
            )


# ---------------------------------------------------------------------------
# P1-1：fenced_commit_terminal 跨 Conversation Run 归属 fail closed
# 用真实 RunCoordinator.create_run（完整 catalog setup，无 raw SQL）。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fenced_commit_terminal_rejects_cross_conversation_run(
    session_factory,
) -> None:
    """caller 传 conversation_A + run（属于 conversation_B）调
    ``fenced_commit_terminal`` 必须 raise ``RunConversationMismatchError``。

    P1-1 防跨 Conversation 写。用真实 ``RunCoordinator.create_run`` 创建 Run
    （完整 catalog setup），不用 raw SQL INSERT。
    """
    from dataclasses import replace

    from app.contexts.agent_execution.application.execution_identity_service import (
        ExecutionIdentityService,
    )
    from app.contexts.agent_execution.application.run_coordinator import (
        RunCoordinator,
    )
    from app.contexts.agent_workspace.application.conversation_service import (
        AgentWorkspaceService,
    )
    from tests.contexts.agent_execution.e1_helpers import make_run_command

    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        # Conversation A + B
        conv_a, _ = await AgentWorkspaceService(setup).create_conversation(
            tenant_id=tenant_id, actor_id=actor_id, title="conv A"
        )
        conv_b, _ = await AgentWorkspaceService(setup).create_conversation(
            tenant_id=tenant_id, actor_id=actor_id, title="conv B"
        )
        identity = await ExecutionIdentityService(setup).bootstrap_direct_rag(
            tenant_id=tenant_id, actor_id=actor_id
        )
        # Run 属于 Conversation B
        command = replace(
            make_run_command(
                identity, tenant_id=tenant_id, conversation_id=conv_b.conversation.id
            ),
            created_by=actor_id,
        )
        result = await RunCoordinator(setup).create_run(command)
        run_b = result.run

    # caller 传 conversation_A + run_B -> RunConversationMismatchError
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RunConversationMismatchError):
            await port.fenced_commit_terminal(
                tenant_id=tenant_id,
                conversation_id=conv_a.conversation.id,  # 故意传 A，Run 属于 B
                run_id=run_b.id,
                queue_seq=run_b.queue_seq,
                expected_status=run_b.status,
                expected_revision=run_b.status_revision,
                result=None,  # type: ignore[arg-type]
            )


@pytest.mark.asyncio
async def test_fenced_commit_terminal_rejects_cross_tenant_run(
    session_factory,
) -> None:
    """caller 传 tenant_A + run（属于 tenant_B）调
    ``fenced_commit_terminal`` -> ``require_run`` 找不到（tenant scoping）->
    ``RunNotFoundError``。

    P1-1 防跨 tenant 写：``require_run(tenant_id=A, run_id=run_in_B)`` 返回 None。
    """
    from dataclasses import replace

    from app.contexts.agent_execution.application.execution_identity_service import (
        ExecutionIdentityService,
    )
    from app.contexts.agent_execution.application.run_coordinator import (
        RunCoordinator,
    )
    from app.contexts.agent_workspace.application.conversation_service import (
        AgentWorkspaceService,
    )
    from tests.contexts.agent_execution.e1_helpers import make_run_command

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conv_b, _ = await AgentWorkspaceService(setup).create_conversation(
            tenant_id=tenant_b, actor_id=actor_id, title="conv B"
        )
        identity = await ExecutionIdentityService(setup).bootstrap_direct_rag(
            tenant_id=tenant_b, actor_id=actor_id
        )
        command = replace(
            make_run_command(
                identity, tenant_id=tenant_b, conversation_id=conv_b.conversation.id
            ),
            created_by=actor_id,
        )
        result = await RunCoordinator(setup).create_run(command)
        run_b = result.run

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RunNotFoundError):
            await port.fenced_commit_terminal(
                tenant_id=tenant_a,  # 故意传 A，Run 属于 B
                conversation_id=conv_b.conversation.id,
                run_id=run_b.id,
                queue_seq=run_b.queue_seq,
                expected_status=run_b.status,
                expected_revision=run_b.status_revision,
                result=None,  # type: ignore[arg-type]
            )
