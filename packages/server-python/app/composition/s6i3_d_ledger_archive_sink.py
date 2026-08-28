"""R1-S6-I3-D D1b：专用 MinIO ledger archive sink（不可变 commit-graph 发布协议）。

D1a 交付 = 只读 ledger snapshot codec（bounded + decoder + reconstruct）；
D1b = 把 D1a 的 segment 字节不可变发布到专用 MinIO archive bucket，
构造线性 commit-graph marker 链并推导 committed tip。

本模块**严格限定** D1b 范围：
- 不可变 segment 字节写入（key = sha256(segment_bytes)）
- 不可变 commit marker 写入（key = `{generation:020d}-{export_id}.json`）
- D1a decoder 双侧校验（PUT 前 + GET 后）
- crash/retry/idempotency（同 export_id 同 marker key）
- V1 = per-tenant single publisher；并发 fork fail closed

**不**实现：replay executor / restore DB mutation / restore-before-open runbook
/ production continuous capture / scheduler 接入 / capability flip / 六 erase 入口
生产可达 —— 全部属 D2 / PR-D / PR-E / C1 / S5 wiring 范畴，本 slice **不启动**。

对象协议（用户裁决 D1b 冻结）：
- segment key: ``v1/tenants/{tenant_id}/segments/{segment_sha256}.json``
- commit marker key: ``v1/tenants/{tenant_id}/commits/{generation:020d}-{export_id}.json``
- marker 至少含 schema_version / tenant_id / export_id / parent_export_id / generation /
  segment_key / segment_sha256 / 每个 record kind 的 generation/count/content_digest

发布顺序：RR + READ ONLY 事务导出 segment → D1a decode 校验 → PUT immutable segment
→ GET-back + digest 校验 → 再 PUT immutable commit marker；marker 出现才代表提交成功。

禁止：临时对象 rename / 普通可变 HEAD 覆盖冒充原子发布；用「写前 stat + 普通 PUT」
伪造 CAS；维护 last-write-wins HEAD；DB 事务持网络 I/O；自动创建 bucket（生产）；drop
/truncate/reseed/重建 metaedu。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.s6i3_ledger_snapshot import (
    LedgerSnapshotError,
    decode_ledger_segment,
    export_ledger_segment,
)

logger = structlog.get_logger(__name__)


# --- 常量（冻结契约 + 用户裁决 D1b 落地） ---

SCHEMA_VERSION: int = 1
KEY_PREFIX_VERSION: str = "v1"
KEY_SEGMENT_SUBDIR: str = "segments"
KEY_COMMIT_SUBDIR: str = "commits"

CANONICAL_UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
LOWERCASE_64HEX_REGEX = re.compile(r"^[0-9a-f]{64}$")
LOWERCASE_16HEX_REGEX = re.compile(r"^[0-9a-f]{16}$")

DEFAULT_BUCKET_NAME: str = "metaedu-ledger-archive"
# 与现有 app.config.minio_bucket（metaedu-resources）必须不同；见 _assert_bucket_distinct
FORBIDDEN_BUCKETS: frozenset[str] = frozenset({"metaedu-resources"})

MAX_PUBLISH_RETRIES: int = 3
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.05, 0.2, 0.5)


# --- 错误（具名 domain error，不泄露 endpoint credential 或 artifact 敏感内容） ---


class LedgerArchiveError(Exception):
    """D1b archive sink domain error 基类。所有 D1b 错误归一化为本类。"""

    def __init__(self, code: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail: dict[str, Any] = dict(detail) if detail else {}


class BucketNotDistinctError(LedgerArchiveError):
    """bucket 配置与通用 minio_bucket 重复。"""


class ObjectKeyInvalidError(LedgerArchiveError):
    """对象 key 不符合冻结前缀 + 不可变 segment-by-sha / commit-by-generation-export 规则。"""


class SegmentDigestMismatchError(LedgerArchiveError):
    """GET-back 后 SHA-256 与发布时记录不一致 —— MinIO/S3 端字节被破坏。"""


class CommitMarkerPayloadCorruptError(LedgerArchiveError):
    """commit marker 反序列化失败或 schema_version 不匹配。"""


class ObjectIdentityCollisionError(LedgerArchiveError):
    """同 key 对象已存在但 content 字节不同 —— 不可变模型下不该发生。"""


class ParentExportMissingError(LedgerArchiveError):
    """指定 parent_export_id 在当前 tenant 不存在。"""


class SegmentObjectMissingError(LedgerArchiveError):
    """marker 引用了不存在的 segment 对象（PUT 失败 / 竞争删除）。"""


class ForkDetectedError(LedgerArchiveError):
    """同 generation 出现多个不同 parent —— 多 publisher fork，V1 失败闭合。"""


class GenerationRegressionError(LedgerArchiveError):
    """新 marker generation 不严格大于既有 tip。"""


class TenantMismatchError(LedgerArchiveError):
    """对象 tenant_id 与 caller expected tenant 不一致。"""


class ExistingPayloadDivergesError(LedgerArchiveError):
    """同 marker key 已存在但 payload 不同 —— 不可变模型下禁止。"""


class PublishPreconditionFailedError(LedgerArchiveError):
    """publish 前置条件（事务属性 / D1a decode 等）失败。"""


class ArchiveUnavailableError(LedgerArchiveError):
    """sink 网络/凭据/服务端错误，超过重试上限。"""


# --- 对象元数据 ---


@dataclass(frozen=True)
class ObjectMetadata:
    """对象元数据：来自 head_object 调用。"""

    key: str
    size: int
    etag: str
    content_type: str


# --- Sink Protocol（fake + minio adapter 共享接口） ---


class LedgerArchiveSink(Protocol):
    """archive sink 接口契约；fake 与 MinIO adapter 均实现本接口。

    所有方法失败归一化为 LedgerArchiveError；不允许裸抛 OSError / 客户端异常。
    """

    bucket: str

    def put_object(
        self, key: str, payload: bytes, *, content_type: str = "application/json"
    ) -> ObjectMetadata: ...

    def get_object(self, key: str) -> bytes: ...

    def head_object(self, key: str) -> ObjectMetadata: ...

    def list_keys(self, *, prefix: str) -> list[str]: ...


# --- helpers ---


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _export_id_from_segment(segment_bytes: bytes) -> str:
    """export_id = sha256(segment_bytes)[:16] —— 同 segment 字节同 export_id。

    设计为 commit marker key 的 second 半部分，确保同 segment 重试（idempotent）落在同
    marker key 上。
    """
    return _sha256_hex(segment_bytes)[:16]


def _assert_canonical_uuid(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not CANONICAL_UUID_REGEX.match(value):
        raise LedgerArchiveError(
            "TENANT_ID_NOT_CANONICAL_UUID",
            detail={"field": field, "type": type(value).__name__},
        )
    return value


def _assert_lowercase_64hex(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not LOWERCASE_64HEX_REGEX.match(value):
        raise LedgerArchiveError(
            "FIELD_NOT_LOWERCASE_64HEX",
            detail={"field": field, "type": type(value).__name__},
        )
    return value


def _assert_lowercase_16hex(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not LOWERCASE_16HEX_REGEX.match(value):
        raise LedgerArchiveError(
            "FIELD_NOT_LOWERCASE_16HEX",
            detail={"field": field, "type": type(value).__name__},
        )
    return value


def _assert_strict_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerArchiveError(
            "FIELD_NOT_STRICT_INT",
            detail={"field": field, "type": type(value).__name__},
        )
    return value


def _assert_bucket_distinct(bucket: str, *, forbidden: Iterable[str] = FORBIDDEN_BUCKETS) -> None:
    if not isinstance(bucket, str) or not bucket:
        raise LedgerArchiveError("BUCKET_NAME_INVALID")
    if bucket in forbidden:
        raise BucketNotDistinctError(
            "BUCKET_NOT_DISTINCT",
            detail={"bucket": bucket, "forbidden": sorted(forbidden)},
        )


def segment_key(tenant_id: str, segment_sha256: str) -> str:
    """不可变 segment key = sha256 派生 —— 同字节同 key，永久。"""
    _assert_canonical_uuid(tenant_id, field="tenant_id")
    _assert_lowercase_64hex(segment_sha256, field="segment_sha256")
    return (
        f"{KEY_PREFIX_VERSION}/tenants/{tenant_id}/{KEY_SEGMENT_SUBDIR}/"
        f"{segment_sha256}.json"
    )


def commit_marker_key(tenant_id: str, generation: int, export_id: str) -> str:
    """commit marker key = generation + export_id —— generation 单调 + export_id 字节确定。"""
    _assert_canonical_uuid(tenant_id, field="tenant_id")
    _assert_strict_int(generation, field="generation")
    if generation < 1:
        raise LedgerArchiveError("GENERATION_NOT_POSITIVE")
    _assert_lowercase_16hex(export_id, field="export_id")
    return (
        f"{KEY_PREFIX_VERSION}/tenants/{tenant_id}/{KEY_COMMIT_SUBDIR}/"
        f"{generation:020d}-{export_id}.json"
    )


def prefix_for_tenant(tenant_id: str) -> str:
    _assert_canonical_uuid(tenant_id, field="tenant_id")
    return f"{KEY_PREFIX_VERSION}/tenants/{tenant_id}/"


# --- Commit marker dataclass ---


@dataclass(frozen=True)
class PerKindMarker:
    """marker 中每个 record kind 的 generation / count / content_digest 三元组。"""

    generation: int
    count: int
    content_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "count": self.count,
            "content_digest": self.content_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PerKindMarker:
        return cls(
            generation=_assert_strict_int(data.get("generation"), field="per_kind.generation"),
            count=_assert_strict_int(data.get("count"), field="per_kind.count"),
            content_digest=_assert_lowercase_64hex(
                data.get("content_digest"), field="per_kind.content_digest"
            ),
        )


@dataclass(frozen=True)
class CommitMarker:
    """不可变 commit marker —— 写入后等同发布事实。"""

    schema_version: int
    tenant_id: str
    export_id: str
    parent_export_id: str | None
    generation: int
    segment_key: str
    segment_sha256: str
    per_kind: dict[str, PerKindMarker]
    published_at_unix: int

    def to_canonical_dict(self) -> dict[str, Any]:
        # sort_keys=True 用于 marker 序列化（marker 自身亦不可变 + 字节确定）
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "export_id": self.export_id,
            "parent_export_id": self.parent_export_id,
            "generation": self.generation,
            "segment_key": self.segment_key,
            "segment_sha256": self.segment_sha256,
            "per_kind": {k: v.to_dict() for k, v in sorted(self.per_kind.items())},
            "published_at_unix": self.published_at_unix,
        }

    def to_bytes(self) -> bytes:
        return json.dumps(
            self.to_canonical_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes) -> CommitMarker:
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommitMarkerPayloadCorruptError(
                "MARKER_NOT_JSON", detail={"error": str(exc)}
            ) from exc
        if not isinstance(obj, dict):
            raise CommitMarkerPayloadCorruptError("MARKER_NOT_OBJECT")
        schema_version = _assert_strict_int(obj.get("schema_version"), field="schema_version")
        if schema_version != SCHEMA_VERSION:
            raise CommitMarkerPayloadCorruptError(
                "MARKER_SCHEMA_VERSION_MISMATCH",
                detail={"expected": SCHEMA_VERSION, "got": schema_version},
            )
        tenant_id = _assert_canonical_uuid(obj.get("tenant_id"), field="tenant_id")
        export_id = _assert_lowercase_16hex(obj.get("export_id"), field="export_id")
        parent = obj.get("parent_export_id")
        if parent is not None:
            parent = _assert_lowercase_16hex(parent, field="parent_export_id")
        generation = _assert_strict_int(obj.get("generation"), field="generation")
        seg_key = obj.get("segment_key")
        if not isinstance(seg_key, str):
            raise CommitMarkerPayloadCorruptError("MARKER_SEGMENT_KEY_NOT_STRING")
        seg_sha = _assert_lowercase_64hex(obj.get("segment_sha256"), field="segment_sha256")
        per_kind_raw = obj.get("per_kind")
        if not isinstance(per_kind_raw, dict):
            raise CommitMarkerPayloadCorruptError("MARKER_PER_KIND_NOT_OBJECT")
        per_kind = {k: PerKindMarker.from_dict(v) for k, v in per_kind_raw.items()}
        published_at_unix = _assert_strict_int(
            obj.get("published_at_unix"), field="published_at_unix"
        )
        return cls(
            schema_version=schema_version,
            tenant_id=tenant_id,
            export_id=export_id,
            parent_export_id=parent,
            generation=generation,
            segment_key=seg_key,
            segment_sha256=seg_sha,
            per_kind=per_kind,
            published_at_unix=published_at_unix,
        )


def build_commit_marker(
    *,
    tenant_id: str,
    export_id: str,
    parent_export_id: str | None,
    generation: int,
    segment_key_str: str,
    segment_sha256: str,
    per_kind: Mapping[str, PerKindMarker],
    now_unix: int | None = None,
) -> CommitMarker:
    if now_unix is None:
        # Deterministic derivation from segment_sha256 —— 保证 marker bytes deterministic，
        # idempotent retry 时字节一致；非用于外部排序/优先级。
        now_unix = int(segment_sha256[:8], 16)
    return CommitMarker(
        schema_version=SCHEMA_VERSION,
        tenant_id=tenant_id,
        export_id=export_id,
        parent_export_id=parent_export_id,
        generation=generation,
        segment_key=segment_key_str,
        segment_sha256=segment_sha256,
        per_kind=dict(per_kind),
        published_at_unix=now_unix,
    )


# --- 错误注入 / sleeper 协议（测试用） ---


class TransientArchiveError(Exception):
    """archive sink 内部 transient 错误（重试可恢复）；测试用 sleeper 抛出。"""


Sleeper = Callable[[float], "asyncio.Future[None] | None"]


async def _sleep_or_yield(seconds: float, *, sleeper: Sleeper | None) -> None:
    """默认 asyncio.sleep；测试可注入 fake sleeper 禁止真实 sleep。"""
    if sleeper is None:
        await asyncio.sleep(seconds)
        return
    result = sleeper(seconds)
    if asyncio.iscoroutine(result):
        await result


async def _retry_with_backoff(
    operation: Callable[[], Any],
    *,
    max_attempts: int = MAX_PUBLISH_RETRIES,
    backoff: Sequence[float] = RETRY_BACKOFF_SECONDS,
    sleeper: Sleeper | None = None,
) -> Any:
    """有界重试：transient 错误（网络/服务端）按 backoff 重试，结构性错误立即 fail。

    非 transient：LedgerArchiveError（含 BucketNotDistinctError 等）直接上抛。
    transient：TransientArchiveError + 超限后转 ArchiveUnavailableError。
    """
    attempts = max_attempts if max_attempts > 0 else 1
    last_exc: Exception | None = None
    for attempt_index in range(attempts):
        try:
            return operation()
        except LedgerArchiveError:
            raise
        except TransientArchiveError as exc:
            last_exc = exc
            if attempt_index >= attempts - 1:
                break
            backoff_seconds = backoff[min(attempt_index, len(backoff) - 1)]
            await _sleep_or_yield(backoff_seconds, sleeper=sleeper)
    raise ArchiveUnavailableError(
        "PUBLISH_RETRY_EXHAUSTED",
        detail={"attempts": attempts, "last_error": repr(last_exc)},
    )


# --- In-memory sink（测试 + 本地 dry-run 用） ---


@dataclass
class _MemObject:
    body: bytes
    content_type: str


class InMemoryLedgerArchiveSink:
    """in-memory fake sink；test 与本地 dry-run 用。

    bucket 必须非空且不在 FORBIDDEN_BUCKETS。
    put_object 支持两种失败注入：collision（同 key 不同 content）与 transient。
    """

    def __init__(
        self,
        *,
        bucket: str,
        on_put: Callable[[str, bytes], None] | None = None,
        collision_keys: set[str] | None = None,
        transient_keys: set[str] | None = None,
    ) -> None:
        _assert_bucket_distinct(bucket)
        self.bucket = bucket
        self._objects: dict[str, _MemObject] = {}
        self._on_put = on_put
        self._collision_keys = collision_keys or set()
        self._transient_keys = transient_keys or set()

    def put_object(
        self, key: str, payload: bytes, *, content_type: str = "application/json"
    ) -> ObjectMetadata:
        if not isinstance(key, str) or not key:
            raise ObjectKeyInvalidError("KEY_NOT_STRING")
        if key in self._transient_keys:
            raise TransientArchiveError(f"transient: {key}")
        existing = self._objects.get(key)
        if existing is not None and existing.body != payload:
            raise ObjectIdentityCollisionError(
                "OBJECT_IDENTITY_COLLISION",
                detail={"key": key, "existing_size": len(existing.body), "new_size": len(payload)},
            )
        if key in self._collision_keys and existing is not None and existing.body != payload:
            raise ObjectIdentityCollisionError(
                "OBJECT_IDENTITY_COLLISION_TEST",
                detail={"key": key},
            )
        if self._on_put is not None:
            self._on_put(key, payload)
        self._objects[key] = _MemObject(body=payload, content_type=content_type)
        return ObjectMetadata(
            key=key,
            size=len(payload),
            etag=_sha256_hex(payload),
            content_type=content_type,
        )

    def get_object(self, key: str) -> bytes:
        obj = self._objects.get(key)
        if obj is None:
            raise LedgerArchiveError("OBJECT_NOT_FOUND", detail={"key": key})
        return obj.body

    def head_object(self, key: str) -> ObjectMetadata:
        obj = self._objects.get(key)
        if obj is None:
            raise LedgerArchiveError("OBJECT_NOT_FOUND", detail={"key": key})
        return ObjectMetadata(
            key=key,
            size=len(obj.body),
            etag=_sha256_hex(obj.body),
            content_type=obj.content_type,
        )

    def list_keys(self, *, prefix: str) -> list[str]:
        if not isinstance(prefix, str):
            raise LedgerArchiveError("PREFIX_NOT_STRING")
        return sorted(k for k in self._objects if k.startswith(prefix))


# --- MinIO adapter（生产；可选 lazy import） ---


class MinioLedgerArchiveSink:
    """MinIO / S3-compatible ledger archive sink。

    - lazy import ``minio`` —— 测试无需安装/连接；
    - bucket 必须预先存在 —— 生产 publish 不自动创建 bucket；
    - 失败归一化为 LedgerArchiveError；transient 转 TransientArchiveError。
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
    ) -> None:
        _assert_bucket_distinct(bucket)
        if not isinstance(endpoint, str) or not endpoint:
            raise LedgerArchiveError("MINIO_ENDPOINT_INVALID")
        self.bucket = bucket
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._secure = bool(secure)
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from minio import Minio  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ArchiveUnavailableError(
                    "MINIO_IMPORT_FAILED",
                    detail={"error": str(exc)},
                ) from exc
            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
        return self._client

    def put_object(
        self, key: str, payload: bytes, *, content_type: str = "application/json"
    ) -> ObjectMetadata:
        from io import BytesIO

        client = self._get_client()
        try:
            result = client.put_object(
                self.bucket, key, BytesIO(payload), length=len(payload), content_type=content_type
            )
        except Exception as exc:  # noqa: BLE001 — minio raises bare
            raise _minio_translate(exc, op="put_object", key=key) from exc
        return ObjectMetadata(
            key=key,
            size=len(payload),
            etag=getattr(result, "etag", "") or "",
            content_type=content_type,
        )

    def get_object(self, key: str) -> bytes:
        client = self._get_client()
        try:
            response = client.get_object(self.bucket, key)
        except Exception as exc:  # noqa: BLE001
            raise _minio_translate(exc, op="get_object", key=key) from exc
        try:
            return response.read()
        finally:
            with contextlib.suppress(Exception):
                response.close()
            with contextlib.suppress(Exception):
                response.release_conn()

    def head_object(self, key: str) -> ObjectMetadata:
        client = self._get_client()
        try:
            stat = client.stat_object(self.bucket, key)
        except Exception as exc:  # noqa: BLE001
            raise _minio_translate(exc, op="head_object", key=key) from exc
        return ObjectMetadata(
            key=key,
            size=int(getattr(stat, "size", 0) or 0),
            etag=str(getattr(stat, "etag", "") or ""),
            content_type=str(getattr(stat, "content_type", "") or "application/json"),
        )

    def list_keys(self, *, prefix: str) -> list[str]:
        client = self._get_client()
        keys: list[str] = []
        try:
            for obj in client.list_objects(self.bucket, prefix=prefix, recursive=True):
                keys.append(str(obj.object_name))
        except Exception as exc:  # noqa: BLE001
            raise _minio_translate(exc, op="list_keys", key=prefix) from exc
        return sorted(keys)


