"""WS-S2 phase-B 冻结的 V1 compatibility launch policy（提交期消费面）。

范围声明（防止误读为 REQ-043 实现）：

- 本模块**只是** phase-C 提交期构造 ``TurnLaunchSpecV1`` 的局部 helper。
- 它**不是** REQ-043 的 ``RuntimeProfileResolver``：不做 profile 选择算法、
  不做 binding 生命周期、不做 conformance、不做 Tool Gateway。
- 它不消费 REQ-047 Extended 的 ToolGrant / Approval / Artifact / Evidence。
- 将来 REQ-043 引入真正的 Resolver 后，其输出必须继续满足 phase-B §1 / §2
  的同一份不变量；本模块届时应被替换而不是被绕过。

V1 冻结取值（phase-B §2）：

- 解析目标 profile 恒为 tenant 内 ``compat.direct_rag.v1``（唯一 compatibility
  profile；不引入多 profile 选择或 Runtime 切换）。
- ``runtime_binding_id`` 恒 ``None``（compatibility 路径无 session binding）。
- context snapshot 三字段恒全 ``None``（schema 内建 all-null-or-all-present 校验）。
- budget 六项取既有 ``_DIRECT_RAG_BUDGET`` 常量，且不得由客户端选项放大。
- capability 快照取 ``DIRECT_RAG_CAPABILITIES``（V1 全 ``False``）。

fail-closed 判定顺序（phase-B §3.2）：

1. definition 存在性与可服务状态：未知 ``agent_definition_version_id`` -> 422
   validation_error；存在但非 published -> 403 capability_denied
   （phase-A §3「服务端校验存在性与启用状态」）
2. 可服务性：无可服务的 enabled compatibility profile -> 403 capability_denied
3. 快照一致性：capability 快照与 profile 登记 digest 不一致 -> 500 internal_error
4. 授权：``parts`` resource 未授权 -> 403 resource_access_denied（由 durable
   ``reserve_user_turn`` 既有 ``_authorize_resource_references`` 承担）

以上任一不满足即拒绝，不降级放行。
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
    RunConfigSnapshot,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)
from app.contexts.agent_workspace.domain import (
    AgentDefinitionNotFoundError,
    CapabilityDeniedError,
    LaunchPolicyInternalError,
)
from app.shared.schemas.agent_integration import (
    RunBudgetSnapshotV1,
    RunConfigSnapshotV1,
    RuntimeCapabilitySnapshotV1,
    TurnLaunchSpecV1,
)

# V1 run config 常量（phase-B §2.3，取自 compatibility 路径现事实）。
_V1_MODEL_PROFILE_KEY = None
_V1_AUTONOMY_LEVEL = 0
_V1_TOOL_KEYS: tuple[str, ...] = ()


class V1CompatibilityLaunchPolicy:
    """按 phase-B §1/§2/§3 为一次 submit 构造 server-selected launch。

    本类是 phase-C 的提交期构造器，不是 profile 选择器：V1 只有一个目标
    profile（``compat.direct_rag.v1``），解析即「按 key 取或拒绝」。
    """

    def __init__(self, session: AsyncSession):
        self._identity = AgentExecutionIdentityRepository(session)

    async def build_launch(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_definition_version_id: uuid.UUID,
    ) -> TurnLaunchSpecV1:
        """构造 V1 launch；不满足 phase-B 不变量时抛对应 domain 错误。

        调用方（router）负责把异常映射到 phase-A §10 冻结错误码。
        """
        # §3.2-1 definition 存在性：未知 definition -> 422。
        definition = await self._identity.get_agent_definition_version(
            tenant_id=tenant_id,
            definition_version_id=agent_definition_version_id,
        )
        if definition is None:
            raise AgentDefinitionNotFoundError(
                "agent definition version is not registered for this tenant"
            )
        # phase-A §3「服务端校验存在性与启用状态」：只有 published definition 可
        # 服务 V1 launch。draft / retired 等不可服务状态一律 403 capability_denied
        # （fail-closed），不得因「行存在」而放行。
        if definition.status is not AgentDefinitionStatus.PUBLISHED:
            raise CapabilityDeniedError(
                "agent definition version is not in a servable published state"
            )

        # §3.2-2 可服务性：按 key 解析 V1 唯一 compatibility profile。
        profile = await self._identity.get_runtime_profile_by_key(
            tenant_id=tenant_id,
            profile_key=DIRECT_RAG_PROFILE_KEY,
        )
        if profile is None:
            raise CapabilityDeniedError(
                "tenant has no servable compatibility Runtime profile"
            )
        if not profile.enabled:
            raise CapabilityDeniedError(
                "tenant compatibility Runtime profile is disabled"
            )
        if (
            profile.runtime_kind != "compatibility"
            or profile.adapter_key != "direct_rag"
        ):
            # profile 身份与 V1 compatibility 路径不符：不可服务。
            raise CapabilityDeniedError(
                "tenant Runtime profile is not the V1 compatibility profile"
            )

        # §3.2-3 快照一致性：构造快照必须等于 profile 登记的 capability digest，
        # 否则视为服务端缺陷，构造失败即提交失败（fail-closed -> 500）。
        if profile.capability_digest != snapshot_digest(DIRECT_RAG_CAPABILITIES):
            raise LaunchPolicyInternalError(
                "tenant compatibility profile capability digest does not match "
                "the frozen V1 capability snapshot"
            )

        # §1 / §2：构造 immutable launch。binding/context 恒 None；
        # budget 六项取既有常量且不得被客户端放大。
        capability = RuntimeCapabilitySnapshotV1.model_validate(
            DIRECT_RAG_CAPABILITIES.model_dump(mode="json")
        )
        budget_v1 = RunBudgetSnapshotV1.model_validate(
            _DIRECT_RAG_BUDGET.model_dump(mode="json")
        )
        run_config = RunConfigSnapshot(
            agent_definition_version_id=agent_definition_version_id,
            runtime_profile_id=profile.id,
            model_profile_key=_V1_MODEL_PROFILE_KEY,
            autonomy_level=_V1_AUTONOMY_LEVEL,
            policy_version=DIRECT_RAG_POLICY_VERSION,
            tool_keys=_V1_TOOL_KEYS,
            budget=_DIRECT_RAG_BUDGET,
        )
        run_config_v1 = RunConfigSnapshotV1.model_validate(
            run_config.model_dump(mode="json")
        )
        return TurnLaunchSpecV1(
            agent_definition_version_id=agent_definition_version_id,
            runtime_profile_id=profile.id,
            runtime_binding_id=None,
            runtime_capability_snapshot=capability,
            run_config_snapshot=run_config_v1,
            context_snapshot_ref=None,
            context_snapshot_digest=None,
            context_snapshot_classification=None,
            budget_snapshot=budget_v1,
            parent_run_id=None,
        )


__all__ = ["V1CompatibilityLaunchPolicy"]
