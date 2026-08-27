# ruff: noqa: E501
"""R1-S6-I3-D D1a: ledger snapshot codec 真实 PG 验收。

契约：Plan §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 + §17.5 用户裁决
（runtime per-binding proof 路径 = c）+ 用户指定 D1a only。

D1a 边界（严格）：
- 只读：所有 DB 操作在 REPEATABLE READ + READ ONLY 事务中
- export_ledger_segment → 字节级 deterministic canonical bytes
- decode_ledger_segment → 严格解析 + 9 类 fail closed
- reconstruct_owner_facts → 纯内存六元组重构
- 严禁调用 adapter / 严禁 replay side effect / 严禁 DB mutation

真实 PG 测试覆盖：
- 4 类 record round-trip + decode + reconstruct
- tenant 隔离（不同 tenant 数据不交叉）
- 确定性 bytes（同一 state 多次 export 字节相同）
- 空 tenant（无 record 时 export + decode 仍合法）
- manifest digest / count 一致性
- schema version mismatch → fail closed
- kind/table identity mismatch → fail closed
- digest tamper → fail closed
- duplicate stable identity → fail closed
- external `ref_value` 不泄露
- transaction 全程零写（只读）
- runtime per-binding proof unavailable 显式判定（用户裁决 c）

数据库硬边界：
- 仅使用 ``metaedu_test``；执行前打印并断言 ``current_database()='metaedu_test'``
- 禁止 drop / truncate / reseed / 重建 ``metaedu``
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.s6i3_ledger_snapshot import (
    SCHEMA_VERSION,
    LedgerSnapshotError,
    decode_ledger_segment,
    export_ledger_segment,
    export_ledger_segment_to_bytes,
    reconstruct_owner_facts,
)
from tests.composition.s6i3_seeds import (
    _seed_checkpoint,
    _seed_conversation,
    _seed_operation,
    _seed_tenant,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64
_OTHER_DIGEST = "b" * 64
_TEST_DB_URL = "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"


@pytest.fixture
async def snapshot_factory():
    """独立 engine/sessionmaker，per-test fresh。"""
    engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _assert_metaedu_test(session: AsyncSession) -> None:
    """数据库硬边界：禁止在非 metaedu_test 库执行 destructive / read test。"""
    row = (await session.execute(text("SELECT current_database()"))).scalar_one()
    assert row == "metaedu_test", (
        f"DB hard boundary: current_database()={row!r} (expected 'metaedu_test'); aborting"
    )


async def _seed_workspace_ref(
    session: AsyncSession, *, tid: uuid.UUID, cid: uuid.UUID, ref_value: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """种 agent_workspace_outbox ref-bearing 行 + external ref ledger registered 行。

    返回 (ref_id, outbox_id)——outbox 是 source 行的真值。
    """
    outbox_id = uuid.uuid4()
    # uq_agent_ws_outbox_turn = (tenant_id, aggregate_id)：每次 seed 分配新 aggregate_id
    aggregate_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "created_at) "
            "VALUES (:id, :t, 'turn.requested.v1', 1, :aggr, 'conversation', "
            "NULL, :rv, :pd, :corr, 'pending', now())"
        ),
        {
            "id": outbox_id,
            "t": tid,
            "aggr": aggregate_id,
            "rv": ref_value,
            "pd": _DIGEST,
            "corr": str(uuid.uuid4()),
        },
    )
    ref_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, receipt_digest, blocked_reason) "
            "VALUES (:id, :t, :c, 'external.payload.v1', 'db_local', :rv, "
            "'agent_workspace_outbox', :sr, 'registered', NULL, NULL)"
        ),
        {
            "id": ref_id,
            "t": tid,
            "c": cid,
            "rv": ref_value,
            "sr": outbox_id,
        },
    )
    return ref_id, outbox_id


async def _seed_reconcile(
    session: AsyncSession,
    *,
    tid: uuid.UUID,
    cid: uuid.UUID,
    issue_code: str = "source_message_missing",
    reconcile_class: str = "tenant_scope",
    owner_key: str = "workspace.transport.v1",
) -> None:
    """种 agent_transport_scope_reconcile 一行（内联实现——s6i3_seeds.py 未提供此 helper）。

    约束（ck_agent_transport_reconcile_class_scope）：`reconcile_class != 'conversation_scope'` ⇒ `conversation_id IS NULL`。
    """
    # 显式：tenant_scope / orphan 必须 conversation_id IS NULL
    cid_value = cid if reconcile_class == "conversation_scope" else None
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_transport_scope_reconcile "
            "(id, tenant_id, owner_key, source_table, source_row_id, conversation_id, "
            "reconcile_class, issue_code, state, revision) "
            "VALUES (gen_random_uuid(), :t, :ok, 'agent_workspace_outbox', gen_random_uuid(), :cid, "
            ":rc, :ic, 'open', 1)"
        ),
        {
            "t": tid,
            "ok": owner_key,
            "cid": cid_value,
            "rc": reconcile_class,
            "ic": issue_code,
        },
    )


# --- helpers ---


async def _seed_minimal_ledger(
    session: AsyncSession,
    *,
    tenant_label: str = "t",
    n_operations: int = 1,
    n_checkpoints: int = 1,
    n_external_refs: int = 1,
    n_reconciles: int = 1,
    ref_value: str = "obj://staging/object/d1a",
) -> dict[str, uuid.UUID]:
    """种最小可解码 ledger（4 类各 ≥ 1 条）。"""
    tid = await _seed_tenant(session, name=tenant_label)
    cid = await _seed_conversation(session, tid=tid)
    op_ids: list[uuid.UUID] = []
    cp_ids: list[uuid.UUID] = []
    ref_ids: list[uuid.UUID] = []
    # uq_agent_purge_revision = (tenant_id, conversation_id, purge_revision)
    # 多个 operation 必须分配不同 purge_revision
    for i in range(n_operations):
        op_id = await _seed_operation(
            session,
            tid=tid,
            cid=cid,
            state="running",
            purge_rev=i + 1,
        )
        op_ids.append(op_id)
    for i in range(n_checkpoints):
        # uq_agent_purge_owner = (tenant_id, purge_operation_id, owner_key)
        # 多 checkpoint 必须分配不同 owner_key（轮转 owner 域）
        owner_keys = (
            "external.payload.v1",
            "runtime.private.v1",
            "workspace.core.v1",
            "execution.core.v1",
            "workspace.transport.v1",
            "execution.transport.v1",
        )
        owner_key = owner_keys[i % len(owner_keys)]
        cp_id = await _seed_checkpoint(
            session,
            tid=tid,
            purge_operation_id=op_ids[0] if op_ids else uuid.uuid4(),
            owner_key=owner_key,
            owner_version=1,
            capability_digest=_DIGEST,
            state="erasing",
            attempt=1,
        )
        cp_ids.append(cp_id)
    for _ in range(n_external_refs):
        ref_id, _ = await _seed_workspace_ref(
            session, tid=tid, cid=cid, ref_value=f"{ref_value}-{i}"
        )
        ref_ids.append(ref_id)
    for _ in range(n_reconciles):
        await _seed_reconcile(
            session,
            tid=tid,
            cid=cid,
            issue_code="source_message_missing",
            reconcile_class="tenant_scope",
            owner_key="workspace.transport.v1",
        )
    await session.commit()
    return {
        "tid": tid,
        "cid": cid,
        "op_ids": op_ids,
        "cp_ids": cp_ids,
        "ref_ids": ref_ids,
    }


# --- tests: round-trip + structural ---


async def test_d1a_round_trip_four_record_kinds(snapshot_factory):
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed)

    async with factory() as session:  # noqa: SIM117
        # REPEATABLE READ + READ ONLY 事务（按用户要求）
        async with session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            payload = await export_ledger_segment(session, tenant_id=ids["tid"])

    # 字节级 deterministic：同一 state 多次 decode 应得相同内容
    manifest1 = decode_ledger_segment(payload)
    manifest2 = decode_ledger_segment(payload)
    assert manifest1.schema_version == SCHEMA_VERSION
    assert manifest1.tenant_id == str(ids["tid"])
    assert manifest1.schema_version == manifest2.schema_version
    assert manifest1.tenant_id == manifest2.tenant_id
    # 4 类 record 都有 ≥ 1
    for kind, count in manifest1.record_count.items():
        assert count >= 1, f"record kind {kind} should have ≥ 1 row"
    assert len(manifest1.records["operation"]) == manifest1.record_count["operation"]
    assert len(manifest1.records["checkpoint"]) == manifest1.record_count["checkpoint"]
    assert len(manifest1.records["external_ref"]) == manifest1.record_count["external_ref"]
    assert len(manifest1.records["reconcile"]) == manifest1.record_count["reconcile"]
    # stable sort verify
    for kind, recs in manifest1.records.items():
        sids = [r.stable_identity for r in recs]
        assert sids == sorted(sids), f"{kind} records not stable-sorted"


async def test_d1a_deterministic_bytes(snapshot_factory):
    """同一 DB state 多次 export 必须字节相同（stable sort + canonical JSON）。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _seed_minimal_ledger(seed)

    payloads: list[bytes] = []
    for _ in range(3):
        async with factory() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            payloads.append(
                await export_ledger_segment(
                    session, tenant_id=await _first_tenant(session)
                )
            )
    assert payloads[0] == payloads[1] == payloads[2]


