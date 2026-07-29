"""R1-S2 S2-C：ingress checkpoint 真实 source key + title/create 接 fence。

Spec §5.1/§6.2（plan §R1-S2「S2-C 契约注记」2026-07-29）：

- ``ingress_checkpoint`` 以 ``workspace.core.v1`` 能力类别为 canonical source
  key——``body_messages`` 用 message ``seq`` 连续水位、``title`` 用
  Conversation ``revision``，epoch 取 ``purge_revision``；digest 走 shared
  ``canonical_digest``。**不用** ``last_body_write_at``（可观察时间戳）或
  fence 自身 ``revision``（CAS 计数器）冒充 ingress checkpoint。
- 正文写 / checkpoint / receipt 同一事务 commit：checkpoint 记录的是**本写**
  分配到的真实 seq（或 title CAS 后的 revision），不是下一水位，也不得落后。
- title（rename/auto-title）经 ``workspace.core.v1`` 的 ``conversation_title``
  能力，与正文同走 fence 裁决 + ingress 推进；fence 非 active 一律
  ``LateBodyWriteRejectedError``。
- Conversation create 真实新建分支经 ``create_fence_under_owner_lock`` 建立
  ``workspace.core.v1`` baseline ``active`` fence（缺失不得解释为安全）。
- list/get/search/history 对 deleted/purged fail closed，已知 UUID 不泄露
  title/正文/actor 或可恢复元数据。
"""

from __future__ import annotations

import pytest

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    LateBodyWriteRejectedError,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    create_baseline_fences,
)
from tests.contexts.agent_control_plane.test_writer_fence import (
    _fence_to_state,
    _text_command,
)

pytestmark = pytest.mark.asyncio

_OWNER_KEY = "workspace.core.v1"


async def _core_fence(session, conversation_id):
    return await AgentErasureRepository(session).get_fence_for_update(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )


async def _ingress_sources(session, conversation_id) -> dict:
    fence = await _core_fence(session, conversation_id)
    assert fence is not None
    return dict(fence.ingress_checkpoint.get("sources", {}))


# ---------------------------------------------------------------------------
# Item 3：真实 ingress_checkpoint（body 用 message seq 水位）
# ---------------------------------------------------------------------------


async def test_body_write_advances_ingress_checkpoint_to_written_seq(db_session):
    """body ingress 真实 source key（Spec §6.2 第 4 步）：首次写用户正文后，
    ``body_messages`` source 的 watermark 等于本写分配到的 message ``seq``
    （连续水位），epoch 等于 Conversation 当前 ``purge_revision``。

    不得用 ``last_body_write_at`` 或 fence ``revision`` 冒充：checkpoint 记录
    的是真实 source 序号。失败形态：checkpoint 仍为空 ``{}``（S2-A 只推进
    last_body_write_at/revision，未写 source key）。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="ingress body"
    )
    conversation_id = view.conversation.id

    result = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=_text_command("first body"),
    )
    assert result.idempotent_replay is False
    written_seq = result.message.seq

    sources = await _ingress_sources(db_session, conversation_id)
    body = sources.get("body_messages")
    assert body is not None, "body_messages source key missing from checkpoint"
    assert body["watermark"] == written_seq
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert body["epoch"] == conversation.purge_revision

    fence = await _core_fence(db_session, conversation_id)
    assert fence is not None
    # digest 与 checkpoint 同源（shared canonical_digest），不伪造。
    from app.shared.schemas.canonical_json import canonical_digest

    assert fence.ingress_digest == canonical_digest(fence.ingress_checkpoint)


async def test_second_body_write_advances_watermark_monotonically(db_session):
    """连续水位随正文写单调推进：第二次写正文后 watermark 推进到新的 seq。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="ingress body 2"
    )
    conversation_id = view.conversation.id

    first = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=_text_command("one"),
    )
    second = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=_text_command("two"),
    )
    assert first.message.seq < second.message.seq

    sources = await _ingress_sources(db_session, conversation_id)
    assert sources["body_messages"]["watermark"] == second.message.seq


