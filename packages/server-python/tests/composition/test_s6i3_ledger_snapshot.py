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
from typing import Any

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

# 异步测试由 pytest-asyncio asyncio_mode="auto" 自动标记；模块级 pytestmark
# 显式移除以允许同步纯内存测试存在（避免 PytestWarning 噪音）

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
    manifest1 = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
    manifest2 = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
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
    m_a = decode_ledger_segment(payload_a, expected_tenant_id=tid_a)
    m_b = decode_ledger_segment(payload_b, expected_tenant_id=tid_b)
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
    m = decode_ledger_segment(payload, expected_tenant_id=tid)
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
    m = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "CONTENT_DIGEST_MISMATCH"


async def test_d1a_duplicate_stable_identity_fails(snapshot_factory):
    """重复 stable_identity → DUPLICATE_STABLE_IDENTITY（cross-kind catch-all）。

    注意：必须用 external_ref record 构造（operation 重复已被 DUPLICATE_OPERATION_ID
    优先拦截，checkpoint 重复已被 DUPLICATE_CHECKPOINT_OWNER_KEY 拦截）。
    本测试只验证 stable_identity 跨 kind 去重这一 catch-all。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 复制第一条 external_ref record 并插入紧邻其原位之后 → 仍按 stable_identity 升序
    dup = dict(env["records"]["external_ref"][0])
    env["records"]["external_ref"].insert(1, dup)
    # count / digest 同步以隔离此 fail closed
    env["manifest"]["external_ref"]["count"] = len(env["records"]["external_ref"])
    from app.shared.schemas.canonical_json import canonical_digest as _cd
    env["manifest"]["external_ref"]["content_digest"] = _cd(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "external_ref",
            "records": [
                {
                    "stable_identity": r["stable_identity"],
                    "table_identity": r["table_identity"],
                    "fields": r["fields"],
                }
                for r in env["records"]["external_ref"]
            ],
        }
    )
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
    m = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
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
    m = decode_ledger_segment(payload, expected_tenant_id=tid)
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
    m = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
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
    m = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
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
    decode_ledger_segment(payload, expected_tenant_id=ids["tid"])


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
    m = decode_ledger_segment(payload, expected_tenant_id=tid)
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "RECORDS_NOT_SORTED"

    # --- 层 2：真实 exporter 调用 → 若 M7 mutation 注入（绕过 sorted）则失败 ---
    # 该层在 mutation 注入时让测试失败；正常代码路径下 export + decode 都通过。
    async with factory() as session2, session2.begin():
        await session2.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        real_payload = await export_ledger_segment(session2, tenant_id=ids["tid"])
    decode_ledger_segment(real_payload, expected_tenant_id=ids["tid"])  # 正常 sorted → 通过


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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "RUNTIME_PROOF_FLAG_MISSING"
    # 2. 显式 True
    env = json.loads(payload)
    env["runtime_per_binding_proof_available"] = True
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
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
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "CROSS_TENANT_RECORD"


# --- 第二轮 P1：逻辑身份 + 六元组完整性 + tenant 绑定 + strict decoder ---


def _recompute_kind_digest(env: dict, kind: str) -> str:
    """辅助：篡改 record fields 后必须同步重算对应 kind content_digest，
    否则会被 CONTENT_DIGEST_MISMATCH 抢占，无法命中目标 fail-closed。"""
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    return _cd(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "records": [
                {
                    "stable_identity": r["stable_identity"],
                    "table_identity": r["table_identity"],
                    "fields": r["fields"],
                }
                for r in env["records"][kind]
            ],
        }
    )


async def test_d1a_stable_identity_id_mismatch_fails(snapshot_factory):
    """stable_identity 与 fields.id 不一致（破坏 f"{record_kind}:{fields.id}" 绑定）
    → STABLE_IDENTITY_BINDING_MISMATCH（按用户裁决 一-1）。"""
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 把第一条 operation 的 stable_identity 改成不匹配 fields.id 的字符串
    real_id = env["records"]["operation"][0]["fields"]["id"]
    env["records"]["operation"][0]["stable_identity"] = f"operation:{real_id}-mismatch"
    # 同步重算 digest 以隔离 CONTENT_DIGEST_MISMATCH 抢占
    env["manifest"]["operation"]["content_digest"] = _recompute_kind_digest(env, "operation")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "STABLE_IDENTITY_BINDING_MISMATCH"
    assert exc.value.detail["kind"] == "operation"
    assert exc.value.detail["reason"] == "stable_identity_does_not_match_fields_id"


async def test_d1a_duplicate_operation_id_fails(snapshot_factory):
    """两条 operation record 共享同一 fields.id → DUPLICATE_OPERATION_ID（按用户裁决 一-2）。

    注意：构造时必须保持 stable_identity 仍 == f"operation:{fields.id}"（否则会被
    STABLE_IDENTITY_BINDING_MISMATCH 抢占），并保持 sorted 顺序（prev_sid == sid）。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed, n_operations=2)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    # 拿第二条 op 的 record，覆写 fields.id 与 stable_identity 与第一条相同（保持 binding）
    op1_id = env["records"]["operation"][0]["fields"]["id"]
    op1_sid = env["records"]["operation"][0]["stable_identity"]
    env["records"]["operation"][1]["fields"]["id"] = op1_id
    env["records"]["operation"][1]["stable_identity"] = op1_sid
    # count + digest 同步
    env["manifest"]["operation"]["count"] = len(env["records"]["operation"])
    env["manifest"]["operation"]["content_digest"] = _recompute_kind_digest(env, "operation")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "DUPLICATE_OPERATION_ID"
    assert exc.value.detail["operation_id"] == str(op1_id)


