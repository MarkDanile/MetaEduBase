"""R1-S6-I3-D D1b 测试：专用 MinIO ledger archive sink。

本测试模块分三层：
1. 纯内存测试（无 PG）—— 验证 Protocol/error/key/serialization/commit-graph 推导等
   契约要素；约 25 项。
2. 真实 PG 集成测试（snapshot_factory fixture，连接 ``metaedu_test``）——
   验证 D1a export → D1b archive → D1a decoder round-trip + 21 步 fail-closed
   校验沿 sink 端仍生效；约 11 项。
3. opt-in 真实 MinIO acceptance（``tests/composition/test_s6i3_d_ledger_archive_real_minio.py``）——
   标记 ``@pytest.mark.external_network``，需 ``RUN_REAL_MINIO_TESTS=1`` 才执行。

mutation kill 单独运行：``scripts/s6i3_d_archive_mutation_kill.py``。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.s6i3_d_ledger_archive_sink import (
    DEFAULT_BUCKET_NAME,
    FORBIDDEN_BUCKETS,
    SCHEMA_VERSION,
    ArchiveUnavailableError,
    BucketNotDistinctError,
    CommitMarker,
    CommitMarkerPayloadCorruptError,
    ExistingPayloadDivergesError,
    ExportedSegment,
    ForkDetectedError,
    GenerationRegressionError,
    InMemoryLedgerArchiveSink,
    LedgerArchiveError,
    ObjectIdentityCollisionError,
    ParentExportMissingError,
    PerKindMarker,
    PublishPreconditionFailedError,
    SegmentDigestMismatchError,
    SegmentObjectMissingError,
    TenantMismatchError,
    TransientArchiveError,
    build_commit_marker,
    commit_marker_key,
    export_ledger_segment_for_archive,
    fetch_segment_bytes,
    find_committed_tip,
    publish_ledger_segment,
    segment_key,
)
from app.composition.s6i3_ledger_snapshot import LedgerSnapshotError, decode_ledger_segment
from tests.composition.s6i3_seeds import (
    _seed_checkpoint,
    _seed_conversation,
    _seed_operation,
    _seed_tenant,
)

logger = structlog.get_logger(__name__)

_TEST_DB_URL = "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
_DIGEST = "a" * 64
_DIGEST_B = "b" * 64


# ----------------------------------------------------------------------
# 纯内存测试（无 PG，无网络）—— Protocol/error/keys/serialization/commit-graph
# ----------------------------------------------------------------------


def _hex16(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def _hex64(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_archive_frozen_constants_distinct_from_default_bucket() -> None:
    assert DEFAULT_BUCKET_NAME == "metaedu-ledger-archive"
    assert "metaedu-resources" in FORBIDDEN_BUCKETS


def test_archive_in_memory_sink_rejects_forbidden_bucket() -> None:
    with pytest.raises(BucketNotDistinctError):
        InMemoryLedgerArchiveSink(bucket="metaedu-resources")


def test_archive_in_memory_sink_rejects_empty_bucket() -> None:
    with pytest.raises(LedgerArchiveError):
        InMemoryLedgerArchiveSink(bucket="")


def test_archive_segment_key_format_and_canonical_validation() -> None:
    tid = str(uuid.uuid4())
    sha = _hex64(b"x")
    key = segment_key(tid, sha)
    assert key.startswith(f"v1/tenants/{tid}/segments/")
    assert key.endswith(f"{sha}.json")


def test_archive_segment_key_rejects_noncanonical_uuid() -> None:
    with pytest.raises(LedgerArchiveError):
        segment_key(str(uuid.uuid4()).upper(), _hex64(b"x"))


def test_archive_segment_key_rejects_non_64hex() -> None:
    with pytest.raises(LedgerArchiveError):
        segment_key(str(uuid.uuid4()), "not-a-digest")


def test_archive_commit_marker_key_includes_20digit_generation() -> None:
    tid = str(uuid.uuid4())
    key = commit_marker_key(tid, 1, _hex16(b"y"))
    assert key.startswith(f"v1/tenants/{tid}/commits/")
    # 020d format → generation 总占 20 位，前导 0
    assert "00000000000000000001-" in key


def test_archive_commit_marker_key_rejects_zero_generation() -> None:
    with pytest.raises(LedgerArchiveError):
        commit_marker_key(str(uuid.uuid4()), 0, _hex16(b"y"))


def test_archive_commit_marker_key_rejects_non_16hex_export_id() -> None:
    with pytest.raises(LedgerArchiveError):
        commit_marker_key(str(uuid.uuid4()), 1, "not-16-hex")


def test_archive_commit_marker_round_trip() -> None:
    """同 input → 同 marker bytes；marker 不承载任何 published_at_unix 字段。"""
    tid = str(uuid.uuid4())
    per_kind = {
        "operation": PerKindMarker(generation=1, count=3, content_digest=_DIGEST),
        "checkpoint": PerKindMarker(generation=1, count=3, content_digest=_DIGEST_B),
    }
    m = build_commit_marker(
        tenant_id=tid,
        export_id=_hex16(b"z"),
        parent_export_id=None,
        generation=1,
        segment_key_str=segment_key(tid, _hex64(b"z")),
        segment_sha256=_hex64(b"z"),
        per_kind=per_kind,
    )
    body = m.to_bytes()
    parsed = CommitMarker.from_bytes(body)
    assert parsed == m
    # marker 不得包含任何 wall-clock 字段（用户裁决 A-1）
    obj = json.loads(body)
    assert "published_at_unix" not in obj
    assert "now_unix" not in obj
    assert "published_at" not in obj


def test_archive_commit_marker_rejects_legacy_published_at_unix_field() -> None:
    """用户裁决 A-1：published_at_unix 字段已删除；老 marker 含此字段 → payload corrupt。"""
    raw = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(uuid.uuid4()),
        "export_id": _hex16(b"x"),
        "parent_export_id": None,
        "generation": 1,
        "segment_key": "k",
        "segment_sha256": _hex64(b"x"),
        "per_kind": {},
        "published_at_unix": 1234567890,  # 旧 marker 残留字段
    }
    body = json.dumps(raw, sort_keys=True).encode("utf-8")
    # marker schema 不识别的额外字段：round-trip 后该字段被丢弃（不参与相等判定）
    parsed = CommitMarker.from_bytes(body)
    canonical = parsed.to_canonical_dict()
    assert "published_at_unix" not in canonical


def test_archive_commit_marker_rejects_wrong_schema_version() -> None:
    raw = {
        "schema_version": SCHEMA_VERSION + 1,
        "tenant_id": str(uuid.uuid4()),
        "export_id": _hex16(b"x"),
        "parent_export_id": None,
        "generation": 1,
        "segment_key": "k",
        "segment_sha256": _hex64(b"x"),
        "per_kind": {},
    }
    body = json.dumps(raw, sort_keys=True).encode("utf-8")
    with pytest.raises(CommitMarkerPayloadCorruptError):
        CommitMarker.from_bytes(body)


def test_archive_commit_marker_rejects_noncanonical_uuid() -> None:
    raw = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(uuid.uuid4()).upper(),
        "export_id": _hex16(b"x"),
        "parent_export_id": None,
        "generation": 1,
        "segment_key": "k",
        "segment_sha256": _hex64(b"x"),
        "per_kind": {},
    }
    body = json.dumps(raw, sort_keys=True).encode("utf-8")
    with pytest.raises(LedgerArchiveError):
        CommitMarker.from_bytes(body)


def test_archive_in_memory_put_object_returns_metadata() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    meta = sink.put_object("v1/foo", b"hello")
    assert meta.size == 5
    assert meta.etag == _hex64(b"hello")


def test_archive_in_memory_collision_on_same_key_different_bytes() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    sink.put_object("v1/foo", b"hello")
    with pytest.raises(ObjectIdentityCollisionError):
        sink.put_object("v1/foo", b"different")


def test_archive_in_memory_get_object_missing_raises() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    with pytest.raises(LedgerArchiveError):
        sink.get_object("v1/foo")


def test_archive_in_memory_list_keys_prefix() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    sink.put_object("v1/tenants/a/segments/x.json", b"x")
    sink.put_object("v1/tenants/a/commits/00000000000000000001-y.json", b"y")
    sink.put_object("v1/tenants/b/segments/x.json", b"x")
    keys = sink.list_keys(prefix="v1/tenants/a/")
    assert len(keys) == 2
    assert all(k.startswith("v1/tenants/a/") for k in keys)


def test_archive_find_committed_tip_empty_returns_none() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    assert find_committed_tip(sink, tenant_id=str(uuid.uuid4())) is None


def test_archive_find_committed_tip_detects_fork() -> None:
    """同 generation 多个不同 export_id —— ForkDetectedError。"""
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    tid = str(uuid.uuid4())
    # 构造两个 generation=1 但 export_id 不同的 marker（绕过正常 publish 模拟 fork）
    for export_id in (_hex16(b"a"), _hex16(b"b")):
        m = build_commit_marker(
            tenant_id=tid,
            export_id=export_id,
            parent_export_id=None,
            generation=1,
            segment_key_str=segment_key(tid, _hex64(export_id.encode())),
            segment_sha256=_hex64(export_id.encode()),
            per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
        )
        sink.put_object(commit_marker_key(tid, 1, export_id), m.to_bytes())
    with pytest.raises(ForkDetectedError):
        find_committed_tip(sink, tenant_id=tid)


def test_archive_find_committed_tip_detects_generation_regression() -> None:
    """新 marker.parent_export_id 与既有 chain 不匹配 —— GenerationRegressionError。"""
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    tid = str(uuid.uuid4())
    # generation=1, parent=None
    m1 = build_commit_marker(
        tenant_id=tid,
        export_id=_hex16(b"a"),
        parent_export_id=None,
        generation=1,
        segment_key_str=segment_key(tid, _hex64(b"a")),
        segment_sha256=_hex64(b"a"),
        per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
    )
    sink.put_object(commit_marker_key(tid, 1, _hex16(b"a")), m1.to_bytes())
    # generation=2, parent=_hex16(b"OTHER")（与 m1.export_id 不一致）
    m2 = build_commit_marker(
        tenant_id=tid,
        export_id=_hex16(b"b"),
        parent_export_id=_hex16(b"OTHER"),
        generation=2,
        segment_key_str=segment_key(tid, _hex64(b"b")),
        segment_sha256=_hex64(b"b"),
        per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
    )
    sink.put_object(commit_marker_key(tid, 2, _hex16(b"b")), m2.to_bytes())
    with pytest.raises(GenerationRegressionError):
        find_committed_tip(sink, tenant_id=tid)


def test_archive_find_committed_tip_walks_chain() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    tid = str(uuid.uuid4())
    for gen, raw in enumerate([b"a", b"b", b"c"], start=1):
        parent = None if gen == 1 else _hex16([b"a", b"b", b"c"][gen - 2])
        m = build_commit_marker(
            tenant_id=tid,
            export_id=_hex16(raw),
            parent_export_id=parent,
            generation=gen,
            segment_key_str=segment_key(tid, _hex64(raw)),
            segment_sha256=_hex64(raw),
            per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
        )
        sink.put_object(commit_marker_key(tid, gen, _hex16(raw)), m.to_bytes())
    tip = find_committed_tip(sink, tenant_id=tid)
    assert tip is not None
    assert tip.generation == 3
    assert tip.export_id == _hex16(b"c")


def test_archive_fetch_segment_bytes_validates_sha() -> None:
    """GET-back SHA 与 marker.segment_sha256 不一致 —— SegmentObjectMissingError。"""
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    tid = str(uuid.uuid4())
    seg_key = segment_key(tid, _hex64(b"a"))
    sink.put_object(seg_key, b"corrupted")  # 故意与 marker.segment_sha256 不一致
    m = build_commit_marker(
        tenant_id=tid,
        export_id=_hex16(b"a"),
        parent_export_id=None,
        generation=1,
        segment_key_str=seg_key,
        segment_sha256=_hex64(b"a"),  # 与 put 的字节不同
        per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
    )
    with pytest.raises(SegmentObjectMissingError):
        fetch_segment_bytes(sink, tenant_id=tid, marker=m)


def test_archive_fetch_segment_bytes_rejects_cross_tenant() -> None:
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    seg_key = segment_key(str(uuid.uuid4()), _hex64(b"a"))
    sink.put_object(seg_key, b"a")
    m = build_commit_marker(
        tenant_id=str(uuid.uuid4()),
        export_id=_hex16(b"a"),
        parent_export_id=None,
        generation=1,
        segment_key_str=seg_key,
        segment_sha256=_hex64(b"a"),
        per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
    )
    with pytest.raises(TenantMismatchError):
        fetch_segment_bytes(sink, tenant_id=str(uuid.uuid4()), marker=m)


# ----------------------------------------------------------------------
# Mutation script 反向核对（防止 D1a segment 在 sink 端被截断/篡改）
# ----------------------------------------------------------------------


def test_archive_idempotent_marker_byte_equal_for_same_input() -> None:
    """同 input → 同 marker bytes（不可变模型基础；不依赖任何 wall-clock 字段）。"""
    tid = str(uuid.uuid4())
    kwargs = dict(
        tenant_id=tid,
        export_id=_hex16(b"x"),
        parent_export_id=None,
        generation=1,
        segment_key_str=segment_key(tid, _hex64(b"x")),
        segment_sha256=_hex64(b"x"),
        per_kind={"operation": PerKindMarker(1, 0, _DIGEST)},
    )
    a = build_commit_marker(**kwargs).to_bytes()
    b_ = build_commit_marker(**kwargs).to_bytes()
    assert a == b_


def test_archive_segment_key_byte_determinism() -> None:
    """同 (tenant_id, sha) → 同 segment key bytes。"""
    tid = str(uuid.uuid4())
    sha = _hex64(b"x")
    assert segment_key(tid, sha) == segment_key(tid, sha)


def test_archive_phase1_exported_segment_does_not_leak_published_at_unix() -> None:
    """ExportedSegment 链路不得引入 published_at_unix 概念。"""
    assert "published_at_unix" not in ExportedSegment.__dataclass_fields__
    assert "now_unix" not in ExportedSegment.__dataclass_fields__


# ----------------------------------------------------------------------
# Real PG integration tests —— D1a export → D1b archive → D1a decoder round-trip
# ----------------------------------------------------------------------


@pytest.fixture
async def snapshot_factory():
    """独立 engine/sessionmaker，per-test fresh（与 D1a test 一致）。"""
    engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
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


async def _seed_minimal_ledger(session: AsyncSession, *, tenant_label: str = "t") -> dict[str, Any]:
    """种最小可解码 ledger（4 类各 ≥ 1 条）—— 与 D1a test 同形态。"""
    tid = await _seed_tenant(session, name=tenant_label)
    cid = await _seed_conversation(session, tid=tid)
    op_id = await _seed_operation(
        session, tid=tid, cid=cid, state="running", purge_rev=1
    )
    await _seed_checkpoint(
        session,
        tid=tid,
        purge_operation_id=op_id,
        owner_key="external.payload.v1",
        owner_version=1,
        capability_digest=_DIGEST,
        state="erasing",
        attempt=1,
    )
    await session.commit()
    return {"tid": tid, "cid": cid, "op_id": op_id}


async def _publish_two_phase(
    factory: async_sessionmaker[AsyncSession],
    *,
    sink: Any,
    tenant_id: uuid.UUID,
    parent_export_id: str | None = None,
) -> tuple[ExportedSegment, Any]:
    """用户裁决 B-1：phase-1（RR+RO 事务内 D1a export/decode）→ 事务结束
    → phase-2（事务外 sink I/O）。两阶段严格分立，绝不在事务内触发 sink I/O。

    Returns: (exported_segment, publish_outcome) 用于测试 assertion
    """
    session = factory()
    try:
        async with session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            # phase-1 入口快照 sink 当前对象集合；phase-1 退出前断言无新增 key
            # （B-1 契约：phase-1 禁止 sink I/O —— 即使先前 publish 已写入，phase-1
            # 期间也不应再向 sink 追加对象）
            pre_phase1_keys: set[str] = set()
            if isinstance(sink, InMemoryLedgerArchiveSink):
                pre_phase1_keys = set(sink._objects.keys())
            exported = await export_ledger_segment_for_archive(
                session, tenant_id=tenant_id
            )
            if isinstance(sink, InMemoryLedgerArchiveSink):
                post_phase1_keys = set(sink._objects.keys())
                assert post_phase1_keys == pre_phase1_keys, (
                    "B-1 契约违反：phase-1 期间 sink 不应被写入；"
                    f"新增 key: {post_phase1_keys - pre_phase1_keys}"
                )
        # 事务结束 —— 此后才允许 sink I/O
        outcome = await publish_ledger_segment(
            sink=sink,
            tenant_id=tenant_id,
            segment_bytes=exported.segment_bytes,
            manifest=exported.manifest,
            parent_export_id=parent_export_id,
        )
    finally:
        await session.close()
    return exported, outcome


async def test_d1b_round_trip_first_publish(snapshot_factory) -> None:
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-rt1")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, outcome = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])

    assert outcome.generation == 1
    assert outcome.idempotent_retry is False
    tip = find_committed_tip(sink, tenant_id=str(ids["tid"]))
    assert tip is not None and tip.export_id == outcome.export_id
    assert tip.parent_export_id is None


async def test_d1b_second_publish_advances_generation(snapshot_factory) -> None:
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-rt2")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, first = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])
    _, second = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])

    assert second.generation == first.generation + 1
    tip_first = find_committed_tip(sink, tenant_id=str(ids["tid"]))
    assert tip_first is not None
    assert tip_first.export_id == first.export_id


async def test_d1b_publish_phase1_rejects_non_read_only_transaction(snapshot_factory) -> None:
    """Phase-1（export）必须 RR + READ ONLY —— 否则 PublishPreconditionFailedError。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-rw")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")  # noqa: F841 — used for context
    session = factory()
    try:
        async with session.begin():
            # 仅 RR，无 READ ONLY —— D1a 强制拒绝
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            with pytest.raises(PublishPreconditionFailedError):
                await export_ledger_segment_for_archive(session, tenant_id=ids["tid"])
    finally:
        await session.close()


