from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

# TD-085 Slice D（ADR-085-4）：workspace 自有的 erasure 协调 domain 类型经本
# 模块再导出（冗余别名 = 显式 re-export），作为 workspace 对外 application
# 契约面的一部分——execution 侧经本模块引用这些类型，不再 direct import
# ``agent_workspace.domain``。
from app.contexts.agent_workspace.domain.erasure import (
    ErasureFence as ErasureFence,
)
from app.contexts.agent_workspace.domain.erasure import (
    ErasureFenceState as ErasureFenceState,
)
from app.contexts.agent_workspace.domain.erasure import (
    PurgeOperationState as PurgeOperationState,
)
from app.contexts.agent_workspace.domain.erasure import (
    PurgeOwnerState as PurgeOwnerState,
)
from app.shared.schemas.agent_integration import (
    AssistantMessagePublishRequestedV1,
)

if TYPE_CHECKING:
    # 仅类型层引用（``from __future__ import annotations`` 下运行期零 import）：
    # port 加载方法的返回标注。application 不在运行期依赖本 context 的
    # infrastructure；默认 adapter 由 composition 装配（见
    # ``app.composition.runtime_snapshot.WorkspaceSnapshotAdapter``）。
    from app.contexts.agent_workspace.infrastructure.models import (
        ConversationModel,
        PurgeOperationModel,
        PurgeOwnerCheckpointModel,
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
    async def share_owned_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool,
    ) -> None: ...

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


class WorkspaceSnapshotPort(Protocol):
    """execution 侧访问 workspace erasure 协调状态的 port（TD-085 Slice D / ADR-085-4）。

    workspace 拥有 fence ledger / purge operation / owner checkpoint / Conversation
    purge 事实；``execution.core.v1`` erasure participant 经本 port 访问这些原语，
    不再 direct import ``agent_workspace.domain`` / ``infrastructure``。

    方法面精确等于 execution participant 的真实消费面（不多不少）：

    - fence / legal hold：1:1 委托 ``AgentErasureRepository`` 同名原语
      （锁序 / fence CAS / hold 判定语义不变，``now`` 默认值与仓库一致）；
    - 三个 ``lock_*_for_update``：Conversation / PurgeOperation /
      PurgeOwnerCheckpoint 的 ``SELECT ... FOR UPDATE``（自 execution
      participant 逐字搬迁，SQL 与锁序不变；checkpoint 变更仍由调用方在返回的
      ORM 行上赋值 + flush，原子 fail-closed 纪律不变）。

    默认实现由 composition 装配：
    ``app.composition.runtime_snapshot.WorkspaceSnapshotAdapter``。
    """

    async def get_fence_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> ErasureFence | None: ...

    async def ensure_fence_under_owner_lock(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        owner_key: str,
    ) -> tuple[ErasureFence, bool]: ...

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
    ) -> ErasureFence: ...

    async def has_active_legal_hold(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> bool: ...

    async def lock_conversation_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationModel | None: ...

    async def lock_operation_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
    ) -> PurgeOperationModel | None: ...

    async def lock_checkpoint_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        purge_operation_id: uuid.UUID,
        owner_key: str,
    ) -> PurgeOwnerCheckpointModel | None: ...