async def test_d1a_duplicate_checkpoint_owner_key_fails(snapshot_factory):
    """两条 checkpoint record 共享同一 (purge_operation_id, owner_key) → DUPLICATE_CHECKPOINT_OWNER_KEY
    （按用户裁决 一-2）。
    """
    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed, n_checkpoints=2)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    env = json.loads(payload)
    cp1 = env["records"]["checkpoint"][0]
    cp2 = env["records"]["checkpoint"][1]
    # 把 cp2 的 (purge_operation_id, owner_key) 改为与 cp1 相同（stable_identity 因 fields.id 不同而不同）
    cp2["fields"]["purge_operation_id"] = cp1["fields"]["purge_operation_id"]
    cp2["fields"]["owner_key"] = cp1["fields"]["owner_key"]
    # stable_identity 因 fields.id 不同而不同 → 不触发 STABLE_IDENTITY_BINDING_MISMATCH
    # 两 record 共用 (op_id, owner_key) → DUPLICATE_CHECKPOINT_OWNER_KEY
    env["records"]["checkpoint"].sort(key=lambda r: r["stable_identity"])
    # count + digest 同步
    env["manifest"]["checkpoint"]["count"] = len(env["records"]["checkpoint"])
    env["manifest"]["checkpoint"]["content_digest"] = _recompute_kind_digest(env, "checkpoint")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "DUPLICATE_CHECKPOINT_OWNER_KEY"
    assert exc.value.detail["purge_operation_id"] == str(cp1["fields"]["purge_operation_id"])
    assert exc.value.detail["owner_key"] == str(cp1["fields"]["owner_key"])


