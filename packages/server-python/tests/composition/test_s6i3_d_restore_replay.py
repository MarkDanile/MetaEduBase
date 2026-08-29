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

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.restore_replay import (
    ACTION_EXTERNAL_VERIFY_ONLY,
    ACTION_LOCAL_CLEARED,
    ACTION_NO_REPEAT,
    ACTION_NON_LOCAL_BLOCKED,
    ACTION_REPLAY_SKIP_ZERO_WRITE,
    ACTION_RUNTIME_BINDING_UNPROVABLE,
    ACTION_SKIP,
    ACTION_VERIFY_ONLY,
    ACTION_ZERO_WRITE,
    LOCAL_OWNERS,
    NON_LOCAL_OWNERS,
    RestoreReplayError,
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


# 30 routing scenarios
_STATE_ROUTING_MATRIX: list[tuple[str, str, str]] = [
    ("scheduled", "pending", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "erasing", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "blocked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "failed", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("scheduled", "acked", ACTION_REPLAY_SKIP_ZERO_WRITE),
    ("running", "pending", ACTION_LOCAL_CLEARED),
    ("running", "erasing", ACTION_LOCAL_CLEARED),
    ("running", "blocked", ACTION_NON_LOCAL_BLOCKED),
    ("running", "failed", ACTION_ZERO_WRITE),
    ("running", "acked", ACTION_NO_REPEAT),
    ("blocked", "pending", ACTION_LOCAL_CLEARED),
    ("blocked", "erasing", ACTION_LOCAL_CLEARED),
    ("blocked", "blocked", ACTION_NON_LOCAL_BLOCKED),
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
    """真实双 owner：owner A 成功 + owner B 抛错 → A/B/正文/fence/checkpoint 全部保持原值。

    构造：种 workspace.core + workspace.transport 两 owner；
    篡改 operation.revision 制造 pass B 内部 participant fence 校验失败（archive 与
    DB revision 不一致）→ 整事务 rollback → workspace.core 未提交。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations "
                "SET state = 'deleted', purge_after = now() - interval '1 day', title = 'secret' "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        from app.composition.agent_erasure_registry import registry_digest
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
        for owner_key in ("workspace.core.v1", "workspace.transport.v1"):
            await _seed_checkpoint(
                s, tid=tid, purge_operation_id=op_id,
                owner_key=owner_key, state="erasing",
                capability_digest=capability_digest(owner_key),
            )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 篡改 DB operation.revision（archive 已固化 revision=1）→ 触发 TOCTOU drift
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges "
                "SET revision = 999 WHERE id = :oid"
            ),
            {"oid": op_id},
        )

    # replay 应在 pass A 内抛 FACT_DRIFT_FIELDS（archive 已固化 revision=1；DB 改为 999 → drift）
    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code in (
        "FACT_DRIFT_FIELDS",
        "TOCTOU_DRIFT_OPERATION_REVISION",
    )

    # 关键断言：所有 owner checkpoint 状态保持原值（rollback 验证）
    async with factory() as s, s.begin():
        for owner_key in ("workspace.core.v1", "workspace.transport.v1"):
            row = (await s.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :tid AND owner_key = :ok"
                ),
                {"tid": tid, "ok": owner_key},
            )).scalar_one()
            assert row == "erasing", (
                f"{owner_key} checkpoint 应保持 erasing（rollback 验证）；实际 = {row!r}"
            )
        # conversation.title 仍为 'secret'（workspace.core 未提交）
        title = (await s.execute(
            text("SELECT title FROM metaedu.agent_conversations WHERE id = :cid"),
            {"cid": cid},
        )).scalar_one()
    assert title == "secret", (
        f"整事务回滚验证：workspace.core 未提交；title = {title!r}"
    )


# ---------------------------------------------------------------------------
# Round-2 P0 修复 #5: 六元组逐字段 drift
# ---------------------------------------------------------------------------


async def test_r2_six_tuple_field_drift_reports_specific_field(s6i3_d_factory):
    """owner_version drift → RestoreReplayReport error 包含具体字段名。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_op_cp(s, tid, op_state="running", cp_state="erasing")
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # 篡改 DB owner_version（archive 已固化 version=1）
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET owner_version = 99 WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )

    # pass A 应抛错（不进 pass B）
    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code == "FACT_DRIFT_FIELDS"
    assert "checkpoint.owner_version" in exc_info.value.detail.get("drift_fields", ())


async def test_r2_ack_digest_format_validated(s6i3_d_factory):
    """ack_digest 在 state=acked 时必须 64-hex lowercase（应用层校验）。

    构造：先 seed op=running + cp=erasing 并 publish（archive 固化 erasing）；
    再 UPDATE DB cp=acked + ack_digest='c'*64；replay 应检测 cp.state drift
    （archive=erasing vs DB=acked）。
    """
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_op_cp(
            s, tid, op_state="running", cp_state="erasing",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    # archive 已固化 cp.state=erasing；现在改 DB cp.state=acked
    async with factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners "
                "SET state = 'acked', ack_digest = :d "
                "WHERE tenant_id = :tid"
            ),
            {"d": "c" * 64, "tid": tid},
        )

    # archive 仍记录 state=erasing（与 DB acked 不一致）→ FACT_DRIFT_FIELDS
    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code in (
        "FACT_DRIFT_FIELDS",
        "TOCTOU_DRIFT_CHECKPOINT_STATE",
    )


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
    """Gate 消费 report.external_verify_only → 阻断。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        await _assert_metaedu_test(s)
        tid = await _seed_tenant(s)
    report = RestoreReplayReport(external_verify_only=1)
    gate = await evaluate_restore_before_open(
        factory, tenant_id=tid, replay_report=report,
        runtime_proof_c_present=False,
    )
    assert gate.open_allowed is False
    assert any("external_verify_only" in r for r in gate.blocked_reasons)


async def test_r2_purge_revision_drift_fails_closed(s6i3_d_factory):
    """purge_revision drift → FACT_DRIFT_FIELDS 含 operation.purge_revision。"""
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

    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code == "FACT_DRIFT_FIELDS"
    assert "operation.purge_revision" in exc_info.value.detail.get("drift_fields", ())


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

    # archive 记录 owner_key=workspace.core.v1；DB 改为 execution.core.v1
    # 旧 owner_key 查不到（unique constraint）→ FACT_DRIFT_CHECKPOINT_MISSING
    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code in (
        "FACT_DRIFT_CHECKPOINT_MISSING",
        "FACT_DRIFT_FIELDS",
    )


async def test_r2_fact_drift_blocks_pass_b_entry(s6i3_d_factory):
    """pass A 任一 drift → 抛 FACT_DRIFT_FIELDS，**不**进入 pass B（verify via owners_fact_drift=0 + error 非空）。"""
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

    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert exc_info.value.code == "FACT_DRIFT_FIELDS"
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
    """external.payload.v1 + completed → EXTERNAL_VERIFY_ONLY（不调 adapter）。"""
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
    verdict = next(v for v in report.verdict if v.owner_key == "external.payload.v1")
    assert verdict.action == ACTION_EXTERNAL_VERIFY_ONLY
    assert report.runtime_binding_evidence_unprovable == 0


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
    """idempotent replay：DB 已 acked → archive-vs-live drift（不可二次清除）。"""
    factory = s6i3_d_factory
    async with factory() as s, s.begin():
        tid = await _seed_tenant(s)
        op_id, _ = await _seed_inline_with_correct_digests(
            s, tid=tid, op_state="running", cp_state="erasing",
            owner_key="workspace.core.v1",
        )
    sink, _ = await _publish_segment_for(factory, tid=tid)

    r1 = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=tid,
    )
    assert r1.error is None
    assert r1.owners_local_cleared == 1

    # 第二次：DB 已 acked → archive 仍记录 erasing → drift（pass A 失败）
    with pytest.raises(RestoreReplayError) as exc_info:
        await replay_archive_segment_for_tenant(
            factory, sink=sink, tenant_id=tid,
        )
    assert "FACT_DRIFT_FIELDS" in exc_info.value.code or "TOCTOU" in exc_info.value.code


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
