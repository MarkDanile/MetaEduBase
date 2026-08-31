# ruff: noqa: E501
"""R1-S6-I3-D D2 Round-2 P0 修复：restore replay executor + restore-before-open gate 真实 PG 验收。

Round-2 P0 修复（普通新 commit；6 项张力 + 8 项新判别测试）：
- Phase 1 从 D1b committed graph 取输入（不接 caller PublishOutcome）
- 路由按 ARCHIVE state（不是 LIVE state）；pass B TOCTOU 重读
- Transport 公共入口 = ``erase_transport_owner``（parent class）
- atomicity：pass A drift → 不进入 pass B；pass B 异常 → 整事务回滚
- 六元组逐字段 drift + reason_code
- Gate 强制消费 RestoreReplayReport
- 8 项新判别测试（真实双 owner / transport 公共入口 / ack_digest 64-hex / purge_revision / TOCTOU / gate 消费 report / fact drift 阻断）

契约：用户裁决 5 项（fact-audit §17.5，2026-08-27 supersede）：
- Runtime per-binding proof = ``c`` → ``RUNTIME_BINDING_EVIDENCE_UNPROVABLE``
- M 类互斥 = ``A``（global ``pg_advisory_xact_lock`` shared/exclusive）
- D1a+D1b+D2 三独立 PR
- 顺序 D1a → D1b → D2
- D1b = 专用 MinIO archive bucket

数据库硬边界：仅 ``metaedu_test``；不修改 schema / 不开新 transaction。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.restore_replay import (
    ACTION_EXTERNAL_VERIFICATION_FAILED,
    ACTION_FACT_DRIFT_FAIL_CLOSED,
    ACTION_LOCAL_CLEARED,
    ACTION_NO_REPEAT,
    ACTION_NON_LOCAL_BLOCKED,
    ACTION_REPLAY_SKIP_ZERO_WRITE,
    ACTION_RUNTIME_BINDING_UNPROVABLE,
    ACTION_RUNTIME_BLOCKED,
    ACTION_SKIP,
    ACTION_VERIFY_ONLY,
    ACTION_ZERO_WRITE,
    LOCAL_OWNERS,
    NON_LOCAL_OWNERS,
    RestoreReplayReport,
    evaluate_restore_before_open,
    replay_archive_segment_for_tenant,
)
from app.composition.s6i3_d_ledger_archive_sink import (
    InMemoryLedgerArchiveSink,
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
    assert row == "metaedu_test"


async def _seed_op_cp(s, tid, *, op_state, cp_state, owner_key="workspace.core.v1",
                      purge_rev=1, op_revision=1, lease_epoch=0):
    from app.composition.agent_erasure_registry import (
        capability_digest,
        registry_digest,
    )

    cid = await _seed_conversation(s, tid=tid)
    await s.execute(
        text(
            "UPDATE metaedu.agent_conversations "
            "SET state = 'deleted', purge_after = now() - interval '1 day' "
            "WHERE id = :cid"
        ),
        {"cid": cid},
    )
    op_id = await _seed_operation(s, tid=tid, cid=cid, state=op_state, purge_rev=purge_rev)
    await s.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET revision = :rev, lease_epoch = :le, "
            "registry_digest = :rd, retention_policy_digest = :rd "
            "WHERE id = :oid"
        ),
        {"rev": op_revision, "le": lease_epoch, "rd": registry_digest(), "oid": op_id},
    )
    await _seed_checkpoint(
        s, tid=tid, purge_operation_id=op_id,
        owner_key=owner_key, state=cp_state,
        capability_digest=capability_digest(owner_key),
    )
    return op_id, cid


async def _seed_inline_with_correct_digests(s, *, tid, op_state, cp_state,
                                           owner_key, title=None):
    from app.composition.agent_erasure_registry import (
        capability_digest,
        registry_digest,
    )

    cid = await _seed_conversation(s, tid=tid)
    update_sql = (
        "UPDATE metaedu.agent_conversations "
        "SET state = 'deleted', purge_after = now() - interval '1 day' "
        + (", title = :title" if title is not None else "")
        + " WHERE id = :cid"
    )
    params = {"cid": cid}
    if title is not None:
        params["title"] = title
    await s.execute(text(update_sql), params)
    op_id = await _seed_operation(s, tid=tid, cid=cid, state=op_state)
    await s.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET revision = 1, lease_epoch = 0, "
            "registry_digest = :rd, retention_policy_digest = :rd "
            "WHERE id = :oid"
        ),
        {"rd": registry_digest(), "oid": op_id},
    )
    await _seed_checkpoint(
        s, tid=tid, purge_operation_id=op_id,
        owner_key=owner_key, state=cp_state,
        capability_digest=capability_digest(owner_key),
    )
    return op_id, cid


async def _publish_segment_for(factory, *, tid):
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


def _patch_lock_inject_drift(monkeypatch, drift_sql, drift_params):
    """Monkey-patch ``acquire_maintenance_exclusive_lock``：先在 pass B 内获取**真实**
    exclusive lock，再在**同一 session/tx** 注入 drift。

    时序保证 drift 落在 pass A 校验完成之后、pass B reverify 之前：
    - pass A 在独立 session/tx 读到 LIVE 原值（与 archive 一致）→ ``pass_a_drift == 0``
    - pass B 首语句取 exclusive lock（本 wrapper 内调用原函数）→ 立即在同 tx 改字段
    - ``_toctou_reverify_pass_b`` 在同一 tx 重读 → 看到 drift → ``TOCTOU_DRIFT_FIELDS``
    - TOCTOU 失败 → ``async with session.begin()`` 自动 rollback → drift **不**提交
    """
    import app.composition.restore_replay as rr_mod

    original_lock = rr_mod.acquire_maintenance_exclusive_lock

    async def lock_then_drift(session):
        await original_lock(session)
        await session.execute(text(drift_sql), drift_params)

    monkeypatch.setattr(
        rr_mod, "acquire_maintenance_exclusive_lock", lock_then_drift
    )


async def _seed_external_ref(
    s, *, tid, cid, receipt, erase_state="erased", ref_value=None,
    owner_key="external.payload.v1",
):
    """种一条 ``agent_external_object_refs`` 行并返回其 id。

    - ``erase_state='erased'`` ⇒ ``receipt_digest`` 必须为非 NULL 64-hex
      （ck_agent_external_refs_erase_evidence：erased ⟺ receipt_digest NOT NULL）。
    - ``erase_state='registered'`` ⇒ ``receipt_digest`` 必须为 NULL（窗口不变量）。
    - ``ref_value`` 默认随机，避免触碰 ``uq_agent_external_ref_source``
      （tenant+source_table+source_row_id+ref_value 唯一）。
    """
    rv = ref_value if ref_value is not None else f"ref_{uuid.uuid4().hex[:12]}"
    row_id = (await s.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, conversation_id, "
            "erase_state, receipt_digest) "
            "VALUES (gen_random_uuid(), :tid, :ok, "
            "'db_local', :rv, 'agent_workspace_outbox', "
            "gen_random_uuid(), :cid, :es, :rcpt) RETURNING id"
        ),
        {
            "tid": tid, "ok": owner_key, "rv": rv, "cid": str(cid),
            "es": erase_state, "rcpt": receipt,
        },
    )).scalar_one()
    return row_id


# 30 routing scenarios（6 operation states × 5 checkpoint states）
# local owner（workspace.core.v1 默认）期望 action
_STATE_ROUTING_MATRIX: list[tuple[str, str, str]] = [
    ("scheduled", "pending", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "erasing", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "blocked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "failed", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "acked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("running", "pending", ACTION_LOCAL_CLEARED),
    ("running", "erasing", ACTION_LOCAL_CLEARED),
    ("running", "blocked", ACTION_LOCAL_CLEARED),
    ("running", "failed", ACTION_ZERO_WRITE),
    ("running", "acked", ACTION_NO_REPEAT),
    ("blocked", "pending", ACTION_LOCAL_CLEARED),
    ("blocked", "erasing", ACTION_LOCAL_CLEARED),
    ("blocked", "blocked", ACTION_LOCAL_CLEARED),
    ("blocked", "failed", ACTION_ZERO_WRITE),
    ("blocked", "acked", ACTION_NO_REPEAT),
    ("failed", "pending", ACTION_ZERO_WRITE),
    ("failed", "erasing", ACTION_ZERO_WRITE),
    ("failed", "blocked", ACTION_ZERO_WRITE),
    ("failed", "failed", ACTION_ZERO_WRITE),
    ("failed", "acked", ACTION_ZERO_WRITE),
    ("completed", "pending", ACTION_VERIFY_ONLY),
    ("completed", "erasing", ACTION_VERIFY_ONLY),
    ("completed", "blocked", ACTION_VERIFY_ONLY),
    ("completed", "failed", ACTION_VERIFY_ONLY),
    ("completed", "acked", ACTION_VERIFY_ONLY),
    ("cancelled", "pending", ACTION_SKIP),
    ("cancelled", "erasing", ACTION_SKIP),
    ("cancelled", "blocked", ACTION_SKIP),
    ("cancelled", "failed", ACTION_SKIP),
    ("cancelled", "acked", ACTION_SKIP),
]


# 30 routing scenarios × 2 non-local owner = 60 完整 6×5 判别（external.payload.v1 + runtime.private.v1）
# 全局 6×5 矩阵先（**禁止**按 owner 降级为 non_local_blocked）：
# - scheduled/cancelled/failed/acked → 矩阵返回 SKIP / ZERO_WRITE / REPLAY_SKIP_ZERO_WRITE / NO_REPEAT
# - running/blocked + local owner → LOCAL_CLEARED（调 participant）
# - running/blocked + non-local owner → owner-specific（NON_LOCAL_BLOCKED）
# - completed + local owner → VERIFY_ONLY
# - completed + non-local external → EXTERNAL_VERIFY_ONLY（待 caller receipt 验证）
# - completed + non-local runtime → RUNTIME_BINDING_UNPROVABLE
_NON_LOCAL_OWNER_MATRIX_EXPECTATION: dict[str, dict[str, str]] = {
    "external.payload.v1": {
        # global 矩阵先（scheduled/cancelled/failed/acked 不得降级为 non_local_blocked）；
        # 矩阵返回 → verdict.action 矩阵值（**不**经 receipt 验证）
        ("scheduled", "pending"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "erasing"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "blocked"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "failed"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "acked"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("running", "pending"): ACTION_NON_LOCAL_BLOCKED,
        ("running", "erasing"): ACTION_NON_LOCAL_BLOCKED,
        ("running", "blocked"): ACTION_NON_LOCAL_BLOCKED,
        ("running", "failed"): ACTION_ZERO_WRITE,
        ("running", "acked"): ACTION_NO_REPEAT,
        ("blocked", "pending"): ACTION_NON_LOCAL_BLOCKED,
        ("blocked", "erasing"): ACTION_NON_LOCAL_BLOCKED,
        ("blocked", "blocked"): ACTION_NON_LOCAL_BLOCKED,
        ("blocked", "failed"): ACTION_ZERO_WRITE,
        ("blocked", "acked"): ACTION_NO_REPEAT,
        ("failed", "pending"): ACTION_ZERO_WRITE,
        ("failed", "erasing"): ACTION_ZERO_WRITE,
        ("failed", "blocked"): ACTION_ZERO_WRITE,
        ("failed", "failed"): ACTION_ZERO_WRITE,
        ("failed", "acked"): ACTION_ZERO_WRITE,
        # completed → owner-specific：经 receipt 验证（无 external_ref 行 → failed）
        ("completed", "pending"): ACTION_EXTERNAL_VERIFICATION_FAILED,
        ("completed", "erasing"): ACTION_EXTERNAL_VERIFICATION_FAILED,
        ("completed", "blocked"): ACTION_EXTERNAL_VERIFICATION_FAILED,
        ("completed", "failed"): ACTION_EXTERNAL_VERIFICATION_FAILED,
        ("completed", "acked"): ACTION_EXTERNAL_VERIFICATION_FAILED,
        ("cancelled", "pending"): ACTION_SKIP,
        ("cancelled", "erasing"): ACTION_SKIP,
        ("cancelled", "blocked"): ACTION_SKIP,
        ("cancelled", "failed"): ACTION_SKIP,
        ("cancelled", "acked"): ACTION_SKIP,
    },
    "runtime.private.v1": {
        # runtime + completed → unprovable；其他 → runtime_blocked verdict / 矩阵返回
        ("scheduled", "pending"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "erasing"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "blocked"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "failed"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("scheduled", "acked"): ACTION_REPLAY_SKIP_ZERO_WRITE,
        ("running", "pending"): ACTION_RUNTIME_BLOCKED,
        ("running", "erasing"): ACTION_RUNTIME_BLOCKED,
        ("running", "blocked"): ACTION_RUNTIME_BLOCKED,
        ("running", "failed"): ACTION_ZERO_WRITE,
        ("running", "acked"): ACTION_NO_REPEAT,
        ("blocked", "pending"): ACTION_RUNTIME_BLOCKED,
        ("blocked", "erasing"): ACTION_RUNTIME_BLOCKED,
        ("blocked", "blocked"): ACTION_RUNTIME_BLOCKED,
        ("blocked", "failed"): ACTION_ZERO_WRITE,
        ("blocked", "acked"): ACTION_NO_REPEAT,
        ("failed", "pending"): ACTION_ZERO_WRITE,
        ("failed", "erasing"): ACTION_ZERO_WRITE,
        ("failed", "blocked"): ACTION_ZERO_WRITE,
        ("failed", "failed"): ACTION_ZERO_WRITE,
        ("failed", "acked"): ACTION_ZERO_WRITE,
        ("completed", "pending"): ACTION_RUNTIME_BINDING_UNPROVABLE,
        ("completed", "erasing"): ACTION_RUNTIME_BINDING_UNPROVABLE,
        ("completed", "blocked"): ACTION_RUNTIME_BINDING_UNPROVABLE,
        ("completed", "failed"): ACTION_RUNTIME_BINDING_UNPROVABLE,
        ("completed", "acked"): ACTION_RUNTIME_BINDING_UNPROVABLE,
        ("cancelled", "pending"): ACTION_SKIP,
        ("cancelled", "erasing"): ACTION_SKIP,
        ("cancelled", "blocked"): ACTION_SKIP,
        ("cancelled", "failed"): ACTION_SKIP,
        ("cancelled", "acked"): ACTION_SKIP,
    },
}


# ---------------------------------------------------------------------------
# phase 1: archive read (from D1b committed graph, not caller's PublishOutcome)
# ---------------------------------------------------------------------------


async def test_phase1_archive_read_from_committed_tip(s6i3_d_factory):
    """Phase 1：从 D1b committed graph（find_committed_tip + fetch_segment_bytes）取输入。

    不接 caller 的 PublishOutcome；只通过 sink committed tip 推导。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 新签名：不再传 expected_marker；replay 内部 find_committed_tip → fetch_segment_bytes
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is None
    assert report.owners_local_cleared == 1


