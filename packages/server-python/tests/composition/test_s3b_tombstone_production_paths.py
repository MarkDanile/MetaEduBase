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
    """构造 RunQueryService，mock _require_run_access 返回 (tombstoned_run, access)。

    验证 get_run/request_cancel/read_event_batch 遇 tombstone 必须 raise
    RunActorAnonymizedError。删除 service 内的 tombstone guard 后测试 fail。
    """
    access = MagicMock()
    service = RunQueryService(
        session=MagicMock(),
        conversation_access=MagicMock(),
    )
    # mock _require_run_access 返回 tombstoned run
    service._require_run_access = AsyncMock(return_value=(run, access))  # type: ignore[method-assign]
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

    通过源码静态检查（inspect）验证 except 链包含 RunActorAnonymizedError
    分支且转 DirectRagTerminalReplayError（确定性 gone/conflict），不被通用
    except 转 DirectRagTurnPendingError（暂态重试）。
    """

    def test_activate_turn_excepts_run_actor_anonymized_to_terminal_replay(self) -> None:
        import inspect

        from app.composition.direct_rag_compatibility import (
            DirectRagCompatibilityAdapter,
        )

        source = inspect.getsource(DirectRagCompatibilityAdapter.activate_turn)
        # 必须包含 RunActorAnonymizedError 捕获
        assert "RunActorAnonymizedError" in source, (
            "activate_turn must explicitly catch RunActorAnonymizedError"
        )
        # 必须转 DirectRagTerminalReplayError（确定性 gone）
        assert "DirectRagTerminalReplayError" in source, (
            "activate_turn must convert tombstone to DirectRagTerminalReplayError"
        )
        # 捕获分支必须在通用 except 之前（不被转 pending）
        anon_idx = source.index("except RunActorAnonymizedError")
        generic_except_idx = source.index("except Exception:")
        assert anon_idx < generic_except_idx, (
            "RunActorAnonymizedError handler must come before generic "
            "except Exception (otherwise tombstone becomes transient pending)"
        )
