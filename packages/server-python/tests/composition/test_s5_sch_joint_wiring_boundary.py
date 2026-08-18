"""R1-S5 B/C/D 联合组合根（S5-SCH-3 组合根启用门禁）真实 PG 判别测试。

契约：Plan §R1-S5-D S5-SCH-3「组合根启用门禁（冻结）」——仅当 SCH-B（orchestrator
+ participant map + coordinator）、SCH-C（rebuild）、SCH-D（concrete settlement）
三 slice 全部装配才允许翻转组合根 erase 入口可达性；partial wiring fail closed。
本批次不接线生产调用方（不新增后台循环/HTTP/CLI/API/migration/registry
capability）；external/runtime adapter 槽位 = FailClosed + registry False。

判别点（每项具名，真实 PostgreSQL）：
- 组合根静态装配完整性（六元素 + 门禁）
- partial wiring fail closed（缺 owner entry / settlement / rebuild → 装配 raise，
  零生产副作用）
- 联合 claim → run_cycle → 每 owner 后 coordinator → operation completed
- erasing owner 经 concrete SettlementPort 在 entry 事务内收口（session 传递）
- external/runtime 槽位 capability fail closed（零擦除副作用）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ConversationPurgeScheduler,
)
from app.composition.owner_execution_orchestrator import (
    OwnerEntryOutcome,
    OwnerEntryRequest,
)
from app.composition.scheduler_composition import (
    CompositionNotReadyError,
    _require_joint_wiring,
    build_owner_entries,
    build_scheduler_composition,
    build_settlement_port,
)
from app.shared.schemas.canonical_json import canonical_digest

_OWNER_KEYS = [str(o["owner_key"]) for o in registry_snapshot()]
assert sorted(_OWNER_KEYS) == _OWNER_KEYS
_EXTERNAL = "external.payload.v1"
_RUNTIME = "runtime.private.v1"
_SUPPORTED = [k for k in _OWNER_KEYS if k not in (_EXTERNAL, _RUNTIME)]

_COMPOSITION_SOURCE = (
    Path(__file__).resolve().parents[2] / "app" / "composition" / "scheduler_composition.py"
)


# ---------------------------------------------------------------------------
# 种子 helpers
# ---------------------------------------------------------------------------


async def _seed_conversation(session):
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) VALUES (:id, :tid, NULL, 'redacted', :digest, :identity, "
            "'t', 'none', 'deleted', now() - interval '1 day', 'scheduled', 1, "
            "0, 1, now(), now())"
        ),
        {"id": cid, "tid": tid, "digest": "c" * 64, "identity": "d" * 64},
    )
    return tid, cid


async def _ensure_tenant(session, tid):
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, 'sch-d-joint-tenant', 'sch-d joint school', "
            "'shared', true, now(), now()) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": tid},
    )


async def _claim(session, tid, cid):
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _set_cp(
    session, op_id, owner_key, *, state, ack=None, digest=None, attempt=None,
    reason=None,
):
    sets = ["state = :state"]
    params = {"op": op_id, "k": owner_key, "state": state}
    if state == "acked":
        sets.append("ack_digest = :a, checkpoint_digest = :a")
        params["a"] = ack or "e" * 64
        sets.append("reason_code = NULL")
    else:
        sets.append("ack_digest = NULL")
    if digest is not None:
        sets.append("checkpoint_digest = :digest")
        params["digest"] = digest
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    if reason is not None:
        sets.append("reason_code = :reason")
        params["reason"] = reason
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        params,
    )


async def _seed_fence(session, tid, cid, owner_key, *, state, ack=None):
    ic = {"schema_version": 1, "sources": {}}
    ack_sql = ", ack_digest, acked_at" if state == "erased" else ""
    ack_vals = ", :ack, now()" if state == "erased" else ""
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest"
            + ack_sql
            + ", revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            ":st, 1, 0, :ic, :ing"
            + ack_vals
            + ", 1, now(), now())"
        ),
        {
            "tid": tid,
            "cid": cid,
            "k": owner_key,
            "st": state,
            "ic": json.dumps(ic, sort_keys=True),
            "ing": canonical_digest(ic),
            "ack": ack,
        },
    )


async def _seed_external_ref(session, tid, cid, *, ref_value="obj://staging/object/x"):
    from app.composition.external_ref_erasure_participant import ExternalRefRow

    row = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme="db_local",
        ref_value=ref_value,
        source_table="agent_workspace_outbox",
        source_row_id=uuid.uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs "
            "(id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "source_table, source_row_id, erase_state, created_at, updated_at) "
            "VALUES (:id, :t, :c, 'external.payload.v1', :rs, :rv, :st, :sr, "
            "'registered', now(), now())"
        ),
        {
            "id": row.id,
            "t": tid,
            "c": cid,
            "rs": row.ref_scheme,
            "rv": row.ref_value,
            "st": row.source_table,
            "sr": row.source_row_id,
        },
    )
    await session.flush()
    return row


async def _op_state(session, op_id, field):
    return (
        await session.execute(
            text(f"SELECT {field} FROM metaedu.agent_conversation_purges WHERE id=:op"),
            {"op": op_id},
        )
    ).scalar_one()


async def _cp(session, op_id, owner_key, field):
    return (
        await session.execute(
            text(
                f"SELECT {field} FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id=:op AND owner_key=:k"
            ),
            {"op": op_id, "k": owner_key},
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# entry fakes（联合边界测试用：ack 自写 checkpoint/fence，镜像 participant DB 效果）
# ---------------------------------------------------------------------------


def _ack_with_db_write(calls: list[str]):
    async def entry(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        calls.append(request.owner_key)
        await request.session.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "state='acked', ack_digest=:a, checkpoint_digest=:a, "
                "reason_code=NULL WHERE purge_operation_id=:op AND owner_key=:k"
            ),
            {"a": "e" * 64, "op": request.purge_operation_id, "k": request.owner_key},
        )
        ic = {"schema_version": 1, "sources": {}}
        await request.session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                "ack_digest, acked_at, revision, created_at, updated_at) VALUES "
                "(:tid, :cid, :o, 1, 'erased', 1, 0, :ic, :ing, :ack, now(), 1, "
                "now(), now())"
            ),
            {
                "tid": request.tenant_id,
                "cid": request.conversation_id,
                "o": request.owner_key,
                "ic": json.dumps(ic, sort_keys=True),
                "ing": canonical_digest(ic),
                "ack": "e" * 64,
            },
        )
        return OwnerEntryOutcome(acked=True, blocked_reason=None)

    return entry


class _LookupEvidenceAdapter:
    """supports_receipt_lookup：evidence → 态 1（settlement 收口用）。"""

    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.lookup_keys: list[str] = []

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_keys.append(idempotency_key)
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")

    async def destroy_session(self, **kwargs):
        raise AssertionError("evidence 后不得 replay")


def _noop_adapter_resolver(adapter):
    def resolve(*, owner_key, owner_version):
        return adapter
    return resolve


def _pad64(value: str) -> str:
    return (value + "x" * 64)[:64]


# ---------------------------------------------------------------------------
# 静态装配完整性 + 门禁
# ---------------------------------------------------------------------------


def test_composition_root_wires_all_joint_elements():
    """S5-SCH-3：组合根必须同窗口装配 B/C/D 全部元素（静态判别）。"""
    source = _COMPOSITION_SOURCE.read_text(encoding="utf-8")
    for required in (
        "CompositionNotReadyError",  # 门禁：partial wiring fail closed
        "OwnerExecutionOrchestrator",  # SCH-B
        "build_owner_entries",  # participant map
        "build_settlement_port",  # SCH-D concrete SettlementPort
        "PurgeRebuildService",  # SCH-C
        "coordinator_scan_providers",  # coordinator
        "ConversationPurgeScheduler",  # SCH-A claim/lease
    ):
        assert required in source, f"联合边界缺 {required!r}"
    for entry in (
        "erase_conversation_body",
        "erase_execution_body",
        "erase_transport_owner",
        "erase_external_payload",
        "erase_runtime_session",
    ):
        assert entry in source, f"participant map 缺 {entry!r}"


def test_partial_wiring_fail_closed(session_factory):
    """partial wiring fail closed：缺 owner entry / settlement / rebuild → 装配
    raise（CompositionNotReadyError），生产调用方不得进入 owner execution。"""
    # 缺 owner entry（participant map 部分）→ fail closed。
    partial_entries = build_owner_entries()
    del partial_entries["runtime.private.v1"]
    with pytest.raises(CompositionNotReadyError, match="owner entries missing"):
        build_scheduler_composition(
            session_factory=session_factory,
            owner_entries=partial_entries,
        )
    # 缺 SCH-D settlement（显式 None）→ fail closed。
    with pytest.raises(CompositionNotReadyError, match="SettlementPort"):
        _require_joint_wiring(
            owner_entries=build_owner_entries(),
            settlement=None,
            rebuild=object(),
            claim=object(),
        )
    # 缺 SCH-C rebuild（显式 None）→ fail closed。
    with pytest.raises(CompositionNotReadyError, match="PurgeRebuildService"):
        _require_joint_wiring(
            owner_entries=build_owner_entries(),
            settlement=build_settlement_port(),
            rebuild=None,
            claim=object(),
        )


# ---------------------------------------------------------------------------
# 联合 claim → run_cycle → coordinator
# ---------------------------------------------------------------------------


async def test_joint_claim_cycle_coordinator_completes(db_session, session_factory):
    """联合 claim → run_cycle：六 owner 顺序 entry、每 entry 后 coordinator、
    operation 收敛 completed（缺任一 wiring 元素 → 装配 raise / 聚合缺失）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    calls: list[str] = []
    entries = {k: _ack_with_db_write(calls) for k in _OWNER_KEYS}
    comp = build_scheduler_composition(
        session_factory=session_factory,
        owner_entries=entries,
        settlement=build_settlement_port(),
    )
    await comp.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    await db_session.commit()

    assert calls == _OWNER_KEYS, "owner 字典序循环（组合根接线）"
    async with session_factory() as verify:
        assert await _op_state(verify, op_id, "state") == "completed", (
            "每 owner 后 coordinator 聚合 → completed"
        )


