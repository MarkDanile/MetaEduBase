"""composition adapter：execution 侧身份事实 -> workspace 中性 launch facts port。

TD-085 已冻结的 bounded context 依赖方向要求 ``agent_workspace`` 不得 import
``agent_execution``（门禁：``tests/composition/test_runtime_snapshot.py::
test_workspace_does_not_import_execution``）。本模块是唯一允许两侧同时出现的
装配层：

- execution 侧：``AgentExecutionIdentityRepository``、definition/profile 查询、
  ``AgentDefinitionStatus``、``snapshot_digest``、``DIRECT_RAG_*`` 冻结常量、
  compatibility 路径既有 ``_DIRECT_RAG_BUDGET``；
- workspace 侧：``RuntimeLaunchFactsPort`` 声明的中性事实类型。

跨 context 的具体类型转换（execution ORM/dataclass -> workspace 中性 DTO）全部
落在本模块，workspace application 层不再认识任何 execution 类型，也不持有
``AsyncSession``。

注意：本模块不是 REQ-043 的 ``RuntimeProfileResolver``。它只做既有
compatibility 身份事实的投影，不引入 profile 选择、binding 生命周期、
conformance 或 Tool Gateway；REQ-043 落地后应替换本 adapter 而不是绕过它。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.direct_rag_compatibility import _DIRECT_RAG_BUDGET
from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
    DIRECT_RAG_POLICY_VERSION,
    DIRECT_RAG_PROFILE_KEY,
)
from app.contexts.agent_execution.domain import (
    AgentDefinitionStatus,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)
from app.contexts.agent_workspace.application.ports import (
    RuntimeDefinitionServability,
    RuntimeLaunchFactsPort,
    RuntimeProfileFacts,
    V1LaunchFacts,
)
from app.contexts.agent_workspace.application.v1_launch_policy import (
    V1CompatibilityLaunchPolicy,
)
from app.shared.schemas.agent_integration import (
    RunBudgetSnapshotV1,
    RuntimeCapabilitySnapshotV1,
)

# V1 冻结常量 -> 中性 shared schema / facts，进程内一次性投影（不可变，可安全共享）。
# ``capability_digest`` 在此按 execution 的 canonical 化规则算出一次；workspace 只
# 与 profile 登记值做等值比对，不重算、不解释 canonical 化规则。
_V1_LAUNCH_FACTS = V1LaunchFacts(
    profile_key=DIRECT_RAG_PROFILE_KEY,
    policy_version=DIRECT_RAG_POLICY_VERSION,
    capability_snapshot=RuntimeCapabilitySnapshotV1.model_validate(
        DIRECT_RAG_CAPABILITIES.model_dump(mode="json")
    ),
    capability_digest=snapshot_digest(DIRECT_RAG_CAPABILITIES),
    budget=RunBudgetSnapshotV1.model_validate(
        _DIRECT_RAG_BUDGET.model_dump(mode="json")
    ),
)


class ExecutionRuntimeLaunchFactsAdapter(RuntimeLaunchFactsPort):
    """``RuntimeLaunchFactsPort`` 的 execution 侧默认实现。

    显式继承 port：mypy 静态校验 adapter 覆盖了 port 全方法面；port 面扩张而
    adapter 未跟进时，本类在构造期即 fail-closed（不会带着未实现的 method 流入
    workspace）。

    每个 HTTP 请求新建一个实例（随 ``get_session`` 请求作用域创建），内部只持有
    一个 execution 身份仓储；不缓存跨请求状态。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._identity = AgentExecutionIdentityRepository(session)

    async def get_definition_servability(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_version_id: uuid.UUID,
    ) -> RuntimeDefinitionServability | None:
        """未知 definition 返回 ``None``（由调用方映射 422）。"""
        definition = await self._identity.get_agent_definition_version(
            tenant_id=tenant_id,
            definition_version_id=definition_version_id,
        )
        if definition is None:
            return None
        return RuntimeDefinitionServability(
            is_published=definition.status is AgentDefinitionStatus.PUBLISHED
        )

    async def get_runtime_profile_facts(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_key: str,
    ) -> RuntimeProfileFacts | None:
        profile = await self._identity.get_runtime_profile_by_key(
            tenant_id=tenant_id,
            profile_key=profile_key,
        )
        if profile is None:
            return None
        return RuntimeProfileFacts(
            runtime_profile_id=profile.id,
            runtime_kind=profile.runtime_kind,
            adapter_key=profile.adapter_key,
            enabled=profile.enabled,
            capability_digest=profile.capability_digest,
        )

    def v1_launch_facts(self) -> V1LaunchFacts:
        return _V1_LAUNCH_FACTS


def build_v1_launch_policy(session: AsyncSession) -> V1CompatibilityLaunchPolicy:
    """composition 装配入口：workspace route 的 launch policy 依赖来源。"""
    return V1CompatibilityLaunchPolicy(ExecutionRuntimeLaunchFactsAdapter(session))


__all__ = [
    "ExecutionRuntimeLaunchFactsAdapter",
    "build_v1_launch_policy",
]
