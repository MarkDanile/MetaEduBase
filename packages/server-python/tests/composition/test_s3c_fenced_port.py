"""S3-C fenced port 单元测试。

R1-S3-C round-6：
- 单元测试只覆盖 advance_checkpoint source_key/watermark 语义与 erasing fence
  verdict 契约。
- 删除 round-5 AST/inspect 测试（dispatch_turn / consume_turn_event 顺序）—
  生产时序由 ``tests/composition/test_s3c_writer_fence_e2e.py`` 真实 PostgreSQL
  反例覆盖。
- 删除 round-5 mock 测试（fenced_create_run / fenced_commit_terminal / fenced_stage
  wrapper 内部行为）— 同上，由真实 PostgreSQL 反例覆盖。
- 删除 round-6 _assert_guard_held 单元测试（hotfix 后移除该方法，避免在
  cancel+delete race 中引入额外 advisory 锁争用）。
- 保留 ``test_advance_checkpoint_uses_correct_source_key_and_watermark`` 与
  ``test_advance_checkpoint_event_counter_increments``（advance_checkpoint 是
  port 的核心 advance 原语，单测足够）。
- 保留 ``test_erasing_fence_rejects_create_via_verdict``（直接验证
  ``require_active_fence`` 在非 active fence 下 raise）。
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
    fence.conversation_id = uuid.uuid4()  # commit-13 _require_fence_identity
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}
    conversation_id = fence.conversation_id  # 必须与 fence 一致

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
    fence.conversation_id = uuid.uuid4()  # commit-13 _require_fence_identity
    fence.purge_revision = 0
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}

    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    await port.advance_checkpoint(
        fence=fence, conversation_id=fence.conversation_id,
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
async def test_erasing_fence_rejects_create_via_verdict() -> None:
    """erasing fence verdict 必须 raise LateBodyWriteRejectedError。"""
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_workspace.domain.errors import (
        LateBodyWriteRejectedError,
    )

    session = MagicMock()
    port = FencedExecutionPort(session)
    port._erasure.require_body_write_fence_for_update = AsyncMock(
        side_effect=LateBodyWriteRejectedError(
            "owner fence execution.core.v1 is erasing; body write rejected"
        )
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await port.require_active_fence(
            tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4()
        )
