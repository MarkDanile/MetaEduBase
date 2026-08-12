r"""R1-S4-E-C：RuntimeErasureParticipant conformance fake 真实 PostgreSQL 测试。

契约事实源：Plan §R1-S4-E E-5-4（S4-E-C）+ spec §10.3（conformance suite：
session destroy + 旧 epoch event + 迟到 seq + unknown outcome + ACK 重放）+
D7（Runtime fake 只证明协议，不变量 7）。

**registry**（E-4）：``runtime.private.v1`` 生产 registry 保持
``erase_available=False``——participant 入口 ``require_capability`` fail closed。
本套件用 monkeypatch 把 runtime owner 临时翻 True 验证 erase 主体，**不改变生产
registry**（registry 断言与实现分离，测试作用域内自动还原）。

**双事务协议（E-2 镜像）**：Tx1（checkpoint -> erasing + attempt+1 + intent digest，
提交释放锁）-> 无锁 adapter destroy session（跨 takeover 稳定 idempotency key）
-> Tx2（E-2a 精确重验 + 清 binding ref + 关 binding + ACK）。participant 内部
``commit()`` 拆分两事务；``session_factory`` 提供可自控 commit 的连接。

判别点（E-6 镜像 / spec §10.3）：
- session destroy 正向：binding ref 清 + status closed + fence erased + checkpoint acked；
- 旧 epoch event / 迟到 seq：``evaluate_runtime_ingest`` 在 purge 窗口内对旧
  epoch（RuntimeEpochMismatchError）与 seq gap（RuntimeSequenceGapError）fail closed，
  ``require_active_fence`` 在 erasing fence 下 LateBodyWriteRejectedError（Spec §6.2 第 4 步
  只允许无正文 tombstone/receipt，不重建正文）；
- unknown outcome：destroy unknown -> binding invalid + ref 保留 + conversation
  blocked（``outcome_unknown``，不 ACK）；
- ACK 重放幂等：erased fence 重放修复 pending checkpoint（adapter 幂等去重，
  calls==1）；
- E-2b：idempotency key 不含 lease_epoch/attempt（跨 takeover 稳定）；
- E-3a 矩阵：success->erased / not-sent->blocked+erase_timeout /
  timeout->unknown / unknown->unknown / failed->blocked+adapter_unavailable；
- E-3b 镜像：blocked/unknown binding 查询 + 有证据 reconcile（仅 receipt 可得时
  补 erased）；
- registry fail closed + fake 不冒充真实 spool（``runtime_spool`` 无清除路径）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import (
    OwnerDefinition,
    capability_digest,
    registry_digest,
)
from app.composition.runtime_erasure_adapter import (
    RuntimeDestroyFailedError,
    RuntimeDestroyNotSentError,
    RuntimeDestroySuccess,
    RuntimeDestroyTimeoutError,
    RuntimeDestroyUnknown,
    RuntimeSessionDestroyAdapter,
    runtime_destroy_idempotency_key,
)
from app.composition.runtime_erasure_participant import (
    RUNTIME_PRIVATE_OWNER,
    RuntimeErasureParticipant,
)
from app.contexts.agent_workspace.domain import PurgeOwnerState
from tests.contexts.agent_control_plane.helpers import TENANT_ID
from tests.contexts.agent_execution.e1_helpers import TENANT_A

pytestmark = pytest.mark.asyncio

_REF_VALUE = "pi://session/1"


class _SuccessAdapter(RuntimeSessionDestroyAdapter):
    """E-3a success：返回可验证 evidence。幂等重放计数。"""

    adapter_key = "fake-pi-sdk"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = False

    def __init__(self) -> None:
        self.calls = 0

    async def destroy_session(self, **kwargs):
        self.calls += 1
        return RuntimeDestroySuccess(
            adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
        )

    async def receipt_lookup(self, **kwargs):
        return None


class _NotSentAdapter(_SuccessAdapter):
    """E-3a not-sent：调用前失败（可证明未发送）。"""

    async def destroy_session(self, **kwargs):
        self.calls += 1
        raise RuntimeDestroyNotSentError("connection failed before send")


class _TimeoutAdapter(_SuccessAdapter):
    """E-3a timeout：调用后超时（可能已生效）。"""

    async def destroy_session(self, **kwargs):
        self.calls += 1
        raise RuntimeDestroyTimeoutError("timeout after send")


class _UnknownAdapter(_SuccessAdapter):
    """E-3a unknown outcome。"""

    async def destroy_session(self, **kwargs):
        self.calls += 1
        return RuntimeDestroyUnknown()


class _FailedAdapter(_SuccessAdapter):
    """E-3a failed：明确失败（可证明无副作用）。"""

    async def destroy_session(self, **kwargs):
        self.calls += 1
        raise RuntimeDestroyFailedError("permanent failure")


class _EmptyEvidenceAdapter(_SuccessAdapter):
    """E-2b 返修镜像（D-9）：返回空 evidence——不得凭「空 evidence」写 erased。"""

    async def destroy_session(self, **kwargs):
        self.calls += 1
        return RuntimeDestroySuccess(adapter_receipt_evidence="")


class _UnsupportedAdapter(_SuccessAdapter):
    """E-2b 硬前置不满足（缺幂等重放 + 缺 receipt lookup）。"""

    supports_idempotent_replay = False
    supports_receipt_lookup = False


class _CrashOnFirstCall(_SuccessAdapter):
    """E-6 崩溃注入：第一次 destroy 后抛非 RuntimeDestroyError（模拟 Tx1 已提交、
    adapter 副作用已发生但进程在 Tx2 前崩溃）。"""

    def __init__(self) -> None:
        super().__init__()
        self._crash_next = True

    async def destroy_session(self, **kwargs):
        self.calls += 1
        if self._crash_next:
            self._crash_next = False
            raise RuntimeError("simulated process crash after adapter side-effect")
        return RuntimeDestroySuccess(
            adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
        )


class _ReceiptLookupAdapter(_SuccessAdapter):
    """E-3b 镜像：receipt lookup 返回可验证 evidence。"""

    supports_receipt_lookup = True
    supports_idempotent_replay = True

    def __init__(self, evidence: str | None = "reconciled-evidence") -> None:
        super().__init__()
        self._evidence = evidence

    async def receipt_lookup(self, **kwargs):
        return self._evidence


class _NoReceiptAdapter(_ReceiptLookupAdapter):
    """E-3b 镜像：receipt lookup 无 evidence。"""

    def __init__(self) -> None:
        super().__init__(evidence=None)


# ---------------------------------------------------------------------------
# registry monkeypatch fixture（runtime 临时翻 True，测试作用域内还原）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _runtime_registry_enabled(monkeypatch):
    """runtime.private.v1 临时翻 True 验证 erase 主体（E-4 registry 断言分离）。

    生产 registry 保持 False；本 fixture 仅测试作用域内生效，自动还原。
    """
    import app.composition.agent_erasure_registry as registry_module

    originals = registry_module._OWNER_DEFINITIONS

    def _enable_runtime(owner: OwnerDefinition):
        if owner.owner_key == RUNTIME_PRIVATE_OWNER:
            return OwnerDefinition(
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                capabilities=owner.capabilities,
                erase_available=True,
            )
        return owner

    enabled = tuple(_enable_runtime(o) for o in originals)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(registry_module, "_OWNERS_BY_KEY", {o.owner_key: o for o in enabled})
    yield


# ---------------------------------------------------------------------------
# 基建
# ---------------------------------------------------------------------------


async def _ensure_test_tenant(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": TENANT_ID,
            "name": "s4ec-tenant",
            "school_name": "s4ec school",
            "isolation": "shared",
            "now": now,
        },
    )
    await db_session.flush()


async def _seed_deleted_expired_conversation(db_session) -> tuple[uuid.UUID, int]:
    """种已删除 + 已过恢复窗口的 Conversation。返回 (conv_id, purge_revision)。"""
    conv_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, creator_identity_digest, "
            "state, title, title_source, "
            "next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            "purge_revision, purged_at, purge_after, deleted_at, created_at, "
            "updated_at, revision, hold_revision, actor_state) "
            "VALUES (:id, :t, NULL, :cd, :cid, 'deleted', :title, 'user', 1, 1, "
            ":now, 'scheduled', 1, NULL, :purge_after, :deleted_at, :now, "
            ":now, 3, 0, 'redacted') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": conv_id,
            "t": TENANT_ID,
            "cd": "a" * 64,
            "cid": "b" * 64,
            "title": "s4ec conversation",
            "now": now,
            "purge_after": now - timedelta(days=1),
            "deleted_at": now - timedelta(days=31),
        },
    )
    # runtime owner fence：active（purge 未开始）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) "
            "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
            ":empty_digest, 1, :now, :now) "
            "ON CONFLICT (tenant_id, conversation_id, owner_key) DO NOTHING"
        ),
        {
            "t": TENANT_ID,
            "c": conv_id,
            "o": RUNTIME_PRIVATE_OWNER,
            "empty_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "now": now,
        },
    )
    await db_session.flush()
    return conv_id, 1


async def _seed_runtime_binding(
    db_session,
    conversation_id: uuid.UUID,
    *,
    ref_value: str = _REF_VALUE,
    status: str = "active",
    current_epoch: int = 1,
    next_seq: int = 1,
    acked_seq: int = 0,
) -> uuid.UUID:
    """种 runtime session binding（active + ref 非空）。返回 binding_id。

    满足现 binding CHECK（ck_agent_runtime_binding_status / ck_agent_runtime_binding_cursor
    / ck_agent_runtime_binding_stream_lease / ck_agent_runtime_binding_revision）。
    runtime_profile_id 用随机 UUID（无 FK 约束于本表之外，binding 自身 FK 指向
    agent_runtime_profiles，用 replica 角色绕 FK——m4 先例）。
    """
    binding_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_session_bindings "
            "(id, tenant_id, conversation_id, runtime_profile_id, "
            "runtime_session_ref, status, current_epoch, next_expected_runtime_seq, "
            "acked_through_runtime_seq, active_stream_id, stream_lease_expires_at, "
            "revision, created_at, updated_at) "
            "VALUES (:id, :t, :c, :rp, :rv, :st, :ep, :ns, :ac, NULL, NULL, "
            "1, :now, :now)"
        ),
        {
            "id": binding_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "rp": uuid.uuid4(),
            "rv": ref_value,
            "st": status,
            "ep": current_epoch,
            "ns": next_seq,
            "ac": acked_seq,
            "now": now,
        },
    )
    await db_session.execute(text("SET LOCAL session_replication_role = default"))
    await db_session.flush()
    return binding_id


async def _make_purge_operation(db_session, conversation_id, purge_revision):
    """建 scheduled purge operation + pending runtime owner checkpoint。"""
    op_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purges "
            "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
            "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
            "hold_revision_snapshot, lease_epoch, scheduled_at, revision, created_at, updated_at) "
            "VALUES (:id, :t, :c, :r, 'scheduled', :rd, :rs, :rps, :rpd, 0, 0, "
            ":now, 1, :now, :now)"
        ),
        {
            "id": op_id,
            "t": TENANT_ID,
            "c": conversation_id,
            "r": purge_revision,
            "rd": registry_digest(),
            "rs": _registry_snapshot_json(),
            "rps": '{"conversation_recovery_days": 30}',
            "rpd": _retention_policy_digest(),
            "now": now,
        },
    )
    cp_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, created_at, updated_at) "
            "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
        ),
        {
            "id": cp_id,
            "t": TENANT_ID,
            "op": op_id,
            "o": RUNTIME_PRIVATE_OWNER,
            "cd": capability_digest(RUNTIME_PRIVATE_OWNER),
            "now": now,
        },
    )
    await db_session.flush()
    return op_id, 1


def _registry_snapshot_json() -> str:
    import json

    from app.composition.agent_erasure_registry import registry_snapshot

    return json.dumps(registry_snapshot(), sort_keys=True, separators=(",", ":"))


def _retention_policy_digest() -> str:
    from app.shared.schemas.canonical_json import canonical_digest

    return canonical_digest({"conversation_recovery_days": 30})


def _participant(session, adapter) -> RuntimeErasureParticipant:
    return RuntimeErasureParticipant(session, adapter)


def _binding_state(db_session, binding_id: uuid.UUID) -> dict:
    return {
        "id": binding_id,
        "state": "unknown",  # placeholder; replaced by _load_binding
    }


async def _load_binding(db_session, binding_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT runtime_session_ref, status, revision FROM "
                "metaedu.agent_runtime_session_bindings WHERE id = :id"
            ),
            {"id": binding_id},
        )
    ).mappings().one()
    return dict(row)


async def _checkpoint_state(db_session, op_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT state, attempt, checkpoint_digest, reason_code FROM "
                "metaedu.agent_conversation_purge_owners WHERE purge_operation_id = :op"
            ),
            {"op": op_id},
        )
    ).mappings().one()
    return dict(row)


async def _fence_state(db_session, conv_id: uuid.UUID) -> dict:
    row = (
        await db_session.execute(
            text(
                "SELECT state, ack_digest FROM metaedu.agent_erasure_fences "
                "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
            ),
            {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
        )
    ).mappings().one()
    return dict(row)


# ---------------------------------------------------------------------------
# E-2b 硬前置（capability 判定，不依赖 registry 翻 True）
# ---------------------------------------------------------------------------


async def test_adapter_prerequisite_fail_closed(db_session):
    """E-2b 硬前置镜像：adapter 缺幂等重放 + 缺 receipt lookup -> 不得开工。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    participant = _participant(db_session, _UnsupportedAdapter())
    with pytest.raises(ValueError):
        await participant.erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


