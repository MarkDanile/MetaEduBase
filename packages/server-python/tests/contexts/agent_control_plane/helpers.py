from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.agent_erasure_registry import owner_registry
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
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.shared.schemas.agent_integration import TurnLaunchSpecV1
from tests.conftest import TEST_DB_URL
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


async def create_baseline_fences(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    skip_owner: str | None = None,
) -> None:
    """为全部 registry owner 建 active baseline fence（等价 backfill 已覆盖）。

    restore 要求 fence 集合完整且全部 active；``skip_owner`` 用于构造
    「缺失 fail closed」反例。
    """
    repo = AgentErasureRepository(session)
    for owner in owner_registry():
        if owner.owner_key == skip_owner:
            continue
        await repo.create_fence_under_owner_lock(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner.owner_key,
        )


async def create_baseline_fences_via_engine(
    *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    """API 测试用：经独立 engine 以生产 create_fence 路径建 baseline fence。"""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session, session.begin():
            await create_baseline_fences(
                session, tenant_id=tenant_id, conversation_id=conversation_id
            )
    finally:
        await engine.dispose()
