"""WS-S2 phase-C：submit route 的 launch policy composition 装配取证。

本文件只回答一个问题：**production route 的 launch policy 到底由谁装配**。

上一版实现让 ``agent_workspace.application`` 直接 import ``agent_execution``
（违反 TD-085 已冻结的 bounded context 依赖方向），代价是真实装配路径从未被
单独取证：单元测试可以全绿，而线上 route 是否真的经 composition adapter 解析
launch policy、adapter 能否装配出满足 phase-B 不变量的 launch，都没有被断言。

修复后的依赖方向是 ``app.composition.runtime_launch_policy`` 持有 execution 侧
身份事实并投影成 workspace 中性 facts port，由 workspace route 经既有
composition DI 路径消费。本文件对这条路径做真实 PostgreSQL 端到端取证。
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.runtime_launch_policy import (
    ExecutionRuntimeLaunchFactsAdapter,
    build_v1_launch_policy,
)
from app.contexts.agent_execution.application.execution_identity_service import (
    ExecutionIdentityService,
)
from app.contexts.agent_workspace.application.v1_launch_policy import (
    V1CompatibilityLaunchPolicy,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_TURNS_PATH = "/api/v1/agent-workspace/conversations/{conversation_id}/turns"


async def _bootstrap_v1_identity(session: AsyncSession):
    """在 seed tenant 下 publish-or-get V1 compatibility identity（既有事实源）。"""
    identity = await ExecutionIdentityService(session).bootstrap_direct_rag(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
    )
    await session.commit()
    return identity


async def _create_conversation(
    client: AsyncClient, headers: dict[str, str]
) -> str:
    resp = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=headers,
        json={"title": "phase-C composition wiring"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _payload(definition_id: uuid.UUID) -> dict:
    return {
        "client_message_id": str(uuid.uuid4()),
        "parts": [
            {"type": "text", "text": "hello from phase-C wiring", "format": "plain_text"}
        ],
        "agent_definition_version_id": str(definition_id),
    }


async def test_submit_route_resolves_launch_policy_through_composition(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """production route 真的走 composition adapter，而不是未装配或旁路路径。

    用**计数包裹**而非 stub：既证明 route 经
    ``app.composition.runtime_launch_policy`` 解析 launch policy，又不放行任何
    被包裹的失败——若 route 绕过 composition 直接在 workspace 内构造 policy，
    计数为 0，断言失败。
    """
    identity = await _bootstrap_v1_identity(db_session)
    conversation_id = await _create_conversation(client, auth_headers)

    from app.contexts.agent_workspace.interfaces.api import router as ws_router

    original = ws_router.build_v1_launch_policy
    calls: list[object] = []

    def _counting_factory(session):
        policy = original(session)
        calls.append(session)
        return policy

    ws_router.build_v1_launch_policy = _counting_factory
    try:
        resp = await client.post(
            _TURNS_PATH.format(conversation_id=conversation_id),
            headers=auth_headers,
            json=_payload(identity.agent_definition_version.id),
        )
    finally:
        ws_router.build_v1_launch_policy = original

    assert resp.status_code == 201, resp.text
    # route 确实经 composition 解析了 launch policy（恰好一次）。
    assert len(calls) == 1


async def test_composition_adapter_builds_servable_v1_launch(
    client: AsyncClient, auth_headers: dict[str, str], db_session
):
    """composition adapter 能装配出满足 phase-B 不变量的真实 V1 launch。

    覆盖「只让单元测试通过、但真实装配失败」的反面：adapter 用真实 session 与
    真实 PostgreSQL 身份事实解析出 launch，且 binding/context 恒 None、policy
    version 与 capability snapshot 取自 execution 侧冻结常量。
    """
    identity = await _bootstrap_v1_identity(db_session)

    policy = build_v1_launch_policy(db_session)
    assert isinstance(policy, V1CompatibilityLaunchPolicy)
    assert isinstance(policy._facts, ExecutionRuntimeLaunchFactsAdapter)

    launch = await policy.build_launch(
        tenant_id=DEFAULT_TENANT_ID,
        agent_definition_version_id=identity.agent_definition_version.id,
    )

    # §1 / §2：binding、context 与 parent 恒 None（compatibility 路径）。
    assert launch.runtime_binding_id is None
    assert launch.parent_run_id is None
    assert launch.context_snapshot_ref is None
    assert launch.context_snapshot_digest is None
    assert launch.context_snapshot_classification is None

    # §2.3：server-selected 事实取自 execution 侧冻结常量，客户端无法放大。
    assert launch.run_config_snapshot.model_profile_key is None
    assert launch.run_config_snapshot.autonomy_level == 0
    assert launch.run_config_snapshot.tool_keys == ()
    assert launch.run_config_snapshot.policy_version == "compat.direct_rag.v1"
    assert launch.runtime_capability_snapshot.runtime_kind == "compatibility"
    assert launch.runtime_capability_snapshot.adapter_key == "direct_rag"

    # §2：budget 六项与 launch 顶层快照一致。
    assert launch.budget_snapshot == launch.run_config_snapshot.budget
    assert launch.budget_snapshot.max_steps == 2
    assert launch.budget_snapshot.max_wall_seconds == 300
    assert launch.budget_snapshot.max_tokens == 100_000
    assert launch.budget_snapshot.max_cost_micros == 2_000_000
    assert launch.budget_snapshot.max_tool_calls == 1
    assert launch.budget_snapshot.max_retries == 0

    # 解析到的是 seed tenant 内登记的 V1 profile。
    assert launch.runtime_profile_id == identity.runtime_profile.id
    assert launch.agent_definition_version_id == (
        identity.agent_definition_version.id
    )
