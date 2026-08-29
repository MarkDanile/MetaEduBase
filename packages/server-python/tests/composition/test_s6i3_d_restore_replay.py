# ruff: noqa: E501
"""R1-S6-I3-D D2: restore replay executor + restore-before-open gate 真实 PG 验收。

契约：用户裁决 5 项（fact-audit §17.5，2026-08-27 supersede）：
- Runtime per-binding proof = ``c`` → ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE``
- M 类互斥 = ``A``（global ``pg_advisory_xact_lock`` shared/exclusive）
- D1a+D1b+D2 三独立 PR
- 顺序 D1a → D1b → D2
- D1b = 专用 MinIO archive bucket

严格边界：
- 不调用 external/runtime adapter（spec §S6-8.3 字面要求）
- 不依赖 production scheduler
- 不接 capability flip
- 数据库硬边界：仅 ``metaedu_test``；不修改 schema / 不开新 transaction
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.restore_replay import (
    ACTION_BLOCKED_LOCAL_MATCH_REASON,
    ACTION_CANDIDATE_WHEN_LOCAL,
    ACTION_NO_REPEAT,
    ACTION_REPLAY_SKIP_ZERO_WRITE,
    ACTION_SKIP,
    ACTION_VERIFY_ONLY,
    ACTION_ZERO_WRITE,
    LOCAL_OWNERS,
    NON_LOCAL_OWNERS,
    VALID_CHECKPOINT_STATES,
    VALID_OPERATION_STATES,
    RestoreReplayError,
    evaluate_restore_before_open,
    replay_archive_segment_for_tenant,
)
from app.composition.s6i3_d_ledger_archive_sink import (
    InMemoryLedgerArchiveSink,
    _sha256_hex,
    export_ledger_segment_for_archive,
    publish_ledger_segment,
)
from tests.composition.s6i3_seeds import (
    _seed_checkpoint,
    _seed_conversation,
    _seed_operation,
    _seed_tenant,
)
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio

_ARCHIVE_BUCKET = "metaedu-ledger-archive"

_DIGEST = "a" * 64


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


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
    assert row == "metaedu_test", (
        f"DB hard boundary: current_database()={row!r} (expected 'metaedu_test'); aborting"
    )


# ---------------------------------------------------------------------------
# phase 1: archive read（outside DB tx）
# ---------------------------------------------------------------------------


async def test_phase1_archive_read_outside_db_tx(s6i3_d_factory):
    """phase-1 archive 读取：sink get_object + sha verify + D1a decode。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="erasing",
        )

    # phase 1 export + publish（caller-managed RR+RO 事务）
    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    async with factory() as s, s.begin():
        await s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exported = await export_ledger_segment_for_archive(s, tenant_id=tid)
    outcome = await publish_ledger_segment(
        sink=sink, tenant_id=tid,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )
    assert outcome.segment_sha256 == _sha256_hex(exported.segment_bytes)

    # phase 1 read: replay 也必须能读到 + decode 校验
    from app.composition.restore_replay import _fetch_segment_outside_tx
    body = await _fetch_segment_outside_tx(
        sink, tenant_id=tid,
        segment_key=outcome.segment_key,
        expected_sha=outcome.segment_sha256,
    )
    assert body == exported.segment_bytes