# ---------------------------------------------------------------------------
# session destroy 正向（E-6 镜像：binding ref 清 + closed + fence erased + ACK）
# ---------------------------------------------------------------------------


async def test_destroy_success_clears_ref_and_closes_binding(db_session):
    """E-6 session destroy 正向：binding ref 清 + status closed + fence erased +
    checkpoint acked。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    summary = await _participant(db_session, adapter).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.destroyed_bindings == 1
    assert summary.scan.total == 0
    assert adapter.calls == 1

    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] is None
    assert binding["status"] == "closed"
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value
    assert cp["attempt"] == 1
    assert cp["checkpoint_digest"] is not None
    fence = await _fence_state(db_session, conv_id)
    assert fence["state"] == "erased"
    assert fence["ack_digest"] is not None


async def test_destroy_success_closes_multiple_bindings(db_session):
    """E-6：多 binding 同一 conversation 全部 destroy + closed（每 binding 一次
    adapter 调用）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    b1 = await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/1")
    b2 = await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/2")
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    summary = await _participant(db_session, adapter).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.destroyed_bindings == 2
    assert adapter.calls == 2
    for b in (b1, b2):
        binding = await _load_binding(db_session, b)
        assert binding["runtime_session_ref"] is None
        assert binding["status"] == "closed"


