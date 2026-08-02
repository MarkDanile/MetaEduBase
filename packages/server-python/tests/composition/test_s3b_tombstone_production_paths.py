"""S3-B round-5 P2-1：tombstone 生产路径直接反例测试。

删除 ``RunQueryService.get_run/request_cancel/read_event_batch`` 的 tombstone
guard（``if run.created_by is None: raise RunActorAnonymizedError``）后这些
测试 fail；删除 ``DirectRagCompatibilityAdapter.activate_turn`` 的
``RunActorAnonymizedError`` 透传后对应测试也 fail。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.contexts.agent_execution.application.run_query_service import (
    RunQueryService,
)
from app.contexts.agent_execution.domain import (
    AgentRun,
    OutputPublishState,
    RunActorAnonymizedError,
    RunStatus,
    RunUsageSummary,
)
from app.contexts.agent_execution.domain.snapshots import (
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RuntimeCapabilitySnapshot,
)


def _make_tombstoned_run() -> AgentRun:
    """S3-B round-3 P2-3：created_by=None + actor_state='redacted' + 64-hex digest。"""
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        queue_seq=1,
        root_input_message_id=uuid.uuid4(),
        parent_run_id=None,
        agent_definition_version_id=uuid.uuid4(),
        runtime_profile_id=uuid.uuid4(),
        runtime_binding_id=None,
        creation_digest="a" * 64,
        status=RunStatus.QUEUED,
        status_revision=1,
        cancel_requested_revision=None,
        next_event_seq=1,
        first_available_event_seq=1,
        last_event_seq=0,
        event_log_complete=True,
        queued_at=datetime(2026, 7, 30),
        started_at=None,
        ended_at=None,
        terminal_code=None,
        terminal_reason=None,
        terminal_result_digest=None,
        terminal_output_ref=None,
        terminal_output_digest=None,
        terminal_output_size=None,
        terminal_output_media_type=None,
        terminal_output_classification=None,
        terminal_message_id=None,
        output_publish_state=OutputPublishState.NOT_REQUIRED,
        created_by=None,  # tombstone
        actor_state="redacted",
        actor_identity_digest="a" * 64,
        correlation_id=uuid.uuid4(),
        runtime_capability_snapshot=RuntimeCapabilitySnapshot(
            runtime_kind="compatibility",
            adapter_key="compatibility",
            resume=False,
            steer=False,
            native_tools=False,
            tool_calls=False,
            input_requests=False,
            approvals=False,
            event_ack=False,
        ),
        run_config_snapshot=RunConfigSnapshot(
            agent_definition_version_id=uuid.uuid4(),
            runtime_profile_id=uuid.uuid4(),
            model_profile_key=None,
            autonomy_level=0,
            policy_version="1",
            tool_keys=(),
            budget=RunBudgetSnapshot(
                max_steps=1,
                max_wall_seconds=1,
                max_tokens=1,
                max_cost_micros=1,
                max_tool_calls=0,
                max_retries=0,
            ),
        ),
        context_snapshot_ref=None,
        context_snapshot_digest=None,
        context_snapshot_classification=None,
        budget_snapshot=RunBudgetSnapshot(
            max_steps=1,
            max_wall_seconds=1,
            max_tokens=1,
            max_cost_micros=1,
            max_tool_calls=0,
            max_retries=0,
        ),
        usage_summary=RunUsageSummary(),
        created_at=datetime(2026, 7, 30),
        updated_at=datetime(2026, 7, 30),
    )


def _make_service_with_tombstoned_run(run: AgentRun) -> RunQueryService:
    """构造 RunQueryService，mock _require_run_access + _repository.get_run 返回
    tombstoned_run。

    验证 get_run/request_cancel/read_event_batch 遇 tombstone 必须 raise
    RunActorAnonymizedError。删除 service 内的 tombstone guard 后测试 fail。

    R1-S3-C round-7 commit-17：request_cancel 不再调 _require_run_access
    （Guard 前置于 access resolution）；改为 mock _repository.get_run +
    _conversation_access.resolve。
    """
    access = MagicMock()
    service = RunQueryService(
        session=MagicMock(),
        conversation_access=MagicMock(),
        workspace_read=MagicMock(),
        guard=MagicMock(),
        fenced_writer=MagicMock(),
    )
    # get_run / read_event_batch 走 _require_run_access
    service._require_run_access = AsyncMock(return_value=(run, access))  # type: ignore[method-assign]
    # request_cancel 走 _repository.get_run + _conversation_access.resolve
    service._repository.get_run = AsyncMock(return_value=run)  # type: ignore[method-assign]
    service._conversation_access.resolve = AsyncMock(return_value=access)  # type: ignore[method-assign]
    return service


class TestRunQueryServiceTombstoneGuard:
    """删除 RunQueryService 三处 tombstone guard 后这些测试 fail。"""

    @pytest.mark.asyncio
    async def test_get_run_raises_on_tombstone(self) -> None:
        run = _make_tombstoned_run()
        service = _make_service_with_tombstoned_run(run)
        with pytest.raises(RunActorAnonymizedError):
            await service.get_run(
                tenant_id=run.tenant_id,
                actor_id=run.correlation_id,
                run_id=run.id,
            )

    @pytest.mark.asyncio
    async def test_request_cancel_raises_on_tombstone(self) -> None:
        run = _make_tombstoned_run()
        service = _make_service_with_tombstoned_run(run)
        with pytest.raises(RunActorAnonymizedError):
            await service.request_cancel(
                tenant_id=run.tenant_id,
                actor_id=run.correlation_id,
                run_id=run.id,
                expected_revision=1,
            )

    @pytest.mark.asyncio
    async def test_read_event_batch_raises_on_tombstone(self) -> None:
        run = _make_tombstoned_run()
        service = _make_service_with_tombstoned_run(run)
        with pytest.raises(RunActorAnonymizedError):
            await service.read_event_batch(
                tenant_id=run.tenant_id,
                actor_id=run.correlation_id,
                run_id=run.id,
                after_seq=0,
            )


class TestDirectRagActivateTurnTombstone:
    """activate_turn 遇 tombstone 必须 raise DirectRagTerminalReplayError，不能 pending。

    round-6 P2-1：动态调 activate_turn（mock AgentBridgeDispatcher + RunCoordinator
    令 dispatch_turn 成功 + require_live_run 抛 RunActorAnonymizedError），断言最终
    异常严格为 DirectRagTerminalReplayError（不是 DirectRagTurnPendingError 暂态重试）。
    删除该转换后测试 fail。
    """

    @pytest.mark.asyncio
    async def test_activate_turn_returns_terminal_replay_on_tombstone(self) -> None:
        """动态调 activate_turn：dispatch_turn 成功 → require_live_run 抛
        RunActorAnonymizedError → activate_turn 严格 raise
        DirectRagTerminalReplayError（不是 DirectRagTurnPendingError）。
        """
        from unittest.mock import patch

        from app.composition import direct_rag_compatibility as drc
        from app.composition.direct_rag_compatibility import (
            DirectRagCompatibilityAdapter,
            DirectRagTerminalReplayError,
            DirectRagTurnPendingError,
        )

        # 构造 adapter（绕开 __init__ 的真实依赖）
        adapter = DirectRagCompatibilityAdapter.__new__(DirectRagCompatibilityAdapter)
        adapter._session = MagicMock()
        adapter._session.rollback = AsyncMock()
        adapter._session_factory = MagicMock()

        # mock AgentBridgeDispatcher（dispatch_turn 成功）和 RunCoordinator
        # （require_live_run 抛 RunActorAnonymizedError）
        tombstone_error = drc.RunActorAnonymizedError("tombstoned")
        with patch.object(
            drc, "RunCoordinator"
        ) as mock_run_coordinator_cls, patch.object(
            drc, "AgentBridgeDispatcher"
        ) as mock_dispatcher_cls:
            mock_dispatcher = MagicMock()
            mock_dispatcher.dispatch_turn = AsyncMock(return_value=None)
            mock_dispatcher_cls.return_value = mock_dispatcher
            mock_coordinator = MagicMock()
            mock_coordinator.require_live_run = AsyncMock(side_effect=tombstone_error)
            mock_run_coordinator_cls.return_value = mock_coordinator

            # 构造最小 prepared turn
            prepared = drc.PreparedDirectRagTurn(
                tenant_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                recording=drc.DirectRagRecording(
                    conversation_id=uuid.uuid4(),
                    user_message_id=uuid.uuid4(),
                    run_id=uuid.uuid4(),
                    assistant_message_id=None,
                ),
                turn_event_id=uuid.uuid4(),
            )

            with pytest.raises(DirectRagTerminalReplayError) as exc_info:
                await adapter.activate_turn(prepared=prepared)
            # 严格断言：是 DirectRagTerminalReplayError，不是 DirectRagTurnPendingError
            assert not isinstance(
                exc_info.value, DirectRagTurnPendingError
            ), (
                "tombstone must be DirectRagTerminalReplayError (deterministic), "
                "NOT DirectRagTurnPendingError (transient pending retry)"
            )

            # 验证 dispatch_turn 被调（前置 step 成功）
            mock_dispatcher.dispatch_turn.assert_awaited_once()
            # 验证 RunCoordinator 构造（require_live_run 被调）
            mock_coordinator.require_live_run.assert_awaited_once()
