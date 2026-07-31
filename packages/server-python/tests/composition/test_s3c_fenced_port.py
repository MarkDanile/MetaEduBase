"""S3-C M1a 单元测试：FencedExecutionPort.advance_run_event_checkpoint 反例。

删除 ``advance_run_event_checkpoint``（或绕过 ``FencedExecutionPort`` 直接调
``AgentErasureRepository.advance_ingress_checkpoint_for_update``）→ event 计数器
不推进 → ``run_event_payload`` source_key 的 ingress_checkpoint 仍为空，
purge scan 会误判 writer 路径未写过事件 → 复活旧反例。

本测试直接调 ``FencedExecutionPort.advance_run_event_checkpoint``（mock
``AgentErasureRepository.advance_ingress_checkpoint_for_update``）验证 fence
advance 路径被真实调用。
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_advance_run_event_checkpoint_invokes_repository() -> None:
    """advance_run_event_checkpoint 必须调用 advance_ingress_checkpoint_for_update。

    删除 advance 调用（mutation）→ run_event_payload source_key 计数器不推进，
    purge scan 误判 writer 路径未写过事件 → 旧 fence 行为复活。本测试 fail。
    """
    from app.composition.execution_fenced_port import FencedExecutionPort

    session = MagicMock()
    port = FencedExecutionPort(session)
    fence = MagicMock()
    fence.tenant_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    epoch = 0

    with patch(
        "app.contexts.agent_workspace.infrastructure.erasure_repository.advance_ingress_checkpoint_for_update"
    ) as mock_advance:
        async def _ok(*_a, **_kw):
            return None

        mock_advance.side_effect = _ok
        await port.advance_run_event_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            epoch=epoch,
        )
        mock_advance.assert_awaited_once()
        # advance 必须以 execution.core.v1 owner + run_event_payload source_key + watermark=0 调用
        _args, kwargs = mock_advance.call_args
        assert kwargs.get("owner_key") == FencedExecutionPort.EXECUTION_OWNER_KEY
        assert kwargs.get("source_key") == "run_event_payload"
        assert kwargs.get("watermark") == 0
        assert kwargs.get("epoch") == epoch
        assert kwargs.get("tenant_id") == fence.tenant_id
        assert kwargs.get("conversation_id") == conversation_id