async def test_destroy_success_no_active_binding_noop_ack(db_session):
    """E-6：无活跃 binding 的 conversation destroy 仍 ACK（scan 零，无残留）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    adapter = _SuccessAdapter()
    summary = await _participant(db_session, adapter).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.destroyed_bindings == 0
    assert summary.scan.total == 0
    assert adapter.calls == 0
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value


# ---------------------------------------------------------------------------
# E-3a 失败矩阵（blocked/unknown，不清 ref）
# ---------------------------------------------------------------------------


async def test_destroy_not_sent_blocks_erase_timeout(db_session):
    """E-3a not-sent：调用前失败（可证明未发送）-> blocked/erase_timeout。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    summary = await _participant(db_session, _NotSentAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.scan.total == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE  # ref 保留
    assert binding["status"] == "invalid"  # blocked 表达
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_erase_timeout"


async def test_destroy_timeout_marks_unknown(db_session):
    """E-3a timeout：调用后超时（可能已生效）-> unknown/outcome_unknown。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    summary = await _participant(db_session, _TimeoutAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.scan.total == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "invalid"
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_outcome_unknown"


async def test_destroy_unknown_marks_unknown(db_session):
    """E-3a unknown outcome：请求可能已生效 -> unknown/outcome_unknown，不 ACK。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    summary = await _participant(db_session, _UnknownAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.scan.total == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "invalid"
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_outcome_unknown"


async def test_destroy_failed_blocks_adapter_unavailable(db_session):
    """E-3a failed：明确失败（可证明无副作用）-> blocked/adapter_unavailable。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    summary = await _participant(db_session, _FailedAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert summary.scan.total == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "invalid"
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_adapter_unavailable"


async def test_destroy_empty_evidence_fail_closed(db_session):
    """E-2b 返修镜像（D-9）：空 evidence 不得写 erased（fail closed）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    with pytest.raises(ValueError):
        await _participant(db_session, _EmptyEvidenceAdapter()).erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    # 失败后 binding 未关、ref 保留（不伪造 erased）。
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "active"


# ---------------------------------------------------------------------------
# 崩溃恢复 + ACK 重放幂等（E-6 / spec §10.3 ACK 重放）
# ---------------------------------------------------------------------------


async def test_crash_after_tx1_replays_to_completion(db_session):
    """E-6 崩溃恢复正向：Tx1 提交后崩溃（checkpoint erasing + attempt + intent 已
    持久化）-> 同 invocation 重放精确重验续做 Tx2，adapter 幂等去重（calls==1），
    binding closed + ref 清 + ACK。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    crash_adapter = _CrashOnFirstCall()
    participant = _participant(db_session, crash_adapter)
    with pytest.raises(RuntimeError):
        await participant.erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    # 崩溃后状态：Tx1 已提交——checkpoint erasing + attempt=1 + intent digest。
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ERASING.value
    assert cp["attempt"] == 1
    assert cp["checkpoint_digest"] is not None
    # DR-2 判别力：第一次 adapter 副作用已发生（calls==1）但 Tx2 **未落地**——
    # binding 仍 active + ref 保留（crash 在 adapter 副作用后、Tx2 关 binding 前）。
    assert crash_adapter.calls == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "active"
    await db_session.commit()

    # 同 invocation 重放（operation revision 语义：operation 已 running，caller 传
    # mark_running 后的 revision=2）。
    op_rev = (
        await db_session.execute(
            text("SELECT revision FROM metaedu.agent_conversation_purges WHERE id = :op"),
            {"op": op_id},
        )
    ).scalar_one()
    adapter2 = _SuccessAdapter()
    await _participant(db_session, adapter2).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )
    # 重放完整执行 Tx2（checkpoint ERASING 续做分支，attempt 不变、intent 匹配）——
    # binding closed + ref 清 + ACK；重放进程 adapter 调用恰为 1（幂等 key 去重）。
    assert adapter2.calls == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] is None
    assert binding["status"] == "closed"
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value
    fence = await _fence_state(db_session, conv_id)
    assert fence["state"] == "erased"


async def test_erased_fence_replay_repairs_pending_checkpoint(db_session):
    """spec §10.3 ACK 重放：erased fence 幂等重放修复 pending checkpoint（ACK 丢失
    恢复），adapter 不重复调用。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    # 第一次：正常 destroy 到 ACK（fence erased + checkpoint acked）。
    adapter1 = _SuccessAdapter()
    await _participant(db_session, adapter1).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    # 模拟 ACK 丢失：把 checkpoint 拉回 pending（fence 已 erased）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET state = 'pending', "
            "ack_digest = NULL, checkpoint_digest = NULL WHERE purge_operation_id = :op"
        ),
        {"op": op_id},
    )
    await db_session.commit()
    # 重放：erased fence 路径修复 pending checkpoint（adapter 不重复调用）。
    # operation 已 running（revision=2，第一次 mark_running bump 过）——重放须
    # 传当前 revision（erased-fence 修复路径的 operation CAS）。
    op_rev = (
        await db_session.execute(
            text("SELECT revision FROM metaedu.agent_conversation_purges WHERE id = :op"),
            {"op": op_id},
        )
    ).scalar_one()
    adapter2 = _SuccessAdapter()
    summary = await _participant(db_session, adapter2).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )
    assert adapter2.calls == 0  # 幂等重放不调 adapter
    # 重放修复后 scan 反映已关闭 binding（destroyed_bindings=1，active=0）。
    assert summary.destroyed_bindings == 1
    assert summary.scan.total == 0
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] is None
    assert binding["status"] == "closed"


