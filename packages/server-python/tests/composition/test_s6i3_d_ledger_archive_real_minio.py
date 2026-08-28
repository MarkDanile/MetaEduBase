"""R1-S6-I3-D D1b 真实 MinIO acceptance 测试（opt-in via RUN_REAL_MINIO_TESTS）。

**严格 opt-in + 严格隔离（Phase 1 安全审计后）**：

- 未设置 ``RUN_REAL_MINIO_TESTS=1`` 时整个模块自动 skip
- **per-run UUID 后缀 bucket**（``metaedu-d1b-acceptance-{uuid4.hex[:12]}``）
- 运行前 bucket 若已存在 → **立即拒绝**（不清理他人留下的 bucket）
- cleanup 使用 **try/finally**（测试失败也保证删 bucket）
- 显式断言 ``bucket != metaedu-resources`` 且 ``bucket != settings.minio_bucket``
- 不访问 PostgreSQL 开发库 ``metaedu``（无 drop/truncate/reseed）
- 真实 MinIO 端点需 MINIO_ROOT_USER/MINIO_ROOT_PASSWORD 全权凭证才能 create/delete bucket

执行命令（按用户裁决 C-1）：

.. code-block:: bash

    # 1. 启动本地 MinIO（仅 minio service；不重建 PG volume）
    docker compose -f deploy/docker-compose.dev.yml up -d minio
    curl -fsS http://localhost:9000/minio/health/live

    # 2. 真实 MinIO acceptance（仅本模块 + external_network 标记）
    cd packages/server-python
    RUN_REAL_MINIO_TESTS=1 \\
        uv run --frozen --extra dev \\
        pytest tests/composition/test_s6i3_d_ledger_archive_real_minio.py \\
        -m external_network -vv

    # 3. （强制）显式验证本模块零引用 metaedu-resources（除作为 bucket != 字符串字面量）
    #    grep -E "\\bwrite_object|remove_bucket.*metaedu-resources\\b" ...

失败模式：
- 未设置环境变量 → 整个模块 skip（pytest collection 不报错）
- MinIO 不可达 → per-test skip（**不**声称已验收）
- per-run bucket 已被占用 → fixture.skip + 显式拒绝（避免删他人 bucket）
- 测试失败 → 仍执行 try/finally 删本轮 bucket；如实登记失败不掩盖

禁止：
- 在 conftest.py 强制启用本模块
- 默认 CI 运行
- 触碰 ``metaedu-resources`` bucket
- 写入生产 / 共享 bucket
- 使用固定 bucket 名（每次运行必须 UUID 后缀）
- 测试失败时跳过 cleanup
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from typing import Any

import pytest

from app.composition.s6i3_d_ledger_archive_sink import (
    FORBIDDEN_BUCKETS,
    BucketNotDistinctError,
    MinioLedgerArchiveSink,
    commit_marker_key,
    find_committed_tip,
    segment_key,
)
from app.composition.s6i3_ledger_snapshot import (
    Manifest,
    decode_ledger_segment,
)
from app.config import settings as app_settings

# 仅 opt-in；本模块所有测试在缺省情况下自动 skip
_RUN_REAL_MINIO = os.environ.get("RUN_REAL_MINIO_TESTS") == "1"

# Real MinIO endpoint（与 deploy/docker-compose.dev.yml 对齐）
_REAL_MINIO_ENDPOINT = os.environ.get("METAEDU_MINIO_ENDPOINT", "127.0.0.1:9000")
_REAL_MINIO_ACCESS_KEY = os.environ.get("METAEDU_MINIO_ACCESS_KEY", "metaedu")
_REAL_MINIO_SECRET_KEY = os.environ.get("METAEDU_MINIO_SECRET_KEY", "dev_only_123")


def _per_run_bucket_name() -> str:
    """Per-run UUID 后缀 bucket（每次 pytest 运行必须唯一）。

    格式：``metaedu-d1b-acceptance-{uuid4.hex[:12]}-{pid}-{ts_ms_low16}``

    双重去重：
    - 12 hex 字符 uuid4（48 bit entropy）
    - PID（同一 pytest 进程并发时）
    - timestamp 低 16 位（毫秒 ms）+ 截断到 4 hex 字符（同一 PID 重启时）
    """
    short_uuid = uuid.uuid4().hex[:12]
    pid = os.getpid()
    ts_low16 = format(int(time.time() * 1000) & 0xFFFF, "04x")
    return f"metaedu-d1b-acceptance-{short_uuid}-{pid}-{ts_low16}"


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


def _assert_bucket_isolated_against_production(bucket: str) -> None:
    """D1b 硬边界：测试 bucket 必须 ≠ 生产 buckets。

    三层防御：
    1. 字面 ``metaedu-resources`` 字符串
    2. ``FORBIDDEN_BUCKETS`` 冻结集
    3. ``app_settings.minio_bucket``（生产 settings）
    """
    assert bucket != "metaedu-resources", (
        f"DB hard boundary violation: test bucket {bucket!r} must NEVER be "
        "'metaedu-resources' (通用 minio_bucket)"
    )
    assert bucket not in FORBIDDEN_BUCKETS, (
        f"D1b bucket isolation violation: test bucket {bucket!r} is in "
        f"FORBIDDEN_BUCKETS {FORBIDDEN_BUCKETS}"
    )
    assert bucket != app_settings.minio_bucket, (
        f"D1b bucket isolation violation: test bucket {bucket!r} == "
        f"app_settings.minio_bucket {app_settings.minio_bucket!r}"
    )
    assert bucket.startswith("metaedu-d1b-acceptance-"), (
        f"D1b test bucket convention violation: {bucket!r} must start with "
        "'metaedu-d1b-acceptance-'"
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
def per_run_minio_bucket() -> Any:
    """Per-run UUID bucket fixture —— **每次运行唯一**。

    关键安全约束（用户裁决 C-1 + Phase 1 审计）：
    - 生成 per-run UUID 后缀 bucket 名
    - 运行前检查：若 bucket 已存在 → **拒绝**（不清理他人遗留）
    - 不存在 → 创建 bucket（需 MINIO_ROOT 全权凭证）
    - yield 给测试
    - **try/finally**：测试通过 / 失败 / 异常 —— 都执行最终 cleanup
    - cleanup：列所有对象并删除 → 删除 bucket 本身
    - 任何 cleanup 失败都不掩盖测试结果；用 contextlib.suppress 抑制 cleanup 异常
    """
    if not _minio_reachable():
        pytest.skip(
            f"MinIO endpoint {_REAL_MINIO_ENDPOINT} not reachable; "
            "real MinIO acceptance aborted. Do NOT claim real-environment verified."
        )

    bucket = _per_run_bucket_name()
    _assert_bucket_isolated_against_production(bucket)

    # 创建 admin client 检查 bucket 是否已存在 + 创建
    from minio import Minio  # type: ignore[import-not-found]

    admin_client = Minio(
        _REAL_MINIO_ENDPOINT,
        access_key=_REAL_MINIO_ACCESS_KEY,
        secret_key=_REAL_MINIO_SECRET_KEY,
        secure=False,
    )

    # 安全检查：per-run bucket 已存在 → 拒绝（不清理他人遗留）
    try:
        if admin_client.bucket_exists(bucket):
            pytest.skip(
                f"per-run bucket {bucket!r} already exists; "
                "refuse to use stale bucket (cannot safely cleanup what we did not create). "
                "Re-run after the stale bucket is manually deleted, "
                "or investigate who created it."
            )
        # 不存在 → 创建
        admin_client.make_bucket(bucket)
    except Exception as exc:
        pytest.skip(
            f"per-run bucket setup failed for {bucket!r}: {type(exc).__name__}: {exc}; "
            "real MinIO acceptance aborted."
        )

    sink = MinioLedgerArchiveSink(
        bucket=bucket,
        endpoint=_REAL_MINIO_ENDPOINT,
        access_key=_REAL_MINIO_ACCESS_KEY,
        secret_key=_REAL_MINIO_SECRET_KEY,
        secure=False,
    )

    try:
        yield bucket, sink
    finally:
        # try/finally —— 无论测试结果如何，cleanup 必须执行
        # cleanup 阶段异常用 contextlib.suppress 抑制，避免掩盖测试本身的 pass/fail
        try:
            # 1) 列所有对象 + 删除
            objs = list(admin_client.list_objects(bucket, prefix="", recursive=True))
            for obj in objs:
                with contextlib.suppress(Exception):
                    admin_client.remove_object(bucket, obj.object_name)
            # 2) 删除 bucket 本身
            with contextlib.suppress(Exception):
                admin_client.remove_bucket(bucket)
        except Exception:
            # cleanup 自身失败（极端）—— 不抛出
            pass


def test_real_minio_segment_put_get_roundtrip(per_run_minio_bucket: Any) -> None:
    """真实 MinIO：MinioLedgerArchiveSink 真实实例化 + PUT segment → GET-back 字节一致。"""
    _bucket, sink = per_run_minio_bucket
    tenant_id = uuid.uuid4()
    payload = b'{"hello":"world"}'
    key = segment_key(str(tenant_id), "a" * 64)
    assert key.startswith("v1/tenants/")
    sink.put_object(key, payload)
    got = sink.get_object(key)
    assert got == payload


def test_real_minio_marker_put_and_list_keys(per_run_minio_bucket: Any) -> None:
    """真实 MinIO：list_keys(prefix) → 含 PUT 的 commit marker。"""
    _bucket, sink = per_run_minio_bucket
    tenant_id = uuid.uuid4()
    marker = b'{"schema_version":1,"tenant_id":"' + str(tenant_id).encode() + b'"}'
    key = commit_marker_key(str(tenant_id), 1, "a" * 16)
    sink.put_object(key, marker)
    keys = sink.list_keys(prefix=f"v1/tenants/{tenant_id}/")
    assert key in keys


def test_real_minio_find_committed_tip_with_one_marker(per_run_minio_bucket: Any) -> None:
    """真实 MinIO：PUT 一个合法 marker → find_committed_tip 返回 tip。"""
    from app.composition.s6i3_d_ledger_archive_sink import (
        PerKindMarker,
        build_commit_marker,
    )

    _bucket, sink = per_run_minio_bucket
    tenant_id = uuid.uuid4()
    export_id = "b" * 16
    sha = "c" * 64
    seg_key = segment_key(str(tenant_id), sha)
    sink.put_object(seg_key, b'{"x":1}')
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
    sink.put_object(marker_key, m.to_bytes())
    tip = find_committed_tip(sink, tenant_id=str(tenant_id))
    assert tip is not None
    assert tip.export_id == export_id
    assert tip.generation == 1


def test_real_minio_rejects_forbidden_bucket_construction() -> None:
    """真实 MinIO 构造器也强制 bucket ≠ metaedu-resources（无需网络）。"""
    with pytest.raises(BucketNotDistinctError):
        MinioLedgerArchiveSink(
            bucket="metaedu-resources",
            endpoint=_REAL_MINIO_ENDPOINT,
            access_key=_REAL_MINIO_ACCESS_KEY,
            secret_key=_REAL_MINIO_SECRET_KEY,
        )


def test_real_minio_archive_segment_via_two_phase_api(per_run_minio_bucket: Any) -> None:
    """真实 MinIO：完整两阶段 API 路径 —— phase-2 publish_ledger_segment 真实执行。

    此测试**直接调用 phase-2 publish_ledger_segment**，绕过 phase-1 PG 部分
    （PG fixture 与 MinIO acceptance 解耦；测试聚焦 sink I/O 行为）。
    """
    import asyncio

    from app.composition.s6i3_d_ledger_archive_sink import publish_ledger_segment
    from app.composition.s6i3_ledger_snapshot import ExportedRecord

    _bucket, sink = per_run_minio_bucket
    tenant_id = uuid.uuid4()
    tenant_id_str = str(tenant_id)
    segment_bytes = b'{"tenant_id":"' + tenant_id_str.encode() + b'","schema_version":1}'

    # D1a decoder 强制 stable_identity == f"{kind}:{fields.id}"，故 id 必须先生成
    op_id = uuid.uuid4()
    op = ExportedRecord(
        record_kind="operation",
        table_identity="purge_operation",
        stable_identity=f"operation:{op_id}",
        fields={"id": str(op_id)},
    )
    ck_id = uuid.uuid4()
    ck = ExportedRecord(
        record_kind="checkpoint",
        table_identity="purge_checkpoint",
        stable_identity=f"checkpoint:{ck_id}",
        fields={"id": str(ck_id)},
    )
    digest = "a" * 64
    manifest = Manifest(
        schema_version=1,
        tenant_id=tenant_id_str,
        record_count={
            "operation": 1,
            "checkpoint": 1,
            "external_ref": 0,
            "reconcile": 0,
        },
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
            sink=sink,
            tenant_id=tenant_id,
            segment_bytes=segment_bytes,
            manifest=manifest,
        )
    )
    assert outcome.generation == 1
    assert outcome.idempotent_retry is False
    # 真实 MinIO 上 segment + marker 都应存在
    assert sink.get_object(outcome.segment_key) == segment_bytes
    assert sink.get_object(outcome.marker_key) is not None


def test_real_minio_archive_segment_d1a_round_trip(per_run_minio_bucket: Any) -> None:
    """真实 MinIO：完整 round-trip —— D1a encode → archive → D1a decode 必须通过。"""
    import asyncio

    from app.composition.s6i3_d_ledger_archive_sink import publish_ledger_segment
    from app.composition.s6i3_ledger_snapshot import (
        ExportedRecord,
        _records_to_envelope,
        export_ledger_segment_to_bytes,
    )

    _bucket, sink = per_run_minio_bucket
    tenant_id = uuid.uuid4()
    tenant_id_str = str(tenant_id)
    # 构造合法 envelope → D1a encode → phase-2 publish → phase-2 后 GET-back → D1a decode
    # D1a decoder 强制 stable_identity == f"{kind}:{fields.id}"，故 id 必须先生成
    op_id = uuid.uuid4()
    op_record = ExportedRecord(
        record_kind="operation",
        table_identity="agent_conversation_purges",
        stable_identity=f"operation:{op_id}",
        fields={
            "id": str(op_id),
            "tenant_id": tenant_id_str,
            "conversation_id": str(uuid.uuid4()),
            "purge_revision": 1,
            "state": "running",
        },
    )
    ck_id = uuid.uuid4()
    # checkpoint 必须挂在 operation 上：D1a 校验 purge_operation_id 是 canonical UUID
    ck_record = ExportedRecord(
        record_kind="checkpoint",
        table_identity="agent_conversation_purge_owners",
        stable_identity=f"checkpoint:{ck_id}",
        fields={
            "id": str(ck_id),
            "tenant_id": tenant_id_str,
            "purge_operation_id": str(op_id),
            "owner_key": "external.payload.v1",
            "owner_version": 1,
            "capability_digest": "a" * 64,
            "state": "erasing",
            "attempt": 1,
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
        record_count={
            "operation": 1,
            "checkpoint": 1,
            "external_ref": 0,
            "reconcile": 0,
        },
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
            sink=sink,
            tenant_id=tenant_id,
            segment_bytes=segment_bytes,
            manifest=manifest,
        )
    )
    # D1a round-trip：GET-back → decode
    archived = sink.get_object(outcome.segment_key)
    decoded = decode_ledger_segment(archived, expected_tenant_id=tenant_id)
    assert decoded.tenant_id == tenant_id_str
    assert decoded.record_count["operation"] == 1
    assert decoded.record_count["checkpoint"] == 1
