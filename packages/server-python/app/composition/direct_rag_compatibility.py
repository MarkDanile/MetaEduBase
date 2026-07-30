from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    ConversationExecutionGuard,
)
from app.contexts.agent_execution.application.compatibility_output_service import (
    CompatibilityOutputReader,
    CompatibilityOutputService,
)
from app.contexts.agent_execution.application.dto import NewRunEvent
from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_POLICY_VERSION,
    ExecutionIdentityService,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    EventVisibility,
    OutputPublishState,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RunEventPayload,
    RunEventType,
    RunNotFoundError,
    RunStatus,
    RunUsageSummary,
    SnapshotClassification,
    TerminalResult,
    inline_event_content,
)
from app.contexts.agent_workspace.application.bridge import (
    AgentWorkspaceBridgeService,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.domain import (
    ContentClassification,
    ConversationNotFoundError,
    Message,
    MessagePartType,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.infrastructure.database import get_advisory_claim_engine
from app.shared.schemas.agent_integration import (
    RunBudgetSnapshotV1,
    RunConfigSnapshotV1,
    RuntimeCapabilitySnapshotV1,
    TurnLaunchSpecV1,
)


class DirectRagResponse(Protocol):
    reply: str
    sources: list[EvidenceItem]


class DirectRagCompatibilityError(Exception):
    """Stable composition failure for the legacy compatibility producer."""


class DirectRagTerminalReplayError(DirectRagCompatibilityError):
    pass


class DirectRagOutputTooLargeError(DirectRagCompatibilityError):
    pass


class DirectRagTurnPendingError(DirectRagCompatibilityError):
    pass


class DirectRagExecutionPendingError(DirectRagCompatibilityError):
    pass


@dataclass(frozen=True, slots=True)
class DirectRagRecording:
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    run_id: uuid.UUID
    assistant_message_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class PreparedDirectRagTurn:
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    recording: DirectRagRecording
    replay_reply: str | None = None
    replay_sources: tuple[EvidenceItem, ...] = ()
    requires_output_publish: bool = False
    turn_event_id: uuid.UUID | None = None

    @property
    def is_completed_replay(self) -> bool:
        return self.replay_reply is not None


_DIRECT_RAG_BUDGET = RunBudgetSnapshot(
    max_steps=2,
    max_wall_seconds=300,
    max_tokens=100_000,
    max_cost_micros=2_000_000,
    max_tool_calls=1,
    max_retries=0,
)


class DirectRagCompatibilityAdapter:
    """Record legacy Direct RAG calls in the durable Agent control plane.

    This adapter is a compatibility producer, not an Agent Runtime. It reuses
    the Workspace/Execution inbox-outbox contracts and never creates a Runtime
    binding, ToolCall, Evidence entity, or hidden reasoning record.
    """

    def __init__(self, session: AsyncSession):
        self._session = session
        if session.bind is None:
            raise RuntimeError("Direct RAG compatibility requires a bound session")
        self._session_factory = async_sessionmaker(
            session.bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._claim_engine = (
            get_advisory_claim_engine(session.bind)
            if isinstance(session.bind, AsyncEngine)
            else None
        )

    async def prepare_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_message_id: uuid.UUID,
        message: str,
        context_window: int,
    ) -> PreparedDirectRagTurn:
        conversation_id = await self._resolve_conversation_id(
            tenant_id=tenant_id,
            actor_id=actor_id,
            requested_id=conversation_id,
        )

        identity = await ExecutionIdentityService(
            self._session
        ).bootstrap_direct_rag(tenant_id=tenant_id, actor_id=actor_id)
        run_config = RunConfigSnapshot(
            agent_definition_version_id=identity.agent_definition_version.id,
            runtime_profile_id=identity.runtime_profile.id,
            model_profile_key=None,
            autonomy_level=0,
            policy_version=DIRECT_RAG_POLICY_VERSION,
            tool_keys=(),
            budget=_DIRECT_RAG_BUDGET,
        )
        budget_v1 = RunBudgetSnapshotV1.model_validate(
            _DIRECT_RAG_BUDGET.model_dump(mode="json")
        )
        launch = TurnLaunchSpecV1(
            agent_definition_version_id=identity.agent_definition_version.id,
            runtime_profile_id=identity.runtime_profile.id,
            runtime_binding_id=None,
            runtime_capability_snapshot=RuntimeCapabilitySnapshotV1.model_validate(
                identity.capability_snapshot.model_dump(mode="json")
            ),
            run_config_snapshot=RunConfigSnapshotV1.model_validate(
                run_config.model_dump(mode="json")
            ),
            budget_snapshot=budget_v1,
        )
        command = TurnCommand(
            client_message_id=client_message_id,
            parts=(
                MessagePartInput(
                    type=MessagePartType.TEXT,
                    text=message,
                    format="plain_text",
                    classification=ContentClassification.INTERNAL,
                ),
            ),
            agent_definition_version_id=identity.agent_definition_version.id,
            client_options={"context_window": context_window},
        )
        coordinator = ConversationExecutionCoordinator(self._session)
        receipt = await coordinator.submit_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=command,
            launch=launch,
        )
        message_record = receipt.reserved.message
        assert message_record.requested_run_id is not None
        return PreparedDirectRagTurn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            recording=DirectRagRecording(
                conversation_id=conversation_id,
                user_message_id=message_record.id,
                run_id=message_record.requested_run_id,
                assistant_message_id=None,
            ),
            turn_event_id=receipt.event_id,
        )

    @asynccontextmanager
    async def execution_claim(self, *, prepared: PreparedDirectRagTurn):
        if prepared.is_completed_replay:
            yield
            return
        if self._claim_engine is None:
            raise DirectRagCompatibilityError(
                "Direct RAG execution claim requires an async engine"
            )
        key = self._execution_claim_key(prepared.recording.run_id)
        try:
            connection = await self._claim_engine.connect()
        except SQLAlchemyTimeoutError:
            raise DirectRagExecutionPendingError(
                "Direct RAG execution claim capacity is exhausted"
            ) from None
        acquired = False
        try:
            acquired = bool(
                await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:claim_key)"),
                    {"claim_key": key},
                )
            )
            await connection.commit()
            if not acquired:
                raise DirectRagExecutionPendingError(
                    "Direct RAG execution is already claimed"
                )
            yield
        finally:
            if acquired:
                try:
                    unlocked = bool(
                        await connection.scalar(
                            text("SELECT pg_advisory_unlock(:claim_key)"),
                            {"claim_key": key},
                        )
                    )
                    await connection.commit()
                    if not unlocked:
                        await connection.invalidate()
                except BaseException:
                    await connection.invalidate()
            await connection.close()

    async def activate_turn(
        self, *, prepared: PreparedDirectRagTurn
    ) -> PreparedDirectRagTurn:
        """Consume the committed turn outbox, then recover or start its Run."""
        if prepared.turn_event_id is None:
            raise DirectRagCompatibilityError("Direct RAG turn event is missing")
        await self._session.rollback()
        try:
            await AgentBridgeDispatcher(
                self._session_factory,
                worker_id="direct-rag-compatibility",
            ).dispatch_turn(event_id=prepared.turn_event_id)
            run = await RunCoordinator(self._session).require_run(
                tenant_id=prepared.tenant_id,
                run_id=prepared.recording.run_id,
            )
        except RunNotFoundError:
            raise DirectRagTurnPendingError(
                "Direct RAG turn is pending execution acceptance"
            ) from None
        except DirectRagCompatibilityError:
            raise
        except Exception:
            raise DirectRagTurnPendingError(
                "Direct RAG turn is pending execution acceptance"
            ) from None
        tenant_id = prepared.tenant_id
        actor_id = prepared.actor_id
        conversation_id = prepared.recording.conversation_id
        message_id = prepared.recording.user_message_id
        coordinator = ConversationExecutionCoordinator(self._session)

        if run.status is RunStatus.COMPLETED:
            if run.output_publish_state is not OutputPublishState.PUBLISHED:
                return PreparedDirectRagTurn(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    recording=DirectRagRecording(
                        conversation_id=conversation_id,
                        user_message_id=message_id,
                        run_id=run.id,
                        assistant_message_id=run.terminal_message_id,
                    ),
                    requires_output_publish=True,
                )
            assistant = await self._require_assistant_message(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                run_id=run.id,
            )
            return PreparedDirectRagTurn(
                tenant_id=tenant_id,
                actor_id=actor_id,
                recording=DirectRagRecording(
                    conversation_id=conversation_id,
                    user_message_id=message_id,
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                ),
                replay_reply=self._message_text(assistant),
                replay_sources=await self._replay_sources(
                    tenant_id=tenant_id, run_id=run.id
                ),
            )
        if run.status in {
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.EXPIRED,
        }:
            raise DirectRagTerminalReplayError(
                f"Direct RAG idempotency key belongs to a {run.status.value} Run"
            )
        if run.status is RunStatus.QUEUED:
            run, _ = await coordinator.start_run(
                tenant_id=tenant_id,
                run_id=run.id,
                expected_revision=run.status_revision,
            )
        if run.status is RunStatus.STARTING:
            run, _ = await RunCoordinator(self._session).transition_run(
                tenant_id=tenant_id,
                run_id=run.id,
                expected_status=RunStatus.STARTING,
                expected_revision=run.status_revision,
                target_status=RunStatus.RUNNING,
                summary="Legacy Direct RAG compatibility execution started",
            )
        if run.status is not RunStatus.RUNNING:
            raise DirectRagCompatibilityError(
                f"Direct RAG Run cannot execute from {run.status.value}"
            )
        return PreparedDirectRagTurn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            recording=DirectRagRecording(
                conversation_id=conversation_id,
                user_message_id=message_id,
                run_id=run.id,
                assistant_message_id=None,
            )
        )

    async def complete_turn(
        self,
        *,
        prepared: PreparedDirectRagTurn,
        response: DirectRagResponse,
    ) -> DirectRagRecording:
        if prepared.is_completed_replay:
            return prepared.recording
        await self._acquire_write_guard(prepared)
        run = await RunCoordinator(self._session).require_run(
            tenant_id=prepared.tenant_id,
            run_id=prepared.recording.run_id,
        )
        if run.status is RunStatus.COMPLETED:
            raise DirectRagTerminalReplayError(
                "another request already completed this Direct RAG Run"
            )
        if run.status is not RunStatus.RUNNING:
            raise DirectRagCompatibilityError(
                f"Direct RAG Run cannot complete from {run.status.value}"
            )

        now = await self._database_now()
        coordinator = RunCoordinator(self._session)
        await coordinator.append_event(
            tenant_id=run.tenant_id,
            run_id=run.id,
            event=NewRunEvent(
                event_type=RunEventType.PHASE_CHANGED,
                content=inline_event_content(
                    RunEventPayload(
                        phase="retrieval_completed",
                        summary=self._evidence_summary(response.sources),
                    ),
                    classification=SnapshotClassification.INTERNAL,
                ),
                visibility=EventVisibility.USER,
                occurred_at=now,
                correlation_id=run.correlation_id,
            ),
        )
        usage = RunUsageSummary()
        await coordinator.append_event(
            tenant_id=run.tenant_id,
            run_id=run.id,
            event=NewRunEvent(
                event_type=RunEventType.USAGE_UPDATED,
                content=inline_event_content(
                    RunEventPayload(
                        summary="Legacy provider did not expose token usage",
                        usage=usage,
                    ),
                    classification=SnapshotClassification.INTERNAL,
                ),
                visibility=EventVisibility.TENANT_ADMIN,
                occurred_at=now,
                correlation_id=run.correlation_id,
            ),
        )

        output = response.reply.encode("utf-8")
        output_ref = f"compat-output:{run.id}"
        try:
            snapshot = await CompatibilityOutputService(self._session).stage(
                tenant_id=run.tenant_id,
                conversation_id=run.conversation_id,
                run_id=run.id,
                output_ref=output_ref,
                reply=response.reply,
                response_envelope=self._response_envelope(response.sources),
            )
        except ValueError as exc:
            raise DirectRagOutputTooLargeError(str(exc)) from None
        assistant_message_id = uuid.uuid4()
        _, terminal_event, _ = await coordinator.commit_terminal(
            tenant_id=run.tenant_id,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=run.status_revision,
            result=TerminalResult(
                outcome="completed",
                code="direct_rag_completed",
                reason="Legacy Direct RAG compatibility execution completed",
                output_ref=output_ref,
                output_digest=snapshot.output_digest,
                output_size=len(output),
                output_media_type="text/markdown",
                output_classification=SnapshotClassification.INTERNAL,
                terminal_message_id=assistant_message_id,
                usage=usage,
            ),
        )
        assert terminal_event is not None
        return DirectRagRecording(
            conversation_id=run.conversation_id,
            user_message_id=run.root_input_message_id,
            run_id=run.id,
            assistant_message_id=assistant_message_id,
        )

    async def publish_completed_turn(
        self, *, prepared: PreparedDirectRagTurn
    ) -> PreparedDirectRagTurn:
        from app.contexts.agent_execution.application.bridge import (
            AgentExecutionBridgeService,
        )

        event, _ = await AgentExecutionBridgeService(
            self._session
        ).require_publish_event(
            tenant_id=prepared.tenant_id,
            run_id=prepared.recording.run_id,
        )
        await self._session.rollback()
        published = await AgentBridgeDispatcher(
            self._session_factory,
            worker_id="direct-rag-compatibility",
            output_reader=CompatibilityOutputReader(self._session_factory),
        ).dispatch_output(event_id=event.event_id)
        if not published:
            raise DirectRagCompatibilityError(
                "Direct RAG assistant output could not be published"
            )
        tenant_id = event.tenant_id
        assistant = await self._require_assistant_message(
            tenant_id=tenant_id,
            actor_id=prepared.actor_id,
            conversation_id=prepared.recording.conversation_id,
            run_id=prepared.recording.run_id,
        )
        return PreparedDirectRagTurn(
            tenant_id=tenant_id,
            actor_id=prepared.actor_id,
            recording=DirectRagRecording(
                conversation_id=prepared.recording.conversation_id,
                user_message_id=prepared.recording.user_message_id,
                run_id=prepared.recording.run_id,
                assistant_message_id=assistant.id,
            ),
            replay_reply=self._message_text(assistant),
            replay_sources=await self._replay_sources(
                tenant_id=tenant_id, run_id=prepared.recording.run_id
            ),
        )

    async def fail_turn(
        self,
        *,
        prepared: PreparedDirectRagTurn,
        code: str = "direct_rag_execution_failed",
    ) -> None:
        run_id = prepared.recording.run_id
        tenant_id = prepared.tenant_id
        await self._acquire_write_guard(prepared)
        coordinator = RunCoordinator(self._session)
        run = await coordinator.require_run(tenant_id=tenant_id, run_id=run_id)
        if run.is_terminal:
            return
        if run.status not in {RunStatus.STARTING, RunStatus.RUNNING}:
            raise DirectRagCompatibilityError(
                f"Direct RAG Run cannot fail from {run.status.value}"
            )
        now = await self._database_now()
        await coordinator.append_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event=NewRunEvent(
                event_type=RunEventType.ERROR_REPORTED,
                content=inline_event_content(
                    RunEventPayload(
                        code=code,
                        summary="Legacy Direct RAG execution failed; diagnostics omitted",
                    ),
                    classification=SnapshotClassification.INTERNAL,
                ),
                visibility=EventVisibility.TENANT_ADMIN,
                occurred_at=now,
                correlation_id=run.correlation_id,
            ),
        )
        await coordinator.commit_terminal(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=run.status,
            expected_revision=run.status_revision,
            result=TerminalResult(
                outcome="failed",
                code=code,
                reason="Legacy Direct RAG execution failed; diagnostics omitted",
            ),
        )

    async def completed_turn(
        self, *, prepared: PreparedDirectRagTurn
    ) -> PreparedDirectRagTurn | None:
        tenant_id = prepared.tenant_id
        run = await RunCoordinator(self._session).require_run(
            tenant_id=tenant_id, run_id=prepared.recording.run_id
        )
        if run.status is not RunStatus.COMPLETED:
            return None
        if run.output_publish_state is not OutputPublishState.PUBLISHED:
            return PreparedDirectRagTurn(
                tenant_id=prepared.tenant_id,
                actor_id=prepared.actor_id,
                recording=DirectRagRecording(
                    conversation_id=run.conversation_id,
                    user_message_id=run.root_input_message_id,
                    run_id=run.id,
                    assistant_message_id=run.terminal_message_id,
                ),
                requires_output_publish=True,
            )
        assistant = await self._require_assistant_message(
            tenant_id=tenant_id,
            actor_id=run.created_by_or_raise,
            conversation_id=run.conversation_id,
            run_id=run.id,
        )
        return PreparedDirectRagTurn(
            tenant_id=prepared.tenant_id,
            actor_id=prepared.actor_id,
            recording=DirectRagRecording(
                conversation_id=run.conversation_id,
                user_message_id=run.root_input_message_id,
                run_id=run.id,
                assistant_message_id=assistant.id,
            ),
            replay_reply=self._message_text(assistant),
            replay_sources=await self._replay_sources(
                tenant_id=tenant_id, run_id=run.id
            ),
        )

    async def _acquire_write_guard(self, prepared: PreparedDirectRagTurn) -> None:
        await ConversationExecutionGuard().acquire(
            self._session,
            tenant_id=prepared.tenant_id,
            conversation_id=prepared.recording.conversation_id,
        )
        await AgentWorkspaceBridgeService(self._session).lock_owned_conversation(
            tenant_id=prepared.tenant_id,
            actor_id=prepared.actor_id,
            conversation_id=prepared.recording.conversation_id,
            include_deleted=False,
        )

    async def _database_now(self) -> datetime:
        value = await self._session.scalar(select(func.clock_timestamp()))
        return value or datetime.now(UTC)

    async def _resolve_conversation_id(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        requested_id: uuid.UUID,
    ) -> uuid.UUID:
        workspace = AgentWorkspaceService(self._session)
        try:
            await workspace.get_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=requested_id,
            )
            return requested_id
        except ConversationNotFoundError:
            scoped_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"metaedu:direct-rag:{tenant_id}:{actor_id}:{requested_id}",
            )
            try:
                await workspace.get_conversation(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    conversation_id=scoped_id,
                )
            except ConversationNotFoundError:
                await workspace.create_conversation(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    conversation_id=scoped_id,
                )
            return scoped_id

    @staticmethod
    def _execution_claim_key(run_id: uuid.UUID) -> int:
        return int.from_bytes(
            hashlib.sha256(b"direct-rag-execution:" + run_id.bytes).digest()[:8],
            byteorder="big",
            signed=True,
        )

    async def _require_assistant_message(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> Message:
        service = AgentWorkspaceService(self._session)
        before_seq: int | None = None
        while True:
            page = await service.list_messages(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                before_seq=before_seq,
                limit=100,
            )
            for message in reversed(page.items):
                if message.origin_run_id == run_id:
                    return message
            if not page.has_more or not page.items:
                break
            before_seq = page.items[0].seq
        raise DirectRagCompatibilityError(
            "completed Direct RAG Run is missing its assistant Message"
        )

    @staticmethod
    def _message_text(message: Message) -> str:
        return "".join(
            part.text_content or ""
            for part in message.parts
            if part.part_type is MessagePartType.TEXT
        )

    @staticmethod
    def _evidence_summary(sources: list[EvidenceItem]) -> str:
        source_types = Counter(source.source_type for source in sources)
        channels = sorted(
            {channel for source in sources for channel in source.channels if channel}
        )
        type_summary = ", ".join(
            f"{source_type}={count}"
            for source_type, count in sorted(source_types.items())
        )
        channel_summary = ", ".join(channels)
        return (
            f"Retrieved {len(sources)} authorized source(s); "
            f"types: {type_summary or 'none'}; channels: {channel_summary or 'none'}"
        )

    @staticmethod
    def _response_envelope(sources: list[EvidenceItem]) -> dict:
        refs: list[dict] = []
        for source in sources:
            ref = source.model_dump(mode="json")
            ref.update(
                {
                    "content": "",
                    "snippet": "",
                    "metadata": {},
                    "score": str(source.score) if source.score is not None else None,
                }
            )
            refs.append(ref)
        return {
            "schema_version": 1,
            "sources": refs,
        }

    async def _replay_sources(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[EvidenceItem, ...]:
        snapshot = await CompatibilityOutputService(self._session).require_by_run(
            tenant_id=tenant_id, run_id=run_id
        )
        values = snapshot.response_envelope.get("sources", [])
        if not isinstance(values, list):
            raise DirectRagCompatibilityError(
                "Direct RAG response envelope sources are malformed"
            )
        return tuple(EvidenceItem.model_validate(value) for value in values)