async def test_erased_fence_replay_scan_nonzero_fail_closed(db_session):
    """erased fence 但 binding 残留非零 -> fail closed（session 泄漏，不修复 checkpoint）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    # 直接把 fence 置 erased（模拟已完成 purge 但 binding 残留泄漏）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = 'erased', "
            "ack_digest = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', "
            "acked_at = clock_timestamp() "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
    )
    await db_session.commit()

    with pytest.raises(ValueError):
        await _participant(db_session, _SuccessAdapter()).erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


# ---------------------------------------------------------------------------
# E-2b idempotency key 稳定性（跨 takeover）
# ---------------------------------------------------------------------------


async def test_idempotency_key_stable_across_lease_epoch(db_session):
    """E-2b 镜像：idempotency key 由 ref + adapter 派生，不含 lease_epoch/attempt
    （跨 takeover 稳定——新 lease 用同 key 去重）。"""
    await _ensure_test_tenant(db_session)
    key1 = runtime_destroy_idempotency_key(
        runtime_session_ref=_REF_VALUE,
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    key2 = runtime_destroy_idempotency_key(
        runtime_session_ref=_REF_VALUE,
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert key1 == key2
    # 改 ref / adapter 身份 -> key 变化（身份输入敏感）。
    key3 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/OTHER",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert key3 != key1


async def test_replay_does_not_double_destroy(db_session):
    """E-6 无重复副作用：同 binding 崩溃重放后 adapter 总调用数仍为 1（幂等 key +
    checkpoint attempt 去重）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    crash_adapter = _CrashOnFirstCall()
    participant = _participant(db_session, crash_adapter)
    with pytest.raises(RuntimeError):
        await participant.erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    assert crash_adapter.calls == 1
    await db_session.commit()
    op_rev = (
        await db_session.execute(
            text("SELECT revision FROM metaedu.agent_conversation_purges WHERE id = :op"),
            {"op": op_id},
        )
    ).scalar_one()
    await _participant(db_session, _SuccessAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )
    assert crash_adapter.calls == 1  # crash adapter 只调用一次


