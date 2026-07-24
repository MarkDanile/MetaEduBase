from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import NewRunEvent
from app.contexts.agent_execution.domain import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_EVENT_TYPES,
    TERMINAL_RUN_STATUSES,
    AgentRun,
    EventVisibility,
    InvalidRuntimeProvenanceError,
    OutputPublishState,
    PersistedRuntimeReceipt,
    RunConflictError,
    RunEvent,
    RunEventConflictError,
    RunEventType,
    RunNotFoundError,
    RunStatus,
    RuntimeBindingStatus,
    RuntimeEventConflictError,
    RuntimeIngestAction,
    RuntimeIngestFrame,
    RuntimeSessionBinding,
    RuntimeStreamLeaseConflictError,
    TerminalResult,
    TerminalResultConflictError,
    TurnInput,
    TurnInputKind,
    UnsupportedRunCapabilitiesError,
    evaluate_runtime_ingest,
    require_run_transition,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.execution_mappers import (
    phase_content,
    run_values,
    terminal_content,
    to_binding,
    to_event,
    to_run,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    AgentRunModel,
    ExecutionOutboxModel,
    RunEventModel,
    RuntimeProfileModel,
    RuntimeSessionBindingModel,
    TurnInputModel,
)
from app.shared.schemas.agent_integration import (
    AssistantMessagePublishRequestedV1,
)
from app.shared.schemas.agent_integration_codec import (
    integration_event_digest,
    integration_event_payload,
)

_E1_UNSUPPORTED_ENTITY_EVENTS = frozenset(
    {
        RunEventType.TOOL_STARTED,
        RunEventType.TOOL_PROGRESS,
        RunEventType.TOOL_COMPLETED,
        RunEventType.TOOL_FAILED,
        RunEventType.TOOL_OUTCOME_UNKNOWN,
        RunEventType.EVIDENCE_ADDED,
        RunEventType.EVIDENCE_CONFLICT,
        RunEventType.APPROVAL_REQUESTED,
        RunEventType.APPROVAL_RESOLVED,
        RunEventType.APPROVAL_EXPIRED,
        RunEventType.INPUT_REQUESTED,
        RunEventType.INPUT_RESOLVED,
        RunEventType.ARTIFACT_CREATED,
        RunEventType.ARTIFACT_UPDATED,
        RunEventType.MESSAGE_PUBLISH_REQUESTED,
        RunEventType.MESSAGE_PUBLISHED,
    }
)

_CONTROL_OWNED_EVENT_TYPES = frozenset(
    {
        RunEventType.RUN_STARTED,
        RunEventType.RUN_RESUME_REQUIRED,
        *TERMINAL_EVENT_TYPES,
    }
)


def _validate_observation_event(event: NewRunEvent) -> None:
    payload = event.content.payload_inline
    if payload is None:
        if event.event_type is RunEventType.PHASE_CHANGED:
            raise RunEventConflictError(
                "observation phase events require an inspectable inline payload"
            )
        return
    if payload.status_from is not None or payload.status_to is not None:
        raise RunEventConflictError(
            "observation events cannot claim Agent Run status transitions"
        )


