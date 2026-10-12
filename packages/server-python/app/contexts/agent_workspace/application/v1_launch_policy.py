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
- budget 六项与 capability 快照取 ``RuntimeLaunchFactsPort`` 供给的既有常量
  （composition 侧从 execution/compatibility 路径原样投影），且不得由客户端
  选项放大。**本模块不重新声明这些常量**，避免两份冻结值静默漂移。

fail-closed 判定顺序（phase-B §3.2）：

1. definition 存在性与可服务状态：未知 ``agent_definition_version_id`` -> 422
   validation_error；存在但非 published -> 403 capability_denied
   （phase-A §3「服务端校验存在性与启用状态」）
2. 可服务性：无可服务的 enabled compatibility profile -> 403 capability_denied
3. 快照一致性：capability 快照与 profile 登记 digest 不一致 -> 500 internal_error
4. 授权：``parts`` resource 未授权 -> 403 resource_access_denied（由 durable
   ``reserve_user_turn`` 既有 ``_authorize_resource_references`` 承担）

以上任一不满足即拒绝，不降级放行。

依赖边界（TD-085）：本模块只 import workspace 自己的 domain / ports 与 shared
integration schema。execution 侧的 ORM / 仓储 / 领域枚举 / V1 常量一律经
``RuntimeLaunchFactsPort`` 由 composition adapter 供给。
"""

from __future__ import annotations

import uuid

from app.contexts.agent_workspace.application.ports import (
    RuntimeLaunchFactsPort,
)
from app.contexts.agent_workspace.domain import (
    AgentDefinitionNotFoundError,
    CapabilityDeniedError,
    LaunchPolicyInternalError,
)
from app.shared.schemas.agent_integration import (
    RunConfigSnapshotV1,
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

    ``facts`` 是 composition 装配的 execution 侧事实供给面；本类不持有 session、
    不直接查询任何表。
    """

    def __init__(self, facts: RuntimeLaunchFactsPort):
        self._facts = facts

    async def build_launch(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_definition_version_id: uuid.UUID,
    ) -> TurnLaunchSpecV1:
        """构造 V1 launch；不满足 phase-B 不变量时抛对应 domain 错误。

        调用方（router）负责把异常映射到 phase-A §10 冻结错误码。
        """
        frozen = self._facts.v1_launch_facts()

        # §3.2-1 definition 存在性：未知 definition -> 422。
        definition = await self._facts.get_definition_servability(
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
        if not definition.is_published:
            raise CapabilityDeniedError(
                "agent definition version is not in a servable published state"
            )

        # §3.2-2 可服务性：按 key 解析 V1 唯一 compatibility profile。
        profile = await self._facts.get_runtime_profile_facts(
            tenant_id=tenant_id,
            profile_key=frozen.profile_key,
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
            profile.runtime_kind != frozen.capability_snapshot.runtime_kind
            or profile.adapter_key != frozen.capability_snapshot.adapter_key
        ):
            # profile 身份与 V1 compatibility 路径不符：不可服务。期望身份即冻结
            # capability 快照自带的 runtime_kind / adapter_key，不另存字面量。
            raise CapabilityDeniedError(
                "tenant Runtime profile is not the V1 compatibility profile"
            )

        # §3.2-3 快照一致性：构造快照必须等于 profile 登记的 capability digest，
        # 否则视为服务端缺陷，构造失败即提交失败（fail-closed -> 500）。
        if profile.capability_digest != frozen.capability_digest:
            raise LaunchPolicyInternalError(
                "tenant compatibility profile capability digest does not match "
                "the frozen V1 capability snapshot"
            )

        # §1 / §2：构造 immutable launch。binding/context 恒 None；
        # budget 与 capability 取 composition 供给的冻结常量且不得被客户端放大。
        run_config_v1 = RunConfigSnapshotV1(
            agent_definition_version_id=agent_definition_version_id,
            runtime_profile_id=profile.runtime_profile_id,
            model_profile_key=_V1_MODEL_PROFILE_KEY,
            autonomy_level=_V1_AUTONOMY_LEVEL,
            policy_version=frozen.policy_version,
            tool_keys=_V1_TOOL_KEYS,
            budget=frozen.budget,
        )
        return TurnLaunchSpecV1(
            agent_definition_version_id=agent_definition_version_id,
            runtime_profile_id=profile.runtime_profile_id,
            runtime_binding_id=None,
            runtime_capability_snapshot=frozen.capability_snapshot,
            run_config_snapshot=run_config_v1,
            context_snapshot_ref=None,
            context_snapshot_digest=None,
            context_snapshot_classification=None,
            budget_snapshot=frozen.budget,
            parent_run_id=None,
        )


__all__ = ["V1CompatibilityLaunchPolicy"]