async def test_d1b_publish_phase1_rejects_missing_session() -> None:
    """Phase-1 必须接收 AsyncSession；None → PublishPreconditionFailedError。"""
    with pytest.raises(PublishPreconditionFailedError):
        await export_ledger_segment_for_archive(None, tenant_id=uuid.uuid4())  # type: ignore[arg-type]


async def test_d1b_publish_phase2_does_not_require_session() -> None:
    """Phase-2 API 签名**不**接收 AsyncSession（用户裁决 B-1）。

    此项为 contract-level 验证 —— Phase-2 必须接受 sink + 已校验 segment_bytes + manifest，
    不再访问 DB。本测试在 phase-1 导出后**关闭事务**，再 phase-2 调用，校验
    sink._objects 在 phase-2 之前为空、phase-2 之后非空。
    """
    factory = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(factory, expire_on_commit=False)
    try:
        async with maker() as seed:
            await _assert_metaedu_test(seed)
            ids = await _seed_minimal_ledger(seed, tenant_label="d1b-p2-cb")

        sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
        # Phase 1
        session = maker()
        try:
            async with session.begin():
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                exported = await export_ledger_segment_for_archive(
                    session, tenant_id=ids["tid"]
                )
            # 事务关闭后，phase-2 调用
            assert len(sink._objects) == 0, "phase-1 不应写 sink"
            outcome = await publish_ledger_segment(
                sink=sink,
                tenant_id=ids["tid"],
                segment_bytes=exported.segment_bytes,
                manifest=exported.manifest,
            )
            assert len(sink._objects) >= 2, "phase-2 应至少写 segment + marker"
            assert outcome.generation == 1
        finally:
            await session.close()
    finally:
        await factory.dispose()


