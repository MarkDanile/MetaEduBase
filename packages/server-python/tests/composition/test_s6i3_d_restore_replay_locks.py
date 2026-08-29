# ruff: noqa: E501
"""R1-S6-I3-D D2: M-class maintenance advisory lock helpers 真实 PG 验收。

契约：用户裁决 A（M 类互斥 = global advisory maintenance lock）；
Plan §R1-S6-8.3 / §R1-S6-13 / §S6-4 锁序登记。
- retention/audit 每个事务先取 ``pg_advisory_xact_lock_shared`` 早于一切 DB 锁
- replay 事务取 ``pg_advisory_xact_lock`` exclusive 早于一切 DB 锁
- 同一 stable namespace/scope；global key（不按 tenant 切分；M 类是维护路径串行化）

数据库硬边界：仅 ``metaedu_test``；不修改 schema / 不开新 transaction。
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
    acquire_maintenance_exclusive_lock,
    acquire_maintenance_shared_lock,
    maintenance_lock_key,
)
from tests.conftest import TEST_DB_URL

# 任意 tenant；M 类 key 是 global，不依赖 tenant_id
_TENANT = uuid.UUID("71000000-0000-0000-0000-000000000099")


def _factory():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_maintenance_lock_key_is_stable_and_64bit():
    """key 必须稳定且可放入 signed 64-bit（pg_advisory_xact_lock 签名约束）。"""
    k1 = maintenance_lock_key()
    k2 = maintenance_lock_key()
    assert k1 == k2, "同一调用必须派生同一 key"
    assert isinstance(k1, int)
    # signed 64-bit：[-2^63, 2^63 - 1]
    assert -(2**63) <= k1 < 2**63, f"key 越界 signed 64-bit: {k1}"


def test_maintenance_lock_key_prefix_is_frozen():
    """反例（mutation KILLED）：前缀必须是契约冻结值；改前缀会跨部署锁漂移。

    任何前缀改动（去版本 / 改名字 / 删 NUL）→ 此测试转红 + 同 key 派生 hash 改变。
    """
    from app.composition import agent_erasure_locks as locks

    prefix = locks._MAINTENANCE_KEY_V1_PREFIX
    assert prefix == b"metaedu.agent.maintenance.v1\x00", (
        "maintenance lock 前缀必须是契约冻结值 metaedu.agent.maintenance.v1；"
        "改动会导致 key 漂移、跨部署 advisory lock 不再互斥"
    )
    # 必须独立于 owner lock / transport aggregate lock 前缀（域隔离）
    assert prefix != locks._OWNER_KEY_V1_PREFIX
    assert prefix != locks._TRANSPORT_AGG_KEY_V1_PREFIX


@pytest.mark.asyncio
async def test_maintenance_shared_blocks_against_exclusive_real_pg():
    """real PG：exclusive 持有期间 shared 申请必须阻塞。"""
    engine, factory = _factory()
    acquired_exclusive = asyncio.Event()
    release_exclusive = asyncio.Event()
    shared_during_exclusive_blocked = False

    async def exclusive_holder():
        async with factory() as session, session.begin():
            await acquire_maintenance_exclusive_lock(session)
            acquired_exclusive.set()
            await release_exclusive.wait()

    async def shared_contender():
        nonlocal shared_during_exclusive_blocked
        await acquired_exclusive.wait()
        async with factory() as session, session.begin():
            try:
                await asyncio.wait_for(
                    acquire_maintenance_shared_lock(session), timeout=0.5
                )
                shared_during_exclusive_blocked = True
            except TimeoutError:
                shared_during_exclusive_blocked = False
                await session.rollback()

    hold = asyncio.create_task(exclusive_holder())
    contend = asyncio.create_task(shared_contender())
    await contend
    assert (
        shared_during_exclusive_blocked is False
    ), "exclusive 持锁期间 shared 申请必须阻塞"
    release_exclusive.set()
    await hold
    await engine.dispose()


@pytest.mark.asyncio
async def test_maintenance_shared_coexist_real_pg():
    """real PG：两个 shared 不互斥（PG advisory lock shared 语义）。"""
    engine, factory = _factory()
    both_held = asyncio.Event()
    release = asyncio.Event()

    async def holder_a():
        async with factory() as session, session.begin():
            await acquire_maintenance_shared_lock(session)
            both_held.set()
            await release.wait()

    async def holder_b():
        await both_held.wait()
        async with factory() as session, session.begin():
            await asyncio.wait_for(
                acquire_maintenance_shared_lock(session), timeout=1.0
            )
            # 进入此行 = 第二个 shared 立即取得

    ta = asyncio.create_task(holder_a())
    tb = asyncio.create_task(holder_b())
    await tb
    release.set()
    await ta
    await engine.dispose()


@pytest.mark.asyncio
async def test_maintenance_exclusive_blocks_against_exclusive_real_pg():
    """real PG：两个 exclusive 严格互斥。"""
    engine, factory = _factory()
    acquired_first = asyncio.Event()
    release_first = asyncio.Event()
    second_acquired = False

    async def holder_first():
        async with factory() as session, session.begin():
            await acquire_maintenance_exclusive_lock(session)
            acquired_first.set()
            await release_first.wait()

    async def contender_second():
        nonlocal second_acquired
        await acquired_first.wait()
        async with factory() as session, session.begin():
            try:
                await asyncio.wait_for(
                    acquire_maintenance_exclusive_lock(session), timeout=0.5
                )
                second_acquired = True
            except TimeoutError:
                second_acquired = False
                await session.rollback()

    h = asyncio.create_task(holder_first())
    c = asyncio.create_task(contender_second())
    await c
    assert second_acquired is False, "第一 exclusive 持锁期间第二 exclusive 必须阻塞"
    release_first.set()
    await h
    await engine.dispose()


# ---------------------------------------------------------------------------
# retention worker integration（Task 3 在此模块追加时一并验证）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retention_worker_takes_shared_lock_succeeds(session_factory):
    """retention worker 启动期取 shared maintenance lock；空 tenant 无候选应立即返回。"""
    from app.composition.retention_workers import run_event_retention
    from tests.composition.s6i3_seeds import _seed_tenant

    factory = session_factory
    async with factory() as s, s.begin():
        await _seed_tenant(s)
    # retention 在空 tenant 上无候选，应立即返回零计数（且不抛错）
    result = await run_event_retention(factory)
    assert result.runs_processed == 0


@pytest.mark.asyncio
async def test_replay_exclusive_blocks_retention_worker(session_factory):
    """exclusive lock 持有期间 retention worker 应被阻塞（用户裁决 A）。"""
    from app.composition.retention_workers import run_event_retention
    from tests.composition.s6i3_seeds import _seed_tenant

    factory = session_factory
    async with factory() as s, s.begin():
        await _seed_tenant(s)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    exclusive_factory = async_sessionmaker(engine, expire_on_commit=False)
    acquired_exclusive = asyncio.Event()
    release_exclusive = asyncio.Event()

    async def exclusive_holder():
        async with exclusive_factory() as session, session.begin():
            await acquire_maintenance_exclusive_lock(session)
            acquired_exclusive.set()
            await release_exclusive.wait()

    hold = asyncio.create_task(exclusive_holder())
    await acquired_exclusive.wait()

    # retention worker 在 exclusive 持锁期间应阻塞
    retention_task = asyncio.create_task(run_event_retention(factory))
    retention_blocked = False
    try:
        await asyncio.wait_for(asyncio.shield(retention_task), timeout=0.5)
        retention_blocked = False  # 完成了（不应发生）
    except TimeoutError:
        retention_blocked = True
        retention_task.cancel()

    release_exclusive.set()
    await hold
    await engine.dispose()
    assert retention_blocked is True, (
        "exclusive lock 持有期间 retention worker 应阻塞（共享申请被独占持有者阻塞）"
    )
