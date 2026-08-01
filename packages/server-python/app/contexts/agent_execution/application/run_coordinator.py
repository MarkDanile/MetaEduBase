from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import (
    CreateRunCommand,
    NewRunEvent,
    RuntimeEventCommand,
)
from app.contexts.agent_execution.application.ports import (
    CapabilityBoundGuardState,
    DurableGuardState,
    FailClosedRunStartBarrier,
    GuardStatePort,
    RunStartBarrierPort,
)
from app.contexts.agent_execution.domain import (
    AgentRun,
    OutputPublishState,
    RunActorAnonymizedError,
    RunConflictError,
    RunEvent,
    RunGuardBlockedError,
    RunStatus,
    RuntimeBindingStatus,
    RuntimeSessionBinding,
    RunUsageSummary,
    TerminalResult,
    TurnInput,
    TurnInputKind,
    UnsupportedRunCapabilitiesError,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.execution_repository import (
    AgentExecutionRepository,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    RuntimeProfileModel,
)


@dataclass(frozen=True, slots=True)
class CreateRunResult:
    run: AgentRun
    created: bool


@dataclass(frozen=True, slots=True)
class RuntimeIngestResult:
    event: RunEvent | None
    acked_through_runtime_seq: int
    idempotent_replay: bool


class RunCoordinator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        guard_state: GuardStatePort | None = None,
        start_barrier: RunStartBarrierPort | None = None,
    ):
        self._repository = AgentExecutionRepository(session)
        self._guard_state = guard_state or CapabilityBoundGuardState()
        self._start_barrier = start_barrier or FailClosedRunStartBarrier()

    async def create_run(self, command: CreateRunCommand) -> CreateRunResult:
        definition = await self._repository.get_definition(
            tenant_id=command.tenant_id,
            definition_id=command.agent_definition_version_id,
        )
        profile = await self._repository.get_profile(
            tenant_id=command.tenant_id,
            profile_id=command.runtime_profile_id,
        )
        self._validate_catalog(command, definition=definition, profile=profile)
        assert profile is not None
        await self._validate_binding(command, profile=profile)
        self._validate_context_snapshot(command)
        creation_digest = self._creation_digest(command)
        now = await self._repository.database_now()
        run = AgentRun(
            id=command.run_id,
            tenant_id=command.tenant_id,
            conversation_id=command.conversation_id,
            queue_seq=command.queue_seq,
            root_input_message_id=command.root_input_message_id,
            parent_run_id=command.parent_run_id,
            agent_definition_version_id=command.agent_definition_version_id,
            runtime_profile_id=command.runtime_profile_id,
            runtime_binding_id=command.runtime_binding_id,
            creation_digest=creation_digest,
            status=RunStatus.QUEUED,
            status_revision=1,
            cancel_requested_revision=None,
            next_event_seq=1,
            first_available_event_seq=1,
            last_event_seq=0,
            event_log_complete=True,
            queued_at=now,
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
            created_by=command.created_by,
            # S3-B round-3 P2-3：完整投影冻结的 erased envelope（present + None）。
            actor_state="present",
            actor_identity_digest=None,
            correlation_id=command.correlation_id,
            runtime_capability_snapshot=command.runtime_capability_snapshot,
            run_config_snapshot=command.run_config_snapshot,
            context_snapshot_ref=command.context_snapshot_ref,
            context_snapshot_digest=command.context_snapshot_digest,
            context_snapshot_classification=command.context_snapshot_classification,
            budget_snapshot=command.budget_snapshot,
            usage_summary=RunUsageSummary(),
            created_at=now,
            updated_at=now,
        )
        root = TurnInput(
            id=uuid.uuid4(),
            tenant_id=command.tenant_id,
            run_id=command.run_id,
            ordinal=0,
            input_kind=TurnInputKind.ROOT,
            message_id=command.root_input_message_id,
            request_id=command.root_request_id,
            expected_runtime_epoch=None,
            context_digest=command.root_context_digest,
            created_by=command.created_by,
            # S3-B round-3 P2-3：完整投影冻结的 erased envelope（present + None）。
            actor_state="present",
            actor_identity_digest=None,
            created_at=now,
        )
        persisted, created = await self._repository.create_run_with_root(run, root)
        return CreateRunResult(run=persisted, created=created)

    async def start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
    ) -> tuple[AgentRun, RunEvent]:
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        allowed = await self._start_barrier.can_start(
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
            run_id=run_id,
            queue_seq=run.queue_seq,
        )
        if not allowed:
            raise RunConflictError("workspace start barrier is not satisfied")
        await self._guard_state.inspect(run)
        return await self._repository.start_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_revision=expected_revision,
        )

    async def transition_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: RunStatus,
        expected_revision: int,
        target_status: RunStatus,
        summary: str,
        cancel_intent_revision: int | None = None,
    ) -> tuple[AgentRun, RunEvent]:
        if target_status in {RunStatus.STARTING, RunStatus.RESUME_REQUIRED}:
            raise RunConflictError(
                "starting and resume_required transitions require owned commands"
            )
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        await self._guard_state.inspect(run)
        if (
            target_status is RunStatus.WAITING_INPUT
            and not run.runtime_capability_snapshot.input_requests
        ):
            raise UnsupportedRunCapabilitiesError(
                "this Run cannot create HumanInputRequest state"
            )
        if (
            target_status is RunStatus.WAITING_APPROVAL
            and not run.runtime_capability_snapshot.approvals
        ):
            raise UnsupportedRunCapabilitiesError(
                "this Run cannot create ApprovalRequest state"
            )
        self._validate_summary(summary)
        return await self._repository.transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_revision=expected_revision,
            target_status=target_status,
            summary=summary,
            cancel_intent_revision=cancel_intent_revision,
        )

    async def mark_run_resume_required(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: RunStatus,
        expected_run_revision: int,
        expected_runtime_epoch: int,
        expected_binding_revision: int,
        summary: str,
    ) -> tuple[AgentRun, RunEvent, RuntimeSessionBinding]:
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        await self._guard_state.inspect(run)
        if (
            not run.runtime_capability_snapshot.resume
            or run.runtime_binding_id is None
        ):
            raise UnsupportedRunCapabilitiesError(
                "this Run cannot enter Runtime resume state"
            )
        self._validate_summary(summary)
        return await self._repository.mark_run_resume_required(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_run_revision=expected_run_revision,
            expected_runtime_epoch=expected_runtime_epoch,
            expected_binding_revision=expected_binding_revision,
            summary=summary,
        )

    async def resume_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_run_revision: int,
        expected_runtime_epoch: int,
        expected_binding_revision: int,
        runtime_session_ref: str,
        summary: str,
    ) -> tuple[AgentRun, RunEvent, RuntimeSessionBinding]:
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        await self._guard_state.inspect(run)
        if (
            not run.runtime_capability_snapshot.resume
            or run.runtime_binding_id is None
        ):
            raise UnsupportedRunCapabilitiesError(
                "this Run cannot resume a Runtime session"
            )
        self._validate_summary(summary)
        return await self._repository.resume_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_run_revision=expected_run_revision,
            expected_runtime_epoch=expected_runtime_epoch,
            expected_binding_revision=expected_binding_revision,
            runtime_session_ref=runtime_session_ref,
            summary=summary,
        )

    async def append_event(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        event: NewRunEvent,
    ) -> RunEvent:
        return await self._repository.append_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event=event,
        )

    async def ingest_runtime_event(
        self, command: RuntimeEventCommand
    ) -> RuntimeIngestResult:
        event, ack, replay = await self._repository.ingest_runtime_event(
            frame=command.frame,
            stream_id=command.stream_id,
            event=command.event,
        )
        return RuntimeIngestResult(
            event=event,
            acked_through_runtime_seq=ack,
            idempotent_replay=replay,
        )

    async def commit_terminal(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: RunStatus,
        expected_revision: int,
        result: TerminalResult,
        cancel_intent_revision: int | None = None,
    ) -> tuple[AgentRun, RunEvent | None, bool]:
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        if not run.is_terminal:
            guard = await self._guard_state.inspect(run)
            self._require_terminal_guard(
                run=run,
                expected_status=expected_status,
                guard=guard,
            )
        return await self._repository.commit_terminal(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_revision=expected_revision,
            result=result,
            cancel_intent_revision=cancel_intent_revision,
        )

    async def reserve_cancel_intent(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
    ) -> tuple[AgentRun, bool]:
        return await self._repository.reserve_cancel_intent(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_revision=expected_revision,
        )

    async def require_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun:
        from app.contexts.agent_execution.domain import RunNotFoundError

        run = await self._repository.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise RunNotFoundError("Agent Run not found")
        return run

    async def require_live_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun:
        """S3-B round-3 P1-1：前置 live-actor 校验（RunActorAnonymizedError）。

        所有 replay/idempotency 入口（activate_turn/completed_turn/create replay
        /query/start/cancel）须先调用本方法，确保 tombstone Run 在任何 status
        分支前 fail closed（不返回 suppressed 投影，不进入重新投影流程）。
        """
        run = await self.require_run(tenant_id=tenant_id, run_id=run_id)
        if run.created_by is None:
            raise RunActorAnonymizedError(
                f"Agent Run {run_id} actor has been anonymized (tombstone); "
                "live actor required"
            )
        return run

    async def list_events(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[RunEvent]:
        await self.require_run(tenant_id=tenant_id, run_id=run_id)
        return await self._repository.list_events(tenant_id=tenant_id, run_id=run_id)

    @staticmethod
    def _validate_catalog(
        command: CreateRunCommand,
        *,
        definition: AgentDefinitionVersionModel | None,
        profile: RuntimeProfileModel | None,
    ) -> None:
        if definition is None or definition.status != "published":
            raise RunConflictError("published Agent definition not found")
        if profile is None or not profile.enabled:
            raise RunConflictError("enabled Runtime profile not found")
        capabilities = command.runtime_capability_snapshot
        config = command.run_config_snapshot
        if snapshot_digest(capabilities) != profile.capability_digest:
            raise RunConflictError("Runtime capability snapshot digest does not match profile")
        if (
            capabilities.runtime_kind != profile.runtime_kind
            or capabilities.adapter_key != profile.adapter_key
        ):
            raise RunConflictError("Runtime capability snapshot identity does not match profile")
        if (
            config.agent_definition_version_id != command.agent_definition_version_id
            or config.runtime_profile_id != command.runtime_profile_id
            or config.budget != command.budget_snapshot
        ):
            raise RunConflictError("Run config snapshot does not match selected identities")
        if capabilities.tool_calls or capabilities.input_requests or capabilities.approvals:
            raise UnsupportedRunCapabilitiesError(
                "E1 only accepts compatibility/read-only capability snapshots"
            )
        if command.queue_seq < 1:
            raise ValueError("Run queue sequence must be positive")
        RunCoordinator._validate_digest(
            command.root_context_digest, "root input context digest"
        )

    async def _validate_binding(
        self,
        command: CreateRunCommand,
        *,
        profile: RuntimeProfileModel,
    ) -> None:
        if profile.runtime_kind == "compatibility":
            if command.runtime_binding_id is not None:
                raise RunConflictError(
                    "compatibility Runs cannot carry Runtime session bindings"
                )
            return
        if command.runtime_binding_id is None:
            raise RunConflictError("native Runtime Runs require a session binding")
        binding = await self._repository.get_binding(
            tenant_id=command.tenant_id,
            binding_id=command.runtime_binding_id,
        )
        if (
            binding is None
            or binding.conversation_id != command.conversation_id
            or binding.runtime_profile_id != command.runtime_profile_id
            or binding.status is not RuntimeBindingStatus.ACTIVE
        ):
            raise RunConflictError(
                "Runtime binding does not match tenant/conversation/profile or status"
            )

    @staticmethod
    def _validate_context_snapshot(command: CreateRunCommand) -> None:
        values = (
            command.context_snapshot_ref,
            command.context_snapshot_digest,
            command.context_snapshot_classification,
        )
        if any(value is None for value in values) and any(
            value is not None for value in values
        ):
            raise RunConflictError("context snapshot ref/digest/classification is partial")
        if command.context_snapshot_ref is not None:
            if "://" in command.context_snapshot_ref or any(
                character.isspace() for character in command.context_snapshot_ref
            ):
                raise RunConflictError("context snapshot ref must be opaque")
            RunCoordinator._validate_digest(
                command.context_snapshot_digest or "", "context snapshot digest"
            )

    @staticmethod
    def _creation_digest(command: CreateRunCommand) -> str:
        return snapshot_digest(
            {
                "agent_definition_version_id": str(
                    command.agent_definition_version_id
                ),
                "budget_snapshot": command.budget_snapshot.model_dump(mode="json"),
                "context_snapshot_classification": (
                    command.context_snapshot_classification.value
                    if command.context_snapshot_classification is not None
                    else None
                ),
                "context_snapshot_digest": command.context_snapshot_digest,
                "context_snapshot_ref": command.context_snapshot_ref,
                "conversation_id": str(command.conversation_id),
                "correlation_id": str(command.correlation_id),
                "created_by": str(command.created_by),
                "parent_run_id": (
                    str(command.parent_run_id) if command.parent_run_id else None
                ),
                "queue_seq": command.queue_seq,
                "root_context_digest": command.root_context_digest,
                "root_input_message_id": str(command.root_input_message_id),
                "root_request_id": str(command.root_request_id),
                "run_config_snapshot": command.run_config_snapshot.model_dump(
                    mode="json"
                ),
                "run_id": str(command.run_id),
                "runtime_binding_id": (
                    str(command.runtime_binding_id)
                    if command.runtime_binding_id
                    else None
                ),
                "runtime_capability_snapshot": (
                    command.runtime_capability_snapshot.model_dump(mode="json")
                ),
                "runtime_profile_id": str(command.runtime_profile_id),
                "schema_version": 1,
                "tenant_id": str(command.tenant_id),
            }
        )

    @staticmethod
    def _require_terminal_guard(
        *,
        run: AgentRun,
        expected_status: RunStatus,
        guard: DurableGuardState,
    ) -> None:
        if (
            guard.active_tool_calls
            or guard.active_input_requests
            or guard.active_approvals
            or guard.outcome_unknown_tool_calls
        ):
            raise RunGuardBlockedError("active durable state blocks Run terminal")
        if expected_status is RunStatus.QUEUED and guard.runtime_invocation_exists:
            raise RunGuardBlockedError(
                "queued Run with a Runtime invocation cannot terminate directly"
            )
        if expected_status is RunStatus.RESUME_REQUIRED and guard.unused_grants:
            raise RunGuardBlockedError(
                "resume_required Run must revoke unused grants before terminal"
            )
        if run.status != expected_status:
            raise RunConflictError("terminal expected status does not match current Run")

    @staticmethod
    def _validate_digest(value: str, label: str) -> None:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"{label} must be lowercase SHA-256")

    @staticmethod
    def _validate_summary(summary: str) -> None:
        if not summary or len(summary) > 4_000:
            raise ValueError("transition summary must contain 1 to 4000 characters")
