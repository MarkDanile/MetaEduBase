"""R1-S4-B M2：transport/external aggregate 集合 advisory lock 真实 PostgreSQL 验证。

覆盖（Plan §R1-S4 B4 + D8 锁链矩阵）：
- key 派生确定性：同四元组 -> 同 key；任一维度变化 -> 不同 key；空 owner_key /
  source_table fail closed（ValueError）。
- key 域隔离：集合锁 key 与 ``conversation_owner_key`` / ``conversation_guard_key``
  不同输出域（独立版本前缀），同 material 不跨域复用。
- 事务级互斥（真实 PG）：两个并发事务对同一四元组取 ``pg_advisory_xact_lock``
  严格互斥（一个持有期间另一个阻塞）；不同四元组不互斥。
- 不依赖数据行：对不存在的 source_row_id（空集合/源行已删）也能取锁。

边界（S4-B）：本模块只提供锁原语，不接线 writer/claim/participant/scheduler。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.agent_erasure_locks import (
    acquire_transport_aggregate_lock,
    conversation_owner_key,
    transport_aggregate_key,
)
from tests.conftest import TEST_DB_URL

_TENANT = uuid.UUID("71000000-0000-0000-0000-000000000001")
_OWNER = "workspace.transport.v1"
_SOURCE_TABLE = "agent_workspace_outbox"


def _factory():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_key_derivation_deterministic_and_distinct():
    row = uuid.uuid4()
    k1 = transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key=_OWNER,
        source_table=_SOURCE_TABLE,
        source_row_id=row,
    )
    k2 = transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key=_OWNER,
        source_table=_SOURCE_TABLE,
        source_row_id=row,
    )
    assert k1 == k2, "同四元组必须派生同 key"
    assert isinstance(k1, int)
    # 任一维度变化 -> 不同 key。
    assert k1 != transport_aggregate_key(
        tenant_id=uuid.uuid4(),
        owner_key=_OWNER,
        source_table=_SOURCE_TABLE,
        source_row_id=row,
    )
    assert k1 != transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key="execution.transport.v1",
        source_table=_SOURCE_TABLE,
        source_row_id=row,
    )
    assert k1 != transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key=_OWNER,
        source_table="agent_execution_outbox",
        source_row_id=row,
    )
    assert k1 != transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key=_OWNER,
        source_table=_SOURCE_TABLE,
        source_row_id=uuid.uuid4(),
    )


def test_key_derivation_fail_closed_on_empty():
    row = uuid.uuid4()
    with pytest.raises(ValueError, match="owner_key"):
        transport_aggregate_key(
            tenant_id=_TENANT,
            owner_key="",
            source_table=_SOURCE_TABLE,
            source_row_id=row,
        )
    with pytest.raises(ValueError, match="source_table"):
        transport_aggregate_key(
            tenant_id=_TENANT,
            owner_key=_OWNER,
            source_table="",
            source_row_id=row,
        )


def test_key_domain_isolated_from_owner_key():
    """集合锁与 owner lock 不同输出域：即使同 tenant+conversation，前缀不同 -> key 不同。"""
    conv = uuid.uuid4()
    agg = transport_aggregate_key(
        tenant_id=_TENANT,
        owner_key=_OWNER,
        source_table=_SOURCE_TABLE,
        source_row_id=conv,
    )
    owner = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=conv, owner_key=_OWNER
    )
    assert agg != owner, "不同版本前缀必须把集合锁与 owner 锁分到不同输出域"


def test_key_version_prefix_is_distinct_and_frozen():
    """反例（变异 KILLED）：集合锁版本前缀必须独立、且为契约冻结值
    ``metaedu.agent.transport.agg.v1\\x00``——若被改成与 owner/guard 相同前缀
    （域隔离失效）或被改成别的值（key 漂移、跨部署不一致），本测试转红。"""
    from app.composition import agent_erasure_locks as locks

    agg_prefix = locks._TRANSPORT_AGG_KEY_V1_PREFIX
    owner_prefix = locks._OWNER_KEY_V1_PREFIX
    assert agg_prefix == b"metaedu.agent.transport.agg.v1\x00", (
        "集合锁前缀必须是契约冻结值 metaedu.agent.transport.agg.v1；"
        "改动会导致 key 漂移、跨部署 advisory lock 不再互斥"
    )
    assert agg_prefix != owner_prefix, "集合锁前缀不得与 owner 锁前缀相同（域隔离失效）"


@pytest.mark.asyncio
async def test_advisory_lock_mutual_exclusion_real_pg():
    """真实 PG：两个事务对同一四元组取 xact advisory lock 严格互斥。"""
    engine, factory = _factory()
    row = uuid.uuid4()
    acquired_first = asyncio.Event()
    release_first = asyncio.Event()
    second_acquired_while_first_held = False

    async def holder():
        async with factory() as session, session.begin():
            await acquire_transport_aggregate_lock(
                session,
                tenant_id=_TENANT,
                owner_key=_OWNER,
                source_table=_SOURCE_TABLE,
                source_row_id=row,
            )
            acquired_first.set()
            # 持锁直到被要求释放（事务结束才释放 xact 锁）。
            await release_first.wait()

    async def contender():
        nonlocal second_acquired_while_first_held
        await acquired_first.wait()
        async with factory() as session, session.begin():
            # 用短超时模拟取锁：第一事务持锁期间应阻塞 -> TimeoutError。
            try:
                await asyncio.wait_for(
                    acquire_transport_aggregate_lock(
                        session,
                        tenant_id=_TENANT,
                        owner_key=_OWNER,
                        source_table=_SOURCE_TABLE,
                        source_row_id=row,
                    ),
                    timeout=0.5,
                )
                second_acquired_while_first_held = True
            except TimeoutError:
                second_acquired_while_first_held = False
                # 超时中断锁等待后事务处于 aborted 态，回滚以便干净退出。
                await session.rollback()

    hold_task = asyncio.create_task(holder())
    contend_task = asyncio.create_task(contender())
    await contend_task
    assert (
        second_acquired_while_first_held is False
    ), "第一事务持锁期间第二事务必须阻塞（xact advisory lock 互斥）"
    release_first.set()
    await hold_task
    await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_distinct_keys_not_blocking():
    """不同四元组的 advisory lock 互不阻塞。"""
    engine, factory = _factory()
    row_a, row_b = uuid.uuid4(), uuid.uuid4()
    async with factory() as s1, s1.begin():
        await acquire_transport_aggregate_lock(
            s1,
            tenant_id=_TENANT,
            owner_key=_OWNER,
            source_table=_SOURCE_TABLE,
            source_row_id=row_a,
        )
        # 不同 key 应能立即获取（不阻塞）。
        async with factory() as s2, s2.begin():
            await asyncio.wait_for(
                acquire_transport_aggregate_lock(
                    s2,
                    tenant_id=_TENANT,
                    owner_key=_OWNER,
                    source_table=_SOURCE_TABLE,
                    source_row_id=row_b,
                ),
                timeout=1.0,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_advisory_lock_works_without_source_row():
    """空集合/源行已删（source_row_id 不存在任何表）也能取锁——不依赖数据行。"""
    engine, factory = _factory()
    phantom = uuid.uuid4()  # 不存在于任何 transport 表
    async with factory() as session, session.begin():
        # 不抛即通过：advisory lock 无需数据行即可获取。
        await acquire_transport_aggregate_lock(
            session,
            tenant_id=_TENANT,
            owner_key=_OWNER,
            source_table=_SOURCE_TABLE,
            source_row_id=phantom,
        )
    await engine.dispose()
