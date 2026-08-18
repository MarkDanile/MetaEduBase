"""R1-S5 root integration：settlement idempotency key 对齐 真实 PG 判别测试。

契约：R1-S5-SCH-2 对齐——settlement 与 participant Tx1 使用**完全相同**的 per-ref
idempotency key（frozen descriptor 协议身份 + 冻结 ref/binding 身份，不含
tenant_id/conversation_id/lease_epoch/attempt）；adapter 调用携带 participant Tx1
所需稳定 ref 输入；E-2a 冻结 intent 重验——缺失/不一致输入 fail closed，禁 fallback
conversation 级简化 key。

判别点（每项具名，真实 PostgreSQL）：
- participant Tx1 与 settlement 同 key（external + runtime 各一，真实 participant
  Tx1 崩溃注入驱动）
- takeover/lease_epoch、attempt 变化 → key 不变（跨租约稳定）
- 历史 descriptor/resolver 变化 → 旧 settlement key 不变（frozen 身份权威，不随
  当前 adapter 身份漂移）
- lookup/replay 同 key 重放 → 不产生第二次外部副作用（零二次 delete）
- 缺失/不一致 ref/session 输入 → fail closed（raise，零 adapter 调用，不 fallback
  tenant+conversation key）
- 多个 refs → 每稳定外部对象身份独立 key（不压缩成 conversation 级 key）
- adapter 调用参数包含正确 ref 与 key
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.composition import agent_erasure_registry as _registry_mod
from app.composition.external_object_adapter import (
    external_erase_idempotency_key,
)
from app.composition.external_ref_erasure_participant import (
    ExternalPayloadErasureParticipant,
    external_delete_intent_digest,
)
from app.composition.runtime_erasure_adapter import (
    runtime_destroy_idempotency_key,
)
from app.composition.runtime_erasure_participant import (
    RuntimeErasureParticipant,
    runtime_destroy_intent_digest,
)
from app.composition.settlement import SettlementService
from app.composition.transactional_projection_coordinator import (
    build_scan_providers,
)
from app.shared.schemas.canonical_json import canonical_digest

_EXTERNAL = "external.payload.v1"
_RUNTIME = "runtime.private.v1"
# frozen descriptor 协议身份（adapter_recovery V1：external→external.object.v1、
# runtime→runtime.session.v1）。participant Tx1 的 adapter 必须呈现该身份，
# settlement 的 key 才能与 Tx1 精确一致。
_PROTOCOL_KEY = {
    _EXTERNAL: "external.object.v1",
    _RUNTIME: "runtime.session.v1",
}


# ---------------------------------------------------------------------------
# registry 翻转 fixture（participant 入口 require_capability 放行）
# ---------------------------------------------------------------------------


@pytest.fixture
def _registry_enabled(monkeypatch):
    """临时把全部 owner erase_available 翻 True（测试作用域内还原）。"""
    enabled = tuple(
        _registry_mod.OwnerDefinition(
            owner_key=o.owner_key,
            owner_version=o.owner_version,
            capabilities=o.capabilities,
            erase_available=True,
        )
        for o in _registry_mod.owner_registry()
    )
    monkeypatch.setattr(_registry_mod, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(
        _registry_mod,
        "_OWNERS_BY_KEY",
        {o.owner_key: o for o in enabled},
    )
    return enabled


# ---------------------------------------------------------------------------
# 种子 helpers（自包含；conversation + tenant + claim + ref/binding 窗口）
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
            "VALUES (:id, 'sch-d-key-tenant', 'sch-d key school', "
            "'shared', true, now(), now()) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": tid},
    )


async def _claim(session, tid, cid):
    from app.composition.conversation_purge_scheduler import (
        ConversationPurgeScheduler,
    )

    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _seed_external_ref(
    session, tid, cid, *, ref_value="obj://staging/object/x",
    ref_scheme="db_local", source_table="agent_workspace_outbox",
):
    from app.composition.external_ref_erasure_participant import ExternalRefRow

    row = ExternalRefRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        ref_scheme=ref_scheme,
        ref_value=ref_value,
        source_table=source_table,
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


async def _seed_runtime_binding(
    session, tid, cid, *, ref_value="pi://session/x",
):
    from app.composition.runtime_erasure_participant import RuntimeBindingRow

    row = RuntimeBindingRow(
        id=uuid.uuid4(),
        tenant_id=tid,
        conversation_id=cid,
        runtime_profile_id=uuid.uuid4(),
        runtime_session_ref=ref_value,
    )
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_session_bindings "
            "(id, tenant_id, conversation_id, runtime_profile_id, "
            "runtime_session_ref, status, current_epoch, next_expected_runtime_seq, "
            "acked_through_runtime_seq, active_stream_id, stream_lease_expires_at, "
            "revision, created_at, updated_at) "
            "VALUES (:id, :t, :c, :rp, :rv, 'active', 1, 1, 0, NULL, NULL, "
            "1, now(), now())"
        ),
        {
            "id": row.id,
            "t": tid,
            "c": cid,
            "rp": row.runtime_profile_id,
            "rv": row.runtime_session_ref,
        },
    )
    await session.execute(text("SET LOCAL session_replication_role = default"))
    await session.flush()
    return row


async def _seed_base(
    session, *, owner_key=_EXTERNAL,
    ref_values=("obj://staging/object/x",),
    binding_refs=("pi://session/x",),
):
    """种子 conversation + tenant + claim（全 owner pending checkpoint）+
    冻结 ref/binding 窗口（不置 erasing、不建 fence）。返回
    (tid, cid, op1, rows, intent_digest)。"""
    tid, cid = await _seed_conversation(session)
    await _ensure_tenant(session, tid)
    out = await _claim(session, tid, cid)
    op1 = out.token.purge_operation_id
    if owner_key == _EXTERNAL:
        rows = [
            await _seed_external_ref(session, tid, cid, ref_value=rv)
            for rv in ref_values
        ]
        intent = external_delete_intent_digest(rows)
    else:
        rows = [
            await _seed_runtime_binding(session, tid, cid, ref_value=rv)
            for rv in binding_refs
        ]
        intent = runtime_destroy_intent_digest(rows)
    return tid, cid, op1, rows, intent


async def _set_cp(session, op_id, owner_key, *, state, digest=None, attempt=None):
    sets = ["state = :state"]
    params = {"op": op_id, "k": owner_key, "state": state}
    if state != "acked":
        sets.append("ack_digest = NULL")
    if digest is not None:
        sets.append("checkpoint_digest = :digest")
        params["digest"] = digest
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        params,
    )


async def _seed_erasing_window(
    session, *, owner_key=_EXTERNAL, **kwargs
):
    """种子冻结窗口 + erasing fence + erasing checkpoint（真实 intent digest）。
    返回 (tid, cid, op1, rows)。"""
    tid, cid, op1, rows, intent = await _seed_base(
        session, owner_key=owner_key, **kwargs
    )
    ic = {"schema_version": 1, "sources": {}}
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            "'erasing', 1, 0, :ic, :ing, 1, now(), now())"
        ),
        {
            "tid": tid,
            "cid": cid,
            "k": owner_key,
            "ic": json.dumps(ic, sort_keys=True),
            "ing": canonical_digest(ic),
        },
    )
    await _set_cp(
        session, op1, owner_key, state="erasing", digest=intent, attempt=1,
    )
    await session.commit()
    return tid, cid, op1, rows


def _pad64(value: str) -> str:
    return (value + "x" * 64)[:64]


def _noop_adapter_resolver(adapter):
    def resolve(*, owner_key, owner_version):
        return adapter
    return resolve


# ---------------------------------------------------------------------------
# recording adapters（断言 key + ref 输入 + 副作用）
# ---------------------------------------------------------------------------


class _RecordingLookupAdapter:
    """supports_receipt_lookup：记录 lookup key；返回 evidence（→ 态 1）。

    协议身份与 frozen descriptor 对齐（``external.object.v1``）。"""

    adapter_key = _PROTOCOL_KEY[_EXTERNAL]
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.lookup_keys: list[str] = []
        self.delete_calls: list[tuple[str, str, str]] = []

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_keys.append(idempotency_key)
        return _pad64(f"ev:{idempotency_key}")

    async def delete_object(self, *, ref_scheme, ref_value, idempotency_key):
        self.delete_calls.append((ref_scheme, ref_value, idempotency_key))
        return None


class _RecordingLookupRuntimeAdapter:
    """runtime 镜像：destroy_session 记录 (runtime_session_ref, key)。"""

    adapter_key = _PROTOCOL_KEY[_RUNTIME]
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.lookup_keys: list[str] = []
        self.destroy_calls: list[tuple[str, str]] = []

    async def receipt_lookup(self, *, idempotency_key):
        self.lookup_keys.append(idempotency_key)
        return _pad64(f"ev:{idempotency_key}")

    async def destroy_session(self, *, runtime_session_ref, idempotency_key):
        self.destroy_calls.append((runtime_session_ref, idempotency_key))
        return None


class _CrashAfterTx1ExternalAdapter:
    """participant Tx1 驱动：delete_object 记录 (ref, key) 后抛通用异常
    （Tx1 已提交、Tx2 未执行 → settlement 窗口）。协议身份对齐。"""

    adapter_key = _PROTOCOL_KEY[_EXTERNAL]
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    async def delete_object(self, *, ref_scheme, ref_value, idempotency_key):
        self.calls.append((ref_scheme, ref_value, idempotency_key))
        raise RuntimeError("simulated crash after participant Tx1")

    async def receipt_lookup(self, *, idempotency_key):
        raise AssertionError("crash adapter performs no lookup")


class _CrashAfterTx1RuntimeAdapter:
    """runtime 镜像：destroy_session 记录 (ref, key) 后抛通用异常。"""

    adapter_key = _PROTOCOL_KEY[_RUNTIME]
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = True

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def destroy_session(self, *, runtime_session_ref, idempotency_key):
        self.calls.append((runtime_session_ref, idempotency_key))
        raise RuntimeError("simulated crash after runtime participant Tx1")

    async def receipt_lookup(self, *, idempotency_key):
        raise AssertionError("crash adapter performs no lookup")


# ---------------------------------------------------------------------------
# 判别测试
# ---------------------------------------------------------------------------


async def test_external_participant_tx1_and_settlement_same_key(
    session_factory, _registry_enabled
):
    """participant Tx1 与 settlement 使用完全相同的 per-ref key（external）。

    真实 participant Tx1 崩溃注入（Tx2 未执行）→ settlement 重放；adapter 收到的
    key 与 Tx1 记录 key 精确相等，且等于冻结身份派生公式。
    """
    async with session_factory() as seed:
        tid, cid, op1, rows, intent = await _seed_base(seed, owner_key=_EXTERNAL)
        await seed.commit()

    crash = _CrashAfterTx1ExternalAdapter()
    async with session_factory() as s:
        participant = ExternalPayloadErasureParticipant(s, crash)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await participant.erase_external_payload(
                tenant_id=tid,
                conversation_id=cid,
                purge_revision=1,
                purge_operation_id=op1,
                expected_operation_revision=1,
                expected_lease_epoch=1,
            )
    assert len(crash.calls) == 1, "participant Tx1 恰一次 adapter 调用"
    tx1_scheme, tx1_value, tx1_key = crash.calls[0]
    ref = rows[0]
    assert (tx1_scheme, tx1_value) == (ref.ref_scheme, ref.ref_value)

    lookup = _RecordingLookupAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(lookup),
        )
        await service.closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        await s.commit()

    assert lookup.lookup_keys == [tx1_key], "participant Tx1 与 settlement 同 key"
    assert tx1_key == external_erase_idempotency_key(
        ref_scheme=ref.ref_scheme,
        ref_value=ref.ref_value,
        adapter_key=_PROTOCOL_KEY[_EXTERNAL],
        adapter_version=1,
    )
    assert lookup.delete_calls == [], "lookup evidence → 零二次 delete（无第二次副作用）"


async def test_runtime_participant_tx1_and_settlement_same_key(
    session_factory, _registry_enabled
):
    """participant Tx1 与 settlement 使用完全相同的 key（runtime 镜像）。"""
    async with session_factory() as seed:
        tid, cid, op1, rows, intent = await _seed_base(seed, owner_key=_RUNTIME)
        await seed.commit()

    crash = _CrashAfterTx1RuntimeAdapter()
    async with session_factory() as s:
        participant = RuntimeErasureParticipant(s, crash)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await participant.erase_runtime_session(
                tenant_id=tid,
                conversation_id=cid,
                purge_revision=1,
                purge_operation_id=op1,
                expected_operation_revision=1,
                expected_lease_epoch=1,
            )
    assert len(crash.calls) == 1
    tx1_ref, tx1_key = crash.calls[0]
    binding = rows[0]
    assert tx1_ref == binding.runtime_session_ref

    lookup = _RecordingLookupRuntimeAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(lookup),
        )
        await service.closeout_erasing(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op1,
            owner_key=_RUNTIME,
        )
        await s.commit()

    assert lookup.lookup_keys == [tx1_key], "runtime Tx1 与 settlement 同 key"
    assert tx1_key == runtime_destroy_idempotency_key(
        runtime_session_ref=binding.runtime_session_ref,
        adapter_key=_PROTOCOL_KEY[_RUNTIME],
        adapter_version=1,
    )
    assert lookup.destroy_calls == [], "lookup evidence → 零二次 destroy"


async def test_key_stable_across_lease_epoch_and_attempt(session_factory):
    """takeover/lease_epoch 变化与 attempt 变化 → settlement key 不变。"""
    async with session_factory() as seed:
        tid, cid, op1, rows = await _seed_erasing_window(seed, owner_key=_EXTERNAL)
    ref = rows[0]

    def _closeout():
        return _RecordingLookupAdapter()

    lookup1 = _closeout()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(lookup1),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        await s.commit()
    key1 = lookup1.lookup_keys[0]

    # 重置窗口（fence/checkpoint 回 erasing，intent 不变）+ takeover 推进
    # lease_epoch + attempt +1。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_erasure_fences SET state='erasing', "
                "ack_digest=NULL, acked_at=NULL "
                "WHERE conversation_id=:cid AND owner_key=:k"
            ),
            {"cid": cid, "k": _EXTERNAL},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET "
                "lease_epoch = lease_epoch + 1 "
                "WHERE id=:op"
            ),
            {"op": op1},
        )
        # 首次 success 会把 checkpoint_digest 覆写为 final scan digest；重置窗口时
        # 恢复原始冻结 intent（attempt 推进为 2）。
        await _set_cp(
            s, op1, _EXTERNAL, state="erasing",
            digest=external_delete_intent_digest([ref]), attempt=2,
        )
        await s.commit()

    lookup2 = _closeout()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(lookup2),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        await s.commit()
    key2 = lookup2.lookup_keys[0]

    assert key2 == key1, "lease_epoch/attempt 变化后 key 不变（跨 takeover 稳定）"
    assert key1 == external_erase_idempotency_key(
        ref_scheme=ref.ref_scheme,
        ref_value=ref.ref_value,
        adapter_key=_PROTOCOL_KEY[_EXTERNAL],
        adapter_version=1,
    )


async def test_key_uses_frozen_descriptor_not_current_adapter(session_factory):
    """历史 descriptor/resolver 变化 → 旧 settlement 用 frozen 身份派生 key。

    当前 adapter 实例呈现**新**身份（``external.object.v2``），frozen descriptor 仍为
    v1——settlement key 必须用 frozen ``external.object.v1``，不随当前 adapter 漂移。
    """
    async with session_factory() as seed:
        tid, cid, op1, rows = await _seed_erasing_window(seed, owner_key=_EXTERNAL)
    ref = rows[0]

    class _NewIdentityAdapter(_RecordingLookupAdapter):
        adapter_key = "external.object.v2"  # 部署后的新 adapter 身份

    adapter = _NewIdentityAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        await s.commit()

    frozen_key = external_erase_idempotency_key(
        ref_scheme=ref.ref_scheme,
        ref_value=ref.ref_value,
        adapter_key=_PROTOCOL_KEY[_EXTERNAL],
        adapter_version=1,
    )
    new_identity_key = external_erase_idempotency_key(
        ref_scheme=ref.ref_scheme,
        ref_value=ref.ref_value,
        adapter_key="external.object.v2",
        adapter_version=1,
    )
    assert adapter.lookup_keys == [frozen_key], "frozen descriptor 身份权威"
    assert frozen_key != new_identity_key, "判别力：新旧身份 key 互异"


async def test_missing_ref_inputs_fail_closed_no_fallback(session_factory):
    """缺失 ref/session 输入 → fail closed（raise），零 adapter 调用，不 fallback
    tenant+conversation 简化 key。"""
    async with session_factory() as seed:
        tid, cid, op1, rows = await _seed_erasing_window(seed, owner_key=_EXTERNAL)
        # 删除全部冻结 ref 输入（Tx1 后 ledger 行被并发/异常清除的等价场景）。
        await seed.execute(
            text(
                "DELETE FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id=:t AND conversation_id=:c"
            ),
            {"t": tid, "c": cid},
        )
        await seed.commit()

    adapter = _RecordingLookupAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        with pytest.raises(ValueError, match="intent digest mismatch"):
            await service.closeout_erasing(
                tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
                owner_key=_EXTERNAL,
            )
        await s.rollback()
    assert adapter.lookup_keys == [], "缺失输入零 adapter 调用（fail closed）"
    assert adapter.delete_calls == [], "不 fallback 简化 key 删除"


async def test_inconsistent_ref_inputs_fail_closed(session_factory):
    """不一致 ref 输入（冻结集合被状态迁移）→ fail closed 零 adapter 调用。"""
    async with session_factory() as seed:
        tid, cid, op1, rows = await _seed_erasing_window(seed, owner_key=_EXTERNAL)
        ref = rows[0]
        # 冻结窗口内一个 ref 被并发写改写（ref_value 变化 → 集合不一致）。
        await seed.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs SET "
                "ref_value='obj://staging/object/CHANGED' WHERE id=:id"
            ),
            {"id": ref.id},
        )
        await seed.commit()

    adapter = _RecordingLookupAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        with pytest.raises(ValueError, match="intent digest mismatch"):
            await service.closeout_erasing(
                tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
                owner_key=_EXTERNAL,
            )
        await s.rollback()
    assert adapter.lookup_keys == [], "不一致输入零 adapter 调用"


async def test_multiple_refs_per_ref_key_granularity(session_factory):
    """多个 external refs 不压缩成 conversation 级 key：每稳定对象身份独立 key。"""
    values = ("obj://staging/object/a", "obj://staging/object/b")
    async with session_factory() as seed:
        tid, cid, op1, rows = await _seed_erasing_window(
            seed, owner_key=_EXTERNAL, ref_values=values
        )

    adapter = _RecordingLookupAdapter()
    async with session_factory() as s:
        service = SettlementService(
            s,
            scan_providers=build_scan_providers(s),
            adapter_resolver=_noop_adapter_resolver(adapter),
        )
        await service.closeout_erasing(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1,
            owner_key=_EXTERNAL,
        )
        await s.commit()

    expected = [
        external_erase_idempotency_key(
            ref_scheme=r.ref_scheme,
            ref_value=r.ref_value,
            adapter_key=_PROTOCOL_KEY[_EXTERNAL],
            adapter_version=1,
        )
        for r in rows
    ]
    assert sorted(adapter.lookup_keys) == sorted(expected), "per-ref key 粒度"
    assert len(set(adapter.lookup_keys)) == 2, "两 ref 两 key（不压缩）"


async def test_settlement_default_key_formula_removed():
    """旧 tenant+conversation 简化 key 公式已被删除（不 fallback 载体存在）。"""
    import inspect

    from app.composition import settlement as _settlement_mod

    assert not hasattr(_settlement_mod, "_default_idempotency_key"), (
        "tenant+conversation 简化 idempotency key 公式必须删除"
    )
    params = set(inspect.signature(SettlementService.__init__).parameters)
    assert "idempotency_key_provider" not in params, "旧 key provider 注入已移除"
