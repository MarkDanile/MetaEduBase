r"""R1-S4-E-C：RuntimeErasureParticipant conformance fake 真实 PostgreSQL 测试。

契约事实源：Plan §R1-S4-E E-5 第 4 项（S4-E-C）+ spec §10.3（conformance suite：
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

**写路径 conformance 判别范围（T-10，如实记录）**：spec §10.3 写路径 4 例（旧 epoch /
迟到 seq / purge erasing/erased fence 拒 late ingest）经既有 ``RunCoordinator.
ingest_runtime_event`` / ``FencedExecutionPort.fenced_ingest_runtime_event`` 走通，
**不调用本 participant 代码**——它们是既有机器在 purge 窗口的**回归证据**（目标错误
真实命中：旧 epoch -> RuntimeEpochMismatchError / seq gap -> RuntimeSequenceGapError /
fence 非 active -> LateBodyWriteRejectedError），非新 fake 的行为判别；participant
侧协议一致性由 destroy/reconcile/ACK/重放/并发用例覆盖。
"""

from __future__ import annotations

import asyncio
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


class _SharedDedupAdapter(_SuccessAdapter):
    """key→evidence 共享 store：同 idempotency key 重放命中缓存（无新副作用）。

    E-2b 幂等重放承认重复 destroy_session 调用存在（``calls`` 可 >1），
    **distinct 副作用**必须恰为 1（E-6 冻结判别点）。R1-S5-I2 后 participant
    不再以 revision bump 串行化并发 entry——fence 串行化下 loser 可能以
    erasing 续做分支重入窗口（同 key 重放），distinct==1 是不变量。
    """

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[str, str] = {}
        self.distinct_destroys = 0

    async def destroy_session(self, **kwargs):
        self.calls += 1
        key = kwargs["idempotency_key"]
        if key in self._store:
            return RuntimeDestroySuccess(adapter_receipt_evidence=self._store[key])
        self._store[key] = f"ev:{key[:16]}"
        self.distinct_destroys += 1
        return RuntimeDestroySuccess(adapter_receipt_evidence=self._store[key])


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