def _minio_translate(exc: BaseException, *, op: str, key: str | None = None) -> Exception:
    """MinIO 异常归一化为 LedgerArchiveError；transient 网络错误转 TransientArchiveError。"""
    name = type(exc).__name__
    detail: dict[str, Any] = {"op": op, "type": name}
    if key is not None:
        detail["key"] = key
    msg = str(exc).lower()
    transient_markers = ("connection", "timeout", "throttl", "503", "504", "reset")
    if any(marker in msg for marker in transient_markers):
        return TransientArchiveError(f"minio {op} transient: {name}")
    return ArchiveUnavailableError(f"MINIO_{op.upper()}_FAILED", detail=detail)


# --- Commit-graph tip walking ---


@dataclass(frozen=True)
class CommittedTip:
    """committed tip —— 由 commit-graph 推导，不持久化。"""

    export_id: str
    parent_export_id: str | None
    generation: int
    marker_key: str
    marker_bytes: bytes
    segment_key: str
    segment_sha256: str


def _walk_tenant_markers(
    sink: LedgerArchiveSink,
    *,
    tenant_id: str,
) -> list[CommitMarker]:
    """列出 tenant 下所有 marker（按 generation 升序；marker key 字典序==generation）。"""
    prefix = (
        f"{KEY_PREFIX_VERSION}/tenants/{tenant_id}/{KEY_COMMIT_SUBDIR}/"
    )
    keys = sink.list_keys(prefix=prefix)
    markers: list[CommitMarker] = []
    for k in keys:
        try:
            body = sink.get_object(k)
        except LedgerArchiveError:
            continue
        try:
            m = CommitMarker.from_bytes(body)
        except CommitMarkerPayloadCorruptError:
            continue
        markers.append(m)
    markers.sort(key=lambda m: m.generation)
    return markers