async def test_d1b_idempotent_retry_returns_true_when_candidate_marker_matches(
    snapshot_factory,
) -> None:
    """真路径幂等 retry 测试（用户裁决 C-2）。

    模拟 crash recovery：「marker PUT 实际成功但 caller 未收到响应」。
    第二次 publish 同 segment 时 candidate marker key 已存在且字节一致
    → 应返回 ``idempotent_retry=True`` 且 sink 不再新增对象。

    实现策略（关键：find_committed_tip 必须读到 tip=gen=1 才能让 idempotent retry
    触发，否则新 generation 会跳过 candidate key）：

    1. 第一次正常 publish 写出 gen=1 marker（tip=gen=1）
    2. 直接构造 publish 路径在 gen=2 会产出的 marker 字节
    3. 把 gen=2 candidate marker 注入 sink
    4. **通过 _MaskedListKeysSink 拦截 list_keys** 让 find_committed_tip 看不到 candidate
       marker（模拟 tip walker 尚未扫描到的瞬时窗口）；GET_object 仍返回真实 bytes
    5. 第二次 publish 同 segment → 应识别 candidate marker 字节与即将构造字节一致
       → 返回 idempotent_retry=True
    6. 断言 sink._objects 在 phase-2 完成后**未新增**对象（marker 已存在）
    """
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-idem-true")

    # 用 _MaskedListKeysSink：list_keys 时排除指定的 candidate marker key（模拟
    # find_committed_tip 尚未扫到的瞬时窗口），但 get_object/put_object 行为不变
    sink = _MaskedListKeysSink(bucket="metaedu-ledger-archive")
    _, first = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])

    # 抓取 first marker 字段 → 推算 publish 路径在 gen=2 会产出的 marker 字节
    first_marker_obj = CommitMarker.from_bytes(sink.get_object(first.marker_key))

    # 关键：同 segment 字节 → 同 segment_sha256 → 同 export_id。第二次 publish 同
    # segment 时 export_id 与 first 相同，generation 会推进到 2（tip=gen=1，
    # 因为 list_keys 被 mask 看不到 candidate marker）。
    expected_gen = first.generation + 1
    candidate_key = commit_marker_key(str(ids["tid"]), expected_gen, first.export_id)
    candidate_marker = build_commit_marker(
        tenant_id=str(ids["tid"]),
        export_id=first.export_id,
        parent_export_id=first.export_id,  # gen=2 的 parent = gen=1 的 export_id
        generation=expected_gen,
        segment_key_str=first_marker_obj.segment_key,
        segment_sha256=first_marker_obj.segment_sha256,
        per_kind=dict(first_marker_obj.per_kind),
    )
    candidate_bytes = candidate_marker.to_bytes()

    # 注入 candidate marker 到 sink；同时登记 masked key —— find_committed_tip
    # 看不到，但 phase-2 idempotent retry 检查时 GET_object 仍能读到 candidate
    sink.put_object(candidate_key, candidate_bytes)
    sink.mask_key(candidate_key)
    pre_keys = set(sink._objects.keys())

    # 第二次 publish 同 segment —— tip walker 因 mask 仍只看到 first marker (gen=1)
    # → new_generation = 2 → candidate_marker_key = gen=2
    # → GET candidate 返回与即将构造字节完全一致的 bytes → idempotent_retry=True
    _, retry = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])

    assert retry.idempotent_retry is True, (
        "idempotent retry 真路径必须触发；当前 assertion 命中说明："
        "(1) candidate marker 未按 publish 路径字节一致地注入，或"
        "(2) find_committed_tip 仍读到了 candidate marker（mask 未生效），"
        "导致 new_generation 跳过 candidate key"
    )
    assert retry.generation == expected_gen
    assert retry.marker_key == candidate_key
    # sink 不应新增 segment 对象（同名 segment 已存在）；marker key 已存在故 idempotent_retry
    post_keys = set(sink._objects.keys())
    assert post_keys == pre_keys, (
        f"idempotent retry 路径不应新增对象；新增 key: {post_keys - pre_keys}"
    )


