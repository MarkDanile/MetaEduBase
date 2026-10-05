"""TD-085 Slice D（ADR-085-4）：composition 共享 snapshot helper + snapshot port 默认 adapter。

两个职责同属「跨 context snapshot / erasure 协调」的 composition 编排面：

1. ``snapshot_digest`` 共享 helper：``agent_execution.domain.snapshots`` 的纯
   函数经本模块再导出（composition → context 为合法依赖方向，与
   ``transport_erasure_participant`` / ``agent_control_plane`` 等 6 处既有
   引用同模式）。``agent_workspace`` 侧 erasure participant 的 receipt
   tombstone digest 改经本模块调用，不再 direct import execution domain——
   digest 算法、canonical 序列化与输入负载构造（调用方冻结键名）完全不变。

2. ``WorkspaceSnapshotAdapter``：``agent_workspace.application.ports``
   新增的 ``WorkspaceSnapshotPort`` 的默认实现（composition wiring）。只搬迁
   execution participant 原有的 workspace 访问原语——fence / legal hold 方法
   1:1 委托 ``AgentErasureRepository``；Conversation / PurgeOperation /
   PurgeOwnerCheckpoint 的 ``SELECT ... FOR UPDATE`` 逐字迁自
   ``execution_erasure_participant``（SQL、锁序与行级锁范围不变）。checkpoint
   的状态裁决与赋值仍由调用方（execution participant）完成，本 adapter 不做
   任何业务裁决，避免业务逻辑向 composition / workspace 渗漏。

本模块不是新的平行 runtime：不含业务流程，只做跨 context 原语转接。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.domain.snapshots import (
    snapshot_digest as snapshot_digest,
)
from app.contexts.agent_workspace.application.ports import WorkspaceSnapshotPort
from app.contexts.agent_workspace.domain.erasure import (
    ErasureFence,
    ErasureFenceState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)

__all__ = ["WorkspaceSnapshotAdapter", "snapshot_digest"]


class WorkspaceSnapshotAdapter(WorkspaceSnapshotPort):
    """``WorkspaceSnapshotPort`` 默认实现（composition 装配点）。

    构造签名与 ``AgentErasureRepository`` 同（单 ``AsyncSession``），供
    ``ExecutionErasureParticipant.__init__`` 默认装配；既有调用方与测试的
    构造方式不变。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)

    # --- fence / legal hold：1:1 委托 AgentErasureRepository --------------

    async def get_fence_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> ErasureFence | None:
        return await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )

    async def ensure_fence_under_owner_lock(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> tuple[ErasureFence, bool]:
        return await self._erasure.ensure_fence_under_owner_lock(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
        )

    async def transition_fence_state(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
        expected_state: ErasureFenceState,
        expected_revision: int,
        new_state: ErasureFenceState,
        purge_revision: int,
        hold_revision: int,
        ack_digest: str | None = None,
    ) -> ErasureFence:
        return await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=owner_key,
            expected_state=expected_state,
            expected_revision=expected_revision,
            new_state=new_state,
            purge_revision=purge_revision,
            hold_revision=hold_revision,
            ack_digest=ack_digest,
        )

    async def has_active_legal_hold(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> bool:
        return await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

    # --- FOR UPDATE 加载：逐字迁自 execution_erasure_participant ----------

    async def lock_conversation_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationModel | None:
        return (
            await self._session.execute(
                select(ConversationModel)
                .where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def lock_operation_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> PurgeOperationModel | None:
        return (
            (
                await self._session.execute(
                    select(PurgeOperationModel)
                    .where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.id == purge_operation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )

    async def lock_checkpoint_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> PurgeOwnerCheckpointModel | None:
        return (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                        PurgeOwnerCheckpointModel.owner_key == owner_key,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
