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
    MAX_RECORDS_PER_KIND,
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
        ids = await _seed_minimal_ledger(seed)

    payloads: list[bytes] = []
    for _ in range(3):
        async with factory() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            payloads.append(
                await export_ledger_segment(session, tenant_id=ids["tid"])
            )
    assert payloads[0] == payloads[1] == payloads[2]


async def test_d1a_tenant_isolation(snapshot_factory):
    """不同 tenant 数据严格隔离——export_a 不含 tenant_b 的 record。

    注意：必须使用 ``_seed_minimal_ledger`` 返回的 tid（**不能**通过 tenants.name 字母序
    反查——metaedu_test 残留大量 prior run 的 A-*/B-* 租户，字母序首个 A-* 与本测试
    种入的 A-* 不同，会造成 SELECT 返回 0 行 + 断言空过，CI fresh DB 下立即暴露。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids_a = await _seed_minimal_ledger(seed, tenant_label="A")
        ids_b = await _seed_minimal_ledger(seed, tenant_label="B")
        tid_a = ids_a["tid"]
        tid_b = ids_b["tid"]

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
    """重复 stable_identity → DUPLICATE_STABLE_IDENTITY。

    注意：必须把重复项插入到「原记录相邻位置」才能避开 RECORDS_NOT_SORTED 检查
    （新增校验顺序：RECORDS_NOT_SORTED → DUPLICATE_STABLE_IDENTITY）。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 复制第一条 operation record 并插入紧邻其原位之后 → 仍按 stable_identity 升序
    dup = dict(env["records"]["operation"][0])
    env["records"]["operation"].insert(1, dup)
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
    """external_ref 严禁输出 ref_value（spec §10 末段 + 用户裁决）。

    M2 mutation 目标：必须先断言 external_ref records 非空（确认 seed 真产生数据），
    再检查 payload 不含 secret → 命中 `_export_external_ref` columns 白名单防线。
    """
    factory = snapshot_factory
    secret = "obj://staging/secret-must-not-leak/d1a"
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed, ref_value=secret)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    # precondition：external_ref records 必须非空（确保 M2 真命中 select 路径）
    m = decode_ledger_segment(payload)
    assert len(m.records["external_ref"]) >= 1, (
        "precondition failed: external_ref records empty, M2 mutation target unreachable"
    )
    # 字符串全包搜索：secret 不应出现
    assert secret.encode("utf-8") not in payload, (
        f"external_ref secret leaked: {secret!r} found in export payload"
    )
    # decoder 进一步断言：external_ref 字段集合不含 ref_value
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
    """reconstruct_owner_facts 返回 (operation_id, owner_key) → OwnerFacts 六元组（用户裁决 3）。

    六元组：owner_key / operation_id / ack_digest / owner_version / capability_digest /
    checkpoint_state / purge_revision。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    m = decode_ledger_segment(payload)
    facts = reconstruct_owner_facts(m)
    expected_op = str(ids["op_ids"][0])
    key = (expected_op, "external.payload.v1")
    assert key in facts
    f = facts[key]
    assert f.owner_key == "external.payload.v1"
    assert f.owner_version == 1
    assert f.capability_digest == _DIGEST
    assert f.checkpoint_state == "erasing"
    assert f.purge_revision == 1
    # runtime per-binding proof unavailable 显式（用户裁决 c）
    assert f.runtime_per_binding_proof_available is False


# --- tests: runtime per-binding proof unavailable explicit ---


async def test_d1a_runtime_per_binding_proof_unavailable_explicit(snapshot_factory):
    """runtime per-binding proof unavailable 显式判定（用户裁决 c）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
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


# --- tests: bounded segment + transaction attribute enforcement (用户裁决 1 + 4) ---


async def test_d1a_segment_limit_exceeded(snapshot_factory):
    """每类 record 上限 → SEGMENT_LIMIT_EXCEEDED，**不**截断后冒充完整 snapshot。"""
    factory = snapshot_factory
    # 种 MAX_RECORDS_PER_KIND + 1 行 operation（最小上限触发）
    async with factory() as seed:
        tid = await _seed_tenant(seed, name="b")
        cid = await _seed_conversation(seed, tid=tid)
        n = MAX_RECORDS_PER_KIND + 1
        for i in range(n):
            await _seed_operation(
                seed,
                tid=tid,
                cid=cid,
                state="running",
                purge_rev=i + 1,
            )
        await seed.commit()
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        with pytest.raises(LedgerSnapshotError) as exc:
            await export_ledger_segment(session, tenant_id=tid)
        assert exc.value.reason == "SEGMENT_LIMIT_EXCEEDED"
        assert exc.value.detail["table"] == "agent_conversation_purges"
        assert exc.value.detail["max_records_per_kind"] == MAX_RECORDS_PER_KIND