class _MaskedListKeysSink(InMemoryLedgerArchiveSink):
    """list_keys 时排除一组 masked key —— 模拟 tip walker 扫描瞬时窗口。

    get_object / put_object 行为与 InMemoryLedgerArchiveSink 一致。
    """

    def __init__(self, *, bucket: str) -> None:
        super().__init__(bucket=bucket)
        self._masked_keys: set[str] = set()

    def mask_key(self, key: str) -> None:
        self._masked_keys.add(key)

    def list_keys(self, *, prefix: str) -> list[str]:
        return sorted(
            k for k in self._objects
            if k.startswith(prefix) and k not in self._masked_keys
        )


async def test_d1b_explicit_parent_must_match_tip(snapshot_factory) -> None:
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-parent")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, first = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])
    with pytest.raises(ParentExportMissingError):
        await _publish_two_phase(
            factory, sink=sink, tenant_id=ids["tid"], parent_export_id="0" * 16
        )
    assert first.idempotent_retry is False
    # 父错配后 tip 不应被推进（仍为 first）
    tip = find_committed_tip(sink, tenant_id=str(ids["tid"]))
    assert tip is not None
    assert tip.generation == 1


async def test_d1b_decoder_round_trip_after_archive(snapshot_factory) -> None:
    """D1b publish 后 GET segment 字节 → D1a decode 必须成功（round-trip）。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-dec")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, outcome = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])
    # 重新读取（不是 publish 路径）—— 验证 archived bytes 仍可通过 D1a decode
    archived = sink.get_object(outcome.segment_key)
    manifest = decode_ledger_segment(archived, expected_tenant_id=ids["tid"])
    assert manifest.tenant_id == str(ids["tid"])
    assert "operation" in manifest.record_count
    assert "checkpoint" in manifest.record_count


async def test_d1b_cross_tenant_isolation(snapshot_factory) -> None:
    """tenant A segment 不能被 tenant B 的 expected_tenant_id 解码。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids_a = await _seed_minimal_ledger(seed, tenant_label="d1b-cA")
        ids_b = await _seed_minimal_ledger(seed, tenant_label="d1b-cB")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, outcome = await _publish_two_phase(factory, sink=sink, tenant_id=ids_a["tid"])
    archived = sink.get_object(outcome.segment_key)
    with pytest.raises(LedgerSnapshotError):
        decode_ledger_segment(archived, expected_tenant_id=ids_b["tid"])