def find_committed_tip(sink: LedgerArchiveSink, *, tenant_id: str) -> CommittedTip | None:
    """推导 tenant 的 committed tip。返回 None 当不存在任何 marker。

    fork 检测：同 generation 出现多个 marker → ForkDetectedError（V1 失败闭合）。
    generation regression：marker.parent_export_id 与既有 chain 不匹配 → GenerationRegressionError。
    """
    markers = _walk_tenant_markers(sink, tenant_id=tenant_id)
    if not markers:
        return None
    seen_generations: dict[int, str] = {}
    last: CommitMarker | None = None
    for m in markers:
        existing_export_id = seen_generations.get(m.generation)
        if existing_export_id is not None and existing_export_id != m.export_id:
            raise ForkDetectedError(
                "FORK_DETECTED",
                detail={
                    "generation": m.generation,
                    "export_ids": sorted({existing_export_id, m.export_id}),
                },
            )
        seen_generations[m.generation] = m.export_id
        if last is not None and m.parent_export_id != last.export_id:
            raise GenerationRegressionError(
                "GENERATION_REGRESSION",
                detail={
                    "current_generation": m.generation,
                    "current_parent": m.parent_export_id,
                    "previous_export_id": last.export_id,
                },
            )
        last = m
    if last is None:
        return None
    return CommittedTip(
        export_id=last.export_id,
        parent_export_id=last.parent_export_id,
        generation=last.generation,
        marker_key=commit_marker_key(last.tenant_id, last.generation, last.export_id),
        marker_bytes=last.to_bytes(),
        segment_key=last.segment_key,
        segment_sha256=last.segment_sha256,
    )