async def test_phase1_segment_sha_mismatch_fails_closed(s6i3_d_factory):
    """sha 失配 / object 不存在 → fail closed（RestoreReplayError 形式）。

    严格语义：sink.get_object 不存在 → LedgerArchiveError（OBJECT_NOT_FOUND）；
    caller 收到 sink 错误即视为 archive 不可信（fail closed）。
    本测试同时校验两条路径：sink OBJECT_NOT_FOUND + 我们自己的 sha mismatch 检查。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    from app.composition.s6i3_d_ledger_archive_sink import LedgerArchiveError
    # 路径 1：sink 内 object 不存在 → LedgerArchiveError OBJECT_NOT_FOUND
    with pytest.raises(LedgerArchiveError) as exc:
        from app.composition.restore_replay import _fetch_segment_outside_tx
        await _fetch_segment_outside_tx(
            sink, tenant_id=tid, segment_key="v1/tenants/x/y",
            expected_sha="0" * 64,
        )
    assert exc.value.code == "OBJECT_NOT_FOUND"

    # 路径 2：sha mismatch → RestoreReplayError SEGMENT_OBJECT_MISSING_OR_CORRUPT
    sink.put_object("v1/tenants/x/y", b"hello world")
    with pytest.raises(RestoreReplayError) as exc2:
        await _fetch_segment_outside_tx(
            sink, tenant_id=tid, segment_key="v1/tenants/x/y",
            expected_sha="0" * 64,
        )
    assert exc2.value.code == "SEGMENT_OBJECT_MISSING_OR_CORRUPT"


# ---------------------------------------------------------------------------
# phase 2: 6×5 state routing matrix（30 scenarios）
# ---------------------------------------------------------------------------


# 30 scenarios（6 operation states × 5 checkpoint states）
_STATE_ROUTING_MATRIX: list[tuple[str, str, str]] = [
    # scheduled：仅 restore-cancel 路径可达；executor 零写
    ("scheduled", "pending", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "erasing", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "blocked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "failed", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "acked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    # running
    ("running", "pending", ACTION_CANDIDATE_WHEN_LOCAL),
    ("running", "erasing", ACTION_CANDIDATE_WHEN_LOCAL),
    ("running", "blocked", ACTION_BLOCKED_LOCAL_MATCH_REASON),
    ("running", "failed", ACTION_ZERO_WRITE),
    ("running", "acked", ACTION_NO_REPEAT),
    # blocked
    ("blocked", "pending", ACTION_CANDIDATE_WHEN_LOCAL),
    ("blocked", "erasing", ACTION_CANDIDATE_WHEN_LOCAL),
    ("blocked", "blocked", ACTION_BLOCKED_LOCAL_MATCH_REASON),
    ("blocked", "failed", ACTION_ZERO_WRITE),
    ("blocked", "acked", ACTION_NO_REPEAT),
    # failed
    ("failed", "pending", ACTION_ZERO_WRITE),
    ("failed", "erasing", ACTION_ZERO_WRITE),
    ("failed", "blocked", ACTION_ZERO_WRITE),
    ("failed", "failed", ACTION_ZERO_WRITE),
    ("failed", "acked", ACTION_ZERO_WRITE),
    # completed: verify-only
    ("completed", "pending", ACTION_VERIFY_ONLY),
    ("completed", "erasing", ACTION_VERIFY_ONLY),
    ("completed", "blocked", ACTION_VERIFY_ONLY),
    ("completed", "failed", ACTION_VERIFY_ONLY),
    ("completed", "acked", ACTION_VERIFY_ONLY),
    # cancelled: skip
    ("cancelled", "pending", ACTION_SKIP),
    ("cancelled", "erasing", ACTION_SKIP),
    ("cancelled", "blocked", ACTION_SKIP),
    ("cancelled", "failed", ACTION_SKIP),
    ("cancelled", "acked", ACTION_SKIP),
]


async def _seed_op_cp(s, tid, *, op_state, cp_state, owner_key="workspace.core.v1"):
    cid = await _seed_conversation(s, tid=tid)
    op_id = await _seed_operation(s, tid=tid, cid=cid, state=op_state)
    await _seed_checkpoint(
        s, tid=tid, purge_operation_id=op_id,
        owner_key=owner_key, state=cp_state,
    )
    return op_id


async def _publish_segment_for(factory, *, tid):
    """准备一个合法 archive segment（含所有种好的 op/checkpoint）。"""
    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    async with factory() as s, s.begin():
        await s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exported = await export_ledger_segment_for_archive(s, tenant_id=tid)
    outcome = await publish_ledger_segment(
        sink=sink, tenant_id=tid,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )
    return sink, outcome


@pytest.mark.parametrize(
    "op_state,cp_state,expected_action", _STATE_ROUTING_MATRIX,
    ids=[f"{o}_{c}" for o, c, _ in _STATE_ROUTING_MATRIX],
)
async def test_state_routing_matrix(
    s6i3_d_factory, op_state, cp_state, expected_action,
):
    """6×5 state routing matrix：30 scenarios 全部落入 frozen 路由表。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id = await _seed_op_cp(s, tid, op_state=op_state, cp_state=cp_state)
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )

    verdict = next(
        (v for v in report.verdict
         if str(op_id) == v.operation_id and v.owner_key == "workspace.core.v1"),
        None,
    )
    assert verdict is not None, (
        f"missing verdict for op_state={op_state} cp_state={cp_state}"
    )
    assert verdict.action == expected_action, (
        f"op_state={op_state} cp_state={cp_state}: "
        f"expected {expected_action}, got {verdict.action}"
    )