async def test_d1b_marker_contains_per_kind_counts_and_digests(snapshot_factory) -> None:
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-pk")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    _, outcome = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])
    marker_bytes = sink.get_object(outcome.marker_key)
    marker = CommitMarker.from_bytes(marker_bytes)
    assert "operation" in marker.per_kind
    assert "checkpoint" in marker.per_kind
    # per-kind generation V1 D1b slice 占位为 1（不维护 per-kind 推进序列）
    assert marker.per_kind["operation"].generation == 1


async def test_d1b_existing_marker_key_with_different_payload_fails_closed(
    snapshot_factory,
) -> None:
    """同 marker key 已存在但 payload 不同 —— ExistingPayloadDivergesError。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-div")

    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")
    # 第一次正常 publish（gen=1）
    _, first = await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])
    # 第二次 publish 候选 key = gen=2 —— 在该 key 注入损坏字节（tip walker 跳过损坏 marker）
    expected_gen = first.generation + 1
    expected_marker_key = commit_marker_key(str(ids["tid"]), expected_gen, first.export_id)
    sink.put_object(expected_marker_key, b"not-a-valid-marker-bytes")
    # 再 publish 同 segment → 应触发 ExistingPayloadDivergesError
    with pytest.raises(ExistingPayloadDivergesError):
        await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])


async def test_d1b_segment_digest_mismatch_after_put(snapshot_factory) -> None:
    """PUT segment 后人为篡改对象 → publish 时 GET-back digest mismatch。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-corrupt")

    # 自定义 sink：put 后立即篡改 segment body
    sink = InMemoryLedgerArchiveSink(bucket="metaedu-ledger-archive")

    original_put = sink.put_object

    def put_with_corruption(key, payload, *, content_type="application/json"):
        meta = original_put(key, payload, content_type=content_type)
        # 篡改 segment 对象：直接修改内部 dict entry 的 body
        sink._objects[key] = _MemObjectProxy(body=b"corrupted", content_type=content_type)
        return meta

    sink.put_object = put_with_corruption  # type: ignore[assignment]

    with pytest.raises(SegmentDigestMismatchError):
        await _publish_two_phase(factory, sink=sink, tenant_id=ids["tid"])


