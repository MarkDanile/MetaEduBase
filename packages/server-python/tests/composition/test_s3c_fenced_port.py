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
