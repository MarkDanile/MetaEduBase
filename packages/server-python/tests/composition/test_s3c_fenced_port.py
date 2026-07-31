"""S3-C M1a 单元测试：FencedExecutionPort.advance_run_event_checkpoint 反例。

删除 ``advance_run_event_checkpoint``（或绕过 ``FencedExecutionPort`` 直接调
``AgentErasureRepository.advance_ingress_checkpoint_for_update``）-> event 计数器
不推进 -> ``run_event_payload`` source_key 的 ingress_checkpoint 仍为空，
purge scan 会误判 writer 路径未写过事件 -> 复活旧反例。

本测试直接调 ``FencedExecutionPort.advance_run_event_checkpoint``（mock
``AgentErasureRepository.advance_ingress_checkpoint_for_update`` 实例方法）验证
fence advance 路径被真实调用且 watermark 递增正确。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_advance_run_event_checkpoint_invokes_repository() -> None:
    """advance_run_event_checkpoint 必须调用 advance_ingress_checkpoint_for_update。

    删除 advance 调用（mutation）-> run_event_payload source_key 计数器不推进，
    purge scan 误判 writer 路径未写过事件 -> 旧 fence 行为复活。本测试 fail。
    """
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.ingress_checkpoint = {"schema_version": 1, "sources": {}}
    conversation_id = uuid.uuid4()
    epoch = 0

    # mock 实例方法（非模块级函数）
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    await port.advance_run_event_checkpoint(
        fence=fence,
        conversation_id=conversation_id,
        epoch=epoch,
    )
    port._erasure.advance_ingress_checkpoint_for_update.assert_awaited_once()
    _args, kwargs = port._erasure.advance_ingress_checkpoint_for_update.call_args
    assert kwargs.get("owner_key") == FencedExecutionPort.EXECUTION_OWNER_KEY
    assert kwargs.get("source_key") == "run_event_payload"
    # baseline 0 -> first advance watermark = 0 + 1 = 1
    assert kwargs.get("watermark") == 1
    assert kwargs.get("epoch") == epoch
    assert kwargs.get("tenant_id") == fence.tenant_id
    assert kwargs.get("conversation_id") == conversation_id


@pytest.mark.asyncio
async def test_advance_increments_from_existing_watermark() -> None:
    """第二次 advance：existing watermark=1 -> advance watermark=2（current + 1）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    fence.ingress_checkpoint = {
        "schema_version": 1,
        "sources": {"run_event_payload": {"watermark": 1, "epoch": 0}},
    }
    port._erasure.advance_ingress_checkpoint_for_update = AsyncMock(return_value=None)
    await port.advance_run_event_checkpoint(
        fence=fence, conversation_id=uuid.uuid4(), epoch=0
    )
    _args, kwargs = port._erasure.advance_ingress_checkpoint_for_update.call_args
    assert kwargs.get("watermark") == 2, f"expected 2 (1+1), got {kwargs['watermark']}"