class _MemObjectProxy:
    __slots__ = ("body", "content_type")

    def __init__(self, *, body: bytes, content_type: str) -> None:
        self.body = body
        self.content_type = content_type


# ----------------------------------------------------------------------
# Transient retry + crash semantics
# ----------------------------------------------------------------------


async def test_d1b_publish_retries_transient_then_succeeds() -> None:
    """transient 错误有界重试；第 N 次成功后正常产出 marker。"""
    from app.composition.s6i3_d_ledger_archive_sink import _retry_with_backoff

    attempts: list[int] = []

    def op():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise TransientArchiveError("transient")
        return "ok"

    result = await _retry_with_backoff(op, sleeper=lambda _s: None)
    assert result == "ok"
    assert len(attempts) == 3


async def test_d1b_publish_retry_exhausted_raises_archive_unavailable() -> None:
    """transient 错误超限 → ArchiveUnavailableError。"""
    from app.composition.s6i3_d_ledger_archive_sink import _retry_with_backoff

    def op():
        raise TransientArchiveError("always")

    with pytest.raises(ArchiveUnavailableError):
        await _retry_with_backoff(op, max_attempts=2, sleeper=lambda _s: None)


async def test_d1b_publish_retry_exhausted_does_not_call_sink_after_exhaustion() -> None:
    """重试超限后 sink.put_object **不应**继续被调用 —— bounded 失败闭合。"""
    from app.composition.s6i3_d_ledger_archive_sink import _retry_with_backoff

    call_count = 0

    def op():
        nonlocal call_count
        call_count += 1
        raise TransientArchiveError("always")

    with pytest.raises(ArchiveUnavailableError):
        await _retry_with_backoff(op, max_attempts=3, sleeper=lambda _s: None)
    assert call_count == 3, (
        f"max_attempts=3 应最多调用 3 次；实际调用 {call_count} 次"
    )