async def test_erasing_owner_settlement_in_entry_transaction(
    db_session, session_factory
):
    """erasing owner 经 concrete SettlementPort 在 entry 事务内收口。

    验证 orchestrator→SettlementPort 的 session 传递：settlement 与 entry 同一
    事务/锁上下文，closeout 后 fence/checkpoint 收敛；非 erasing owner 跳过。
    """
    from app.composition.external_ref_erasure_participant import (
        external_delete_intent_digest,
    )

    tid, cid = await _seed_conversation(db_session)
    await _ensure_tenant(db_session, tid)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    ref = await _seed_external_ref(db_session, tid, cid)
    intent = external_delete_intent_digest([ref])
    for k in _OWNER_KEYS:
        if k == _EXTERNAL:
            await _set_cp(
                db_session, op_id, k, state="erasing", digest=intent, attempt=1
            )
        else:
            await _set_cp(db_session, op_id, k, state="acked")
    await _seed_fence(db_session, tid, cid, _EXTERNAL, state="erasing")
    await db_session.commit()

    adapter = _LookupEvidenceAdapter()
    comp = build_scheduler_composition(
        session_factory=session_factory,
        settlement=build_settlement_port(
            adapter_resolver=_noop_adapter_resolver(adapter),
        ),
    )
    result = await comp.run_cycle(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    await db_session.commit()

    # 非 erasing owner 全部 skipped；external erasing 经 settlement 收口。
    assert result.owners_entered == (), "erasing → settlement（非 entry）"
    async with session_factory() as verify:
        fence = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE conversation_id=:cid AND owner_key=:k"
                ),
                {"cid": cid, "k": _EXTERNAL},
            )
        ).scalar_one()
        assert fence == "erased", "concrete settlement 收口 fence"
        assert await _cp(verify, op_id, _EXTERNAL, "state") == "acked"
    assert adapter.lookup_keys, "settlement lookup 执行（session 传递验证）"