@pytest.mark.parametrize(
    "missing_field",
    [
        "owner_key",
        "purge_operation_id",
        "owner_version",
        "capability_digest",
        "state",
    ],
)
async def test_d1a_owner_six_tuple_incomplete_checkpoint_field_missing(
    snapshot_factory, missing_field
):
    """checkpoint 六元组各必需字段缺失 → OWNER_SIX_TUPLE_INCOMPLETE（按用户裁决 一-3）。

    decoder 阶段即抛（不再等到 reconstruct_owner_facts 才暴露 KeyError）。
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
    env["records"]["checkpoint"][0]["fields"][missing_field] = None
    env["manifest"]["checkpoint"]["count"] = len(env["records"]["checkpoint"])
    env["manifest"]["checkpoint"]["content_digest"] = _recompute_kind_digest(env, "checkpoint")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "OWNER_SIX_TUPLE_INCOMPLETE"
    assert exc.value.detail["kind"] == "checkpoint"
    assert missing_field in exc.value.detail["missing_fields"]
    assert exc.value.detail["reason"] == "checkpoint_required_field_missing"


async def test_d1a_owner_six_tuple_incomplete_purge_revision_missing(snapshot_factory):
    """operation.purge_revision 缺失 → OWNER_SIX_TUPLE_INCOMPLETE（按用户裁决 一-3）。

    decoder 阶段即抛；reconstruct_owner_facts 不再触发 KeyError。
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
    env["records"]["operation"][0]["fields"]["purge_revision"] = None
    env["manifest"]["operation"]["count"] = len(env["records"]["operation"])
    env["manifest"]["operation"]["content_digest"] = _recompute_kind_digest(env, "operation")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "OWNER_SIX_TUPLE_INCOMPLETE"
    assert exc.value.detail["kind"] == "operation"
    assert "purge_revision" in exc.value.detail["missing_fields"]
    assert exc.value.detail["reason"] == "operation_purge_revision_missing"


async def test_d1a_tenant_binding_mismatch_empty_artifact_fails(snapshot_factory):
    """空 artifact（records 全空）也必须校验 tenant binding——不得依赖 records 非空
    （按用户裁决 二-4）。"""
    factory = snapshot_factory
    async with factory() as seed:
        tid_a = await _seed_tenant(seed, name="ta")
        tid_b = await _seed_tenant(seed, name="tb")
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=tid_a)
    # 确认 envelope 是空 records + declared=tid_a
    m = decode_ledger_segment(payload, expected_tenant_id=tid_a)
    assert m.record_count["operation"] == 0
    # 现在传 expected=tid_b → TENANT_BINDING_MISMATCH（即使 artifact 全空）
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(payload, expected_tenant_id=tid_b)
    assert exc.value.reason == "TENANT_BINDING_MISMATCH"
    assert exc.value.detail["declared_tenant_id"] == str(tid_a)
    assert exc.value.detail["expected_tenant_id"] == str(tid_b)


async def test_d1a_tenant_not_uuid_fails(snapshot_factory):
    """tenant_id 字符串不是规范 UUID → TENANT_ID_NOT_UUID（按用户裁决 二-3）。

    非空记录与空记录都必须拒绝——以防 producer 端某 tenant 字段被静默序列化。
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
    env["tenant_id"] = "not-a-uuid"
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "TENANT_ID_NOT_UUID"


async def test_d1a_manifest_unknown_kind_fails(snapshot_factory):
    """manifest 顶层 keys 含 RECORD_KINDS 之外的 kind → MANIFEST_KIND_UNKNOWN（按用户裁决 三-1）。
    与 UNKNOWN_KIND（records 顶层）独立；manifest-only 反例覆盖此隔离路径。
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
    # manifest 额外加 bogus_kind（records 不变——确保 records 路径不抢先）
    env["manifest"]["bogus_kind"] = {"count": 0, "content_digest": "a" * 64}
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "MANIFEST_KIND_UNKNOWN"
    assert "bogus_kind" in exc.value.detail["extra_kinds"]