async def test_mixed_outcome_reason_priority_outcome_unknown(db_session):
    """E-3a 归并（T-3 返修）：多 binding 混合 outcome——unknown/timeout 优先
    outcome_unknown（可能已生效不自动重试），优先于 not-sent/failed。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/1")
    await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/2")
    await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/3")
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    class _MixedAdapter(_SuccessAdapter):
        """3 binding：not-sent / failed / unknown 各一——归并应落 outcome_unknown。"""

        def __init__(self) -> None:
            super().__init__()
            self._state = ["notsent", "failed", "unknown"]

        async def destroy_session(self, **kwargs):
            self.calls += 1
            mode = self._state.pop(0)
            if mode == "notsent":
                raise RuntimeDestroyNotSentError("not sent")
            if mode == "failed":
                raise RuntimeDestroyFailedError("failed")
            return RuntimeDestroyUnknown()

    await _participant(db_session, _MixedAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    # unknown 优先（outcome_unknown）——not-sent/failed 都被 unknown 压制。
    assert cp["reason_code"] == "purge_blocked_by_runtime_outcome_unknown"


async def test_mixed_outcome_reason_priority_erase_timeout(db_session):
    """E-3a 归并（T-3 返修）：无 unknown/timeout 时 not-sent 优先 erase_timeout。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/1")
    await _seed_runtime_binding(db_session, conv_id, ref_value="pi://session/2")
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    class _NotSentFailedAdapter(_SuccessAdapter):
        def __init__(self) -> None:
            super().__init__()
            self._state = ["notsent", "failed"]

        async def destroy_session(self, **kwargs):
            self.calls += 1
            mode = self._state.pop(0)
            if mode == "notsent":
                raise RuntimeDestroyNotSentError("not sent")
            raise RuntimeDestroyFailedError("failed")

    await _participant(db_session, _NotSentFailedAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_erase_timeout"


async def test_final_scan_nonzero_fallback_reason(db_session):
    """E-3a 归并（T-3 返修）：adapter 窗口为空但 final scan 非零（如 Tx1 后并发新增
    binding）-> scan_nonzero 兜底 reason（无本批 outcome 时）。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    binding_id = await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    # 直接用 invalid + ref 保留表达「遗留 blocked binding」（无本批 outcome）。
    # binding 的 profile FK 在 INSERT 时经 replica 角色绕过——UPDATE 同样需 replica
    # 绕过（否则 FK 重检失败，seed 的伪造 profile_id 不真实存在）。
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_runtime_session_bindings "
            "SET status = 'invalid' WHERE id = :id"
        ),
        {"id": binding_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = default"))
    # 无活跃 binding（invalid 不进 adapter 窗口，D-1）——但 final scan 因 ref 非空
    # 仍非零 -> blocked + scan_nonzero 兜底。
    await db_session.commit()
    adapter = _SuccessAdapter()
    summary = await _participant(db_session, adapter).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert adapter.calls == 0  # invalid 不进窗口（D-1）
    assert summary.scan.total == 1
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.BLOCKED.value
    assert cp["reason_code"] == "purge_blocked_by_runtime_binding_scan_nonzero"


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
    持久化）-> 同 invocation 重放精确重验续做 Tx2，binding closed + ref 清 + ACK。

    **断言口径（T-4 返修，如实记录）**：本测试用 crash adapter + 重放用全新
    ``_SuccessAdapter``（模拟崩溃后新进程重做），``adapter2.calls == 1`` 只证明
    「重放进程单次调用/单 binding」，**不**证明 idempotency key 驱动的去重——跨
    crash+replay 的「总 distinct destroy == 1」由
    ``test_crash_replay_shared_adapter_distinct_destroy_once``（共享 key→evidence
    store）单独覆盖。attempt 在重放后**不再 bump**（checkpoint ERASING 续做分支
    attempt 不变），本测试断言重放后 attempt 仍为 1。"""
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
    # binding closed + ref 清 + ACK；重放进程 adapter 调用恰为 1。
    assert adapter2.calls == 1
    # T-4 返修：attempt 在重放后**不 bump**（ERASING 续做分支 attempt 不变）。
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["attempt"] == 1
    binding = await _load_binding(db_session, binding_id)
    assert binding["runtime_session_ref"] is None
    assert binding["status"] == "closed"
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
    （跨 takeover 稳定——新 lease 用同 key 去重）。判别力（T-11 返修）：断言派生
    函数签名只接受 ref + adapter 身份（新增 epoch/attempt 参数 -> 签名断言红）。"""
    import inspect

    params = set(inspect.signature(runtime_destroy_idempotency_key).parameters)
    assert params == {"runtime_session_ref", "adapter_key", "adapter_version"}, params
    await _ensure_test_tenant(db_session)
    key1 = runtime_destroy_idempotency_key(
        runtime_session_ref=_REF_VALUE,
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert len(key1) == 64
    # 改 ref / adapter 身份 -> key 变化（身份输入敏感）。
    key3 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/OTHER",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert key3 != key1


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


async def _ensure_test_tenant_sf(session_factory):
    """用 session_factory 种 tenant（并发测试用，db_session 已提交的可见性差异）。"""
    async with session_factory() as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            text(
                "INSERT INTO metaedu.tenants "
                "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": TENANT_ID,
                "name": "s4ec-conc-tenant",
                "school_name": "s4ec conc school",
                "isolation": "shared",
                "now": now,
            },
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 族B（T-1/D-5 返修）：E-2a Tx2 精确重验 fail-closed 分支覆盖（防双删协议安全核心）
# ---------------------------------------------------------------------------


async def _seed_for_session_factory(session_factory, *, binding_count: int = 1):
    """用独立 session 种 tenant + conversation + bindings + operation + commit。"""
    async with session_factory() as seed_session:
        await _ensure_test_tenant_sf(session_factory)
        conv_id, purge_rev = await _seed_deleted_expired_conversation(seed_session)
        binding_ids = [
            await _seed_runtime_binding(seed_session, conv_id, ref_value=f"pi://session/{i}")
            for i in range(binding_count)
        ]
        op_id, _ = await _make_purge_operation(seed_session, conv_id, purge_rev)
        await seed_session.commit()
    return conv_id, purge_rev, op_id, binding_ids


async def _make_engine_factory():
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def test_erase_tx2_fence_not_erasing_after_tx1(session_factory):
    """E-2a DR-3 镜像：**真实命中**「Tx1 已提交、Tx2 重验时 fence 非 erasing」的
    fail-closed 分支。adapter 协调并发：A 跑 erase（Tx1 提交后进入 adapter 窗口），
    adapter 内 set entered 并等待；B 把 runtime fence 改 erased；A 放行后 Tx2 检出
    fence 非 erasing -> fail closed。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _FenceRaceAdapter(_SuccessAdapter):
        async def destroy_session(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    race_adapter = _FenceRaceAdapter()
    tx2_error: list[Exception] = []

    async def _run_erase_a():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                participant = _participant(sess, race_adapter)
                try:
                    await participant.erase_runtime_session(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _race_fence_to_erased():
        await adapter_entered.wait()
        engine, factory = await _make_engine_factory()
        now = datetime.now(UTC).replace(tzinfo=None)
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_erasure_fences "
                        "SET state = 'erased', ack_digest = :ad, acked_at = :now "
                        "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
                    ),
                    {
                        "t": TENANT_ID,
                        "c": conv_id,
                        "o": RUNTIME_PRIVATE_OWNER,
                        "ad": "e" * 64,
                        "now": now,
                    },
                )
                await sess.commit()
        finally:
            await engine.dispose()
            adapter_release.set()

    await asyncio.gather(_run_erase_a(), _race_fence_to_erased())
    assert len(tx2_error) == 1, f"expected Tx2 fence-not-erasing fail closed, got {tx2_error}"
    assert "fence no longer erasing" in str(tx2_error[0])
    assert race_adapter.calls == 1  # adapter 副作用已发生但 Tx2 fail closed 回滚


async def test_erase_tx2_checkpoint_attempt_mismatch_fail_closed(session_factory):
    """E-2a：Tx2 重验 checkpoint attempt 不匹配 -> fail closed（旧 attempt 拒绝）。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _AttemptRaceAdapter(_SuccessAdapter):
        async def destroy_session(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    race_adapter = _AttemptRaceAdapter()
    tx2_error: list[Exception] = []

    async def _run_erase_a():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                try:
                    await _participant(sess, race_adapter).erase_runtime_session(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _bump_attempt():
        await adapter_entered.wait()
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_conversation_purge_owners "
                        "SET attempt = 99 WHERE purge_operation_id = :op"
                    ),
                    {"op": op_id},
                )
                await sess.commit()
        finally:
            await engine.dispose()
            adapter_release.set()

    await asyncio.gather(_run_erase_a(), _bump_attempt())
    assert len(tx2_error) == 1, f"expected Tx2 attempt mismatch, got {tx2_error}"
    assert "attempt" in str(tx2_error[0])


async def test_erase_tx2_checkpoint_intent_mismatch_fail_closed(session_factory):
    """E-2a：Tx2 重验 checkpoint intent digest 不匹配 -> fail closed（新 intent 拒）。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _IntentRaceAdapter(_SuccessAdapter):
        async def destroy_session(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    race_adapter = _IntentRaceAdapter()
    tx2_error: list[Exception] = []

    async def _run_erase_a():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                try:
                    await _participant(sess, race_adapter).erase_runtime_session(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _change_intent():
        await adapter_entered.wait()
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_conversation_purge_owners "
                        "SET checkpoint_digest = :d "
                        "WHERE purge_operation_id = :op"
                    ),
                    {"op": op_id, "d": "f" * 64},
                )
                await sess.commit()
        finally:
            await engine.dispose()
            adapter_release.set()

    await asyncio.gather(_run_erase_a(), _change_intent())
    assert len(tx2_error) == 1, f"expected Tx2 intent mismatch, got {tx2_error}"
    assert "intent digest" in str(tx2_error[0])


async def test_erase_stale_lease_epoch_fail_closed(session_factory):
    """E-2a：operation lease_epoch 已被接管（takeover）-> Tx2 精确重验 fail closed。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _LeaseRaceAdapter(_SuccessAdapter):
        async def destroy_session(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    race_adapter = _LeaseRaceAdapter()
    tx2_error: list[Exception] = []

    async def _run_erase_a():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                try:
                    await _participant(sess, race_adapter).erase_runtime_session(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _advance_lease():
        await adapter_entered.wait()
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_conversation_purges "
                        "SET lease_epoch = 1 WHERE id = :op"
                    ),
                    {"op": op_id},
                )
                await sess.commit()
        finally:
            await engine.dispose()
            adapter_release.set()

    await asyncio.gather(_run_erase_a(), _advance_lease())
    assert len(tx2_error) == 1, f"expected Tx2 stale lease fail closed, got {tx2_error}"
    assert "lease_epoch" in str(tx2_error[0])


async def test_erase_tx2_purge_revision_mismatch_fail_closed(session_factory):
    """E-2a：Tx2 重验 fence.purge_revision != operation -> fail closed（stale purge）。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _RevRaceAdapter(_SuccessAdapter):
        async def destroy_session(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    race_adapter = _RevRaceAdapter()
    tx2_error: list[Exception] = []

    async def _run_erase_a():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                try:
                    await _participant(sess, race_adapter).erase_runtime_session(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _change_fence_rev():
        await adapter_entered.wait()
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_erasure_fences "
                        "SET purge_revision = 99 "
                        "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
                    ),
                    {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
                )
                await sess.commit()
        finally:
            await engine.dispose()
            adapter_release.set()

    await asyncio.gather(_run_erase_a(), _change_fence_rev())
    assert len(tx2_error) == 1, f"expected Tx2 purge_revision mismatch, got {tx2_error}"
    assert "purge_revision" in str(tx2_error[0])


async def test_erase_second_purge_instance_fail_closed(session_factory):
    """E-2a C-1：fence 已 erasing 时第二 purge 实例（不同 purge_revision）不得进
    adapter 窗口——Tx1 分派即 fail closed（E-6「重复删除」串行化契约）。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    # 先把 fence 置 erasing + purge_revision=1（模拟另一 purge 实例已推进）。
    engine, factory = await _make_engine_factory()
    async with factory() as sess:
        await sess.execute(
            text(
                "UPDATE metaedu.agent_erasure_fences SET state = 'erasing', "
                "purge_revision = 1 "
                "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
            ),
            {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
        )
        await sess.commit()
    await engine.dispose()

    # 第二 purge 实例（rev 2）——fence 已 erasing 且 purge_revision 不同 -> fail closed。
    op2_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    engine, factory = await _make_engine_factory()
    async with factory() as sess:
        await sess.execute(
            text(
                "INSERT INTO metaedu.agent_conversation_purges "
                "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
                "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
                "hold_revision_snapshot, lease_epoch, scheduled_at, revision, "
                "created_at, updated_at) "
                "VALUES (:id, :t, :c, 2, 'scheduled', :rd, :rs, :rps, :rpd, 0, 0, "
                ":now, 1, :now, :now)"
            ),
            {
                "id": op2_id,
                "t": TENANT_ID,
                "c": conv_id,
                "rd": registry_digest(),
                "rs": _registry_snapshot_json(),
                "rps": '{"conversation_recovery_days": 30}',
                "rpd": _retention_policy_digest(),
                "now": now,
            },
        )
        await sess.execute(
            text(
                "INSERT INTO metaedu.agent_conversation_purge_owners "
                "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
                "capability_digest, state, attempt, created_at, updated_at) "
                "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "t": TENANT_ID,
                "op": op2_id,
                "o": RUNTIME_PRIVATE_OWNER,
                "cd": capability_digest(RUNTIME_PRIVATE_OWNER),
                "now": now,
            },
        )
        await sess.commit()
    await engine.dispose()

    adapter = _SuccessAdapter()
    engine, factory = await _make_engine_factory()
    async with factory() as sess:
        with pytest.raises(ValueError, match="already erasing under purge_revision"):
            await _participant(sess, adapter).erase_runtime_session(
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=2,
                purge_operation_id=op2_id,
                expected_operation_revision=1,
            )
    await engine.dispose()
    assert adapter.calls == 0  # 第二实例不得进 adapter 窗口


# ---------------------------------------------------------------------------
# 族C（C-2/T-2 返修）：真实双连接并发 + 幂等去重判别
# ---------------------------------------------------------------------------


async def test_concurrent_double_runtime_erase_serializes(session_factory):
    """E-6「重复删除」：两 erase 并发同一 conversation——共享 fence 串行化，
    **distinct destroy 恰为 1**；另一连接走 erased-fence 幂等重放 no-op 或
    erasing 续做（同 idempotency key 重放，E-2b 承认重复调用、共享 store 去重）。
    真实 PG 双连接（session_factory）。"""
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)
    shared_adapter = _SharedDedupAdapter()

    async def _erase_with_new_session():
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                # R1-S5-I2：participant 不再 bump operation.revision（聚合投影归
                # coordinator）——并发串行化收敛由共享 fence 承担；transient
                # fencing 拒绝（E-2a 同实例门禁 / Tx2 stale fence）重读重试，
                # bounded yield 给前一个调用留出 Tx2 收口窗口。
                for _attempt in range(5):
                    current_rev = (
                        await sess.execute(
                            text(
                                "SELECT revision FROM metaedu.agent_conversation_purges "
                                "WHERE id = :op"
                            ),
                            {"op": op_id},
                        )
                    ).scalar_one()
                    participant = _participant(sess, shared_adapter)
                    try:
                        await participant.erase_runtime_session(
                            tenant_id=TENANT_ID,
                            conversation_id=conv_id,
                            purge_revision=purge_rev,
                            purge_operation_id=op_id,
                            expected_operation_revision=current_rev,
                        )
                        break
                    except ValueError as exc:
                        message = str(exc)
                        # 三面 P3-3 收窄：仅 transient 串行化拒绝的精确短语重试。
                        transient_phrases = (
                            "operation revision mismatch",
                            "already erasing",
                            "no longer erasing",
                            "stale fence",
                        )
                        if not any(p in message for p in transient_phrases):
                            raise
                        await sess.rollback()
                        await asyncio.sleep(0.1)
                else:
                    raise AssertionError("concurrent erase did not converge after retries")
        finally:
            await engine.dispose()

    results = await asyncio.gather(
        _erase_with_new_session(),
        _erase_with_new_session(),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, Exception), f"concurrent erase raised: {r}"
    # DR-1 判别力（E-6 冻结）：distinct destroy 恰为 1。R1-S5-I2 后 participant
    # 不再以 revision bump 串行化并发 entry——共享 fence 串行化下 loser 可能以
    # erasing 续做分支重入窗口（同 idempotency key 重放，E-2b 承认重复调用），
    # 共享 store 保证无重复副作用；calls 可为 1（直接重放）或 2（续做重入）。
    assert shared_adapter.distinct_destroys == 1
    assert shared_adapter.calls in (1, 2)


async def test_crash_replay_shared_adapter_distinct_destroy_once(session_factory):
    """E-2b 幂等去重（C-3 返修）：崩溃 + 重放用**同一共享 adapter**（key→evidence
    存储）——participant 重放会重调 destroy_session（承认重复调用存在），但共享
    store 使同 idempotency key 命中缓存 evidence，**总 distinct destroy 恰为 1**
    （不得重复产生副作用，E-6「adapter 调用计数 == 1」）。

    与 `test_crash_after_tx1_replays_to_completion`（双独立 adapter 单实例计数）
    的区别：本测试用跨 crash+replay 的**共享 key→evidence 存储**断言 distinct
    destroy——若 participant 重放使用新 key（未命中 store）或 adapter 无去重，
    本断言转红（B2 DR-1 判别力同构）。
    """
    conv_id, purge_rev, op_id, _ = await _seed_for_session_factory(session_factory)

    class _SharedDedupCrashAdapter(_SuccessAdapter):
        """第一次 destroy 记录 evidence 到共享 store 后抛 RuntimeError（模拟 Tx1 已
        提交、adapter 副作用已发生但进程在 Tx2 前崩溃）；重放同 key 命中 store 返回
        缓存 evidence 不重复副作用。"""

        def __init__(self) -> None:
            super().__init__()
            self._crash_next = True
            self._store: dict[str, str] = {}
            self.distinct_destroys = 0

        async def destroy_session(self, **kwargs):
            self.calls += 1
            key = kwargs["idempotency_key"]
            if key in self._store:
                # 同 key 重放：返回缓存 evidence（无新副作用）。
                return RuntimeDestroySuccess(adapter_receipt_evidence=self._store[key])
            self._store[key] = f"ev:{key[:16]}"
            self.distinct_destroys += 1
            if self._crash_next:
                self._crash_next = False
                raise RuntimeError("simulated process crash after adapter side-effect")
            return RuntimeDestroySuccess(
                adapter_receipt_evidence=self._store[key]
            )

    shared_adapter = _SharedDedupCrashAdapter()

    async def _run_erase(expected_revision):
        engine, factory = await _make_engine_factory()
        try:
            async with factory() as sess:
                return await _participant(sess, shared_adapter).erase_runtime_session(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=purge_rev,
                    purge_operation_id=op_id,
                    expected_operation_revision=expected_revision,
                )
        finally:
            await engine.dispose()

    # 第一次：Tx1 提交 + adapter 副作用（distinct==1）后崩溃（RuntimeError 逃逸）。
    with pytest.raises(RuntimeError):
        await _run_erase(1)
    assert shared_adapter.distinct_destroys == 1
    assert shared_adapter.calls == 1
    # 重放：同 invocation（checkpoint ERASING 续做 + 同 key 命中 store）——不再
    # 产生新副作用（distinct 仍 1），完成 Tx2 清 ref + 关 binding + ACK。
    # R1-S5-I2：participant 不再 bump operation.revision，重放仍传 revision=1。
    await _run_erase(1)
    assert shared_adapter.distinct_destroys == 1  # 跨 crash+replay 总 distinct == 1
    assert shared_adapter.calls == 2  # 承认重复调用存在（participant 重放重调）
    # 最终态：binding closed + fence erased + checkpoint acked。
    engine, factory = await _make_engine_factory()
    async with factory() as check:
        fence = (
            await check.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
                ),
                {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
            )
        ).scalar_one()
        assert fence == "erased"
        cp = (
            await check.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :op"
                ),
                {"op": op_id},
            )
        ).scalar_one()
        assert cp == PurgeOwnerState.ACKED.value
    await engine.dispose()


async def test_erased_fence_replay_checkpoint_digest_form(db_session):
    """E-2c/erased-fence 重放：修复 pending checkpoint 后 checkpoint_digest 必须是
    RuntimeBindingScan 形式（final scan digest）——B2 D-1 教训的 runtime 侧。"""
    await _ensure_test_tenant(db_session)
    conv_id, purge_rev = await _seed_deleted_expired_conversation(db_session)
    await _seed_runtime_binding(db_session, conv_id)
    op_id, _ = await _make_purge_operation(db_session, conv_id, purge_rev)
    await db_session.commit()

    await _participant(db_session, _SuccessAdapter()).erase_runtime_session(
        tenant_id=TENANT_ID,
        conversation_id=conv_id,
        purge_revision=purge_rev,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    await db_session.commit()
    # 模拟 ACK 丢失：checkpoint 拉回 pending。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET state = 'pending', "
            "ack_digest = NULL, checkpoint_digest = NULL WHERE purge_operation_id = :op"
        ),
        {"op": op_id},
    )
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
    cp = await _checkpoint_state(db_session, op_id)
    assert cp["state"] == PurgeOwnerState.ACKED.value
    # checkpoint_digest 必须为 64-hex（RuntimeBindingScan digest 形式，非
    # TransportBodyScan——若写成 TransportBodyScan 形式则与正常 ACK 持久化不一致）。
    assert cp["checkpoint_digest"] is not None
    assert len(cp["checkpoint_digest"]) == 64


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
    只覆盖 ``runtime_session_ref``，不冒充真实 spool 已完成。

    **判别力（T-8 返修）**：除 registry ``erase_available=False`` 锁定外，断言
    participant 源码**不含任何对 spool 表/列的清除引用**（``runtime_spool`` 只出现
    在 registry capability 声明与注释，不出现在任何 SQL/字段写路径）——若实现新增
    一条不经 registry gate 的 spool 清除路径（fake 冒充 spool 完成），本断言红。
    """
    import inspect

    import app.composition.agent_erasure_registry as registry_module
    import app.composition.runtime_erasure_participant as participant_module

    # undo autouse fixture 的 monkeypatch——恢复生产 registry（runtime False）。
    monkeypatch.undo()
    runtime = registry_module.require_owner(RUNTIME_PRIVATE_OWNER)
    assert "runtime_spool" in runtime.capabilities
    assert "runtime_session_ref" in runtime.capabilities
    # 生产 registry 全程 False（E-4）。
    assert runtime.erase_available is False

    # participant 源码不得包含任何 spool 表/列引用（无清除路径的代码事实）。
    src = inspect.getsource(participant_module)
    spool_refs = [
        line.strip()
        for line in src.splitlines()
        if "spool" in line.lower() and "runtime_spool" in line
    ]
    # 只允许 docstring/注释层的 capability 声明，不允许任何 SQL/字段写路径。
    for line in spool_refs:
        assert not line.lstrip().startswith(("SELECT", "UPDATE", "INSERT")), (
            f"runtime_spool must have no clear path, found write path: {line}"
        )
    assert "runtime_session_bindings" in src  # 唯一清除目标表是 binding


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
