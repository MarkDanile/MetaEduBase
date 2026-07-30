"""R1-S2 S2-D/E round-3：workspace.core.v1 正文清除 + final body scan + participant ACK。

Spec §3/§5.2/§6.1/§7.1/§9.2（plan §R1-S2「S2-D/E 契约注记」+「round-2/round-3 复审修订」）：

- purge 前置（P1-1）：仅 deleted + now>=purge_after + purged_at IS NULL 可擦除；
  **但已 erased fence 的幂等重放先于前置**（P1-4：purged_at 后不得在读 fence 前被拒绝）。
- HMAC actor digest（P1-2 / round-3 P1-4）：独立 ``actor_erasure_secret``（非
  jwt_secret）+ 版本契约（``actor_erasure_secret_version`` 混入 key 派生）、生产
  启动期 + 构造期强度校验（>= 32 字符）、tenant-scoped 派生 key、不可逆、可复现。
- ACK fencing（P1-3 / round-3 P1-2）：``purge_operation_id`` + ``expected_operation_revision``
  必填；ACK 绑定具体 operation--校验 conversation_id / purge_revision / lease_epoch /
  registry drift / hold_revision_snapshot / **operation revision CAS** + checkpoint
  owner_version / capability_digest CAS（owner_version 取自 fence，不硬编码）。
- erased fence 恢复（P1-4 / round-3 P1-3）：fence 已 erased 但 checkpoint 仍 pending
  -> 幂等重放修复 checkpoint 到 acked；**erased + 非零 scan = 正文泄漏 -> fail closed**；
  operation 必须处可修复状态（非 cancelled/failed/completed）。
- blocked 可靠提交 + 重试（P1-5 / round-3 P1-1）：scan 非零 -> blocked 正常返回提交；
  重试 blocked->erasing->erased，operation scheduled/blocked->running（清 failure_code
  + bump revision），重试 ACK 后 operation=running / checkpoint=acked / purge_state=running 一致。
- archived_by/deleted_by 清除（P1-3/P1-5）：直接主体标识全清，scan 含这两列。
- 时钟（P2-3 / round-3 P1-5）：``erase_conversation_body`` 不暴露 ``now`` 参数，始终用
  PostgreSQL ``clock_timestamp()``（非进程时钟）。
- reason code（P2-4）：legal hold 用 Spec §9.2 ``purge_blocked_by_legal_hold``。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    registry_digest,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import (
    ConversationNotPurgeableError,
    ConversationState,
    ErasureFenceState,
    LateBodyWriteRejectedError,
    PurgeOwnerState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ConversationUserStateModel,
    MessageModel,
    MessagePartModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.contexts.agent_workspace.infrastructure.repository import (
    AgentWorkspaceRepository,
)
from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
    ACTOR_ERASURE_SECRET_MIN_LENGTH,
    REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
    REASON_WORKSPACE_BODY_SCAN_NONZERO,
    WORKSPACE_CORE_OWNER,
    WorkspaceErasureParticipant,
    _actor_audit_digest,
    validate_production_actor_erasure_secret,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
)
from tests.contexts.agent_control_plane.test_writer_fence import _text_command

pytestmark = pytest.mark.asyncio

_OWNER = WORKSPACE_CORE_OWNER
_AUDIT_SECRET = "test-audit-secret"
_AUDIT_SECRET_VERSION = 1


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


async def _seed_active_with_body(db_session, *, title="sensitive title"):
    """建一个 active 会话（带 user_input Message + Part + UserState pin）。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title=title
    )
    conversation_id = view.conversation.id
    await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=_text_command("user body to erase"),
    )
    await service.set_pinned(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        pinned=True,
    )
    await db_session.commit()
    return conversation_id


async def _seed_deleted_expired_with_body(db_session, *, title="sensitive title"):
    """建会话 + 正文，再 soft_delete 并把 purge_after 设到过去（恢复窗口已过）。

    返回 (conversation_id, purge_revision)。delete 推进 purge_revision 0->1。
    """
    conversation_id = await _seed_active_with_body(db_session, title=title)
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv is not None
    expired = datetime.now(UTC) - timedelta(days=1)
    deleted_at = datetime.now(UTC) - timedelta(days=31)
    await AgentWorkspaceRepository(db_session).soft_delete_after_guard(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=conv.revision,
        purge_after=expired,
        deleted_at=deleted_at,
    )
    await db_session.commit()
    return conversation_id, 1


async def _make_purge_operation(
    db_session, conversation_id, purge_revision, *, hold_revision_snapshot=0
):
    """建 scheduled purge operation + pending workspace owner checkpoint。

    返回 (operation_id, operation_revision)。operation 的 registry_digest/
    lease_epoch/hold_revision_snapshot 与 create_purge_operation 默认对齐
    （lease_epoch=0、hold_revision_snapshot=参数、revision=1）。
    """
    repo = AgentErasureRepository(db_session)
    operation = await repo.create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=hold_revision_snapshot,
    )
    await repo.create_owner_checkpoint(
        tenant_id=TENANT_ID,
        purge_operation_id=operation.id,
        owner_key=_OWNER,
    )
    await db_session.commit()
    return operation.id, operation.revision