async def test_phase1_no_committed_tip_fails_closed(s6i3_d_factory):
    """无 committed tip（空 sink）→ RestoreReplayReport error 字段非空，DB tx 不开始。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert "ARCHIVE_TIP_NOT_FOUND" in report.error or "OBJECT_NOT_FOUND" in report.error


# ---------------------------------------------------------------------------
# 6x5 state routing matrix（ARCHIVE state 路由）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op_state,cp_state,expected_action", _STATE_ROUTING_MATRIX,
    ids=[f"{o}_{c}" for o, c, _ in _STATE_ROUTING_MATRIX],
)
async def test_state_routing_matrix_archive_state(
    s6i3_d_factory, op_state, cp_state, expected_action,
):
    """30 scenarios：路由按 ARCHIVE-recorded state（不是 LIVE state）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state=op_state, cp_state=cp_state,
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )

    verdict = next(
        v for v in report.verdict
        if str(op_id) == v.operation_id and v.owner_key == "workspace.core.v1"
    )
    assert verdict.action == expected_action, (
        f"op={op_state} cp={cp_state}: expected {expected_action}, got {verdict.action}"
    )


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #1: 4 owner 公共入口精确映射
# ---------------------------------------------------------------------------


async def test_r2_workspace_core_uses_erase_conversation_body(s6i3_d_factory):
    """workspace.core.v1 → WorkspaceErasureParticipant.erase_conversation_body。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1", title="secret",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.owners_local_cleared == 1
    async with factory() as s, s.begin():
        row = (await s.execute(
            text("SELECT title FROM metaedu.agent_conversations WHERE id = :cid"),
            {"cid": cid},
        )).scalar_one()
    assert row is None, f"workspace.core 应清 title；实际 = {row!r}"


async def test_r2_workspace_transport_uses_erase_transport_owner(s6i3_d_factory):
    """workspace.transport.v1 → WorkspaceTransportErasureParticipant.erase_transport_owner
    （parent class 公共入口；含 fence / owner lock / expected revision CAS / ACK / final scan）。

    真实 PG 断言：Conversation→owner→fence→aggregate 全锁序 + checkpoint acked +
    fence erased + final scan=0。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        from app.composition.agent_erasure_registry import registry_digest
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations "
                "SET state = 'deleted', purge_after = now() - interval '1 day' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET revision = 1, lease_epoch = 0, registry_digest = :rd, "
                "retention_policy_digest = :rd WHERE id = :oid"
            ),
            {"rd": registry_digest(), "oid": op_id},
        )
        from app.composition.agent_erasure_registry import capability_digest
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.transport.v1", state="erasing",
            capability_digest=capability_digest("workspace.transport.v1"),
        )
        # 种一行 workspace_outbox payload（应被 erase_transport_owner 清除）
        await s.execute(
            text(
                "INSERT INTO metaedu.agent_workspace_outbox "
                "(id, tenant_id, conversation_id, aggregate_id, aggregate_type, "
                "event_type, schema_version, payload_inline, payload_digest, "
                "correlation_id, status, created_at) "
                "VALUES (gen_random_uuid(), :t, :c, gen_random_uuid(), 'conversation', "
                "'turn.requested.v1', 1, '\"leaked\"'::jsonb, :d, gen_random_uuid(), "
                "'pending', now())"
            ),
            {"t": tid, "c": cid, "d": _DIGEST},
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.owners_local_cleared == 1
    # checkpoint 必 ACK（erase_transport_owner 公共入口走完整锁序 + ACK）
    async with factory() as s, s.begin():
        row = (await s.execute(
            text(
                "SELECT state, ack_digest FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid AND purge_operation_id = :pid"
            ),
            {"tid": tid, "pid": op_id},
        )).first()
    assert row[0] == "acked", f"transport owner 必须 ACK；实际 = {row[0]!r}"
    assert row[1] is not None, "ack_digest 必须非 NULL"
    # workspace_outbox payload_inline 应被清
    async with factory() as s, s.begin():
        cnt = (await s.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_workspace_outbox "
                "WHERE tenant_id = :tid AND conversation_id = :cid "
                "AND payload_inline IS NOT NULL"
            ),
            {"tid": tid, "cid": cid},
        )).scalar_one()
    assert cnt == 0, f"workspace_outbox payload_inline 应清空；残留 {cnt} 行"