# ---------------------------------------------------------------------------
# E-3b 镜像：blocked/unknown 查询 + 有证据 reconcile
# ---------------------------------------------------------------------------


async def test_query_blocked_unknown_bindings(db_session):
    """E-3b 镜像：blocked/unknown binding 查询（invalid + ref 非空）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    await db_session.commit()

    rows = await _participant(db_session, _UnknownAdapter()).list_blocked_unknown_bindings(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
    )
    # 尚未 erase——无 invalid 行。
    assert rows == []

    # 先 erase 到 blocked/unknown。
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()
    await _participant(db_session, _UnknownAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    rows = await _participant(db_session, _SuccessAdapter()).list_blocked_unknown_bindings(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
    )
    assert len(rows) == 1
    assert str(rows[0]["id"]) == str(binding_id)
    assert rows[0]["runtime_session_ref"] == _REF_VALUE
    assert rows[0]["status"] == "invalid"


async def test_reconcile_with_evidence_closes_binding(db_session):
    """E-3b 镜像：有证据 reconcile——receipt lookup 返回 evidence -> 清 ref + 关
    binding（补 erased）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    # 先 erase 到 unknown。
    await _participant(db_session, _UnknownAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    binding = await _load_binding(db_session, binding_id)
    assert binding["status"] == "invalid"
    await db_session.commit()

    # reconcile：receipt 可得 -> closed。
    adapter = _ReceiptLookupAdapter()
    result = await _participant(db_session, adapter).reconcile_runtime_binding(
        tenant_id=TENANT_ID,
        binding_id=binding_id,
    )
    assert result == "closed"
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] is None
    assert binding["status"] == "closed"
    assert adapter.calls == 0  # reconcile 只查 receipt，不调 destroy


