from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.ports import (
    ConversationAccessDecision,
    RunConversationAccessPort,
)
from app.contexts.agent_execution.application.run_query_service import RunQueryService
from app.contexts.agent_execution.domain import EventVisibility
from app.contexts.agent_workspace.application.bridge import AgentWorkspaceBridgeService
from app.contexts.agent_workspace.domain import ConversationNotFoundError
from app.contexts.identity.infrastructure.models import UserModel


class WorkspaceOwnedConversationAccess(RunConversationAccessPort):
    """Resolve A1 access from the Workspace-owned private Conversation fact."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._workspace = AgentWorkspaceBridgeService(session)

    async def resolve(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationAccessDecision | None:
        active_actor = (
            await self._session.execute(
                select(UserModel.id)
                .where(
                    UserModel.tenant_id == tenant_id,
                    UserModel.id == actor_id,
                    UserModel.is_active.is_(True),
                )
                .with_for_update(read=True)
            )
        ).scalar_one_or_none()
        if active_actor is None:
            return None
        try:
            await self._workspace.share_owned_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                include_deleted=False,
            )
        except ConversationNotFoundError:
            return None
        return ConversationAccessDecision(
            audience_key=f"conversation_owner.v1:{actor_id}",
            visible_event_scopes=frozenset({EventVisibility.USER}),
            can_cancel=True,
        )


def build_run_query_service(session: AsyncSession) -> RunQueryService:
    # R1-S3-C round-7 commit-5：注入 WorkspaceReadPort（AgentWorkspaceBridgeService
    # 实现），使 RunQueryService.request_cancel 能取 Conv 行锁而不反向 import
    # concrete bridge。
    from app.contexts.agent_workspace.application.bridge import (
        AgentWorkspaceBridgeService,
    )

    return RunQueryService(
        session,
        conversation_access=WorkspaceOwnedConversationAccess(session),
        workspace_read=AgentWorkspaceBridgeService(session),
    )
