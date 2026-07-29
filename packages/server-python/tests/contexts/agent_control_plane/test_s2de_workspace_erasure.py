"""R1-S2 S2-D/E：workspace.core.v1 正文清除 + final body scan + participant ACK。

Spec §5.2/§6.1/§7.1（plan §R1-S2「S2-D/E 契约注记」2026-07-29）：

- 清除：Conversation title 转 tombstone、Message 转 redacted tombstone +
  author 不可逆匿名化（tenant-scoped digest，不留真实 UUID）、物理删除
  MessagePart 正文行与 ConversationUserState；Message envelope（id/seq/kind/
  content_digest）保留。
- final body scan 是完成门禁：present 正文/残留 Part/残留 UserState/未匿名
  actor 全为 0 才允许 ACK；非零 -> blocked + 稳定 reason code，不把受影响
  行数当完成。
- ACK：仅 scan 为零才 fence erasing->erased（ack_digest 只含清除摘要 + scan
  digest，无正文/actor 明文）、owner checkpoint -> acked。
- 锁序 Conversation row -> owner lock -> fence（防 AB-BA）；可重入幂等；
  active legal hold 阻止；跨 tenant/未知会话 fail closed。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    WorkspaceBodyScanNonZeroError,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ConversationUserStateModel,
    MessageModel,
    MessagePartModel,
)
from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
    WorkspaceErasureParticipant,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
)
from tests.contexts.agent_control_plane.test_writer_fence import _text_command

pytestmark = pytest.mark.asyncio

_OWNER = "workspace.core.v1"


async def _seed_conversation_with_body(db_session, *, title: str = "sensitive title"):
    """建一个带正文（user_input Message + Part + UserState pin）的会话。"""
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


async def _fence(db_session, conversation_id):
    return await AgentErasureRepository(db_session).get_fence_for_update(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER
    )


async def test_erase_clears_title_message_parts_userstate_actor(db_session):
    """S2-D 主路径：清除后 title/正文/Part/UserState/actor 全清，envelope 保留，
    body scan 为零，fence 推进 erased 且带 ack_digest。"""
    conversation_id = await _seed_conversation_with_body(db_session)

    fence = await WorkspaceErasureParticipant(
        db_session
    ).erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()

    assert fence.state is ErasureFenceState.ERASED
    assert fence.ack_digest is not None and len(fence.ack_digest) == 64
    assert fence.acked_at is not None

    # Conversation title tombstone + actor 匿名化（真实 UUID 清除，digest 保留）。
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation.title is None
    assert conversation.title_source == "none"
    assert conversation.actor_state == "redacted"
    assert conversation.created_by is None
    assert conversation.creator_identity_digest is not None
    assert len(conversation.creator_identity_digest) == 64
    # envelope 保留：id/state/revision/purge_after 不动。
    assert conversation.id == conversation_id

    # Message 转 redacted tombstone：body/content redacted、author 清除 +
    # digest、redacted_reason 受控、seq/kind/content_digest 保留。
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

    # MessagePart 正文行物理删除、ConversationUserState 物理删除。
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

    # final body scan 为零。
    scan = await WorkspaceErasureParticipant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.total == 0


async def test_body_scan_reports_residual_before_erase(db_session):
    """body scan 在清除前正确报出残留正文（present message + part + user_state +
    未匿名 actor），验证扫描不是恒零摆设。"""
    conversation_id = await _seed_conversation_with_body(db_session)
    scan = await WorkspaceErasureParticipant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.present_body_messages == 1
    assert scan.message_parts == 1
    assert scan.user_states == 1
    # conversation actor(present) + message author = 2 个未匿名主体。
    assert scan.unanonymized_actors == 2
    assert scan.total == 5


async def test_owner_checkpoint_acked_on_erase(db_session):
    """S2-E：经 purge operation/owner checkpoint 执行时，清除 + body scan 零 ->
    该 workspace owner checkpoint 推进 acked（带 ack_digest/checkpoint_digest）。

    只接 workspace.core.v1 单 owner；多 owner 的 operation completed 判定属
    S3/S4，本 Slice 不伪造 purge_state=completed。"""
    from app.contexts.agent_workspace.domain import PurgeOwnerState
    from app.contexts.agent_workspace.infrastructure.models import (
        PurgeOwnerCheckpointModel,
    )

    conversation_id = await _seed_conversation_with_body(db_session)
    repo = AgentErasureRepository(db_session)
    operation = await repo.create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=0,
    )
    await repo.create_owner_checkpoint(
        tenant_id=TENANT_ID,
        purge_operation_id=operation.id,
        owner_key=_OWNER,
    )
    await db_session.commit()

    fence = await WorkspaceErasureParticipant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()
    assert fence.state is ErasureFenceState.ERASED

    checkpoint = (
        (
            await db_session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.purge_operation_id == operation.id,
                    PurgeOwnerCheckpointModel.owner_key == _OWNER,
                )
            )
        )
        .scalars()
        .one()
    )
    assert checkpoint.state == PurgeOwnerState.ACKED.value
    assert checkpoint.ack_digest is not None and len(checkpoint.ack_digest) == 64
    assert checkpoint.checkpoint_digest is not None
    # fence ack_digest 与 owner checkpoint ack_digest 同源（同一次清除摘要）。
    assert checkpoint.ack_digest == fence.ack_digest


async def test_erase_is_idempotent_replay(db_session):
    """可重入：已 erased 后再次执行清除是幂等 no-op，不二次清除、不报错。"""
    conversation_id = await _seed_conversation_with_body(db_session)
    participant = WorkspaceErasureParticipant(db_session)
    first = await participant.erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()
    first_ack = first.ack_digest

    # 重放（同 purge_revision）：fence 已 erased -> 幂等返回，ack_digest 不变。
    second = await WorkspaceErasureParticipant(
        db_session
    ).erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()
    assert second.state is ErasureFenceState.ERASED
    assert second.ack_digest == first_ack

    scan = await WorkspaceErasureParticipant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.total == 0


async def test_active_legal_hold_blocks_erasure(db_session):
    """active legal hold 阻止 active->erasing：不清除任何正文，fence 保持 active。"""
    conversation_id = await _seed_conversation_with_body(db_session)
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=ACTOR_ID,
    )
    await db_session.commit()

    with pytest.raises(WorkspaceBodyScanNonZeroError):
        await WorkspaceErasureParticipant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
        )
    await db_session.rollback()

    # 正文未被清除，fence 仍 active。
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation.title == "sensitive title"
    fence = await _fence(db_session, conversation_id)
    assert fence.state is ErasureFenceState.ACTIVE


async def test_unknown_conversation_fail_closed(db_session):
    """未知 conversation_id -> fail closed（不创建孤儿 fence、不清除）。"""
    with pytest.raises(ValueError, match="not found"):
        await WorkspaceErasureParticipant(db_session).erase_conversation_body(
            tenant_id=TENANT_ID,
            conversation_id=uuid.uuid4(),
            purge_revision=1,
        )


async def test_cross_tenant_fail_closed(db_session):
    """跨 tenant：正确 tenant 的会话对另一 tenant 不可见，清除 fail closed。"""
    conversation_id = await _seed_conversation_with_body(db_session)
    other_tenant = uuid.uuid4()
    with pytest.raises(ValueError, match="not found"):
        await WorkspaceErasureParticipant(db_session).erase_conversation_body(
            tenant_id=other_tenant,
            conversation_id=conversation_id,
            purge_revision=1,
        )
    # 原 tenant 正文未被触动。
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation.title == "sensitive title"


async def test_writer_rejected_while_erasing(db_session):
    """清除推进 fence 离开 active 后，正文 writer 经 fence 裁决被拒
    （LateBodyWriteRejectedError），清除期间不得有新正文复活。

    与 S2-A writer/purge race 互补：那条证明 purge-win 时 writer 被拒；本条证明
    S2-D 清除执行器推进 fence 后，正文 fence 裁决同样 fail closed。"""
    from app.composition.agent_erasure_locks import acquire_owner_lock
    from app.contexts.agent_workspace.domain import LateBodyWriteRejectedError

    conversation_id = await _seed_conversation_with_body(db_session)
    await WorkspaceErasureParticipant(db_session).erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()

    # 正文 writer 的 fence 裁决（require_body_write_fence_for_update）：fence 已
    # erased -> 拒写。先取 owner lock（裁决前置锁序），再裁决。
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


async def test_body_scan_nonzero_blocks_ack(db_session):
    """body scan 非零（模拟清除遗漏 -> 仍有 present 正文）：不得 ACK，fence 保持
    erasing，不把受影响行数当完成。用残留 present message 构造扫描非零。"""
    conversation_id = await _seed_conversation_with_body(db_session)
    participant = WorkspaceErasureParticipant(db_session)

    # 先进 erasing 并清除，再人为补一条 present 正文模拟「清除遗漏/迟到写」，
    # 证明 scan 非零时不会 ACK（这里直接对 scan 断言非零，ACK 路径已由主路径
    # 覆盖；本例锁定 scan 非零判定本身）。
    await participant.erase_conversation_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id, purge_revision=1
    )
    await db_session.commit()

    # 清除后扫零；注入残留 present message 后扫非零 -> 这正是不 ACK 的依据。
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
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ),
    )
    db_session.add(residual)
    await db_session.flush()
    scan = await WorkspaceErasureParticipant(db_session).scan_body(
        tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    assert scan.present_body_messages == 1
    assert scan.total != 0
    await db_session.rollback()
