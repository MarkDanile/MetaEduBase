from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.composition.agent_run_access import build_run_query_service
from app.contexts.agent_execution.application.dto import EventReplayWindow
from app.contexts.agent_execution.application.ports import ConversationAccessDecision
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.application.run_query_service import RunQueryService
from app.contexts.agent_execution.domain import (
    EventVisibility,
    RunRevisionConflictError,
    RunStatus,
    SnapshotClassification,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.execution_query_repository import (
    AgentExecutionQueryRepository,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
)
from app.contexts.agent_execution.interfaces.api.router import (
    _stream_event_frames,
)
from app.contexts.agent_execution.interfaces.api.router import (
    router as agent_execution_router,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import ConversationState
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
from app.contexts.identity.infrastructure.models import UserModel
from app.contexts.identity.interfaces.api.dependencies import (
    get_current_user,
    get_stream_current_user,
)
from app.main import app
from app.shared.infrastructure.database import get_session, get_session_factory
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_execution.e1_helpers import (
    AllowStartBarrier,
    make_event,
    make_run_command,
)
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class _AllowCancel:
    """R1-S3-C round-7 commit-17：Guard-first 后不再能在 resolve 中做并发 mutation
    （会死锁等 Guard）。改用 committed-before-cancel 模式，access resolve 只返回
    can_cancel=True。"""

    async def resolve(self, **_kwargs):
        return ConversationAccessDecision(
            audience_key=f"conversation_owner.v1:{DEFAULT_ADMIN_ID}",
            visible_event_scopes=frozenset({EventVisibility.USER}),
            can_cancel=True,
        )


def _build_cancel_service(session: AsyncSession) -> RunQueryService:
    """构造 RunQueryService 注入三个必填 Protocol（commit-12）。"""
    from app.composition.agent_control_plane import ConversationExecutionGuard
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_workspace.application.bridge import (
        AgentWorkspaceBridgeService,
    )

    return RunQueryService(
        session,
        conversation_access=_AllowCancel(),
        workspace_read=AgentWorkspaceBridgeService(session),
        guard=ConversationExecutionGuard(),
        fenced_writer=FencedExecutionPort(session),
    )


@pytest_asyncio.fixture
async def run_client(client: AsyncClient, session_factory):
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    yield client
    app.dependency_overrides.pop(get_session_factory, None)


async def _create_run(session, *, title: str = "A1 run"):
    conversation, _ = await AgentWorkspaceService(session).create_conversation(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
        title=title,
    )
    from app.contexts.agent_execution.application.execution_identity_service import (
        ExecutionIdentityService,
    )

    identity = await ExecutionIdentityService(session).bootstrap_direct_rag(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
    )
    command = replace(
        make_run_command(
            identity,
            tenant_id=DEFAULT_TENANT_ID,
            conversation_id=conversation.conversation.id,
        ),
        created_by=DEFAULT_ADMIN_ID,
    )
    result = await RunCoordinator(session).create_run(command)
    await session.commit()
    return result.run


async def _append_event(
    session,
    run,
    *,
    summary: str,
    visibility: EventVisibility = EventVisibility.USER,
):
    event = replace(
        make_event(summary=summary, correlation_id=run.correlation_id),
        visibility=visibility,
    )
    persisted = await RunCoordinator(session).append_event(
        tenant_id=run.tenant_id,
        run_id=run.id,
        event=event,
    )
    await session.commit()
    return persisted


def _sse_frames(body: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        if not block or block.startswith(":"):
            continue
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, value = line.split(":", maxsplit=1)
            fields[key] = value.lstrip()
        frames.append(
            {
                "id": int(fields["id"]),
                "event": fields["event"],
                "data": json.loads(fields["data"]),
            }
        )
    return frames


async def test_run_get_and_queued_cancel_are_owner_scoped_and_idempotent(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session)

    detail = await run_client.get(
        f"/api/v1/agent-runs/{run.id}", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "queued"
    assert detail.json()["first_available_event_seq"] == 1
    assert detail.json()["last_event_seq"] == 0

    other_token = await register_and_login(
        run_client,
        username=f"other_a1_{uuid.uuid4().hex[:8]}",
        role="super_admin",
    )
    hidden = await run_client.get(
        f"/api/v1/agent-runs/{run.id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden.status_code == 404

    app.dependency_overrides[get_current_user] = lambda: {
        "tenant_id": uuid.uuid4(),
        "id": DEFAULT_ADMIN_ID,
    }
    try:
        cross_tenant = await run_client.get(f"/api/v1/agent-runs/{run.id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert cross_tenant.status_code == 404

    cancelled, concurrent = await asyncio.gather(
        run_client.post(
            f"/api/v1/agent-runs/{run.id}/cancel",
            headers=auth_headers,
            json={"expected_revision": 1},
        ),
        run_client.post(
            f"/api/v1/agent-runs/{run.id}/cancel",
            headers=auth_headers,
            json={"expected_revision": 1},
        ),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert concurrent.status_code == 200, concurrent.text
    assert cancelled.json()["status"] == "cancelled"
    assert concurrent.json()["status"] == "cancelled"
    assert concurrent.json()["status_revision"] == cancelled.json()["status_revision"]
    assert cancelled.json()["status_revision"] == 2
    assert cancelled.json()["last_event_seq"] == 1

    replay = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": 1},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "cancelled"
    assert replay.json()["status_revision"] == 2
    wrong_replay = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": 999},
    )
    assert wrong_replay.status_code == 409
    assert wrong_replay.json()["detail"]["code"] == "revision_conflict"
    event_count = (
        await db_session.execute(
            select(func.count()).select_from(RunEventModel).where(
                RunEventModel.run_id == run.id
            )
        )
    ).scalar_one()
    assert event_count == 1


async def test_active_run_cancel_records_idempotent_cancelling_intent(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    session_factory,
):
    run = await _create_run(db_session, title="active cancellation")
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    run, _ = await coordinator.start_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_revision=run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="runtime started",
    )
    await db_session.commit()

    first, second = await asyncio.gather(
        run_client.post(
            f"/api/v1/agent-runs/{run.id}/cancel",
            headers=auth_headers,
            json={"expected_revision": run.status_revision},
        ),
        run_client.post(
            f"/api/v1/agent-runs/{run.id}/cancel",
            headers=auth_headers,
            json={"expected_revision": run.status_revision},
        ),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "cancelling"
    assert second.json()["status"] == "cancelling"
    assert first.json()["status_revision"] == second.json()["status_revision"]
    current_revision = first.json()["status_revision"]

    replay = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": run.status_revision},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "cancelling"
    assert replay.json()["status_revision"] == current_revision

    async with session_factory() as session, session.begin():
        terminal, _, _ = await RunCoordinator(session).commit_terminal(
            tenant_id=run.tenant_id,
            run_id=run.id,
            expected_status=RunStatus.CANCELLING,
            expected_revision=current_revision,
            result=TerminalResult(
                outcome="cancelled",
                code="user_cancel_requested",
                reason="Cancellation completed after Runtime acknowledgement",
            ),
        )
    assert terminal.status is RunStatus.CANCELLED

    terminal_replay = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": run.status_revision},
    )
    assert terminal_replay.status_code == 200, terminal_replay.text
    assert terminal_replay.json()["status"] == "cancelled"
    assert terminal_replay.json()["status_revision"] == current_revision + 1


async def test_cancel_losing_to_start_returns_revision_conflict(
    db_session,
    session_factory,
):
    run = await _create_run(db_session, title="cancel start race")
    await db_session.commit()

    # R1-S3-C round-7 commit-17：Guard-first 后 cancel 不会在 resolve 期间被
    # start 抢先（Guard 串行化）。改为先 committed start（separate session），
    # 再用 stale revision cancel -> RunRevisionConflictError。
    stale_revision = run.status_revision
    async with session_factory() as session, session.begin():
        await RunCoordinator(
            session,
            start_barrier=AllowStartBarrier(),
        ).start_run(
            tenant_id=run.tenant_id,
            run_id=run.id,
            expected_revision=stale_revision,
        )

    service = _build_cancel_service(db_session)
    with pytest.raises(RunRevisionConflictError):
        await service.request_cancel(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            expected_revision=stale_revision,
        )
    await db_session.rollback()


@pytest.mark.parametrize("outcome", ["completed", "failed", "expired"])
async def test_cancel_losing_to_terminal_returns_revision_conflict(
    db_session,
    session_factory,
    outcome: str,
):
    run = await _create_run(db_session, title=f"cancel {outcome} race")
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    run, _ = await coordinator.start_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_revision=run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="runtime started",
    )
    await db_session.commit()

    # R1-S3-C round-7 commit-17：先 committed terminal（separate session），
    # 再用 stale revision cancel -> RunRevisionConflictError。
    stale_revision = run.status_revision
    result_kwargs: dict[str, object] = {}
    if outcome == "completed":
        result_kwargs = {
            "output_ref": "artifact:terminal-output",
            "output_digest": "0" * 64,
            "output_size": 1,
            "output_media_type": "text/plain",
            "output_classification": SnapshotClassification.INTERNAL,
            "terminal_message_id": uuid.uuid4(),
        }
    async with session_factory() as session, session.begin():
        await RunCoordinator(session).commit_terminal(
            tenant_id=run.tenant_id,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=stale_revision,
            result=TerminalResult(
                outcome=outcome,
                code=f"concurrent_{outcome}",
                reason="Concurrent terminal transition won the Run lock",
                **result_kwargs,
            ),
        )

    service = _build_cancel_service(db_session)
    with pytest.raises(RunRevisionConflictError):
        await service.request_cancel(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            expected_revision=stale_revision,
        )
    await db_session.rollback()
    await db_session.rollback()


async def test_active_cancel_and_conversation_delete_do_not_deadlock_or_delete_run(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session, title="cancel delete race")
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    run, _ = await coordinator.start_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_revision=run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=run.tenant_id,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="runtime started",
    )
    await db_session.commit()

    cancel, delete_response = await asyncio.wait_for(
        asyncio.gather(
            run_client.post(
                f"/api/v1/agent-runs/{run.id}/cancel",
                headers=auth_headers,
                json={"expected_revision": run.status_revision},
            ),
            run_client.delete(
                "/api/v1/agent-workspace/conversations/"
                f"{run.conversation_id}",
                headers={**auth_headers, "If-Match": "1"},
            ),
        ),
        timeout=5,
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelling"
    assert delete_response.status_code == 409, delete_response.text
    assert delete_response.json()["detail"]["code"] == (
        "conversation_has_non_terminal_run"
    )


async def test_sse_replays_mixed_visibility_without_sequence_gaps(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session, title="mixed visibility")
    await _append_event(db_session, run, summary="visible plan")
    await _append_event(
        db_session,
        run,
        summary="internal operation",
        visibility=EventVisibility.INTERNAL,
    )
    cancelled = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": 1},
    )
    assert cancelled.status_code == 200, cancelled.text

    response = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=0",
        headers={**auth_headers, "Accept": "text/event-stream"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    assert [frame["id"] for frame in frames] == [1, 2, 3]
    assert [frame["event"] for frame in frames] == [
        "plan.summary",
        "event.redacted",
        "run.cancelled",
    ]
    visible = frames[0]["data"]
    assert visible["payload"]["summary"] == "visible plan"
    assert "payload_digest" not in visible
    redacted = frames[1]["data"]
    assert set(redacted) == {
        "schema_version",
        "run_id",
        "seq",
        "reason",
        "delivery_digest",
    }
    assert redacted["reason"] == "not_authorized"
    assert "internal operation" not in response.text

    deterministic_replay = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=0",
        headers=auth_headers,
    )
    assert deterministic_replay.text == response.text

    resumed = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events",
        headers={**auth_headers, "Last-Event-ID": "2"},
    )
    assert [frame["id"] for frame in _sse_frames(resumed.text)] == [3]


async def test_sse_rejects_ambiguous_or_unissued_cursors_and_url_tokens(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session, title="cursor validation")

    conflict = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=0",
        headers={**auth_headers, "Last-Event-ID": "1"},
    )
    assert conflict.status_code == 400
    assert conflict.json()["detail"]["code"] == "event_cursor_conflict"

    duplicate = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=0&after_seq=0",
        headers=auth_headers,
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "event_cursor_conflict"

    invalid = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events",
        headers={**auth_headers, "Last-Event-ID": "-1"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_event_cursor"

    oversized_header = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events",
        headers={**auth_headers, "Last-Event-ID": "9" * 40},
    )
    assert oversized_header.status_code == 400
    assert oversized_header.json()["detail"]["code"] == "invalid_event_cursor"

    oversized_query = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq={2**63}",
        headers=auth_headers,
    )
    assert oversized_query.status_code == 422

    ahead = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=1",
        headers=auth_headers,
    )
    assert ahead.status_code == 409
    assert ahead.json()["detail"]["code"] == "event_cursor_ahead"

    for credential_key in (
        "token",
        "auth_token",
        "id_token",
        "password",
        "session_id",
        "access_key",
        "bearer",
        "foo",
    ):
        url_token = await run_client.get(
            f"/api/v1/agent-runs/{run.id}/events?{credential_key}=secret",
            headers=auth_headers,
        )
        assert url_token.status_code == 400
        assert url_token.json()["detail"]["code"] == "url_token_forbidden"

    duplicate_header = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events",
        headers=[
            ("Authorization", auth_headers["Authorization"]),
            ("Last-Event-ID", "0"),
            ("Last-Event-ID", "1"),
        ],
    )
    assert duplicate_header.status_code == 400
    assert duplicate_header.json()["detail"]["code"] == "event_cursor_conflict"


