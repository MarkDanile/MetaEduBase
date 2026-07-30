"""R1-S2 S2-D/E round-2：workspace.core.v1 正文清除 + final body scan + participant ACK。

Spec §3/§5.2/§6.1/§7.1/§9.2（plan §R1-S2「S2-D/E 契约注记」+「S2-D/E 复审修订」）：

- purge 前置（P1-1）：仅 deleted + now>=purge_after + purged_at IS NULL 可擦除；
  **但已 erased fence 的幂等重放先于前置**（P1-4：purged_at 后不得在读 fence 前被拒绝）。
- HMAC actor digest（P1-2）：独立 ``actor_erasure_secret``（非 jwt_secret）、
  tenant-scoped 派生 key、不可逆、可复现。
- ACK fencing（P1-3）：``purge_operation_id`` 必填；ACK 绑定具体 operation--
  校验 conversation_id / purge_revision / lease_epoch / registry drift /
  hold_revision_snapshot + checkpoint owner_version / capability_digest CAS。
  同 tenant 同 revision 跨 Conversation operation 不得误 ACK。
- erased fence 恢复（P1-4）：fence 已 erased 但 checkpoint 仍 pending（ACK 丢失）->
  幂等重放修复 checkpoint 到 acked（用 fence.ack_digest）。
- blocked 可靠提交 + 重试（P1-5）：scan 非零 -> blocked 正常返回提交（不抛异常）；
  重试 blocked->erasing->erased，清除幂等（处理所有 author_id 残留）。
- archived_by/deleted_by 清除（P1-3/P1-5）：直接主体标识全清，scan 含这两列。
- 时钟（P2-3）：省略 ``now`` 时用 PostgreSQL ``clock_timestamp()``（非进程时钟）。
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
    REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
    REASON_WORKSPACE_BODY_SCAN_NONZERO,
    WORKSPACE_CORE_OWNER,
    WorkspaceErasureParticipant,
    _actor_audit_digest,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
)
from tests.contexts.agent_control_plane.test_writer_fence import _text_command

pytestmark = pytest.mark.asyncio

_OWNER = WORKSPACE_CORE_OWNER
_AUDIT_SECRET = "test-audit-secret"


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

    返回 operation_id。operation 的 registry_digest/lease_epoch/hold_revision_snapshot
    与 create_purge_operation 默认对齐（lease_epoch=0、hold_revision_snapshot=参数）。
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
    return operation.id


async def _seed_purgeable_with_operation(db_session, *, title="sensitive title"):
    """标准基线：deleted+expired 会话（带正文）+ scheduled operation + pending checkpoint。

    返回 (conversation_id, purge_revision, operation_id)。
    """
    conversation_id, purge_revision = await _seed_deleted_expired_with_body(
        db_session, title=title
    )
    operation_id = await _make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    return conversation_id, purge_revision, operation_id


def _participant(db_session) -> WorkspaceErasureParticipant:
    return WorkspaceErasureParticipant(db_session, audit_secret=_AUDIT_SECRET)


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


# ---------------------------------------------------------------------------
# P1-1：purge 前置（state=deleted + now>=purge_after + purged_at IS NULL）
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
            now=datetime.now(UTC),
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
            now=datetime.now(UTC),
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
            now=datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# P1-2：HMAC actor audit digest（独立 secret + tenant-scoped，非普通 SHA-256）
# ---------------------------------------------------------------------------


async def test_p1_2_actor_digest_is_hmac_not_plain_sha256():
    """P1-2：digest 必须是 HMAC-SHA256（tenant-scoped key），不是普通 SHA-256。

    普通 SHA-256(tenant||actor) 不满足不可逆 HMAC 契约；HMAC 用派生的
    tenant-scoped key，与普通 hash 产生不同结果。
    """
    tenant = uuid.UUID("71000000-0000-0000-0000-000000000001")
    actor = uuid.UUID("71000000-0000-0000-0000-000000000002")
    digest = _actor_audit_digest(
        secret=_AUDIT_SECRET, tenant_id=tenant, actor_id=actor
    )
    assert len(digest) == 64  # SHA-256 hex
    # 与普通 SHA-256(tenant||actor) 不同（证明用了 HMAC + 派生 key）。
    plain = hashlib.sha256(tenant.bytes + actor.bytes).hexdigest()
    assert digest != plain
    # 可复现。
    assert digest == _actor_audit_digest(
        secret=_AUDIT_SECRET, tenant_id=tenant, actor_id=actor
    )


async def test_p1_2_actor_digest_is_tenant_scoped():
    """P1-2：不同 tenant 同一 actor 产生不同 digest（tenant-scoped）；不同 secret
    产生不同 digest（密钥隔离--与 jwt_secret 解耦）。"""
    actor = uuid.UUID("71000000-0000-0000-0000-000000000002")
    t1 = uuid.UUID("71000000-0000-0000-0000-000000000001")
    t2 = uuid.UUID("72000000-0000-0000-0000-000000000001")
    d1 = _actor_audit_digest(secret=_AUDIT_SECRET, tenant_id=t1, actor_id=actor)
    d2 = _actor_audit_digest(secret=_AUDIT_SECRET, tenant_id=t2, actor_id=actor)
    assert d1 != d2  # tenant-scoped
    # 不同 secret -> 不同 digest（密钥隔离）。
    d3 = _actor_audit_digest(secret="other-secret", tenant_id=t1, actor_id=actor)
    assert d1 != d3


async def test_p1_2_erase_produces_hmac_digest(db_session):
    """P1-2：erase 落库的 creator_identity_digest 必须等于 HMAC 派生值，
    不等于普通 SHA-256。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()

    conv = await db_session.get(ConversationModel, conversation_id)
    expected = _actor_audit_digest(
        secret=_AUDIT_SECRET, tenant_id=TENANT_ID, actor_id=ACTOR_ID
    )
    assert conv.creator_identity_digest == expected
    plain = hashlib.sha256(TENANT_ID.bytes + ACTOR_ID.bytes).hexdigest()
    assert conv.creator_identity_digest != plain