async def test_reconcile_without_evidence_keeps_state(db_session):
    """E-3b 镜像：无 receipt / 空 evidence -> 保持原状态（禁止无 receipt 强制 erased）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    await _participant(db_session, _UnknownAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    await db_session.commit()

    result = await _participant(db_session, _NoReceiptAdapter()).reconcile_runtime_binding(
        tenant_id=TENANT_ID,
        binding_id=binding_id,
    )
    assert result == "invalid"  # 无 receipt 保持
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] == _REF_VALUE
    assert binding["status"] == "invalid"


async def test_reconcile_requires_receipt_lookup_capability(db_session):
    """E-3b 镜像：adapter 缺 receipt lookup -> reconcile 保持原状态（不做无证强制）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    await _participant(db_session, _UnknownAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    await db_session.commit()

    result = await _participant(db_session, _SuccessAdapter()).reconcile_runtime_binding(
        tenant_id=TENANT_ID,
        binding_id=binding_id,
    )
    assert result == "invalid"


# ---------------------------------------------------------------------------
# registry fail closed + fake 不冒充真实 spool
# ---------------------------------------------------------------------------


async def test_capability_gate_fail_closed_when_registry_false(db_session, monkeypatch):
    """E-4：registry 恢复 False 时入口 fail closed（生产 registry 全程 False）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    # undo autouse fixture 的 monkeypatch——恢复生产 registry（runtime False）。
    monkeypatch.undo()
    from app.composition.agent_erasure_registry import OwnerCapabilityUnavailableError

    with pytest.raises(OwnerCapabilityUnavailableError):
        await _participant(db_session, _SuccessAdapter()).erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )


async def test_runtime_spool_capability_has_no_clear_path(db_session, monkeypatch):
    """D7 / E-7 边界：``runtime_spool`` capability 当前无实现、无清除路径——fake
    只覆盖 ``runtime_session_ref``，不冒充真实 spool 已完成。断言生产 registry 中
    ``runtime_spool`` 存在但 ``erase_available=False``。"""
    import app.composition.agent_erasure_registry as registry_module

    # undo autouse fixture 的 monkeypatch——恢复生产 registry（runtime False）。
    monkeypatch.undo()
    runtime = registry_module.require_owner(RUNTIME_PRIVATE_OWNER)
    assert "runtime_spool" in runtime.capabilities
    assert "runtime_session_ref" in runtime.capabilities
    # 生产 registry 全程 False（E-4）。
    assert runtime.erase_available is False


# ---------------------------------------------------------------------------
# spec §10.3 写路径 conformance：旧 epoch event + 迟到 seq（purge 窗口内 fail
# closed，不重建正文）
# ---------------------------------------------------------------------------


async def _seed_native_running(
    session, *, conversation_id: uuid.UUID
) -> tuple[object, object, object, uuid.UUID, object]:
    """bootstrap native runtime identity + create/start/run（e1_helpers 镜像）。

    先种 active Conversation 行（``require_active_fence`` 需经
    ``session.get(ConversationModel, conversation_id)`` 加载）。返回
    (coordinator, command, binding, stream_id, run)。
    """
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
    from app.contexts.agent_execution.domain import RunStatus
    from tests.contexts.agent_execution.e1_helpers import (
        READONLY_NATIVE_CAPABILITIES,
        AllowStartBarrier,
        bootstrap_compatibility,
        bootstrap_native_binding,
        make_run_command,
    )

    await _insert_active_conversation(
        session, tenant_id=TENANT_A, conversation_id=conversation_id
    )
    identity = await bootstrap_compatibility(session)
    profile_id, binding, stream_id = await bootstrap_native_binding(
        session, identity, conversation_id=conversation_id
    )
    command = make_run_command(
        identity,
        tenant_id=TENANT_A,
        conversation_id=conversation_id,
        runtime_profile_id=profile_id,
        runtime_capabilities=READONLY_NATIVE_CAPABILITIES,
        runtime_binding_id=binding.id,
    )
    coordinator = RunCoordinator(session, start_barrier=AllowStartBarrier())
    created = await coordinator.create_run(command)
    run, _ = await coordinator.start_run(
        tenant_id=command.tenant_id,
        run_id=created.run.id,
        expected_revision=created.run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=command.tenant_id,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Pi read-only Runtime is running",
    )
    await session.commit()
    return coordinator, command, binding, stream_id, run


async def _insert_active_conversation(
    session, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    """种 active Conversation 行（S3C e2e 同款最小列，满足 require_active_fence
    的 ``session.get(ConversationModel)`` 加载）。"""
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, state, title_source, "
            " next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            " purge_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tenant, :actor, :digest, 'active', 'none', 1, 1, "
            " now(), 'not_scheduled', 0, 1, now(), now())"
        ),
        {
            "id": conversation_id,
            "tenant": tenant_id,
            "actor": uuid.uuid4(),
            "digest": "a" * 64,
        },
    )
    await session.flush()


async def _ensure_execution_fence(session, *, tenant_id, conversation_id) -> None:
    """经 fenced port 惰性建 execution.core.v1 active fence（与生产路径一致），
    供随后 UPDATE 为 erasing/erased。"""
    from app.composition.execution_fenced_port import FencedExecutionPort

    await FencedExecutionPort(session).require_active_fence(
        tenant_id=tenant_id, conversation_id=conversation_id
    )
    await session.commit()


def _runtime_command(
    *,
    command,
    binding,
    stream_id: uuid.UUID,
    seq: int,
    digest: str,
    epoch: int | None = None,
    event_id: uuid.UUID | None = None,
) -> object:
    from app.contexts.agent_execution.application.dto import RuntimeEventCommand
    from app.contexts.agent_execution.domain import RunEventType
    from app.contexts.agent_execution.domain.runtime_ingest import (
        RuntimeEventProvenance,
        RuntimeIngestFrame,
    )
    from tests.contexts.agent_execution.e1_helpers import make_event

    return RuntimeEventCommand(
        frame=RuntimeIngestFrame(
            tenant_id=command.tenant_id,
            conversation_id=command.conversation_id,
            run_id=command.run_id,
            runtime_profile_id=command.runtime_profile_id,
            provenance=RuntimeEventProvenance(
                binding_id=binding.id,
                runtime_epoch=epoch if epoch is not None else binding.current_epoch,
                runtime_seq=seq,
                runtime_event_id=event_id or uuid.uuid4(),
            ),
            event_digest=digest,
        ),
        stream_id=stream_id,
        event=make_event(
            event_type=RunEventType.PLAN_SUMMARY,
            summary=f"Runtime event {seq}",
            correlation_id=command.correlation_id,
        ),
    )


async def test_late_seq_gap_fail_closed(db_session):
    """spec §10.3 迟到 seq：purge 窗口前 seq gap -> RuntimeSequenceGapError（不重建
    正文、不推进 ack）。"""
    from app.contexts.agent_execution.domain.runtime_ingest import RuntimeSequenceGapError

    conversation_id = uuid.uuid4()
    coordinator, command, binding, stream_id, _ = await _seed_native_running(
        db_session, conversation_id=conversation_id
    )
    # seq=1 正常 ingest。
    digest = "e" * 64
    await coordinator.ingest_runtime_event(
        _runtime_command(
            command=command, binding=binding, stream_id=stream_id, seq=1, digest=digest
        )
    )
    # seq=3（gap，跳过 2）-> RuntimeSequenceGapError。
    with pytest.raises(RuntimeSequenceGapError):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command, binding=binding, stream_id=stream_id, seq=3, digest=digest
            )
        )
    # ack 不推进（仍为 1）。
    binding_row = (
        await db_session.execute(
            text(
                "SELECT acked_through_runtime_seq FROM "
                "metaedu.agent_runtime_session_bindings WHERE id = :id"
            ),
            {"id": binding.id},
        )
    ).scalar_one()
    assert binding_row == 1


async def test_old_epoch_event_fail_closed(db_session):
    """spec §10.3 旧 epoch event：epoch 低于 binding current_epoch ->
    RuntimeEpochMismatchError（旧 epoch 迟到写被拒，不复活正文）。"""
    from app.contexts.agent_execution.domain.runtime_ingest import RuntimeEpochMismatchError

    conversation_id = uuid.uuid4()
    coordinator, command, binding, stream_id, _ = await _seed_native_running(
        db_session, conversation_id=conversation_id
    )
    digest = "e" * 64
    # 把 binding.current_epoch 推进到 2（模拟 resume/restore 已推进 epoch），当前
    # 事件的 runtime_epoch=1 即旧 epoch。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_runtime_session_bindings "
            "SET current_epoch = 2, revision = revision + 1 "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_A, "id": binding.id},
    )
    await db_session.commit()
    # 提交 epoch=1（旧）-> mismatch。
    with pytest.raises(RuntimeEpochMismatchError):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=1,
                digest=digest,
                epoch=1,
            )
        )
    # 无 runtime-provenance 事件落库（正文未复活；seed 的 starting/running 是
    # execution 生命周期事件，无 runtime provenance）。
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :t AND run_id = :r AND runtime_binding_id IS NOT NULL"
            ),
            {"t": command.tenant_id, "r": command.run_id},
        )
    ).scalar_one()
    assert count == 0


async def test_purge_fence_rejects_late_runtime_ingest(db_session):
    """spec §10.3 迟到 event（purge 窗口内）：execution fence 置 erasing 后
    ``fenced_ingest_runtime_event`` -> LateBodyWriteRejectedError，不重建正文（Spec
    §6.2 第 4 步：fence 非 active 只能拒绝或写无正文 tombstone）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
    from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError
    from tests.contexts.agent_execution.e1_helpers import AllowStartBarrier

    conversation_id = uuid.uuid4()
    _, command, binding, stream_id, _ = await _seed_native_running(
        db_session, conversation_id=conversation_id
    )
    # 经 fenced port 惰性建 execution active fence（供随后置 erasing）。
    await _ensure_execution_fence(
        db_session, tenant_id=command.tenant_id, conversation_id=conversation_id
    )
    # 先正常 ingest seq=1（正文已存在），再置 execution fence 为 erasing。
    digest = "e" * 64
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    await coordinator.ingest_runtime_event(
        _runtime_command(
            command=command, binding=binding, stream_id=stream_id, seq=1, digest=digest
        )
    )
    # 置 execution.core.v1 fence 为 erasing（purge 窗口）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = 'erasing' "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {"t": command.tenant_id, "c": conversation_id, "o": "execution.core.v1"},
    )
    await db_session.commit()
    count_before = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :t AND run_id = :r AND runtime_binding_id IS NOT NULL"
            ),
            {"t": command.tenant_id, "r": command.run_id},
        )
    ).scalar_one()

    # late ingest seq=2 -> LateBodyWriteRejectedError（fence 非 active）。
    port = FencedExecutionPort(db_session)
    with pytest.raises(LateBodyWriteRejectedError):
        await port.fenced_ingest_runtime_event(
            tenant_id=command.tenant_id,
            conversation_id=conversation_id,
            run_id=command.run_id,
            command=_runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=2,
                digest=digest,
            ),
        )
    # 无新 runtime event 落库（不重建正文）。
    count_after = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :t AND run_id = :r AND runtime_binding_id IS NOT NULL"
            ),
            {"t": command.tenant_id, "r": command.run_id},
        )
    ).scalar_one()
    assert count_after == count_before


