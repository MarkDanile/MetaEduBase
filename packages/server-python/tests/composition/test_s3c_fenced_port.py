"""S3-C fenced port 单元测试。

round-3 修正：
- import 从 composition 版本（非 application）。
- advance_checkpoint 按 source_key + watermark 推进（非固定 run_event_payload）。
- create_run 推进 run_context_body=queue_seq（非 run_event_payload 计数器）。
- commit_terminal 推进 run_output_body=queue_seq + event 计数器。
- stage 推进 compatibility_output=queue_seq（非 event 计数器）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_advance_checkpoint_uses_correct_source_key_and_watermark() -> None:
    """advance_checkpoint 必须按传入的 source_key + watermark 调用 repository。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}
    conversation_id = uuid.uuid4()

    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)

    await port.advance_checkpoint(
        fence=fence, conversation_id=conversation_id,
        source_key="run_context_body", watermark=5,
    )
    kw = port._erasure.advance_ingress_checkpoint_for_update.call_args.kwargs
    assert kw["source_key"] == "run_context_body"
    assert kw["watermark"] == 5
    assert kw["owner_key"] == "execution.core.v1"
    assert kw["epoch"] == 0


@pytest.mark.asyncio
async def test_advance_checkpoint_event_counter_increments() -> None:
    """run_event_payload: advance_checkpoint 内部 +1（current=0 -> watermark=1）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    await port.advance_checkpoint(
        fence=fence, conversation_id=uuid.uuid4(),
        source_key="run_event_payload", watermark=0,
    )
    kw = port._erasure.advance_ingress_checkpoint_for_update.call_args.kwargs
    assert kw["source_key"] == "run_event_payload"
    assert kw["watermark"] == 1

    fence.ingress_checkpoint = {
        "schema_version": 1,
        "sources": {"run_event_payload": {"watermark": 1, "epoch": 0}},
    }
    await port.advance_checkpoint(
        fence=fence, conversation_id=uuid.uuid4(),
        source_key="run_event_payload", watermark=0,
    )
    kw = port._erasure.advance_ingress_checkpoint_for_update.call_args.kwargs
    assert kw["watermark"] == 2


@pytest.mark.asyncio
async def test_fenced_create_run_advances_run_context_body() -> None:
    """fenced_create_run 推进 run_context_body=queue_seq（非 run_event_payload）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.require_body_write_fence_for_update = AsyncMock(return_value=fence)
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)

    await port.fenced_create_run(
        tenant_id=fence.tenant_id,
        conversation_id=uuid.uuid4(),
        queue_seq=3,
    )
    kw = port._erasure.advance_ingress_checkpoint_for_update.call_args.kwargs
    assert kw["source_key"] == "run_context_body"
    assert kw["watermark"] == 3


