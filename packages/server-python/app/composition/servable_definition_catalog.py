"""REQ-042 WS-S2 definition discovery（composition adapter）。

契约：docs/02-delivery-plans/01-specs/2026-10-19-req-042-ws-s2-definition-discovery-contract.md

本模块是 discovery 的唯一装配点：workspace 侧消费
``ServableDefinitionCatalogPort`` 声明的中性 ``ServableDefinitionItem``，
execution 侧的 ORM / 仓储 / 领域枚举 / V1 冻结常量只在本模块出现
（TD-085 依赖方向不变）。

可服务性判定与 phase-C 提交期判定链同源（契约 §3 五谓词）：
published definition + tenant 内 ``compat.direct_rag.v1`` profile 存在 +
enabled + V1 身份 + capability digest 一致。共享 profile digest 缺陷
（谓词 5）= 服务端配置缺陷：读面 fail-safe 返回空 + 按缺陷去重的单条
warning（不按 definition 重复刷）；提交面对应路径仍 fail-closed 500，不变。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
    DIRECT_RAG_PROFILE_KEY,
)
from app.contexts.agent_execution.domain import snapshot_digest
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)
from app.contexts.agent_workspace.application.ports import (
    ServableDefinitionCatalogPort,
    ServableDefinitionItem,
)

logger = logging.getLogger(__name__)

_V1_RUNTIME_KIND = "compatibility"
_V1_ADAPTER_KEY = "direct_rag"
# 契约 §3 谓词 5 的唯一判定基准：canonical DIRECT_RAG_CAPABILITIES 的
# snapshot_digest（与 phase-C 提交期判定链同源）。
_V1_CAPABILITY_DIGEST = snapshot_digest(DIRECT_RAG_CAPABILITIES)

# 共享 profile 缺陷的进程内去重登记：同一 (tenant, profile_key) 缺陷只警告一次
# （契约 §3：一次缺陷一条 warning，不按 definition 重复刷同一配置告警）。
_warned_profile_defects: set[tuple[uuid.UUID, str]] = set()


class ExecutionServableDefinitionCatalog(ServableDefinitionCatalogPort):
    """``ServableDefinitionCatalogPort`` 的 execution 侧默认实现。

    显式继承 port：port 面扩张而 adapter 未跟进时构造期即 fail-closed。
    每个请求新建实例（随 ``get_session`` 请求作用域）；**只读，零写库**
    （契约 §4）。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._identity = AgentExecutionIdentityRepository(session)

    async def list_servable_definitions(
        self, *, tenant_id: uuid.UUID
    ) -> list[ServableDefinitionItem]:
        """契约 §3 五谓词；空列表是正常语义（契约 §2）。"""
        profile = await self._identity.get_runtime_profile_by_key(
            tenant_id=tenant_id,
            profile_key=DIRECT_RAG_PROFILE_KEY,
        )
        # 谓词 2-4：profile 缺失 / disabled / 身份不符 -> 空（正常语义）。
        if profile is None or not profile.enabled:
            return []
        if profile.runtime_kind != _V1_RUNTIME_KIND or profile.adapter_key != _V1_ADAPTER_KEY:
            return []
        # 谓词 5：capability digest 不符 = 服务端配置缺陷 -> 空 + 按缺陷去重
        # warning（不按 definition 重复刷）。
        if profile.capability_digest != _V1_CAPABILITY_DIGEST:
            defect_key = (tenant_id, DIRECT_RAG_PROFILE_KEY)
            if defect_key not in _warned_profile_defects:
                _warned_profile_defects.add(defect_key)
                logger.warning(
                    "servable definition discovery suppressed for tenant %s: "
                    "shared profile %s capability digest mismatch "
                    "(registered=%s, expected V1 frozen)",
                    tenant_id,
                    DIRECT_RAG_PROFILE_KEY,
                    profile.capability_digest,
                )
            return []

        # 谓词 1：published definition（draft/retired 由仓储查询排除）。
        definitions = await self._identity.list_published_agent_definition_versions(
            tenant_id=tenant_id
        )
        return [
            ServableDefinitionItem(
                id=d.id,
                definition_key=d.definition_key,
                version=d.version,
            )
            for d in definitions
        ]


def build_servable_definition_catalog(
    session: AsyncSession,
) -> ExecutionServableDefinitionCatalog:
    """composition 装配入口：discovery route 的依赖来源。"""
    return ExecutionServableDefinitionCatalog(session)


__all__ = [
    "ExecutionServableDefinitionCatalog",
    "build_servable_definition_catalog",
]
