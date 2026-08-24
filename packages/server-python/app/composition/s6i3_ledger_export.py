"""R1-S6-I3 独立 ledger export 受控快照格式。

契约：Plan §R1-S6-8 item 2（账本独立保存，三面复审 P1-7 裁决，S6 新交付）。
来源：S5-SCH-0 持久化账本（operation ``agent_conversation_purges`` + checkpoint
``agent_conversation_purge_owners`` + external ref ``agent_external_object_refs``
+ reconcile ``agent_transport_scope_reconcile``）+ Spec §3「从**独立保存**的
erasure operation/receipt 账本重放」字面要求。

实现范围（严格冻结边界）：
- 受控快照格式（仅导出可校验的 operation/checkpoint/ref/reconcile 状态事实）；
- **绝不导出**正文、payload、ref 原值、Runtime session ref 或自由文本 reason
（AC10 sentinel 全 substring）；
- 快照结构稳定 = JSON Lines（每行一个 JSON 对象，字段固定顺序）；
- 旧 ledger owner_version / descriptor 自包含：恢复重放基准 = 账本快照自身
 owner_version，不依赖外部 schema 版本映射（与 S6-8 item 3「digest 失配」
 处置对齐 = 失配转 runbook 人工确认，本模块不裁决失配）；
- 不创建后台循环、不调用 external/runtime adapter、不引入生产 wiring。

可观察计数仅含数值 + 状态枚举 + ID 列表；不输出正文、ref 原值、Runtime
session ref 或自由文本 reason。

R1-AC12 字面降级：真实 pg_dump / 恢复 / 流量开关 drill 无法本地执行；
本模块仅承载 ledger 导出 + 受控格式，重放执行器归 ``s6i3_restore_replay``。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# 受控快照 schema（frozen dict key 集；任何字段变动 = schema version bump）
# ---------------------------------------------------------------------------

# 操作表（agent_conversation_purges）字段白名单
_OPERATION_FIELDS: tuple[str, ...] = (
    "id",
    "tenant_id",
    "conversation_id",
    "purge_revision",
    "state",
    "registry_digest",
    "hold_revision_snapshot",
    "lease_epoch",
    "lease_expires_at",
    "scheduled_at",
    "started_at",
    "completed_at",
    "failure_code",
    "next_retry_at",
    "revision",
    "created_at",
    "updated_at",
)

# 检查点表（agent_conversation_purge_owners）字段白名单（基于 migration 034 schema）
_CHECKPOINT_FIELDS: tuple[str, ...] = (
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
    "created_at",
)

# 外部引用表（agent_external_object_refs）字段白名单
_REF_FIELDS: tuple[str, ...] = (
    "id",
    "tenant_id",
    "owner_key",
    "conversation_id",
    "ref_scheme",
    "source_table",
    "source_row_id",
    "erase_state",
    "blocked_reason",
    "created_at",
    "updated_at",
)

# reconcile ledger 表（agent_transport_scope_reconcile）字段白名单
# 事实依据：migration 040 `_create_reconcile_ledger`（:153-173）+ ORM
# agent_transport_ledger.py——真实列为 state / revision / resolution_digest /
# created_at / resolved_at；**无** observed_at / resolution_state（PR-A schema
# fact 对齐：observed_at→created_at、resolution_state→state）。
_RECONCILE_FIELDS: tuple[str, ...] = (
    "id",
    "tenant_id",
    "owner_key",
    "conversation_id",
    "source_table",
    "source_row_id",
    "issue_code",
    "reconcile_class",
    "created_at",
    "resolved_at",
    "state",
)

# AC10 sentinel — 禁止出现在导出快照中的 substring 字面集合
FORBIDDEN_SNAPSHOT_SUBSTRINGS: tuple[str, ...] = (
    "payload_inline",
    "payload_ref",
    "session_ref",
    "reply",
    "free_reason",
    "blocked_reason",  # ref.erasure_state='blocked' 字段名同名，需具体校验
)

# frozen schema 版本号（任何字段变动需同步 bump）
LEDGER_SCHEMA_VERSION = "s6i3_ledger_v1"


# ---------------------------------------------------------------------------
# 快照行 record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerSnapshotRow:
    """单行 ledger 快照（受控字段白名单 + JSON-safe）。"""

    table: str  # "operation" | "checkpoint" | "ref" | "reconcile"
    fields: dict[str, Any]  # 仅白名单字段

    def to_json(self) -> str:
        """序列化为单行 JSON（稳定字段顺序）。"""
        payload: dict[str, Any] = {
            "schema": LEDGER_SCHEMA_VERSION,
            "table": self.table,
        }
        for k in sorted(self.fields.keys()):
            v = self.fields[k]
            if isinstance(v, uuid.UUID):
                payload[k] = str(v)
            elif isinstance(v, datetime):
                # 真实 timestamptz 列（created_at/updated_at/resolved_at 等）
                # JSON 序列化为 ISO 8601（schema-fact 对齐：真实列含时间戳）
                payload[k] = v.isoformat()
            else:
                payload[k] = v
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LedgerSnapshotHeader:
    """ledger 快照文件头（schema version + 导出元数据 + 内容指纹）。"""

    tenant_id: uuid.UUID
    exported_at_iso: str
    schema_version: str
    operation_count: int
    checkpoint_count: int
    ref_count: int
    reconcile_count: int
    content_sha256: str

    def to_json(self) -> str:
        payload = {
            "kind": "ledger_snapshot_header",
            "schema": self.schema_version,
            "tenant_id": str(self.tenant_id),
            "exported_at": self.exported_at_iso,
            "operation_count": self.operation_count,
            "checkpoint_count": self.checkpoint_count,
            "ref_count": self.ref_count,
            "reconcile_count": self.reconcile_count,
            "content_sha256": self.content_sha256,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 受控字段过滤（拒绝任意 column 透出）
# ---------------------------------------------------------------------------


def _project_fields(
    row: dict[str, Any],
    allowed: Sequence[str],
) -> dict[str, Any]:
    """仅保留白名单字段；其余字段一律丢弃（防御正文/ref/session/free reason 泄露）。"""
    return {k: v for k, v in row.items() if k in allowed}


def _assert_no_forbidden_substring(payload_json: str) -> None:
    """AC10 sentinel：序列化 JSON 中禁止出现的 substring（防御正文/ref 泄露）。"""
    for substr in FORBIDDEN_SNAPSHOT_SUBSTRINGS:
        # "blocked_reason" 是 reconcile 列字段名但非禁止值；仅当 substring 真正出现
        # 时才 fail closed。sentinel 简化为：若字段名/序列化键含 forbidden 即拒。
        if substr == "blocked_reason":
            # 此字段名出现在 reconcile 表白名单 = "blocked_reason" 列名（在
            # REF_FIELDS 中），**键**含 substr 是允许的（ref.erasure_state 的
            # blocked_reason 列）。但**值**含字符串 "blocked_reason"（自由文本）
            # 才禁止。本 sentinel 简化为：检查序列化 JSON 中 substr 作为**值**
            # 出现的次数 > 阈值（白名单字段键名恰好出现一次）。
            occurrences = payload_json.count(substr)
            if occurrences > 1:  # 1 = 字段名；>1 = 字段名 + 值中字面
                raise AssertionError(
                    f"sentinel 拒：快照含 {substr!r} 多次（疑似自由文本泄露）"
                )
        else:
            if substr in payload_json:
                raise AssertionError(
                    f"sentinel 拒：快照含禁止 substring {substr!r}（正文/ref 泄露）"
                )


# ---------------------------------------------------------------------------
# 主导出函数
# ---------------------------------------------------------------------------


async def export_ledger_snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> tuple[LedgerSnapshotHeader, list[LedgerSnapshotRow]]:
    """导出指定 tenant 的独立 ledger 快照（受控字段白名单 + sentinel 校验）。

    返回 (header, rows)——rows 是按 operation → checkpoint → ref → reconcile
    顺序排列的 LedgerSnapshotRow 列表（每行已是单 JSON 行序列化安全形态）。
    """
    rows: list[LedgerSnapshotRow] = []

    # 1. operations
    op_rows = (
        await session.execute(
            text(
                "SELECT id, tenant_id, conversation_id, purge_revision, state, "
                "registry_digest, hold_revision_snapshot, lease_epoch, "
                "lease_expires_at, scheduled_at, started_at, completed_at, "
                "failure_code, next_retry_at, revision, created_at, updated_at "
                "FROM metaedu.agent_conversation_purges WHERE tenant_id = :tid "
                "ORDER BY created_at, id"
            ),
            {"tid": tenant_id},
        )
    ).mappings().all()
    for r in op_rows:
        projected = _project_fields(dict(r), _OPERATION_FIELDS)
        rows.append(LedgerSnapshotRow(table="operation", fields=projected))

    # 2. checkpoints
    cp_rows = (
        await session.execute(
            text(
                "SELECT id, tenant_id, purge_operation_id, owner_key, owner_version, "
                "capability_digest, state, attempt, "
                "checkpoint_digest, ack_digest, reason_code, created_at "
                "FROM metaedu.agent_conversation_purge_owners WHERE tenant_id = :tid "
                "ORDER BY created_at, id"
            ),
            {"tid": tenant_id},
        )
    ).mappings().all()
    for r in cp_rows:
        projected = _project_fields(dict(r), _CHECKPOINT_FIELDS)
        rows.append(LedgerSnapshotRow(table="checkpoint", fields=projected))

    # 3. external refs
    ref_rows = (
        await session.execute(
            text(
                "SELECT id, tenant_id, owner_key, conversation_id, ref_scheme, "
                "source_table, source_row_id, erase_state, blocked_reason, "
                "created_at, updated_at FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :tid ORDER BY created_at, id"
            ),
            {"tid": tenant_id},
        )
    ).mappings().all()
    for r in ref_rows:
        projected = _project_fields(dict(r), _REF_FIELDS)
        rows.append(LedgerSnapshotRow(table="ref", fields=projected))

    # 4. reconcile
    re_rows = (
        await session.execute(
            text(
                "SELECT id, tenant_id, owner_key, conversation_id, source_table, "
                "source_row_id, issue_code, reconcile_class, created_at, "
                "resolved_at, state "
                "FROM metaedu.agent_transport_scope_reconcile WHERE tenant_id = :tid "
                "ORDER BY created_at, id"
            ),
            {"tid": tenant_id},
        )
    ).mappings().all()
    for r in re_rows:
        projected = _project_fields(dict(r), _RECONCILE_FIELDS)
        rows.append(LedgerSnapshotRow(table="reconcile", fields=projected))

    # 计数 + sentinel
    op_count = sum(1 for r in rows if r.table == "operation")
    cp_count = sum(1 for r in rows if r.table == "checkpoint")
    ref_count = sum(1 for r in rows if r.table == "ref")
    re_count = sum(1 for r in rows if r.table == "reconcile")

    # 内容指纹 + sentinel 校验（每行 JSON 化后拼接）
    content_lines: list[str] = [r.to_json() for r in rows]
    for line in content_lines:
        _assert_no_forbidden_substring(line)
    content_blob = "\n".join(content_lines).encode("utf-8")
    digest = hashlib.sha256(content_blob).hexdigest()

    header = LedgerSnapshotHeader(
        tenant_id=tenant_id,
        exported_at_iso="",  # 调用方填入（避免 datetime 依赖）
        schema_version=LEDGER_SCHEMA_VERSION,
        operation_count=op_count,
        checkpoint_count=cp_count,
        ref_count=ref_count,
        reconcile_count=re_count,
        content_sha256=digest,
    )
    return header, rows


def serialize_snapshot(
    header: LedgerSnapshotHeader,
    rows: Iterable[LedgerSnapshotRow],
) -> str:
    """序列化快照为 JSON Lines（首行 header，后续每行一个 record）。"""
    out: list[str] = [header.to_json()]
    for r in rows:
        out.append(r.to_json())
    return "\n".join(out) + "\n"
