"""TD-114 显式初始化编排的 composition 层真实 PostgreSQL contract tests。

契约验收归属（§10-A 组，composition 真实 PG）：

- A-2 tenant 隔离
- A-3 重复调用幂等（composition 侧）
- A-4 并发（独立连接/独立事务）
- A-5 注入式中途失败整体回滚 + 重试
- A-6 状态矩阵（全缺失/部分缺失×2/完整/disabled/draft/retired/digest 冲突/
  身份冲突/自定义记录保留；预置冲突 409 分支零写入）
- A-7 disabled profile 不自动启用
- A-9 并发下 created 归属 = 实际插入行数（RETURNING 判定）
- V1 内容等价钉住：本模块 digest 与 ``bootstrap_direct_rag`` 实际写库值一致

测试直验数据库最终状态；真实 PostgreSQL；不 mock repository。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.agent_identity_bootstrap import (
    ExecutionIdentityBootstrapAdapter,
    build_agent_identity_bootstrap,
)
from app.contexts.agent_execution.application.execution_identity_service import (
    ExecutionIdentityService,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    RuntimeProfileModel,
)
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio

TENANT_A = uuid.UUID("40000000-0000-4000-8000-0000000000a1")
TENANT_B = uuid.UUID("50000000-0000-4000-8000-0000000000b1")
ACTOR = uuid.UUID("40000000-0000-4000-8000-0000000000a2")


async def _row_counts(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, int]:
    definitions = (
        await session.execute(
            select(func.count())
            .select_from(AgentDefinitionVersionModel)
            .where(AgentDefinitionVersionModel.tenant_id == tenant_id)
        )
    ).scalar_one()
    profiles = (
        await session.execute(
            select(func.count())
            .select_from(RuntimeProfileModel)
            .where(RuntimeProfileModel.tenant_id == tenant_id)
        )
    ).scalar_one()
    return definitions, profiles


async def _seed_profile(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    config_digest: str,
    capability_digest: str,
    enabled: bool,
) -> None:
    """直接 INSERT 构造 profile 状态（publish 恒写 enabled=True，draft 态无写入路径）。"""
    now = await session.scalar(text("SELECT now()"))
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, "
            " config_digest, capability_digest, enabled, revision, "
            " created_at, updated_at) "
            "VALUES (:id, :tid, 'compat.direct_rag.v1', 'compatibility', "
            "        'direct_rag', :cd, :pd, :enabled, 1, :now, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "cd": config_digest,
            "pd": capability_digest,
            "enabled": enabled,
            "now": now,
        },
    )


async def _seed_definition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: str,
    digest: str,
    definition_key: str = "system.direct_rag",
) -> None:
    """直接 INSERT 构造 definition 状态（publish 恒写 published，无 draft 写入路径）。"""
    now = await session.scalar(text("SELECT now()"))
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, "
            " definition_digest, created_by, created_at) "
            "VALUES (:id, :tid, :key, 1, :status, :digest, :actor, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "key": definition_key,
            "status": status,
            "digest": digest,
            "actor": ACTOR,
            "now": now,
        },
    )


async def test_new_tenant_bootstrap_creates_exactly_one_row_each(db_session):
    """A 组基线：新 tenant 初始化——两表恰各 1 行，200 语义（initialized=True）。"""
    outcome = await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
        tenant_id=TENANT_A, actor_id=ACTOR
    )
    assert outcome.initialized is True
    assert outcome.disabled_existing is False
    assert outcome.conflict is False
    assert await _row_counts(db_session, TENANT_A) == (1, 1)


async def test_bootstrap_is_idempotent_and_tenant_scoped(db_session):
    """A-2 + A-3：重复调用同行同 id 零新增；tenant B 零变化。"""
    adapter = build_agent_identity_bootstrap(db_session)
    first = await adapter.bootstrap_v1_identity(tenant_id=TENANT_A, actor_id=ACTOR)
    replay = await adapter.bootstrap_v1_identity(tenant_id=TENANT_A, actor_id=ACTOR)
    assert first.initialized and replay.initialized
    assert await _row_counts(db_session, TENANT_A) == (1, 1)

    # tenant 隔离：初始化 B 不影响 A 的行；两 tenant 行各自独立
    other = await adapter.bootstrap_v1_identity(tenant_id=TENANT_B, actor_id=ACTOR)
    assert other.initialized
    assert await _row_counts(db_session, TENANT_A) == (1, 1)
    assert await _row_counts(db_session, TENANT_B) == (1, 1)
    rows_a = (
        (
            await db_session.execute(
                select(AgentDefinitionVersionModel.id).where(
                    AgentDefinitionVersionModel.tenant_id == TENANT_A
                )
            )
        )
        .scalars()
        .all()
    )
    rows_b = (
        (
            await db_session.execute(
                select(AgentDefinitionVersionModel.id).where(
                    AgentDefinitionVersionModel.tenant_id == TENANT_B
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows_a != rows_b


async def test_concurrent_bootstrap_produces_exactly_one_row_each(db_session):
    """A-4 + A-9：独立连接/独立事务并发——全成功、两表恰各 1 行、
    全局 created 计数 == 实际插入行数（RETURNING 归属判定）。"""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def run():
        async with factory() as session:
            detail = await build_agent_identity_bootstrap(session).bootstrap_v1_identity_with_stats(
                tenant_id=TENANT_A, actor_id=ACTOR
            )
            await session.commit()
            return detail

    try:
        results = await asyncio.gather(run(), run(), run())
    finally:
        await engine.dispose()

    assert all(r.outcome.initialized for r in results)
    assert sum(r.created for r in results) == 2  # definition 1 + profile 1
    assert await _row_counts(db_session, TENANT_A) == (1, 1)


async def test_partial_failure_rolls_back_both_writes(db_session, monkeypatch):
    """A-5：注入式中途失败——definition 已成功写入后 profile 写方法抛错。

    断言事务整体回滚（两表均不残留）；撤除注入后重试成功且幂等。
    真实 PG + 真实事务语义；不以 mock 返回值或写前查询冒充回滚证据。
    """
    from app.contexts.agent_execution.infrastructure.repository import (
        AgentExecutionIdentityRepository,
    )

    original = AgentExecutionIdentityRepository.insert_runtime_profile_if_absent

    async def boom(self, **kwargs):
        raise RuntimeError("injected profile write failure")

    monkeypatch.setattr(AgentExecutionIdentityRepository, "insert_runtime_profile_if_absent", boom)
    with pytest.raises(RuntimeError, match="injected profile write failure"):
        await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
            tenant_id=TENANT_A, actor_id=ACTOR
        )
    # route 语义：异常即整体回滚
    await db_session.rollback()
    assert await _row_counts(db_session, TENANT_A) == (0, 0)

    # 撤除注入后重试：成功、两表恰各 1 行；再次重试幂等
    monkeypatch.setattr(
        AgentExecutionIdentityRepository,
        "insert_runtime_profile_if_absent",
        original,
    )
    outcome = await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
        tenant_id=TENANT_A, actor_id=ACTOR
    )
    assert outcome.initialized is True
    assert await _row_counts(db_session, TENANT_A) == (1, 1)
    replay = await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
        tenant_id=TENANT_A, actor_id=ACTOR
    )
    assert replay.initialized is True
    assert await _row_counts(db_session, TENANT_A) == (1, 1)


async def test_state_matrix(db_session):
    """A-6：§4 状态矩阵逐项；冲突分支零写入。"""
    adapter = build_agent_identity_bootstrap(db_session)

    # 部分缺失：仅 definition
    t_partial_def = uuid.uuid4()
    await _seed_definition(
        db_session, t_partial_def, status="published", digest=_v1_definition_digest()
    )
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_partial_def, actor_id=ACTOR)
    assert outcome.initialized and not outcome.conflict
    assert await _row_counts(db_session, t_partial_def) == (1, 1)

    # 部分缺失：仅 profile
    t_partial_profile = uuid.uuid4()
    await _seed_profile(
        db_session,
        t_partial_profile,
        config_digest=_v1_profile_config_digest(),
        capability_digest=_v1_capability_digest(),
        enabled=True,
    )
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_partial_profile, actor_id=ACTOR)
    assert outcome.initialized and not outcome.conflict
    assert await _row_counts(db_session, t_partial_profile) == (1, 1)

    # draft definition → conflict，零写入
    t_draft = uuid.uuid4()
    await _seed_definition(db_session, t_draft, status="draft", digest=_v1_definition_digest())
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_draft, actor_id=ACTOR)
    assert outcome.conflict and not outcome.initialized
    assert outcome.conflict_reason is not None
    assert await _row_counts(db_session, t_draft) == (1, 0)

    # retired definition → conflict
    t_retired = uuid.uuid4()
    await _seed_definition(db_session, t_retired, status="retired", digest=_v1_definition_digest())
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_retired, actor_id=ACTOR)
    assert outcome.conflict
    assert await _row_counts(db_session, t_retired) == (1, 0)

    # definition digest 冲突 → conflict，不覆盖
    t_digest = uuid.uuid4()
    await _seed_definition(db_session, t_digest, status="published", digest="f" * 64)
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_digest, actor_id=ACTOR)
    assert outcome.conflict
    assert await _row_counts(db_session, t_digest) == (1, 0)

    # profile 身份冲突（digest 不符）→ conflict，不覆盖
    t_pdigest = uuid.uuid4()
    await _seed_profile(
        db_session,
        t_pdigest,
        config_digest=_v1_profile_config_digest(),
        capability_digest="f" * 64,
        enabled=True,
    )
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_pdigest, actor_id=ACTOR)
    assert outcome.conflict
    assert await _row_counts(db_session, t_pdigest) == (0, 1)

    # 自定义记录（其他 key）零触碰
    t_custom = uuid.uuid4()
    await _seed_definition(
        db_session,
        t_custom,
        status="published",
        digest="a" * 64,
        definition_key="custom.other",
    )
    outcome = await adapter.bootstrap_v1_identity(tenant_id=t_custom, actor_id=ACTOR)
    assert outcome.initialized and not outcome.conflict
    custom_rows = (
        await db_session.execute(
            select(func.count())
            .select_from(AgentDefinitionVersionModel)
            .where(
                AgentDefinitionVersionModel.tenant_id == t_custom,
                AgentDefinitionVersionModel.definition_key == "custom.other",
            )
        )
    ).scalar_one()
    assert custom_rows == 1  # 自定义行保留
    assert await _row_counts(db_session, t_custom) == (2, 1)  # + V1 definition


async def test_disabled_profile_is_reported_not_reenabled(db_session):
    """A-7：disabled profile —— initialized=True + disabled_existing=True，
    enabled 保持 false（不自动启用）。"""
    t_disabled = uuid.uuid4()
    await _seed_definition(
        db_session, t_disabled, status="published", digest=_v1_definition_digest()
    )
    await _seed_profile(
        db_session,
        t_disabled,
        config_digest=_v1_profile_config_digest(),
        capability_digest=_v1_capability_digest(),
        enabled=False,
    )
    outcome = await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
        tenant_id=t_disabled, actor_id=ACTOR
    )
    assert outcome.initialized is True
    assert outcome.disabled_existing is True
    assert outcome.conflict is False
    enabled = (
        await db_session.execute(
            select(RuntimeProfileModel.enabled).where(RuntimeProfileModel.tenant_id == t_disabled)
        )
    ).scalar_one()
    assert enabled is False
    assert await _row_counts(db_session, t_disabled) == (1, 1)


async def test_v1_digests_match_bootstrap_direct_rag(db_session):
    """等价钉住：本模块 V1 digest 与 bootstrap_direct_rag 实际写库值一致。

    payload 形状漂移（execution_identity_service.py 改动）会使本测试转红，
    避免 bootstrap 端点与 compatibility 懒路径写库内容静默分叉。
    """
    t_compat = uuid.uuid4()
    identity = await ExecutionIdentityService(db_session).bootstrap_direct_rag(
        tenant_id=t_compat, actor_id=ACTOR
    )
    await db_session.commit()

    from app.composition import agent_identity_bootstrap as module

    assert identity.agent_definition_version.definition_digest == (module._V1_DEFINITION_DIGEST)
    assert identity.runtime_profile.config_digest == module._V1_PROFILE_CONFIG_DIGEST
    assert identity.runtime_profile.capability_digest == module._V1_CAPABILITY_DIGEST
    # 双路径写同 tenant 幂等同行（publish-or-get / insert-if-absent 殊途同归）
    outcome = await build_agent_identity_bootstrap(db_session).bootstrap_v1_identity(
        tenant_id=t_compat, actor_id=ACTOR
    )
    assert outcome.initialized and not outcome.conflict
    assert await _row_counts(db_session, t_compat) == (1, 1)


def _v1_definition_digest() -> str:
    from app.composition.agent_identity_bootstrap import _V1_DEFINITION_DIGEST

    return _V1_DEFINITION_DIGEST


def _v1_profile_config_digest() -> str:
    from app.composition.agent_identity_bootstrap import _V1_PROFILE_CONFIG_DIGEST

    return _V1_PROFILE_CONFIG_DIGEST


def _v1_capability_digest() -> str:
    from app.composition.agent_identity_bootstrap import _V1_CAPABILITY_DIGEST

    return _V1_CAPABILITY_DIGEST


# 保持对 ExecutionIdentityBootstrapAdapter 显式继承 port 的静态锚定。
# （Protocol 非 runtime_checkable，用 __mro__ 而非 issubclass。）
async def test_adapter_explicitly_implements_port():
    from app.contexts.agent_workspace.application.ports import (
        AgentIdentityBootstrapPort,
    )

    assert AgentIdentityBootstrapPort in ExecutionIdentityBootstrapAdapter.__mro__