async def test_d1a_ack_not_hex_fails(snapshot_factory):
    """checkpoint.state='acked' 但 ack_digest 是 64 字符但非小写 hex
    → ACK_INVARIANT_VIOLATED（按用户裁决 三-3：64-hex lowercase 应用层门禁）。

    注意：迁移 034 仅约束 length=64，**64-hex 校验为应用层附加门禁**。
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
    ck = env["records"]["checkpoint"][0]
    ck["fields"]["state"] = "acked"
    ck["fields"]["ack_digest"] = "Z" * 64  # 64 chars 但含大写 Z（非小写 hex）
    env["manifest"]["checkpoint"]["count"] = len(env["records"]["checkpoint"])
    env["manifest"]["checkpoint"]["content_digest"] = _recompute_kind_digest(env, "checkpoint")
    bad = json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=ids["tid"])
    assert exc.value.reason == "ACK_INVARIANT_VIOLATED"
    assert (
        exc.value.detail["reason"] == "acked_requires_64hex_lowercase_ack_digest"
    )


async def test_d1a_reconstruct_owner_facts_defensive_no_silent_overwrite(snapshot_factory):
    """reconstruct_owner_facts 防御性兜底：即使 envelope 异常导致必须字段 None，
    仍以具名错误抛出（OWNER_SIX_TUPLE_INCOMPLETE / CHECKPOINT_WITHOUT_OPERATION），
    **绝不**以默认字符串/sentinel 静默构造 owner fact。

    此处直接构造 ``Manifest`` 对象绕过 decoder（六元组缺失不会被 decoder 捕获），
    验证 reconstruct 路径同样 fail closed。
    """
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        Manifest,
    )

    factory = snapshot_factory
    async with factory() as seed:
        ids = await _seed_minimal_ledger(seed)
    async with factory() as session, session.begin():
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        payload = await export_ledger_segment(session, tenant_id=ids["tid"])
    m = decode_ledger_segment(payload, expected_tenant_id=ids["tid"])
    # 篡改 checkpoint record 的 owner_key 字段为 None（绕过 decoder；直接改 Manifest.records）
    cp_records = list(m.records["checkpoint"])
    cp0 = cp_records[0]
    tampered_fields = dict(cp0.fields)
    tampered_fields["owner_key"] = None
    tampered = ExportedRecord(
        record_kind=cp0.record_kind,
        table_identity=cp0.table_identity,
        stable_identity=cp0.stable_identity,
        fields=tampered_fields,
    )
    cp_records[0] = tampered
    new_records = dict(m.records)
    new_records["checkpoint"] = tuple(cp_records)
    bad_manifest = Manifest(
        schema_version=m.schema_version,
        tenant_id=m.tenant_id,
        record_count=m.record_count,
        content_digest=m.content_digest,
        runtime_per_binding_proof_available=m.runtime_per_binding_proof_available,
        records=new_records,
        raw=m.raw,
    )
    with pytest.raises(LedgerSnapshotError) as exc:
        reconstruct_owner_facts(bad_manifest)
    assert exc.value.reason == "OWNER_SIX_TUPLE_INCOMPLETE"
    assert "owner_key" in exc.value.detail["missing_fields"]


# --- 第三轮 P1：纯内存 decoder 负例 + reconstruct 防御性归一化 ---


_DIGEST_HEX = "a" * 64


def _build_envelope_one_record(
    *,
    tid: uuid.UUID,
    op_id: uuid.UUID,
    cp_id: uuid.UUID,
    ext_id: uuid.UUID,
    rec_id: uuid.UUID,
    op_state: str = "running",
    cp_state: str = "erasing",
    cp_owner_key: str = "external.payload.v1",
    cp_owner_version: int = 1,
    cp_capability_digest: str = _DIGEST_HEX,
    op_purge_revision: int = 1,
    cp_ack_digest: str | None = None,
) -> dict:
    """纯内存构造一份含 1 op / 1 cp / 1 ext / 1 rec 的合法 envelope dict。

    所有字段均按真实 DB 列语义填齐；content_digest 由 ``_envelope_with_digest`` 重算。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tid),
        "manifest": {},  # 由 _envelope_with_digest 重算
        "runtime_per_binding_proof_available": False,
        "records": {
            "operation": [
                {
                    "stable_identity": f"operation:{op_id}",
                    "table_identity": "agent_conversation_purges",
                    "fields": {
                        "id": str(op_id),
                        "tenant_id": str(tid),
                        "conversation_id": str(uuid.uuid4()),
                        "purge_revision": op_purge_revision,
                        "state": op_state,
                        "registry_digest": _DIGEST_HEX,
                        "retention_policy_digest": _DIGEST_HEX,
                        "hold_revision_snapshot": 0,
                        "lease_epoch": 1,
                        "failure_code": None,
                        "revision": 1,
                        "scheduled_at": None,
                        "started_at": None,
                        "completed_at": None,
                        "next_retry_at": None,
                    },
                }
            ],
            "checkpoint": [
                {
                    "stable_identity": f"checkpoint:{cp_id}",
                    "table_identity": "agent_conversation_purge_owners",
                    "fields": {
                        "id": str(cp_id),
                        "tenant_id": str(tid),
                        "purge_operation_id": str(op_id),
                        "owner_key": cp_owner_key,
                        "owner_version": cp_owner_version,
                        "capability_digest": cp_capability_digest,
                        "state": cp_state,
                        "attempt": 1,
                        "checkpoint_digest": _DIGEST_HEX,
                        "ack_digest": cp_ack_digest,
                        "reason_code": None,
                    },
                }
            ],
            "external_ref": [
                {
                    "stable_identity": f"external_ref:{ext_id}",
                    "table_identity": "agent_external_object_refs",
                    "fields": {
                        "id": str(ext_id),
                        "tenant_id": str(tid),
                        "conversation_id": str(uuid.uuid4()),
                        "owner_key": cp_owner_key,
                        "ref_scheme": "db_local",
                        "source_table": "agent_workspace_outbox",
                        "source_row_id": str(uuid.uuid4()),
                        "erase_state": "registered",
                        "receipt_digest": None,
                        "blocked_reason": None,
                        "created_at": None,
                        "updated_at": None,
                    },
                }
            ],
            "reconcile": [
                {
                    "stable_identity": f"reconcile:{rec_id}",
                    "table_identity": "agent_transport_scope_reconcile",
                    "fields": {
                        "id": str(rec_id),
                        "tenant_id": str(tid),
                        "owner_key": "workspace.transport.v1",
                        "source_table": "agent_workspace_outbox",
                        "source_row_id": str(uuid.uuid4()),
                        "conversation_id": None,
                        "reconcile_class": "tenant_scope",
                        "issue_code": "source_message_missing",
                        "state": "open",
                        "resolution_digest": None,
                        "revision": 1,
                        "created_at": None,
                        "resolved_at": None,
                    },
                }
            ],
        },
    }