async def test_p1_2_constructor_uses_actor_erasure_secret_not_jwt(
    db_session, monkeypatch
):
    """P1-2：构造默认用 ``settings.actor_erasure_secret``（非 jwt_secret）--密钥
    用途隔离：JWT 轮换不得改变审计身份摘要。"""
    from app.config import settings

    monkeypatch.setattr(settings, "actor_erasure_secret", "configured-actor-secret")
    monkeypatch.setattr(settings, "jwt_secret", "a-different-jwt-secret")
    participant = WorkspaceErasureParticipant(db_session)  # 不传 audit_secret
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()

    conv = await db_session.get(ConversationModel, conversation_id)
    expected = _actor_audit_digest(
        secret="configured-actor-secret", tenant_id=TENANT_ID, actor_id=ACTOR_ID
    )
    assert conv.creator_identity_digest == expected
    # 与 jwt_secret 派生的 digest 不同（密钥隔离）。
    jwt_digest = _actor_audit_digest(
        secret="a-different-jwt-secret", tenant_id=TENANT_ID, actor_id=ACTOR_ID
    )
    assert conv.creator_identity_digest != jwt_digest


async def test_p1_2_production_fail_fast_on_empty_secret(db_session, monkeypatch):
    """P1-2：生产环境 ``actor_erasure_secret`` 为空 -> fail fast（RuntimeError），
    不退化到 jwt_secret 或 dev 占位。"""
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "actor_erasure_secret", "")
    with pytest.raises(RuntimeError, match="actor_erasure_secret must be set"):
        WorkspaceErasureParticipant(db_session)  # 不传 audit_secret


# ---------------------------------------------------------------------------
# P1-3：archived_by / deleted_by 清除 + operation/checkpoint fencing 表驱动反例
# ---------------------------------------------------------------------------


