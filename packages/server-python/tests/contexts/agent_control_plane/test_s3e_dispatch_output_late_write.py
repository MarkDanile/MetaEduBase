"""R1-S3-E §8：dispatch_output 遇 LateBodyWriteRejectedError -> deterministic 分类。

plan §8（「不盲重试正文写」，R1-AC8）：execution outbox -> workspace assistant
message publish 时，若 workspace.core.v1 fence 非 active（purge 进行中/已完成），
``require_body_write_fence_for_update`` 抛 ``LateBodyWriteRejectedError``。该结果是
deterministic（Conversation 已在 purge，重试永远无法写入正文），dispatcher 不得
走 transient 的 backoff 重试，应直接把 outbox 事件落为不可重试终态：

- outbox 事件 ``status = 'cancelled'``（脱离 pending/claimed 可重试集）；
- ``decision_reason = 'late_body_write_rejected'``（受控 reason code，非异常类名）；
- ``Run.output_publish_state = 'suppressed'``；
- 不排 ``next_attempt_at``、清零在途 claim（``claimed_by``/``claimed_at``）。

边界（plan §8 / S4）：本路径只 suppress 投影、**不清 transport owner 正文**
（outbox ``payload_inline``/``payload_ref`` 原样保留，归 execution.transport.v1）。
transient 故障（非 LateBodyWriteRejectedError）不受影响，仍走 backoff 重试。

变异验证：把 dispatcher 的 ``except LateBodyWriteRejectedError`` 分支移除（退回
通用 ``_record_output_failure`` backoff 重试），以下测试全部转红。
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import select

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    DispatchPolicy,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    OutputPublishState,
    RunStatus,
    SnapshotClassification,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import ErasureFenceModel
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    StaticOutputReader,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio

_WORKSPACE_OWNER = "workspace.core.v1"


async def _completed_run_with_pending_outbox(
    db_session, session_factory, *, content: bytes
):
    """真实 dispatch_turn + start + transition + commit_terminal -> completed Run +
    一个 pending 的 assistant publish outbox 事件（正文尚未投影到 workspace）。"""
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "complete output"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="s3e-setup"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None
    terminal_message_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        started, _ = await ConversationExecutionCoordinator(session).start_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_revision=1,
        )
        running, _ = await RunCoordinator(session).transition_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="Runtime started",
        )
        completed, _, _ = await RunCoordinator(session).commit_terminal(
            tenant_id=TENANT_ID,
            run_id=run.id,
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
                terminal_message_id=terminal_message_id,
            ),
        )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None and outbox.status == "pending"
    return conversation_id, completed, outbox


async def _flip_workspace_fence_to_erased(
    db_session, *, tenant_id, conversation_id
) -> None:
    """把 workspace.core.v1 fence ACTIVE -> ERASING -> ERASED（模拟 purge 完成）。

    只翻 workspace fence（dispatch_output 检查的是 workspace.core.v1），不经 S3-D
    participant（避免误清 workspace 正文 / 触发 execution 清除，越出本测试边界）。
    """
    repo = AgentErasureRepository(db_session)
    fence = await db_session.scalar(
        select(ErasureFenceModel).where(
            ErasureFenceModel.tenant_id == tenant_id,
            ErasureFenceModel.conversation_id == conversation_id,
            ErasureFenceModel.owner_key == _WORKSPACE_OWNER,
        )
    )
    assert fence is not None, "workspace fence should exist after bootstrap"
    # ->erasing/erased 必须带 purge fencing token（>=1）；测试用 purge_revision+1
    # 模拟一次真实 purge 推进的 token（production 由 purge operation 提供）。
    purge_token = fence.purge_revision + 1
    await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_WORKSPACE_OWNER,
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASING,
        purge_revision=purge_token,
        hold_revision=fence.hold_revision,
    )
    await db_session.flush()
    fence = await db_session.scalar(
        select(ErasureFenceModel).where(
            ErasureFenceModel.tenant_id == tenant_id,
            ErasureFenceModel.conversation_id == conversation_id,
            ErasureFenceModel.owner_key == _WORKSPACE_OWNER,
        )
    )
    await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_WORKSPACE_OWNER,
        expected_state=ErasureFenceState.ERASING,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASED,
        purge_revision=purge_token,
        hold_revision=fence.hold_revision,
        ack_digest="0" * 64,
    )
    await db_session.flush()


async def test_dispatch_output_late_write_is_deterministic_not_retried(
    db_session, session_factory
):
    """erased fence 下 dispatch_output：outbox 事件 deterministic 终态、不重试。"""
    conversation_id, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"# purged answer"
    )
    await _flip_workspace_fence_to_erased(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await db_session.commit()
    payload_inline_before = outbox.payload_inline

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="s3e-output",
        output_reader=StaticOutputReader(b"# purged answer"),
        policy=DispatchPolicy(max_attempts=5),
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await dispatcher.dispatch_output(event_id=outbox.id)

    # fresh session 重读，断言 deterministic 终态已提交。
    async with session_factory() as check:
        persisted = await check.get(ExecutionOutboxModel, outbox.id)
        assert persisted is not None
        assert persisted.status == "cancelled", "deterministic: 脱离可重试集"
        assert persisted.decision_reason == "late_body_write_rejected"
        assert persisted.decision_digest is not None
        assert persisted.claimed_by is None and persisted.claimed_at is None
        # S4 边界：不清 transport owner 正文（payload 原样保留）。
        assert persisted.payload_inline == payload_inline_before
        persisted_run = await check.get(AgentRunModel, run.id)
        assert persisted_run is not None
        assert (
            persisted_run.output_publish_state == OutputPublishState.SUPPRESSED.value
        )

    # 不重试：事件已离开 pending/claimed，dispatcher 再跑应无事件可 claim。
    again = AgentBridgeDispatcher(
        session_factory,
        worker_id="s3e-output-retry",
        output_reader=StaticOutputReader(b"# purged answer"),
    )
    assert await again.dispatch_output(event_id=outbox.id) is False


async def test_dispatch_output_transient_failure_still_retries(
    db_session, session_factory
):
    """对照组：transient 故障（非 LateBodyWriteRejectedError）仍走 backoff 重试。

    钉死「deterministic 分支不误伤 transient 重试」——S3-E 只对
    LateBodyWriteRejectedError 分类，其他异常维持既有 backoff 语义。
    """
    from tests.contexts.agent_control_plane.helpers import FailingOutputReader

    _, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"transient output"
    )
    await db_session.commit()

    failing = AgentBridgeDispatcher(
        session_factory,
        worker_id="s3e-transient",
        output_reader=FailingOutputReader(),
        policy=DispatchPolicy(max_attempts=3),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        await failing.dispatch_output(event_id=outbox.id)

    async with session_factory() as check:
        persisted = await check.get(ExecutionOutboxModel, outbox.id)
        assert persisted is not None
        # transient：仍回 pending 可重试（attempt_count<max_attempts），不 suppress。
        assert persisted.status == "pending"
        assert persisted.decision_reason is None
        persisted_run = await check.get(AgentRunModel, run.id)
        assert persisted_run is not None
        assert persisted_run.output_publish_state == OutputPublishState.PENDING.value
