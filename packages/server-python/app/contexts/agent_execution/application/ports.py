from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.domain.event import EventVisibility, RunEvent
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


class GuardLockPort(Protocol):
    """R1-S3-C round-7 commit-12：ConversationExecutionGuard 的 Protocol 抽象。

    实现由 composition 层 ``ConversationExecutionGuard`` 提供；application 层
    依赖 Protocol 不反向 import composition，避免跨上下文违规（与 commit-5
    FencedWriterPort 拆分层级一致）。
    """

    async def acquire(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None: ...


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


class FencedWriterPort(Protocol):
    """R1-S3-C round-7：S3-C 单一受控 fenced writer port（Protocol）。

    实现由 composition 层 ``FencedExecutionPort`` 提供；application 层
    （``RunQueryService`` 等）只依赖 Protocol，不反向 import composition
    实现，遵循 ``ARCHITECTURE.md:154`` §5.5 跨边界规则。

    锁序前置：调用方必须在 fenced_* 入参前持 Guard + Conversation 行锁
    （Spec §6.1）。Wrapper 入口强制校验 Run 归属（commit-3）：
    ``conversation_id / queue_seq`` 与 ``AgentRun`` 自身一致，
    ``fenced_ingest_runtime_event`` 的 frame.tenant_id / run_id 与外层一致。
    """

    async def require_active_fence(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Any: ...

    async def fenced_create_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> None: ...

    async def fenced_append_event(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        event: Any,
    ) -> RunEvent: ...

    async def fenced_commit_terminal(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
        expected_status: Any,
        expected_revision: int,
        result: Any,
        cancel_intent_revision: int | None = None,
    ) -> tuple[AgentRun, RunEvent | None, bool]: ...

    async def fenced_stage(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
        output_ref: str,
        reply: str,
        response_envelope: dict,
    ) -> tuple[Any, bool]: ...

    async def fenced_start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
        start_barrier: Any = None,
    ) -> tuple[AgentRun, RunEvent]: ...

    async def fenced_transition_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status: Any,
        expected_revision: int,
        target_status: Any,
        summary: str,
        cancel_intent_revision: int | None = None,
    ) -> tuple[AgentRun, RunEvent]: ...


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