async def _seed_purgeable_with_operation(db_session, *, title="sensitive title"):
    """标准基线：deleted+expired 会话（带正文）+ scheduled operation + pending checkpoint。

    返回 (conversation_id, purge_revision, operation_id, operation_revision)。
    """
    conversation_id, purge_revision = await _seed_deleted_expired_with_body(
        db_session, title=title
    )
    operation_id, op_revision = await _make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    return conversation_id, purge_revision, operation_id, op_revision


def _participant(db_session) -> WorkspaceErasureParticipant:
    return WorkspaceErasureParticipant(
        db_session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )


async def _fence(db_session, conversation_id):
    return await AgentErasureRepository(db_session).get_fence_for_update(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER
    )


async def _checkpoint_model(db_session, operation_id) -> PurgeOwnerCheckpointModel:
    return (
        (
            await db_session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.purge_operation_id == operation_id,
                    PurgeOwnerCheckpointModel.owner_key == _OWNER,
                )
            )
        )
        .scalars()
        .one()
    )


async def _operation_model(db_session, operation_id) -> PurgeOperationModel:
    return (
        (
            await db_session.execute(
                select(PurgeOperationModel).where(
                    PurgeOperationModel.tenant_id == TENANT_ID,
                    PurgeOperationModel.id == operation_id,
                )
            )
        )
        .scalars()
        .one()
    )


async def _op_revision(db_session, operation_id) -> int:
    """读 operation 当前 revision（多轮 erase 调用间追踪用）。"""
    return (await _operation_model(db_session, operation_id)).revision


# ---------------------------------------------------------------------------
# P1-1：purge 前置 + round-3 P1-1 blocked 重试状态一致
# ---------------------------------------------------------------------------


async def test_p1_1_active_conversation_not_purgeable(db_session):
    """P1-1 反例：active 会话不得被直接擦除--执行器无条件强制 purge 前置。

    前置在 operation 加载前裁决，故不需真实 operation（dummy id 即可）。"""
    conversation_id = await _seed_active_with_body(db_session)
    with pytest.raises(ConversationNotPurgeableError, match="only deleted"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )
    await db_session.rollback()
    # 正文未被触动。
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"
    assert conv.state == ConversationState.ACTIVE.value


async def test_p1_1_not_yet_expired_not_purgeable(db_session):
    """P1-1 反例：已删除但恢复窗口未过（now < purge_after）不得擦除。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    # 把 purge_after 拉到未来，模拟未到期。
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.purge_after = datetime.now(UTC) + timedelta(days=10)
    await db_session.commit()

    with pytest.raises(ConversationNotPurgeableError, match="recovery window"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )
    await db_session.rollback()
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"  # 未清除


async def test_p1_1_already_purged_not_purgeable(db_session):
    """P1-1 反例：已 purged（purged_at 非空）且 fence 未 erased 不得重复擦除。

    fence 未 erased（freshly created active）-> 走前置 -> purged_at 拒绝。
    与 P1-4 erased-fence-replay-before-precondition 形成对照。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.purged_at = datetime.now(UTC)
    await db_session.commit()

    with pytest.raises(ConversationNotPurgeableError, match="already purged"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )


async def test_p1_1_round3_blocked_retry_state_consistent(db_session, monkeypatch):
    """round-3 P1-1：blocked 重试 ACK 后 operation=running（非 blocked）、
    failure_code=None，与 checkpoint=acked / conversation.purge_state=running 一致。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    # 第一次：scan 非零 -> blocked。
    participant1 = _participant(db_session)
    real_scan = participant1.scan_body

    async def _nonzero_scan(*, tenant_id, conversation_id):
        real = await real_scan(tenant_id=tenant_id, conversation_id=conversation_id)
        return type(real)(
            present_body_messages=real.present_body_messages + 1,
            message_parts=real.message_parts,
            user_states=real.user_states,
            unanonymized_actors=real.unanonymized_actors,
        )

    monkeypatch.setattr(participant1, "scan_body", _nonzero_scan)
    blocked = await participant1.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert blocked.blocked
    # blocked 后 operation=blocked + failure_code=scan_nonzero。
    op = await _operation_model(db_session, operation_id)
    assert op.state == "blocked"
    assert op.failure_code == REASON_WORKSPACE_BODY_SCAN_NONZERO
    op_revision_after = op.revision

    # 重试：scan 归零 -> ACK。expected_operation_revision = 当前 revision。
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert outcome.erased

    # round-3 P1-1：重试 ACK 后状态一致--operation=running + failure_code=None
    # （非 blocked），与 checkpoint=acked / conversation.purge_state=running 对齐。
    op = await _operation_model(db_session, operation_id)
    assert op.state == "running"
    assert op.failure_code is None
    cp = await _checkpoint_model(db_session, operation_id)
    assert cp.state == PurgeOwnerState.ACKED.value
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state == "running"


# ---------------------------------------------------------------------------
# P1-2：HMAC actor digest + 版本契约 + 强度校验
# ---------------------------------------------------------------------------


async def test_p1_2_actor_digest_is_hmac_not_plain_sha256():
    """P1-2：digest 必须是 HMAC-SHA256（tenant-scoped key），不是普通 SHA-256。"""
    tenant = uuid.UUID("71000000-0000-0000-0000-000000000001")
    actor = uuid.UUID("71000000-0000-0000-0000-000000000002")
    digest = _actor_audit_digest(
        secret=_AUDIT_SECRET,
        secret_version=_AUDIT_SECRET_VERSION,
        tenant_id=tenant,
        actor_id=actor,
    )
    assert len(digest) == 64  # SHA-256 hex
    plain = hashlib.sha256(tenant.bytes + actor.bytes).hexdigest()
    assert digest != plain
    assert digest == _actor_audit_digest(
        secret=_AUDIT_SECRET,
        secret_version=_AUDIT_SECRET_VERSION,
        tenant_id=tenant,
        actor_id=actor,
    )


async def test_p1_2_actor_digest_is_tenant_scoped():
    """P1-2：不同 tenant / 不同 secret / 不同 version 产生不同 digest。"""
    actor = uuid.UUID("71000000-0000-0000-0000-000000000002")
    t1 = uuid.UUID("71000000-0000-0000-0000-000000000001")
    t2 = uuid.UUID("72000000-0000-0000-0000-000000000001")
    d1 = _actor_audit_digest(
        secret=_AUDIT_SECRET, secret_version=1, tenant_id=t1, actor_id=actor
    )
    d2 = _actor_audit_digest(
        secret=_AUDIT_SECRET, secret_version=1, tenant_id=t2, actor_id=actor
    )
    assert d1 != d2  # tenant-scoped
    d3 = _actor_audit_digest(
        secret="other-secret", secret_version=1, tenant_id=t1, actor_id=actor
    )
    assert d1 != d3  # 密钥隔离


async def test_p1_2_round3_secret_version_in_digest():
    """round-3 P1-4：digest 派生混入 secret_version--不同版本产生不同 digest
    （轮换防跨版本碰撞），同版本可复现。"""
    tenant = uuid.UUID("71000000-0000-0000-0000-000000000001")
    actor = uuid.UUID("71000000-0000-0000-0000-000000000002")
    d1 = _actor_audit_digest(
        secret=_AUDIT_SECRET, secret_version=1, tenant_id=tenant, actor_id=actor
    )
    d2 = _actor_audit_digest(
        secret=_AUDIT_SECRET, secret_version=2, tenant_id=tenant, actor_id=actor
    )
    assert d1 != d2  # 版本不同 -> digest 不同
    assert d1 == _actor_audit_digest(
        secret=_AUDIT_SECRET, secret_version=1, tenant_id=tenant, actor_id=actor
    )


async def test_p1_2_erase_produces_hmac_digest(db_session):
    """P1-2：erase 落库的 creator_identity_digest 必须等于 HMAC 派生值，
    不等于普通 SHA-256。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    conv = await db_session.get(ConversationModel, conversation_id)
    expected = _actor_audit_digest(
        secret=_AUDIT_SECRET,
        secret_version=_AUDIT_SECRET_VERSION,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )
    assert conv.creator_identity_digest == expected
    plain = hashlib.sha256(TENANT_ID.bytes + ACTOR_ID.bytes).hexdigest()
    assert conv.creator_identity_digest != plain


async def test_p1_2_constructor_uses_actor_erasure_secret_not_jwt(
    db_session, monkeypatch
):
    """P1-2：构造默认用 ``settings.actor_erasure_secret`` + version（非 jwt_secret）
    --密钥用途隔离：JWT 轮换不得改变审计身份摘要。"""
    from app.config import settings

    monkeypatch.setattr(settings, "actor_erasure_secret", "configured-actor-secret")
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 3)
    monkeypatch.setattr(settings, "jwt_secret", "a-different-jwt-secret")
    participant = WorkspaceErasureParticipant(db_session)  # 不传 audit_secret
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    conv = await db_session.get(ConversationModel, conversation_id)
    expected = _actor_audit_digest(
        secret="configured-actor-secret", secret_version=3,
        tenant_id=TENANT_ID, actor_id=ACTOR_ID,
    )
    assert conv.creator_identity_digest == expected
    # 与 jwt_secret 派生的 digest 不同（密钥隔离）。
    jwt_digest = _actor_audit_digest(
        secret="a-different-jwt-secret", secret_version=3,
        tenant_id=TENANT_ID, actor_id=ACTOR_ID,
    )
    assert conv.creator_identity_digest != jwt_digest


async def test_p1_2_round3_production_strength_validation(db_session, monkeypatch):
    """round-3 P1-4：生产环境构造期强度校验--空 / 弱（< 32 字符）-> fail fast；
    >= 32 字符通过。"""
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    # 空 -> fail。
    monkeypatch.setattr(settings, "actor_erasure_secret", "")
    with pytest.raises(RuntimeError, match="high-entropy"):
        WorkspaceErasureParticipant(db_session)
    # 弱（< 32）-> fail。
    monkeypatch.setattr(settings, "actor_erasure_secret", "short")
    with pytest.raises(RuntimeError, match="high-entropy"):
        WorkspaceErasureParticipant(db_session)
    # 强（>= 32）-> 通过。
    monkeypatch.setattr(settings, "actor_erasure_secret", "x" * ACTOR_ERASURE_SECRET_MIN_LENGTH)
    WorkspaceErasureParticipant(db_session)  # 不抛