async def _first_tenant(session: AsyncSession) -> uuid.UUID:
    return (await session.execute(text("SELECT id FROM metaedu.tenants LIMIT 1"))).scalar_one()


async def test_d1a_tenant_isolation(snapshot_factory):
    """不同 tenant 数据严格隔离——export_a 不含 tenant_b 的 record。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _seed_minimal_ledger(seed, tenant_label="A")
        await _seed_minimal_ledger(seed, tenant_label="B")

    async with factory() as session:
        rows = (
            await session.execute(text("SELECT id, name FROM metaedu.tenants ORDER BY name"))
        ).mappings().all()
        # name = "A-<uuid>" / "B-<uuid>"
        tid_a = next(r["id"] for r in rows if str(r["id"]) in str(r["name"]) and r["name"].startswith("A-"))
        tid_b = next(r["id"] for r in rows if r["name"].startswith("B-"))

    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload_a = await export_ledger_segment(session, tenant_id=tid_a)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload_b = await export_ledger_segment(session, tenant_id=tid_b)
    m_a = decode_ledger_segment(payload_a)
    m_b = decode_ledger_segment(payload_b)
    assert m_a.tenant_id == str(tid_a)
    assert m_b.tenant_id == str(tid_b)
    # 所有 record 的 tenant_id 必须等于 declared tenant
    for kind, recs in m_a.records.items():
        for r in recs:
            assert r.fields.get("tenant_id") == str(tid_a), (
                f"tenant A payload leaked non-A record: {kind} {r.stable_identity}"
            )
    for _kind, recs in m_b.records.items():
        for r in recs:
            assert r.fields.get("tenant_id") == str(tid_b)


async def test_d1a_empty_tenant(snapshot_factory):
    """空 tenant：四类 record 均为 0，export + decode 仍合法。"""
    factory = snapshot_factory
    async with factory() as seed:
        tid = await _seed_tenant(seed, name="empty")
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=tid)
    m = decode_ledger_segment(payload)
    for kind in ("operation", "checkpoint", "external_ref", "reconcile"):
        assert m.record_count[kind] == 0
        assert m.records[kind] == ()
    # 确定性 bytes
    assert export_ledger_segment_to_bytes(m.raw) == payload


async def test_d1a_manifest_digest_and_count_consistency(snapshot_factory):
    """manifest 字段与 records 严格一致：count + content_digest。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(
            seed, n_operations=2, n_checkpoints=3, n_external_refs=2, n_reconciles=2
        )
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    m = decode_ledger_segment(payload)
    for kind in ("operation", "checkpoint", "external_ref", "reconcile"):
        assert m.record_count[kind] == len(m.records[kind])
        # content_digest 已通过 decoder 校验 → 隐式一致