async def test_d1a_transaction_read_committed_rejected(snapshot_factory):
    """read committed 事务必须拒绝（按用户裁决 4）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        with pytest.raises(LedgerSnapshotError) as exc:
            await export_ledger_segment(session, tenant_id=ids["tid"])
        assert exc.value.reason == "TX_ISOLATION_NOT_REPEATABLE_READ"


async def test_d1a_transaction_repeatable_read_write_rejected(snapshot_factory):
    """REPEATABLE READ 但 read-write 事务必须拒绝（按用户裁决 4）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        # isolation 是 RR，但没设 READ ONLY → exporter 入口拒绝
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        with pytest.raises(LedgerSnapshotError) as exc:
            await export_ledger_segment(session, tenant_id=ids["tid"])
        assert exc.value.reason == "TX_NOT_READ_ONLY"


async def test_d1a_transaction_repeatable_read_only_accepted(snapshot_factory):
    """REPEATABLE READ + READ ONLY 事务正常通过（基线）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    decode_ledger_segment(payload)


# --- tests: six-tuple no overwrite (用户裁决 3) ---


async def test_d1a_two_operations_same_owner_key_preserved(snapshot_factory):
    """同 tenant 两个 operation 共享同一 owner_key → 两者均保留（不得仅以 owner_key 覆盖）。

    验证 reconstruct_owner_facts 返回 dict[tuple[operation_id, owner_key], OwnerFacts]
    能容纳同 owner_key 的两个 operation。
    """
    factory = snapshot_factory
    async with factory() as seed:
        tid = await _seed_tenant(seed, name="two-op")
        cid = await _seed_conversation(seed, tid=tid)
        # 两个 operation（不同 purge_revision）
        op1_id = await _seed_operation(
            seed, tid=tid, cid=cid, state="running", purge_rev=1
        )
        op2_id = await _seed_operation(
            seed, tid=tid, cid=cid, state="running", purge_rev=2
        )
        # 同一个 owner_key 在两个 operation 上各一条 checkpoint
        await _seed_checkpoint(
            seed,
            tid=tid,
            purge_operation_id=op1_id,
            owner_key="external.payload.v1",
            owner_version=1,
            state="acked",
            ack_digest=_DIGEST,
        )
        await _seed_checkpoint(
            seed,
            tid=tid,
            purge_operation_id=op2_id,
            owner_key="external.payload.v1",  # 同一 owner_key
            owner_version=2,
            state="acked",
            ack_digest=_OTHER_DIGEST,
        )
        await seed.commit()

    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=tid)
    m = decode_ledger_segment(payload)
    facts = reconstruct_owner_facts(m)
    # 两条 facts 都应在，键为 (operation_id, owner_key)
    key1 = (str(op1_id), "external.payload.v1")
    key2 = (str(op2_id), "external.payload.v1")
    assert key1 in facts, f"missing {key1} in facts"
    assert key2 in facts, f"missing {key2} in facts (same owner_key overwritten)"
    assert facts[key1].owner_version == 1
    assert facts[key1].ack_digest == _DIGEST
    assert facts[key2].owner_version == 2
    assert facts[key2].ack_digest == _OTHER_DIGEST


# --- tests: decoder strictness (用户裁决 5) ---


async def test_d1a_operation_state_out_of_whitelist(snapshot_factory):
    """operation.state 越界（migration 034 ck_agent_purge_state 之外）→ CROSS_LAYER_STATE_MIX。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["records"]["operation"][0]["fields"]["state"] = "rolled_back"  # 不在 6 值闭集
    # count / digest 同步以隔离 CONTENT_DIGEST_MISMATCH 抢占
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    env["manifest"]["operation"]["count"] = len(env["records"]["operation"])
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
    assert exc.value.reason == "CROSS_LAYER_STATE_MIX"
    assert exc.value.detail["reason"] == "state_out_of_whitelist"
    assert exc.value.detail["kind"] == "operation"