async def test_p1_2_round3_startup_validation_contract(monkeypatch):
    """round-3 P1-4 / round-4 P1-4：启动期 ``validate_production_actor_erasure_secret``
    强度校验 + 版本冻结契约（development 不校验；production 空/弱/版本!=1 fail）。"""
    from app.config import settings

    # development -> 不校验（空也通过）。
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "actor_erasure_secret", "")
    validate_production_actor_erasure_secret(settings)  # 不抛

    # production + 空 -> fail。
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="ACTOR_ERASURE_SECRET"):
        validate_production_actor_erasure_secret(settings)
    # production + 弱 -> fail。
    monkeypatch.setattr(settings, "actor_erasure_secret", "short")
    with pytest.raises(RuntimeError, match="不少于 32"):
        validate_production_actor_erasure_secret(settings)
    # round-4 P1-4：production + 强但 version != 1（冻结）-> fail。
    monkeypatch.setattr(settings, "actor_erasure_secret", "x" * ACTOR_ERASURE_SECRET_MIN_LENGTH)
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 2)
    with pytest.raises(RuntimeError, match="必须为 1"):
        validate_production_actor_erasure_secret(settings)
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 0)
    with pytest.raises(RuntimeError, match="必须为 1"):
        validate_production_actor_erasure_secret(settings)
    # production + 强 + version=1（冻结 V1）-> 通过。
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 1)
    validate_production_actor_erasure_secret(settings)  # 不抛


async def test_p1_2_round4_production_version_frozen_at_1(db_session, monkeypatch):
    """round-4 P1-4：生产环境 actor_erasure_secret_version 冻结 V1--version != 1
    -> 构造期 fail fast（digest version 未持久化，轮换会孤儿化历史 digest）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "actor_erasure_secret", "x" * ACTOR_ERASURE_SECRET_MIN_LENGTH)
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 2)
    with pytest.raises(RuntimeError, match="must be 1 in production"):
        WorkspaceErasureParticipant(db_session)
    # version=1 -> 通过。
    monkeypatch.setattr(settings, "actor_erasure_secret_version", 1)
    WorkspaceErasureParticipant(db_session)  # 不抛


# ---------------------------------------------------------------------------
# P1-3：archived_by / deleted_by 清除 + operation/checkpoint fencing 表驱动反例
# ---------------------------------------------------------------------------


async def test_p1_3_archived_by_deleted_by_cleared(db_session):
    """P1-3：清除后 archived_by/deleted_by（直接主体标识）必须为 NULL。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.archived_by = ACTOR_ID  # deleted_by 已由 soft_delete 设置
    await db_session.commit()
    assert conv.deleted_by is not None
    assert conv.archived_by is not None

    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.created_by is None
    assert conv.archived_by is None
    assert conv.deleted_by is None
    assert conv.actor_state == "redacted"


@pytest.mark.parametrize(
    "scenario, expected_match",
    [
        # operation 身份反例：跨 Conversation operation 不得误 ACK。
        ("cross_conversation", "cross-conversation ACK rejected"),
        # operation fencing token 反例。
        ("purge_revision_mismatch", "purge_revision mismatch"),
        ("stale_lease_epoch", "lease_epoch mismatch"),
        ("hold_revision_drift", "hold_revision drift"),
        # round-3 P1-2：operation revision CAS（replay fencing）。
        ("stale_operation_revision", "operation revision mismatch"),
        # checkpoint owner capability CAS 反例（ACK 路径裁决）。
        ("checkpoint_owner_version", "checkpoint owner_version"),
        ("checkpoint_capability_digest", "checkpoint capability_digest"),
    ],
)
async def test_p1_3_operation_fencing_counterexamples(
    db_session, scenario, expected_match
):
    """P1-3 / round-3 P1-2 表驱动反例：operation 身份 / lease / hold / revision /
    owner capability 任一不符 -> fail closed（ValueError），不基于过期或跨域 operation ACK。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    call_kwargs = {
        "purge_revision": purge_revision,
        "expected_lease_epoch": 0,
        "expected_operation_revision": op_revision,
    }

    if scenario == "cross_conversation":
        other_conv_id, other_rev = await _seed_deleted_expired_with_body(
            db_session, title="other conv"
        )
        operation_id, other_op_rev = await _make_purge_operation(
            db_session, other_conv_id, other_rev
        )
        call_kwargs["purge_revision"] = other_rev
        call_kwargs["expected_operation_revision"] = other_op_rev
    elif scenario == "purge_revision_mismatch":
        call_kwargs["purge_revision"] = 999
    elif scenario == "stale_lease_epoch":
        call_kwargs["expected_lease_epoch"] = 5
    elif scenario == "hold_revision_drift":
        conv = await db_session.get(ConversationModel, conversation_id)
        conv.hold_revision = 1
        await db_session.commit()
    elif scenario == "stale_operation_revision":
        # 调用方观测的 revision 过期（operation 被并发 bump）。
        call_kwargs["expected_operation_revision"] = op_revision + 5
    elif scenario == "checkpoint_owner_version":
        cp = await _checkpoint_model(db_session, operation_id)
        cp.owner_version = 2  # fence owner_version=1
        await db_session.commit()
    elif scenario == "checkpoint_capability_digest":
        cp = await _checkpoint_model(db_session, operation_id)
        cp.capability_digest = "0" * 64
        await db_session.commit()

    with pytest.raises(ValueError, match=expected_match):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_operation_id=operation_id,
            **call_kwargs,
        )


# ---------------------------------------------------------------------------
# P1-4：ACK 绑定 operation/checkpoint CAS + erased fence 恢复 + round-3 P1-3
# ---------------------------------------------------------------------------


async def test_p1_4_ack_binds_to_operation_checkpoint_cas(db_session):
    """P1-4：ACK 绑定具体 operation_id + owner checkpoint CAS，ack_digest/
    checkpoint_digest 落库且与 fence ack_digest 同源；operation=running。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert outcome.erased

    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    assert checkpoint.ack_digest == outcome.ack_digest
    assert checkpoint.checkpoint_digest is not None
    assert checkpoint.checkpoint_digest != checkpoint.ack_digest
    operation = await _operation_model(db_session, operation_id)
    assert operation.state == "running"
    assert operation.failure_code is None