class AgentExecutionRepository:
    """Tenant-scoped durable Run/Event store. It never commits its session."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def database_now(self) -> datetime:
        from sqlalchemy import func

        return (
            await self._session.execute(select(func.clock_timestamp()))
        ).scalar_one()

    async def get_definition(
        self, *, tenant_id: uuid.UUID, definition_id: uuid.UUID
    ) -> AgentDefinitionVersionModel | None:
        return (
            await self._session.execute(
                select(AgentDefinitionVersionModel).where(
                    AgentDefinitionVersionModel.tenant_id == tenant_id,
                    AgentDefinitionVersionModel.id == definition_id,
                )
            )
        ).scalar_one_or_none()

    async def get_profile(
        self, *, tenant_id: uuid.UUID, profile_id: uuid.UUID
    ) -> RuntimeProfileModel | None:
        return (
            await self._session.execute(
                select(RuntimeProfileModel).where(
                    RuntimeProfileModel.tenant_id == tenant_id,
                    RuntimeProfileModel.id == profile_id,
                )
            )
        ).scalar_one_or_none()

    async def get_binding(
        self, *, tenant_id: uuid.UUID, binding_id: uuid.UUID
    ) -> RuntimeSessionBinding | None:
        row = (
            await self._session.execute(
                select(RuntimeSessionBindingModel).where(
                    RuntimeSessionBindingModel.tenant_id == tenant_id,
                    RuntimeSessionBindingModel.id == binding_id,
                )
            )
        ).scalar_one_or_none()
        return to_binding(row) if row is not None else None

    async def create_run_with_root(
        self, run: AgentRun, root_input: TurnInput
    ) -> tuple[AgentRun, bool]:
        try:
            async with self._session.begin_nested():
                return await self._create_run_with_root(run, root_input)
        except IntegrityError as exc:
            cause = getattr(exc.orig, "__cause__", None)
            if getattr(cause, "constraint_name", None) != "uq_agent_turn_input_request":
                raise
            raise RunConflictError(
                "root input request id is already owned by another Run"
            ) from exc

    async def _create_run_with_root(
        self, run: AgentRun, root_input: TurnInput
    ) -> tuple[AgentRun, bool]:
        statement = (
            insert(AgentRunModel)
            .values(**run_values(run))
            .on_conflict_do_nothing(index_elements=[AgentRunModel.id])
            .returning(AgentRunModel.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        if inserted_id is not None:
            self._session.add(
                TurnInputModel(
                    id=root_input.id,
                    tenant_id=root_input.tenant_id,
                    run_id=root_input.run_id,
                    ordinal=root_input.ordinal,
                    input_kind=root_input.input_kind.value,
                    message_id=root_input.message_id,
                    request_id=root_input.request_id,
                    expected_runtime_epoch=root_input.expected_runtime_epoch,
                    context_digest=root_input.context_digest,
                    created_by=root_input.created_by,
                    created_at=root_input.created_at,
                )
            )
            await self._session.flush()
            return run, True
        row = await self._get_run_row(
            tenant_id=run.tenant_id, run_id=run.id, for_update=False
        )
        if row is None or row.creation_digest != run.creation_digest:
            raise RunConflictError("Run id is already used by another create command")
        existing_root = (
            await self._session.execute(
                select(TurnInputModel).where(
                    TurnInputModel.tenant_id == run.tenant_id,
                    TurnInputModel.run_id == run.id,
                    TurnInputModel.input_kind == TurnInputKind.ROOT.value,
                )
            )
        ).scalar_one_or_none()
        if (
            existing_root is None
            or existing_root.request_id != root_input.request_id
            or existing_root.message_id != root_input.message_id
            or existing_root.context_digest != root_input.context_digest
        ):
            raise RunConflictError("Run root input conflicts with the persisted command")
        return to_run(row), False

    async def get_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun | None:
        row = await self._get_run_row(
            tenant_id=tenant_id, run_id=run_id, for_update=False
        )
        return to_run(row) if row is not None else None

    async def start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
    ) -> tuple[AgentRun, RunEvent]:
        row, predecessors = await self._lock_start_prefix(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        self._require_status_revision(
            row,
            expected_status=RunStatus.QUEUED,
            expected_revision=expected_revision,
        )
        for predecessor in predecessors:
            if RunStatus(predecessor.status) not in TERMINAL_RUN_STATUSES:
                raise RunConflictError("an earlier Run is not terminal")
            if predecessor.output_publish_state not in {
                OutputPublishState.PUBLISHED.value,
                OutputPublishState.NOT_REQUIRED.value,
                OutputPublishState.SUPPRESSED.value,
            }:
                raise RunConflictError("an earlier Run output projection is unresolved")
        if row.runtime_binding_id is not None:
            binding = await self._require_binding_for_update(
                tenant_id=tenant_id,
                binding_id=row.runtime_binding_id,
            )
            if (
                binding.conversation_id != row.conversation_id
                or binding.runtime_profile_id != row.runtime_profile_id
                or binding.status != RuntimeBindingStatus.ACTIVE.value
            ):
                raise RunConflictError(
                    "Runtime binding is not active for the queued Run"
                )
        now = await self.database_now()
        row.status = RunStatus.STARTING.value
        row.status_revision += 1
        row.started_at = now
        row.updated_at = now
        event = await self._append_event_locked(
            row,
            NewRunEvent(
                event_type=RunEventType.RUN_STARTED,
                content=phase_content(
                    status_from=RunStatus.QUEUED,
                    status_to=RunStatus.STARTING,
                    summary="Agent Run acquired the conversation execution lease",
                ),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=row.correlation_id,
            ),
        )
        await self._session.flush()
        return to_run(row), event

    async def _lock_start_prefix(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> tuple[AgentRunModel, list[AgentRunModel]]:
        candidate = await self._get_run_row(
            tenant_id=tenant_id,
            run_id=run_id,
            for_update=False,
        )
        if candidate is None:
            raise RunNotFoundError("Agent Run not found")
        prefix = list(
            (
                await self._session.execute(
                    select(AgentRunModel)
                    .where(
                        AgentRunModel.tenant_id == tenant_id,
                        AgentRunModel.conversation_id == candidate.conversation_id,
                        AgentRunModel.queue_seq <= candidate.queue_seq,
                    )
                    .order_by(AgentRunModel.queue_seq)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalars()
        )
        row = next((item for item in prefix if item.id == run_id), None)
        if row is None or row.queue_seq != candidate.queue_seq:
            raise RunConflictError("Agent Run queue identity changed during start")
        return row, [item for item in prefix if item.queue_seq < row.queue_seq]

    async def transition_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: RunStatus,
        expected_revision: int,
        target_status: RunStatus,
        summary: str,
    ) -> tuple[AgentRun, RunEvent]:
        if target_status in TERMINAL_RUN_STATUSES:
            raise RunConflictError("terminal transitions require commit_terminal")
        if target_status in {RunStatus.STARTING, RunStatus.RESUME_REQUIRED}:
            raise RunConflictError(
                "starting and resume_required transitions require owned commands"
            )
        row = await self._require_run_for_update(tenant_id=tenant_id, run_id=run_id)
        self._require_status_revision(
            row,
            expected_status=expected_status,
            expected_revision=expected_revision,
        )
        require_run_transition(expected_status, target_status)
        now = await self.database_now()
        row.status = target_status.value
        row.status_revision += 1
        row.updated_at = now
        event_type = (
            RunEventType.RUN_RESUME_REQUIRED
            if target_status is RunStatus.RESUME_REQUIRED
            else RunEventType.PHASE_CHANGED
        )
        event = await self._append_event_locked(
            row,
            NewRunEvent(
                event_type=event_type,
                content=phase_content(
                    status_from=expected_status,
                    status_to=target_status,
                    summary=summary,
                ),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=row.correlation_id,
            ),
        )
        await self._session.flush()
        return to_run(row), event

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
        row = await self._require_run_for_update(tenant_id=tenant_id, run_id=run_id)
        self._require_status_revision(
            row,
            expected_status=expected_status,
            expected_revision=expected_run_revision,
        )
        require_run_transition(expected_status, RunStatus.RESUME_REQUIRED)
        if row.runtime_binding_id is None:
            raise RunConflictError("resume requires a Runtime binding")
        binding = await self._require_binding_for_update(
            tenant_id=tenant_id,
            binding_id=row.runtime_binding_id,
        )
        if (
            binding.runtime_profile_id != row.runtime_profile_id
            or binding.conversation_id != row.conversation_id
            or binding.current_epoch != expected_runtime_epoch
            or binding.revision != expected_binding_revision
            or binding.status != RuntimeBindingStatus.ACTIVE.value
        ):
            raise RunConflictError(
                "Runtime binding cannot enter resume_required at the expected revision"
            )
        now = await self.database_now()
        if (
            binding.active_stream_id is not None
            and binding.stream_lease_expires_at is not None
            and binding.stream_lease_expires_at > now
        ):
            raise RuntimeStreamLeaseConflictError(
                "a live ingest stream must expire before resume is required"
            )
        binding.status = RuntimeBindingStatus.RESUME_REQUIRED.value
        binding.active_stream_id = None
        binding.stream_lease_expires_at = None
        binding.revision += 1
        binding.updated_at = now
        row.status = RunStatus.RESUME_REQUIRED.value
        row.status_revision += 1
        row.updated_at = now
        event = await self._append_event_locked(
            row,
            NewRunEvent(
                event_type=RunEventType.RUN_RESUME_REQUIRED,
                content=phase_content(
                    status_from=expected_status,
                    status_to=RunStatus.RESUME_REQUIRED,
                    summary=summary,
                ),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=row.correlation_id,
            ),
        )
        await self._session.flush()
        return to_run(row), event, to_binding(binding)

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
        if not runtime_session_ref or len(runtime_session_ref) > 500:
            raise ValueError("runtime session ref must contain 1 to 500 characters")
        row = await self._require_run_for_update(tenant_id=tenant_id, run_id=run_id)
        self._require_status_revision(
            row,
            expected_status=RunStatus.RESUME_REQUIRED,
            expected_revision=expected_run_revision,
        )
        require_run_transition(RunStatus.RESUME_REQUIRED, RunStatus.STARTING)
        if row.runtime_binding_id is None:
            raise RunConflictError("resume requires a Runtime binding")
        binding = await self._require_binding_for_update(
            tenant_id=tenant_id,
            binding_id=row.runtime_binding_id,
        )
        if (
            binding.runtime_profile_id != row.runtime_profile_id
            or binding.conversation_id != row.conversation_id
            or binding.current_epoch != expected_runtime_epoch
            or binding.revision != expected_binding_revision
            or binding.status != RuntimeBindingStatus.RESUME_REQUIRED.value
        ):
            raise RunConflictError(
                "Runtime binding cannot resume at the expected epoch and revision"
            )
        now = await self.database_now()
        binding.runtime_session_ref = runtime_session_ref
        binding.status = RuntimeBindingStatus.ACTIVE.value
        binding.current_epoch += 1
        binding.next_expected_runtime_seq = 1
        binding.acked_through_runtime_seq = 0
        binding.active_stream_id = None
        binding.stream_lease_expires_at = None
        binding.revision += 1
        binding.updated_at = now
        row.status = RunStatus.STARTING.value
        row.status_revision += 1
        row.updated_at = now
        event = await self._append_event_locked(
            row,
            NewRunEvent(
                event_type=RunEventType.PHASE_CHANGED,
                content=phase_content(
                    status_from=RunStatus.RESUME_REQUIRED,
                    status_to=RunStatus.STARTING,
                    summary=summary,
                ),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=row.correlation_id,
            ),
        )
        await self._session.flush()
        return to_run(row), event, to_binding(binding)

    async def append_event(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID, event: NewRunEvent
    ) -> RunEvent:
        if event.event_type in TERMINAL_EVENT_TYPES:
            raise RunEventConflictError(
                "canonical terminal events require commit_terminal"
            )
        if event.event_type is RunEventType.RUNTIME_TERMINAL_OBSERVED:
            raise RunEventConflictError(
                "Runtime terminal observations require Runtime ingestion"
            )
        if event.event_type in _CONTROL_OWNED_EVENT_TYPES:
            raise RunEventConflictError(
                "Run lifecycle events require their owned coordinator command"
            )
        _validate_observation_event(event)
        row = await self._require_run_for_update(tenant_id=tenant_id, run_id=run_id)
        if RunStatus(row.status) in TERMINAL_RUN_STATUSES:
            raise RunEventConflictError("new events cannot be appended after Run terminal")
        result = await self._append_event_locked(row, event)
        await self._session.flush()
        return result

    async def ingest_runtime_event(
        self,
        *,
        frame: RuntimeIngestFrame,
        stream_id: uuid.UUID,
        event: NewRunEvent,
    ) -> tuple[RunEvent | None, int, bool]:
        if event.event_type in TERMINAL_EVENT_TYPES:
            raise RunEventConflictError(
                "Runtime frames cannot create canonical terminal events"
            )
        if event.event_type in _CONTROL_OWNED_EVENT_TYPES:
            raise RunEventConflictError(
                "Runtime frames cannot create control-plane lifecycle events"
            )
        _validate_observation_event(event)
        provenance = frame.provenance
        if provenance.binding_id is None:
            raise RunEventConflictError("Runtime ingestion requires native provenance")
        run_row = await self._require_run_for_update(
            tenant_id=frame.tenant_id, run_id=frame.run_id
        )
        binding_row = await self._require_binding_for_update(
            tenant_id=frame.tenant_id,
            binding_id=provenance.binding_id,
        )
        database_now = await self.database_now()
        if (
            binding_row.status != RuntimeBindingStatus.ACTIVE.value
            or binding_row.active_stream_id != stream_id
            or binding_row.stream_lease_expires_at is None
            or binding_row.stream_lease_expires_at <= database_now
        ):
            raise RuntimeStreamLeaseConflictError(
                "Runtime ingest stream does not own a live lease"
            )
        binding = to_binding(binding_row)
        if (
            run_row.conversation_id != binding.conversation_id
            or run_row.runtime_profile_id != frame.runtime_profile_id
            or run_row.runtime_binding_id != binding.id
        ):
            raise InvalidRuntimeProvenanceError(
                "runtime frame does not match the target Run binding"
            )
        receipt = None
        runtime_seq = provenance.runtime_seq
        if runtime_seq is None:
            raise RunEventConflictError("runtime_seq is required")
        if runtime_seq == binding.next_expected_runtime_seq:
            reused_event_id = (
                await self._session.execute(
                    select(RunEventModel.id).where(
                        RunEventModel.tenant_id == frame.tenant_id,
                        RunEventModel.runtime_binding_id == binding.id,
                        RunEventModel.runtime_epoch == provenance.runtime_epoch,
                        RunEventModel.runtime_event_id == provenance.runtime_event_id,
                    )
                )
            ).scalar_one_or_none()
            if reused_event_id is not None:
                raise RuntimeEventConflictError(
                    "runtime event id was reused for another sequence"
                )
        if runtime_seq <= binding.acked_through_runtime_seq:
            receipt_row = (
                await self._session.execute(
                    select(RunEventModel).where(
                        RunEventModel.tenant_id == frame.tenant_id,
                        RunEventModel.runtime_binding_id == binding.id,
                        RunEventModel.runtime_epoch == provenance.runtime_epoch,
                        RunEventModel.runtime_seq == runtime_seq,
                    )
                )
            ).scalar_one_or_none()
            if receipt_row is not None:
                receipt_values = (
                    receipt_row.runtime_profile_id,
                    receipt_row.runtime_binding_id,
                    receipt_row.runtime_epoch,
                    receipt_row.runtime_seq,
                    receipt_row.runtime_event_id,
                    receipt_row.runtime_event_digest,
                )
                if any(value is None for value in receipt_values):
                    raise RunEventConflictError(
                        "persisted Runtime receipt has incomplete provenance"
                    )
                assert receipt_row.runtime_profile_id is not None
                assert receipt_row.runtime_binding_id is not None
                assert receipt_row.runtime_epoch is not None
                assert receipt_row.runtime_seq is not None
                assert receipt_row.runtime_event_id is not None
                assert receipt_row.runtime_event_digest is not None
                receipt = PersistedRuntimeReceipt(
                    tenant_id=receipt_row.tenant_id,
                    run_id=receipt_row.run_id,
                    runtime_profile_id=receipt_row.runtime_profile_id,
                    binding_id=receipt_row.runtime_binding_id,
                    runtime_epoch=receipt_row.runtime_epoch,
                    runtime_seq=receipt_row.runtime_seq,
                    runtime_event_id=receipt_row.runtime_event_id,
                    event_digest=receipt_row.runtime_event_digest,
                )
        decision = evaluate_runtime_ingest(
            binding=binding,
            expected_run_id=run_row.id,
            frame=frame,
            persisted_receipt=receipt,
        )
        if decision.action is RuntimeIngestAction.IDEMPOTENT_REPLAY:
            return None, decision.acked_through_runtime_seq, True
        if RunStatus(run_row.status) not in ACTIVE_RUN_STATUSES:
            raise RunEventConflictError("new Runtime events require an active Run")
        result = await self._append_event_locked(
            run_row,
            event,
            runtime_profile_id=frame.runtime_profile_id,
            runtime_binding_id=binding.id,
            runtime_epoch=provenance.runtime_epoch,
            runtime_seq=runtime_seq,
            runtime_event_id=provenance.runtime_event_id,
            runtime_event_digest=frame.event_digest,
        )
        binding_row.acked_through_runtime_seq = runtime_seq
        binding_row.next_expected_runtime_seq = runtime_seq + 1
        binding_row.revision += 1
        binding_row.updated_at = database_now
        await self._session.flush()
        return result, runtime_seq, False

    async def commit_terminal(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: RunStatus,
        expected_revision: int,
        result: TerminalResult,
    ) -> tuple[AgentRun, RunEvent | None, bool]:
        digest = snapshot_digest(result.model_dump(mode="json"))
        row = await self._require_run_for_update(tenant_id=tenant_id, run_id=run_id)
        current_status = RunStatus(row.status)
        if current_status in TERMINAL_RUN_STATUSES:
            if row.terminal_result_digest == digest:
                return to_run(row), None, True
            raise TerminalResultConflictError(
                "terminal result conflicts with the persisted Run terminal"
            )
        self._require_status_revision(
            row,
            expected_status=expected_status,
            expected_revision=expected_revision,
        )
        target_status = RunStatus(result.outcome)
        require_run_transition(expected_status, target_status)
        now = await self.database_now()
        if expected_status is RunStatus.RESUME_REQUIRED:
            if row.runtime_binding_id is None:
                raise RunConflictError(
                    "resume_required terminal requires a Runtime binding"
                )
            binding = await self._require_binding_for_update(
                tenant_id=tenant_id,
                binding_id=row.runtime_binding_id,
            )
            if (
                binding.runtime_profile_id != row.runtime_profile_id
                or binding.conversation_id != row.conversation_id
                or binding.status != RuntimeBindingStatus.RESUME_REQUIRED.value
            ):
                raise RunConflictError(
                    "Runtime recovery intent is not open for this Run"
                )
            binding.status = RuntimeBindingStatus.CLOSED.value
            binding.active_stream_id = None
            binding.stream_lease_expires_at = None
            binding.revision += 1
            binding.updated_at = now
        row.status = target_status.value
        row.status_revision += 1
        row.ended_at = now
        row.terminal_code = result.code
        row.terminal_reason = result.reason
        row.terminal_result_digest = digest
        row.usage_summary = result.usage.model_dump(mode="json")
        if target_status is RunStatus.COMPLETED:
            assert result.output_ref is not None
            assert result.output_digest is not None
            assert result.output_size is not None
            assert result.output_media_type is not None
            assert result.output_classification is not None
            assert result.terminal_message_id is not None
            row.terminal_output_ref = result.output_ref
            row.terminal_output_digest = result.output_digest
            row.terminal_output_size = result.output_size
            row.terminal_output_media_type = result.output_media_type
            row.terminal_output_classification = result.output_classification.value
            row.terminal_message_id = result.terminal_message_id
            row.output_publish_state = OutputPublishState.PENDING.value
        row.updated_at = now
        event_type = {
            RunStatus.COMPLETED: RunEventType.RUN_COMPLETED,
            RunStatus.FAILED: RunEventType.RUN_FAILED,
            RunStatus.CANCELLED: RunEventType.RUN_CANCELLED,
            RunStatus.EXPIRED: RunEventType.RUN_EXPIRED,
        }[target_status]
        event = await self._append_event_locked(
            row,
            NewRunEvent(
                event_type=event_type,
                content=terminal_content(result),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=row.correlation_id,
            ),
        )
        if target_status is RunStatus.COMPLETED:
            assert row.terminal_message_id is not None
            assert row.terminal_output_ref is not None
            assert row.terminal_output_digest is not None
            assert row.terminal_output_size is not None
            assert row.terminal_output_media_type is not None
            assert row.terminal_output_classification is not None
            publish_event = AssistantMessagePublishRequestedV1(
                event_id=uuid.uuid4(),
                tenant_id=row.tenant_id,
                aggregate_id=row.id,
                conversation_id=row.conversation_id,
                run_id=row.id,
                message_id=row.terminal_message_id,
                reply_to_message_id=row.root_input_message_id,
                agent_definition_version_id=row.agent_definition_version_id,
                output_ref=row.terminal_output_ref,
                output_digest=row.terminal_output_digest,
                output_size=row.terminal_output_size,
                output_media_type=row.terminal_output_media_type,
                output_classification=cast(
                    Literal["public", "internal", "restricted"],
                    row.terminal_output_classification,
                ),
                correlation_id=row.correlation_id,
                causation_id=event.id,
                occurred_at=now,
            )
            self._session.add(
                ExecutionOutboxModel(
                    id=publish_event.event_id,
                    tenant_id=row.tenant_id,
                    event_type=publish_event.event_type,
                    schema_version=publish_event.schema_version,
                    aggregate_id=row.id,
                    aggregate_type=publish_event.aggregate_type,
                    payload_inline=integration_event_payload(publish_event),
                    payload_ref=None,
                    payload_digest=integration_event_digest(publish_event),
                    correlation_id=row.correlation_id,
                    causation_id=event.id,
                    status="pending",
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                )
            )
        await self._session.flush()
        return to_run(row), event, False

    async def list_events(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[RunEvent]:
        rows = (
            await self._session.execute(
                select(RunEventModel)
                .where(
                    RunEventModel.tenant_id == tenant_id,
                    RunEventModel.run_id == run_id,
                )
                .order_by(RunEventModel.seq)
            )
        ).scalars()
        return [to_event(row) for row in rows]

    async def _append_event_locked(
        self,
        run_row: AgentRunModel,
        event: NewRunEvent,
        *,
        runtime_profile_id: uuid.UUID | None = None,
        runtime_binding_id: uuid.UUID | None = None,
        runtime_epoch: int | None = None,
        runtime_seq: int | None = None,
        runtime_event_id: uuid.UUID | None = None,
        runtime_event_digest: str | None = None,
    ) -> RunEvent:
        persisted_at = await self.database_now()
        if event.event_type in _E1_UNSUPPORTED_ENTITY_EVENTS:
            raise UnsupportedRunCapabilitiesError(
                "E1 cannot emit events without their durable entity stores"
            )
        if event.correlation_id != run_row.correlation_id:
            raise RunEventConflictError(
                "RunEvent correlation does not match its Agent Run"
            )
        content = event.content
        row = RunEventModel(
            id=uuid.uuid4(),
            tenant_id=run_row.tenant_id,
            conversation_id=run_row.conversation_id,
            run_id=run_row.id,
            seq=run_row.next_event_seq,
            event_type=event.event_type.value,
            schema_version=1,
            occurred_at=event.occurred_at,
            persisted_at=persisted_at,
            visibility=event.visibility.value,
            classification=content.classification.value,
            payload_inline=(
                content.payload_inline.model_dump(mode="json")
                if content.payload_inline is not None
                else None
            ),
            payload_ref=content.payload_ref,
            payload_state=content.payload_state.value,
            payload_digest=content.payload_digest,
            payload_size=content.payload_size,
            media_type=content.media_type,
            expires_at=content.expires_at,
            runtime_profile_id=runtime_profile_id,
            runtime_binding_id=runtime_binding_id,
            runtime_epoch=runtime_epoch,
            runtime_seq=runtime_seq,
            runtime_event_id=runtime_event_id,
            runtime_event_digest=runtime_event_digest,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
        )
        self._session.add(row)
        run_row.last_event_seq = run_row.next_event_seq
        run_row.next_event_seq += 1
        run_row.updated_at = persisted_at
        await self._session.flush()
        return to_event(row)

    async def _get_run_row(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID, for_update: bool
    ) -> AgentRunModel | None:
        statement = select(AgentRunModel).where(
            AgentRunModel.tenant_id == tenant_id,
            AgentRunModel.id == run_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def _require_run_for_update(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRunModel:
        row = await self._get_run_row(
            tenant_id=tenant_id, run_id=run_id, for_update=True
        )
        if row is None:
            raise RunNotFoundError("Agent Run not found")
        return row

    async def _require_binding_for_update(
        self, *, tenant_id: uuid.UUID, binding_id: uuid.UUID
    ) -> RuntimeSessionBindingModel:
        row = (
            await self._session.execute(
                select(RuntimeSessionBindingModel)
                .where(
                    RuntimeSessionBindingModel.tenant_id == tenant_id,
                    RuntimeSessionBindingModel.id == binding_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise RunConflictError("Runtime binding not found")
        return row

    @staticmethod
    def _require_status_revision(
        row: AgentRunModel,
        *,
        expected_status: RunStatus,
        expected_revision: int,
    ) -> None:
        if row.status != expected_status.value or row.status_revision != expected_revision:
            raise RunConflictError(
                "Agent Run status or revision precondition failed"
            )