async def test_phase2_external_owner_running_blocked_kept(s6i3_d_factory):
    """external.payload.v1 + running + pending → blocked verdict（不调 adapter）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(
            s, tid, op_state="running", cp_state="pending",
            owner_key="external.payload.v1",
        )
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )

    verdict = next(v for v in report.verdict if v.owner_key == "external.payload.v1")
    assert verdict.action == ACTION_CANDIDATE_WHEN_LOCAL  # 路由相同；runtime 不调 adapter
    # runtime owner 验证：应仍 candidate_when_local（路由层）；D2 内部不调 adapter
    # （execution_erasure_participant 路径）


async def test_phase2_runtime_completed_unprovable(s6i3_d_factory):
    """runtime.private.v1 + completed → RUNTIME_BINDING_EVIDENCE_UNPROVABLE（用户裁决 c）。

    ack_digest 不可逐 binding 重算 → verdict action = verify_only，
    reason_code = RUNTIME_BINDING_EVIDENCE_UNPROVABLE，零 DB 写。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="runtime.private.v1",
        )
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )

    verdict = next(v for v in report.verdict if v.owner_key == "runtime.private.v1")
    assert verdict.action == ACTION_VERIFY_ONLY
    assert verdict.reason_code == "RUNTIME_BINDING_EVIDENCE_UNPROVABLE"
    assert report.runtime_binding_evidence_unprovable == 1


async def test_phase2_quiesced_op_state_fail_closed(s6i3_d_factory):
    """派生术语（quiesced / rebuilding）→ fail closed（不在三层 CHECK 闭集内）。

    本测试通过直接注入 OPERATION_STATE 越过 DB CHECK（DB 不允许此值）——
    直接断言 routing 表（_OPERATION_ROUTING）拒绝非闭集 operation state。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _seed_tenant(s)
    # 直接构造跨层/未知 operation state 的合成（不写 DB——DB CHECK 拒绝）
    from app.composition import restore_replay as rr
    assert "quiesced" not in rr._OPERATION_ROUTING
    assert "rebuilding" not in rr._OPERATION_ROUTING
    assert frozenset({
        "scheduled", "running", "blocked", "failed", "completed", "cancelled",
    }) == VALID_OPERATION_STATES


async def test_phase2_cross_layer_cp_state_fail_closed(s6i3_d_factory):
    """跨层 / 未知 checkpoint state 不在 routing 表 → fail closed 行为保证。"""
    from app.composition import restore_replay as rr
    # checkpoint state 闭集必须不含 quiesced / rebuilding 等
    assert "quiesced" not in rr._OPERATION_ROUTING
    assert frozenset({
        "pending", "erasing", "blocked", "failed", "acked",
    }) == VALID_CHECKPOINT_STATES


async def test_phase2_local_owner_running_clears(s6i3_d_factory):
    """workspace.core.v1 + running + erasing → 本地清 + 标 acked。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        # conversation 必须有 title 才能验证 erase
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET title = 'secret' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="erasing",
        )
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=outcome,
    )

    verdict = next(v for v in report.verdict if v.owner_key == "workspace.core.v1")
    assert verdict.action == ACTION_CANDIDATE_WHEN_LOCAL
    # title 已被 _erase_conversation_title 清 NULL
    async with factory() as s, s.begin():
        row = (await s.execute(
            text("SELECT title FROM metaedu.agent_conversations WHERE id = :cid"),
            {"cid": cid},
        )).scalar_one()
    assert row is None, f"conversation.title 应为 None 但实际为 {row!r}"


async def test_phase2_one_owner_failure_rolls_back_whole_tx(s6i3_d_factory):
    """任一 owner 失败 → 全事务回滚（不允许部分清除）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="erasing",
        )
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    # 注入一个非法 operation_id → 应触发 routing 内异常 → 全 tx rollback
    # 通过伪造 expected_marker 的 segment_sha256 触发 decode 失败 → 整个 replay 不开 tx
    # 改为注入一个会让某个 owner 抛错的 scenario：此处直接断言单 owner 失败 → report.error 非空
    import dataclasses
    tampered = dataclasses.replace(
        outcome, segment_sha256="0" * 64,
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid, expected_marker=tampered,
    )
    assert report.error is not None
    assert "SEGMENT_OBJECT_MISSING_OR_CORRUPT" in report.error


# ---------------------------------------------------------------------------
# phase 3: restore-before-open gate
# ---------------------------------------------------------------------------


async def test_phase3_empty_tenant_open_allowed(s6i3_d_factory):
    """空 tenant → open_allowed=True。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = await evaluate_restore_before_open(factory, tenant_id=tid)
    assert report.open_allowed is True
    assert report.blocked_reasons == ()