async def test_p1_4_ack_registry_drift_fail_closed(db_session, monkeypatch):
    """P1-4 反例：operation registry_digest 与已安装 registry 不匹配（drift）
    -> ACK fail closed（OwnerRegistryChangedError）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    monkeypatch.setattr(
        "app.contexts.agent_workspace.infrastructure.workspace_erasure_participant."
        "registry_digest",
        lambda: "0" * 64,
    )
    with pytest.raises(OwnerRegistryChangedError):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision,
        )
    assert registry_digest() != "0" * 64  # monkeypatch 已还原


async def test_p1_4_erased_fence_repairs_pending_checkpoint(db_session):
    """P1-4：fence 已 erased 但 checkpoint 仍 pending（ACK 丢失/历史不一致）->
    幂等重放先于 purge 前置（purged_at 不得阻断恢复），修复 checkpoint 到 acked、
    operation 修复到 running。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert first.erased
    fence_ack_digest = first.fence.ack_digest
    op_revision_after = await _op_revision(db_session, operation_id)

    # 模拟 ACK 丢失：fence 保持 erased，checkpoint 回退 pending、operation 回退
    # scheduled；并设 purged_at--证明恢复先于前置。
    cp = await _checkpoint_model(db_session, operation_id)
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    op = await _operation_model(db_session, operation_id)
    op.state = "scheduled"
    op.failure_code = "stale"
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.purged_at = datetime.now(UTC)
    await db_session.commit()

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.ack_digest == fence_ack_digest

    cp = await _checkpoint_model(db_session, operation_id)
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack_digest
    op = await _operation_model(db_session, operation_id)
    assert op.state == "running"  # scheduled -> running 修复
    assert op.failure_code is None


async def test_p1_4_round3_erased_fence_nonzero_scan_fail_closed(db_session):
    """round-3 P1-3：erased fence + 非零 scan（正文泄漏/绕过 fence 回写）-> fail
    closed，不在泄漏正文上补 ACK。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert first.erased
    op_revision_after = await _op_revision(db_session, operation_id)

    # 注入残留 present 正文（模拟 body 泄漏）。
    residual = MessageModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        seq=99,
        message_kind="system_notice",
        author_type="system",
        author_id=None,
        content_state="visible",
        content_digest="0" * 64,
        body_state="present",
        created_at=datetime.now(UTC),
    )
    db_session.add(residual)
    await db_session.commit()

    with pytest.raises(ValueError, match="body scan non-zero"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision_after,
        )


async def test_p1_4_round3_erased_repair_terminal_operation_fail_closed(db_session):
    """round-3 P1-3：erased fence 重放时 operation 已处终态（cancelled）-> fail
    closed，不在已取消 operation 上补 ACK。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert first.erased
    op_revision_after = await _op_revision(db_session, operation_id)

    # 模拟 operation 被并发取消（restore 场景），revision 也 bump。
    op = await _operation_model(db_session, operation_id)
    op.state = "cancelled"
    op.revision = op_revision_after + 1
    await db_session.commit()

    with pytest.raises(ValueError, match="not repairable from terminal state"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision_after + 1,
        )


# ---------------------------------------------------------------------------
# P1-5：blocked 可靠提交 + 重试 + legal hold
# ---------------------------------------------------------------------------


