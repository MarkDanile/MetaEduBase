from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.contexts.agent_execution.domain.event import EventVisibility
from app.contexts.agent_execution.domain.run import AgentRun
from app.shared.schemas.agent_integration import TurnRequestedV1


@dataclass(frozen=True, slots=True)
class DurableGuardState:
    active_tool_calls: int = 0
    active_input_requests: int = 0
    active_approvals: int = 0
    outcome_unknown_tool_calls: int = 0
    runtime_invocation_exists: bool = False
    unused_grants: int = 0


@dataclass(frozen=True, slots=True)
class ConversationAccessDecision:
    audience_key: str
    visible_event_scopes: frozenset[EventVisibility]
    can_cancel: bool


class RunConversationAccessPort(Protocol):
    async def resolve(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationAccessDecision | None: ...


class GuardStatePort(Protocol):
    async def inspect(self, run: AgentRun) -> DurableGuardState: ...


class RunStartBarrierPort(Protocol):
    async def can_start(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool: ...


class ExecutionRunReadPort(Protocol):
    async def has_non_terminal_run(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool: ...

    async def has_turn_acceptance(
        self, event: TurnRequestedV1, *, payload_digest: str
    ) -> bool: ...


class CapabilityBoundGuardState:
    """Production fail-closed guard until extended durable stores are installed."""

    async def inspect(self, run: AgentRun) -> DurableGuardState:
        capabilities = run.runtime_capability_snapshot
        if capabilities.tool_calls or capabilities.input_requests or capabilities.approvals:
            from app.contexts.agent_execution.domain.errors import (
                UnsupportedRunCapabilitiesError,
            )

            raise UnsupportedRunCapabilitiesError(
                "durable Tool/Input/Approval stores are not installed"
            )
        return DurableGuardState()


class FailClosedRunStartBarrier:
    async def can_start(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool:
        return False