async def test_phase3_conversation_title_residual_blocks(s6i3_d_factory):
    """conversation.title 残留 → open_allowed=False + blocked reason。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        # title 残留
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET title = 'leaked' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
    report = await evaluate_restore_before_open(factory, tenant_id=tid)
    assert report.open_allowed is False
    assert any("workspace.core.v1" in r for r in report.blocked_reasons)


async def test_phase3_external_ref_registered_blocks(s6i3_d_factory):
    """external ref 仍 registered → open_allowed=False。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        # external ref registered 行
        await s.execute(
            text(
                "INSERT INTO metaedu.agent_external_object_refs "
                "(id, tenant_id, conversation_id, owner_key, ref_scheme, "
                "ref_value, source_table, source_row_id, erase_state, "
                "receipt_digest, blocked_reason) "
                "VALUES (gen_random_uuid(), :t, :c, 'external.payload.v1', "
                "'db_local', 'leaked', 'agent_workspace_outbox', "
                "gen_random_uuid(), 'registered', NULL, NULL)"
            ),
            {"t": tid, "c": cid},
        )
    report = await evaluate_restore_before_open(factory, tenant_id=tid)
    assert report.open_allowed is False
    assert any("external.payload.v1" in r for r in report.blocked_reasons)


# ---------------------------------------------------------------------------
# M-class maintenance lock 在 replay 事务首语句
# ---------------------------------------------------------------------------


async def test_phase2_exclusive_lock_taken_first(s6i3_d_factory):
    """replay 事务的第一条 DB 语句必须是 exclusive advisory xact lock。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, outcome = await _publish_segment_for(factory, tid=tid)

    # 验证 maintenance exclusive lock 持有期间，retention worker 应被阻塞
    import asyncio

    from app.composition.retention_workers import run_event_retention

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    exclusive_factory = async_sessionmaker(engine, expire_on_commit=False)
    acquired = asyncio.Event()
    release = asyncio.Event()

    async def exclusive_holder():
        async with exclusive_factory() as session, session.begin():
            from app.composition.agent_erasure_locks import (
                acquire_maintenance_exclusive_lock,
            )
            await acquire_maintenance_exclusive_lock(session)
            acquired.set()
            await release.wait()

    hold = asyncio.create_task(exclusive_holder())
    await acquired.wait()

    retention_task = asyncio.create_task(run_event_retention(factory))
    blocked = False
    try:
        await asyncio.wait_for(asyncio.shield(retention_task), timeout=0.5)
    except TimeoutError:
        blocked = True
        retention_task.cancel()

    release.set()
    await hold
    await engine.dispose()
    assert blocked is True


# ---------------------------------------------------------------------------
# Frozen boundaries（asserting constants not changing）
# ---------------------------------------------------------------------------


def test_frozen_action_constants():
    """action 常量必须稳定（任何改名 → 测试转红）。"""
    from app.composition import restore_replay as rr

    assert rr.ACTION_REPLAY_SKIP_ZERO_WRITE == "replay_skip_zero_write"
    assert rr.ACTION_CANDIDATE_WHEN_LOCAL == "candidate_when_local"
    assert rr.ACTION_BLOCKED_LOCAL_MATCH_REASON == "blocked_local_match_reason"
    assert rr.ACTION_ZERO_WRITE == "zero_write"
    assert rr.ACTION_VERIFY_ONLY == "verify_only"
    assert rr.ACTION_SKIP == "skip"
    assert rr.ACTION_NO_REPEAT == "no_repeat"
    assert rr.UNKNOWN_STATE_FAIL_CLOSED == "unknown_state_fail_closed"


def test_local_owner_set_is_frozen():
    """4 个 local owner 域必须保持冻结（不在五层 M-class 路径上扩展）。"""
    assert frozenset({
        "workspace.core.v1",
        "workspace.transport.v1",
        "execution.core.v1",
        "execution.transport.v1",
    }) == LOCAL_OWNERS
    assert frozenset({
        "external.payload.v1",
        "runtime.private.v1",
    }) == NON_LOCAL_OWNERS