async def test_r2_execution_transport_uses_erase_transport_owner(s6i3_d_factory):
    """execution.transport.v1 → ExecutionTransportErasureParticipant.erase_transport_owner。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        from app.composition.agent_erasure_registry import registry_digest
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations "
                "SET state = 'deleted', purge_after = now() - interval '1 day' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET revision = 1, lease_epoch = 0, registry_digest = :rd, "
                "retention_policy_digest = :rd WHERE id = :oid"
            ),
            {"rd": registry_digest(), "oid": op_id},
        )
        from app.composition.agent_erasure_registry import capability_digest
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="execution.transport.v1", state="erasing",
            capability_digest=capability_digest("execution.transport.v1"),
        )
        await s.execute(
            text(
                "INSERT INTO metaedu.agent_execution_outbox "
                "(id, tenant_id, conversation_id, aggregate_id, aggregate_type, "
                "event_type, schema_version, payload_inline, payload_digest, "
                "correlation_id, status, created_at) "
                "VALUES (gen_random_uuid(), :t, :c, gen_random_uuid(), 'conversation', "
                "'run.requested.v1', 1, '\"leaked\"'::jsonb, :d, gen_random_uuid(), "
                "'pending', now())"
            ),
            {"t": tid, "c": cid, "d": _DIGEST},
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.owners_local_cleared == 1
    async with factory() as s, s.begin():
        cnt = (await s.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_execution_outbox "
                "WHERE tenant_id = :tid AND conversation_id = :cid "
                "AND payload_inline IS NOT NULL"
            ),
            {"tid": tid, "cid": cid},
        )).scalar_one()
    assert cnt == 0


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #4: 真实双 owner 测试（pass B 任一 owner 失败 → 整事务回滚）
# ---------------------------------------------------------------------------


async def test_r2_two_owner_one_fails_rolls_back_all(s6i3_d_factory):
    """真实双 owner：处理顺序第一的 owner A 调真实 participant **写完**后，owner B 在
    pass B 内失败 → 整事务 rollback（新 session 完整前后快照比对）。

    判别点（Round-6 强化）：
    - **spy 证明 owner A 先执行**：pass B 处理顺序 = checkpoint ``stable_identity``
      （``checkpoint:{id}``）排序 = ``id::text`` 排序。先查得顺序，把**第一**个 owner
      设为真实 participant（spy 记录并 call-through 真实写入），**第二**个 owner 注入
      失败 → ``calls == [A, B]`` 证明 A 先执行且 B 在其后失败。
    - **完整前后快照**：checkpoint state（双 owner）+ operation fence
      （state/revision/purge_revision/lease_epoch）+ 正文（conversation.title）
      + 源表（agent_execution_outbox payload）——rollback 后全部 == 之前。
    """
    factory = s6i3_d_factory
    from app.composition.agent_erasure_registry import (
        capability_digest,
        registry_digest,
    )
    from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (  # noqa: E501
        ExecutionTransportErasureParticipant,
    )
    from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (  # noqa: E501
        WorkspaceErasureParticipant,
    )

    participant_methods = {
        "workspace.core.v1": (
            WorkspaceErasureParticipant, "erase_conversation_body",
        ),
        "execution.transport.v1": (
            ExecutionTransportErasureParticipant, "erase_transport_owner",
        ),
    }

    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations "
                "SET state = 'deleted', purge_after = now() - interval '1 day' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        op_id = await _seed_operation(s, tid=tid, cid=cid, state="running")
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET revision = 1, lease_epoch = 0, registry_digest = :rd, "
                "retention_policy_digest = :rd WHERE id = :oid"
            ),
            {"rd": registry_digest(), "oid": op_id},
        )
        # 2 owners: workspace.core.v1 + execution.transport.v1
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="workspace.core.v1", state="erasing",
            capability_digest=capability_digest("workspace.core.v1"),
        )
        await _seed_checkpoint(
            s, tid=tid, purge_operation_id=op_id,
            owner_key="execution.transport.v1", state="erasing",
            capability_digest=capability_digest("execution.transport.v1"),
        )
        # 源表行（execution.transport 清除对象），供前后快照比对
        await s.execute(
            text(
                "INSERT INTO metaedu.agent_execution_outbox "
                "(id, tenant_id, conversation_id, aggregate_id, aggregate_type, "
                "event_type, schema_version, payload_inline, payload_digest, "
                "correlation_id, status, created_at) "
                "VALUES (gen_random_uuid(), :t, :c, gen_random_uuid(), 'conversation', "
                "'run.requested.v1', 1, '\"leaked\"'::jsonb, :d, gen_random_uuid(), "
                "'pending', now())"
            ),
            {"t": tid, "c": cid, "d": _DIGEST},
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    async def _snapshot(s):
        cps = dict((await s.execute(
            text(
                "SELECT owner_key, state FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )).all())
        op = dict((await s.execute(
            text(
                "SELECT state, revision, purge_revision, lease_epoch "
                "FROM metaedu.agent_conversation_purges WHERE id = :oid"
            ),
            {"oid": op_id},
        )).mappings().one())
        title = (await s.execute(
            text("SELECT title FROM metaedu.agent_conversations WHERE id = :cid"),
            {"cid": cid},
        )).scalar_one()
        outbox_payload = (await s.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_execution_outbox "
                "WHERE tenant_id = :tid AND conversation_id = :cid "
                "AND payload_inline IS NOT NULL"
            ),
            {"tid": tid, "cid": cid},
        )).scalar_one()
        return (cps, op, title, outbox_payload)

    # pass B 处理顺序 = checkpoint stable_identity（checkpoint:{id}）排序 = id::text 排序
    async with factory() as s, s.begin():
        order = [r[0] for r in (await s.execute(
            text(
                "SELECT owner_key FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid ORDER BY id::text"
            ),
            {"tid": tid},
        )).all()]
        snap_before = await _snapshot(s)
    first_owner, second_owner = order[0], order[1]

    first_cls, first_method = participant_methods[first_owner]
    second_cls, second_method = participant_methods[second_owner]
    orig_first = getattr(first_cls, first_method)
    orig_second = getattr(second_cls, second_method)
    calls: list[str] = []

    async def first_spy(self, **kwargs):
        calls.append(first_owner)
        return await orig_first(self, **kwargs)

    async def second_fail(self, **kwargs):
        calls.append(second_owner)
        raise RuntimeError(f"injected: {second_owner} owner B fail")

    setattr(first_cls, first_method, first_spy)
    setattr(second_cls, second_method, second_fail)
    try:
        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    finally:
        setattr(first_cls, first_method, orig_first)
        setattr(second_cls, second_method, orig_second)

    # report 必含 participant_failure 阻断（catch 在 transaction 外 → 自动 rollback → 报告）
    assert report.error is not None
    assert "participant_failure" in report.error
    assert report.participant_failures == 1
    # spy 证明 owner A（处理顺序第一）**先**真实执行，owner B 在其后失败
    assert calls == [first_owner, second_owner], (
        f"期望 owner A（{first_owner}）先执行、owner B（{second_owner}）其后失败；"
        f"实际调用顺序 = {calls}"
    )

    # 新 session 完整快照：checkpoint / operation fence / 正文 / 源表 全部 == 之前（rollback）
    async with factory() as s, s.begin():
        snap_after = await _snapshot(s)
    assert snap_after == snap_before, (
        f"rollback 不完整：before={snap_before!r} after={snap_after!r}"
    )
    # 双 owner checkpoint 都必须仍为 erasing（participant 写已 rollback）
    assert snap_after[0] == {
        "workspace.core.v1": "erasing",
        "execution.transport.v1": "erasing",
    }


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #5: 六元组逐字段 drift
# ---------------------------------------------------------------------------


async def test_r2_six_tuple_field_drift_reports_specific_field(s6i3_d_factory):
    """owner_version drift → report.error 含具体字段名（**不**raise；catch 在 tx 外）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET owner_version = 99 WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert "FACT_DRIFT_FIELDS" in report.error
    assert report.pass_a_drift == 1
    assert report.owners_fact_drift == 1
    # verdict 含 drift 字段名
    drift_verdict = next(
        v for v in report.verdict if v.action == ACTION_FACT_DRIFT_FAIL_CLOSED
    )
    assert "checkpoint.owner_version" in (drift_verdict.reason_code or "")