async def test_sse_returns_explicit_retention_and_internal_gap_errors(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    monkeypatch,
):
    retained_run = await _create_run(db_session, title="retained history")
    await _append_event(db_session, retained_run, summary="retained envelope")
    await db_session.execute(
        update(AgentRunModel)
        .where(AgentRunModel.id == retained_run.id)
        .values(first_available_event_seq=2, event_log_complete=False)
    )
    await db_session.commit()

    expired = await run_client.get(
        f"/api/v1/agent-runs/{retained_run.id}/events?after_seq=0",
        headers=auth_headers,
    )
    assert expired.status_code == 410
    assert expired.json()["detail"] == {
        "code": "event_history_expired",
        "message": "requested event history is no longer available",
        "first_available_event_seq": 2,
        "run_status": "queued",
        "event_log_complete": False,
    }

    gap_run = await _create_run(db_session, title="corrupt gap")
    await _append_event(db_session, gap_run, summary="first")
    second = await _append_event(db_session, gap_run, summary="second")
    current_run = await RunCoordinator(db_session).require_run(
        tenant_id=gap_run.tenant_id,
        run_id=gap_run.id,
    )

    async def _corrupt_window(self, **_kwargs):
        return EventReplayWindow(run=current_run, events=(second,))

    monkeypatch.setattr(
        AgentExecutionQueryRepository,
        "read_event_replay_window",
        _corrupt_window,
    )

    gap = await run_client.get(
        f"/api/v1/agent-runs/{gap_run.id}/events?after_seq=0",
        headers=auth_headers,
    )
    assert gap.status_code == 409
    assert gap.json()["detail"]["code"] == "event_gap_detected"
    assert gap.json()["detail"]["expected_seq"] == 1
    assert gap.json()["detail"]["received_seq"] == 2


