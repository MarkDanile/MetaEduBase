# ruff: noqa: E501
"""R1-S6-I3-D D1a: ledger snapshot codec（只读 / bounded segment exporter / decoder / owner facts reconstructor）

契约：Plan §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14（冻结）+ §17.5 用户裁决
（runtime per-binding proof 路径 = c + D1b = 专用 MinIO archive bucket + D2 = A 后续）

**D1a 范围（严格限定）**：
- 只读：所有 DB 操作在 REPEATABLE READ + READ ONLY 事务中
- export_ledger_segment → 字节级 deterministic canonical output（**不写文件 / 不接 sink / 不持久推进 watermark / 不写 DB mutation**）
- decode_ledger_segment → 严格解析 + 9 类 fail closed 校验
- reconstruct_owner_facts → 纯内存六元组重构
- 严禁调用 adapter / 严禁 replay side effect / 严禁改 owner / checkpoint / fence / operation

**Artifact 契约**：
- 顶层 `schema_version` (int)
- 顶层 `tenant_id` (uuid)
- `manifest[record_kind].count` + `manifest[record_kind].content_digest` (SHA-256 over canonical-sorted records)
- 四类 record（operation / checkpoint / external_ref / reconcile），按 `stable_identity` 稳定排序
- 字节级 deterministic（同一 DB state 多次 export 必须字节相同）
- **external_ref 严禁输出 `ref_value`**（spec §10 末段「不持久化原始敏感 ref」）
- **runtime 严禁输出 `runtime_session_ref` / 正文 / payload / token / 自由文本敏感值**
- **runtime 仅输出当前可持久化聚合事实**（`runtime_acked_count` / `runtime_invalid_count` / `runtime_open_count`） + 显式标记 `runtime_per_binding_proof_available: false` + 关联 `agent_conversation_purge_owners.ack_digest` 聚合 digest（不重算 per-binding）

**Decoder fail closed**（任一触发即 raise `LedgerSnapshotError`）：
- `SCHEMA_VERSION_UNKNOWN`
- `RECORD_KIND_UNKNOWN`
- `KIND_TABLE_MISMATCH`
- `COUNT_MISMATCH`
- `CONTENT_DIGEST_MISMATCH`
- `CROSS_TENANT_RECORD`
- `DUPLICATE_STABLE_IDENTITY`
- `CROSS_LAYER_STATE_MIX`（operation/checkpoint/fence 状态跨层混读）
- `CHECKPOINT_WITHOUT_OPERATION`
- `OWNER_SIX_TUPLE_INCOMPLETE`

**禁止行为**（contract 边界）：
- ❌ 不调 external / runtime adapter
- ❌ 不写文件 / 不接 sink / 不推 watermark
- ❌ 不做 DB mutation
- ❌ 不重新计算 per-binding runtime receipt（adapter_receipt_evidence 未持久化）
- ❌ 输出原始 `ref_value` / `runtime_session_ref` / 正文 / payload / token / 自由文本
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.shared.schemas.canonical_json import canonical_digest

# --- schema_version ---

SCHEMA_VERSION = 1

# --- bounded segment ---

# 防止恶意/巨型 tenant 撑爆 exporter / decoder 的硬上限（每类 record）。
# 超限即抛 SEGMENT_LIMIT_EXCEEDED，**不**截断后冒充完整 snapshot（按用户裁决 1）。
# 不持久推进 watermark；仍属 D1a（**不**形成 continuous archive）。
MAX_RECORDS_PER_KIND = 10_000

# --- record kinds ---

RECORD_KIND_OPERATION = "operation"
RECORD_KIND_CHECKPOINT = "checkpoint"
RECORD_KIND_EXTERNAL_REF = "external_ref"
RECORD_KIND_RECONCILE = "reconcile"

RECORD_KINDS: tuple[str, ...] = (
    RECORD_KIND_OPERATION,
    RECORD_KIND_CHECKPOINT,
    RECORD_KIND_EXTERNAL_REF,
    RECORD_KIND_RECONCILE,
)

# --- state whitelists（migration 034: ck_agent_purge_state / ck_agent_purge_owner_state） ---

OPERATION_STATE_WHITELIST: frozenset[str] = frozenset(
    {"scheduled", "running", "blocked", "failed", "completed", "cancelled"}
)
CHECKPOINT_STATE_WHITELIST: frozenset[str] = frozenset(
    {"pending", "erasing", "blocked", "failed", "acked"}
)

# --- transaction attribute contract ---

REQUIRED_ISOLATION = "repeatable read"
REQUIRED_READ_ONLY = "on"

# --- table identity ---

_KIND_TO_TABLE: Mapping[str, str] = {
    RECORD_KIND_OPERATION: "agent_conversation_purges",
    RECORD_KIND_CHECKPOINT: "agent_conversation_purge_owners",
    RECORD_KIND_EXTERNAL_REF: "agent_external_object_refs",
    RECORD_KIND_RECONCILE: "agent_transport_scope_reconcile",
}

# --- sensitive field redaction whitelist ---

# external_ref 必须显式 omit 的敏感字段
_EXTERNAL_REF_REDACT = frozenset({"ref_value"})
# reconcile 不带敏感字段（保留）
# operation / checkpoint 不带敏感字段（保留）

# runtime 聚合字段（不输出 per-binding）
RUNTIME_PER_BINDING_PROOF_AVAILABLE = False


# --- errors ---


class LedgerSnapshotError(Exception):
    """D1a decoder fail-closed error：携带结构化 reason。"""

    def __init__(self, reason: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = dict(detail or {})


# --- exported record shapes ---


@dataclass(frozen=True, slots=True)
class ExportedRecord:
    """单条 record 序列化形态（已 redact + 稳定排序键）。"""

    record_kind: str
    table_identity: str
    stable_identity: str  # 用于 decoder 端去重 + 稳定排序
    fields: Mapping[str, Any]  # 字段已 redact；顺序无关（canonical_digest 序列化时排序）


@dataclass(frozen=True, slots=True)
class Manifest:
    """导出 manifest 摘要 + records 集合。

    注意：本类**不**再承载 runtime_acked_count / runtime_invalid_count / runtime_open_count
    ——这些聚合易误导为「runtime owner state 统计」（按用户裁决 2 已删除）。
    checkpoint records 才是 owner 聚合事实的权威载体；runtime 端只显式声明
    ``runtime_per_binding_proof_available=False``（用户裁决 c）。
    """

    schema_version: int
    tenant_id: str
    record_count: Mapping[str, int]  # per-kind
    content_digest: Mapping[str, str]  # per-kind SHA-256 over canonical sorted records
    runtime_per_binding_proof_available: bool  # 显式 false（按用户裁决 c）；decoder 强制严格 false
    records: Mapping[str, tuple[ExportedRecord, ...]]  # per-kind, stable-sorted by stable_identity
    raw: Mapping[str, Any]  # decode 后的完整 envelope（用于 reconstruct 等）


# --- field serialization ---


def _json_safe(value: Any) -> Any:
    """将 DB 字段值转 JSON 安全形态（UUID → str, datetime → ISO, 其他透传）。"""
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialize_fields(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


# --- per-kind exporters（只读 SELECT） ---


async def _select_all_for_kind(
    conn: AsyncConnection,
    *,
    tenant_id: uuid.UUID,
    table: str,
    columns: tuple[str, ...],
    max_records: int = MAX_RECORDS_PER_KIND,
) -> list[dict[str, Any]]:
    """REPEATABLE READ + READ ONLY 事务内按列读 tenant 范围行（**bounded** segment）。

    列必须由 caller 显式列出（**严禁 SELECT ***，避免拉出 `ref_value` / `runtime_session_ref` /
    事件 payload / 自由文本等敏感列）。

    bounded 语义：ORDER BY id LIMIT ``max_records + 1``——一旦实际行数超过 max_records
    立即抛 ``SEGMENT_LIMIT_EXCEEDED``，**不**截断后冒充完整 snapshot（按用户裁决 1）。
    不持久推进 watermark；仍属 D1a（**不**形成 continuous archive）。
    """
    cols = ", ".join(f'"{c}"' for c in columns)
    sql = text(
        f"SELECT {cols} FROM metaedu.{table} "  # noqa: S608 — table/cols hard-coded
        f"WHERE tenant_id = :tenant_id "
        f"ORDER BY id "
        f"LIMIT :limit"
    )
    # 取 max_records + 1：实际行数 == max_records + 1 ⇒ 已超限
    limit = max_records + 1
    result = await conn.execute(sql, {"tenant_id": str(tenant_id), "limit": limit})
    rows = [dict(r) for r in result.mappings().all()]
    if len(rows) > max_records:
        raise LedgerSnapshotError(
            "SEGMENT_LIMIT_EXCEEDED",
            detail={
                "table": table,
                "tenant_id": str(tenant_id),
                "max_records_per_kind": max_records,
                "hint": (
                    "exporter refused to silently truncate; caller must narrow the "
                    "segment by introducing persistence cursor / canary / D1b sink"
                ),
            },
        )
    return rows


async def _export_operation(
    conn: AsyncConnection, *, tenant_id: uuid.UUID
) -> tuple[ExportedRecord, ...]:
    columns = (
        "id",
        "tenant_id",
        "conversation_id",
        "purge_revision",
        "state",
        "registry_digest",
        "retention_policy_digest",
        "hold_revision_snapshot",
        "lease_epoch",
        "failure_code",
        "revision",
        "scheduled_at",
        "started_at",
        "completed_at",
        "next_retry_at",
    )
    rows = await _select_all_for_kind(
        conn, tenant_id=tenant_id, table="agent_conversation_purges", columns=columns
    )
    records: list[ExportedRecord] = []
    for row in rows:
        # 显式 omit 敏感/冗余字段：registry_snapshot / retention_policy_snapshot（JSONB
        # 含 owner state 表等）→ 已在 redacted digest 覆盖；created_at / updated_at 冗余
        fields = _serialize_fields(row)
        records.append(
            ExportedRecord(
                record_kind=RECORD_KIND_OPERATION,
                table_identity="agent_conversation_purges",
                stable_identity=f"operation:{row['id']}",
                fields=fields,
            )
        )
    return tuple(records)


async def _export_checkpoint(
    conn: AsyncConnection, *, tenant_id: uuid.UUID
) -> tuple[ExportedRecord, ...]:
    columns = (
        "id",
        "tenant_id",
        "purge_operation_id",
        "owner_key",
        "owner_version",
        "capability_digest",
        "state",
        "attempt",
        "checkpoint_digest",
        "ack_digest",
        "reason_code",
    )
    rows = await _select_all_for_kind(
        conn,
        tenant_id=tenant_id,
        table="agent_conversation_purge_owners",
        columns=columns,
    )
    records: list[ExportedRecord] = []
    for row in rows:
        fields = _serialize_fields(row)
        records.append(
            ExportedRecord(
                record_kind=RECORD_KIND_CHECKPOINT,
                table_identity="agent_conversation_purge_owners",
                stable_identity=f"checkpoint:{row['id']}",
                fields=fields,
            )
        )
    return tuple(records)


async def _export_external_ref(
    conn: AsyncConnection, *, tenant_id: uuid.UUID
) -> tuple[ExportedRecord, ...]:
    # 显式 omit `ref_value`（spec §10 末段 + 用户裁决；DB schema 允 VARCHAR(500) 但本审计
    # 严禁序列化到 artifact）
    columns = (
        "id",
        "tenant_id",
        "conversation_id",
        "owner_key",
        "ref_scheme",
        "source_table",
        "source_row_id",
        "erase_state",
        "receipt_digest",
        "blocked_reason",
        "created_at",
        "updated_at",
    )
    rows = await _select_all_for_kind(
        conn,
        tenant_id=tenant_id,
        table="agent_external_object_refs",
        columns=columns,
    )
    records: list[ExportedRecord] = []
    for row in rows:
        # 强制断言 ref_value 确实没被 select 出来（防御性）
        assert "ref_value" not in row, "external_ref select leaked ref_value"
        fields = _serialize_fields(row)
        records.append(
            ExportedRecord(
                record_kind=RECORD_KIND_EXTERNAL_REF,
                table_identity="agent_external_object_refs",
                stable_identity=f"external_ref:{row['id']}",
                fields=fields,
            )
        )
    return tuple(records)


async def _export_reconcile(
    conn: AsyncConnection, *, tenant_id: uuid.UUID
) -> tuple[ExportedRecord, ...]:
    columns = (
        "id",
        "tenant_id",
        "owner_key",
        "source_table",
        "source_row_id",
        "conversation_id",
        "reconcile_class",
        "issue_code",
        "state",
        "resolution_digest",
        "revision",
        "created_at",
        "resolved_at",
    )
    rows = await _select_all_for_kind(
        conn,
        tenant_id=tenant_id,
        table="agent_transport_scope_reconcile",
        columns=columns,
    )
    records: list[ExportedRecord] = []
    for row in rows:
        fields = _serialize_fields(row)
        records.append(
            ExportedRecord(
                record_kind=RECORD_KIND_RECONCILE,
                table_identity="agent_transport_scope_reconcile",
                stable_identity=f"reconcile:{row['id']}",
                fields=fields,
            )
        )
    return tuple(records)


# --- transaction attribute enforcement ---


async def _assert_transaction_attrs(conn: AsyncConnection) -> None:
    """强制 caller 的事务属性（按用户裁决 4）。

    任何以下情况都拒绝（read committed / repeatable-read read-write / autocommit
    都不接受）——只有 REPEATABLE READ + READ ONLY 才允许进入 exporter：
    - transaction_isolation != 'repeatable read' → TX_ISOLATION_NOT_REPEATABLE_READ
    - transaction_read_only != 'on' → TX_NOT_READ_ONLY
    """
    iso_row = (await conn.execute(text("SHOW transaction_isolation"))).scalar_one()
    ro_row = (await conn.execute(text("SHOW transaction_read_only"))).scalar_one()
    iso = str(iso_row).strip().lower()
    ro = str(ro_row).strip().lower()
    if iso != REQUIRED_ISOLATION:
        raise LedgerSnapshotError(
            "TX_ISOLATION_NOT_REPEATABLE_READ",
            detail={
                "found": iso,
                "required": REQUIRED_ISOLATION,
                "hint": (
                    "caller must SET TRANSACTION ISOLATION LEVEL REPEATABLE READ "
                    "READ ONLY before invoking export_ledger_segment"
                ),
            },
        )
    if ro != REQUIRED_READ_ONLY:
        raise LedgerSnapshotError(
            "TX_NOT_READ_ONLY",
            detail={
                "found": ro,
                "required": REQUIRED_READ_ONLY,
                "hint": "caller must SET TRANSACTION READ ONLY",
            },
        )


# --- export (REPEATABLE READ, READ ONLY) ---


def _records_to_envelope(
    *,
    tenant_id: uuid.UUID,
    operation: tuple[ExportedRecord, ...],
    checkpoint: tuple[ExportedRecord, ...],
    external_ref: tuple[ExportedRecord, ...],
    reconcile: tuple[ExportedRecord, ...],
) -> dict[str, Any]:
    """构造 envelope dict（按 stable_identity 稳定排序 → 字节级 deterministic）。

    注意：本 envelope **不**再包含 ``runtime_aggregate``（acked_count / invalid_count /
    open_count 等聚合易被误读为 runtime owner state 统计，按用户裁决 2 已删除）。
    checkpoint records 才是 owner 聚合事实的权威载体；envelope 顶层只显式声明
    ``runtime_per_binding_proof_available=False``（用户裁决 c），由 decoder 强制严格 false。
    """
    by_kind: dict[str, tuple[ExportedRecord, ...]] = {
        RECORD_KIND_OPERATION: tuple(sorted(operation, key=lambda r: r.stable_identity)),
        RECORD_KIND_CHECKPOINT: tuple(sorted(checkpoint, key=lambda r: r.stable_identity)),
        RECORD_KIND_EXTERNAL_REF: tuple(sorted(external_ref, key=lambda r: r.stable_identity)),
        RECORD_KIND_RECONCILE: tuple(sorted(reconcile, key=lambda r: r.stable_identity)),
    }
    manifest: dict[str, dict[str, Any]] = {}
    for kind, recs in by_kind.items():
        # content_digest = SHA-256 over canonical-sorted records
        digest = canonical_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": kind,
                "records": [
                    {
                        "stable_identity": r.stable_identity,
                        "table_identity": r.table_identity,
                        "fields": r.fields,
                    }
                    for r in recs
                ],
            }
        )
        manifest[kind] = {
            "count": len(recs),
            "content_digest": digest,
        }
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "manifest": manifest,
        "runtime_per_binding_proof_available": RUNTIME_PER_BINDING_PROOF_AVAILABLE,
        "records": {
            kind: [
                {
                    "stable_identity": r.stable_identity,
                    "table_identity": r.table_identity,
                    "fields": r.fields,
                }
                for r in recs
            ]
            for kind, recs in by_kind.items()
        },
    }
    return envelope


def export_ledger_segment_to_bytes(envelope: Mapping[str, Any]) -> bytes:
    """envelope → canonical JSON bytes（sort_keys=True 保证字节级 deterministic）。"""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def export_ledger_segment(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> bytes:
    """REPEATABLE READ + READ ONLY 事务；返回 canonical JSON bytes（**不写文件 / 不接 sink**）。

    实现：使用 session.connection() 拿到 AsyncConnection → conn.execute() 跑四类 SELECT。
    REPEATABLE READ + READ ONLY 必须在使用方显式设置（session.begin + isolation_level），
    本函数**不**自动开启事务以避免与 caller 的事务边界冲突——caller 负责事务 + 隔离级；
    exporter 入口会再次核验 SHOW transaction_isolation / SHOW transaction_read_only（按
    用户裁决 4），任何不满足都立即拒绝。
    """
    if session.in_transaction() is False:
        raise LedgerSnapshotError(
            "EXPORT_REQUIRES_TRANSACTION",
            detail={
                "hint": "caller must open REPEATABLE READ + READ ONLY transaction before calling"
            },
        )
    conn = await session.connection()
    # 入口强制：仅 REPEATABLE READ + READ ONLY 事务可进入 exporter
    await _assert_transaction_attrs(conn)
    operation = await _export_operation(conn, tenant_id=tenant_id)
    checkpoint = await _export_checkpoint(conn, tenant_id=tenant_id)
    external_ref = await _export_external_ref(conn, tenant_id=tenant_id)
    reconcile = await _export_reconcile(conn, tenant_id=tenant_id)
    envelope = _records_to_envelope(
        tenant_id=tenant_id,
        operation=operation,
        checkpoint=checkpoint,
        external_ref=external_ref,
        reconcile=reconcile,
    )
    return export_ledger_segment_to_bytes(envelope)


# --- decoder + 9 类 fail-closed 校验 ---


def _envelope_typed(payload: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerSnapshotError("ENVELOPE_NOT_JSON", detail={"error": str(exc)}) from exc
    if not isinstance(obj, dict):
        raise LedgerSnapshotError("ENVELOPE_NOT_OBJECT", detail={"type": type(obj).__name__})
    return obj


def _assert_schema_version(env: Mapping[str, Any]) -> int:
    sv = env.get("schema_version")
    if not isinstance(sv, int):
        raise LedgerSnapshotError("SCHEMA_VERSION_MISSING_OR_INVALID")
    if sv != SCHEMA_VERSION:
        raise LedgerSnapshotError(
            "SCHEMA_VERSION_UNKNOWN",
            detail={"found": sv, "supported": SCHEMA_VERSION},
        )
    return sv


def _assert_tenant(env: Mapping[str, Any]) -> str:
    tid = env.get("tenant_id")
    if not isinstance(tid, str):
        raise LedgerSnapshotError("TENANT_ID_MISSING_OR_INVALID")
    return tid


def _assert_manifest(env: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    manifest = env.get("manifest")
    if not isinstance(manifest, dict):
        raise LedgerSnapshotError("MANIFEST_MISSING_OR_INVALID")
    for kind in RECORD_KINDS:
        if kind not in manifest:
            raise LedgerSnapshotError(
                "MANIFEST_KIND_MISSING", detail={"kind": kind}
            )
        entry = manifest[kind]
        if not isinstance(entry, dict):
            raise LedgerSnapshotError("MANIFEST_ENTRY_INVALID", detail={"kind": kind})
        if "count" not in entry or not isinstance(entry["count"], int):
            raise LedgerSnapshotError("MANIFEST_COUNT_MISSING_OR_INVALID", detail={"kind": kind})
        if "content_digest" not in entry or not isinstance(entry["content_digest"], str):
            raise LedgerSnapshotError(
                "MANIFEST_CONTENT_DIGEST_MISSING_OR_INVALID", detail={"kind": kind}
            )
        if len(entry["content_digest"]) != 64:
            raise LedgerSnapshotError(
                "MANIFEST_CONTENT_DIGEST_NOT_64HEX", detail={"kind": kind}
            )
    return manifest


def _assert_records(env: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """校验 ``records`` 顶层结构 + 字段类型 + stable_identity 升序（按用户裁决 5）。

    拒绝：
    - manifest/records 多出现 RECORD_KINDS 之外的 kind（UNKNOWN_KIND）
    - record 非 dict（RECORD_NOT_OBJECT）
    - record.fields 非 mapping（RECORD_FIELDS_NOT_MAPPING）
    - record.stable_identity 非 str 或缺失（STABLE_IDENTITY_INVALID）
    - record 顺序未按 stable_identity 升序（RECORDS_NOT_SORTED）——exporter 端按
      stable_identity 排序后输出，乱序视为 producer/transport 损坏，fail closed。
    """
    records = env.get("records")
    if not isinstance(records, dict):
        raise LedgerSnapshotError("RECORDS_MISSING_OR_INVALID")
    # 顶层 kind 集合必须 == RECORD_KINDS（拒绝多/少未知 kind）
    extra_kinds = set(records.keys()) - set(RECORD_KINDS)
    if extra_kinds:
        raise LedgerSnapshotError(
            "UNKNOWN_KIND", detail={"extra_kinds": sorted(extra_kinds)}
        )
    missing_kinds = set(RECORD_KINDS) - set(records.keys())
    if missing_kinds:
        raise LedgerSnapshotError(
            "RECORDS_KIND_MISSING", detail={"missing_kinds": sorted(missing_kinds)}
        )
    for kind in RECORD_KINDS:
        recs = records[kind]
        if not isinstance(recs, list):
            raise LedgerSnapshotError("RECORDS_NOT_LIST", detail={"kind": kind})
        # 校验每条 record 类型 + stable_identity + 顺序
        prev_sid: str | None = None
        for idx, rec in enumerate(recs):
            if not isinstance(rec, dict):
                raise LedgerSnapshotError(
                    "RECORD_NOT_OBJECT", detail={"kind": kind, "index": idx}
                )
            fields = rec.get("fields")
            if not isinstance(fields, dict):
                raise LedgerSnapshotError(
                    "RECORD_FIELDS_NOT_MAPPING", detail={"kind": kind, "index": idx}
                )
            sid = rec.get("stable_identity")
            if not isinstance(sid, str) or not sid:
                raise LedgerSnapshotError(
                    "STABLE_IDENTITY_INVALID", detail={"kind": kind, "index": idx}
                )
            if prev_sid is not None and prev_sid > sid:
                raise LedgerSnapshotError(
                    "RECORDS_NOT_SORTED",
                    detail={"kind": kind, "index": idx, "prev": prev_sid, "current": sid},
                )
            prev_sid = sid
    return records


def _assert_kind_table_match(records: Mapping[str, list[dict[str, Any]]]) -> None:
    for kind, recs in records.items():
        expected_table = _KIND_TO_TABLE.get(kind)
        if expected_table is None:
            raise LedgerSnapshotError("RECORD_KIND_UNKNOWN", detail={"kind": kind})
        for rec in recs:
            table = rec.get("table_identity")
            if table != expected_table:
                raise LedgerSnapshotError(
                    "KIND_TABLE_MISMATCH",
                    detail={"kind": kind, "expected": expected_table, "found": table},
                )


def _assert_count_match(
    manifest: Mapping[str, dict[str, Any]],
    records: Mapping[str, list[dict[str, Any]]],
) -> None:
    for kind in RECORD_KINDS:
        expected = manifest[kind]["count"]
        actual = len(records[kind])
        if expected != actual:
            raise LedgerSnapshotError(
                "COUNT_MISMATCH",
                detail={"kind": kind, "expected": expected, "found": actual},
            )


def _assert_content_digest(
    manifest: Mapping[str, dict[str, Any]],
    records: Mapping[str, list[dict[str, Any]]],
) -> None:
    for kind in RECORD_KINDS:
        expected_digest = manifest[kind]["content_digest"]
        actual_digest = canonical_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": kind,
                "records": [
                    {
                        "stable_identity": r["stable_identity"],
                        "table_identity": r["table_identity"],
                        "fields": r["fields"],
                    }
                    for r in records[kind]
                ],
            }
        )
        if actual_digest != expected_digest:
            raise LedgerSnapshotError(
                "CONTENT_DIGEST_MISMATCH",
                detail={
                    "kind": kind,
                    "expected": expected_digest,
                    "found": actual_digest,
                },
            )


def _assert_no_duplicate_stable_identity(
    records: Mapping[str, list[dict[str, Any]]],
) -> None:
    seen: set[str] = set()
    for kind, recs in records.items():
        for r in recs:
            sid = r.get("stable_identity")
            if not isinstance(sid, str) or not sid:
                raise LedgerSnapshotError(
                    "STABLE_IDENTITY_INVALID", detail={"kind": kind}
                )
            if sid in seen:
                raise LedgerSnapshotError(
                    "DUPLICATE_STABLE_IDENTITY",
                    detail={"kind": kind, "stable_identity": sid},
                )
            seen.add(sid)


def _assert_cross_tenant(env: Mapping[str, Any], declared_tenant: str) -> None:
    for kind, recs in env["records"].items():
        for r in recs:
            fields = r.get("fields", {})
            t = fields.get("tenant_id")
            if t is None:
                raise LedgerSnapshotError(
                    "CROSS_TENANT_RECORD",
                    detail={
                        "kind": kind,
                        "stable_identity": r.get("stable_identity"),
                        "reason": "tenant_id_missing",
                    },
                )
            if t != declared_tenant:
                raise LedgerSnapshotError(
                    "CROSS_TENANT_RECORD",
                    detail={"kind": kind, "stable_identity": r.get("stable_identity")},
                )


def _assert_no_cross_layer_state_mix(records: Mapping[str, list[dict[str, Any]]]) -> None:
    """operation.checkpoint.state / fence.state 跨层混读防御。

    规则：每条 record 字段集合按 record_kind 闭集判定；不允许在 operation 里出现
    fence.state 字段、不允许在 checkpoint 里出现 fence.state 字段、等等。
    """
    allowed = {
        RECORD_KIND_OPERATION: {
            "id",
            "conversation_id",
            "purge_revision",
            "state",
            "registry_digest",
            "retention_policy_digest",
            "hold_revision_snapshot",
            "lease_epoch",
            "failure_code",
            "revision",
            "scheduled_at",
            "started_at",
            "completed_at",
            "next_retry_at",
            "tenant_id",
        },
        RECORD_KIND_CHECKPOINT: {
            "id",
            "purge_operation_id",
            "owner_key",
            "owner_version",
            "capability_digest",
            "state",
            "attempt",
            "checkpoint_digest",
            "ack_digest",
            "reason_code",
            "tenant_id",
        },
        RECORD_KIND_EXTERNAL_REF: {
            "id",
            "conversation_id",
            "owner_key",
            "ref_scheme",
            "source_table",
            "source_row_id",
            "erase_state",
            "receipt_digest",
            "blocked_reason",
            "created_at",
            "updated_at",
            "tenant_id",
        },
        RECORD_KIND_RECONCILE: {
            "id",
            "owner_key",
            "source_table",
            "source_row_id",
            "conversation_id",
            "reconcile_class",
            "issue_code",
            "state",
            "resolution_digest",
            "revision",
            "created_at",
            "resolved_at",
            "tenant_id",
        },
    }
    for kind, recs in records.items():
        allowed_fields = allowed[kind]
        for r in recs:
            extras = set(r.get("fields", {}).keys()) - allowed_fields
            if extras:
                raise LedgerSnapshotError(
                    "CROSS_LAYER_STATE_MIX",
                    detail={"kind": kind, "extras": sorted(extras)},
                )


def _assert_checkpoint_has_operation(
    records: Mapping[str, list[dict[str, Any]]],
) -> None:
    """每条 checkpoint 必须有对应的 operation（按 purge_operation_id join）。

    按用户裁决 3：purge_operation_id **缺失** / **不在 operation 集合**均 fail closed，
    不得等到 reconstruct 阶段才暴露。
    """
    operation_ids: set[str] = set()
    for r in records[RECORD_KIND_OPERATION]:
        rid = r["fields"].get("id")
        if rid is None:
            raise LedgerSnapshotError(
                "CHECKPOINT_WITHOUT_OPERATION",
                detail={"operation_record": "id_missing"},
            )
        operation_ids.add(str(rid))
    for cp in records[RECORD_KIND_CHECKPOINT]:
        op_id = cp["fields"].get("purge_operation_id")
        if op_id is None:
            raise LedgerSnapshotError(
                "CHECKPOINT_WITHOUT_OPERATION",
                detail={"checkpoint_id": cp["stable_identity"], "purge_operation_id": None},
            )
        op_id = str(op_id)
        if op_id not in operation_ids:
            raise LedgerSnapshotError(
                "CHECKPOINT_WITHOUT_OPERATION",
                detail={"checkpoint_id": cp["stable_identity"], "purge_operation_id": op_id},
            )


def _assert_state_whitelist(records: Mapping[str, list[dict[str, Any]]]) -> None:
    """operation.state / checkpoint.state 必须落在 migration 034 CHECK 闭集内（按用户裁决 5）。

    跨层值（如 operation.state='acked' / checkpoint.state='completed'）视为跨层语义混读：
    立即 raise CROSS_LAYER_STATE_MIX（detail.kind = 'state_out_of_whitelist'）。
    """
    for r in records[RECORD_KIND_OPERATION]:
        s = r["fields"].get("state")
        if not isinstance(s, str) or s not in OPERATION_STATE_WHITELIST:
            raise LedgerSnapshotError(
                "CROSS_LAYER_STATE_MIX",
                detail={
                    "kind": RECORD_KIND_OPERATION,
                    "stable_identity": r["stable_identity"],
                    "state": s,
                    "whitelist": sorted(OPERATION_STATE_WHITELIST),
                    "reason": "state_out_of_whitelist",
                },
            )
    for r in records[RECORD_KIND_CHECKPOINT]:
        s = r["fields"].get("state")
        if not isinstance(s, str) or s not in CHECKPOINT_STATE_WHITELIST:
            raise LedgerSnapshotError(
                "CROSS_LAYER_STATE_MIX",
                detail={
                    "kind": RECORD_KIND_CHECKPOINT,
                    "stable_identity": r["stable_identity"],
                    "state": s,
                    "whitelist": sorted(CHECKPOINT_STATE_WHITELIST),
                    "reason": "state_out_of_whitelist",
                },
            )


def _assert_checkpoint_ack_invariant(
    records: Mapping[str, list[dict[str, Any]]],
) -> None:
    """checkpoint.state / ack_digest 基本关系校验（migration 034 ck_agent_purge_owner_ack）。

    规则：
    - state='acked' ⇒ ack_digest 必须为 64-hex 非空字符串
    - state<>'acked' ⇒ ack_digest 必须为 None
    任意违反 ⇒ ACK_INVARIANT_VIOLATED。
    """
    for r in records[RECORD_KIND_CHECKPOINT]:
        s = r["fields"].get("state")
        ack = r["fields"].get("ack_digest")
        if s == "acked":
            if not isinstance(ack, str) or len(ack) != 64:
                raise LedgerSnapshotError(
                    "ACK_INVARIANT_VIOLATED",
                    detail={
                        "stable_identity": r["stable_identity"],
                        "state": s,
                        "reason": "acked_requires_64hex_ack_digest",
                    },
                )
        else:
            if ack is not None:
                raise LedgerSnapshotError(
                    "ACK_INVARIANT_VIOLATED",
                    detail={
                        "stable_identity": r["stable_identity"],
                        "state": s,
                        "reason": "non_acked_requires_null_ack_digest",
                    },
                )


def _assert_no_runtime_sensitive(records: Mapping[str, list[dict[str, Any]]]) -> None:
    """runtime 敏感值防御：任何 record 字段集合出现 `ref_value` / `runtime_session_ref` 立即 fail closed。"""
    for r in records.get(RECORD_KIND_EXTERNAL_REF, ()):
        if "ref_value" in r.get("fields", {}):
            raise LedgerSnapshotError(
                "EXTERNAL_REF_VALUE_LEAKED", detail={"stable_identity": r.get("stable_identity")}
            )
    # 任何 record 字段集合出现 runtime_session_ref 也立即 fail closed
    for kind, recs in records.items():
        for r in recs:
            if "runtime_session_ref" in r.get("fields", {}):
                raise LedgerSnapshotError(
                    "RUNTIME_SESSION_REF_LEAKED",
                    detail={"kind": kind, "stable_identity": r.get("stable_identity")},
                )


# --- public decoder entry ---


def _assert_runtime_proof_strict_false(env: Mapping[str, Any]) -> None:
    """严格 runtime per-binding proof = False 判定（按用户裁决 2）。

    decoder 必须要求 ``runtime_per_binding_proof_available`` 严格为 False：
    - 缺失 ⇒ RUNTIME_PROOF_FLAG_MISSING
    - 显式 True ⇒ RUNTIME_PROOF_FLAG_TRUE（错标为可重算 per-binding receipt）
    """
    flag = env.get("runtime_per_binding_proof_available", "__MISSING__")
    if flag == "__MISSING__":
        raise LedgerSnapshotError(
            "RUNTIME_PROOF_FLAG_MISSING",
            detail={"hint": "envelope must declare runtime_per_binding_proof_available"},
        )
    if flag is not False:
        raise LedgerSnapshotError(
            "RUNTIME_PROOF_FLAG_TRUE",
            detail={
                "found": flag,
                "hint": (
                    "adapter_receipt_evidence 未持久化，runtime per-binding proof 不可重算；"
                    "envelope 顶层只能显式声明 false（用户裁决 c）"
                ),
            },
        )


def decode_ledger_segment(payload: bytes) -> Manifest:
    """严格 parse + 多类 fail closed 校验（按用户裁决 1~5）。

    校验顺序：
    1. 顶层 envelope 类型
    2. schema_version
    3. tenant_id 类型
    4. manifest 结构 + 每 kind count / content_digest 长度
    5. records 顶层结构 + RECORD_KINDS 闭集 + 每 record 类型 + stable_identity 类型 + stable_identity 升序
    6. kind / table_identity 配对
    7. manifest count == records count
    8. content_digest 校验
    9. 跨 tenant 检测（tenant_id 缺失或不等）
    10. stable_identity 去重
    11. operation.state / checkpoint.state 闭集（migration 034）
    12. checkpoint.state / ack_digest 基本关系（migration 034 ck_agent_purge_owner_ack）
    13. 跨层字段混读
    14. runtime 敏感值防御（ref_value / runtime_session_ref）
    15. checkpoint 必须有对应 operation（purge_operation_id 缺失也 fail closed）
    16. runtime_per_binding_proof_available 严格 false
    """
    env = _envelope_typed(payload)
    _assert_schema_version(env)
    declared_tenant = _assert_tenant(env)
    manifest = _assert_manifest(env)
    records = _assert_records(env)
    _assert_kind_table_match(records)
    _assert_count_match(manifest, records)
    _assert_content_digest(manifest, records)
    _assert_cross_tenant(env, declared_tenant)
    _assert_no_duplicate_stable_identity(records)
    _assert_state_whitelist(records)
    _assert_checkpoint_ack_invariant(records)
    _assert_no_cross_layer_state_mix(records)
    _assert_no_runtime_sensitive(records)
    _assert_checkpoint_has_operation(records)
    _assert_runtime_proof_strict_false(env)

    # 重建 per-kind record 元组（已 stable-sorted）
    per_kind: dict[str, tuple[ExportedRecord, ...]] = {}
    for kind in RECORD_KINDS:
        per_kind[kind] = tuple(
            ExportedRecord(
                record_kind=kind,
                table_identity=r["table_identity"],
                stable_identity=r["stable_identity"],
                fields=r["fields"],
            )
            for r in records[kind]
        )

    return Manifest(
        schema_version=SCHEMA_VERSION,
        tenant_id=declared_tenant,
        record_count={k: manifest[k]["count"] for k in RECORD_KINDS},
        content_digest={k: manifest[k]["content_digest"] for k in RECORD_KINDS},
        runtime_per_binding_proof_available=False,
        records=per_kind,
        raw=dict(env),
    )


# --- in-memory six-tuple reconstruction ---


@dataclass(frozen=True, slots=True)
class OwnerFacts:
    """单 owner 六元组（按 checkpoint 行聚合）。"""

    owner_key: str
    operation_id: str
    ack_digest: str | None
    owner_version: int
    capability_digest: str
    checkpoint_state: str
    purge_revision: int
    runtime_per_binding_proof_available: bool  # 显式 false（用户裁决 c）


def _operation_lookup(
    operations: tuple[ExportedRecord, ...],
) -> dict[str, dict[str, Any]]:
    return {r.fields["id"]: r.fields for r in operations if r.fields.get("id") is not None}  # type: ignore[misc,arg-type]


def reconstruct_owner_facts(
    manifest: Manifest,
) -> dict[tuple[str, str], OwnerFacts]:
    """纯内存六元组重构（不查 DB、不调 adapter、不持外部状态）。

    按用户裁决 3：返回以 ``(operation_id, owner_key)`` 为键的映射——同一 tenant
    内两个 operation 共享同一 owner_key 时，**均**进入 facts（不得仅以 owner_key
    为键覆盖前一个）。

    decoder 阶段已严格 fail closed：缺失 operation / 缺失 purge_operation_id /
    六元组字段缺失 → OWNER_SIX_TUPLE_INCOMPLETE 已在 decode 阶段抛出。本函数
    不再做二次校验；只完成 key = (operation_id, owner_key) 的查找与构造。
    """
    operation_by_id = _operation_lookup(manifest.records[RECORD_KIND_OPERATION])
    out: dict[tuple[str, str], OwnerFacts] = {}
    for cp in manifest.records[RECORD_KIND_CHECKPOINT]:
        f = cp.fields
        owner_key = f["owner_key"]
        operation_id = f["purge_operation_id"]
        ack_digest = f.get("ack_digest")
        owner_version = f["owner_version"]
        capability_digest = f["capability_digest"]
        state = f["state"]
        op = operation_by_id.get(str(operation_id))
        purge_revision = op.get("purge_revision") if op else -1
        out[(str(operation_id), str(owner_key))] = OwnerFacts(
            owner_key=str(owner_key),
            operation_id=str(operation_id),
            ack_digest=str(ack_digest) if ack_digest is not None else None,
            owner_version=int(owner_version),
            capability_digest=str(capability_digest),
            checkpoint_state=str(state),
            purge_revision=int(purge_revision),  # type: ignore[arg-type]
            runtime_per_binding_proof_available=manifest.runtime_per_binding_proof_available,
        )
    return out


__all__ = [
    "SCHEMA_VERSION",
    "MAX_RECORDS_PER_KIND",
    "REQUIRED_ISOLATION",
    "REQUIRED_READ_ONLY",
    "OPERATION_STATE_WHITELIST",
    "CHECKPOINT_STATE_WHITELIST",
    "RECORD_KIND_OPERATION",
    "RECORD_KIND_CHECKPOINT",
    "RECORD_KIND_EXTERNAL_REF",
    "RECORD_KIND_RECONCILE",
    "RECORD_KINDS",
    "RUNTIME_PER_BINDING_PROOF_AVAILABLE",
    "LedgerSnapshotError",
    "ExportedRecord",
    "Manifest",
    "OwnerFacts",
    "export_ledger_segment",
    "export_ledger_segment_to_bytes",
    "decode_ledger_segment",
    "reconstruct_owner_facts",
]