def _envelope_with_digest(env: dict) -> dict:
    """按 envelope 内容重算 manifest count + content_digest，返回完整 envelope。"""
    from app.shared.schemas.canonical_json import canonical_digest as _cd

    out = dict(env)
    records = env["records"]
    manifest: dict[str, dict[str, Any]] = {}
    for kind, recs in records.items():
        manifest[kind] = {
            "count": len(recs),
            "content_digest": _cd(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": kind,
                    "records": [
                        {
                            "stable_identity": r["stable_identity"],
                            "table_identity": r["table_identity"],
                            "fields": r["fields"],
                        }
                        for r in recs
                    ],
                }
            ),
        }
    out["manifest"] = manifest
    return out


def _envelope_to_bytes(env: dict) -> bytes:
    import json as _json

    return _json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _make_seed_ids() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    return (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )


def test_d1a_schema_version_bool_rejected_memory():
    """schema_version=True（bool 是 int 子类）⇒ SCHEMA_VERSION_MISSING_OR_INVALID。

    纯内存反例——不依赖 PG；攻击者构造 envelope 时若把 schema_version 设 True，
    decoder 必须按严格 int（排除 bool）拒绝。
    """
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    env["schema_version"] = True
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "SCHEMA_VERSION_MISSING_OR_INVALID"
    assert exc.value.detail.get("reason") == "strict_int_required"


