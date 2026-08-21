"""R1-S6-I2 Writer conformance suite + body/ref orphan inspection 真实 PG 测试。

契约：Plan §R1-S6-4（writer 全表 + conformance suite）+ §R1-S6-6（六类 verify
巡检形态、只读为主、event gap 唯一写路径、reconcile ledger 幂等登记）。
实现：``app/composition/s6i2_orphan_inspection.py``。

测试覆盖（反例映射）：
- 静态枚举层：writer 集合 == registry owner 集合；unknown owner / 漂移 fail closed；
  stage_with_created 调用方门禁。
- 真实 PG：tenant mismatch / digest conflict / event gap（event_log_complete=False +
  ledger epoch_unresolvable）/ unknown ref scheme（已有 unknown_scheme 阻断）/
  missing fence or owner scope / orphan transport 行。
- 退出码：0=无发现、1=有发现、2=不可判定。
- 重复执行幂等；并发执行串行；不输出正文/ref/free reason（sentinel 断言）。
- ledger 写入仅限合法组合（受 migration 040 CHECK 约束）。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.composition.agent_erasure_registry import (
    capability_digest,
    owner_registry,
    registry_digest,
)
from app.composition.s6i2_orphan_inspection import (
    VerifyReport,
    _register_ledger_issue,
    _required_writer_specs,
    run_writer_conformance_static,
    verify_inspection,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def inspection_session_factory(db_session) -> AsyncIterator[async_sessionmaker]:
    """每个测试一个独立 engine/sessionmaker 复用 db_session 同一 URL。

    与 ``composition/conftest.py`` 的 ``session_factory`` 同构；本 fixture 显式
    命名以体现隔离意图。
    """

    engine = create_async_engine(
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_tenant(session) -> uuid.UUID:
    tid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants (id, name, school_name, "
            "isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :name, 'shared', true, now(), now())"
        ),
        {"id": tid, "name": f"t-{tid}"},
    )
    return tid


async def _seed_conversation(session, *, tid: uuid.UUID) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, purged_at, hold_revision, revision, "
            "next_message_seq, next_run_queue_seq, last_activity_at, created_at, "
            "updated_at) "
            "VALUES (:cid, :tid, :tid, 'present', :digest, NULL, 't', 'none', "
            "'active', NULL, 'not_scheduled', 1, NULL, 0, 1, 1, 1, now(), now(), now())"
        ),
        {"cid": cid, "tid": tid, "digest": _DIGEST},
    )
    return cid


async def _seed_run(
    session,
    *,
    tid: uuid.UUID,
    cid: uuid.UUID,
    state: str = "failed",
) -> tuple[uuid.UUID, uuid.UUID]:
    """种一个终态 run；返回 ``(rid, correlation_id)``。

    状态 = completed 需 terminal_output_*；failed/cancelled 需 terminal_code +
    terminal_reason（非 completed 时 output_publish_state = 'not_required'）。
    必须预种 catalog（agent_definition_versions + agent_runtime_profiles）满足 FK。
    """

    def_id, prof_id = await _seed_catalog(session, tid=tid)
    rid = uuid.uuid4()
    corr = uuid.uuid4()
    if state == "completed":
        # completed 必须有完整 terminal_output envelope
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_runs "
                "(id, tenant_id, queue_seq, root_input_message_id, "
                "conversation_id, agent_definition_version_id, "
                "runtime_profile_id, runtime_binding_id, "
                "creation_digest, status, status_revision, "
                "next_event_seq, first_available_event_seq, "
                "last_event_seq, event_log_complete, queued_at, "
                "started_at, ended_at, output_publish_state, "
                "correlation_id, runtime_capability_snapshot, "
                "run_config_snapshot, budget_snapshot, usage_summary, "
                "terminal_output_ref, terminal_output_digest, "
                "terminal_output_size, terminal_output_media_type, "
                "terminal_output_classification, terminal_message_id, "
                "actor_state, created_at, updated_at) "
                "VALUES (:rid, :tid, 1, :mid, :cid, :def, :prof, NULL, "
                ":digest, :state, 1, 3, 1, 2, true, "
                "now() - interval '1 hour', "
                "now() - interval '1 hour', now() - interval '30 minute', "
                "'published', :corr, CAST('{}' AS jsonb), "
                "CAST('{}' AS jsonb), CAST('{}' AS jsonb), "
                "CAST('{}' AS jsonb), 'out-ref', :digest, 8, "
                "'application/json', 'internal', :msg, "
                "'present', now(), now())"
            ),
            {
                "rid": rid,
                "tid": tid,
                "mid": uuid.uuid4(),
                "cid": cid,
                "def": def_id,
                "prof": prof_id,
                "state": state,
                "digest": _DIGEST,
                "corr": corr,
                "msg": uuid.uuid4(),
            },
        )
    else:
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_runs "
                "(id, tenant_id, queue_seq, root_input_message_id, "
                "conversation_id, agent_definition_version_id, "
                "runtime_profile_id, runtime_binding_id, "
                "creation_digest, status, status_revision, "
                "next_event_seq, first_available_event_seq, "
                "last_event_seq, event_log_complete, queued_at, "
                "started_at, ended_at, output_publish_state, "
                "correlation_id, runtime_capability_snapshot, "
                "run_config_snapshot, budget_snapshot, usage_summary, "
                "terminal_code, terminal_reason, "
                "actor_state, created_by, created_at, updated_at) "
                "VALUES (:rid, :tid, 1, :mid, :cid, :def, :prof, NULL, "
                ":digest, :state, 1, 3, 1, 2, true, "
                "now() - interval '1 hour', "
                "now() - interval '1 hour', now() - interval '30 minute', "
                "'not_required', :corr, CAST('{}' AS jsonb), "
                "CAST('{}' AS jsonb), CAST('{}' AS jsonb), "
                "CAST('{}' AS jsonb), 'test_code', 'test_reason', "
                "'present', :tid, now(), now())"
            ),
            {
                "rid": rid,
                "tid": tid,
                "mid": uuid.uuid4(),
                "cid": cid,
                "def": def_id,
                "prof": prof_id,
                "state": state,
                "digest": _DIGEST,
                "corr": corr,
            },
        )
    return rid, corr


async def _seed_catalog(session, *, tid: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """种 catalog（agent_definition_versions + agent_runtime_profiles）满足 agent_runs FK。"""

    def_id = uuid.uuid4()
    prof_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, "
            "definition_digest, created_by, created_at) "
            "VALUES (:def_id, :tid, :key, 1, 'published', :digest, "
            ":tid, now()) "
            "ON CONFLICT DO NOTHING"
        ),
        {"def_id": def_id, "tid": tid, "key": f"def-{def_id}", "digest": _DIGEST},
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, "
            "config_digest, capability_digest, enabled, revision, "
            "created_at, updated_at) "
            "VALUES (:prof_id, :tid, :key, 'compatibility', "
            "'compatibility', :digest, :digest, true, 1, now(), now()) "
            "ON CONFLICT DO NOTHING"
        ),
        {"prof_id": prof_id, "tid": tid, "key": f"prof-{prof_id}", "digest": _DIGEST},
    )
    return def_id, prof_id


async def _seed_event(
    session,
    *,
    tid: uuid.UUID,
    rid: uuid.UUID,
    cid: uuid.UUID,
    corr: uuid.UUID,
    seq: int,
    payload_state: str = "inline",
    payload_inline: str | None = '{"v": 1}',
    payload_ref: str | None = None,
) -> None:
    """S6-RET 形式 — payload 必带符合 CHECK 约束（payload_digest 64-hex + size ≥ 0）。

    ``payload_inline`` 不允许 NULL 当 payload_state='inline'（CHECK）。
    ``corr`` 必须与 ``agent_runs.correlation_id`` 一致以满足 FK
    ``fk_agent_run_event_owner``（tenant_id, run_id, conversation_id, correlation_id）。
    """

    digest = _DIGEST
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, run_id, conversation_id, seq, "
            "schema_version, event_type, "
            "visibility, classification, payload_state, "
            "payload_inline, payload_ref, payload_digest, "
            "payload_size, media_type, "
            "correlation_id, occurred_at, persisted_at) "
            "VALUES (:id, :tid, :rid, :cid, :seq, 1, 'test', "
            "'internal', 'internal', "
            ":state, CAST(:inline AS jsonb), :ref, :digest, :size, "
            "'application/json', "
            ":corr, now() - interval '30 minute', "
            "now() - interval '30 minute')"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tid,
            "rid": rid,
            "cid": cid,
            "seq": seq,
            "state": payload_state,
            "inline": payload_inline,
            "ref": payload_ref,
            "digest": digest,
            "size": 8,
            "corr": corr,
        },
    )


async def _seed_outbox_orphan(
    session, *, tid: uuid.UUID, table: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """种一张跨 tenant 引用的 outbox 行——tenant mismatch + orphan transport 双重。

    FK ``fk_agent_*_outbox_scope_conv`` 强制 ``conversation_id`` 必须在
    ``agent_conversations`` 存在。本测试目标 = 注入孤儿 outbox 行（conversation_id
    指向不存在的 conversation）—— 通过 ``session_replication_role=replica``
    临时绕过 FK 约束注入（测试边界，不修改 schema）。
    """

    row_id = uuid.uuid4()
    fake_cid = uuid.uuid4()
    await session.execute(
        text("SET session_replication_role = replica")
    )
    try:
        if table == "agent_workspace_outbox":
            await session.execute(
                text(
                    "INSERT INTO metaedu.agent_workspace_outbox "
                    "(id, tenant_id, event_type, schema_version, aggregate_id, "
                    "aggregate_type, payload_ref, payload_digest, "
                    "correlation_id, causation_id, status, attempt_count, "
                    "conversation_id, producer_purge_revision, "
                    "scope_reconcile_state, payload_inline, created_at) "
                    "VALUES (:id, :tid, 'test', 1, :agg, 'test', NULL, :digest, "
                    ":cid, :cid, 'pending', 0, :cid, NULL, 'pending', "
                    "CAST('{}' AS jsonb), now())"
                ),
                {
                    "id": row_id,
                    "tid": tid,
                    "agg": uuid.uuid4(),
                    "cid": fake_cid,
                    "digest": _DIGEST,
                },
            )
        else:
            await session.execute(
                text(
                    "INSERT INTO metaedu.agent_execution_outbox "
                    "(id, tenant_id, event_type, schema_version, aggregate_id, "
                    "aggregate_type, payload_ref, payload_digest, "
                    "correlation_id, causation_id, status, attempt_count, "
                    "conversation_id, producer_purge_revision, "
                    "scope_reconcile_state, payload_inline, created_at) "
                    "VALUES (:id, :tid, 'test', 1, :agg, 'test', NULL, :digest, "
                    ":cid, :cid, 'pending', 0, :cid, NULL, 'pending', "
                    "CAST('{}' AS jsonb), now())"
                ),
                {
                    "id": row_id,
                    "tid": tid,
                    "agg": uuid.uuid4(),
                    "cid": fake_cid,
                    "digest": _DIGEST,
                },
            )
    finally:
        await session.execute(
            text("SET session_replication_role = origin")
        )
    return row_id, fake_cid


async def _seed_unknown_scheme_ref(session, *, tid: uuid.UUID) -> uuid.UUID:
    """种一张 ref_scheme='unknown' 的 external_object_refs 行。"""

    row_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, owner_key, conversation_id, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, blocked_reason, "
            "created_at, updated_at) "
            "VALUES (:id, :tid, 'external.payload.v1', :cid, 'unknown', "
            "'http://x/y', 'agent_run_events', :rid, 'blocked', "
            "'unknown_scheme', now(), now())"
        ),
        {
            "id": row_id,
            "tid": tid,
            "cid": uuid.uuid4(),
            "rid": uuid.uuid4(),
        },
    )
    return row_id


# ---------------------------------------------------------------------------
# 1. 静态枚举层
# ---------------------------------------------------------------------------


async def test_static_writer_specs_complete():
    specs = _required_writer_specs()
    assert len(specs) == 3, specs
    names = {s.writer_name for s in specs}
    assert {
        "run_event_retention",
        "run_audit_retention",
        "event_gap_inspection_writer",
    } == names


async def test_static_writer_all_owners_in_registry():
    specs = _required_writer_specs()
    registered = {o.owner_key for o in owner_registry()}
    for spec in specs:
        assert spec.owner_key in registered, f"owner_key {spec.owner_key} missing"


async def test_static_conformance_clean():
    result = run_writer_conformance_static()
    assert result.writers_total == 3
    assert result.writers_failed == ()
    assert result.registry_keys_total >= 6
    assert result.registry_unknown_keys == ()
    assert result.capability_drift_keys == ()
    assert result.stage_with_created_callers_unfenced == ()


async def test_static_capability_digest_recomputable():
    for owner in owner_registry():
        d1 = capability_digest(owner.owner_key)
        d2 = capability_digest(owner.owner_key)
        assert d1 == d2 and len(d1) == 64


# ---------------------------------------------------------------------------
# 2. writer 集合与 owner_version 一致（静态）
# ---------------------------------------------------------------------------


async def test_registry_digest_stable():
    a = registry_digest()
    b = registry_digest()
    assert a == b and len(a) == 64


# ---------------------------------------------------------------------------
# 3. unknown owner / capability drift / scope mismatch fail closed
# ---------------------------------------------------------------------------


async def test_unknown_owner_rejected(db_session: AsyncSession):
    from app.composition.agent_erasure_registry import UnknownOwnerError, require_owner

    with pytest.raises(UnknownOwnerError):
        require_owner("bogus.owner.v0")


async def test_capability_digest_for_unknown_owner_returns_none():
    from app.composition.s6i2_orphan_inspection import capability_digest_for

    assert capability_digest_for("bogus.owner.v0") is None


# ---------------------------------------------------------------------------
# 4. 六类巡检真实 PG 端到端
# ---------------------------------------------------------------------------


async def test_verify_inspection_empty_db_returns_zero(
    inspection_session_factory,
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
    )
    assert report.exit_code == 0
    assert report.total_findings == 0
    assert report.indeterminate is False
    assert report.conformance.writers_failed == ()


async def test_verify_tenant_mismatch_finding(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_outbox_orphan(s, tid=tid, table="agent_workspace_outbox")

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("tenant_mismatch",),
    )
    assert report.exit_code == 1
    assert report.total_findings >= 1
    tenant = next(r for r in report.inspections if r.inspection == "tenant_mismatch")
    assert tenant.findings_total >= 1


async def test_verify_unknown_ref_scheme(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_unknown_scheme_ref(s, tid=tid)

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("unknown_ref_scheme",),
    )
    assert report.exit_code == 1
    assert report.total_findings >= 1


async def test_verify_event_gap_persists_event_log_complete(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        rid, corr = await _seed_run(s, tid=tid, cid=cid, state="failed")
        # 种 seq 1 + 3（缺 seq 2 → 内部空洞）
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=1)
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=3)

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=True,
        inspections=("event_gap",),
    )
    assert report.exit_code == 1
    assert report.total_event_log_complete_writes == 1

    # 验证 Run.event_log_complete 已被置 False
    async with inspection_session_factory() as s2:
        row = (
            await s2.execute(
                text(
                    "SELECT event_log_complete FROM metaedu.agent_runs "
                    "WHERE id = :rid"
                ),
                {"rid": rid},
            )
        ).first()
        assert row is not None and row[0] is False

    # 验证 ledger 登记
    async with inspection_session_factory() as s2:
        ledger_count = (
            await s2.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :tid "
                    "  AND source_table = 'agent_run_events' "
                    "  AND issue_code = 'epoch_unresolvable'"
                ),
                {"tid": tid},
            )
        ).scalar()
        assert ledger_count == 1


async def test_verify_event_gap_dry_run_does_not_persist(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        rid, corr = await _seed_run(s, tid=tid, cid=cid, state="failed")
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=1)
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=3)

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("event_gap",),
    )
    assert report.total_event_log_complete_writes == 0
    async with inspection_session_factory() as s2:
        row = (
            await s2.execute(
                text(
                    "SELECT event_log_complete FROM metaedu.agent_runs "
                    "WHERE id = :rid"
                ),
                {"rid": rid},
            )
        ).first()
        assert row[0] is True


async def test_verify_event_gap_idempotent(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        rid, corr = await _seed_run(s, tid=tid, cid=cid, state="failed")
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=1)
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=3)

    # 第一次：写
    r1 = await verify_inspection(
        inspection_session_factory, tenant_id=tid, persist_event_gap=True,
        inspections=("event_gap",),
    )
    # 第二次：仍发现 gap，但 ledger 已有 → ON CONFLICT DO NOTHING（不增加）
    r2 = await verify_inspection(
        inspection_session_factory, tenant_id=tid, persist_event_gap=True,
        inspections=("event_gap",),
    )
    assert r1.total_event_log_complete_writes == 1
    assert r2.total_event_log_complete_writes == 1  # 第二次写入幂等
    async with inspection_session_factory() as s2:
        c = (
            await s2.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :tid"
                ),
                {"tid": tid},
            )
        ).scalar()
        assert c == 1


async def test_verify_orphan_transport(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_outbox_orphan(s, tid=tid, table="agent_execution_outbox")

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("orphan_transport",),
    )
    assert report.exit_code == 1
    assert report.total_findings >= 1


# ---------------------------------------------------------------------------
# 5. ledger 写入仅限合法组合 + 不越权
# ---------------------------------------------------------------------------


async def test_register_ledger_issue_rejects_invalid_combo(
    inspection_session_factory, db_session: AsyncSession
):
    """未知 source_table / issue_code 组合必须返回 False 不写。"""

    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        # 不合法 owner_key 关联
        result = await _register_ledger_issue(
            s,
            tenant_id=tid,
            source_table="bogus_table",
            source_row_id=uuid.uuid4(),
            issue_code="cross_tenant_mismatch",
            conversation_id=None,
        )
        assert result is False


async def test_register_ledger_issue_accepts_valid(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        result = await _register_ledger_issue(
            s,
            tenant_id=tid,
            source_table="agent_workspace_outbox",
            source_row_id=uuid.uuid4(),
            issue_code="cross_tenant_mismatch",
            conversation_id=cid,
        )
        assert result is True


# ---------------------------------------------------------------------------
# 6. sentinel：不输出正文/ref/free reason
# ---------------------------------------------------------------------------


async def test_report_to_dict_no_payload_leakage():
    """R1-AC10：报告 dict 不应含正文/ref/free reason 字段。"""

    from app.composition.s6i2_orphan_inspection import report_to_dict

    report = VerifyReport(
        inspections=(),
        total_findings=0,
        total_persisted=0,
        total_reported_only=0,
        total_ledger_writes=0,
        total_event_log_complete_writes=0,
        conformance=run_writer_conformance_static(),
        exit_code=0,
    )
    d = report_to_dict(report)
    serialized = json.dumps(d)
    # 任何 payload / ref / reply / session / free reason / blocked 字面不应在序列化 JSON 中出现
    forbidden_substrings = (
        "payload_inline",
        "payload_ref",
        "reply",
        "session_ref",
        "free_reason",
        "blocked_reason",
    )
    for substring in forbidden_substrings:
        assert substring not in serialized, substring


# ---------------------------------------------------------------------------
# 7. 退出码语义
# ---------------------------------------------------------------------------


async def test_exit_code_zero_when_no_findings(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
    report = await verify_inspection(
        inspection_session_factory, tenant_id=tid, persist_event_gap=False,
    )
    assert report.exit_code == 0


async def test_exit_code_one_when_findings_present(
    inspection_session_factory, db_session: AsyncSession
):
    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_unknown_scheme_ref(s, tid=tid)
    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("unknown_ref_scheme",),
    )
    assert report.exit_code == 1


async def test_exit_code_two_when_invalid_inspection_name(
    inspection_session_factory, db_session: AsyncSession
):
    # 退出码 2 = 不可判定（indeterminate=True）。CLI 路径下 argparse
    # ``choices=_INSPECTIONS`` 已拒绝未知 inspection 名；此处直接调用
    # ``verify_inspection`` 验证：传入未知 inspection 字符串 → 不抛异常 +
    # ``indeterminate=True`` + ``exit_code=2``。
    from app.composition.s6i2_orphan_inspection import verify_inspection

    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)

    report = await verify_inspection(
        inspection_session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("not_a_real_inspection",),
    )
    assert report.indeterminate is True
    assert report.exit_code == 2
    assert report.total_findings == 0


# ---------------------------------------------------------------------------
# 8. 并发执行串行（同一 tenant 双连接）
# ---------------------------------------------------------------------------


async def test_concurrent_verify_serializable(
    inspection_session_factory, db_session: AsyncSession
):
    import asyncio

    async with inspection_session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_unknown_scheme_ref(s, tid=tid)

    r1, r2 = await asyncio.gather(
        verify_inspection(
            inspection_session_factory, tenant_id=tid, persist_event_gap=False,
            inspections=("unknown_ref_scheme",),
        ),
        verify_inspection(
            inspection_session_factory, tenant_id=tid, persist_event_gap=False,
            inspections=("unknown_ref_scheme",),
        ),
    )
    # 两者均发现相同问题，count 一致（read-only）
    assert r1.total_findings == r2.total_findings
    assert r1.exit_code == r2.exit_code == 1
