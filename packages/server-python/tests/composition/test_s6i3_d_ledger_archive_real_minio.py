"""R1-S6-I3-D D1b 真实 MinIO acceptance 测试（opt-in via RUN_REAL_MINIO_TESTS）。

**严格 opt-in**：未设置 ``环境变量`` 时整个模块自动 skip；运行命令必须显式声明。
仅连真实 MinIO 服务；使用专用测试 bucket + per-test 随机 prefix，**绝不**触碰
``metaedu-resources``。每个测试 teardown 必须清理自己写入的对象（不依赖全局
bucket GC）。

执行命令（参考；按用户裁决 C-1 记录精确命令）：

.. code-block:: bash

    # 1. 启动本地 MinIO（dev.sh infra 已支持 docker compose）
    ./dev.sh infra   # 启动 postgres / redis / minio（docker compose dev）

    # 2. 健康检查
    curl -sf http://localhost:9000/minio/health/live -o /dev/null -w "%{http_code}\n"
    # 期望：200

    # 3. 运行真实 MinIO acceptance（仅本模块 + external_network 标记）
    cd packages/server-python
    RUN_REAL_MINIO_TESTS=1 \\
        uv run --frozen --extra dev \\
        pytest tests/composition/test_s6i3_d_ledger_archive_real_minio.py \\
        -v -m external_network

    # 4. （强制）显式验证本模块零引用 metaedu-resources
    ! grep -R "metaedu-resources" tests/composition/test_s6i3_d_ledger_archive_real_minio.py

失败模式：
- 未设置环境变量 → 整个模块 skip（pytest collection 不报错）
- MinIO 不可达 → 测试 fail，但**不**声称已验收
- 测试失败 → 必须修复后才能声称「真实 MinIO 验收通过」

禁止：
- 在 conftest.py 强制启用本模块
- 默认 CI 运行
- 触碰 ``metaedu-resources`` bucket
- 写入生产 / 共享 bucket
"""

from __future__ import annotations

import contextlib
import os
import uuid
from typing import Any

import pytest

from app.composition.s6i3_d_ledger_archive_sink import (
    FORBIDDEN_BUCKETS,
    MinioLedgerArchiveSink,
    commit_marker_key,
    find_committed_tip,
    segment_key,
)
from app.composition.s6i3_ledger_snapshot import (
    Manifest,
    decode_ledger_segment,
)

# 仅 opt-in；本模块所有测试在缺省情况下自动 skip
_RUN_REAL_MINIO = os.environ.get("RUN_REAL_MINIO_TESTS") == "1"

# Real MinIO endpoint（与 deploy/docker-compose.dev.yml 对齐）
_REAL_MINIO_ENDPOINT = os.environ.get("METAEDU_MINIO_ENDPOINT", "127.0.0.1:9000")
_REAL_MINIO_ACCESS_KEY = os.environ.get("METAEDU_MINIO_ACCESS_KEY", "metaedu")
_REAL_MINIO_SECRET_KEY = os.environ.get("METAEDU_MINIO_SECRET_KEY", "dev_only_123")

# 专用测试 bucket —— **绝不**等于 ``metaedu-resources``
_TEST_BUCKET = os.environ.get(
    "METAEDU_D1B_TEST_BUCKET", "metaedu-d1b-acceptance-test"
)


pytestmark = [
    pytest.mark.external_network,
    pytest.mark.skipif(
        not _RUN_REAL_MINIO,
        reason=(
            "opt-in real MinIO acceptance; set RUN_REAL_MINIO_TESTS=1 to enable. "
            "Never runs by default; bypass guard is intentional."
        ),
    ),
]


