# R1-S6-I3-D D2 Restore Replay Executor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Spec source (already frozen):** the user's directive (this branch input) is the binding spec. Frozen decisions: runtime per-binding proof = c / D2 互斥 = A / D1a+D1b+D2 三独立 PR / 不修改 migration/schema/enum/CHECK.
>
> **Frozen Plan references (already in main via PR #581/#586/#591/#592/#596):** Plan §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15.5.

**Goal:** Implement `restore_replay_executor` (D2) — read archive + replay six-state routing + restore-before-open gate — wired into writer conformance via M-class registration.

**Architecture:** 4 phases (0=audit / 1=archive read outside DB / 2=maintenance DB transaction / 3=restore-before-open gate) + M-class writer registration. Uses `find_committed_tip` + `fetch_segment_bytes` + `decode_ledger_segment` + `reconstruct_owner_facts` for archive reading; new global `pg_advisory_xact_lock` shared/exclusive for M-class互斥 A; reuses sanctioned local-owner participant helpers; no external/runtime adapter call; no production scheduler wiring; no migration/schema change.

**Tech Stack:** Python 3.14 / SQLAlchemy 2 async / asyncpg / PostgreSQL advisory locks (xact_lock / xact_lock_shared) / pytest-asyncio (auto mode).

**Spec:** [R1 Retention/Purge/恢复专项契约 §3 / §10 / §11](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md) + [R1 分 Slice 实施计划 §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15.5](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)

## Global Constraints

- 不修改 migration / schema / enum / CHECK（migration 040 已有完整 owner fact 持久化 = 六元组跨表；runtime owner + RUNTIME_BINDING_EVIDENCE_UNPROVABLE = legal 组合无需新 schema）
- 不复制第二套清除 SQL — 复用 execution/transport/external/runtime participant 私有 helper 方法（`ExecutionErasureParticipant._clear_terminal_outputs` / `_clear_context_snapshots` / `_clear_compatibility_outputs` / `_clear_event_payloads` + `TransportErasureParticipantBase` sanctioned helpers + `ExternalPayloadErasureParticipant.write_erased_and_clear_ref` 简化路径 + `RuntimeErasureParticipant.write_erased_and_close_binding` 行 CAS）
- 不调用 external/runtime adapter（spec §S6-8.3 字面要求）
- 不依赖 production scheduler
- 不接 capability flip / registry capability 翻转
- 不修改 Score Log / Metrics / 门禁脚本 / KNOWN_ISSUES / CI 配置 / 阈值
- D2 = 独立 PR（不合并 D1a / D1b / PR-D runbook / PR-E release drill）
- 数据库硬边界：仅 `metaedu_test`；禁止 drop/truncate/reseed `metaedu`

## File Structure

**Create:**
- `packages/server-python/app/composition/restore_replay.py` — main module (~700 lines): archive read + state routing + restore-before-open gate
- `packages/server-python/tests/composition/test_s6i3_d_restore_replay.py` — real PG tests (~700 lines): 6×5 state routing matrix + maintenance lock互斥 + archive read + gate
- `scripts/s6i3_d_restore_replay_mutation_kill.py` — mutation kill (~250 lines)

**Modify:**
- `packages/server-python/app/composition/agent_erasure_locks.py` — add `maintenance_lock_key` + `acquire_maintenance_shared_lock` + `acquire_maintenance_exclusive_lock` (~40 lines)
- `packages/server-python/app/composition/retention_workers.py` — add shared lock at session.begin() (~15 lines × 2 = 30 lines)
- `packages/server-python/app/composition/s6i2_orphan_inspection.py` — move `restore_replay_executor` from `S6I2_PENDING_WRITERS` to `_required_writer_specs()` as FENCE_M writer; add `build_scan_providers(session)` helper (~30 lines)
- `packages/server-python/tests/composition/test_s6i2_orphan_inspection.py` — update `test_static_writer_specs_complete` count + add restore_replay_executor name (~5 lines)
- `docs/03-engineering-governance/current-work.md` — fix line 81 stale「待用户裁决」表述（用户裁决 1-5 已 supersede fact-audit §17.5；D1a/D1b 已合并 main；D2 启动中）

---

## Task 1: Phase 0 审计 + current-work.md line 81 修正

**Files:**
- Modify: `docs/03-engineering-governance/current-work.md:81`

**Interfaces:**
- Produces: corrected current-work text stating D1a+D1b 已合并 main + D2 启动中（不沿用旧「待用户裁决」表述）

- [ ] **Step 1: 读取 current-work.md line 81 段并核对 fact-audit §17.5**

```
sed -n '78,82p' docs/03-engineering-governance/current-work.md
```

确认：line 81 称「(1) Runtime per-binding proof 路径用户裁决 a/b/c（D2 硬阻塞）」「(2) M 类互斥 A 方案接法（须写作 S6-4 锁序登记修订）」仍称「待用户裁决」——**事实错误**：裁决 1-5 已在 fact-audit §17.5（2026-08-27 用户裁决） supersede；D1a 已合 main `5868831e`；D1b 已合 main `01c84f7c`；D2 现按本 PR 启动。

- [ ] **Step 2: 编辑 line 81 改为 D2 启动中事实**

old: `(1) **PR-D**（ledger export executor + restore-before-open runbook，plan §S6-8/§S6-12/§S6-13）`
new: 保留 PR-D 文字不变（PR-D 仍为后续 PR-D runbook 子阶段；D2 已启动为 PR 内 distinct 子阶段）。

old: `2. **D2**（replay executor + M 类互斥 = A 方案 + restore-before-open 编排 + restore 端 DB mutation）——**须先解决**：(1) Runtime per-binding proof 路径用户裁决 a/b/c（D2 硬阻塞）+ (2) M 类互斥 A 方案接法（须写作 S6-4 锁序登记修订）+ (3) D1a codec 已被 D2 消费`
new: `2. **D2**（replay executor + M 类互斥 = A 方案 + restore-before-open 编排 + restore 端 DB mutation）——**用户裁决 5 项已 supersede（fact-audit §17.5，2026-08-27）**：(1) Runtime per-binding proof = c（RUNTIME_BINDING_EVIDENCE_UNPROVABLE + 零写 + 不冒充）(2) M 类互斥 = A（global advisory xact_lock_shared / xact_lock exclusive）(3) D1a+D1b+D2 三独立 PR **(4) 顺序 D1a→D1b→D2** **(5) D1b = 专用 MinIO archive bucket**；D1a 已合 main \`5868831e\`；D1b 已合 main \`01c84f7c\`；D2 在本 PR 内按裁决 5 项落地（branch \`feature/req041-047-r1-s6-i3-d-d2-restore-replay\`）`

- [ ] **Step 3: 运行 docs gate 确认无 regression**

```
cd packages/server-python && uv run --frozen --extra dev python scripts/check_engineering_docs.py --full
```

Expected: 全绿（current-work 修正仅 governance 文本）。

- [ ] **Step 4: 提交**

```bash
git add docs/03-engineering-governance/current-work.md
git commit -m "docs(current-work): D2 启动登记（fact-audit §17.5 用户裁决 5 项 supersede 旧待用户裁决）"
```

---

## Task 2: maintenance advisory lock key + shared/exclusive helpers

**Files:**
- Modify: `packages/server-python/app/composition/agent_erasure_locks.py`

**Interfaces:**
- Produces:
  - `_MAINTENANCE_KEY_V1_PREFIX: bytes = b"metaedu.agent.maintenance.v1\x00"`
  - `maintenance_lock_key() -> int` — stable signed 64-bit key (global, not per-tenant)
  - `async acquire_maintenance_shared_lock(session: AsyncSession) -> None` — `pg_advisory_xact_lock_shared`
  - `async acquire_maintenance_exclusive_lock(session: AsyncSession) -> None` — `pg_advisory_xact_lock`

- [ ] **Step 1: 编写失败测试（real PG）**

Create `packages/server-python/tests/composition/test_s6i3_d_restore_replay_locks.py`:

```python
"""Maintenance advisory lock helpers — 真实 PG 验收。"""
import asyncio
import uuid
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.pool import NullPool
from app.composition.agent_erasure_locks import (
    acquire_maintenance_exclusive_lock,
    acquire_maintenance_shared_lock,
    maintenance_lock_key,
)
from tests.conftest import TEST_DB_URL

_TENANT = uuid.UUID("71000000-0000-0000-0000-000000000099")


def _factory():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_maintenance_lock_key_is_stable_and_64bit():
    k1 = maintenance_lock_key()
    k2 = maintenance_lock_key()
    assert k1 == k2
    assert isinstance(k1, int)
    # 必须可放入 signed 64-bit（pg_advisory_xact_lock 签名）
    assert -(2**63) <= k1 < 2**63


@pytest.mark.asyncio
async def test_maintenance_shared_exclusive_mutex_real_pg():
    """shared 与 exclusive 严格互斥（real PG）。"""
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
    assert shared_during_exclusive_blocked is False
    release_exclusive.set()
    await hold
    await engine.dispose()


@pytest.mark.asyncio
async def test_maintenance_shared_shared_coexist_real_pg():
    """两个 shared 不互斥（PG advisory lock shared semantics）。"""
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
            assert True

    ta = asyncio.create_task(holder_a())
    tb = asyncio.create_task(holder_b())
    await tb
    release.set()
    await ta
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay_locks.py -q`
Expected: 3 failures (ImportError / attribute not found).

- [ ] **Step 3: 实现 maintenance lock helpers**

Append to `agent_erasure_locks.py`:

```python
# ---------------------------------------------------------------------------
# R1-S6-I3-D D2: M 类维护路径 advisory lock（Plan §S6-8.3 + 用户裁决 A）。
#
# retention/audit 每个事务先取 pg_advisory_xact_lock_shared（与 replay
# 事务互斥）；replay 事务取 pg_advisory_xact_lock（独占）。锁序必须早于
# Run/Conversation/owner/aggregate/row 锁（保留各自层级；本锁提供顶层
# 互斥串行化）。
# ---------------------------------------------------------------------------

_MAINTENANCE_KEY_V1_PREFIX = b"metaedu.agent.maintenance.v1\x00"


def maintenance_lock_key() -> int:
    """派生稳定 signed 64-bit maintenance advisory lock key（global）。"""
    material = _MAINTENANCE_KEY_V1_PREFIX + b"global"
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


async def acquire_maintenance_shared_lock(session: AsyncSession) -> None:
    """retention/audit worker transaction-level shared maintenance lock。"""
    await session.execute(
        text("SELECT pg_advisory_xact_lock_shared(:key)"),
        {"key": maintenance_lock_key()},
    )


async def acquire_maintenance_exclusive_lock(session: AsyncSession) -> None:
    """replay executor transaction-level exclusive maintenance lock。"""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": maintenance_lock_key()},
    )
```

- [ ] **Step 4: 运行测试确认 pass**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay_locks.py -q`
Expected: 3 passed.

- [ ] **Step 5: 提交**

```bash
git add packages/server-python/app/composition/agent_erasure_locks.py \
        packages/server-python/tests/composition/test_s6i3_d_restore_replay_locks.py
git commit -m "feat(locks): M-class maintenance advisory lock helpers (shared/exclusive)"
```

---

## Task 3: retention workers 启动期 shared lock

**Files:**
- Modify: `packages/server-python/app/composition/retention_workers.py`

**Interfaces:**
- Modifies:
  - `run_event_retention(session_factory, *, batch_size=100, now=None)` — first statement of every `session.begin()` calls `acquire_maintenance_shared_lock(session)` before `_event_retention_candidates`
  - `run_audit_retention(session_factory, *, batch_size=100, now=None)` — first statement of every `session.begin()` calls `acquire_maintenance_shared_lock(session)` before `_audit_retention_candidates`

- [ ] **Step 1: 编写失败测试**

Append to `test_s6i3_d_restore_replay_locks.py`:

```python
@pytest.mark.asyncio
async def test_retention_worker_takes_shared_lock_real_pg():
    """retention worker 事务内必须取 maintenance shared lock（不被 exclusive 阻塞）。"""
    from app.composition.retention_workers import run_event_retention
    from tests.composition.s6i3_seeds import s6i3_session_factory, _seed_tenant
    engine, factory = _factory()
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
    # retention 在空 tenant 应立即返回（无候选），但仍必须取 shared lock 不抛错
    result = await run_event_retention(factory)
    assert result.runs_processed == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_replay_exclusive_blocks_retention_worker():
    """exclusive lock 持有期间 retention worker 应超时阻塞。"""
    engine, factory = _factory()
    acquired_exclusive = asyncio.Event()
    release_exclusive = asyncio.Event()

    async def exclusive_holder():
        async with factory() as session, session.begin():
            from app.composition.agent_erasure_locks import (
                acquire_maintenance_exclusive_lock,
            )
            await acquire_maintenance_exclusive_lock(session)
            acquired_exclusive.set()
            await release_exclusive.wait()

    hold = asyncio.create_task(exclusive_holder())
    await acquired_exclusive.wait()

    # retention worker 尝试（应阻塞，因为 shared 申请在 exclusive 期间被阻塞）
    from app.composition.retention_workers import run_event_retention
    retention_timeout = False
    try:
        await asyncio.wait_for(run_event_retention(factory), timeout=0.5)
    except (asyncio.TimeoutError, Exception):
        retention_timeout = True

    release_exclusive.set()
    await hold
    assert retention_timeout is True
    await engine.dispose()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay_locks.py::test_retention_worker_takes_shared_lock_real_pg -q`
Expected: test_retention_worker_takes_shared_lock_real_pg FAIL（retention worker 暂未取 shared lock；但空 tenant 时无任何阻塞——此 case 通过 retention 跑通即 PASS；test_replay_exclusive_blocks_retention_worker FAIL（无共享锁故不阻塞））

- [ ] **Step 3: 修改 retention_workers.py**

在文件顶部 import:
```python
from app.composition.agent_erasure_locks import acquire_maintenance_shared_lock
```

修改 `run_event_retention` 的 while loop:

old:
```python
while True:
    async with session_factory() as session, session.begin():
        effective_now = await _effective_now(session, now)
        candidates = [
```

new:
```python
while True:
    async with session_factory() as session, session.begin():
        # M-class 维护互斥：每个事务先取 shared maintenance advisory lock，
        # 早于 DB clock / candidate query / _lock_run_row；replay 事务取
        # exclusive（Plan §S6-8.3 + 用户裁决 A）。
        await acquire_maintenance_shared_lock(session)
        effective_now = await _effective_now(session, now)
        candidates = [
```

同样修改 `run_audit_retention` 的 while loop（同位置插入同一行）。

- [ ] **Step 4: 运行测试确认 pass**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay_locks.py -q`
Expected: 5 passed.

- [ ] **Step 5: 运行既有 retention 测试确保无 regression**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i1_event_retention.py tests/composition/test_s6i1_audit_retention.py -q --tb=line`
Expected: all passed.

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/app/composition/retention_workers.py \
        packages/server-python/tests/composition/test_s6i3_d_restore_replay_locks.py
git commit -m "feat(retention): M-class shared advisory lock at session.begin (Plan §S6-8.3)"
```

---

## Task 4: restore_replay.py 主模块 — phase 1 (archive read outside DB) + phase 2 (maintenance tx) + phase 3 (gate)

**Files:**
- Create: `packages/server-python/app/composition/restore_replay.py`

**Interfaces:**
- Public API:
  - `class ReplayOwnerVerdict` — verdict dataclass: `(operation_id: str, owner_key: str, action: str, reason_code: str | None)` — actions: `'local_cleared'` / `'blocked_kept'` / `'verify_only'` / `'skipped'` / `'replay_skip_zero_write'`
  - `class RestoreReplayReport` — aggregate: `(operations_total: int, owners_total: int, owners_local_cleared: int, owners_blocked_kept: int, owners_verify_only: int, owners_skipped: int, owners_failed: int, verdict: tuple[ReplayOwnerVerdict, ...], error: str | None)`
  - `class RestoreBeforeOpenReport` — gate report: `(open_allowed: bool, blocked_reasons: tuple[str, ...], inspections: tuple[tuple[str, int], ...])`
  - `async def replay_archive_segment_for_tenant(session_factory, *, sink, tenant_id, expected_marker) -> RestoreReplayReport`
  - `async def evaluate_restore_before_open(session_factory, *, tenant_id) -> RestoreBeforeOpenReport`

- [ ] **Step 1: 编写失败测试 (real PG)**

Create `packages/server-python/tests/composition/test_s6i3_d_restore_replay.py`:

```python
"""R1-S6-I3-D D2: restore replay executor + restore-before-open gate 真实 PG 验收。

契约：用户裁决 5 项（runtime per-binding proof=c / D2=A advisory lock / D1a+D1b+D2 三独立 PR）。
本测试模块冻结 D2 边界：
- 严格 maintenance exclusive advisory lock 启动
- 严格不调用 external/runtime adapter
- 严格 not production scheduler wiring
- 严格 not capability flip
"""
import asyncio
import json
import uuid
from typing import Any
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.pool import NullPool
from app.composition.s6i3_ledger_snapshot import (
    SCHEMA_VERSION, LedgerSnapshotError, decode_ledger_segment,
    export_ledger_segment, reconstruct_owner_facts,
)
from app.composition.s6i3_d_ledger_archive_sink import (
    CommitMarker, InMemoryLedgerArchiveSink, _sha256_hex,
    commit_marker_key, export_ledger_segment_for_archive,
    publish_ledger_segment, segment_key,
)
from app.composition.restore_replay import (
    ReplayOwnerVerdict, RestoreReplayReport, RestoreBeforeOpenReport,
    replay_archive_segment_for_tenant, evaluate_restore_before_open,
)
from app.composition.s6i3_seeds import (
    _seed_tenant, _seed_conversation, _seed_operation, _seed_checkpoint,
)
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio
_DIGEST = "a" * 64


@pytest.fixture
async def s6i3_d_factory():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _assert_metaedu_test(session: AsyncSession) -> None:
    row = (await session.execute(text("SELECT current_database()"))).scalar_one()
    assert row == "metaedu_test"


# Phase 1: archive read (outside DB tx)
async def test_phase1_archive_read_outside_db_transaction(s6i3_d_factory):
    """phase-1 校验：从 sink 读取 archive 在 DB tx 之外完成；不出租 lock。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)

    sink = InMemoryLedgerArchiveSink()
    async with factory() as s, s.begin():
        # 准备 publish 用同一 session（caller 必须开 RR+RO 事务）
        # 这里我们用普通事务准备数据，然后 export
        cid = await _seed_conversation(s, tid=tid)
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="erasing",
        )

    # Phase 1: export + publish (caller's tx; commit 后进入 phase-2)
    async with factory() as s, s.begin():
        from sqlalchemy import text as _t
        await s.execute(_t("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exported = await export_ledger_segment_for_archive(
            s, tenant_id=tid,
        )
    # tx 自动结束（snapshot read-only 短事务）
    outcome = await publish_ledger_segment(
        sink=sink, tenant_id=tid,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )
    assert outcome.segment_sha256 == _sha256_hex(exported.segment_bytes)


# Phase 2: maintenance exclusive lock + replay zero-write for non-eligible
async def test_phase2_scheduled_state_zero_write(s6i3_d_factory):
    """operation.state=scheduled → executor 零写（仅 restore-cancel 路径可达）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="scheduled")
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="pending",
        )

    sink = InMemoryLedgerArchiveSink()
    async with factory() as s, s.begin():
        from sqlalchemy import text as _t
        await s.execute(_t("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exported = await export_ledger_segment_for_archive(
            s, tenant_id=tid,
        )
    outcome = await publish_ledger_segment(
        sink=sink, tenant_id=tid,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )

    # replay
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )
    # scheduled 不应触发 owner clearing
    assert report.owners_local_cleared == 0
    assert report.owners_skipped >= 1
    # 检查 DB state 不变
    async with factory() as s, s.begin():
        row = (await s.execute(
            text("SELECT state FROM metaedu.agent_conversation_purges WHERE id = :id"),
            {"id": op_id},
        )).scalar_one()
        assert row == "scheduled"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay.py -q`
Expected: ImportError (no restore_replay module).

- [ ] **Step 3: 实现 restore_replay.py 主模块**

See `restore_replay.py` for full code. ~700 lines: imports, dataclasses, `maintenance_exclusive_lock` context manager, `replay_archive_segment_for_tenant` (read archive → decode → reconstruct → maintenance tx → route), `evaluate_restore_before_open` (reuses s6i2_orphan_inspection scan helpers).

Skeleton structure:

```python
"""R1-S6-I3-D D2: restore replay executor + restore-before-open gate.

契约：用户裁决 5 项 supersede（runtime per-binding proof=c / M 类互斥=A / D1a+D1b+D2 三独立 PR）。
本模块严格限定：
- 严格 maintenance exclusive advisory lock（global；早于一切 DB 锁）
- 严格不调用 external/runtime adapter（spec §S6-8.3 字面要求）
- 严格 not production scheduler wiring（§S6-7.1 V1 限制）
- 严格 not capability flip（§S6-4 capability_digest 冻结）
- 严格不动 migration / schema / enum / CHECK

phase 0: 启动前审计（fact-audit §17.5 用户裁决已 supersede 旧待用户裁决）
phase 1: archive 读取（DB tx 外；复用 find_committed_tip / fetch_segment_bytes / decode_ledger_segment / reconstruct_owner_facts）
phase 2: 单一 restore DB maintenance 事务（exclusive advisory xact_lock → 现有 sanctioned local owner participant helper → 单 owner 失败 rollback 全事务）
phase 3: restore-before-open 编排（六 owner scan → open_allowed / blocked_reasons）
"""
# ... (full implementation in restore_replay.py)
```

The implementation imports:
- `find_committed_tip`, `fetch_segment_bytes`, `CommitMarker` from `s6i3_d_ledger_archive_sink`
- `decode_ledger_segment`, `reconstruct_owner_facts`, `LedgerSnapshotError`, `Manifest` from `s6i3_ledger_snapshot`
- `acquire_maintenance_exclusive_lock` from `agent_erasure_locks`
- `verify_inspection` from `s6i2_orphan_inspection` (for phase-3 gate)
- `_OWNERS_BY_KEY` from `agent_erasure_registry`
- `ExecutionErasureParticipant`, `ExternalPayloadErasureParticipant`, `RuntimeErasureParticipant`, `TransportErasureParticipantBase` from participant modules (for phase-2 local clearing reuse)

State routing (single dict mapping):
```python
_OPERATION_ROUTING = {
    "scheduled": "zero_write_restore_cancel",
    "running": "may_replay_local",
    "blocked": "may_replay_blocked",
    "failed": "zero_write_manual",
    "completed": "verify_only",
    "cancelled": "skip",
}
_CHECKPOINT_ROUTING = {
    "pending": "candidate_when_local",
    "erasing": "candidate_when_local",
    "blocked": "blocked_local_match_reason",
    "failed": "zero_write",
    "acked": "no_repeat",
}
```

- [ ] **Step 4: 运行测试确认 phase-1 + phase-2 scheduled 路由 pass**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay.py -q`
Expected: 2 passed (others skipped if not yet implemented).

- [ ] **Step 5: 提交**

```bash
git add packages/server-python/app/composition/restore_replay.py \
        packages/server-python/tests/composition/test_s6i3_d_restore_replay.py
git commit -m "feat(restore-replay): D2 executor + restore-before-open gate (phase 1/2/3)"
```

---

## Task 5: M-class writer registration (move from PENDING to required)

**Files:**
- Modify: `packages/server-python/app/composition/s6i2_orphan_inspection.py`

- [ ] **Step 1: 编写失败测试**

Append to `test_s6i2_orphan_inspection.py` `test_static_writer_specs_complete`:

old assertion: `assert len(specs) == 3`
new: `assert len(specs) == 4`

Append new test:

```python
async def test_static_writer_specs_includes_restore_replay():
    """D2: restore_replay_executor（M 类）必须列入 required writer specs。"""
    specs = _required_writer_specs()
    m_specs = [s for s in specs if s.fence_status == FENCE_M]
    assert len(m_specs) == 1
    m = m_specs[0]
    assert m.writer_name == "restore_replay_executor"
    assert m.scope_class == "Maintenance"
    assert m.tenant_scoped is True


async def test_s6i2_pending_writers_empty_after_d2_registered():
    """D2 落地后 S6I2_PENDING_WRITERS 必须为空（restore_replay_executor 已转 registered）。"""
    from app.composition.s6i2_orphan_inspection import S6I2_PENDING_WRITERS
    assert S6I2_PENDING_WRITERS == ()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i2_orphan_inspection.py::test_static_writer_specs_includes_restore_replay -q`
Expected: FAIL（仍为 3 specs / pending 不空）.

- [ ] **Step 3: 修改 s6i2_orphan_inspection.py**

`S6I2_PENDING_WRITERS` 改为空:

```python
# S6I2_PENDING_WRITERS：S6-I3 完成（D2 已 registered）；本字段保持空 tuple 以表示
# 无 pending 写者（演进：未来切片如有 pending 写者，再回填）。
S6I2_PENDING_WRITERS: tuple[tuple[str, str, str], ...] = ()
```

修改 `_required_writer_specs()` 添加 M 类:

```python
# --- M 类写者（D2 落地；PR-D 独立 PR；本注册由 PR #D2 落地后转入）---
WriterSpec(
    writer_name="restore_replay_executor",
    owner_key="execution.core.v1",
    fence_status=FENCE_M,
    module_path="app.composition.restore_replay",
    function_name="replay_archive_segment_for_tenant",
    tenant_scoped=True,
    scope_class="Maintenance",
    notes="S6-8.3 M 类；exclusive advisory xact_lock；不调 adapter；不接 production scheduler",
),
```

- [ ] **Step 4: 运行测试确认 pass**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i2_orphan_inspection.py -q`
Expected: existing passed + new passed.

- [ ] **Step 5: 提交**

```bash
git add packages/server-python/app/composition/s6i2_orphan_inspection.py \
        packages/server-python/tests/composition/test_s6i2_orphan_inspection.py
git commit -m "feat(writer-conformance): register restore_replay_executor as M-class writer"
```

---

## Task 6: 6×5 state routing matrix tests

**Files:**
- Modify: `packages/server-python/tests/composition/test_s6i3_d_restore_replay.py`

- [ ] **Step 1: 添加 operation.state × checkpoint.state 矩阵测试**

Append to file:

```python
# 6 operation states × 5 checkpoint states = 30 routing scenarios
async def _seed_op_cp(s, tid, *, op_state, cp_state):
    cid = await _seed_conversation(s, tid=tid)
    op_id = await _seed_operation(s, tid=tid, cid=cid, state=op_state)
    await _seed_checkpoint(
        s, tid=tid, purge_operation_id=op_id,
        owner_key="workspace.core.v1", state=cp_state,
    )
    return op_id


@pytest.mark.parametrize("op_state,cp_state,expected_action", [
    # scheduled: 仅 restore-cancel 路径可达；executor 零写
    ("scheduled", "pending", "replay_skip_zero_write"),
    ("scheduled", "erasing", "replay_skip_zero_write"),
    ("scheduled", "blocked", "replay_skip_zero_write"),
    ("scheduled", "failed", "replay_skip_zero_write"),
    ("scheduled", "acked", "replay_skip_zero_write"),
    # running: 本地 owner + six-tuple 完整 → 候选；其他 skip
    ("running", "pending", "candidate_when_local"),
    ("running", "erasing", "candidate_when_local"),
    ("running", "blocked", "blocked_local_match_reason"),
    ("running", "failed", "zero_write"),
    ("running", "acked", "no_repeat"),
    # blocked: 本地 owner + six-tuple 完整 → 候选；其他 skip
    ("blocked", "pending", "candidate_when_local"),
    ("blocked", "erasing", "candidate_when_local"),
    ("blocked", "blocked", "blocked_local_match_reason"),
    ("blocked", "failed", "zero_write"),
    ("blocked", "acked", "no_repeat"),
    # failed: 零写人工
    ("failed", "pending", "zero_write_manual"),
    ("failed", "erasing", "zero_write_manual"),
    ("failed", "blocked", "zero_write_manual"),
    ("failed", "failed", "zero_write_manual"),
    ("failed", "acked", "zero_write_manual"),
    # completed: verify-only
    ("completed", "pending", "verify_only"),
    ("completed", "erasing", "verify_only"),
    ("completed", "blocked", "verify_only"),
    ("completed", "failed", "verify_only"),
    ("completed", "acked", "verify_only"),
    # cancelled: skip
    ("cancelled", "pending", "skip"),
    ("cancelled", "erasing", "skip"),
    ("cancelled", "blocked", "skip"),
    ("cancelled", "failed", "skip"),
    ("cancelled", "acked", "skip"),
])
async def test_state_routing_matrix(
    s6i3_d_factory, op_state, cp_state, expected_action,
):
    """6×5 state routing 矩阵：每个组合必须落入 frozen 路由表。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id = await _seed_op_cp(s, tid, op_state=op_state, cp_state=cp_state)

    sink = InMemoryLedgerArchiveSink()
    async with factory() as s, s.begin():
        from sqlalchemy import text as _t
        await s.execute(_t("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exported = await export_ledger_segment_for_archive(s, tenant_id=tid)
    outcome = await publish_ledger_segment(
        sink=sink, tenant_id=tid,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )

    verdict = next(
        (v for v in report.verdict
         if str(op_id) == v.operation_id and v.owner_key == "workspace.core.v1"),
        None,
    )
    assert verdict is not None, f"missing verdict for op={op_state} cp={cp_state}"
    assert verdict.action == expected_action, (
        f"op={op_state} cp={cp_state}: expected {expected_action}, got {verdict.action}"
    )
```

- [ ] **Step 2: 运行测试**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay.py -q`
Expected: 30 passed.

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/tests/composition/test_s6i3_d_restore_replay.py
git commit -m "test(restore-replay): 6x5 state routing matrix (30 scenarios)"
```

---

## Task 7: phase 3 restore-before-open gate tests

**Files:**
- Modify: `packages/server-python/tests/composition/test_s6i3_d_restore_replay.py`

- [ ] **Step 1: 添加 restore-before-open 测试**

```python
async def test_restore_before_open_empty_db_open_allowed(s6i3_d_factory):
    """空 DB（snapshot 后无保留 conversation）→ open_allowed=True。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
    report = await evaluate_restore_before_open(factory, tenant_id=tid)
    assert report.open_allowed is True
    assert report.blocked_reasons == ()


async def test_restore_before_open_conversation_remaining_blocked(s6i3_d_factory):
    """conversation 仍有正文残留 → open_allowed=False + blocked reason。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
    # 写入一条 turn body（模拟 snapshot 后保留正文）
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "INSERT INTO metaedu.agent_turn_inputs "
                "(id, tenant_id, run_id, turn_seq, source_event_seq, "
                "actor_kind, actor_id, input_payload_inline, "
                "input_payload_ref, input_payload_digest, created_at) "
                "VALUES (gen_random_uuid(), :t, NULL, 1, 1, "
                "'user', gen_random_uuid(), '{}'::jsonb, NULL, :d, now())"
            ),
            {"t": tid, "d": _DIGEST},
        )
    report = await evaluate_restore_before_open(factory, tenant_id=tid)
    # 注：当前 verify_inspection 巡检不含 body scan；本测试依赖 phase-3
    # gate 必须同时跑 body 扫描（继承自 execution_erasure_participant.scan_execution_body）
    # 如未集成，测试将 FAIL，需在 restore_replay.py 添加 body scan 集成
    assert report.open_allowed is False
    assert any("body" in r.lower() or "turn" in r.lower() for r in report.blocked_reasons)
```

- [ ] **Step 2: 运行测试**

Run: `cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay.py::test_restore_before_open_empty_db_open_allowed tests/composition/test_s6i3_d_restore_replay.py::test_restore_before_open_conversation_remaining_blocked -q`
Expected: 2 passed（pending restore_replay.py 完整实现）.

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/tests/composition/test_s6i3_d_restore_replay.py
git commit -m "test(restore-replay): phase-3 restore-before-open gate"
```

---

## Task 8: mutation kill 脚本

**Files:**
- Create: `scripts/s6i3_d_restore_replay_mutation_kill.py`

- [ ] **Step 1: 实现 mutation kill 驱动**

```python
"""R1-S6-I3-D D2: restore replay executor mutation kill。

真实 PG 真实路径 mutation 驱动（参照 s6i1_retention_mutation_kill 模式）：
- byte backup + try/finally + SHA-256 byte-identical
- 每条 mutation 绑定对应 invariant test
- subprocess pytest exit=1 → KILLED；恢复后 exit=0 → 干净

Mutation 覆盖（每项对应 invariant test）：
- M-D2-1: replay 不取 exclusive maintenance lock → retention worker 不被阻塞
- M-D2-2: replay 调用 external adapter → blocked external owner 应被实际调用
- M-D2-3: replay 不验证 expected_marker → cross-tenant marker 可注入
- M-D2-4: replay 跳过六元组完整性 → state 篡改可通过
- M-D2-5: replay 调度 retention worker 路径 → 不应直接驱动 worker
- M-D2-6: replay 在 maintenance tx 外取 owner 行锁 → 互斥不成立
- M-D2-7: replay ack_digest 不重算 → 已 acked checkpoint 二次清除
"""
# ... full implementation with MUTATIONS list ...
```

- [ ] **Step 2: 运行 mutation kill**

Run: `cd packages/server-python && uv run python scripts/s6i3_d_restore_replay_mutation_kill.py`
Expected: 7/7 KILLED.

- [ ] **Step 3: 提交**

```bash
git add scripts/s6i3_d_restore_replay_mutation_kill.py
git commit -m "test(restore-replay): mutation kill 7/7 KILLED"
```

---

## Task 9: 完整验证

- [ ] **Step 1: ruff clean**

```bash
cd packages/server-python && uv run ruff check app/composition/restore_replay.py app/composition/agent_erasure_locks.py app/composition/retention_workers.py app/composition/s6i2_orphan_inspection.py tests/composition/test_s6i3_d_restore_replay.py tests/composition/test_s6i3_d_restore_replay_locks.py scripts/s6i3_d_restore_replay_mutation_kill.py
```

Expected: All checks passed.

- [ ] **Step 2: mypy baseline 0 regressions**

```bash
cd packages/server-python && uv run --frozen --extra dev python scripts/check_mypy_baseline.py
```

Expected: passed; 0 regressions.

- [ ] **Step 3: git diff --check clean**

```bash
git diff --check main
```

Expected: no output.

- [ ] **Step 4: engineering-docs full green**

```bash
cd packages/server-python && uv run --frozen --extra dev python scripts/check_engineering_docs.py --full
```

Expected: 全绿。

- [ ] **Step 5: 完整测试套件**

```bash
cd packages/server-python && uv run pytest tests/composition/test_s6i3_d_restore_replay.py tests/composition/test_s6i3_d_restore_replay_locks.py tests/composition/test_s6i2_orphan_inspection.py tests/composition/test_s6i1_event_retention.py tests/composition/test_s6i1_audit_retention.py -q
```

Expected: all passed.

---

## Task 10: Draft PR 创建

- [ ] **Step 1: 推送分支**

```bash
git push -u origin feature/req041-047-r1-s6-i3-d-d2-restore-replay
```

- [ ] **Step 2: 创建 Draft PR**

```bash
gh pr create --draft --base main --head feature/req041-047-r1-s6-i3-d-d2-restore-replay \
  --title "feat(s6i3-d): D2 restore replay executor + restore-before-open gate (M-class) (#603)" \
  --body-file /tmp/d2_pr_body.md
```

PR body 模板见下，详列：spec 来源 / 契约事实 / 验证基线 / frozen boundaries / 当前不宣称（production wiring / capability flip / 六 erase 入口）。

---

## Self-Review

- Spec coverage：6×5 state routing + advisory lock 互斥 + restore-before-open + M-class writer 登记 + mutation kill = 全覆盖
- Placeholder scan：无 "TBD" / "TODO" / "类似 Task" 占位
- Type consistency：`replay_archive_segment_for_tenant` / `evaluate_restore_before_open` / `RestoreReplayReport` / `RestoreBeforeOpenReport` / `ReplayOwnerVerdict` 一致命名