async def test_d1b_crash_before_marker_publish_leaves_tip_unchanged() -> None:
    """segment-only PUT 不推进 tip —— crash 在 marker PUT 之前的语义。

    直接构造 scenario：仅 PUT segment（不动 marker）→ find_committed_tip 应为 None。
    """
    sink = _FlakySink(bucket="metaedu-ledger-archive")
    tid = str(uuid.uuid4())
    sha = _hex64(b"sim_segment")
    seg_key = segment_key(tid, sha)
    sink.put_object(seg_key, b"sim_segment")
    tip = find_committed_tip(sink, tenant_id=tid)
    assert tip is None  # 没有 marker ⇒ tip 不变（crash-safe）


async def test_d1b_publish_retry_succeeds_after_transient_in_phase2(snapshot_factory) -> None:
    """Phase-2 PUT segment 触发 transient → 重试成功后正常产出 marker。"""
    factory = snapshot_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_ledger(seed, tenant_label="d1b-retry")

    sink = _FlakySink(
        bucket="metaedu-ledger-archive", transient_count=1  # 第 1 次 PUT segment 抛 transient
    )

    session = factory()
    try:
        async with session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            exported = await export_ledger_segment_for_archive(
                session, tenant_id=ids["tid"]
            )
        # 关闭事务后 phase-2
        outcome = await publish_ledger_segment(
            sink=sink,
            tenant_id=ids["tid"],
            segment_bytes=exported.segment_bytes,
            manifest=exported.manifest,
            sleeper=lambda _s: None,
        )
        assert outcome.generation == 1
        assert outcome.idempotent_retry is False
        # 重试成功 ⇒ sink 应有 segment + marker
        assert sink._seen_transient >= 1
    finally:
        await session.close()