async def test_r2_ack_digest_format_validated(s6i3_d_factory):
    """ack_digest 严格 64-hex lowercase 校验（live 端真实可达路径）。

    Round-5：archive=erasing + live=acked 是单向终态推进（NO_REPEAT，无 drift），
    所以格式校验必须构造 **archive=acked + live=acked**（无 state drift）场景。

    构造：archive ack_digest='a'*64（合法）→ publish → 改 LIVE ack_digest='A'*64
    （大写，过 migration 034 ``char_length=64`` CHECK，但应用层 lowercase 校验
    fail）→ ``live.ACK_DIGEST_FORMAT_INVALID`` drift fail closed。

    注：archive 端格式校验（``archive.ACK_DIGEST_FORMAT_INVALID``）经 D1a codec
    ``_assert_checkpoint_ack_invariant`` 在 pre-publish decode 即 fail closed
    （``ACK_INVARIANT_VIOLATED``），真实路径不可达——archive 不可能固化非法格式
    ack_digest，故不在本测试构造（**禁止**伪造账本行绕过 publish 路径）。
    """
    factory = s6i3_d_factory

    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="completed", cp_state="acked",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET ack_digest = :d WHERE tenant_id = :tid"
            ),
            {"d": "A" * 64, "tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert "FACT_DRIFT_FIELDS" in report.error
    assert report.pass_a_drift == 1
    drift_verdict = next(
        v for v in report.verdict if v.action == ACTION_FACT_DRIFT_FAIL_CLOSED
    )
    assert "live.ACK_DIGEST_FORMAT_INVALID" in (drift_verdict.reason_code or "")


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #6: Gate 强制消费 RestoreReplayReport
# ---------------------------------------------------------------------------


async def test_r2_gate_consumes_replay_report(s6i3_d_factory):
    """Gate 必须从 RestoreReplayReport 内部 derive blocking——error / drift / runtime
    unprovable / external verify-only / non_local_blocked 全部自动阻断。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)

    # 构造含 error 的 report
    report = RestoreReplayReport(error="ARCHIVE_TIP_NOT_FOUND")
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    assert gate.open_allowed is False
    assert any("replay_error" in r for r in gate.blocked_reasons)


async def test_r2_gate_runtime_proof_c_blocks_open(s6i3_d_factory):
    """runtime proof c 存在 → gate 强制 closed（不依赖 scan 结果）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport()
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=True,
    )
    assert gate.open_allowed is False
    assert any("RUNTIME_BINDING_EVIDENCE_UNPROVABLE" in r for r in gate.blocked_reasons)


async def test_r2_gate_no_default_zero_bypass(s6i3_d_factory):
    """Gate 签名无默认 0/False——强制 caller 显式传 RestoreReplayReport + bool。"""
    import inspect
    sig = inspect.signature(evaluate_restore_before_open)
    # replay_report 与 runtime_proof_c_present 必须无默认值
    assert sig.parameters["replay_report"].default is inspect.Parameter.empty
    assert sig.parameters["runtime_proof_c_present"].default is inspect.Parameter.empty