async def test_p1_5_blocked_state_is_committed_not_rolled_back(
    db_session, monkeypatch
):
    """P1-5：scan 非零时 blocked 作为正常返回提交（不抛异常致回滚）。blocked 状态
    + scan digest 持久化（P2-2），可重试。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    real_scan = participant.scan_body

    async def _nonzero_scan(*, tenant_id, conversation_id):
        real = await real_scan(tenant_id=tenant_id, conversation_id=conversation_id)
        return type(real)(
            present_body_messages=real.present_body_messages + 1,
            message_parts=real.message_parts,
            user_states=real.user_states,
            unanonymized_actors=real.unanonymized_actors,
        )

    monkeypatch.setattr(participant, "scan_body", _nonzero_scan)
    outcome = await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_WORKSPACE_BODY_SCAN_NONZERO
    assert not outcome.erased
    assert outcome.ack_digest is None

    fence = await _fence(db_session, conversation_id)
    assert fence.state is ErasureFenceState.BLOCKED
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.BLOCKED.value
    assert checkpoint.reason_code == REASON_WORKSPACE_BODY_SCAN_NONZERO
    assert checkpoint.checkpoint_digest is not None  # P2-2
    op = await _operation_model(db_session, operation_id)
    assert op.state == "blocked"
    assert op.failure_code == REASON_WORKSPACE_BODY_SCAN_NONZERO
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state == "blocked"


async def test_p1_5_retry_after_blocked_acks(db_session, monkeypatch):
    """P1-5 重试：首次 scan 非零 -> blocked（commit）；重试 scan 归零 -> ACK。
    清除幂等（已 redacted 不重复处理）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant1 = _participant(db_session)
    real_scan = participant1.scan_body

    async def _nonzero_scan(*, tenant_id, conversation_id):
        real = await real_scan(tenant_id=tenant_id, conversation_id=conversation_id)
        return type(real)(
            present_body_messages=real.present_body_messages + 1,
            message_parts=real.message_parts,
            user_states=real.user_states,
            unanonymized_actors=real.unanonymized_actors,
        )

    monkeypatch.setattr(participant1, "scan_body", _nonzero_scan)
    blocked = await participant1.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert blocked.blocked
    op_revision_after = await _op_revision(db_session, operation_id)

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.ack_digest is not None

    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    assert checkpoint.ack_digest == outcome.ack_digest


async def test_p1_5_legal_hold_blocks_as_normal_return(db_session):
    """P1-5：active legal hold -> blocked 正常返回（不抛异常），不清除正文，
    fence 保持 active，operation/checkpoint 记 blocked（P2-4 reason code）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    assert not outcome.erased
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"
    fence = await _fence(db_session, conversation_id)
    assert fence.state is ErasureFenceState.ACTIVE
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.BLOCKED.value
    assert checkpoint.reason_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD


# ---------------------------------------------------------------------------
# P1-5：scan 完整性 + 已 redacted author_id 残留清除
# ---------------------------------------------------------------------------


async def test_p1_5_scan_counts_archived_by_deleted_by(db_session):
    """P1-5：body scan 必须计入 archived_by/deleted_by（直接主体标识）。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.archived_by = ACTOR_ID  # deleted_by 已由 soft_delete 设置
    await db_session.commit()
    scan = await _participant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    # actor_state=present(+1) + archived_by(+1) + deleted_by(+1) + message author(+1) = 4。
    assert scan.unanonymized_actors == 4


async def test_p1_5_redacts_author_id_on_already_redacted_messages(db_session):
    """P1-5：已 redacted 但仍带 author_id 的 assistant_output Message 也必须被清除
    author_id，否则 scan 永久非零、blocked 无法自愈重试。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    residual_msg = MessageModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        seq=2,
        message_kind="assistant_output",
        author_type="agent",
        author_id=ACTOR_ID,  # 残留 agent author
        content_state="redacted",
        content_digest="b" * 64,
        body_state="redacted",
        origin_run_id=uuid.uuid4(),
        output_ordinal=0,
        created_at=datetime.now(UTC),
    )
    db_session.add(residual_msg)
    await db_session.commit()

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.body_scan.total == 0
    msg = (
        (
            await db_session.execute(
                select(MessageModel).where(MessageModel.id == residual_msg.id)
            )
        )
        .scalars()
        .one()
    )
    assert msg.author_id is None
    # round-4 P1-5：agent author 的 actor_identity_digest 必须保留（不可逆丢失审计身份）。
    assert msg.actor_identity_digest is not None
    assert len(msg.actor_identity_digest) == 64
    assert msg.actor_identity_digest == _actor_audit_digest(
        secret=_AUDIT_SECRET,
        secret_version=_AUDIT_SECRET_VERSION,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
    )


# ---------------------------------------------------------------------------
# P2-1 / P2-3：scan tenant 谓词 + 始终用 DB 时钟
# ---------------------------------------------------------------------------


async def test_p2_1_scan_body_tenant_scoped(db_session):
    """P2-1：scan_body 的 Conversation 查询带 tenant_id 谓词--跨 tenant 不得
    误报另一 tenant 会话的 actor 残留。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    other_tenant = uuid.uuid4()
    scan = await _participant(db_session).scan_body(
        tenant_id=other_tenant, conversation_id=conversation_id
    )
    assert scan.unanonymized_actors == 0
    assert scan.present_body_messages == 0


async def test_p2_3_always_uses_database_clock(db_session, monkeypatch):
    """round-3 P1-5 / P2-3：``erase_conversation_body`` 不暴露 ``now`` 参数，始终
    用 PostgreSQL ``clock_timestamp()``（非进程时钟）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    called = []
    real = participant._database_now

    async def _spy():
        called.append(True)
        return await real()

    monkeypatch.setattr(participant, "_database_now", _spy)
    outcome = await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert outcome.erased
    assert called  # 走了 DB 时钟路径


async def test_p2_3_round3_now_param_not_accepted(db_session):
    """round-3 P1-5：``erase_conversation_body`` 不接受 ``now`` 关键字参数--
    防调用方绕过 DB 时钟传进程时钟。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    with pytest.raises(TypeError, match="unexpected keyword argument 'now'"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision,
            now=datetime.now(UTC),  # 不应被接受
        )