async def test_p1_3_archived_by_deleted_by_cleared(db_session):
    """P1-3：清除后 archived_by/deleted_by（直接主体标识）必须为 NULL，
    不能只清 created_by。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    # deleted_by 已由 soft_delete 设置；再补 archived_by（模拟归档后删除）。
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.archived_by = ACTOR_ID
    await db_session.commit()
    assert conv.deleted_by is not None
    assert conv.archived_by is not None

    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
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
        # checkpoint owner capability CAS 反例（ACK 路径裁决）。
        ("checkpoint_owner_version", "checkpoint owner_version"),
        ("checkpoint_capability_digest", "checkpoint capability_digest"),
    ],
)
async def test_p1_3_operation_fencing_counterexamples(
    db_session, scenario, expected_match
):
    """P1-3 表驱动反例：operation 身份 / lease / hold / owner capability 任一不符
    -> fail closed（ValueError），不基于过期或跨域 operation ACK。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    call_kwargs = {"purge_revision": purge_revision, "expected_lease_epoch": 0}

    if scenario == "cross_conversation":
        # 用另一 conversation 的 operation 误 ACK 本 conversation。
        other_conv_id, other_rev = await _seed_deleted_expired_with_body(
            db_session, title="other conv"
        )
        operation_id = await _make_purge_operation(
            db_session, other_conv_id, other_rev
        )
        # purge_revision 对齐到 other operation（conversation_id 校验先于 revision）。
        call_kwargs["purge_revision"] = other_rev
    elif scenario == "purge_revision_mismatch":
        call_kwargs["purge_revision"] = 999  # operation 冻结 purge_revision=1
    elif scenario == "stale_lease_epoch":
        call_kwargs["expected_lease_epoch"] = 5  # operation lease_epoch=0
    elif scenario == "hold_revision_drift":
        # operation 冻结 hold_revision_snapshot=0；bump conversation hold_revision
        # 模拟 operation 调度后新置 hold -> snapshot 漂移。
        conv = await db_session.get(ConversationModel, conversation_id)
        conv.hold_revision = 1
        await db_session.commit()
    elif scenario == "checkpoint_owner_version":
        cp = await _checkpoint_model(db_session, operation_id)
        cp.owner_version = 2  # fence owner_version=1
        await db_session.commit()
    elif scenario == "checkpoint_capability_digest":
        cp = await _checkpoint_model(db_session, operation_id)
        cp.capability_digest = "0" * 64  # 与已安装 capability 不匹配
        await db_session.commit()

    with pytest.raises(ValueError, match=expected_match):
        await _participant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            purge_operation_id=operation_id,
            now=datetime.now(UTC),
            **call_kwargs,
        )


# ---------------------------------------------------------------------------
# P1-4：ACK 绑定具体 operation/checkpoint CAS + erased fence 恢复
# ---------------------------------------------------------------------------


async def test_p1_4_ack_binds_to_operation_checkpoint_cas(db_session):
    """P1-4：经 purge operation 调用时，ACK 绑定具体 operation_id + owner
    checkpoint CAS（pending/erasing/blocked -> acked），ack_digest/checkpoint_digest
    落库，且与 fence ack_digest 同源。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert outcome.erased

    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    assert checkpoint.ack_digest == outcome.ack_digest
    # checkpoint_digest 与 ack_digest 分离（scan digest vs 摘要 digest）。
    assert checkpoint.checkpoint_digest is not None
    assert checkpoint.checkpoint_digest != checkpoint.ack_digest
    # operation 推进到 running（单 owner 不伪造 completed）。
    operation = await _operation_model(db_session, operation_id)
    assert operation.state == "running"


async def test_p1_4_ack_registry_drift_fail_closed(db_session, monkeypatch):
    """P1-4 反例：operation 的 registry_digest 与已安装 registry 不匹配（drift）
    -> ACK fail closed（OwnerRegistryChangedError），不基于过期能力视图 ACK。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )

    # 模拟 registry drift：已安装 registry digest 与 operation 冻结时不一致。
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
            now=datetime.now(UTC),
        )
    assert registry_digest() != "0" * 64  # 确认 monkeypatch 已还原