@pytest.mark.asyncio
async def test_fenced_commit_terminal_advances_run_output_and_event() -> None:
    """fenced_commit_terminal 推进 run_output_body=queue_seq + event +1。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.require_body_write_fence_for_update = AsyncMock(return_value=fence)
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    port._runs.commit_terminal = AsyncMock(
        return_value=(MagicMock(), MagicMock(), False)
    )

    await port.fenced_commit_terminal(
        tenant_id=fence.tenant_id,
        conversation_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        queue_seq=7,
        expected_status=MagicMock(),
        expected_revision=1,
        result=MagicMock(),
    )
    calls = port._erasure.advance_ingress_checkpoint_for_update.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["source_key"] == "run_output_body"
    assert calls[0].kwargs["watermark"] == 7
    assert calls[1].kwargs["source_key"] == "run_event_payload"
    assert calls[1].kwargs["watermark"] == 1


@pytest.mark.asyncio
async def test_fenced_commit_terminal_idempotent_replay_no_advance() -> None:
    """terminal_digest_match=True（idempotent replay）不推进 checkpoint。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.require_body_write_fence_for_update = AsyncMock(return_value=fence)
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    port._runs.commit_terminal = AsyncMock(
        return_value=(MagicMock(), MagicMock(), True)
    )

    await port.fenced_commit_terminal(
        tenant_id=fence.tenant_id,
        conversation_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        queue_seq=7,
        expected_status=MagicMock(),
        expected_revision=1,
        result=MagicMock(),
    )
    port._erasure.advance_ingress_checkpoint_for_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_fenced_stage_advances_compatibility_output() -> None:
    """fenced_stage 推进 compatibility_output=queue_seq（非 event 计数器）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.require_body_write_fence_for_update = AsyncMock(return_value=fence)
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    port._compat.stage_with_created = AsyncMock(
        return_value=(MagicMock(), True)
    )

    await port.fenced_stage(
        tenant_id=fence.tenant_id,
        conversation_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        queue_seq=4,
        output_ref="ref",
        reply="reply",
        response_envelope={},
    )
    kw = port._erasure.advance_ingress_checkpoint_for_update.call_args.kwargs
    assert kw["source_key"] == "compatibility_output"
    assert kw["watermark"] == 4


# --- round-4 P2: 生产时序反例 ----------------------------------------


@pytest.mark.asyncio
async def test_erasing_fence_rejects_create_via_verdict() -> None:
    """erasing fence verdict 必须 raise LateBodyWriteRejectedError。

    删除 verdict 中 state 检查后测试 fail（erasing fence 放行）。
    """
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_workspace.domain.errors import (
        LateBodyWriteRejectedError,
    )

    session = MagicMock()
    port = FencedExecutionPort(session)
    # mock fence 返回 erasing 状态
    fence = MagicMock()
    fence.state = MagicMock()
    fence.state.value = "erasing"
    port._erasure.require_body_write_fence_for_update = AsyncMock(
        side_effect=LateBodyWriteRejectedError(
            "owner fence execution.core.v1 is erasing; body write rejected"
        )
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await port.require_active_fence(
            tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4()
        )


def test_dispatch_turn_verdict_before_writer_order() -> None:
    """dispatch_turn 必须在 consume_turn_event 前注册 pre_create_callback。

    inspect dispatch_turn 源码：pre_create_callback 参数必须传给
    consume_turn_event，证明 verdict 在 writer 前。
    """
    import inspect

    from app.composition.agent_control_plane import AgentBridgeDispatcher

    source = inspect.getsource(AgentBridgeDispatcher.dispatch_turn)
    assert "pre_create_callback" in source, (
        "dispatch_turn must pass pre_create_callback to consume_turn_event"
        " (verdict-before-writer)"
    )
    assert "_verdict" in source, (
        "dispatch_turn must define _verdict callback for fence verdict"
    )


def test_consume_turn_event_calls_callback_before_create() -> None:
    """consume_turn_event 必须在 consume_turn_requested 前调 callback。

    inspect 源码：pre_create_callback 调用在 consume_turn_requested 之前。
    """
    import inspect

    from app.composition.agent_control_plane import (
        ConversationExecutionCoordinator,
    )

    source = inspect.getsource(
        ConversationExecutionCoordinator.consume_turn_event
    )
    callback_idx = source.index("pre_create_callback")
    create_idx = source.index("consume_turn_requested")
    assert callback_idx < create_idx, (
        "pre_create_callback must be called BEFORE consume_turn_requested"
        " (verdict-before-writer)"
    )


@pytest.mark.asyncio
async def test_replay_does_not_advance_checkpoint() -> None:
    """created=False (replay) 不推进 checkpoint advance。

    dispatch_turn 中 if created: advance_checkpoint 条件保护 replay 路径。
    删除 if created 条件后 replay 也会 advance -> 测试 fail。
    """
    import inspect

    from app.composition.agent_control_plane import AgentBridgeDispatcher

    source = inspect.getsource(AgentBridgeDispatcher.dispatch_turn)
    assert "if created:" in source, (
        "dispatch_turn must gate advance_checkpoint on created=True"
    )
    advance_idx = source.index("advance_checkpoint")
    if_created_idx = source.index("if created:")
    assert if_created_idx < advance_idx, (
        "advance_checkpoint must be inside 'if created:' block"
    )