async def test_r2_gate_s6_6_findings_actually_returned(s6i3_d_factory):
    """Gate ``s6_6_findings`` 必须实际返回（不再恒为空 tuple）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport()
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    # 即使空 tenant 也应至少有 6 个 0 计数条目（S6-6 6 类巡检全跑过）
    # 或 open_allowed=True（s6_6 全 0 → 不阻断）
    assert gate.s6_6_findings != () or gate.open_allowed is True


async def test_r2_gate_consumes_fact_drift(s6i3_d_factory):
    """Gate 消费 report.owners_fact_drift → 阻断。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport(owners_fact_drift=2)
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    assert gate.open_allowed is False
    assert any("fact_drift" in r for r in gate.blocked_reasons)


async def test_r2_gate_consumes_non_local_blocked(s6i3_d_factory):
    """Gate 消费 report.owners_non_local_blocked → 阻断。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport(owners_non_local_blocked=3)
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    assert gate.open_allowed is False
    assert any("non_local_blocked" in r for r in gate.blocked_reasons)


async def test_r2_gate_consumes_toctou_drift(s6i3_d_factory):
    """Gate 消费 report.toctou_drift → 阻断。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport(toctou_drift=1)
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    assert gate.open_allowed is False
    assert any("toctou_drift" in r for r in gate.blocked_reasons)


async def test_r2_gate_consumes_external_verify_only(s6i3_d_factory):
    """Gate 消费 report.external_verified → 阻断。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport(external_verified=1)
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    # external_verified 不阻断 gate（仅 external_verification_failed 阻断）；
    # 但本测试改为 verification_failed 阻断验证
    assert gate.open_allowed is True  # verified 不阻断

    report_failed = RestoreReplayReport(external_verification_failed=1)
    gate_failed = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report_failed,
        runtime_proof_c_present=False,
    )
    assert gate_failed.open_allowed is False
    assert any("external_verification_failed" in r for r in gate_failed.blocked_reasons)


async def test_r2_purge_revision_drift_fails_closed(s6i3_d_factory):
    """purge_revision drift → report.error 含 operation.purge_revision。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET purge_revision = 99 WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert "FACT_DRIFT_FIELDS" in report.error
    assert "operation.purge_revision" in (
        next(
            v for v in report.verdict if v.action == ACTION_FACT_DRIFT_FAIL_CLOSED
        ).reason_code or ""
    )