async def test_idempotent_replay_does_not_advance_watermark(db_session):
    """幂等重放（同 client_message_id）不写新正文，watermark 不得推进——
    checkpoint 只反映真实正文写。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="ingress replay"
    )
    conversation_id = view.conversation.id
    command = _text_command("replayed body")

    first = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
    )
    replay = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
    )
    assert replay.idempotent_replay is True
    assert replay.message.seq == first.message.seq

    sources = await _ingress_sources(db_session, conversation_id)
    assert sources["body_messages"]["watermark"] == first.message.seq


# ---------------------------------------------------------------------------
# Item 2 + 3：title writer 接 fence + title ingress（用 Conversation revision）
# ---------------------------------------------------------------------------


async def test_rename_advances_title_ingress_checkpoint(db_session):
    """title ingress 真实 source key：rename 写 title 后，``title`` source 的
    watermark 等于 title CAS 后的 Conversation ``revision``，epoch 等于
    ``purge_revision``。title 经 ``conversation_title`` 能力接 fence。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title=None
    )
    conversation_id = view.conversation.id
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await db_session.commit()

    await service.rename_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        title="renamed title",
        expected_revision=1,
    )
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None

    sources = await _ingress_sources(db_session, conversation_id)
    title = sources.get("title")
    assert title is not None, "title source key missing from checkpoint"
    assert title["watermark"] == conversation.revision
    assert title["epoch"] == conversation.purge_revision


async def test_rename_with_erasing_fence_rejected(db_session):
    """title writer fence（item 2）：fence erasing 时 rename 必须 fail closed
    （LateBodyWriteRejectedError），不得在清除路径上改写 title。

    失败形态：set_title 当前不接 fence，rename 直接成功（无拒绝）。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="original"
    )
    conversation_id = view.conversation.id
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await service.rename_conversation(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            title="should be rejected",
            expected_revision=1,
        )
    await db_session.rollback()
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert conversation.title == "original"


async def test_auto_title_with_erasing_fence_rejected(db_session):
    """auto-title writer fence：fence 非 active 时 apply_auto_title fail closed。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title=None
    )
    conversation_id = view.conversation.id
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await service.apply_auto_title(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            title="auto title",
            expected_revision=1,
        )


# ---------------------------------------------------------------------------
# Item 2：Conversation create 建 baseline fence
# ---------------------------------------------------------------------------


async def test_create_conversation_establishes_baseline_core_fence(db_session):
    """create 真实新建分支建 workspace.core.v1 baseline active fence（缺失不得
    解释为安全）。幂等重放分支不重建 fence。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, created = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="baseline fence"
    )
    assert created is True
    conversation_id = view.conversation.id

    fence = await _core_fence(db_session, conversation_id)
    assert fence is not None, "create must establish baseline core fence"
    assert fence.state is ErasureFenceState.ACTIVE
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert fence.purge_revision == conversation.purge_revision
    assert fence.hold_revision == conversation.hold_revision


# ---------------------------------------------------------------------------
# Item 1：read 路径 fail closed（已知 UUID 不泄露 title/正文/actor）
# ---------------------------------------------------------------------------


async def test_get_history_deleted_conversation_fail_closed(db_session):
    """deleted 会话已知 UUID：get/list_messages 返回 gone/not-found，不泄露
    title、正文或 actor。"""
    from app.contexts.agent_workspace.domain import ConversationNotFoundError

    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="secret title"
    )
    conversation_id = view.conversation.id
    await db_session.commit()

    # 软删除（经 coordinator 维持不变量）。
    from app.composition.agent_control_plane import ConversationExecutionCoordinator

    await ConversationExecutionCoordinator(db_session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
    )
    await db_session.commit()

    # get（默认不含 deleted）-> gone。
    got = await service._repo.get_conversation(
        TENANT_ID, ACTOR_ID, conversation_id
    )
    assert got is None
    # history（list_messages）-> not found，不泄露正文。
    with pytest.raises(ConversationNotFoundError):
        await service.list_messages(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
        )


# ---------------------------------------------------------------------------
# Item 6：reserve fence 校验先于幂等 replay 查找
# ---------------------------------------------------------------------------


async def test_reserve_fence_check_precedes_idempotent_replay(db_session):
    """item 6（plan §R1-S2 S2-C 注记）：``reserve_user_turn`` 的 fence 校验必须
    先于幂等 replay 查找——fence 非 active（purge 进行中）时，即使
    ``client_message_id`` 已存在（本可幂等命中返回）也 fail closed
    ``LateBodyWriteRejectedError``，不得因幂等命中而复活清除路径上的正文。

    顺序错误形态：先查 replay 命中直接返回，fence 拒绝被绕过。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="fence before replay"
    )
    conversation_id = view.conversation.id
    command = _text_command("existing body")
    first = await service.reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
    )
    assert first.idempotent_replay is False
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    # 推进 fence 到 erasing（purge 进行中）。
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    # 同一 client_message_id 重放：fence 校验先于 replay 命中 -> fail closed。
    with pytest.raises(LateBodyWriteRejectedError):
        await service.reserve_user_turn(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            command=command,
        )