async def test_d1a_checkpoint_state_out_of_whitelist(snapshot_factory):
    """checkpoint.state 越界（migration 034 ck_agent_purge_owner_state 之外）→ CROSS_LAYER_STATE_MIX。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["records"]["checkpoint"][0]["fields"]["state"] = "completed"  # 不在 5 值闭集
    # count / digest 同步以隔离 CONTENT_DIGEST_MISMATCH 抢占
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    env["manifest"]["checkpoint"]["count"] = len(env["records"]["checkpoint"])
    env["manifest"]["checkpoint"]["content_digest"] = _cd(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "checkpoint",
            "records": [
                {
                    "stable_identity": r["stable_identity"],
                    "table_identity": r["table_identity"],
                    "fields": r["fields"],
                }
                for r in env["records"]["checkpoint"]
            ],
        }
    )
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "CROSS_LAYER_STATE_MIX"
    assert exc.value.detail["reason"] == "state_out_of_whitelist"
    assert exc.value.detail["kind"] == "checkpoint"


async def test_d1a_ack_constraint_violation_acked_missing_digest(snapshot_factory):
    """checkpoint.state='acked' 但 ack_digest 非 64-hex → ACK_INVARIANT_VIOLATED。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 将一条 checkpoint 设为 state='acked' + ack_digest 缺失
    ck = env["records"]["checkpoint"][0]
    ck["fields"]["state"] = "acked"
    ck["fields"]["ack_digest"] = None
    # count / digest 同步以隔离此 fail closed
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    env["manifest"]["checkpoint"]["count"] = len(env["records"]["checkpoint"])
    env["manifest"]["checkpoint"]["content_digest"] = _cd(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "checkpoint",
            "records": [
                {
                    "stable_identity": r["stable_identity"],
                    "table_identity": r["table_identity"],
                    "fields": r["fields"],
                }
                for r in env["records"]["checkpoint"]
            ],
        }
    )
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "ACK_INVARIANT_VIOLATED"


async def test_d1a_records_out_of_order_fails(snapshot_factory):
    """records 顺序未按 stable_identity 升序 → RECORDS_NOT_SORTED（按用户裁决 5）。

    M7 mutation 目标：通过真实 exporter 调用验证——若 exporter 端 ``sorted()`` 被绕过，
    输出的 records 必然乱序，decoder 的 RECORDS_NOT_SORTED 立即拒绝。

    双层验证：
    - 手动构造逆序 envelope → decoder 拒绝 RECORDS_NOT_SORTED（不依赖 exporter）
    - 真实 export + decode → 仅在 M7 mutation 注入时才失败（命中 exporter 防线）
    """
    factory = snapshot_factory

    # --- 层 1：手动构造逆序 envelope → decoder 直接拒绝 ---
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed, n_operations=3)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    sids = [r["stable_identity"] for r in env["records"]["operation"]]
    assert len(sids) >= 2
    assert sids == sorted(sids), "precondition: seeded records already unsorted"
    env["records"]["operation"] = list(reversed(env["records"]["operation"]))
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    env["manifest"]["operation"]["count"] = len(env["records"]["operation"])
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
    assert exc.value.reason == "RECORDS_NOT_SORTED"

    # --- 层 2：真实 exporter 调用 → 若 M7 mutation 注入（绕过 sorted）则失败 ---
    # 该层在 mutation 注入时让测试失败；正常代码路径下 export + decode 都通过。
    async with factory() as session2, session2.begin():
        await session2.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        real_payload = await export_ledger_segment(session2, tenant_id=ids["tid"])
    decode_ledger_segment(real_payload)  # 正常 sorted → 通过


async def test_d1a_decoder_unknown_kind_fails(snapshot_factory):
    """records 出现 RECORD_KINDS 之外的 kind → UNKNOWN_KIND。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    env["records"]["bogus_kind"] = []
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "UNKNOWN_KIND"


async def test_d1a_decoder_runtime_proof_missing_or_true_fails(snapshot_factory):
    """runtime_per_binding_proof_available 缺失或显式 True → fail closed（按用户裁决 2）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 1. 缺失
    env.pop("runtime_per_binding_proof_available")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "RUNTIME_PROOF_FLAG_MISSING"
    # 2. 显式 True
    env = json.loads(payload)
    env["runtime_per_binding_proof_available"] = True
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "RUNTIME_PROOF_FLAG_TRUE"


# --- tests: 篡改 payload 命中 decoder 防线（mutation 配套测试，按用户裁决 6） ---


async def test_d1a_count_tamper_fails(snapshot_factory):
    """篡改 manifest.count（不重算 digest）→ COUNT_MISMATCH。

    M4 mutation 目标：实际篡改 manifest count，确认仅 _assert_count_match 能拒绝。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 篡改 operation manifest count（不重算 content_digest）→ count 与 records 不一致
    env["manifest"]["operation"]["count"] = env["manifest"]["operation"]["count"] + 1
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad)
    assert exc.value.reason == "COUNT_MISMATCH"


async def test_d1a_cross_tenant_tamper_fails(snapshot_factory):
    """篡改 record tenant_id + 同步重算该 kind digest → 仅 _assert_cross_tenant 拒绝。

    M9 mutation 目标：修改 record tenant_id 为另一 tenant uuid，同步重算该 kind 的
    content_digest（避开 _assert_content_digest 抢占），仅 _assert_cross_tenant 能拒。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 用一个明显非本 tenant 的 UUID 替换 operation record 的 tenant_id
    other_tenant = "deadbeef-dead-beef-dead-beefdeadbeef"
    env["records"]["operation"][0]["fields"]["tenant_id"] = other_tenant
    # 同步重算 content_digest（避开 _assert_content_digest 抢占）
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
    assert exc.value.reason == "CROSS_TENANT_RECORD"
