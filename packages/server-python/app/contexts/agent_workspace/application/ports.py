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
    RunBudgetSnapshotV1,
    RuntimeCapabilitySnapshotV1,
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


# --- WS-S2 phase-C：提交期 runtime launch facts port -----------------------
#
# TD-085 已冻结的 bounded context 依赖方向要求 ``agent_workspace`` 不得 import
# ``agent_execution``。本组是 phase-C 提交期 launch policy 的**唯一**外部依赖面：
# execution 的 ORM / 仓储 / 领域枚举 / V1 冻结常量由 composition adapter 投影成
# 下列中性事实类型，workspace application 层不再认识任何 execution 类型。
#
# 中立性纪律：port 面只允许 workspace-owned dataclass 与 shared integration
# schema；不得把 execution 领域对象当作 port 类型泄漏到 workspace。


@dataclass(frozen=True, slots=True)
class RuntimeDefinitionServability:
    """tenant 内 definition version 的可服务事实（中性投影）。

    composition adapter 把 execution 的 ``AgentDefinitionStatus`` 折叠成
    ``is_published`` 布尔：workspace 只需要 phase-A §3「只服务 published」的
    判定这一位事实，不需要认识 execution 的状态枚举取值域。
    """

    is_published: bool


@dataclass(frozen=True, slots=True)
class RuntimeProfileFacts:
    """tenant 内 Runtime profile 的提交期消费事实（中性投影）。

    ``capability_digest`` 是 execution 登记在 profile 上的不可变快照摘要，
    workspace 只做等值比对，不重算、不解释其 canonical 化规则。
    """

    runtime_profile_id: uuid.UUID
    runtime_kind: str
    adapter_key: str
    enabled: bool
    capability_digest: str


@dataclass(frozen=True, slots=True)
class V1LaunchFacts:
    """V1 compatibility 路径的冻结常量（phase-B §2）中性投影。

    取值事实归 execution / composition 所有，workspace **只消费不重新声明**：
    在两侧各存一份 V1 常量（capability snapshot、budget、policy version）会造成
    静默漂移，而漂移只会在 capability digest 比对时以 500 的形式暴露。
    """

    profile_key: str
    policy_version: str
    capability_snapshot: RuntimeCapabilitySnapshotV1
    capability_digest: str
    budget: RunBudgetSnapshotV1


class RuntimeLaunchFactsPort(Protocol):
    """phase-C 提交期 launch policy 对 execution 身份事实与 V1 常量的消费面。

    默认实现由 composition 装配：
    ``app.composition.runtime_launch_policy.ExecutionRuntimeLaunchFactsAdapter``。
    """

    async def get_definition_servability(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_version_id: uuid.UUID,
    ) -> RuntimeDefinitionServability | None: ...

    async def get_runtime_profile_facts(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_key: str,
    ) -> RuntimeProfileFacts | None: ...

    def v1_launch_facts(self) -> V1LaunchFacts: ...
