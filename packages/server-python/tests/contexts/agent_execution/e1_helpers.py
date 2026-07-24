from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import (
    CreateRunCommand,
    NewRunEvent,
)
from app.contexts.agent_execution.application.execution_identity_service import (
    CompatibilityIdentity,
    ExecutionIdentityService,
)
from app.contexts.agent_execution.application.ports import DurableGuardState
from app.contexts.agent_execution.domain import (
    EventVisibility,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RunEventPayload,
    RunEventType,
    RuntimeCapabilitySnapshot,
    RuntimeSessionBinding,
    SnapshotClassification,
    inline_event_content,
    snapshot_digest,
)

TENANT_A = uuid.UUID("61000000-0000-0000-0000-000000000001")
TENANT_B = uuid.UUID("62000000-0000-0000-0000-000000000001")
ACTOR = uuid.UUID("61000000-0000-0000-0000-000000000002")

READONLY_NATIVE_CAPABILITIES = RuntimeCapabilitySnapshot(
    runtime_kind="pi",
    adapter_key="pi-sdk",
    resume=True,
    steer=True,
    native_tools=False,
    tool_calls=False,
    input_requests=False,
    approvals=False,
    event_ack=True,
)


class AllowStartBarrier:
    async def can_start(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool:
        return True


class StaticGuardState:
    def __init__(self, state: DurableGuardState | None = None):
        self._state = state or DurableGuardState()

    async def inspect(self, run) -> DurableGuardState:
        return self._state


def make_budget() -> RunBudgetSnapshot:
    return RunBudgetSnapshot(
        max_steps=20,
        max_wall_seconds=300,
        max_tokens=100_000,
        max_cost_micros=2_000_000,
        max_tool_calls=0,
        max_retries=2,
    )


def make_run_command(
    identity: CompatibilityIdentity,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    conversation_id: uuid.UUID | None = None,
    queue_seq: int = 1,
    run_id: uuid.UUID | None = None,
    runtime_profile_id: uuid.UUID | None = None,
    runtime_capabilities: RuntimeCapabilitySnapshot | None = None,
    runtime_binding_id: uuid.UUID | None = None,
) -> CreateRunCommand:
    profile_id = runtime_profile_id or identity.runtime_profile.id
    capabilities = runtime_capabilities or identity.capability_snapshot
    budget = make_budget()
    return CreateRunCommand(
        run_id=run_id or uuid.uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation_id or uuid.uuid4(),
        queue_seq=queue_seq,
        root_input_message_id=uuid.uuid4(),
        root_request_id=uuid.uuid4(),
        root_context_digest="a" * 64,
        parent_run_id=None,
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=profile_id,
        runtime_binding_id=runtime_binding_id,
        runtime_capability_snapshot=capabilities,
        run_config_snapshot=RunConfigSnapshot(
            agent_definition_version_id=identity.agent_definition_version.id,
            runtime_profile_id=profile_id,
            model_profile_key="model.readonly.v1",
            autonomy_level=1,
            policy_version="policy.v1",
            tool_keys=(),
            budget=budget,
        ),
        context_snapshot_ref=None,
        context_snapshot_digest=None,
        context_snapshot_classification=None,
        budget_snapshot=budget,
        created_by=ACTOR,
        correlation_id=uuid.uuid4(),
    )


def make_event(
    *,
    event_type: RunEventType = RunEventType.PLAN_SUMMARY,
    summary: str = "Durable execution event",
    correlation_id: uuid.UUID | None = None,
) -> NewRunEvent:
    return NewRunEvent(
        event_type=event_type,
        content=inline_event_content(
            RunEventPayload(summary=summary),
            classification=SnapshotClassification.INTERNAL,
        ),
        visibility=EventVisibility.USER,
        occurred_at=datetime.now(UTC),
        correlation_id=correlation_id or uuid.uuid4(),
    )


async def bootstrap_compatibility(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID = TENANT_A,
) -> CompatibilityIdentity:
    return await ExecutionIdentityService(session).bootstrap_direct_rag(
        tenant_id=tenant_id,
        actor_id=ACTOR,
    )


async def bootstrap_native_binding(
    session: AsyncSession,
    identity: CompatibilityIdentity,
    *,
    conversation_id: uuid.UUID,
) -> tuple[uuid.UUID, RuntimeSessionBinding, uuid.UUID]:
    service = ExecutionIdentityService(session)
    profile = await service.publish_runtime_profile(
        tenant_id=TENANT_A,
        profile_key="runtime.pi.readonly.e1.v1",
        runtime_kind="pi",
        adapter_key="pi-sdk",
        config_digest=snapshot_digest(
            {"profile_key": "runtime.pi.readonly.e1.v1", "schema_version": 1}
        ),
        capability_snapshot=READONLY_NATIVE_CAPABILITIES,
        enabled=True,
    )
    binding = await service.create_runtime_binding(
        tenant_id=TENANT_A,
        conversation_id=conversation_id,
        runtime_profile_id=profile.id,
    )
    binding = await service.activate_runtime_binding(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_session_ref=f"pi-e1-{conversation_id}",
        expected_revision=binding.revision,
    )
    stream_id = uuid.uuid4()
    binding = await service.claim_ingest_stream(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_profile_id=profile.id,
        runtime_epoch=binding.current_epoch,
        stream_id=stream_id,
        lease_seconds=300,
    )
    return profile.id, binding, stream_id