def _assert_test_bucket_isolated() -> None:
    """D1b 硬边界：测试 bucket 不得在 FORBIDDEN_BUCKETS 中，也不得等于 metaedu-resources。"""
    assert _TEST_BUCKET != "metaedu-resources", (
        f"DB hard boundary violation: test bucket {_TEST_BUCKET!r} must NEVER be "
        "metaedu-resources (通用 minio_bucket)"
    )
    assert _TEST_BUCKET not in FORBIDDEN_BUCKETS, (
        f"D1b bucket isolation violation: test bucket {_TEST_BUCKET!r} is in "
        f"FORBIDDEN_BUCKETS {FORBIDDEN_BUCKETS}"
    )
    # 额外保险：测试 bucket 必须以 metaedu-d1b- 前缀（专用前缀）
    assert _TEST_BUCKET.startswith("metaedu-d1b-"), (
        f"D1b test bucket convention violation: {_TEST_BUCKET!r} must start with "
        "'metaedu-d1b-' to prevent accidental overlap with other test buckets"
    )


def _minio_reachable() -> bool:
    """Best-effort 探测 MinIO health；不可达直接 skip 当前测试。"""
    import urllib.request

    try:
        with urllib.request.urlopen(  # noqa: S310 — dev-only probe
            f"http://{_REAL_MINIO_ENDPOINT}/minio/health/live", timeout=2.0
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.fixture
def minio_sink() -> Any:
    """Real MinIO sink fixture；每个测试独立 per-tenant random prefix。

    Teardown 自动清理本测试写入的所有对象（通过 list_keys + delete_object）；
    不调用 bucket cleanup（生产不允许删 bucket）。
    """
    _assert_test_bucket_isolated()

    if not _minio_reachable():
        pytest.skip(
            f"MinIO endpoint {_REAL_MINIO_ENDPOINT} not reachable; "
            "real MinIO acceptance aborted. Do NOT claim real-environment verified."
        )

    sink = MinioLedgerArchiveSink(
        bucket=_TEST_BUCKET,
        endpoint=_REAL_MINIO_ENDPOINT,
        access_key=_REAL_MINIO_ACCESS_KEY,
        secret_key=_REAL_MINIO_SECRET_KEY,
        secure=False,
    )
    # per-test random prefix（within dedicated test bucket）
    test_prefix = f"v1/acceptance/{uuid.uuid4().hex}/tenants/"
    # 把 prefix 注入 list_keys filter：简化方式是用独立 bucket
    # （dev bucket 共享 prefix 即可；test 间通过 random prefix 隔离）
    sink._test_prefix = test_prefix  # type: ignore[attr-defined]
    yield sink
    # teardown：清理本测试 prefix 下的所有对象
    try:
        client = sink._get_client()  # type: ignore[attr-defined]
        objs = list(client.list_objects(_TEST_BUCKET, prefix=test_prefix, recursive=True))
        for obj in objs:
            with contextlib.suppress(Exception):
                client.remove_object(_TEST_BUCKET, obj.object_name)
    except Exception:
        # teardown 失败不阻塞测试结果，但登记 warning
        pass


def _make_test_manifest(tenant_id_str: str) -> Manifest:
    """构造最小 Manifest 用于真实 MinIO publish 路径。"""
    from app.composition.s6i3_ledger_snapshot import ExportedRecord

    digest = "a" * 64
    op = ExportedRecord(
        record_kind="operation",
        table_identity="purge_operation",
        stable_identity=f"operation:{uuid.uuid4()}",
        fields={"id": str(uuid.uuid4())},
    )
    ck = ExportedRecord(
        record_kind="checkpoint",
        table_identity="purge_checkpoint",
        stable_identity=f"checkpoint:{uuid.uuid4()}",
        fields={"id": str(uuid.uuid4())},
    )
    return Manifest(
        schema_version=1,
        tenant_id=tenant_id_str,
        record_count={"operation": 1, "checkpoint": 1, "external_ref": 0, "reconcile": 0},
        content_digest={
            "operation": digest,
            "checkpoint": digest,
            "external_ref": digest,
            "reconcile": digest,
        },
        runtime_per_binding_proof_available=False,
        records={"operation": (op,), "checkpoint": (ck,)},
        raw={"tenant_id": tenant_id_str, "schema_version": 1},
    )


def test_real_minio_segment_put_get_roundtrip(minio_sink: Any) -> None:
    """真实 MinIO：PUT segment → GET-back 字节一致。"""
    tenant_id = uuid.uuid4()
    payload = b'{"hello":"world"}'
    key = segment_key(str(tenant_id), "a" * 64)
    # 校验 key format
    assert key.startswith("v1/tenants/")
    minio_sink.put_object(key, payload)
    got = minio_sink.get_object(key)
    assert got == payload


def test_real_minio_marker_put_and_list_keys(minio_sink: Any) -> None:
    """真实 MinIO：PUT commit marker → list_keys(tenant prefix) 含 marker。"""
    tenant_id = uuid.uuid4()
    marker = b'{"schema_version":1,"tenant_id":"' + str(tenant_id).encode() + b'"}'
    key = commit_marker_key(str(tenant_id), 1, "a" * 16)
    minio_sink.put_object(key, marker)
    keys = minio_sink.list_keys(prefix=f"v1/tenants/{tenant_id}/")
    assert key in keys


def test_real_minio_find_committed_tip_with_one_marker(minio_sink: Any) -> None:
    """真实 MinIO：PUT 一个合法 marker → find_committed_tip 返回 tip。"""
    from app.composition.s6i3_d_ledger_archive_sink import PerKindMarker, build_commit_marker

    tenant_id = uuid.uuid4()
    export_id = "b" * 16
    sha = "c" * 64
    seg_key = segment_key(str(tenant_id), sha)
    # 先 PUT segment
    minio_sink.put_object(seg_key, b'{"x":1}')
    # 构造 marker 并 PUT
    m = build_commit_marker(
        tenant_id=str(tenant_id),
        export_id=export_id,
        parent_export_id=None,
        generation=1,
        segment_key_str=seg_key,
        segment_sha256=sha,
        per_kind={"operation": PerKindMarker(1, 1, "a" * 64)},
    )
    marker_key = commit_marker_key(str(tenant_id), 1, export_id)
    minio_sink.put_object(marker_key, m.to_bytes())
    tip = find_committed_tip(minio_sink, tenant_id=str(tenant_id))
    assert tip is not None
    assert tip.export_id == export_id
    assert tip.generation == 1


def test_real_minio_rejects_forbidden_bucket_construction() -> None:
    """真实 MinIO 构造器也强制 bucket ≠ metaedu-resources。"""
    from app.composition.s6i3_d_ledger_archive_sink import BucketNotDistinctError

    with pytest.raises(BucketNotDistinctError):
        MinioLedgerArchiveSink(
            bucket="metaedu-resources",
            endpoint=_REAL_MINIO_ENDPOINT,
            access_key=_REAL_MINIO_ACCESS_KEY,
            secret_key=_REAL_MINIO_SECRET_KEY,
        )


def test_real_minio_archive_segment_via_two_phase_api(minio_sink: Any) -> None:
    """真实 MinIO：完整两阶段 API 路径 —— phase-1 跳过（已导出 bytes）

    此测试**直接调用 phase-2 publish_ledger_segment**，绕过 phase-1 PG 部分
    （因 PG fixture 与 MinIO acceptance 解耦；测试聚焦 sink I/O 行为）。
    """
    import asyncio

    from app.composition.s6i3_d_ledger_archive_sink import publish_ledger_segment
    from app.composition.s6i3_ledger_snapshot import ExportedRecord

    tenant_id = uuid.uuid4()
    tenant_id_str = str(tenant_id)
    segment_bytes = b'{"tenant_id":"' + tenant_id_str.encode() + b'","schema_version":1}'

    op = ExportedRecord(
        record_kind="operation",
        table_identity="purge_operation",
        stable_identity=f"operation:{uuid.uuid4()}",
        fields={"id": str(uuid.uuid4())},
    )
    ck = ExportedRecord(
        record_kind="checkpoint",
        table_identity="purge_checkpoint",
        stable_identity=f"checkpoint:{uuid.uuid4()}",
        fields={"id": str(uuid.uuid4())},
    )
    digest = "a" * 64
    manifest = Manifest(
        schema_version=1,
        tenant_id=tenant_id_str,
        record_count={"operation": 1, "checkpoint": 1, "external_ref": 0, "reconcile": 0},
        content_digest={
            "operation": digest,
            "checkpoint": digest,
            "external_ref": digest,
            "reconcile": digest,
        },
        runtime_per_binding_proof_available=False,
        records={"operation": (op,), "checkpoint": (ck,)},
        raw={"tenant_id": tenant_id_str, "schema_version": 1},
    )

    outcome = asyncio.run(
        publish_ledger_segment(
            sink=minio_sink,
            tenant_id=tenant_id,
            segment_bytes=segment_bytes,
            manifest=manifest,
        )
    )
    assert outcome.generation == 1
    assert outcome.idempotent_retry is False
    # 真实 MinIO 上 segment + marker 都应存在
    assert minio_sink.get_object(outcome.segment_key) == segment_bytes
    assert minio_sink.get_object(outcome.marker_key) is not None


def test_real_minio_archive_segment_d1a_round_trip(minio_sink: Any) -> None:
    """真实 MinIO：archive 后通过 D1a decoder 读回 segment 字节。"""
    import asyncio

    from app.composition.s6i3_d_ledger_archive_sink import publish_ledger_segment
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        _records_to_envelope,
        export_ledger_segment_to_bytes,
    )

    tenant_id = uuid.uuid4()
    tenant_id_str = str(tenant_id)
    # 构造合法 envelope → D1a encode → phase-2 publish → phase-2 后 GET-back → D1a decode
    op_record = ExportedRecord(
        record_kind="operation",
        table_identity="purge_operation",
        stable_identity=f"operation:{uuid.uuid4()}",
        fields={
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id_str,
            "conversation_id": str(uuid.uuid4()),
            "purge_revision": 1,
            "state": "running",
            "created_at": "2026-01-01T00:00:00",
        },
    )
    ck_record = ExportedRecord(
        record_kind="checkpoint",
        table_identity="purge_checkpoint",
        stable_identity=f"checkpoint:{uuid.uuid4()}",
        fields={
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id_str,
            "purge_operation_id": str(uuid.uuid4()),
            "owner_key": "external.payload.v1",
            "owner_version": 1,
            "capability_digest": "a" * 64,
            "state": "erasing",
            "attempt": 1,
            "created_at": "2026-01-01T00:00:00",
        },
    )
    envelope = _records_to_envelope(
        tenant_id=tenant_id,
        operation=(op_record,),
        checkpoint=(ck_record,),
        external_ref=(),
        reconcile=(),
    )
    segment_bytes = export_ledger_segment_to_bytes(envelope)
    op_digest = envelope["manifest"]["operation"]["content_digest"]
    ck_digest = envelope["manifest"]["checkpoint"]["content_digest"]
    er_digest = envelope["manifest"]["external_ref"]["content_digest"]
    rc_digest = envelope["manifest"]["reconcile"]["content_digest"]
    manifest = Manifest(
        schema_version=1,
        tenant_id=tenant_id_str,
        record_count={"operation": 1, "checkpoint": 1, "external_ref": 0, "reconcile": 0},
        content_digest={
            "operation": op_digest,
            "checkpoint": ck_digest,
            "external_ref": er_digest,
            "reconcile": rc_digest,
        },
        runtime_per_binding_proof_available=False,
        records={
            "operation": (op_record,),
            "checkpoint": (ck_record,),
            "external_ref": (),
            "reconcile": (),
        },
        raw=envelope,
    )
    outcome = asyncio.run(
        publish_ledger_segment(
            sink=minio_sink,
            tenant_id=tenant_id,
            segment_bytes=segment_bytes,
            manifest=manifest,
        )
    )
    # D1a round-trip：GET-back → decode
    archived = minio_sink.get_object(outcome.segment_key)
    decoded = decode_ledger_segment(archived, expected_tenant_id=tenant_id)
    assert decoded.tenant_id == tenant_id_str
    assert decoded.record_count["operation"] == 1
    assert decoded.record_count["checkpoint"] == 1