async def test_sse_preflight_detects_gap_beyond_first_delivery_batch(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session, title="deep corrupt gap")
    coordinator = RunCoordinator(db_session)
    last_event = None
    for index in range(1, 101):
        last_event = await coordinator.append_event(
            tenant_id=run.tenant_id,
            run_id=run.id,
            event=make_event(
                summary=f"event {index}",
                correlation_id=run.correlation_id,
            ),
        )
    assert last_event is not None
    await db_session.commit()

    content = last_event.content
    db_session.add(
        RunEventModel(
            id=uuid.uuid4(),
            tenant_id=last_event.tenant_id,
            conversation_id=last_event.conversation_id,
            run_id=last_event.run_id,
            seq=102,
            event_type=last_event.event_type.value,
            schema_version=last_event.schema_version,
            occurred_at=last_event.occurred_at,
            persisted_at=last_event.persisted_at,
            visibility=last_event.visibility.value,
            classification=content.classification.value,
            payload_inline=(
                content.payload_inline.model_dump(mode="json")
                if content.payload_inline is not None
                else None
            ),
            payload_ref=content.payload_ref,
            payload_state=content.payload_state.value,
            payload_digest=content.payload_digest,
            payload_size=content.payload_size,
            media_type=content.media_type,
            expires_at=content.expires_at,
            runtime_profile_id=None,
            runtime_binding_id=None,
            runtime_epoch=None,
            runtime_seq=None,
            runtime_event_id=None,
            runtime_event_digest=None,
            correlation_id=last_event.correlation_id,
            causation_id=None,
        )
    )
    await db_session.execute(
        update(AgentRunModel)
        .where(AgentRunModel.id == run.id)
        .values(last_event_seq=102, next_event_seq=103)
    )
    await db_session.commit()

    response = await run_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_seq=0",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "event_gap_detected"
    assert response.json()["detail"]["expected_seq"] == 101
    assert response.json()["detail"]["received_seq"] == 102