async def test_purge_fence_erased_rejects_late_runtime_ingest(db_session):
    """spec §10.3：fence 已 erased（purge 完成）后迟到 runtime event 同样被拒
    （不重建正文）。"""
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError

    conversation_id = uuid.uuid4()
    _, command, binding, stream_id, _ = await _seed_native_running(
        db_session, conversation_id=conversation_id
    )
    # 经 fenced port 惰性建 execution active fence（供随后置 erased）。
    await _ensure_execution_fence(
        db_session, tenant_id=command.tenant_id, conversation_id=conversation_id
    )
    digest = "e" * 64
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = 'erased', "
            "ack_digest = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', "
            "acked_at = clock_timestamp() "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {"t": command.tenant_id, "c": conversation_id, "o": "execution.core.v1"},
    )
    await db_session.commit()
    port = FencedExecutionPort(db_session)
    with pytest.raises(LateBodyWriteRejectedError):
        await port.fenced_ingest_runtime_event(
            tenant_id=command.tenant_id,
            conversation_id=conversation_id,
            run_id=command.run_id,
            command=_runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=1,
                digest=digest,
            ),
        )
    # 无 runtime-provenance 事件落库（fence 已 erased，正文不得复活；seed 的
    # starting/running 事件是 execution 生命周期事件，无 runtime provenance）。
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :t AND run_id = :r AND runtime_binding_id IS NOT NULL"
            ),
            {"t": command.tenant_id, "r": command.run_id},
        )
    ).scalar_one()
    assert count == 0

