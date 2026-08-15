"""R1-S5-I2 六 owner participant 去共享投影写真实 PG 测试。

断言核心：六 owner 的 erase 入口（running/blocked/repair/ACK/erased replay 各
路径）全程 **零 operation/Conversation 投影写**——operation.state/failure_code/
started_at/revision 与 Conversation.purge_state/purged_at 快照零变化；owner-scoped
checkpoint/fence/ledger/binding 写保留（acked/erased/blocked 正常落账）。

mutation-kill 方向（S5-A-7 ② 冻结）：守卫断言「participant 擦除全程零
operation/Conversation 写」；变异 = 在任一写点加回 operation.state=.../
conversation.purge_state=... → 本套件必须变红。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import OwnerDefinition
from app.composition.external_object_adapter import (
    ExternalEraseSuccess,
    ExternalObjectAdapter,
)
from app.composition.external_ref_erasure_participant import (
    ExternalPayloadErasureParticipant,
)
from app.composition.runtime_erasure_adapter import (
    RuntimeDestroySuccess,
    RuntimeSessionDestroyAdapter,
)
from app.composition.runtime_erasure_participant import RuntimeErasureParticipant
from app.composition.transport_erasure_participant import (
    TransportErasureParticipantBase,
)
from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    ExecutionErasureParticipant,
)
from app.contexts.agent_execution.infrastructure.execution_transport_erasure_participant import (
    ExecutionTransportErasureParticipant,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
    WorkspaceErasureParticipant,
)
from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
    WorkspaceTransportErasureParticipant,
)

WS_CORE = "workspace.core.v1"
EX_CORE = "execution.core.v1"
WS_TRANSPORT = "workspace.transport.v1"
EX_TRANSPORT = "execution.transport.v1"
EXTERNAL = "external.payload.v1"
RUNTIME = "runtime.private.v1"

_AUDIT_SECRET = "test-audit-secret"
_AUDIT_SECRET_VERSION = 1


# ---------------------------------------------------------------------------
# 种子 helpers
# ---------------------------------------------------------------------------


async def _seed_conversation(session) -> tuple[uuid.UUID, uuid.UUID]:
    """deleted + purge_after 已过 + actor redacted（workspace scan 零前提）。"""
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    purge_after = datetime.now(UTC) - timedelta(days=1)
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) "
            "VALUES (:id, :tid, NULL, 'redacted', :digest, :identity, "
            "'sensitive title', 'none', 'deleted', :purge_after, 'scheduled', "
            "1, 0, 1, now(), now())"
        ),
        {
            "id": cid,
            "tid": tid,
            "digest": "a" * 64,
            "identity": "d" * 64,
            "purge_after": purge_after,
        },
    )
    return tid, cid


async def _seed_operation_and_checkpoint(
    session, tid, cid, owner_key: str, *, hold_revision_snapshot: int = 0
) -> tuple[uuid.UUID, int]:
    repo = AgentErasureRepository(session)
    operation = await repo.create_purge_operation(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=hold_revision_snapshot,
    )
    await repo.create_owner_checkpoint(
        tenant_id=tid,
        purge_operation_id=operation.id,
        owner_key=owner_key,
    )
    return operation.id, operation.revision


async def _read_operation(session, operation_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT state, failure_code, started_at, revision FROM "
                "metaedu.agent_conversation_purges WHERE id=:op"
            ),
            {"op": operation_id},
        )
    ).mappings().one()
    return dict(row)


async def _read_conversation_projection(session, cid: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT purge_state, purged_at FROM metaedu.agent_conversations "
                "WHERE id=:cid"
            ),
            {"cid": cid},
        )
    ).mappings().one()
    return dict(row)


async def _read_checkpoint(session, operation_id: uuid.UUID, owner_key: str) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT state, ack_digest, reason_code FROM "
                "metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id=:op AND owner_key=:owner"
            ),
            {"op": operation_id, "owner": owner_key},
        )
    ).mappings().one()
    return dict(row)


async def _read_fence(session, cid: uuid.UUID, owner_key: str) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT state, ack_digest FROM metaedu.agent_erasure_fences "
                "WHERE conversation_id=:cid AND owner_key=:owner"
            ),
            {"cid": cid, "owner": owner_key},
        )
    ).mappings().one()
    return dict(row)


def _assert_zero_shared_writes(
    operation: dict, conversation: dict, *, operation_id: uuid.UUID, cid: uuid.UUID
) -> None:
    """守卫断言：erase 全程零 operation/Conversation 投影写。"""
    assert operation["state"] == "scheduled", (
        f"operation {operation_id} state changed by participant: {operation['state']}"
    )
    assert operation["failure_code"] is None
    assert operation["started_at"] is None
    assert operation["revision"] == 1, (
        f"operation {operation_id} revision bumped by participant"
    )
    assert conversation["purge_state"] == "scheduled", (
        f"conversation {cid} purge_state changed by participant"
    )
    assert conversation["purged_at"] is None


# ---------------------------------------------------------------------------
# workspace.core.v1
# ---------------------------------------------------------------------------


async def test_workspace_core_ack_path_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_CORE)
    participant = WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    outcome = await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert outcome.blocked is False
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, WS_CORE)
    assert checkpoint["state"] == "acked"  # owner-scoped 写保留
    fence = await _read_fence(db_session, cid, WS_CORE)
    assert fence["state"] == "erased"


async def test_workspace_core_erased_replay_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_CORE)
    participant = WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    # erased-fence 幂等重放：repair 路径不得写 operation/Conversation。
    replay = await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert replay.blocked is False
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )


async def test_workspace_core_legal_hold_blocked_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    # hold 先行（I1 语义：create bump hold_revision 0→1），operation snapshot=1。
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=tid,
    )
    op_id, _ = await _seed_operation_and_checkpoint(
        db_session, tid, cid, WS_CORE, hold_revision_snapshot=1
    )
    participant = WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    outcome = await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert outcome.blocked is True
    assert outcome.block_reason == "purge_blocked_by_legal_hold"
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, WS_CORE)
    assert checkpoint["state"] == "blocked"
    assert checkpoint["reason_code"] == "purge_blocked_by_legal_hold"


# ---------------------------------------------------------------------------
# execution.core.v1
# ---------------------------------------------------------------------------


async def test_execution_core_ack_and_replay_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, EX_CORE)
    participant = ExecutionErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    outcome = await participant.erase_execution_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert outcome.blocked is False
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, EX_CORE)
    assert checkpoint["state"] == "acked"
    fence = await _read_fence(db_session, cid, EX_CORE)
    assert fence["state"] == "erased"
    # erased-fence replay：repair 路径零共享写。
    replay = await participant.erase_execution_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert replay.blocked is False
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )


# ---------------------------------------------------------------------------
# transport 两 owner（复用基类；各 owner 独立判别力测试）
# ---------------------------------------------------------------------------


async def _run_transport_erase_and_assert(
    db_session, tid, cid, op_id, participant: TransportErasureParticipantBase
) -> None:
    outcome = await participant.erase_transport_owner(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert outcome.blocked is False
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )


async def test_workspace_transport_ack_and_replay_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_TRANSPORT)
    participant = WorkspaceTransportErasureParticipant(db_session)
    await _run_transport_erase_and_assert(db_session, tid, cid, op_id, participant)
    checkpoint = await _read_checkpoint(db_session, op_id, WS_TRANSPORT)
    assert checkpoint["state"] == "acked"
    fence = await _read_fence(db_session, cid, WS_TRANSPORT)
    assert fence["state"] == "erased"
    # erased replay。
    await _run_transport_erase_and_assert(db_session, tid, cid, op_id, participant)


async def test_execution_transport_ack_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, EX_TRANSPORT)
    participant = ExecutionTransportErasureParticipant(db_session)
    await _run_transport_erase_and_assert(db_session, tid, cid, op_id, participant)
    checkpoint = await _read_checkpoint(db_session, op_id, EX_TRANSPORT)
    assert checkpoint["state"] == "acked"
    fence = await _read_fence(db_session, cid, EX_TRANSPORT)
    assert fence["state"] == "erased"


async def test_workspace_transport_ref_bearing_blocked_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_TRANSPORT)
    # ref-bearing outbox 行（external receipt 前不得清）→ purge_owner_unavailable。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, conversation_id, event_type, schema_version, "
            "aggregate_id, aggregate_type, payload_ref, payload_inline, "
            "payload_digest, correlation_id, status, attempt_count, created_at) "
            "VALUES (:id, :tid, :cid, 'turn.submitted', 1, :agg, 'turn', "
            "'obj://staging/o/1', NULL, :digest, :corr, 'pending', 0, now())"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tid,
            "cid": cid,
            "agg": uuid.uuid4(),
            "digest": "a" * 64,
            "corr": uuid.uuid4(),
        },
    )
    participant = WorkspaceTransportErasureParticipant(db_session)
    outcome = await participant.erase_transport_owner(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    assert outcome.blocked is True
    assert outcome.block_reason == "purge_owner_unavailable"
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, WS_TRANSPORT)
    assert checkpoint["state"] == "blocked"


# ---------------------------------------------------------------------------
# external.payload.v1 / runtime.private.v1（registry monkeypatch + fake adapter）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _external_runtime_registry_enabled(monkeypatch):
    """external/runtime 临时翻 True（镜像 s4eb2/s4ec；生产保持 False 不变）。"""
    import app.composition.agent_erasure_registry as registry_module

    originals = registry_module._OWNER_DEFINITIONS

    def _enable(owner: OwnerDefinition) -> OwnerDefinition:
        if owner.owner_key in (EXTERNAL, RUNTIME):
            return OwnerDefinition(
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                capabilities=owner.capabilities,
                erase_available=True,
            )
        return owner

    enabled = tuple(_enable(o) for o in originals)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(registry_module, "_OWNERS_BY_KEY", {o.owner_key: o for o in enabled})
    yield


class _SuccessExternalAdapter(ExternalObjectAdapter):
    adapter_key = "fake-db-local"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = False

    def __init__(self) -> None:
        self.calls = 0

    async def delete_object(self, **kwargs):
        self.calls += 1
        return ExternalEraseSuccess(
            adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
        )

    async def receipt_lookup(self, **kwargs):
        return None


class _SuccessRuntimeAdapter(RuntimeSessionDestroyAdapter):
    adapter_key = "fake-runtime"
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


async def test_external_ack_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, EXTERNAL)
    adapter = _SuccessExternalAdapter()
    participant = ExternalPayloadErasureParticipant(db_session, adapter)
    # 成功路径返回 summary（无 blocked 字段；异常路径 raise 或 ledger blocked）。
    # 空 ref 集时 adapter 可能零调用（无可删对象仍合法 ACK）——调用计数判别力由
    # s4eb2 套件承担，本测试只守「零 operation/Conversation 投影写」。
    await participant.erase_external_payload(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, EXTERNAL)
    assert checkpoint["state"] == "acked"
    fence = await _read_fence(db_session, cid, EXTERNAL)
    assert fence["state"] == "erased"


async def test_runtime_ack_zero_shared_writes(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, RUNTIME)
    adapter = _SuccessRuntimeAdapter()
    participant = RuntimeErasureParticipant(db_session, adapter)
    # 成功路径返回 summary（无 blocked 字段；异常路径 raise 或 binding blocked）。
    # 空 binding 集时 adapter 可能零调用（无可销毁 session 仍合法 ACK）——调用
    # 计数判别力由 s4ec 套件承担，本测试只守「零 operation/Conversation 投影写」。
    await participant.erase_runtime_session(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    _assert_zero_shared_writes(
        await _read_operation(db_session, op_id),
        await _read_conversation_projection(db_session, cid),
        operation_id=op_id,
        cid=cid,
    )
    checkpoint = await _read_checkpoint(db_session, op_id, RUNTIME)
    assert checkpoint["state"] == "acked"
    fence = await _read_fence(db_session, cid, RUNTIME)
    assert fence["state"] == "erased"


# ---------------------------------------------------------------------------
# I2 冻结门禁（S5-A-4，回填自 S5-B-8 第 8 项）
# ---------------------------------------------------------------------------


async def test_stale_operation_purge_revision_gate_fail_closed(db_session):
    """旧 revision 拒绝门禁：Conversation.purge_revision 已推进而 operation 仍为
    旧 revision → participant entry fail closed（caller 参数与 operation 一致也
    不得放行——首锁内 Conversation 当前值裁决）。"""
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_CORE)
    # Conversation 推进到 purge_revision=2（operation 仍 1）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET purge_revision=2 "
            "WHERE id=:cid"
        ),
        {"cid": cid},
    )
    participant = WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    with pytest.raises(ValueError, match="stale operation revision rejected"):
        await participant.erase_conversation_body(
            tenant_id=tid,
            conversation_id=cid,
            purge_revision=1,  # 与 operation 一致（旧值）——仍须被门禁拒绝
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    await db_session.rollback()


async def test_workspace_core_erased_fence_cross_revision_gate_fail_closed(db_session):
    """workspace.core.v1 erased-fence 跨 purge 实例门禁（镜像 transport:746）：fence
    purge_revision 与请求不一致 → fail closed（跨实例 ack 摘要污染防护）。"""
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, WS_CORE)
    participant = WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    await participant.erase_conversation_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    # 第二 purge 实例（purge_revision=2）重放旧 erased fence → fail closed。
    with pytest.raises(ValueError, match="cross-purge-instance ACK repair rejected"):
        await participant.erase_conversation_body(
            tenant_id=tid,
            conversation_id=cid,
            purge_revision=2,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    await db_session.rollback()


async def test_execution_core_erased_fence_cross_revision_gate_fail_closed(db_session):
    """execution.core.v1 erased-fence 跨 purge 实例门禁（镜像 transport:746）。"""
    tid, cid = await _seed_conversation(db_session)
    op_id, _ = await _seed_operation_and_checkpoint(db_session, tid, cid, EX_CORE)
    participant = ExecutionErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )
    await participant.erase_execution_body(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=1,
    )
    with pytest.raises(ValueError, match="cross-purge-instance ACK repair rejected"):
        await participant.erase_execution_body(
            tenant_id=tid,
            conversation_id=cid,
            purge_revision=2,
            purge_operation_id=op_id,
            expected_operation_revision=1,
        )
    await db_session.rollback()
