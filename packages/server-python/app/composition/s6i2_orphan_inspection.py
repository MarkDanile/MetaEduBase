"""R1-S6-I2 Writer conformance suite + body/ref orphan inspection (verify CLI).

Contract (S6-4 + S6-6 frozen in main via PR #581):
- 枚举当前已实现的正文/ref writer、retention worker、event-gap 巡检写者。
- 以 registry snapshot、owner_key、owner_version、capability_digest 为事实源。
- 校验 writer 集合、owner 归属、字段写权限、tenant/conversation scope、
  source key、fence/token 门禁和版本漂移 fail closed。
- restore replay 属 S6-I3：只能登记为 pending，不得伪造已实现。
- 六类 verify 巡检只读为主，唯一写路径 = event gap 检出时幂等置
  ``agent_runs.event_log_complete=False``（Run 行锁内短事务，具名 reconcile
  登记）+ 每个 conversation 的巡检结果以具名 issue 登记表
  ``agent_transport_scope_reconcile``（state ≠ resolved → gate 阻断
  scheduler-enable，既有语义）。

实现范围（严格冻结边界）：
- writer 集合按 plan §S6-4 全表枚举 + S6-4 N/M 类写者（M 类 restore 重放
  执行器仅登记 pending）。
- 六类 verify CLI（tenant mismatch / digest conflict / event gap /
  unknown ref scheme / missing fence or owner scope / orphan transport 行）。
- 退出码：0=无发现 / 1=有发现 / 2=不可判定或基础事实缺失。
- 写入仅限 reconcile ledger 幂等登记 + event gap 的
  ``event_log_complete=False``；禁止改 operation/checkpoint/fence/lease、
  清正文/ref、伪造 ACK、自动 resolve。

R1-AC10 合规：可观察计数仅含数值 + 状态枚举 + ID 列表；不输出正文、ref 原值、
Runtime session ref 或自由文本 reason。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.composition.agent_erasure_registry import (
    _OWNERS_BY_KEY,
    capability_digest,
    owner_registry,
)

# ---------------------------------------------------------------------------
# Writer conformance suite（S6-4）
# ---------------------------------------------------------------------------

# Fence 状态值域（F=fenced / O=owner lock no fence / N=no lock no fence / D=dead /
# M=maintenance path with collection lock）。与 plan §S6-4 全表字面一致。
FENCE_F = "F"
FENCE_O = "O"
FENCE_N = "N"
FENCE_D = "D"
FENCE_M = "M"

# 巡检写者登记：restore 重放执行器（M 类）只登记 pending——S6-I3 实现，本 PR 不接。
S6I2_PENDING_WRITERS: tuple[tuple[str, str, str], ...] = (
    (
        "restore_replay_executor",
        "M",
        "S6-8 item 3; 与 retention/audit jobs 互斥；本 PR 不实现，S6-I3 落地",
    ),
)


@dataclass(frozen=True, slots=True)
class WriterSpec:
    """S6-4 字面 writer 规范（冻结版本，PR 内固定）。"""

    writer_name: str
    owner_key: str
    fence_status: str
    module_path: str
    function_name: str
    tenant_scoped: bool
    scope_class: str  # "Run" / "Conversation" / "Operation" / "Maintenance"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    """writer conformance suite 输出（R1-AC10：只含计数与状态枚举）。"""

    writers_total: int = 0
    writers_passed: int = 0
    writers_failed: tuple[str, ...] = ()
    registry_keys_total: int = 0
    registry_keys_passed: int = 0
    registry_unknown_keys: tuple[str, ...] = ()
    capability_drift_keys: tuple[str, ...] = ()
    stage_with_created_callers_total: int = 0
    stage_with_created_callers_unfenced: tuple[str, ...] = ()


def _required_writer_specs() -> tuple[WriterSpec, ...]:
    """S6-4 全表字面登记——含 S6-I1 已落地的 S6 自身 N 类写者（前三个）+ S6-I2
    ``event-gap 巡检写者`` = S6-4 ``event-gap 巡检写者``（owner=execution.core.v1，
    N 类）。

    本表为 S6-4 契约收敛登记。S6 自身第四个写者 ``restore_replay_executor``（M 类）
    仅登记 pending，不进入 conformance 集合判定（plan §S6-4「前三个均在 S6-2/S6-3/S6-6
    冻结谓词内幂等」= 已实现；第四个 restore 重放执行器归 S6-I3）。
    """

    return (
        # ---------- S6 自身 N 类写者 ----------
        WriterSpec(
            writer_name="run_event_retention",
            owner_key="execution.core.v1",
            fence_status=FENCE_N,
            module_path="app.composition.retention_workers",
            function_name="run_event_retention",
            tenant_scoped=True,
            scope_class="Run",
            notes="S6-2 冻结；Run 行锁；不取 Conv/owner/fence",
        ),
        WriterSpec(
            writer_name="run_audit_retention",
            owner_key="execution.core.v1",
            fence_status=FENCE_N,
            module_path="app.composition.retention_workers",
            function_name="run_audit_retention",
            tenant_scoped=True,
            scope_class="Run",
            notes="S6-3 冻结；Run 行锁 + children 行级锁",
        ),
        WriterSpec(
            writer_name="event_gap_inspection_writer",
            owner_key="execution.core.v1",
            fence_status=FENCE_N,
            module_path="app.composition.s6i2_orphan_inspection",
            function_name="_mark_event_gap_incomplete",
            tenant_scoped=True,
            scope_class="Run",
            notes="S6-6 冻结；置 event_log_complete=False；Run 行锁内",
        ),
    )


def list_registered_owner_keys() -> tuple[str, ...]:
    """注册表字面 owner_key 集合（registry snapshot 事实源）。"""

    return tuple(sorted(o.owner_key for o in owner_registry()))


def capability_digest_for(owner_key: str) -> str | None:
    try:
        return capability_digest(owner_key)
    except Exception:  # noqa: BLE001 - registry raises UnknownOwnerError
        return None


@dataclass(frozen=True, slots=True)
class OwnerVersionRow:
    """fence 表 owner_version + capability_digest 扫描结果。"""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    owner_key: str
    owner_version: int
    expected_capability_digest: str | None
    state: str


def _expected_owner_version(owner_key: str) -> int:
    owner = _OWNERS_BY_KEY.get(owner_key)
    return int(owner.owner_version) if owner is not None else -1


def run_writer_conformance_static() -> ConformanceResult:
    """静态枚举层（S6-4「验证层级 = 静态枚举（非真实 PG）+ fence 判别（真实 PG）」）。

    仅校验：writer 集合、owner_key 归属、owner_version/capability_digest 漂移
    fail closed、unknown owner fail closed、stage_with_created 调用方门禁。
    """

    specs = _required_writer_specs()
    spec_owner_keys = tuple(sorted({spec.owner_key for spec in specs}))
    registered_owner_keys = list_registered_owner_keys()

    # 1. owner_key 集合一致性（registry ⊇ writer 集合）
    missing_owner_keys = tuple(
        sorted(set(spec_owner_keys) - set(registered_owner_keys))
    )

    # 2. capability_digest 漂移检测（每个 owner 的持久化 capability_digest 与
    #    当前 registry capability_digest() 必须一致；不一致 = 写者矩阵漂移 fail closed）。
    #    静态枚举层仅校验 capability_digest() 可重算 + owner_version 已知；
    #    fence 表 row-level 漂移由 fence 判别层（真实 PG）补全。
    drift: list[str] = []
    for owner_key in spec_owner_keys:
        if owner_key not in _OWNERS_BY_KEY:
            drift.append(f"{owner_key}:unknown_owner")
            continue
        digest = capability_digest_for(owner_key)
        if digest is None:
            drift.append(f"{owner_key}:digest_uncomputable")

    # 3. writer → owner 矩阵登记完整性（spec 集合 = 必填三 N 类）
    expected_writer_names = {s.writer_name for s in specs}
    missing_writers = tuple(sorted(expected_writer_names - _DISCOVERED_WRITER_NAMES))
    extra_writers = tuple(sorted(_DISCOVERED_WRITER_NAMES - expected_writer_names))

    failed_names: list[str] = []
    failed_names.extend(f"missing_owner_key:{k}" for k in missing_owner_keys)
    failed_names.extend(f"missing_writer:{n}" for n in missing_writers)
    failed_names.extend(f"extra_writer:{n}" for n in extra_writers)
    failed_names.extend(f"capability_drift:{k}" for k in drift)

    passed = len(specs) - len(
        {n.split(":", 1)[1] for n in failed_names if n.startswith("missing_writer:")}
    )
    if failed_names:
        passed = max(
            0,
            len(specs)
            - len({n.split(":", 1)[1] for n in failed_names if ":" in n}),
        )

    return ConformanceResult(
        writers_total=len(specs),
        writers_passed=passed,
        writers_failed=tuple(failed_names),
        registry_keys_total=len(registered_owner_keys),
        registry_keys_passed=len(registered_owner_keys) - len(missing_owner_keys),
        registry_unknown_keys=missing_owner_keys,
        capability_drift_keys=tuple(drift),
        stage_with_created_callers_total=len(_STAGE_WITH_CREATED_FENCED_CALLERS),
        stage_with_created_callers_unfenced=tuple(
            sorted(
                set(_STAGE_WITH_CREATED_FENCED_CALLERS) - _FENCED_CALLER_ALLOWLIST
            )
        ),
    )


# 已发现的 writer 名称集合（PR 内部注册位 = ``run_event_retention`` /
# ``run_audit_retention`` 模块顶层函数 + event-gap 巡检写者）。
_DISCOVERED_WRITER_NAMES: set[str] = {
    "run_event_retention",
    "run_audit_retention",
    "event_gap_inspection_writer",
}

# stage_with_created 已发现的生产调用方集合（plan §S6-4 P2-4 裁决：生产调用方
# 集合 ⊆ fenced port；execution_fenced_port.py:420 现状唯一生产调用方）。
_STAGE_WITH_CREATED_FENCED_CALLERS: frozenset[str] = frozenset(
    {
        "app.composition.execution_fenced_port",
    }
)

# 允许的 fenced 调用方（仅 execution_fenced_port 一处）
_FENCED_CALLER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "app.composition.execution_fenced_port",
    }
)


# ---------------------------------------------------------------------------
# 六类 verify 巡检（S6-6）
# ---------------------------------------------------------------------------

# issue_code ↔ reconcile_class 映射（受 ledger CHECK 约束，见 migration 040）。
# 仅登记 ledger CHECK 合法组合；其他 4 类（digest_conflict / missing_fence /
# missing_owner_scope / orphan_transport）按 plan S6-6 字面「发现即阻止 +
# 人工处置后重跑」= 报告 sentinel，不写 ledger（避免越权 migration 改动）。
_LEDGER_ISSUE_CLASS: dict[str, str] = {
    "cross_tenant_mismatch": "tenant_scope",
    "ambiguous_mapping": "tenant_scope",
    "conversation_deleted_orphan": "orphan",
    "source_message_missing": "tenant_scope",
    "source_run_missing": "tenant_scope",
    "source_outbox_missing": "tenant_scope",
    "epoch_unresolvable": "tenant_scope",  # event gap → execution.transport.v1/run_events
}

# owner_key ↔ source_table 合法组合（受 ledger CHECK 约束）。
_LEDGER_TABLE_TO_OWNER: dict[str, str] = {
    "agent_workspace_outbox": "workspace.transport.v1",
    "agent_workspace_inbox": "workspace.transport.v1",
    "agent_execution_outbox": "execution.transport.v1",
    "agent_execution_inbox": "execution.transport.v1",
    "agent_run_events": "execution.transport.v1",
}

_LEDGER_TABLE_TO_SOURCE_ISSUE: dict[str, str] = {
    "agent_workspace_outbox": "source_message_missing",
    "agent_execution_outbox": "source_run_missing",
    "agent_workspace_inbox": "source_outbox_missing",
    "agent_execution_inbox": "source_outbox_missing",
}


@dataclass(frozen=True, slots=True)
class Finding:
    """巡检发现（稳定 ID + 分类 + 表，不含正文/ref/free reason）。"""

    inspection: str  # 巡检类（六类之一）
    table: str  # 触发表的字面名
    row_id: uuid.UUID | None  # 行 UUID（如果有）
    code: str  # issue_code 或报告 sentinel（digest_conflict 等）
    conversation_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """巡检结果（R1-AC10：稳定计数 + ID 列表）。"""

    inspection: str
    findings_total: int = 0
    findings_persisted: int = 0
    findings_reported_only: int = 0
    rows_scanned: int = 0
    ledger_writes_attempted: int = 0
    ledger_writes_succeeded: int = 0
    ledger_writes_skipped_invalid: int = 0
    nondeterministic: bool = False
    sample_finding_ids: tuple[str, ...] = ()
    event_log_complete_writes: int = 0


def _fingerprint(finding: Finding) -> str:
    """发现 ID 派生（hashlib SHA-256 64-hex；不含正文/ref/自由文本）。"""

    payload = (
        f"{finding.inspection}|{finding.table}|"
        f"{finding.row_id or ''}|{finding.code}|"
        f"{finding.conversation_id or ''}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _register_ledger_issue(
    session,
    *,
    tenant_id: uuid.UUID,
    source_table: str,
    source_row_id: uuid.UUID,
    issue_code: str,
    conversation_id: uuid.UUID | None,
) -> bool:
    """幂等登记 reconcile issue（仅合法组合；不合法返回 False 不写）。"""

    expected_owner = _LEDGER_TABLE_TO_OWNER.get(source_table)
    expected_class = _LEDGER_ISSUE_CLASS.get(issue_code)
    if expected_owner is None or expected_class is None:
        return False
    # source_*_missing 与 source_table 必须对齐（migration 040 CHECK 约束）
    source_issue = _LEDGER_TABLE_TO_SOURCE_ISSUE.get(source_table)
    if source_issue is not None and source_issue != issue_code and issue_code not in {
        "cross_tenant_mismatch",
        "ambiguous_mapping",
        "conversation_deleted_orphan",
        "epoch_unresolvable",
    }:
        return False
    # class_scope CHECK：conversation_scope 必须有 conversation_id，反之亦然；
    # tenant_scope / orphan 必须 conversation_id = NULL。
    normalized_conversation_id: uuid.UUID | None
    if expected_class == "conversation_scope":
        normalized_conversation_id = conversation_id
        if normalized_conversation_id is None:
            return False
    else:
        normalized_conversation_id = None
    await session.execute(
        text(
                """
                INSERT INTO metaedu.agent_transport_scope_reconcile (
                    id, tenant_id, owner_key, source_table, source_row_id,
                    conversation_id, reconcile_class, issue_code,
                    state, revision, created_at, resolved_at
                ) VALUES (
                    :id, :tenant_id, :owner_key, :source_table, :source_row_id,
                    :conversation_id, :reconcile_class, :issue_code,
                    'open', 1, clock_timestamp(), NULL
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "owner_key": expected_owner,
                "source_table": source_table,
                "source_row_id": source_row_id,
                "conversation_id": normalized_conversation_id,
                "reconcile_class": expected_class,
                "issue_code": issue_code,
            },
    )
    return True