# ---------------------------------------------------------------------------
# Item 7：concurrent double-restore race
# ---------------------------------------------------------------------------


async def test_concurrent_double_restore_race_single_winner(
    db_session, session_factory
):
    """item 7（plan §R1-S2 S2-C 注记）：两个并发 restore（同一
    expected_revision）只有一个成功——Conversation 行锁串行 + revision CAS
    兜底，第二个 fail closed（revision_conflict / 状态非法），不得双推进
    purge_revision 或重复取消 purge operation。

    hold 生效中的 restore 归 hold slice（S5），本测试只覆盖无 hold 的
    double-restore race。"""
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.composition.agent_control_plane import ConversationExecutionCoordinator

    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="double restore"
    )
    conversation_id = view.conversation.id
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    deleted_at = datetime(2026, 1, 1, tzinfo=UTC)
    await ConversationExecutionCoordinator(db_session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
        now=deleted_at,
    )
    await db_session.commit()
    restore_now = deleted_at + timedelta(days=1)

    async def restore_once():
        async with session_factory() as session, session.begin():
            return await ConversationExecutionCoordinator(
                session
            ).restore_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                expected_revision=2,
                now=restore_now,
            )

    results = await asyncio.gather(
        restore_once(), restore_once(), return_exceptions=True
    )
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    # 恰好一个成功；另一个 fail closed（不双推进）。
    assert len(successes) == 1, f"expected single winner, got {results!r}"
    assert len(failures) == 1

    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert conversation.state == "active"
    # purge_revision 只推进一次（delete +1、restore +1），不得双推进。
    assert conversation.purge_revision == 2


# ---------------------------------------------------------------------------
# Item 8：advance 非 active 守卫（writer-win race 原子兜底）
# ---------------------------------------------------------------------------


async def test_advance_ingress_checkpoint_rejects_non_active_fence(db_session):
    """item 8（M6 反例）：``advance_ingress_checkpoint_for_update`` 对非 active
    fence 必须 fail closed——这是「verdict 放行后被并发 purge 接管」race 的原子
    兜底：fence 已 erasing 时不得为已拒正文补 checkpoint（不复活清除路径）。"""
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="advance guard"
    )
    conversation_id = view.conversation.id
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    repo = AgentErasureRepository(db_session)
    with pytest.raises(LateBodyWriteRejectedError):
        await repo.advance_ingress_checkpoint_for_update(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            owner_key=_OWNER_KEY,
            source_key="body_messages",
            watermark=1,
            epoch=0,
        )
    await db_session.rollback()
    # checkpoint 未被推进（仍为空 sources）。
    fence = await _core_fence(db_session, conversation_id)
    assert fence is not None
    assert fence.ingress_checkpoint.get("sources") in (None, {})