async def test_p1_3_round3_record_blocked_uses_fence_owner_version(db_session):
    """round-3 P1-6：blocked 路径 ``_record_blocked`` 用 ``fence.owner_version``
    （非硬编码 1）--fence + checkpoint owner_version 同步为 2 时仍能匹配，硬编码 1
    会误判 mismatch。"""
    from app.contexts.agent_workspace.infrastructure.models import ErasureFenceModel

    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    # 把 fence + checkpoint 的 owner_version 同步改 2（一致），模拟未来 owner
    # version bump 场景。legal-hold 路径不 transition fence（不触发
    # require_owner_version），可直接验证 _record_blocked 用 fence.owner_version。
    fence_model = (
        await db_session.execute(
            select(ErasureFenceModel).where(
                ErasureFenceModel.tenant_id == TENANT_ID,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == _OWNER,
            )
        )
    ).scalar_one()
    fence_model.owner_version = 2
    cp = await _checkpoint_model(db_session, operation_id)
    cp.owner_version = 2
    await db_session.commit()

    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    # 用 fence.owner_version=2 匹配 checkpoint.owner_version=2 -> blocked 成功
    # （硬编码 1 会 raise "checkpoint owner_version 2 != fence 1"）。
    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.BLOCKED.value


# ---------------------------------------------------------------------------
# round-4：legal-hold revision CAS / 投影一致 / erased repair 矛盾事实
# ---------------------------------------------------------------------------


async def test_p1_1_round4_legal_hold_stale_revision_fail_closed(db_session):
    """round-4 P1-1：legal-hold 路径也裁决 operation revision CAS--stale caller
    （revision 过期）不得改状态，零状态变更 fail closed。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()
    # 调用方观测的 revision 过期（operation 被并发 bump）。
    with pytest.raises(ValueError, match="operation revision mismatch"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision + 5,
        )
    await db_session.rollback()
    # 零状态变更：operation/checkpoint 仍是初始 scheduled/pending，未被改成 blocked。
    op = await _operation_model(db_session, operation_id)
    assert op.state == "scheduled"
    assert op.failure_code is None
    cp = await _checkpoint_model(db_session, operation_id)
    assert cp.state == PurgeOwnerState.PENDING.value
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state != "blocked"


async def test_p1_2_round4_legal_hold_projects_purge_state_blocked(db_session):
    """round-4 P1-2：legal-hold blocked 路径把 Conversation.purge_state 投影为
    blocked（与 operation/checkpoint 同事务一致，Spec §5.2）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert outcome.blocked
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state == "blocked"  # P1-2 投影一致
    op = await _operation_model(db_session, operation_id)
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD


async def test_p1_2_round4_record_blocked_reason_change_bumps_revision(
    db_session, monkeypatch
):
    """round-4 P1-2：已 blocked operation 遇新 reason（scan_nonzero -> legal_hold）
    更新 failure_code + bump revision（不保留旧 reason）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    # 第一次：scan 非零 -> blocked (reason=scan_nonzero)。
    participant1 = _participant(db_session)
    real_scan = participant1.scan_body

    async def _nonzero_scan(*, tenant_id, conversation_id):
        real = await real_scan(tenant_id=tenant_id, conversation_id=conversation_id)
        return type(real)(
            present_body_messages=real.present_body_messages + 1,
            message_parts=real.message_parts,
            user_states=real.user_states,
            unanonymized_actors=real.unanonymized_actors,
        )

    monkeypatch.setattr(participant1, "scan_body", _nonzero_scan)
    await participant1.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    op = await _operation_model(db_session, operation_id)
    assert op.failure_code == REASON_WORKSPACE_BODY_SCAN_NONZERO
    op_revision_after = op.revision

    # 重试时 scan 归零（清除 monkeypatch）但加 legal hold -> legal-hold 路径把
    # reason 从 scan_nonzero 改成 legal_hold。
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    op = await _operation_model(db_session, operation_id)
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD  # reason 更新
    assert op.revision == op_revision_after + 1  # bump（state 已 blocked，仅 reason 变）


async def test_p1_3_round4_erased_repair_acked_digest_mismatch_fail_closed(db_session):
    """round-4 P1-3：erased 重放时 checkpoint 已 acked 但 ack_digest 与 fence 不一致
    （矛盾事实）-> fail closed，不接受孤立 ACK。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert first.erased
    op_revision_after = await _op_revision(db_session, operation_id)
    # 篡改 checkpoint.ack_digest（模拟矛盾事实--与 fence.ack_digest 不一致）。
    cp = await _checkpoint_model(db_session, operation_id)
    cp.ack_digest = "0" * 64
    await db_session.commit()
    with pytest.raises(ValueError, match="contradictory ACK fact"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision_after,
        )