# --- tests: decoder fail closed ---


async def test_d1a_schema_version_mismatch_fails(snapshot_factory):
    """schema version 未知 → SCHEMA_VERSION_UNKNOWN。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["schema_version"] = SCHEMA_VERSION + 1
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "SCHEMA_VERSION_UNKNOWN"


async def test_d1a_kind_table_mismatch_fails(snapshot_factory):
    """kind/table identity 失配 → KIND_TABLE_MISMATCH。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["records"]["operation"][0]["table_identity"] = "agent_external_object_refs"
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "KIND_TABLE_MISMATCH"


async def test_d1a_digest_tamper_fails(snapshot_factory):
    """content_digest 被篡改 → CONTENT_DIGEST_MISMATCH。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["records"]["operation"][0]["fields"]["state"] = "completed"  # tamper a field
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "CONTENT_DIGEST_MISMATCH"


async def test_d1a_duplicate_stable_identity_fails(snapshot_factory):
    """重复 stable_identity → DUPLICATE_STABLE_IDENTITY。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 复制一条 operation record（构造 stable_identity 冲突）
    dup = dict(env["records"]["operation"][0])
    env["records"]["operation"].append(dup)
    # count / digest 同步以隔离此 fail closed
    env["manifest"]["operation"]["count"] = len(env["records"]["operation"])
    from app.shared.schemas.canonical_json import canonical_digest as _cd
    env["manifest"]["operation"]["content_digest"] = _cd(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "operation",
            "records": [
                {
                    "stable_identity": r["stable_identity"],
                    "table_identity": r["table_identity"],
                    "fields": r["fields"],
                }
                for r in env["records"]["operation"]
            ],
        }
    )
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "DUPLICATE_STABLE_IDENTITY"