async def test_p1_4_erased_fence_repairs_pending_checkpoint(db_session):
    """P1-4：fence 已 erased 但 checkpoint 仍 pending（ACK 丢失/历史不一致）->
    幂等重放**先于 purge 前置**（purged_at 不得阻断恢复），修复 checkpoint 到
    acked（用 fence.ack_digest）、operation 修复到 running。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    # 正常清除 -> fence erased + checkpoint acked + operation running。
    first = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert first.erased
    fence_ack_digest = first.fence.ack_digest

    # 模拟 ACK 丢失：fence 保持 erased，checkpoint 回退 pending、operation 回退
    # scheduled；并设 purged_at--证明恢复先于前置（purged_at 不阻断 erased 重放）。
    cp = await _checkpoint_model(db_session, operation_id)
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    op = await _operation_model(db_session, operation_id)
    op.state = "scheduled"
    conv = await db_session.get(ConversationModel, conversation_id)
    conv.purged_at = datetime.now(UTC)
    await db_session.commit()

    # 幂等重放：fence erased -> 修复 pending checkpoint（先于 purged_at 前置）。
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.ack_digest == fence_ack_digest  # 复用 fence ack_digest

    cp = await _checkpoint_model(db_session, operation_id)
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack_digest
    op = await _operation_model(db_session, operation_id)
    assert op.state == "running"  # scheduled -> running 修复


# ---------------------------------------------------------------------------
# P1-5：blocked 可靠提交 + 重试 + legal hold
# ---------------------------------------------------------------------------


async def test_p1_5_blocked_state_is_committed_not_rolled_back(
    db_session, monkeypatch
):
    """P1-5：scan 非零时 blocked 作为正常返回提交（不抛异常致回滚）。调用方
    commit 后 operation/checkpoint/fence 的 blocked 状态持久化 + scan digest
    落库（P2-2），可重试。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )

    participant = _participant(db_session)
    # 模拟清除后仍残留正文（race/bug）--scan 非零。
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
        now=datetime.now(UTC),
    )
    # 正常返回（不抛异常），调用方 commit。
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_WORKSPACE_BODY_SCAN_NONZERO
    assert not outcome.erased
    assert outcome.ack_digest is None

    # blocked 状态已持久化（未被回滚）。
    fence = await _fence(db_session, conversation_id)
    assert fence.state is ErasureFenceState.BLOCKED
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.BLOCKED.value
    assert checkpoint.reason_code == REASON_WORKSPACE_BODY_SCAN_NONZERO
    # P2-2：blocked 路径也写 scan digest（非零 scan 的证据）。
    assert checkpoint.checkpoint_digest is not None
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.purge_state == "blocked"


async def test_p1_5_retry_after_blocked_acks(db_session, monkeypatch):
    """P1-5 重试：首次 scan 非零 -> blocked（fence erasing->blocked，commit）；
    重试 scan 归零 -> fence blocked->erasing->erased，owner checkpoint -> acked。
    清除幂等（已 redacted 不重复处理）。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )

    # 第一次：scan 非零 -> blocked，commit。
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
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert blocked.blocked
    assert blocked.fence.state is ErasureFenceState.BLOCKED

    # 重试：scan 归零（不再 monkeypatch）-> blocked->erasing->erased，ACK。
    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.fence.state is ErasureFenceState.ERASED
    assert outcome.ack_digest is not None

    # owner checkpoint 经重试最终 acked。
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    assert checkpoint.ack_digest == outcome.ack_digest


async def test_p1_5_legal_hold_blocks_as_normal_return(db_session):
    """P1-5：active legal hold -> blocked 正常返回（不抛异常），不清除正文，
    fence 保持 active，operation/checkpoint 记 blocked（P2-4 reason code）。"""
    conversation_id, purge_revision, operation_id = (
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
        now=datetime.now(UTC),
    )
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    assert not outcome.erased
    # 正文未被清除，fence 仍 active（未进 erasing）。
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"
    fence = await _fence(db_session, conversation_id)
    assert fence.state is ErasureFenceState.ACTIVE
    # operation/checkpoint 记 blocked + Spec §9.2 reason code。
    checkpoint = await _checkpoint_model(db_session, operation_id)
    assert checkpoint.state == PurgeOwnerState.BLOCKED.value
    assert checkpoint.reason_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD


async def test_p1_5_scan_counts_archived_by_deleted_by(db_session):
    """P1-5：body scan 必须计入 archived_by/deleted_by（直接主体标识），
    否则归档/删除操作者残留会绕过完成门禁。"""
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
    """P1-5：已 redacted 但仍带 author_id 的 assistant_output Message（body_state
    非 present）也必须被清除 author_id，否则 scan 永久非零、blocked 无法自愈重试。

    覆盖 ``_redact_messages`` 的 ``or_(body_state=present, author_id IS NOT NULL)``
    选择谓词--只选 body_state=present 会漏掉这类残留。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    # 注入一个已 redacted 但仍带 author_id 的 assistant_output（CHECK 允许：
    # assistant_output 无 author_id/body_state 约束）。
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
        now=datetime.now(UTC),
    )
    await db_session.commit()
    # 清除了残留 author_id -> scan 归零 -> ACK（不是永久 blocked）。
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