async def test_p1_3_round4_erased_repair_blocked_operation_to_running(db_session):
    """round-4 P1-3：erased 重放时 operation 卡 blocked + purge_state=blocked ->
    修复到 running（不只清 failure_code），Conversation.purge_state 也修复到
    running，三方一致（fence=erased / checkpoint=acked / operation=running）。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    assert first.erased
    fence_ack_digest = first.fence.ack_digest
    op_revision_after = await _op_revision(db_session, operation_id)
    # 模拟矛盾：fence erased 但 operation=blocked + purge_state=blocked。
    op = await _operation_model(db_session, operation_id)
    op.state = "blocked"
    op.failure_code = "stale"
    op.revision = op_revision_after + 1  # 并发 bump
    cp = await _checkpoint_model(db_session, operation_id)
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.purge_state = "blocked"
    await db_session.commit()

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after + 1,
    )
    await db_session.commit()
    assert outcome.erased
    # operation 修复到 running（非 blocked），failure_code 清除。
    op = await _operation_model(db_session, operation_id)
    assert op.state == "running"
    assert op.failure_code is None
    # conversation.purge_state 修复到 running（三方一致）。
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state == "running"
    cp = await _checkpoint_model(db_session, operation_id)
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack_digest


# ---------------------------------------------------------------------------
# S2-D 主路径：清除 + envelope 保留 + scan 零 + ACK
# ---------------------------------------------------------------------------


async def test_erase_clears_title_message_parts_userstate_actor(db_session):
    """S2-D 主路径：清除后 title/正文/Part/UserState/actor 全清，envelope 保留，
    body scan 为零，fence 推进 erased 且带 ack_digest。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    assert outcome.erased
    fence = outcome.fence
    assert fence.state is ErasureFenceState.ERASED
    assert fence.ack_digest is not None and len(fence.ack_digest) == 64
    assert outcome.ack_digest == fence.ack_digest

    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title is None
    assert conv.title_source == "none"
    assert conv.actor_state == "redacted"
    assert conv.created_by is None
    assert conv.creator_identity_digest is not None
    assert len(conv.creator_identity_digest) == 64
    assert conv.id == conversation_id  # envelope 保留

    messages = (
        (
            await db_session.execute(
                select(MessageModel).where(
                    MessageModel.conversation_id == conversation_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    message = messages[0]
    assert message.body_state == "redacted"
    assert message.content_state == "redacted"
    assert message.author_id is None
    assert message.actor_identity_digest is not None
    assert len(message.actor_identity_digest) == 64
    assert message.redacted_reason == "retention_expired"
    assert message.seq == 1  # envelope 保留，seq 不改写
    assert len(message.content_digest) == 64

    parts = await db_session.scalar(
        select(func.count())
        .select_from(MessagePartModel)
        .where(MessagePartModel.message_id == message.id)
    )
    assert parts == 0
    user_states = await db_session.scalar(
        select(func.count())
        .select_from(ConversationUserStateModel)
        .where(ConversationUserStateModel.conversation_id == conversation_id)
    )
    assert user_states == 0
    scan = await _participant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.total == 0


async def test_body_scan_reports_residual_before_erase(db_session):
    """body scan 在清除前正确报出残留正文（非恒零摆设）。"""
    conversation_id = await _seed_active_with_body(db_session)
    scan = await _participant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.present_body_messages == 1
    assert scan.message_parts == 1
    assert scan.user_states == 1
    assert scan.unanonymized_actors == 2  # conversation actor + message author
    assert scan.total == 5


# ---------------------------------------------------------------------------
# 幂等 / fail-closed / writer 被拒
# ---------------------------------------------------------------------------


async def test_erase_is_idempotent_replay(db_session):
    """可重入：已 erased 后再次执行清除是幂等 no-op，ack_digest 不变；
    checkpoint 已 acked -> repair no-op。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    first = await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()
    op_revision_after = await _op_revision(db_session, operation_id)

    second = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert second.erased
    assert second.fence.ack_digest == first.fence.ack_digest
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    scan = await _participant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.total == 0


async def test_unknown_conversation_fail_closed(db_session):
    """未知 conversation_id -> fail closed（不创建孤儿 fence、不清除）。"""
    with pytest.raises(ValueError, match="not found"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=uuid.uuid4(),
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )


async def test_cross_tenant_fail_closed(db_session):
    """跨 tenant：正确 tenant 的会话对另一 tenant 不可见，清除 fail closed。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    other_tenant = uuid.uuid4()
    with pytest.raises(ValueError, match="not found"):
        await _participant(db_session).erase_conversation_body(
            tenant_id=other_tenant,
            conversation_id=conversation_id,
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"


async def test_writer_rejected_while_erasing(db_session):
    """清除推进 fence 离开 active 后，正文 writer 经 fence 裁决被拒
    （LateBodyWriteRejectedError），清除期间不得有新正文复活。"""
    from app.composition.agent_erasure_locks import acquire_owner_lock

    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    await acquire_owner_lock(
        db_session,
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        owner_key=_OWNER,
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await AgentErasureRepository(
            db_session
        ).require_body_write_fence_for_update(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            owner_key=_OWNER,
        )


async def test_body_scan_detects_residual(db_session):
    """body scan 检测残留 present 正文（不恒零）：清除后注入残留 -> scan 非零。"""
    conversation_id, purge_revision, operation_id, op_revision = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        expected_operation_revision=op_revision,
    )
    await db_session.commit()

    residual = MessageModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        seq=99,
        message_kind="system_notice",
        author_type="system",
        author_id=None,
        content_state="visible",
        content_digest="0" * 64,
        body_state="present",
        created_at=datetime.now(UTC),
    )
    db_session.add(residual)
    await db_session.flush()
    scan = await _participant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.present_body_messages == 1
    assert scan.total != 0
    await db_session.rollback()