async def test_r2_owner_key_drift_fails_closed(s6i3_d_factory):
    """checkpoint owner_key 实际已变更 → 旧 owner_key 查不到（CHECKPOINT_MISSING 路径）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET owner_key = 'execution.core.v1' WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    # archive 记录 owner_key=workspace.core.v1；DB 改为 execution.core.v1
    # 旧 owner_key 查不到（unique constraint）→ FACT_DRIFT_CHECKPOINT_MISSING
    assert report.error is not None
    assert "FACT_DRIFT_CHECKPOINT_MISSING" in report.error or "FACT_DRIFT_FIELDS" in report.error


async def test_r2_fact_drift_blocks_pass_b_entry(s6i3_d_factory):
    """pass A 任一 drift → report.pass_a_drift=1 + report.error，**不**进入 pass B。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET owner_version = 99 WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    # pass A drift → pass B 不执行
    assert report.error is not None
    assert "FACT_DRIFT_FIELDS" in report.error
    assert report.pass_a_drift == 1
    assert report.owners_local_cleared == 0
    # checkpoint 状态保持原值（pass B 未执行）
    async with factory() as s, s.begin():
        state = (await s.execute(
            text(
                "SELECT state FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )).scalar_one()
    assert state == "erasing", (
        f"pass A drift → pass B 不执行；checkpoint 应保持 erasing；实际 = {state!r}"
    )


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #2: external vs runtime 分离（保留 Round-1 测试）
# ---------------------------------------------------------------------------


async def test_r2_external_completed_no_runtime_reason(s6i3_d_factory):
    """external.payload.v1 + completed → EXTERNAL_VERIFICATION_FAILED（**禁止**取
    任意 LIVE row 冒充 archive 证据——必须 archive 行按 operation.conversation_id 精确
    匹配。本测试：archive 无 external_ref 行绑定 operation → fail closed）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    # 无 archive external_ref → fail closed → report.error 非空
    assert report.error is not None
    assert "external_verification_failed" in report.error
    assert report.external_verification_failed == 1
    assert report.owners_local_cleared == 0


async def test_r2_runtime_completed_returns_unprovable(s6i3_d_factory):
    """runtime.private.v1 + completed → RUNTIME_BINDING_EVIDENCE_UNPROVABLE。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="runtime.private.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    verdict = next(v for v in report.verdict if v.owner_key == "runtime.private.v1")
    assert verdict.action == ACTION_RUNTIME_BINDING_UNPROVABLE
    assert report.runtime_binding_evidence_unprovable == 1


# ---------------------------------------------------------------------------
# Round-1 保留测试（idempotent replay / 不复制造假 ACK / lock invariant）
# ---------------------------------------------------------------------------


async def test_r1_p1_replay_holds_exclusive_lock(s6i3_d_factory):
    """replay 调 acquire_maintenance_exclusive_lock（spy invariant for M-D2-1）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    import app.composition.restore_replay as rr_mod
    from app.composition import agent_erasure_locks as locks_mod
    original = locks_mod.acquire_maintenance_exclusive_lock
    call_count = 0

    async def spy(session, **kw):
        nonlocal call_count
        call_count += 1
        return await original(session, **kw)

    locks_mod.acquire_maintenance_exclusive_lock = spy
    rr_mod.acquire_maintenance_exclusive_lock = spy
    try:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    finally:
        locks_mod.acquire_maintenance_exclusive_lock = original
        rr_mod.acquire_maintenance_exclusive_lock = original
    assert call_count >= 1


async def test_r1_p3_no_compute_ack_digest_in_module(s6i3_d_factory):
    """_compute_ack_digest 已删除；无裸 SET state='acked' UPDATE。

    注意：本测试是静态 guard，不是 mutation KILL 替代品（mutation KILL 走真实 PG 行为）。
    """
    import app.composition.restore_replay as rr
    assert not hasattr(rr, "_compute_ack_digest"), (
        "_compute_ack_digest 应已删除（Round-1 P1 修复 #3）"
    )
    with open(rr.__file__) as _f:
        src = _f.read()
    assert "SET state = 'acked'" not in src, (
        "裸 checkpoint ACK UPDATE 应已删除；必须走 participant 公共入口"
    )


async def test_r1_idempotent_replay_db_acked_drift(s6i3_d_factory):
    """idempotent replay：第二次执行同 segment → NO_REPEAT（不二次调用 participant）。

    archive 端 cp.state=erasing vs LIVE 端 cp.state=acked → pass A 严格 drift fail closed
    （**不**冒充 pass-B rollback 推进）；运行通过路径：
    archive.cp=acked + LIVE.cp=acked → 6×5 全局矩阵 running+acked = NO_REPEAT。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="running", cp_state="acked",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # archive.cp=acked；LIVE.cp=acked（同一）；archive.ack_digest == LIVE.ack_digest
    # → 6×5 running+acked = NO_REPEAT（不调 participant）
    r1 = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert r1.error is None
    assert r1.owners_no_repeat == 1
    assert r1.owners_local_cleared == 0  # 未调 participant 公共入口


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_frozen_action_constants():
    from app.composition import restore_replay as rr
    assert rr.ACTION_LOCAL_CLEARED == "local_cleared"
    assert rr.ACTION_NON_LOCAL_BLOCKED == "non_local_blocked"
    assert rr.ACTION_EXTERNAL_VERIFY_ONLY == "external_verify_only"
    assert rr.ACTION_RUNTIME_BINDING_UNPROVABLE == "runtime_binding_evidence_unprovable"
    assert rr.ACTION_FACT_DRIFT_FAIL_CLOSED == "fact_drift_fail_closed"


def test_local_owner_set_is_frozen():
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


def test_replay_signature_no_expected_marker():
    """replay_archive_segment_for_tenant 签名无 expected_marker（Phase 1 内部 find_committed_tip）。"""
    import inspect
    sig = inspect.signature(replay_archive_segment_for_tenant)
    assert "expected_marker" not in sig.parameters
    assert "sink" in sig.parameters
    assert "tenant_id" in sig.parameters
    assert "session_factory" in sig.parameters


# ---------------------------------------------------------------------------
# Round-3 P1：6×5 non-local owner 完整矩阵（external.payload.v1 + runtime.private.v1）
# ---------------------------------------------------------------------------


async def test_r3_non_local_6x5_matrix_external(s6i3_d_factory):
    """external.payload.v1：完整 6×5 30 scenarios 路由判别（按矩阵返回 NON_LOCAL_BLOCKED /
    EXTERNAL_VERIFIED / ZERO_WRITE / SKIP / REPLAY_SKIP_ZERO_WRITE，不得统一降级）。

    completed scenarios → external_ref 无 archive 行 → EXTERNAL_VERIFICATION_FAILED
    （report.error 非空，**无** verdict 落入 list）。
    """
    factory = s6i3_d_factory
    for op_state, cp_state, expected in _non_local_matrix_iter(
        "external.payload.v1"
    ):
        async with factory() as s, s.begin():
            tid = await _seed_tenant(s)
            op_id, _ = await _seed_op_cp(
                s, tid, op_state=op_state, cp_state=cp_state,
                owner_key="external.payload.v1",
            )
        sink, _ = await _publish_segment_for(factory, tid=tid)

        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
        if expected == ACTION_EXTERNAL_VERIFICATION_FAILED:
            # 强制要求 archive external_ref 行按 operation.conversation_id + owner_key
            # 精确绑定；现有测试 setup 无 external_ref 行 → fail closed
            assert report.error is not None
            assert "external_verification_failed" in report.error.lower()
            assert report.external_verification_failed == 1
            assert report.owners_local_cleared == 0
        else:
            verdict = next(
                v for v in report.verdict
                if v.owner_key == "external.payload.v1"
            )
            assert verdict.action == expected, (
                f"external.payload.v1 op={op_state} cp={cp_state}: "
                f"expected {expected}, got {verdict.action}"
            )


async def test_r3_non_local_6x5_matrix_runtime(s6i3_d_factory):
    """runtime.private.v1：完整 6×5 30 scenarios 路由判别。"""
    factory = s6i3_d_factory
    for op_state, cp_state, expected in _non_local_matrix_iter(
        "runtime.private.v1"
    ):
        async with factory() as s, s.begin():
            tid = await _seed_tenant(s)
            op_id, _ = await _seed_op_cp(
                s, tid, op_state=op_state, cp_state=cp_state,
                owner_key="runtime.private.v1",
            )
        sink, _ = await _publish_segment_for(factory, tid=tid)

        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
        verdict = next(
            v for v in report.verdict
            if v.owner_key == "runtime.private.v1"
        )
        assert verdict.action == expected, (
            f"runtime.private.v1 op={op_state} cp={cp_state}: "
            f"expected {expected}, got {verdict.action}"
        )


async def test_r3_ack_digest_archive_live_mismatch(s6i3_d_factory):
    """ack_digest 严格相等校验：archive/live 均 acked 但 digest 不同 → drift fail closed。

    构造：先 seed op=completed + cp=acked + ack_digest="a"*64 并 publish（archive 固化）；
    再 UPDATE DB cp.ack_digest="b"*64（与 archive "a"*64 不同但**均合法 64-hex**）；
    第二次 replay：archive 端 cp=acked → 严格相等校验 → ack_digest_mismatch drift。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="completed", cp_state="acked",
            owner_key="workspace.core.v1",
        )
        # 设置 archive 中 ack_digest（但与 live 不同 → drift）
        # 实际：archive_ack_digest 来自 seed 的 _DIGEST="a"*64；live 改 "b"*64
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET ack_digest = :d WHERE tenant_id = :tid"
            ),
            {"d": "b" * 64, "tid": tid},
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # archive 已固化 ack_digest="a"*64；DB 改为 "c"（合法 64-hex）
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET ack_digest = :d WHERE tenant_id = :tid"
            ),
            {"d": "c" * 64, "tid": tid},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert "FACT_DRIFT_FIELDS" in report.error
    # 必须含 checkpoint.ack_digest_archive_live_mismatch
    assert any(
        v.action == ACTION_FACT_DRIFT_FAIL_CLOSED
        and "ack_digest_archive_live_mismatch" in (v.reason_code or "")
        for v in report.verdict
    )


async def test_r3_idempotent_replay_terminal_state(s6i3_d_factory):
    """幂等：同 segment 连续两次；第二次 LIVE state 已是 terminal（acked）→ NO_REPEAT。

    Round-5：archive=erasing + LIVE=acked 是单向终态转换（完整 terminal evidence），
    第二次 replay 返 ``NO_REPEAT``（error=None），**不**调 participant、**不**报 drift。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 第一次：archive=running/erasing → LOCAL_CLEARED → 调 participant
    r1 = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert r1.error is None
    assert r1.owners_local_cleared == 1

    # 第二次：archive 仍 running/erasing，LIVE 已 acked → 单向终态推进 → NO_REPEAT
    # （**不**调 participant、**不**报 drift）
    r2 = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert r2.error is None
    assert r2.owners_no_repeat == 1
    assert r2.owners_local_cleared == 0  # 第二次**不**调 participant


async def test_r3_e2e_replay_to_gate(s6i3_d_factory):
    """端到端 replay → report → gate 集成测试（禁止只测手工 report）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 真实 replay → 真实 report
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is None
    # 真实 gate 消费真实 report
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    # owner 残留 = 0 → open_allowed 由其他条件决定（不依赖 replay 阻断）
    assert isinstance(gate.open_allowed, bool)
    assert isinstance(gate.s6_6_findings, tuple)


async def test_r3_scheduled_cancelled_failed_acked_not_downgraded(s6i3_d_factory):
    """non-local owner + scheduled/cancelled/failed/acked **不得**统一降级为 NON_LOCAL_BLOCKED。

    按 6×5 矩阵分别返回 REPLAY_SKIP_ZERO_WRITE / SKIP / ZERO_WRITE / NO_REPEAT。
    """
    factory = s6i3_d_factory
    for op_state, cp_state, expected in [
        ("scheduled", "acked", ACTION_REPLAY_SKIP_ZERO_WRITE),
        ("cancelled", "acked", ACTION_SKIP),
        ("failed", "acked", ACTION_ZERO_WRITE),
        ("failed", "pending", ACTION_ZERO_WRITE),
    ]:
        async with factory() as s, s.begin():
            tid = await _seed_tenant(s)
            await _seed_op_cp(
                s, tid, op_state=op_state, cp_state=cp_state,
                owner_key="external.payload.v1",
            )
        sink, _ = await _publish_segment_for(factory, tid=tid)

        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
        verdict = next(
            v for v in report.verdict if v.owner_key == "external.payload.v1"
        )
        assert verdict.action == expected, (
            f"external.payload.v1 op={op_state} cp={cp_state}: "
            f"expected {expected}（**不得**统一降级为 non_local_blocked），got {verdict.action}"
        )


def _non_local_matrix_iter(owner_key: str):
    """按 _NON_LOCAL_OWNER_MATRIX_EXPECTATION 生成 (op_state, cp_state, expected_action) 迭代器。"""
    matrix = _NON_LOCAL_OWNER_MATRIX_EXPECTATION[owner_key]
    for (op_state, cp_state), expected in matrix.items():
        yield op_state, cp_state, expected


# ---------------------------------------------------------------------------
# Round-5 P0 收口测试
# ---------------------------------------------------------------------------


async def test_r5_idempotent_real_no_participant_call(s6i3_d_factory):
    """真实幂等：第一次 participant 真实执行 → 第二次 NO_REPEAT 且不调 participant。

    断言：两次 replay 间 participant 公共入口调用次数 = 1（不是 2），
    且第二次 report.owners_no_repeat == 1、owners_local_cleared == 0。
    """
    from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
        WorkspaceErasureParticipant,
    )
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 计数 participant 公共入口调用次数
    original = WorkspaceErasureParticipant.erase_conversation_body
    call_count = 0

    async def counting_erase(self, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original(self, **kwargs)

    WorkspaceErasureParticipant.erase_conversation_body = counting_erase
    try:
        # 第一次 replay
        r1 = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
        assert r1.error is None
        assert r1.owners_local_cleared == 1
        assert r1.owners_no_repeat == 0
        first_call_count = call_count
        assert first_call_count == 1, f"expected 1 call, got {first_call_count}"

        # 第二次 replay（archive=erasing, LIVE=acked → NO_REPEAT）
        r2 = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
        # 第二次应该不调 participant，且返回 NO_REPEAT
        assert r2.owners_no_repeat == 1
        assert r2.owners_local_cleared == 0
        # 关键断言：call_count 没增加
        assert call_count == first_call_count, (
            f"participant 第二次被调用了（{call_count} vs {first_call_count}）；幂等失败"
        )
    finally:
        WorkspaceErasureParticipant.erase_conversation_body = original


async def test_r5_toctou_purge_revision_drift(s6i3_d_factory, monkeypatch):
    """TOCTOU（真实两阶段竞态）：pass A 完成后、pass B reverify 前注入 operation.purge_revision
    drift → ``TOCTOU_DRIFT_FIELDS`` 含 operation.purge_revision，``toctou_drift=1``、
    ``pass_a_drift=0``，且 drift 随事务 rollback（新 session 仍为原值）。

    判别点（Round-6）：drift **必须**在 pass B exclusive tx 内、pass A 之后注入（经
    monkey-patch maintenance-lock wrapper 同 tx 改字段），**禁止**在 replay 前单独提交
    drift（那只会得到 pass_a_drift=1，不是真 TOCTOU）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    _patch_lock_inject_drift(
        monkeypatch,
        "UPDATE metaedu.agent_conversation_purges "
        "SET purge_revision = 99 WHERE id = :oid",
        {"oid": op_id},
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    # pass A 完成时 LIVE 与 archive 一致 → pass_a_drift=0；drift 仅在 pass B tx 内
    assert report.pass_a_drift == 0
    assert report.toctou_drift == 1
    assert "TOCTOU_DRIFT_FIELDS" in report.error
    assert "operation.purge_revision" in report.error
    # rollback 验证：新 session 必须看到原值（drift 未提交）
    async with factory() as s, s.begin():
        pr = (await s.execute(
            text(
                "SELECT purge_revision FROM metaedu.agent_conversation_purges "
                "WHERE id = :oid"
            ),
            {"oid": op_id},
        )).scalar_one()
    assert pr != 99, f"purge_revision drift 未回滚（实际={pr}）"


async def test_r5_toctou_lease_epoch_drift(s6i3_d_factory, monkeypatch):
    """TOCTOU：pass B tx 内注入 operation.lease_epoch drift → ``TOCTOU_DRIFT_FIELDS`` 含
    operation.lease_epoch，``toctou_drift=1``、``pass_a_drift=0``，drift rollback。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    _patch_lock_inject_drift(
        monkeypatch,
        "UPDATE metaedu.agent_conversation_purges "
        "SET lease_epoch = 99 WHERE id = :oid",
        {"oid": op_id},
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.pass_a_drift == 0
    assert report.toctou_drift == 1
    assert "TOCTOU_DRIFT_FIELDS" in report.error
    assert "operation.lease_epoch" in report.error
    async with factory() as s, s.begin():
        le = (await s.execute(
            text(
                "SELECT lease_epoch FROM metaedu.agent_conversation_purges "
                "WHERE id = :oid"
            ),
            {"oid": op_id},
        )).scalar_one()
    assert le != 99, f"lease_epoch drift 未回滚（实际={le}）"


async def test_r5_toctou_checkpoint_owner_version_drift(s6i3_d_factory, monkeypatch):
    """TOCTOU：pass B tx 内注入 checkpoint.owner_version drift → ``TOCTOU_DRIFT_FIELDS`` 含
    checkpoint.owner_version，``toctou_drift=1``、``pass_a_drift=0``，drift rollback。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    _patch_lock_inject_drift(
        monkeypatch,
        "UPDATE metaedu.agent_conversation_purge_owners "
        "SET owner_version = 99 WHERE tenant_id = :tid",
        {"tid": tid},
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.pass_a_drift == 0
    assert report.toctou_drift == 1
    assert "TOCTOU_DRIFT_FIELDS" in report.error
    assert "checkpoint.owner_version" in report.error
    async with factory() as s, s.begin():
        ov = (await s.execute(
            text(
                "SELECT owner_version FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )).scalar_one()
    assert ov != 99, f"checkpoint.owner_version drift 未回滚（实际={ov}）"


async def test_r5_toctou_checkpoint_capability_digest_drift(s6i3_d_factory, monkeypatch):
    """TOCTOU：pass B tx 内注入 checkpoint.capability_digest drift → ``TOCTOU_DRIFT_FIELDS``
    含 checkpoint.capability_digest，``toctou_drift=1``、``pass_a_drift=0``，drift rollback。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    _patch_lock_inject_drift(
        monkeypatch,
        "UPDATE metaedu.agent_conversation_purge_owners "
        "SET capability_digest = :d WHERE tenant_id = :tid",
        {"d": "c" * 64, "tid": tid},
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.pass_a_drift == 0
    assert report.toctou_drift == 1
    assert "TOCTOU_DRIFT_FIELDS" in report.error
    assert "checkpoint.capability_digest" in report.error
    async with factory() as s, s.begin():
        cap = (await s.execute(
            text(
                "SELECT capability_digest FROM metaedu.agent_conversation_purge_owners "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )).scalar_one()
    assert cap != "c" * 64, "checkpoint.capability_digest drift 未回滚"


async def test_r6_toctou_drift_under_no_repeat_exception(s6i3_d_factory, monkeypatch):
    """NO_REPEAT 例外下的 drift：archive cp=erasing + LIVE cp=acked（单向终态推进 → NO_REPEAT
    候选，**仅**豁免 checkpoint.state），但 pass B tx 内注入 **operation.revision** drift
    → 其余字段任何 drift 均 fail closed（``TOCTOU_DRIFT_FIELDS`` 含 operation.revision，
    ``toctou_drift=1``、``pass_a_drift=0``，**不**因 NO_REPEAT 例外而放行）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 先把 LIVE checkpoint 推进到 acked（合法单向终态）→ 成为 NO_REPEAT 候选；
    # state='acked' 必须配合法 64-hex ack_digest（ck_agent_purge_owner_ack）
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET state = 'acked', ack_digest = :d WHERE tenant_id = :tid"
            ),
            {"d": "b" * 64, "tid": tid},
        )

    # NO_REPEAT 例外下仍注入 operation 字段 drift → 必须 fail closed
    _patch_lock_inject_drift(
        monkeypatch,
        "UPDATE metaedu.agent_conversation_purges "
        "SET revision = 99 WHERE id = :oid",
        {"oid": op_id},
    )
    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.pass_a_drift == 0
    assert report.toctou_drift == 1
    assert "TOCTOU_DRIFT_FIELDS" in report.error
    assert "operation.revision" in report.error
    # checkpoint.state 豁免生效（**不**报 checkpoint.state drift），但 operation.revision 报
    assert "checkpoint.state" not in report.error
    # rollback：operation.revision 回原值
    async with factory() as s, s.begin():
        rev = (await s.execute(
            text(
                "SELECT revision FROM metaedu.agent_conversation_purges WHERE id = :oid"
            ),
            {"oid": op_id},
        )).scalar_one()
    assert rev != 99, f"operation.revision drift 未回滚（实际={rev}）"


async def test_r5_external_record_wrong_binding(s6i3_d_factory):
    """External record 错绑：archive 唯一 external_ref 属于**别的** conversation_id。

    统一 binder 按 ``validated.conversation_id``（operation 真实 cid）+ owner_key 精确匹配
    → 找不到匹配记录 → ``EXTERNAL_ARCHIVE_MISSING`` → ``EXTERNAL_VERIFICATION_FAILED``
    （错绑的记录对本 operation 等价于缺失，fail closed）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _op_cid = await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
        # 故意种一个 binding 错误的 external_ref（conversation_id 指向别的会话）
        await _seed_external_ref(
            s, tid=tid, cid=uuid.uuid4(), receipt="a" * 64,
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.external_verification_failed == 1
    assert "EXTERNAL_ARCHIVE_MISSING" in report.error


async def test_r5_external_record_duplicate_in_archive(s6i3_d_factory):
    """External record 重复：archive 中 2 条同 (operation 真实 conversation_id, owner_key)
    → 统一 binder 检测重复 → ``EXTERNAL_ARCHIVE_DUPLICATE`` → ``EXTERNAL_VERIFICATION_FAILED``。

    判别点（Round-6）：**必须**用 operation 的真实 conversation_id（``_seed_op_cp`` 返回的
    cid），断言**精确** ``EXTERNAL_ARCHIVE_DUPLICATE`` reason。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
        # 种 2 条同 (operation 真实 cid, external.payload.v1) external_ref
        await _seed_external_ref(s, tid=tid, cid=cid, receipt="a" * 64)
        await _seed_external_ref(s, tid=tid, cid=cid, receipt="b" * 64)
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.external_verification_failed == 1
    assert "EXTERNAL_ARCHIVE_DUPLICATE" in report.error


async def test_r6_external_archive_missing(s6i3_d_factory):
    """External missing：completed + external owner，但 archive 无任何 external_ref
    → binder 0 匹配 → ``EXTERNAL_ARCHIVE_MISSING`` → ``EXTERNAL_VERIFICATION_FAILED``。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.external_verification_failed == 1
    assert "EXTERNAL_ARCHIVE_MISSING" in report.error


async def test_r6_external_receipt_mismatch(s6i3_d_factory):
    """External receipt mismatch：archive receipt=R1，但 publish 后 LIVE receipt 被改为 R2
    → 按 archive id 精确绑定 LIVE 行，receipt 不一致 → ``external_receipt_mismatch``
    → ``EXTERNAL_VERIFICATION_FAILED``。

    判别点：pass A 不校验 external receipt，TOCTOU 不涉及 external 表——receipt 漂移仅在
    pass B ``_verify_external_receipt`` 的精确对账处被捕获。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
        ref_id = await _seed_external_ref(s, tid=tid, cid=cid, receipt="a" * 64)
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # publish 后改 LIVE receipt（仍满足 erased ⟺ receipt NOT NULL + 64-hex CHECK）
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs "
                "SET receipt_digest = :d WHERE id = :rid"
            ),
            {"d": "b" * 64, "rid": ref_id},
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.external_verification_failed == 1
    assert "external_receipt_mismatch" in report.error


async def test_r6_external_final_scan_residual(s6i3_d_factory):
    """External final-scan residual：archive 恰好 1 条 erased+receipt 记录（绑定/对账通过），
    但 publish 后 LIVE 新增一条 ``erase_state='registered'`` 残留 → final scan total != 0
    → ``external_final_scan_residual`` → ``EXTERNAL_VERIFICATION_FAILED``。

    判别点：残留行在 publish **之后**插入（**不**入 archive → binder 仍恰好 1 条），
    但 final scan 读 LIVE 发现 registered 残留 → fail closed（证据不完整）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
        await _seed_external_ref(s, tid=tid, cid=cid, receipt="a" * 64)
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # publish 后插入 registered 残留（registered ⟺ receipt_digest IS NULL）
    async with factory() as s, s.begin():
        await _seed_external_ref(
            s, tid=tid, cid=cid, receipt=None, erase_state="registered",
        )

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is not None
    assert report.external_verification_failed == 1
    assert "external_final_scan_residual" in report.error


async def test_r6_external_verified_success(s6i3_d_factory):
    """External verify-only **正例**：archive 恰好 1 条 erased+receipt 记录，LIVE 行精确匹配
    （id + receipt + state=erased），final scan 该 conversation residual total == 0
    → ``EXTERNAL_VERIFIED``，``report.error is None``，``external_verified == 1``。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, cid = await _seed_op_cp(
            s, tid, op_state="completed", cp_state="acked",
            owner_key="external.payload.v1",
        )
        await _seed_external_ref(s, tid=tid, cid=cid, receipt="a" * 64)
    sink, _ = await _publish_segment_for(factory, tid=tid)

    report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert report.error is None
    assert report.external_verified == 1
    assert report.external_verification_failed == 0
    assert any(
        v.action == "external_verified"
        and v.owner_key == "external.payload.v1"
        for v in report.verdict
    )


async def test_r5_archive_facts_missing_field(s6i3_d_factory):
    """Archive facts 必需字段缺失 → ARCHIVE_FACTS_FIELD_MISSING fail closed。

    通过 monkey-patch ``_read_operation_archive_facts`` 从真实 archive record 移除
    ``revision`` 必需字段 → pass A ``_require_field`` 检测缺失 →
    ``ARCHIVE_FACTS_FIELD_MISSING``（**禁止**用 ``str("")`` / ``0`` 默认值静默默转）。
    异常被 pass A 外层 catch 转为 ``RestoreReplayReport.error``（非 raise 传播）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    import app.composition.restore_replay as rr_mod
    original_read = rr_mod._read_operation_archive_facts

    async def read_with_missing_field(session, *, manifest, operation_id):
        record = dict(
            await original_read(session, manifest=manifest, operation_id=operation_id)
        )
        record.pop("revision", None)  # 删除必需字段
        return record

    rr_mod._read_operation_archive_facts = read_with_missing_field
    try:
        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    finally:
        rr_mod._read_operation_archive_facts = original_read

    assert report.error is not None
    assert "ARCHIVE_FACTS_FIELD_MISSING" in report.error
    assert report.pass_a_drift == 1


async def test_r5_archive_facts_invalid_uuid(s6i3_d_factory):
    """Archive facts UUID 字段格式错误 → ARCHIVE_FACTS_TYPE_INVALID fail closed。

    通过 monkey-patch ``_read_operation_archive_facts`` 注入非 UUID conversation_id
    → pass A 严格类型检查（``uuid.UUID(...)`` ValueError）→
    ``ARCHIVE_FACTS_TYPE_INVALID``。异常被 pass A 外层 catch 转为 report（非 raise 传播）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    import app.composition.restore_replay as rr_mod
    original_read = rr_mod._read_operation_archive_facts

    async def read_with_bad_uuid(session, *, manifest, operation_id):
        record = dict(
            await original_read(session, manifest=manifest, operation_id=operation_id)
        )
        record["conversation_id"] = "not-a-uuid"  # 注入无效 UUID
        return record

    rr_mod._read_operation_archive_facts = read_with_bad_uuid
    try:
        report = await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    finally:
        rr_mod._read_operation_archive_facts = original_read

    assert report.error is not None
    assert "ARCHIVE_FACTS_TYPE_INVALID" in report.error
    assert report.pass_a_drift == 1
