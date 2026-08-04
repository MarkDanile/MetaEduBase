"""R1-S3-E §6：fenced port 无旁路守卫（行为断言版）。

plan §2 / §11（round-1 P1-1 + round-2 P1-2）：所有生产路径写 execution.core.v1
正文必须经 composition-owned ``FencedExecutionPort``，禁止生产路径直调未 fenced
的 ``RunCoordinator`` / ``CompatibilityOutputService`` writer。

round-5 的 AST/字符串守卫因脆弱（误报 docstring、检出不了「接了 port 却绕过裁
决」）被删。本测试改用**行为断言**锁定无旁路：把 execution fence 翻 erased 后，
production 写正文入口必须实抛 ``LateBodyWriteRejectedError``。若某入口绕过 fence
裁决（直调 RunCoordinator writer），写会成功、不抛错 -> 测试转红。这是「无旁路」
的可证等价物：fence 非 active 时唯一合法结果是拒绝，任何能写成功的路径都是旁路。

变异验证：把 ``start_run``/``consume_turn_event`` 的 fence 裁决移除（直调
``RunCoordinator`` writer）-> 对应入口不再抛 ``LateBodyWriteRejectedError`` -> 转红。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
)
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio

_EXECUTION_OWNER = "execution.core.v1"


async def _force_execution_fence(db_session, *, conversation_id, state: str) -> None:
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = :state "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {"state": state, "t": TENANT_ID, "c": conversation_id, "o": _EXECUTION_OWNER},
    )
    await db_session.flush()


async def _seed_active_run(db_session, session_factory):
    """bootstrap workspace + submit_turn + dispatch_turn -> 一个 active fence 下
    已创建的 Run（QUEUED）。返回 (conversation_id, run)。"""
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "trigger"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="s3e-nobypass-seed"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None
    return conversation_id, identity, launch, run


async def test_start_run_rejects_when_execution_fence_erased(
    db_session, session_factory
):
    """production ``start_run`` 入口：fence erased -> 抛 LateBodyWriteRejectedError。

    钉死 start_run 经 fence 裁决（无直调 RunCoordinator.start_run 旁路）。
    """
    conversation_id, _, _, run = await _seed_active_run(db_session, session_factory)
    await _force_execution_fence(
        db_session, conversation_id=conversation_id, state="erasing"
    )
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError) as excinfo:
        await ConversationExecutionCoordinator(db_session).start_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_revision=run.status_revision,
        )
    # 钉死「确经 fence 裁决」：报错须来自 owner fence 非 active（而非下游
    # barrier/状态机巧合拒绝）。变异（绕过 fence 直调 RunCoordinator）->
    # 抛 RunConflictError 或写成功，本断言与上一条一起转红。
    assert "fence" in str(excinfo.value).lower()


async def test_consume_turn_event_rejects_when_execution_fence_erased(
    db_session, session_factory
):
    """create_run 真实入口 consume_turn_event：fence erased -> 抛 LateBodyWriteRejectedError。

    round-2 P1-2：Run 由 dispatch_turn -> consume_turn_event 创建（不是
    submit_turn）。钉死该 create 入口经 fence 裁决、无旁路。
    """
    conversation_id, identity, launch, _run = await _seed_active_run(
        db_session, session_factory
    )
    await _force_execution_fence(
        db_session, conversation_id=conversation_id, state="erasing"
    )
    await db_session.commit()

    # fence erased 后再提交一个 turn 并 dispatch（create_run 真实路径）。
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "second turn"),
        launch=launch,
    )
    await db_session.commit()
    with pytest.raises(LateBodyWriteRejectedError):
        await AgentBridgeDispatcher(
            session_factory, worker_id="s3e-nobypass-dispatch"
        ).dispatch_turn(event_id=receipt.event_id)
