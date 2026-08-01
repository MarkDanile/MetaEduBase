"""S3-C fenced port 单元测试。

round-5 revert：
- 回退 round-4 verdict-before-writer（pre_create_callback 触发 CI 30+ 分钟
  挂起）；回到 round-3 顺序（verdict after writer in same txn）。
- 保留 round-4 erasing fence reject 用例（直接验证 require_active_fence）。
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


# --- round-5 revert P2: 生产时序反例（round-3 顺序） -------------------


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


def test_dispatch_turn_uses_fenced_create_run_after_writer() -> None:
    """dispatch_turn 必须在 consume_turn_event 之后调 fenced_create_run。

    inspect dispatch_turn 源码：round-3 顺序——writer 先 commit（同事务持
    Guard + Conversation 行锁），created=True 时再调 fenced_create_run
    （取 owner lock + advance run_context_body=queue_seq）。
    删除 fenced_create_run 调用会破坏 round-3 契约 → 测试 fail。
    """
    import ast
    import inspect
    import textwrap

    from app.composition.agent_control_plane import AgentBridgeDispatcher

    source = inspect.getsource(AgentBridgeDispatcher.dispatch_turn)
    tree = ast.parse(textwrap.dedent(source))
    func_body = tree.body[0]
    assert isinstance(func_body, (ast.FunctionDef, ast.AsyncFunctionDef))
    body_src = ast.unparse(func_body)
    # round-5 revert：dispatch_turn 函数体不再用 pre_create_callback
    # （verdict-before-writer）。注释里允许提及历史决策（explanation）；
    # 只检查函数体（unparse 后注释已剥离）。
    assert "pre_create_callback" not in body_src, (
        "dispatch_turn body must NOT pass pre_create_callback to consume_turn_event"
        " (round-5 reverted: verdict-after-writer in same txn; round-4"
        " callback caused Backend CI 30+ min hang)"
    )
    # round-3 顺序：consume_turn_event 先，fenced_create_run 在其后
    assert "fenced_create_run" in body_src, (
        "dispatch_turn must call fenced_create_run when created=True"
    )
    consume_idx = body_src.index("consume_turn_event")
    fenced_idx = body_src.index("fenced_create_run")
    assert consume_idx < fenced_idx, (
        "fenced_create_run must be called AFTER consume_turn_event"
        " (round-3 verdict-after-writer in same txn)"
    )


def test_consume_turn_event_signature_no_callback() -> None:
    """consume_turn_event 不再接受 pre_create_callback 参数。

    round-5 revert：consume_turn_event 回归原始签名（无 callback），所有
    verdict 推迟到 writer commit 之后。
    """
    import inspect

    from app.composition.agent_control_plane import (
        ConversationExecutionCoordinator,
    )

    sig = inspect.signature(
        ConversationExecutionCoordinator.consume_turn_event
    )
    assert "pre_create_callback" not in sig.parameters, (
        "consume_turn_event must NOT expose pre_create_callback"
        " (round-5 reverted; verdict happens in caller after writer commit)"
    )


def test_dispatch_turn_advance_only_when_created() -> None:
    """dispatch_turn 仅 created=True 时推进 checkpoint。

    round-3 顺序：consume_turn_event 返回 created；False（idempotent replay）
    不调 fenced_create_run，watermark 不动。
    删除 if created 条件后 replay 也会 advance → 测试 fail。
    """
    import ast
    import inspect
    import textwrap

    from app.composition.agent_control_plane import AgentBridgeDispatcher

    source = inspect.getsource(AgentBridgeDispatcher.dispatch_turn)
    tree = ast.parse(textwrap.dedent(source))
    func_body = tree.body[0]
    assert isinstance(func_body, (ast.FunctionDef, ast.AsyncFunctionDef))
    body_src = ast.unparse(func_body)
    assert "if created:" in body_src, (
        "dispatch_turn must gate fenced_create_run on created=True"
    )
    fenced_idx = body_src.index("fenced_create_run")
    if_created_idx = body_src.index("if created:")
    assert if_created_idx < fenced_idx, (
        "fenced_create_run must be inside 'if created:' block"
    )