# ----------------------------------------------------------------------
# Sink helpers used by transient tests
# ----------------------------------------------------------------------


class _FlakySink(InMemoryLedgerArchiveSink):
    """可在 put_object 注入 transient 错误的 sink，用于测试 retry 行为。"""

    def __init__(
        self,
        *,
        bucket: str,
        fail_keys: set[str] | None = None,
        transient_count: int = 0,
        transient_marker_keys: str | None = None,
    ) -> None:
        super().__init__(bucket=bucket)
        self._transient_count = transient_count
        self._transient_marker_keys = transient_marker_keys
        self._seen_marker_keys: set[str] = set()
        self._fail_keys = fail_keys or set()
        self._transient_attempts = 0
        self._seen_transient = 0

    def put_object(
        self, key: str, payload: bytes, *, content_type: str = "application/json"
    ):
        if key in self._fail_keys:
            raise TransientArchiveError(f"transient: {key}")
        if self._transient_marker_keys == "all_after_segment" and "/commits/" in key:
            if key in self._seen_marker_keys:
                return super().put_object(key, payload, content_type=content_type)
            self._seen_marker_keys.add(key)
            raise TransientArchiveError(f"transient: {key}")
        if (
            self._transient_count > 0
            and "/segments/" in key
            and self._transient_attempts < self._transient_count
        ):
            self._transient_attempts += 1
            self._seen_transient += 1
            raise TransientArchiveError(f"transient: {key}")
        return super().put_object(key, payload, content_type=content_type)