def fetch_segment_bytes(sink: LedgerArchiveSink, *, tenant_id: str, marker: CommitMarker) -> bytes:
    """通过 marker 读取 segment 字节，校验 SHA-256，校验 tenant_id。"""
    if marker.tenant_id != tenant_id:
        raise TenantMismatchError(
            "MARKER_TENANT_MISMATCH",
            detail={"expected": tenant_id, "marker": marker.tenant_id},
        )
    body = sink.get_object(marker.segment_key)
    actual_sha = _sha256_hex(body)
    if actual_sha != marker.segment_sha256:
        raise SegmentObjectMissingError(
            "SEGMENT_OBJECT_MISSING_OR_CORRUPT",
            detail={
                "expected_sha": marker.segment_sha256,
                "actual_sha": actual_sha,
            },
        )
    return body


# --- Publish orchestration ---


@dataclass(frozen=True)
class PublishOutcome:
    """publish 结果 —— caller 据此推进 source cursor（不属 D1b）。"""

    export_id: str
    generation: int
    marker_key: str
    segment_key: str
    segment_sha256: str
    idempotent_retry: bool


async def archive_ledger_segment(
    session: AsyncSession,
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
    parent_export_id: str | None = None,
    sleeper: Sleeper | None = None,
    per_kind_counts_and_digests: Mapping[str, tuple[int, str]] | None = None,
    now_unix: int | None = None,
) -> PublishOutcome:
    """D1b 主入口：导出 D1a segment 字节 → 不可变发布到 archive sink。

    Args:
        session: caller-managed RR + READ ONLY DB 事务（按 D1a 用户裁决）。
        sink: archive sink（fake / MinIO）。
        tenant_id: 规范 UUID —— sink 路由 key 由其决定，cross-tenant 严格隔离。
        parent_export_id: 同 payload 同 export_id 重试必须返回相同结果；
            同一 segment 重试会自动落到同一 export_id（无需 caller 传）。
        sleeper: 测试可注入，禁用真实 sleep。
        per_kind_counts_and_digests: D1a decoder 输出的 manifest counts/content_digest；
            None 时 publish 内部 decode 校验并提取。
        now_unix: 测试可注入；None 时取 ``int(time.time())``。

    Raises:
        PublishPreconditionFailedError: D1a decode 校验失败 / RR+RO 事务属性未满足。
        ForkDetectedError: 同 generation 多 export_id。
        GenerationRegressionError: 新 generation 不严格大于既有 tip。
        ParentExportMissingError: 指定 parent_export_id 在 tenant 不存在。
        ArchiveUnavailableError: 重试超限。
    """
    tenant_id_str = str(tenant_id)
    _assert_canonical_uuid(tenant_id_str, field="tenant_id")
    if parent_export_id is not None:
        _assert_lowercase_16hex(parent_export_id, field="parent_export_id")

    # 1. D1a 导出（caller-managed RR + READ ONLY 事务）
    try:
        segment_bytes = await export_ledger_segment(session, tenant_id=tenant_id)
    except LedgerSnapshotError as exc:
        raise PublishPreconditionFailedError(
            "D1A_EXPORT_FAILED",
            detail={"reason": exc.reason, **exc.detail},
        ) from exc

    # 2. 计算 segment sha + export_id
    segment_sha = _sha256_hex(segment_bytes)
    export_id = _export_id_from_segment(segment_bytes)
    seg_key = segment_key(tenant_id_str, segment_sha)

    # 3. PUT 前 D1a decoder 校验（用户裁决：发布前后均调用 decode）
    try:
        manifest = decode_ledger_segment(
            segment_bytes, expected_tenant_id=tenant_id
        )
    except LedgerSnapshotError as exc:
        raise PublishPreconditionFailedError(
            "D1A_DECODE_PRE_PUBLISH_FAILED",
            detail={"reason": exc.reason, **exc.detail},
        ) from exc

    # 4. 提取 per-kind counts/content_digest（如 caller 未传）
    if per_kind_counts_and_digests is None:
        per_kind_payload: dict[str, tuple[int, str]] = {
            kind: (
                int(manifest.record_count[kind]),
                str(manifest.content_digest[kind]),
            )
            for kind in sorted(manifest.record_count)
        }
    else:
        per_kind_payload = dict(per_kind_counts_and_digests)

    # 5. 推导 tip（必须发生在 PUT 之前 —— 用以确定 parent / generation）
    tip = find_committed_tip(sink, tenant_id=tenant_id_str)
    if parent_export_id is None:
        # caller 未指定：跟随 current tip 链
        expected_parent = tip.export_id if tip is not None else None
    else:
        # caller 指定 parent_export_id：必须匹配当前 tip
        if tip is None or tip.export_id != parent_export_id:
            raise ParentExportMissingError(
                "PARENT_EXPORT_MISSING",
                detail={"caller_parent": parent_export_id, "tip": tip.export_id if tip else None},
            )
        expected_parent = parent_export_id

    new_generation = (tip.generation + 1) if tip is not None else 1
    marker_key_str = commit_marker_key(tenant_id_str, new_generation, export_id)

    # 6. PUT segment（不可变；同 sha 同 key；同 key 不同字节 → collision）
    try:
        await _retry_with_backoff(
            lambda: sink.put_object(seg_key, segment_bytes),
            sleeper=sleeper,
        )
    except LedgerArchiveError:
        raise

    # 7. GET-back + digest 校验（确保 MinIO/S3 端字节未损坏）
    def _get_back_and_verify() -> None:
        body = sink.get_object(seg_key)
        actual_sha = _sha256_hex(body)
        if actual_sha != segment_sha:
            raise SegmentDigestMismatchError(
                "SEGMENT_DIGEST_MISMATCH",
                detail={"expected": segment_sha, "actual": actual_sha},
            )

    await _retry_with_backoff(_get_back_and_verify, sleeper=sleeper)

    # 8. 构造 commit marker
    per_kind_markers: dict[str, PerKindMarker] = {
        kind: PerKindMarker(
            generation=1,  # per-kind generation 起点 = 1（本 slice 不区分 per-kind 推进语义）
            count=int(count),
            content_digest=digest,
        )
        for kind, (count, digest) in sorted(per_kind_payload.items())
    }
    marker = build_commit_marker(
        tenant_id=tenant_id_str,
        export_id=export_id,
        parent_export_id=expected_parent,
        generation=new_generation,
        segment_key_str=seg_key,
        segment_sha256=segment_sha,
        per_kind=per_kind_markers,
        now_unix=now_unix,
    )

    # 9. idempotent retry: candidate marker key 已存在且字节完全一致 → 复用
    # marker bytes 在 publish_at_unix 确定性派生后字节稳定；不同字节 = diverges
    candidate_marker_key = marker_key_str
    try:
        existing_marker_bytes = sink.get_object(candidate_marker_key)
        if existing_marker_bytes == marker.to_bytes():
            return PublishOutcome(
                export_id=export_id,
                generation=new_generation,
                marker_key=candidate_marker_key,
                segment_key=seg_key,
                segment_sha256=segment_sha,
                idempotent_retry=True,
            )
        # 同 key 不同字节 → 不可变模型禁止
        raise ExistingPayloadDivergesError(
            "EXISTING_PAYLOAD_DIVERGES",
            detail={"marker_key": marker_key_str},
        )
    except LedgerArchiveError:
        # 不存在或损坏 → 走 PUT 路径
        pass

    # 10. PUT commit marker（不可变；同 key 不同字节 → collision）
    try:
        await _retry_with_backoff(
            lambda: sink.put_object(marker_key_str, marker.to_bytes()),
            sleeper=sleeper,
        )
    except ObjectIdentityCollisionError as exc:
        # 同 key 已存在但 payload 不同 —— 不可变模型下禁止
        raise ExistingPayloadDivergesError(
            "EXISTING_PAYLOAD_DIVERGES",
            detail={"marker_key": marker_key_str, "code": exc.code},
        ) from exc

    return PublishOutcome(
        export_id=export_id,
        generation=new_generation,
        marker_key=marker_key_str,
        segment_key=seg_key,
        segment_sha256=segment_sha,
        idempotent_retry=False,
    )


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_BUCKET_NAME",
    "FORBIDDEN_BUCKETS",
    "MAX_PUBLISH_RETRIES",
    "RETRY_BACKOFF_SECONDS",
    "LedgerArchiveError",
    "BucketNotDistinctError",
    "ObjectKeyInvalidError",
    "SegmentDigestMismatchError",
    "CommitMarkerPayloadCorruptError",
    "ObjectIdentityCollisionError",
    "ParentExportMissingError",
    "SegmentObjectMissingError",
    "ForkDetectedError",
    "GenerationRegressionError",
    "TenantMismatchError",
    "ExistingPayloadDivergesError",
    "PublishPreconditionFailedError",
    "ArchiveUnavailableError",
    "TransientArchiveError",
    "ObjectMetadata",
    "LedgerArchiveSink",
    "InMemoryLedgerArchiveSink",
    "MinioLedgerArchiveSink",
    "PerKindMarker",
    "CommitMarker",
    "CommittedTip",
    "PublishOutcome",
    "build_commit_marker",
    "segment_key",
    "commit_marker_key",
    "prefix_for_tenant",
    "find_committed_tip",
    "fetch_segment_bytes",
    "archive_ledger_segment",
]