async def test_budget_exhaustion_concrete_settlement_converges_fence(
    db_session, session_factory
):
    """预算耗尽路径：orchestrator raw SQL 写 failed 后经 concrete SettlementPort
    同事务收敛 fence erasing→blocked。

    变异「settlement checkpoint 重读不加 populate_existing（identity map 陈旧）」
    → 红（converge 读 stale blocked 提前返回，fence 永留 erasing）。
    """
    from app.composition.owner_execution_orchestrator import RETRY_BUDGET

    ws_core = "workspace.core.v1"
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        if k == ws_core:
            await _set_cp(
                db_session, op_id, k, state="blocked",
                reason="purge_blocked_by_workspace_scan_nonzero",
                attempt=RETRY_BUDGET,
            )
        else:
            await _set_cp(db_session, op_id, k, state="acked")
    await _seed_fence(db_session, tid, cid, ws_core, state="erasing")
    await db_session.commit()

    comp = build_scheduler_composition(
        session_factory=session_factory,
        settlement=build_settlement_port(),
    )
    await comp.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    await db_session.commit()

    async with session_factory() as verify:
        fence = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE conversation_id=:cid AND owner_key=:k"
                ),
                {"cid": cid, "k": ws_core},
            )
        ).scalar_one()
        assert fence == "blocked", "预算耗尽后 concrete settlement 收敛 fence"
        assert await _cp(verify, op_id, ws_core, "state") == "failed"


async def test_external_slot_fail_closed_capability_zero_side_effect(
    db_session, session_factory
):
    """external/runtime 槽位 = FailClosed + registry False：pending external owner
    进入 → capability 门禁 fail closed，零擦除副作用（无 ledger 写、checkpoint 不
    推进）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    for k in _OWNER_KEYS:
        if k in _SUPPORTED:
            await _set_cp(db_session, op_id, k, state="acked")
    # external pending（无 capability）→ 编排进入即 fail closed。
    await _set_cp(db_session, op_id, _EXTERNAL, state="pending")
    await _set_cp(db_session, op_id, _RUNTIME, state="acked")
    await db_session.commit()

    comp = build_scheduler_composition(session_factory=session_factory)
    with pytest.raises(Exception) as exc:
        await comp.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    await db_session.rollback()

    from app.composition.agent_erasure_registry import OwnerCapabilityUnavailableError

    assert isinstance(
        exc.value, OwnerCapabilityUnavailableError
    ) or "not installed" in str(exc.value), "capability 门禁 fail closed"
    async with session_factory() as verify:
        # 零擦除副作用：external checkpoint 保持 pending（未推进 erasing）。
        assert await _cp(verify, op_id, _EXTERNAL, "state") == "pending"
        n_refs = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id=:t AND conversation_id=:c"
                ),
                {"t": tid, "c": cid},
            )
        ).scalar_one()
        assert n_refs == 0, "零 external ledger 副作用"