# --- tests: redacted fields ---


async def test_d1a_external_ref_value_not_exported(snapshot_factory):
    """external_ref 严禁输出 ref_value（spec §10 末段 + 用户裁决）。"""
    factory = snapshot_factory
    secret = "obj://staging/secret-must-not-leak/d1a"
    async with factory() as seed:
        await _seed_minimal_ledger(seed, ref_value=secret)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        tid = await _first_tenant(session)
        payload = await export_ledger_segment(session, tenant_id=tid)
    # 字符串全包搜索：secret 不应出现
    assert secret.encode("utf-8") not in payload, (
        f"external_ref secret leaked: {secret!r} found in export payload"
    )
    # decoder 进一步断言：external_ref 字段集合不含 ref_value
    m = decode_ledger_segment(payload)
    for r in m.records["external_ref"]:
        assert "ref_value" not in r.fields, (
            f"external_ref leaked ref_value in {r.stable_identity}"
        )


async def test_d1a_runtime_session_ref_not_exported(snapshot_factory):
    """runtime 严禁输出 runtime_session_ref（按用户裁决 c + spec §10 末段）。"""
    factory = snapshot_factory
    async with factory() as seed:
        tid = await _seed_tenant(seed, name="r")
        # 种一条 runtime profile + runtime binding（runtime_session_ref='secret-ref-d1a'）
        runtime_ref = "secret-ref-d1a-must-not-leak"
        profile_id = uuid.uuid4()
        await seed.execute(
            text(
                "INSERT INTO metaedu.agent_runtime_profiles "
                "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, capability_digest, enabled) "
                "VALUES (:p, :t, 'r', 'rt', 'ak', :cd, :cd, true)"
            ),
            {"p": profile_id, "t": tid, "cd": _DIGEST},
        )
        await seed.execute(
            text(
                "INSERT INTO metaedu.agent_runtime_session_bindings "
                "(tenant_id, conversation_id, runtime_profile_id, runtime_session_ref, status, current_epoch) "
                "VALUES (:t, :c, :p, :r, 'creating', 1)"
            ),
            {
                "t": tid,
                "c": uuid.uuid4(),
                "p": profile_id,
                "r": runtime_ref,
            },
        )
        await seed.commit()
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=tid)
    # 字符串搜索：runtime_ref 不应出现
    assert runtime_ref.encode("utf-8") not in payload
    # decoder 进一步断言：任何 record 字段集合不含 runtime_session_ref
    m = decode_ledger_segment(payload)
    for kind, recs in m.records.items():
        for r in recs:
            assert "runtime_session_ref" not in r.fields, (
                f"{kind} leaked runtime_session_ref in {r.stable_identity}"
            )