def test_d1a_manifest_count_bool_rejected_memory():
    """manifest[*].count=False ⇒ MANIFEST_COUNT_MISSING_OR_INVALID（按 strict int）。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    env["manifest"]["operation"]["count"] = False
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "MANIFEST_COUNT_MISSING_OR_INVALID"
    assert exc.value.detail["found_type"] == "bool"


def test_d1a_tenant_uppercase_uuid_rejected_memory():
    """大写 UUID（非 canonical）⇒ TENANT_ID_NOT_CANONICAL_UUID。

    ``str(uuid.UUID(tid))`` 必须 == tid；大写形式 fail closed。
    """
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    # 用大写形式重置 envelope 顶层 tenant_id（虽然 uuid.UUID 解析后 str() 会 lowercase）
    env["tenant_id"] = str(uuid.UUID(str(tid))).upper()
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "TENANT_ID_NOT_CANONICAL_UUID"


def test_d1a_tenant_no_hyphens_rejected_memory():
    """去连字符 UUID（非 canonical）⇒ TENANT_ID_NOT_CANONICAL_UUID。

    uuid.UUID() 接受无连字符 hex，但 str() 会重规范化为连字符形式。
    """
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    env["tenant_id"] = str(tid).replace("-", "")
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "TENANT_ID_NOT_CANONICAL_UUID"


def test_d1a_manifest_digest_uppercase_hex_rejected_memory():
    """manifest.content_digest 含大写 hex（长度合法但非小写）⇒ MANIFEST_CONTENT_DIGEST_NOT_64HEX。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    env["manifest"]["operation"]["content_digest"] = "A" * 64
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "MANIFEST_CONTENT_DIGEST_NOT_64HEX"


def test_d1a_manifest_digest_non_hex_rejected_memory():
    """manifest.content_digest 64 字符但非 hex（含 'Z'）⇒ MANIFEST_CONTENT_DIGEST_NOT_64HEX。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    env["manifest"]["operation"]["content_digest"] = "Z" * 64
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "MANIFEST_CONTENT_DIGEST_NOT_64HEX"


def test_d1a_operation_purge_revision_bool_rejected_memory():
    """operation.purge_revision=True（bool）⇒ OPERATION_PURGE_REVISION_TYPE_INVALID。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _build_envelope_one_record(
        tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
        op_purge_revision=1,
    )
    env["records"]["operation"][0]["fields"]["purge_revision"] = True
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "OPERATION_PURGE_REVISION_TYPE_INVALID"
    assert exc.value.detail["reason"] == "strict_int_required"


def test_d1a_checkpoint_owner_version_bool_rejected_memory():
    """checkpoint.owner_version=True ⇒ CHECKPOINT_OWNER_VERSION_TYPE_INVALID。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _build_envelope_one_record(
        tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
        cp_owner_version=1,
    )
    env["records"]["checkpoint"][0]["fields"]["owner_version"] = True
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "CHECKPOINT_OWNER_VERSION_TYPE_INVALID"


def test_d1a_checkpoint_owner_key_int_rejected_memory():
    """checkpoint.owner_key 是 int ⇒ CHECKPOINT_OWNER_KEY_TYPE_INVALID（string 字段）。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _build_envelope_one_record(
        tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
        cp_owner_key="external.payload.v1",
    )
    env["records"]["checkpoint"][0]["fields"]["owner_key"] = 12345
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "CHECKPOINT_OWNER_KEY_TYPE_INVALID"