async def test_live_tail_polls_without_notification_and_closes_after_access_revocation(
    session_factory,
):
    async with session_factory() as session:
        run = await _create_run(session, title="live handoff")
        await _append_event(session, run, summary="replayed")
        initial = await build_run_query_service(session).read_event_batch(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            after_seq=0,
        )

    stream = _stream_event_frames(
        request=_ConnectedRequest(),
        session_factory=session_factory,
        tenant_id=run.tenant_id,
        actor_id=DEFAULT_ADMIN_ID,
        run_id=run.id,
        initial_batch=initial,
        token_expires_at=2**63,
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=60,
    )
    first_frame = await anext(stream)
    assert b"id: 1" in first_frame

    async with session_factory() as session, session.begin():
        await RunCoordinator(session).append_event(
            tenant_id=run.tenant_id,
            run_id=run.id,
            event=make_event(
                summary="live event",
                correlation_id=run.correlation_id,
            ),
        )
    live_frame = await anext(stream)
    assert b"id: 2" in live_frame
    assert b"live event" in live_frame

    async with session_factory() as session, session.begin():
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == run.conversation_id)
            .values(state=ConversationState.DELETED.value)
        )
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_live_tail_closes_when_account_is_disabled(session_factory):
    async with session_factory() as session:
        run = await _create_run(session, title="account revocation")
        initial = await build_run_query_service(session).read_event_batch(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            after_seq=0,
        )

    stream = _stream_event_frames(
        request=_ConnectedRequest(),
        session_factory=session_factory,
        tenant_id=run.tenant_id,
        actor_id=DEFAULT_ADMIN_ID,
        run_id=run.id,
        initial_batch=initial,
        token_expires_at=2**63,
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=60,
    )
    async with session_factory() as session, session.begin():
        await session.execute(
            update(UserModel)
            .where(UserModel.id == DEFAULT_ADMIN_ID)
            .values(is_active=False)
        )
    try:
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(UserModel)
                .where(UserModel.id == DEFAULT_ADMIN_ID)
                .values(is_active=True)
            )