# --- tests: transaction zero-write ---


async def test_d1a_transaction_zero_write(snapshot_factory):
    """export 全程只读，事务提交后 row count 无变化。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)

    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        row_counts_before: dict[str, int] = {}
        for table in (
            "agent_conversation_purges",
            "agent_conversation_purge_owners",
            "agent_external_object_refs",
            "agent_transport_scope_reconcile",
        ):
            row_counts_before[table] = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} "  # noqa: S608
                        f"WHERE tenant_id = :t"
                    ),
                    {"t": str(ids["tid"])},
                )
            ).scalar_one()
        await export_ledger_segment(session, tenant_id=ids["tid"])
        # 事务内 row count 应仍为同一值
        for table, before in row_counts_before.items():
            after = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} "  # noqa: S608
                        f"WHERE tenant_id = :t"
                    ),
                    {"t": str(ids["tid"])},
                )
            ).scalar_one()
            assert after == before, f"row count changed in {table} during export"

    async with factory() as session:
        for table, before in row_counts_before.items():
            after = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} "  # noqa: S608
                        f"WHERE tenant_id = :t"
                    ),
                    {"t": str(ids["tid"])},
                )
            ).scalar_one()
            assert after == before, f"row count changed in {table} after export"


# --- tests: reconstruct ---


async def test_d1a_reconstruct_owner_facts_six_tuple(snapshot_factory):
    """reconstruct_owner_facts 返回 owner_key → OwnerFacts 六元组。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    m = decode_ledger_segment(payload)
    facts = reconstruct_owner_facts(m)
    assert "external.payload.v1" in facts
    f = facts["external.payload.v1"]
    assert f.owner_key == "external.payload.v1"
    assert f.owner_version == 1
    assert f.capability_digest == _DIGEST
    assert f.checkpoint_state == "erasing"
    assert f.has_operation is True
    assert f.purge_revision == 1
    # runtime per-binding proof unavailable 显式（用户裁决 c）
    assert f.runtime_per_binding_proof_available is False


# --- tests: runtime per-binding proof unavailable explicit ---


async def test_d1a_runtime_per_binding_proof_unavailable_explicit(snapshot_factory):
    """runtime per-binding proof unavailable 显式判定（用户裁决 c）。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=await _first_tenant(session))
    env = json.loads(payload)
    assert env["runtime_per_binding_proof_available"] is False
    m = decode_ledger_segment(payload)
    assert m.runtime_per_binding_proof_available is False


async def test_d1a_requires_transaction(snapshot_factory):
    """未在事务中调用 export → EXPORT_REQUIRES_TRANSACTION。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session:
        # 不开事务
        with pytest.raises(LedgerSnapshotError) as exc:
            await export_ledger_segment(session, tenant_id=ids["tid"])
        assert exc.value.reason == "EXPORT_REQUIRES_TRANSACTION"