def test_d1a_checkpoint_capability_digest_int_rejected_memory():
    """checkpoint.capability_digest 是 int ⇒ CHECKPOINT_CAPABILITY_DIGEST_TYPE_INVALID。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _build_envelope_one_record(
        tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
        cp_capability_digest=_DIGEST_HEX,
    )
    env["records"]["checkpoint"][0]["fields"]["capability_digest"] = 12345
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    # int 先撞 _assert_string_field 的 TYPE_INVALID 路径（非 FORMAT_INVALID）
    assert exc.value.reason == "CHECKPOINT_CAPABILITY_DIGEST_TYPE_INVALID"


def test_d1a_checkpoint_id_not_canonical_uuid_rejected_memory():
    """checkpoint.id 是非 canonical UUID ⇒ CHECKPOINT_ID_NOT_CANONICAL_UUID。"""
    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _build_envelope_one_record(
        tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
    )
    env["records"]["checkpoint"][0]["fields"]["id"] = str(cp_id).upper()
    env["records"]["checkpoint"][0]["stable_identity"] = f"checkpoint:{str(cp_id).upper()}"
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "CHECKPOINT_ID_NOT_CANONICAL_UUID"


def test_d1a_reconstruct_direct_manifest_normalizes_type_error():
    """caller 直接构造 Manifest 绕过 decoder——owner_version 是字符串 "abc"。

    不应漏出 ``int("abc")`` ValueError；必须归一化为
    ``RECONSTRUCT_OWNER_VERSION_TYPE_INVALID``。
    """
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        Manifest,
    )

    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    m = decode_ledger_segment(_envelope_to_bytes(env), expected_tenant_id=tid)
    # 直接篡改 Manifest 内部 records（绕过 decoder）
    cp0 = m.records["checkpoint"][0]
    tampered_fields = dict(cp0.fields)
    tampered_fields["owner_version"] = "abc"  # 非 strict int
    tampered = ExportedRecord(
        record_kind=cp0.record_kind,
        table_identity=cp0.table_identity,
        stable_identity=cp0.stable_identity,
        fields=tampered_fields,
    )
    new_records = dict(m.records)
    new_records["checkpoint"] = (tampered,)
    bad_manifest = Manifest(
        schema_version=m.schema_version,
        tenant_id=m.tenant_id,
        record_count=m.record_count,
        content_digest=m.content_digest,
        runtime_per_binding_proof_available=m.runtime_per_binding_proof_available,
        records=new_records,
        raw=m.raw,
    )
    with pytest.raises(LedgerSnapshotError) as exc:
        reconstruct_owner_facts(bad_manifest)
    # 防御性归一化：必须是 LedgerSnapshotError，**不**是 ValueError
    assert exc.value.reason == "RECONSTRUCT_OWNER_VERSION_TYPE_INVALID"


def test_d1a_reconstruct_direct_manifest_ack_field_format_invalid():
    """caller 直接构造 Manifest——ack_digest 长度 64 但含大写（state=acked）。"""
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        Manifest,
    )

    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id,
            cp_state="acked",
            cp_ack_digest="a" * 64,
        )
    )
    m = decode_ledger_segment(_envelope_to_bytes(env), expected_tenant_id=tid)
    cp0 = m.records["checkpoint"][0]
    tampered_fields = dict(cp0.fields)
    tampered_fields["ack_digest"] = "Z" * 64  # 64 chars but uppercase Z
    tampered = ExportedRecord(
        record_kind=cp0.record_kind,
        table_identity=cp0.table_identity,
        stable_identity=cp0.stable_identity,
        fields=tampered_fields,
    )
    new_records = dict(m.records)
    new_records["checkpoint"] = (tampered,)
    bad_manifest = Manifest(
        schema_version=m.schema_version,
        tenant_id=m.tenant_id,
        record_count=m.record_count,
        content_digest=m.content_digest,
        runtime_per_binding_proof_available=m.runtime_per_binding_proof_available,
        records=new_records,
        raw=m.raw,
    )
    with pytest.raises(LedgerSnapshotError) as exc:
        reconstruct_owner_facts(bad_manifest)
    assert exc.value.reason == "RECONSTRUCT_ACK_DIGEST_FORMAT_INVALID"


def test_d1a_reconstruct_direct_manifest_normalizes_internal_type_error():
    """caller 直接构造 Manifest——capability_digest 是 list（不应漏出 TypeError）。

    防御性归一化路径：``_HEX_LOWER_64.match(list)`` 抛 TypeError，应被 wrapper
    归一化为 ``RECONSTRUCT_INTERNAL_TYPE_ERROR``（按用户裁决 三-2 末段）。
    """
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        Manifest,
    )

    tid, op_id, cp_id, ext_id, rec_id = _make_seed_ids()
    env = _envelope_with_digest(
        _build_envelope_one_record(
            tid=tid, op_id=op_id, cp_id=cp_id, ext_id=ext_id, rec_id=rec_id
        )
    )
    m = decode_ledger_segment(_envelope_to_bytes(env), expected_tenant_id=tid)
    cp0 = m.records["checkpoint"][0]
    tampered_fields = dict(cp0.fields)
    tampered_fields["capability_digest"] = [1, 2, 3]  # list，不是 str
    tampered = ExportedRecord(
        record_kind=cp0.record_kind,
        table_identity=cp0.table_identity,
        stable_identity=cp0.stable_identity,
        fields=tampered_fields,
    )
    new_records = dict(m.records)
    new_records["checkpoint"] = (tampered,)
    bad_manifest = Manifest(
        schema_version=m.schema_version,
        tenant_id=m.tenant_id,
        record_count=m.record_count,
        content_digest=m.content_digest,
        runtime_per_binding_proof_available=m.runtime_per_binding_proof_available,
        records=new_records,
        raw=m.raw,
    )
    with pytest.raises(LedgerSnapshotError) as exc:
        reconstruct_owner_facts(bad_manifest)
    # capability_digest 是 list，_assert_string_field helper 抛
    # RECONSTRUCT_CAPABILITY_DIGEST_FORMAT_INVALID（更具体的子路径）。
    # 关键是**不**漏出原生 TypeError。
    assert isinstance(exc.value, LedgerSnapshotError)
    assert exc.value.reason in (
        "RECONSTRUCT_CAPABILITY_DIGEST_FORMAT_INVALID",
        "RECONSTRUCT_INTERNAL_TYPE_ERROR",
    )


def test_d1a_consumer_segment_limit_exceeded_memory():
    """10001 条合法摘要 artifact 在 consumer 端被强制拦截（按用户裁决 三-3）。

    producer 端 ``_select_all_for_kind`` 用 SQL LIMIT 截断；本测试模拟 caller
    直接构造 10001 条 record + 合法 manifest 的 artifact——decoder 必须 fail closed。
    """
    tid = uuid.uuid4()
    n = MAX_RECORDS_PER_KIND + 1
    # 构造 10001 条 operation record（stable_identity 按字典序排序以通过 RECORDS_NOT_SORTED）
    op_records: list[dict[str, Any]] = []
    for i in range(n):
        op_id = uuid.uuid4()
        op_records.append(
            {
                "stable_identity": f"operation:{op_id}",
                "table_identity": "agent_conversation_purges",
                "fields": {
                    "id": str(op_id),
                    "tenant_id": str(tid),
                    "conversation_id": str(uuid.uuid4()),
                    "purge_revision": i + 1,
                    "state": "running",
                    "registry_digest": _DIGEST_HEX,
                    "retention_policy_digest": _DIGEST_HEX,
                    "hold_revision_snapshot": 0,
                    "lease_epoch": 1,
                    "failure_code": None,
                    "revision": 1,
                    "scheduled_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "next_retry_at": None,
                },
            }
        )
    # 按 stable_identity 字典序排序，确保 RECORDS_NOT_SORTED 不抢先
    op_records.sort(key=lambda r: r["stable_identity"])
    env = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tid),
        "manifest": {},
        "runtime_per_binding_proof_available": False,
        "records": {
            "operation": op_records,
            "checkpoint": [],
            "external_ref": [],
            "reconcile": [],
        },
    }
    env = _envelope_with_digest(env)
    bad = _envelope_to_bytes(env)
    with pytest.raises(LedgerSnapshotError) as exc:
        decode_ledger_segment(bad, expected_tenant_id=tid)
    assert exc.value.reason == "SEGMENT_LIMIT_EXCEEDED"
    assert exc.value.detail["kind"] == "operation"
    assert exc.value.detail["actual"] == n
    assert exc.value.detail["max_records_per_kind"] == MAX_RECORDS_PER_KIND