async def test_live_tail_closes_when_token_expires(session_factory):
    async with session_factory() as session:
        run = await _create_run(session, title="token expiry")
        await _append_event(session, run, summary="before expiry")
        await _append_event(session, run, summary="must not leak after expiry")
        initial = await build_run_query_service(session).read_event_batch(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            after_seq=0,
        )

    now = [100.0]
    stream = _stream_event_frames(
        request=_ConnectedRequest(),
        session_factory=session_factory,
        tenant_id=run.tenant_id,
        actor_id=DEFAULT_ADMIN_ID,
        run_id=run.id,
        initial_batch=initial,
        token_expires_at=101.0,
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=60,
        epoch_seconds=lambda: now[0],
    )
    assert b"id: 1" in await anext(stream)
    now[0] = 101.0
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_sse_heartbeat_is_a_comment_and_does_not_consume_event_seq(
    session_factory,
):
    async with session_factory() as session:
        run = await _create_run(session, title="heartbeat")
        initial = await build_run_query_service(session).read_event_batch(
            tenant_id=run.tenant_id,
            actor_id=DEFAULT_ADMIN_ID,
            run_id=run.id,
            after_seq=0,
        )

    stream = _stream_event_frames(
        request=_ConnectedRequest(),
        session_factory=session_factory,
        tenant_id=run.tenant_id,
        actor_id=DEFAULT_ADMIN_ID,
        run_id=run.id,
        initial_batch=initial,
        token_expires_at=2**63,
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=0,
    )
    assert await anext(stream) == b": heartbeat\n\n"

    async with session_factory() as session, session.begin():
        await RunCoordinator(session).append_event(
            tenant_id=run.tenant_id,
            run_id=run.id,
            event=make_event(
                summary="first canonical event",
                correlation_id=run.correlation_id,
            ),
        )
    event_frame = await anext(stream)
    assert b"id: 1" in event_frame
    await stream.aclose()


