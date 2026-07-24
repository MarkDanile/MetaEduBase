from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.shared.schemas.agent_integration import (
    AssistantMessagePublishRequestedV1,
)


class ResourceReferenceAccessPort(Protocol):
    """Authorize opaque Resource references without importing Resource internals."""

    async def can_reference_resources(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_ids: tuple[uuid.UUID, ...],
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class TerminalOutput:
    content: bytes
    media_type: str


class TerminalOutputReaderPort(Protocol):
    async def read_terminal_output(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
    ) -> TerminalOutput: ...


class FailClosedTerminalOutputReader:
    async def read_terminal_output(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
    ) -> TerminalOutput:
        raise RuntimeError("terminal output reader is not configured")


class WorkspaceReadPort(Protocol):
    async def lock_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> None: ...

    async def has_unacknowledged_turn(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool: ...

    async def can_start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> bool: ...

    async def output_is_projected(
        self,
        *,
        event: AssistantMessagePublishRequestedV1,
        payload_digest: str,
    ) -> bool: ...