# ---------------------------------------------------------------------------
# P2-1：scan_body Conversation 查询带 tenant_id 谓词
# ---------------------------------------------------------------------------


async def test_p2_1_scan_body_tenant_scoped(db_session):
    """P2-1：scan_body 的 Conversation 查询带 tenant_id 谓词--跨 tenant 不得
    误报另一 tenant 会话的 actor 残留（不用裸 get(PK)）。"""
    conversation_id, _ = await _seed_deleted_expired_with_body(db_session)
    other_tenant = uuid.uuid4()
    scan = await _participant(db_session).scan_body(
        tenant_id=other_tenant, conversation_id=conversation_id
    )
    # 跨 tenant：Conversation 不可见 -> 全零（message 查询也有 tenant 谓词）。
    assert scan.unanonymized_actors == 0
    assert scan.present_body_messages == 0


# ---------------------------------------------------------------------------
# P2-3：purge 截止用 PostgreSQL clock_timestamp()（非进程时钟）
# ---------------------------------------------------------------------------


async def test_p2_3_uses_database_clock_when_now_omitted(db_session, monkeypatch):
    """P2-3：省略 ``now`` 时用 PostgreSQL ``clock_timestamp()``（非进程时钟）作为
    purge 截止--在 Conversation 锁后采样。"""
    conversation_id, purge_revision, operation_id = (
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
        # now 省略 -> 走 _database_now()
    )
    await db_session.commit()
    assert outcome.erased
    assert called  # 确认走了 DB 时钟路径


# ---------------------------------------------------------------------------
# S2-D 主路径：清除 + envelope 保留 + scan 零 + ACK
# ---------------------------------------------------------------------------


async def test_erase_clears_title_message_parts_userstate_actor(db_session):
    """S2-D 主路径：清除后 title/正文/Part/UserState/actor 全清，envelope 保留，
    body scan 为零，fence 推进 erased 且带 ack_digest。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )

    outcome = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()

    assert outcome.erased
    assert not outcome.blocked
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
    # conversation actor(present) + message author = 2。
    assert scan.unanonymized_actors == 2
    assert scan.total == 5


# ---------------------------------------------------------------------------
# 幂等 / fail-closed / writer 被拒
# ---------------------------------------------------------------------------


async def test_erase_is_idempotent_replay(db_session):
    """可重入：已 erased 后再次执行清除是幂等 no-op，ack_digest 不变；
    checkpoint 已 acked -> repair no-op。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    first = await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()

    second = await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()
    assert second.erased
    assert second.fence.ack_digest == first.fence.ack_digest
    # checkpoint 仍 acked（repair no-op）。
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
            now=datetime.now(UTC),
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
            now=datetime.now(UTC),
        )
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv.title == "sensitive title"


async def test_writer_rejected_while_erasing(db_session):
    """清除推进 fence 离开 active 后，正文 writer 经 fence 裁决被拒
    （LateBodyWriteRejectedError），清除期间不得有新正文复活。"""
    from app.composition.agent_erasure_locks import acquire_owner_lock

    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    await _participant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
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
    """body scan 检测残留 present 正文（不恒零）：清除后注入残留 -> scan 非零，
    这正是 blocked 不 ACK 的依据。"""
    conversation_id, purge_revision, operation_id = (
        await _seed_purgeable_with_operation(db_session)
    )
    participant = _participant(db_session)
    await participant.erase_conversation_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        purge_operation_id=operation_id,
        now=datetime.now(UTC),
    )
    await db_session.commit()

    # 清除后扫零；注入残留 present message 后扫非零。
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
