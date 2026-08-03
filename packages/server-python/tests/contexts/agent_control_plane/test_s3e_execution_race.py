"""R1-S3-E：execution.core.v1 owner 侧竞态/幂等收口测试（plan §11）。

plan §11「竞态与不变量复核」execution owner 侧缺口补齐（对照 workspace 侧
S2-D ``test_writer_fence.py`` 已冻结的同构 race）：

- **purge-win race**（plan §11「清除与并发执行 writer」）：purge 在 owner lock
  内把 execution fence 推进 erasing/erased 后，执行 writer 经
  ``FencedExecutionPort.require_active_fence`` / ``fenced_*`` 裁决即被拒
  （``LateBodyWriteRejectedError``，Spec §6.2），清除期间不得有新 execution
  正文复活。对照 workspace
  ``test_writer_fence_purge_win_race_body_not_resurrected``。
- **writer-win race**（plan §11 同条 + 「dispatch_output race」锁序语义）：
  writer 在 purge 翻 fence 之前持 Conversation 行锁 + owner lock + fence 行锁
  commit 正文（合法）；purge 在锁上等待、writer 提交后接管，participant 的
  清除动作 + final scan 覆盖这份「fence check 后写入」的正文（terminal
  output/context/event payload/actor 归零，正文不残留）。对照 workspace
  ``test_writer_win_race_purge_waits_then_takes_over``。
- **迟到 runtime event**（plan §11「迟到 event」，Spec §6.2）：fence
  erasing/erased 下旧 Runtime event 经 ``fenced_ingest_runtime_event`` 被拒，
  不重建正文、不推进 ``run_event_payload`` watermark。
- **IDEMPOTENT_REPLAY 不推进计数器**（plan §11「event 计数器持久化 + 幂等」）：
  同一 runtime event ingest 两次，第二次是 idempotent replay，
  ``run_event_payload`` watermark 只 +1。对照 workspace
  ``test_s2c_ingress_and_title_fence.py::test_idempotent_replay_does_not_advance_watermark``。

并发协调模式严格复用 workspace 模板：asyncio.Event barrier + 第二会话
（``session_factory``）+ Conversation 行锁/owner advisory lock 串行。
全部真实 PostgreSQL（``db_session``/``session_factory`` fixture），不 mock DB。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid

import pytest
from sqlalchemy import func, select

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_suppression_reasons import SUPPRESSION_REASON_CODES
from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_execution.application.dto import RuntimeEventCommand
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    RunConfigSnapshot,
    RunEventType,
    RunStatus,
    RuntimeEventProvenance,
    RuntimeIngestFrame,
    SnapshotClassification,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
    TurnInputModel,
)
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
    ErasureFenceModel,
)
from tests.contexts.agent_control_plane import s3d_helpers as h
from tests.contexts.agent_execution.e1_helpers import (
    ACTOR,
    READONLY_NATIVE_CAPABILITIES,
    TENANT_A,
    AllowStartBarrier,
    bootstrap_compatibility,
    bootstrap_native_binding,
    make_budget,
    make_event,
    make_run_command,
)

pytestmark = pytest.mark.asyncio

_OWNER_KEY = h.EXECUTION_CORE_OWNER
_ERASED_ACK_DIGEST = "b" * 64  # 64-hex placeholder（满足 char_length=64 CHECK）


# ---------------------------------------------------------------------------
# 锁/围栏/watermark helpers
# ---------------------------------------------------------------------------


async def _lock_conversation_row(session, conversation_id, *, tenant_id) -> None:
    """锁序第一步（Spec §6.1）：Conversation 行 FOR UPDATE。"""
    row = (
        await session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == conversation_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    assert row is not None


async def _execution_fence_to_state(
    session,
    conversation_id,
    target: ErasureFenceState,
    *,
    tenant_id=h.TENANT_ID,
    ack_digest: str | None = None,
):
    """按锁序（owner lock -> fence FOR UPDATE CAS）推进 execution.core.v1 fence。

    对照 workspace ``test_writer_fence.py::_fence_to_state``（owner_key 换成
    execution.core.v1）。purge 模拟用：flip fence 到 erasing/erased 并持有锁，
    由调用方控制提交时机。
    """
    await acquire_owner_lock(
        session,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )
    repo = AgentErasureRepository(session)
    fence = await repo.get_fence_for_update(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    erasing = await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASING,
        purge_revision=1,
        hold_revision=0,
    )
    if target is ErasureFenceState.ERASING:
        return erasing
    return await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
        expected_state=ErasureFenceState.ERASING,
        expected_revision=erasing.revision,
        new_state=target,
        purge_revision=1,
        hold_revision=0,
        ack_digest=ack_digest,
    )


async def _create_active_execution_fence(db_session, conversation_id) -> None:
    """seed execution.core.v1 active baseline fence（等价 backfill 已覆盖）。"""
    await AgentErasureRepository(db_session).create_fence_under_owner_lock(
        tenant_id=h.TENANT_ID,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )


async def _fence_row(session, conversation_id, *, tenant_id) -> ErasureFenceModel:
    return (
        await session.execute(
            select(ErasureFenceModel).where(
                ErasureFenceModel.tenant_id == tenant_id,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == _OWNER_KEY,
            )
        )
    ).scalar_one()


async def _run_event_watermark(session, conversation_id, *, tenant_id) -> int:
    """fence.ingress_checkpoint 的 run_event_payload watermark（缺失视为 0）。"""
    fence = await _fence_row(session, conversation_id, tenant_id=tenant_id)
    sources = (fence.ingress_checkpoint or {}).get("sources", {})
    entry = sources.get("run_event_payload")
    return 0 if entry is None else int(entry.get("watermark", 0))


def _runtime_command(
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    runtime_profile_id: uuid.UUID,
    binding_id: uuid.UUID,
    runtime_epoch: int,
    stream_id: uuid.UUID,
    seq: int,
    digest: str,
    runtime_event_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    with_event: bool = True,
) -> RuntimeEventCommand:
    """构造 RuntimeEventCommand（对照 test_runtime_ingest_and_terminal._runtime_command）。"""
    return RuntimeEventCommand(
        frame=RuntimeIngestFrame(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            runtime_profile_id=runtime_profile_id,
            provenance=RuntimeEventProvenance(
                binding_id=binding_id,
                runtime_epoch=runtime_epoch,
                runtime_seq=seq,
                runtime_event_id=runtime_event_id or uuid.uuid4(),
            ),
            event_digest=digest,
        ),
        stream_id=stream_id,
        event=(
            make_event(
                event_type=RunEventType.PLAN_SUMMARY,
                summary=f"Runtime event {seq}",
                correlation_id=correlation_id,
            )
            if with_event
            else None
        ),
    )


# ---------------------------------------------------------------------------
# 1. purge-win race：fence 翻 erasing/erased 后 writer 被拒，正文不复活
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_state", ["erasing", "erased"])
async def test_execution_purge_win_race_body_not_resurrected(
    db_session, session_factory, target_state
):
    """R1-AC3 / plan §11「清除与并发执行 writer」purge-win：purge 先把
    execution fence 推进 erasing/erased 并提交；writer（fenced_append_event）
    在 Conversation 行锁/owner lock 上等待，purge 提交后必须 fail closed
    （LateBodyWriteRejectedError），正文不得复活。

    对照 workspace ``test_writer_fence_purge_win_race_body_not_resurrected``：
    purge 模拟锁序（Conversation row -> owner lock -> fence CAS）并持锁暂停，
    writer 仅靠同一条锁链串行。
    """
    target = ErasureFenceState(target_state)
    ctx = await h.seed_purgeable_with_run(db_session)
    conversation_id = ctx["conversation_id"]
    run_id = ctx["run_id"]
    identity = ctx["identity"]
    # s3d seed 直落 ORM 的 run_config_snapshot/budget_snapshot 是精简 dict，
    # domain mapper（require_run -> to_run）校验不过；补齐为完整快照让
    # fenced_* 的 Run 归属校验可走真实加载路径。
    budget = make_budget()
    run_row = await db_session.get(AgentRunModel, run_id)
    assert run_row is not None
    run_row.run_config_snapshot = RunConfigSnapshot(
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=identity.runtime_profile.id,
        model_profile_key="model.readonly.v1",
        autonomy_level=1,
        policy_version="policy.v1",
        tool_keys=(),
        budget=budget,
    ).model_dump(mode="json")
    run_row.budget_snapshot = budget.model_dump(mode="json")
    await _create_active_execution_fence(db_session, conversation_id)
    await db_session.commit()

    fence_transitioned = asyncio.Event()
    release_purge = asyncio.Event()

    async def purge_fences_conversation():
        async with session_factory() as session, session.begin():
            # purge 模拟锁序：Conversation row -> owner lock -> fence CAS，
            # 与 writer 仅靠同一条锁链串行。
            await _lock_conversation_row(
                session, conversation_id, tenant_id=h.TENANT_ID
            )
            await _execution_fence_to_state(
                session,
                conversation_id,
                target,
                ack_digest=_ERASED_ACK_DIGEST
                if target is ErasureFenceState.ERASED
                else None,
            )
            fence_transitioned.set()
            await release_purge.wait()

    async def writer():
        async with session_factory() as session, session.begin():
            # writer 锁序（Spec §6.1）：Conversation 行锁 -> fenced port 裁决
            # （owner lock + fence FOR UPDATE）。
            await _lock_conversation_row(
                session, conversation_id, tenant_id=h.TENANT_ID
            )
            return await FencedExecutionPort(session).fenced_append_event(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                run_id=run_id,
                event=make_event(summary="racing execution body"),
            )

    purge_task = asyncio.create_task(purge_fences_conversation())
    writer_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(fence_transitioned.wait(), timeout=5)
        writer_task = asyncio.create_task(writer())
        # purge 持有 Conversation row/owner/fence 锁：writer 不得插队完成。
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(writer_task), timeout=0.5)
        release_purge.set()
        await asyncio.wait_for(purge_task, timeout=5)
        # purge 已提交非 active fence：writer 继续后必须 fail closed。
        with pytest.raises(LateBodyWriteRejectedError):
            await asyncio.wait_for(writer_task, timeout=5)
    finally:
        release_purge.set()
        for task in (purge_task, writer_task):
            if task is not None and not task.done():
                task.cancel()

    # 正文未复活：无新 RunEvent / AgentRun，seed 的 terminal output 未被改写。
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(RunEventModel.conversation_id == conversation_id)
            )
            == 1  # 仅 seed 的一条
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AgentRunModel)
                .where(AgentRunModel.conversation_id == conversation_id)
            )
            == 1
        )
        run = await h.run_model(session, run_id)
        assert run.terminal_output_ref == "obj://terminal/output"
        assert run.output_publish_state == "published"


# ---------------------------------------------------------------------------
# 2. writer-win race：writer 先 commit 正文，purge 等待后接管并清除该正文
# ---------------------------------------------------------------------------


async def test_execution_writer_win_race_purge_waits_then_erases_late_body(
    db_session, session_factory
):
    """R1-AC3 / plan §11 writer-win：writer 通过 active fence 裁决后在 commit
    前暂停（持有 Conversation 行锁 + owner lock + fence 行锁）；purge
    （真实 ``ExecutionErasureParticipant.erase_execution_body``）必须在
    Conversation 行锁上等待，不得插队。writer 提交正文（completed Run 全链：
    create -> start -> running -> commit_terminal + context snapshot）后
    purge 才获锁——purge 的清除动作 + final scan 必须覆盖这份「fence 裁决后
    才写入」的迟到正文（terminal output/context/event payload/actor 归零），
    否则 scan 非零不得 ACK。

    对照 workspace ``test_writer_win_race_purge_waits_then_takes_over``：
    两个方向（purge-win/writer-win）都不丢正确性。
    """
    conversation_id, identity, purge_revision = await h.seed_purgeable(db_session)
    operation_id, op_revision = await h.make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    # execution fence 由 writer 惰性首写建立（Spec §4.2 三重保障之一）。

    writer_holds_locks = asyncio.Event()
    release_writer = asyncio.Event()

    async def writer():
        async with session_factory() as session, session.begin():
            await _lock_conversation_row(
                session, conversation_id, tenant_id=h.TENANT_ID
            )
            port = FencedExecutionPort(session)
            # fenced port 裁决：惰性建 active fence 并持 fence 行锁。
            await port.require_active_fence(
                tenant_id=h.TENANT_ID, conversation_id=conversation_id
            )
            # fence check 已通过、锁在握；在 commit 前暂停，模拟「writer 过
            # check 后与 purge 竞争」的窗口。
            writer_holds_locks.set()
            await release_writer.wait()
            # 窗口后写正文（fence 仍 active，writer 合法持锁）：完整
            # completed Run 链 + context snapshot 正文。
            command = make_run_command(
                identity,
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
            )
            created = await RunCoordinator(session).create_run(command)
            run = created.run
            await port.fenced_create_run(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                run_id=run.id,
                queue_seq=run.queue_seq,
            )
            started, _ = await port.fenced_start_run(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                run_id=run.id,
                expected_revision=run.status_revision,
                start_barrier=AllowStartBarrier(),
            )
            running, _ = await port.fenced_transition_run(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                run_id=run.id,
                expected_status=RunStatus.STARTING,
                expected_revision=started.status_revision,
                target_status=RunStatus.RUNNING,
                summary="Runtime started",
            )
            content = b"writer-win late terminal body"
            await port.fenced_commit_terminal(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                run_id=run.id,
                queue_seq=run.queue_seq,
                expected_status=RunStatus.RUNNING,
                expected_revision=running.status_revision,
                result=TerminalResult(
                    outcome="completed",
                    code="ok",
                    reason="answer ready",
                    output_ref=f"terminal-output-{run.id}",
                    output_digest=hashlib.sha256(content).hexdigest(),
                    output_size=len(content),
                    output_media_type="text/markdown",
                    output_classification=SnapshotClassification.INTERNAL,
                    terminal_message_id=uuid.uuid4(),
                ),
            )
            # context snapshot 正文（create_run 命令不含；同事务落库，模拟
            # create-time snapshot）。
            run_row = await session.get(AgentRunModel, run.id)
            assert run_row is not None
            run_row.context_snapshot_ref = "obj://context/writer-win"
            run_row.context_snapshot_digest = "a" * 64
            run_row.context_snapshot_classification = "internal"
            return run.id

    async def purge():
        async with session_factory() as session, session.begin():
            return await h.participant(session).erase_execution_body(
                tenant_id=h.TENANT_ID,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                purge_operation_id=operation_id,
                expected_operation_revision=op_revision,
            )

    writer_task = asyncio.create_task(writer())
    purge_task: asyncio.Task | None = None
    try:
        # writer 已持 Conversation 行锁 + owner lock + fence 行锁。
        await asyncio.wait_for(writer_holds_locks.wait(), timeout=5)
        purge_task = asyncio.create_task(purge())
        # purge 在 Conversation 行锁上被 writer 阻塞，不得插队完成。
        await asyncio.sleep(0.5)
        assert not purge_task.done()
        # writer 提交正文后释放锁；purge 获锁接管。
        release_writer.set()
        run_id = await asyncio.wait_for(writer_task, timeout=5)
        outcome = await asyncio.wait_for(purge_task, timeout=5)
    finally:
        release_writer.set()
        for task in (writer_task, purge_task):
            if task is not None and not task.done():
                task.cancel()

    # purge 接管后清除 + final scan 全零 -> ACK erased（覆盖 writer 迟到正文）。
    assert outcome.erased
    assert outcome.ack_digest is not None

    async with session_factory() as session:
        run = await h.run_model(session, run_id)
        # terminal output suppress：正文字段归零，tombstone digest/size 保留。
        assert run.output_publish_state == "suppressed"
        assert run.terminal_output_ref is None
        assert run.terminal_output_media_type is None
        assert run.terminal_output_classification is None
        assert run.terminal_message_id is None
        assert run.terminal_output_digest is not None
        # terminal_code/reason 归一受控白名单。
        assert run.terminal_code in SUPPRESSION_REASON_CODES
        assert run.terminal_reason in SUPPRESSION_REASON_CODES
        # context snapshot 清除。
        assert run.context_snapshot_ref is None
        assert run.context_snapshot_digest is None
        assert run.context_snapshot_classification is None
        # actor 匿名化。
        assert run.created_by is None
        assert run.actor_state == "redacted"
        # event payload tombstone：writer 链产生的 start/transition/terminal
        # 事件全部 redacted，无 inline 正文残留。
        total_events = await session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(RunEventModel.run_id == run_id)
        )
        assert total_events >= 3
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(
                    RunEventModel.run_id == run_id,
                    RunEventModel.payload_inline.isnot(None),
                )
            )
            == 0
        )
        # TurnInput actor 匿名化（plan §11「TurnInput 覆盖」）。
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TurnInputModel)
                .where(
                    TurnInputModel.run_id == run_id,
                    TurnInputModel.created_by.isnot(None),
                )
            )
            == 0
        )
        # fence 终态 erased + ACK digest 落库。
        fence = await _fence_row(session, conversation_id, tenant_id=h.TENANT_ID)
        assert fence.state == ErasureFenceState.ERASED.value
        assert fence.ack_digest == outcome.ack_digest


# ---------------------------------------------------------------------------
# 3. 迟到 runtime event：fence erasing/erased 下被拒，不重建正文、不推进计数器
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_state", ["erasing", "erased"])
async def test_late_runtime_event_rejected_under_non_active_fence(
    db_session, session_factory, target_state
):
    """plan §11「迟到 event」（Spec §6.2）：fence erasing/erased 下旧 Runtime
    event 经 ``fenced_ingest_runtime_event`` 必须 (a) 抛
    ``LateBodyWriteRejectedError``，(b) 不重建正文（无新 RunEvent、seed 正文
    不被改写），(c) 不推进 ``run_event_payload`` watermark
    （fence.ingress_checkpoint 不变）。
    """
    target = ErasureFenceState(target_state)
    ctx = await h.seed_purgeable_with_run(db_session)
    conversation_id = ctx["conversation_id"]
    run_id = ctx["run_id"]
    await _create_active_execution_fence(db_session, conversation_id)
    await db_session.commit()

    # 先把 run_event_payload watermark 推进到 1（迟到的 ingest 不得再动它）。
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        fence = await port.require_active_fence(
            tenant_id=h.TENANT_ID, conversation_id=conversation_id
        )
        await port.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key="run_event_payload",
            watermark=0,  # advance_checkpoint 内部 +1
        )
    assert (
        await _run_event_watermark(db_session, conversation_id, tenant_id=h.TENANT_ID)
        == 1
    )

    # purge fencing：fence 翻 erasing/erased 并提交。
    await _execution_fence_to_state(
        db_session,
        conversation_id,
        target,
        ack_digest=_ERASED_ACK_DIGEST
        if target is ErasureFenceState.ERASED
        else None,
    )
    await db_session.commit()

    # 迟到 runtime event：frame 身份一致（过 _require_frame_identity），
    # 在 fence 裁决处被拒，ingest 本体不会执行。
    late_event_id = uuid.uuid4()
    command = _runtime_command(
        tenant_id=h.TENANT_ID,
        conversation_id=conversation_id,
        run_id=run_id,
        runtime_profile_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        runtime_epoch=1,
        stream_id=uuid.uuid4(),
        seq=1,
        digest="c" * 64,
        runtime_event_id=late_event_id,
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await FencedExecutionPort(db_session).fenced_ingest_runtime_event(
            tenant_id=h.TENANT_ID,
            conversation_id=conversation_id,
            run_id=run_id,
            command=command,
        )
    await db_session.rollback()

    # (b) 不重建正文：迟到事件未落库，RunEvent 总数不变，seed 正文未改写。
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(RunEventModel.runtime_event_id == late_event_id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(RunEventModel.conversation_id == conversation_id)
        )
        == 1  # 仅 seed 的一条
    )
    run = await h.run_model(db_session, run_id)
    assert run.terminal_output_ref == "obj://terminal/output"
    assert run.output_publish_state == "published"
    # (c) watermark 不推进：仍为 1。
    assert (
        await _run_event_watermark(db_session, conversation_id, tenant_id=h.TENANT_ID)
        == 1
    )


# ---------------------------------------------------------------------------
# 4. IDEMPOTENT_REPLAY 不推进 run_event_payload 计数器（真实 PG）
# ---------------------------------------------------------------------------


async def test_ingest_idempotent_replay_does_not_advance_run_event_watermark(
    session_factory,
):
    """plan §11「event 计数器持久化 + 幂等」：真实 PG 下同一 runtime event 经
    ``fenced_ingest_runtime_event`` ingest 两次——第一次真实插入
    （``idempotent_replay=False``，watermark +1），第二次 idempotent replay
    （``idempotent_replay=True``）不推进：``run_event_payload`` watermark
    只 +1（不 +2）。

    对照 workspace
    ``test_s2c_ingress_and_title_fence.py::test_idempotent_replay_does_not_advance_watermark``
    与 execution 侧 ``test_runtime_ingest_and_terminal.py`` 的 replay 语义。
    run 生命周期 setup 走未 fenced 的 RunCoordinator（只让 ingest 一条路径
    推进计数器，便于精确断言 +1）。
    """
    # setup：真实 Conversation + native binding + RUNNING Run（未经 fenced
    # port，不产生 run_event_payload 推进）。
    async with session_factory() as setup, setup.begin():
        view, _ = await AgentWorkspaceService(setup).create_conversation(
            tenant_id=TENANT_A, actor_id=ACTOR, title="s3e replay"
        )
        conversation_id = view.conversation.id
        identity = await bootstrap_compatibility(setup, tenant_id=TENANT_A)
        profile_id, binding, stream_id = await bootstrap_native_binding(
            setup, identity, conversation_id=conversation_id
        )
        coordinator = RunCoordinator(setup, start_barrier=AllowStartBarrier())
        command = make_run_command(
            identity,
            tenant_id=TENANT_A,
            conversation_id=conversation_id,
            runtime_profile_id=profile_id,
            runtime_capabilities=READONLY_NATIVE_CAPABILITIES,
            runtime_binding_id=binding.id,
        )
        created = await coordinator.create_run(command)
        started, _ = await coordinator.start_run(
            tenant_id=TENANT_A,
            run_id=created.run.id,
            expected_revision=created.run.status_revision,
        )
        run, _ = await coordinator.transition_run(
            tenant_id=TENANT_A,
            run_id=started.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="Pi read-only Runtime is running",
        )

    ingest = _runtime_command(
        tenant_id=TENANT_A,
        conversation_id=conversation_id,
        run_id=run.id,
        runtime_profile_id=profile_id,
        binding_id=binding.id,
        runtime_epoch=binding.current_epoch,
        stream_id=stream_id,
        seq=1,
        digest="c" * 64,
        correlation_id=run.correlation_id,
    )

    # 第一次 ingest：真实插入，watermark +1。
    async with session_factory() as session, session.begin():
        first = await FencedExecutionPort(session).fenced_ingest_runtime_event(
            tenant_id=TENANT_A,
            conversation_id=conversation_id,
            run_id=run.id,
            command=ingest,
        )
    assert first.idempotent_replay is False
    assert first.event is not None

    # 第二次 ingest（同 frame/event id/digest）：idempotent replay。
    async with session_factory() as session, session.begin():
        replay = await FencedExecutionPort(session).fenced_ingest_runtime_event(
            tenant_id=TENANT_A,
            conversation_id=conversation_id,
            run_id=run.id,
            command=ingest,
        )
    assert replay.idempotent_replay is True
    assert replay.event is None

    # watermark 只 +1（replay 不推进）。
    async with session_factory() as session:
        assert (
            await _run_event_watermark(session, conversation_id, tenant_id=TENANT_A)
            == 1
        )