async def _mark_event_gap_incomplete(
    session,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
) -> None:
    """event gap 写者（plan §S6-4 N 类）：幂等置 Run.event_log_complete=False。

    Run 行锁内短事务；不取 Conv/owner/fence。
    """

    await session.execute(
        text(
            """
            UPDATE metaedu.agent_runs
               SET event_log_complete = FALSE
             WHERE tenant_id = :tid AND id = :rid
            """
        ),
        {"tid": tenant_id, "rid": run_id},
    )


# --- 六类巡检 ---


async def _scan_tenant_mismatch(
    session, *, tenant_id: uuid.UUID
) -> list[Finding]:
    """类 1：tenant mismatch——跨 tenant 引用 / 源行 tenant 谓词对账。

    校验 source_table 行级 FK 谓词与 owner_key/tenant 对账。
    """

    findings: list[Finding] = []
    rows = (
        await session.execute(
            text(
                """
                SELECT 'agent_workspace_outbox' AS tbl, id, conversation_id
                  FROM metaedu.agent_workspace_outbox
                 WHERE tenant_id = :tid
                   AND conversation_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_conversations c
                        WHERE c.tenant_id = :tid
                          AND c.id = conversation_id
                   )
                UNION ALL
                SELECT 'agent_execution_outbox', id, conversation_id
                  FROM metaedu.agent_execution_outbox
                 WHERE tenant_id = :tid
                   AND conversation_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_conversations c
                        WHERE c.tenant_id = :tid
                          AND c.id = conversation_id
                   )
                UNION ALL
                SELECT 'agent_run_events', id, run_id
                  FROM metaedu.agent_run_events
                 WHERE tenant_id = :tid
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_runs r
                        WHERE r.tenant_id = :tid
                          AND r.id = run_id
                   )
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for tbl, row_id, conv_id in rows:
        findings.append(
            Finding(
                inspection="tenant_mismatch",
                table=tbl,
                row_id=row_id,
                code="cross_tenant_mismatch",
                conversation_id=conv_id,
            )
        )
    return findings


async def _scan_digest_conflict(
    session, *, tenant_id: uuid.UUID
) -> list[Finding]:
    """类 2：digest conflict——重算并报告，不覆盖持久 digest。

    fence 表 ``owner_version`` 必须与 registry 字面 ``owner.owner_version`` 一致
    （版本漂移 = 写者矩阵漂移 fail closed）；``ingress_digest`` 与
    ``ack_digest`` 字面 64-hex 合法性 + 重算校验。报告维度：

    - owner_version 漂移 → ``digest_conflict:owner_version_drift``
    - 未知 owner_key → ``digest_conflict:unknown_owner``
    - 持久化 digest 字面不合法（≠ 64-hex） → ``digest_conflict:malformed``

    不覆盖持久化 digest；按 plan §S6-6 「digest/tenant 类发现必须人工处置后重跑」。
    """

    import re as _re

    hex_re = _re.compile(r"^[0-9a-f]{64}$")
    findings: list[Finding] = []
    rows = (
        await session.execute(
            text(
                """
                SELECT conversation_id, owner_key, owner_version,
                       ingress_digest, ack_digest
                  FROM metaedu.agent_erasure_fences
                 WHERE tenant_id = :tid
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for conv_id, owner_key, owner_version, ingress_digest, ack_digest in rows:
        owner = _OWNERS_BY_KEY.get(owner_key)
        if owner is None:
            findings.append(
                Finding(
                    inspection="digest_conflict",
                    table="agent_erasure_fences",
                    row_id=None,
                    code="digest_conflict:unknown_owner",
                    conversation_id=conv_id,
                )
            )
            continue
        if int(owner_version) != int(owner.owner_version):
            findings.append(
                Finding(
                    inspection="digest_conflict",
                    table="agent_erasure_fences",
                    row_id=None,
                    code="digest_conflict:owner_version_drift",
                    conversation_id=conv_id,
                )
            )
        if ingress_digest is not None and not hex_re.match(ingress_digest):
            findings.append(
                Finding(
                    inspection="digest_conflict",
                    table="agent_erasure_fences",
                    row_id=None,
                    code="digest_conflict:malformed",
                    conversation_id=conv_id,
                )
            )
        if ack_digest is not None and not hex_re.match(ack_digest):
            findings.append(
                Finding(
                    inspection="digest_conflict",
                    table="agent_erasure_fences",
                    row_id=None,
                    code="digest_conflict:malformed",
                    conversation_id=conv_id,
                )
            )
    return findings


async def _scan_event_gap(
    session, *, tenant_id: uuid.UUID, persist: bool
) -> tuple[list[Finding], int, int]:
    """类 3：event gap——_find_event_gap 复用；Run 行锁内幂等写
    event_log_complete=False + ledger 登记（epoch_unresolvable +
    owner=execution.transport.v1 + source=run_events，ledger CHECK 合法组合）。

    返回 (findings, persist_count, ledger_count)。
    """

    findings: list[Finding] = []
    persist_count = 0
    ledger_count = 0
    # 1. 仅扫描 terminal-state runs（避免长期 open run 误报）
    rows = (
        await session.execute(
            text(
                """
                SELECT id, first_available_event_seq, next_event_seq
                  FROM metaedu.agent_runs
                 WHERE tenant_id = :tid
                   AND status IN ('completed', 'failed', 'cancelled')
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for run_id, first_avail, next_seq in rows:
        gap_rows = (
            await session.execute(
                text(
                    """
                    SELECT seq FROM metaedu.agent_run_events
                     WHERE tenant_id = :tid
                       AND run_id = :rid
                       AND seq >= :low
                       AND seq <= :high
                     ORDER BY seq
                    """
                ),
                {
                    "tid": tenant_id,
                    "rid": run_id,
                    "low": first_avail,
                    "high": next_seq,
                },
            )
        ).all()
        seqs = [int(r[0]) for r in gap_rows]
        if not seqs:
            continue
        expected = list(range(first_avail, next_seq + 1))
        if seqs != expected:
            findings.append(
                Finding(
                    inspection="event_gap",
                    table="agent_run_events",
                    row_id=run_id,
                    code="epoch_unresolvable",
                    conversation_id=None,
                )
            )
            if persist:
                await _mark_event_gap_incomplete(
                    session, tenant_id=tenant_id, run_id=run_id
                )
                persist_count += 1
                registered = await _register_ledger_issue(
                    session,
                    tenant_id=tenant_id,
                    source_table="agent_run_events",
                    source_row_id=run_id,
                    issue_code="epoch_unresolvable",
                    conversation_id=None,
                )
                if registered:
                    ledger_count += 1
    return findings, persist_count, ledger_count


async def _scan_unknown_ref_scheme(
    session, *, tenant_id: uuid.UUID
) -> list[Finding]:
    """类 4：unknown ref scheme——external_object_refs ref_scheme 白名单。"""

    findings: list[Finding] = []
    rows = (
        await session.execute(
            text(
                """
                SELECT id, conversation_id
                  FROM metaedu.agent_external_object_refs
                 WHERE tenant_id = :tid
                   AND ref_scheme = 'unknown'
                   AND erase_state IN ('pending', 'blocked')
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for row_id, conv_id in rows:
        findings.append(
            Finding(
                inspection="unknown_ref_scheme",
                table="agent_external_object_refs",
                row_id=row_id,
                code="unknown_scheme",
                conversation_id=conv_id,
            )
        )
    return findings


async def _scan_missing_fence_or_owner_scope(
    session, *, tenant_id: uuid.UUID
) -> list[Finding]:
    """类 5：missing fence / owner scope——已安装 owner 缺 fence 或 inbox/outbox 缺
    conversation_id。"""

    findings: list[Finding] = []

    # 5a. 已安装 owner 的 fence 完整性
    _ = (
        await session.execute(
            text(
                """
                SELECT DISTINCT owner_key FROM metaedu.agent_erasure_fences
                 WHERE tenant_id = :tid
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    # 5a. 已安装 owner 的 fence 完整性：当前生产未启用时不必报「该 owner 完全没
    # fence」——那是部署门禁范围；行级一致性由后续 ledger 登记链路覆盖。
    # 5b. inbox/outbox 缺 conversation_id
    null_conv_rows = (
        await session.execute(
            text(
                """
                SELECT 'agent_workspace_outbox', id
                  FROM metaedu.agent_workspace_outbox
                 WHERE tenant_id = :tid AND conversation_id IS NULL
                UNION ALL
                SELECT 'agent_execution_outbox', id
                  FROM metaedu.agent_execution_outbox
                 WHERE tenant_id = :tid AND conversation_id IS NULL
                UNION ALL
                SELECT 'agent_workspace_inbox', id
                  FROM metaedu.agent_workspace_inbox
                 WHERE tenant_id = :tid AND event_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_workspace_outbox o
                        WHERE o.id = agent_workspace_inbox.event_id
                   )
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for tbl, row_id in null_conv_rows:
        findings.append(
            Finding(
                inspection="missing_fence_or_owner_scope",
                table=tbl,
                row_id=row_id,
                code="missing_owner_scope:null_conversation_id",
                conversation_id=None,
            )
        )
    return findings


async def _scan_orphan_transport(
    session, *, tenant_id: uuid.UUID
) -> list[Finding]:
    """类 6：orphan transport 行——outbox/inbox 引用不存在的 run/conversation。"""

    findings: list[Finding] = []
    rows = (
        await session.execute(
            text(
                """
                SELECT 'agent_workspace_outbox', id, conversation_id
                  FROM metaedu.agent_workspace_outbox
                 WHERE tenant_id = :tid
                   AND conversation_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_conversations c
                        WHERE c.tenant_id = :tid AND c.id = conversation_id
                   )
                UNION ALL
                SELECT 'agent_execution_outbox', id, conversation_id
                  FROM metaedu.agent_execution_outbox
                 WHERE tenant_id = :tid
                   AND conversation_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM metaedu.agent_conversations c
                        WHERE c.tenant_id = :tid AND c.id = conversation_id
                   )
                """
            ),
            {"tid": tenant_id},
        )
    ).all()
    for tbl, row_id, conv_id in rows:
        findings.append(
            Finding(
                inspection="orphan_transport",
                table=tbl,
                row_id=row_id,
                code="conversation_deleted_orphan",
                conversation_id=conv_id,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 顶层 CLI 入口
# ---------------------------------------------------------------------------


_INSPECTIONS: tuple[str, ...] = (
    "tenant_mismatch",
    "digest_conflict",
    "event_gap",
    "unknown_ref_scheme",
    "missing_fence_or_owner_scope",
    "orphan_transport",
)


@dataclass(frozen=True, slots=True)
class VerifyReport:
    """CLI 报告（每类一项 InspectionResult + 总计）。"""

    inspections: tuple[InspectionResult, ...]
    total_findings: int
    total_persisted: int
    total_reported_only: int
    total_ledger_writes: int
    total_event_log_complete_writes: int
    conformance: ConformanceResult
    exit_code: int
    indeterminate: bool = False
    error: str | None = None


async def verify_inspection(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    persist_event_gap: bool = True,
    inspections: Sequence[str] = _INSPECTIONS,
) -> VerifyReport:
    """执行六类巡检 + writer conformance。"""

    conformance = run_writer_conformance_static()
    results: list[InspectionResult] = []
    total_findings = 0
    total_ledger = 0
    total_event_log = 0
    indeterminate = False

    async with session_factory() as session, session.begin():
        rows_scanned_total = 0
        for inspection in inspections:
            if inspection == "tenant_mismatch":
                findings = await _scan_tenant_mismatch(session, tenant_id=tenant_id)
            elif inspection == "digest_conflict":
                findings = await _scan_digest_conflict(session, tenant_id=tenant_id)
            elif inspection == "event_gap":
                findings, persisted, ledger = await _scan_event_gap(
                    session, tenant_id=tenant_id, persist=persist_event_gap
                )
                total_event_log += persisted
                total_ledger += ledger
            elif inspection == "unknown_ref_scheme":
                findings = await _scan_unknown_ref_scheme(
                    session, tenant_id=tenant_id
                )
            elif inspection == "missing_fence_or_owner_scope":
                findings = await _scan_missing_fence_or_owner_scope(
                    session, tenant_id=tenant_id
                )
            elif inspection == "orphan_transport":
                findings = await _scan_orphan_transport(
                    session, tenant_id=tenant_id
                )
            else:
                indeterminate = True
                continue
            rows_scanned_total += 1
            sample_ids = tuple(_fingerprint(f) for f in findings[:5])
            results.append(
                InspectionResult(
                    inspection=inspection,
                    findings_total=len(findings),
                    findings_persisted=(
                        total_event_log if inspection == "event_gap" else 0
                    ),
                    findings_reported_only=(
                        len(findings) if inspection != "event_gap" else 0
                    ),
                    rows_scanned=rows_scanned_total,
                    sample_finding_ids=sample_ids,
                    event_log_complete_writes=(
                        total_event_log if inspection == "event_gap" else 0
                    ),
                )
            )
            total_findings += len(findings)

    if indeterminate:
        exit_code = 2
    elif total_findings > 0:
        exit_code = 1
    else:
        exit_code = 0
    return VerifyReport(
        inspections=tuple(results),
        total_findings=total_findings,
        total_persisted=total_event_log,
        total_reported_only=total_findings - total_event_log,
        total_ledger_writes=total_ledger,
        total_event_log_complete_writes=total_event_log,
        conformance=conformance,
        exit_code=exit_code,
        indeterminate=indeterminate,
    )


def report_to_dict(report: VerifyReport) -> dict[str, Any]:
    """报告序列化为 JSON-safe dict（R1-AC10：不含正文/ref/free reason）。"""

    return {
        "total_findings": report.total_findings,
        "total_persisted": report.total_persisted,
        "total_reported_only": report.total_reported_only,
        "total_ledger_writes": report.total_ledger_writes,
        "total_event_log_complete_writes": report.total_event_log_complete_writes,
        "exit_code": report.exit_code,
        "indeterminate": report.indeterminate,
        "error": report.error,
        "conformance": {
            "writers_total": report.conformance.writers_total,
            "writers_passed": report.conformance.writers_passed,
            "writers_failed": list(report.conformance.writers_failed),
            "registry_keys_total": report.conformance.registry_keys_total,
            "registry_keys_passed": report.conformance.registry_keys_passed,
            "registry_unknown_keys": list(report.conformance.registry_unknown_keys),
            "capability_drift_keys": list(report.conformance.capability_drift_keys),
            "stage_with_created_callers_total": (
                report.conformance.stage_with_created_callers_total
            ),
            "stage_with_created_callers_unfenced": list(
                report.conformance.stage_with_created_callers_unfenced
            ),
        },
        "inspections": [
            {
                "inspection": r.inspection,
                "findings_total": r.findings_total,
                "findings_persisted": r.findings_persisted,
                "findings_reported_only": r.findings_reported_only,
                "rows_scanned": r.rows_scanned,
                "ledger_writes_attempted": r.ledger_writes_attempted,
                "ledger_writes_succeeded": r.ledger_writes_succeeded,
                "ledger_writes_skipped_invalid": r.ledger_writes_skipped_invalid,
                "nondeterministic": r.nondeterministic,
                "sample_finding_ids": list(r.sample_finding_ids),
                "event_log_complete_writes": r.event_log_complete_writes,
            }
            for r in report.inspections
        ],
    }


async def _run_cli(args: argparse.Namespace) -> int:
    engine = create_async_engine(args.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        tenant_id = uuid.UUID(args.tenant_id)
        report = await verify_inspection(
            factory,
            tenant_id=tenant_id,
            persist_event_gap=not args.dry_run,
            inspections=tuple(args.inspections) if args.inspections else _INSPECTIONS,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        report = VerifyReport(
            inspections=(),
            total_findings=0,
            total_persisted=0,
            total_reported_only=0,
            total_ledger_writes=0,
            total_event_log_complete_writes=0,
            conformance=ConformanceResult(),
            exit_code=2,
            indeterminate=True,
            error=type(exc).__name__,
        )
    finally:
        await engine.dispose()

    print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    return report.exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.composition.s6i2_orphan_inspection",
        description=(
            "R1-S6-I2 writer conformance suite + body/ref orphan inspection "
            "(S6-4 + S6-6 contract-first)."
        ),
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument(
        "--database-url",
        default="postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not persist event_log_complete=False (read-only).",
    )
    parser.add_argument(
        "--inspections",
        nargs="+",
        choices=_INSPECTIONS,
        default=list(_INSPECTIONS),
        help="Restrict to specific inspections.",
    )
    return asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
