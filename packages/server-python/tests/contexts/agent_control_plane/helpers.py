from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    CompatibilityIdentity,
    ExecutionIdentityService,
)
from app.contexts.agent_execution.domain import RunConfigSnapshot
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.application.ports import TerminalOutput
from app.contexts.agent_workspace.domain import MessagePartType
from app.shared.schemas.agent_integration import TurnLaunchSpecV1
from tests.contexts.agent_execution.e1_helpers import make_budget

TENANT_ID = uuid.UUID("71000000-0000-0000-0000-000000000001")
ACTOR_ID = uuid.UUID("71000000-0000-0000-0000-000000000002")


class StaticOutputReader:
    def __init__(self, content: bytes, media_type: str = "text/markdown"):
        self._output = TerminalOutput(content=content, media_type=media_type)

    async def read_terminal_output(self, **_kwargs) -> TerminalOutput:
        return self._output


class FailingOutputReader:
    async def read_terminal_output(self, **_kwargs) -> TerminalOutput:
        raise RuntimeError("terminal object is unavailable")


async def bootstrap_workspace(
    session: AsyncSession,
) -> tuple[uuid.UUID, CompatibilityIdentity, TurnLaunchSpecV1]:
    conversation, _ = await AgentWorkspaceService(session).create_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        title="B1 control plane",
    )
    identity = await ExecutionIdentityService(session).bootstrap_direct_rag(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    budget = make_budget()
    run_config = RunConfigSnapshot(
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=identity.runtime_profile.id,
        model_profile_key="model.readonly.v1",
        autonomy_level=1,
        policy_version="policy.v1",
        tool_keys=(),
        budget=budget,
    )
    launch = TurnLaunchSpecV1(
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=identity.runtime_profile.id,
        runtime_capability_snapshot=identity.capability_snapshot.model_dump(mode="json"),
        run_config_snapshot=run_config.model_dump(mode="json"),
        budget_snapshot=budget.model_dump(mode="json"),
    )
    return conversation.conversation.id, identity, launch


def turn_command(identity: CompatibilityIdentity, text: str) -> TurnCommand:
    return TurnCommand(
        client_message_id=uuid.uuid4(),
        parts=(MessagePartInput(type=MessagePartType.TEXT, text=text),),
        agent_definition_version_id=identity.agent_definition_version.id,
    )