async def test_a1_registers_run_routes_without_opening_workspace_submit_turn():
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/agent-runs/{run_id}"]
    assert "post" in paths["/api/v1/agent-runs/{run_id}/cancel"]
    assert "get" in paths["/api/v1/agent-runs/{run_id}/events"]
    assert (
        "/api/v1/agent-workspace/conversations/{conversation_id}/turns"
        not in paths
    )

    stream_route = next(
        route
        for route in agent_execution_router.routes
        if getattr(route, "path", None) == "/api/v1/agent-runs/{run_id}/events"
    )
    auth_dependency = next(
        dependency
        for dependency in stream_route.dependant.dependencies
        if dependency.call is get_stream_current_user
    )
    session_dependency = next(
        dependency
        for dependency in auth_dependency.dependencies
        if dependency.call is get_session_factory
    )
    assert session_dependency.computed_scope is None
    assert all(
        dependency.call is not get_session
        for dependency in auth_dependency.dependencies
    )


async def test_sse_handshake_succeeds_with_a_single_connection_pool(
    run_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
):
    run = await _create_run(db_session, title="single connection handshake")
    cancelled = await run_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel",
        headers=auth_headers,
        json={"expected_revision": 1},
    )
    assert cancelled.status_code == 200, cancelled.text

    engine = create_async_engine(
        TEST_DB_URL,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.25,
    )
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    previous_override = app.dependency_overrides[get_session_factory]
    app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        response = await run_client.get(
            f"/api/v1/agent-runs/{run.id}/events?after_seq=0",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides[get_session_factory] = previous_override
        await engine.dispose()
    assert response.status_code == 200, response.text
    assert [frame["id"] for frame in _sse_frames(response.text)] == [1]


async def test_run_routes_require_normal_authorization(db_session, client: AsyncClient):
    run = await _create_run(db_session, title="authorization required")
    detail = await client.get(f"/api/v1/agent-runs/{run.id}")
    events = await client.get(f"/api/v1/agent-runs/{run.id}/events?token=jwt")
    assert detail.status_code in {401, 403}
    assert events.status_code in {401, 403}
