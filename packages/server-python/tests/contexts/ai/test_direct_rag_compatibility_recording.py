from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    ConversationExecutionGuard,
)
from app.composition.direct_rag_compatibility import (
    DirectRagCompatibilityAdapter,
    DirectRagRecording,
    PreparedDirectRagTurn,
)
from app.contexts.agent_execution.application.execution_identity_service import (
    ExecutionIdentityService,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RunConflictError,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    AgentRunModel,
    CompatibilityOutputModel,
    RunEventModel,
    RuntimeProfileModel,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.domain import MessagePartType
from app.contexts.agent_workspace.infrastructure.models import MessageModel
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.main import app
from app.shared.infrastructure.database import (
    dispose_advisory_claim_engines,
    get_session_factory,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from app.shared.infrastructure.tenant_context import (
    clear_tenant_context,
    set_tenant_context,
)
from app.shared.schemas.agent_integration import TurnLaunchSpecV1
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio


def _fake_chat_response() -> MagicMock:
    source = EvidenceItem(
        evidence_id="chunk:authorized",
        source_type="chunk",
        file_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        title="Authorized handbook",
        snippet="PRIVATE-SNIPPET-MUST-NOT-BE-RECORDED",
        score=0.91,
        channels=["vector", "keyword"],
    )
    return MagicMock(
        reply="The durable compatibility answer.",
        sources=[source],
        document_sources=[],
        diagnostics={
            "prompt_preview": "RAW-PROMPT-MUST-NOT-BE-RECORDED",
            "packed_blocks": [{"content": "RAW-CONTEXT-MUST-NOT-BE-RECORDED"}],
        },
    )


def _scoped_conversation_id(
    requested_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
    actor_id: uuid.UUID = DEFAULT_ADMIN_ID,
) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"metaedu:direct-rag:{tenant_id}:{actor_id}:{requested_id}",
    )


async def _db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def test_evidence_chat_records_durable_contract_and_replays_without_duplicates(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    client_message_id = uuid.uuid4()
    fake_service = MagicMock()
    fake_service.chat = AsyncMock(return_value=_fake_chat_response())
    request = {
        "message": "Record this Direct RAG request",
        "context_window": 7,
        "conversation_id": str(conversation_id),
        "client_message_id": str(client_message_id),
    }

    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        first = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )
        replay = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["reply"] == "The durable compatibility answer."
    actual_conversation_id = uuid.UUID(first_body["conversation_id"])
    assert actual_conversation_id != conversation_id
    assert first_body["user_message_id"]
    assert first_body["run_id"]
    assert first_body["assistant_message_id"]

    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["reply"] == first_body["reply"]
    assert replay_body["conversation_id"] == first_body["conversation_id"]
    assert replay_body["user_message_id"] == first_body["user_message_id"]
    assert replay_body["run_id"] == first_body["run_id"]
    assert replay_body["assistant_message_id"] == first_body["assistant_message_id"]
    assert replay_body["sources"][0]["evidence_id"] == "chunk:authorized"
    assert replay_body["sources"][0]["snippet"] == ""
    assert replay_body["sources"][0]["content"] == ""
    assert replay_body["sources"][0]["metadata"] == {}
    assert replay_body["document_sources"] == []
    assert replay_body["diagnostics"] == {"compatibility_replay": True}
    fake_service.chat.assert_awaited_once()

    other_tenant_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid.uuid4()),
        "tenant_id": str(other_tenant_id),
        "role": "super_admin",
    }
    set_tenant_context(other_tenant_id)
    try:
        with patch(
            "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
            new=fake_service,
        ):
            cross_tenant = await client.post(
                "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        clear_tenant_context()
    assert cross_tenant.status_code == 200, cross_tenant.text
    assert cross_tenant.json()["conversation_id"] not in {
        str(conversation_id),
        str(actual_conversation_id),
    }
    assert fake_service.chat.await_count == 2

    engine, factory = await _db_session()
    try:
        async with factory() as session:
            run_id = uuid.UUID(first_body["run_id"])
            run = await session.get(AgentRunModel, run_id)
            assert run is not None
            assert run.conversation_id == actual_conversation_id
            assert run.runtime_binding_id is None
            assert run.status == "completed"
            assert run.output_publish_state == "published"
            assert run.terminal_message_id == uuid.UUID(
                first_body["assistant_message_id"]
            )

            definition = await session.get(
                AgentDefinitionVersionModel, run.agent_definition_version_id
            )
            profile = await session.get(RuntimeProfileModel, run.runtime_profile_id)
            assert definition is not None
            assert definition.definition_key == "system.direct_rag"
            assert definition.version == 1
            assert profile is not None
            assert profile.profile_key == "compat.direct_rag.v1"

            messages = list(
                (
                    await session.execute(
                        select(MessageModel)
                        .where(MessageModel.conversation_id == actual_conversation_id)
                        .order_by(MessageModel.seq)
                    )
                ).scalars()
            )
            assert [message.message_kind for message in messages] == [
                "user_input",
                "assistant_output",
            ]
            assert messages[0].client_message_id == client_message_id
            assert messages[0].turn_dispatch_state == "accepted"
            assert messages[1].origin_run_id == run_id

            output_snapshot = (
                await session.execute(
                    select(CompatibilityOutputModel).where(
                        CompatibilityOutputModel.run_id == run_id
                    )
                )
            ).scalar_one()
            serialized_snapshot = json.dumps(
                output_snapshot.response_envelope, ensure_ascii=False
            )
            assert output_snapshot.reply_text == first_body["reply"]
            assert "PRIVATE-SNIPPET-MUST-NOT-BE-RECORDED" not in serialized_snapshot
            assert "RAW-PROMPT-MUST-NOT-BE-RECORDED" not in serialized_snapshot

            events = list(
                (
                    await session.execute(
                        select(RunEventModel)
                        .where(RunEventModel.run_id == run_id)
                        .order_by(RunEventModel.seq)
                    )
                ).scalars()
            )
            assert [event.event_type for event in events] == [
                "run.started",
                "phase.changed",
                "phase.changed",
                "usage.updated",
                "run.completed",
            ]
            serialized_events = json.dumps(
                [event.payload_inline for event in events], ensure_ascii=False
            )
            assert "RAW-PROMPT-MUST-NOT-BE-RECORDED" not in serialized_events
            assert "RAW-CONTEXT-MUST-NOT-BE-RECORDED" not in serialized_events
            assert "PRIVATE-SNIPPET-MUST-NOT-BE-RECORDED" not in serialized_events

        messages_response = await client.get(
            f"/api/v1/agent-workspace/conversations/{actual_conversation_id}/messages",
            headers=auth_headers,
        )
        run_response = await client.get(
            f"/api/v1/agent-runs/{first_body['run_id']}", headers=auth_headers
        )
        app.dependency_overrides[get_session_factory] = lambda: factory
        events_response = await client.get(
            f"/api/v1/agent-runs/{first_body['run_id']}/events?after_seq=0",
            headers={**auth_headers, "Accept": "text/event-stream"},
        )
        assert messages_response.status_code == 200, messages_response.text
        assert len(messages_response.json()["items"]) == 2
        assert run_response.status_code == 200, run_response.text
        assert run_response.json()["status"] == "completed"
        assert events_response.status_code == 200, events_response.text
    finally:
        app.dependency_overrides.pop(get_session_factory, None)
        await engine.dispose()


async def test_evidence_chat_records_sanitized_failed_terminal(
    client: AsyncClient,
    auth_headers: dict,
    caplog,
) -> None:
    conversation_id = uuid.uuid4()
    client_message_id = uuid.uuid4()
    fake_service = MagicMock()
    fake_service.chat = AsyncMock(
        side_effect=RuntimeError("SECRET-PROVIDER-DIAGNOSTIC")
    )

    with (
        patch(
            "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
            new=fake_service,
        ),
    ):
        response = await client.post(
            "/api/v1/ai/chat/evidence",
            headers=auth_headers,
            json={
                "message": "Fail after durable preparation",
                "conversation_id": str(conversation_id),
                "client_message_id": str(client_message_id),
            },
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "direct_rag_execution_failed"
    assert "SECRET-PROVIDER-DIAGNOSTIC" not in response.text
    assert "SECRET-PROVIDER-DIAGNOSTIC" not in caplog.text

    engine, factory = await _db_session()
    try:
        async with factory() as session:
            run = await session.get(
                AgentRunModel, uuid.UUID(response.json()["detail"]["run_id"])
            )
            assert run is not None
            assert run.status == "failed"
            assert run.terminal_code == "direct_rag_execution_failed"
            assert "SECRET-PROVIDER-DIAGNOSTIC" not in (run.terminal_reason or "")
            events = list(
                (
                    await session.execute(
                        select(RunEventModel)
                        .where(RunEventModel.run_id == run.id)
                        .order_by(RunEventModel.seq)
                    )
                ).scalars()
            )
            assert events[-2].event_type == "error.reported"
            assert events[-1].event_type == "run.failed"
            serialized_events = json.dumps(
                [event.payload_inline for event in events], ensure_ascii=False
            )
            assert "SECRET-PROVIDER-DIAGNOSTIC" not in serialized_events
    finally:
        await engine.dispose()


async def test_terminal_output_projection_recovers_after_dispatch_failure(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    request = {
        "message": "Recover a committed terminal output",
        "conversation_id": str(conversation_id),
        "client_message_id": str(uuid.uuid4()),
    }
    fake_service = MagicMock()
    fake_service.chat = AsyncMock(return_value=_fake_chat_response())

    with (
        patch(
            "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
            new=fake_service,
        ),
        patch.object(
            AgentBridgeDispatcher,
            "dispatch_output",
            AsyncMock(side_effect=RuntimeError("projection unavailable")),
        ),
    ):
        failed_delivery = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert failed_delivery.status_code == 503
    assert failed_delivery.json()["detail"]["code"] == "direct_rag_output_pending"

    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        recovered = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert recovered.status_code == 200, recovered.text
    body = recovered.json()
    assert body["reply"] == "The durable compatibility answer."
    assert body["sources"][0]["evidence_id"] == "chunk:authorized"
    assert body["sources"][0]["snippet"] == ""
    assert body["diagnostics"] == {"compatibility_replay": True}
    fake_service.chat.assert_awaited_once()


async def test_turn_dispatch_recovers_from_committed_workspace_outbox(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    request = {
        "message": "Recover a committed workspace turn",
        "conversation_id": str(conversation_id),
        "client_message_id": str(uuid.uuid4()),
    }
    fake_service = MagicMock()
    fake_service.chat = AsyncMock(return_value=_fake_chat_response())

    with (
        patch(
            "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
            new=fake_service,
        ),
        patch.object(
            AgentBridgeDispatcher,
            "dispatch_turn",
            AsyncMock(side_effect=RuntimeError("execution bridge unavailable")),
        ),
    ):
        pending = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert pending.status_code == 503, pending.text
    assert pending.json()["detail"]["code"] == "direct_rag_turn_pending"
    fake_service.chat.assert_not_awaited()

    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        recovered = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["reply"] == "The durable compatibility answer."
    fake_service.chat.assert_awaited_once()


async def test_concurrent_idempotent_requests_return_the_persisted_winner(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    client_message_id = uuid.uuid4()
    first_inside_model = asyncio.Event()
    release_first = asyncio.Event()
    async def chat(*_args, **_kwargs):
        first_inside_model.set()
        await release_first.wait()
        response = _fake_chat_response()
        response.reply = "same concurrent answer"
        response.sources[0].evidence_id = "winner-evidence"
        return response

    fake_service = MagicMock()
    fake_service.chat = AsyncMock(side_effect=chat)
    request = {
        "message": "Concurrent idempotent request",
        "conversation_id": str(conversation_id),
        "client_message_id": str(client_message_id),
    }

    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        first_task = asyncio.create_task(
            client.post(
                "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
            )
        )
        await asyncio.wait_for(first_inside_model.wait(), timeout=5)
        pending = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )
        release_first.set()
        winner = await asyncio.wait_for(first_task, timeout=5)
        replay = await client.post(
            "/api/v1/ai/chat/evidence", headers=auth_headers, json=request
        )

    assert pending.status_code == 503, pending.text
    assert pending.json()["detail"]["code"] == "direct_rag_execution_pending"
    assert winner.status_code == 200, winner.text
    winner_body = winner.json()
    replay_body = replay.json()
    assert winner_body["reply"] == "same concurrent answer"
    assert winner_body["sources"][0]["evidence_id"] == "winner-evidence"
    assert replay_body["reply"] == "same concurrent answer"
    assert replay_body["sources"][0]["evidence_id"] == "winner-evidence"
    assert replay_body["sources"][0]["snippet"] == ""
    assert replay_body["diagnostics"] == {"compatibility_replay": True}
    assert replay_body["run_id"] == winner_body["run_id"]
    assert replay_body["assistant_message_id"] == winner_body["assistant_message_id"]
    fake_service.chat.assert_awaited_once()

    engine, factory = await _db_session()
    try:
        async with factory() as session:
            messages = list(
                (
                    await session.execute(
                        select(MessageModel).where(
                            MessageModel.conversation_id
                            == uuid.UUID(winner_body["conversation_id"])
                        )
                    )
                ).scalars()
            )
            assert len(messages) == 2
            assert sum(message.message_kind == "assistant_output" for message in messages) == 1
    finally:
        await engine.dispose()


async def test_execution_claim_pool_is_isolated_from_request_database_pool() -> None:
    request_engine = create_async_engine(
        TEST_DB_URL,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    factory = async_sessionmaker(
        request_engine, class_=AsyncSession, expire_on_commit=False
    )
    prepared = PreparedDirectRagTurn(
        tenant_id=DEFAULT_TENANT_ID,
        actor_id=DEFAULT_ADMIN_ID,
        recording=DirectRagRecording(
            conversation_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            assistant_message_id=None,
        ),
    )
    try:
        async with factory() as session:
            adapter = DirectRagCompatibilityAdapter(session)
            async with (
                adapter.execution_claim(prepared=prepared),
                request_engine.connect() as connection,
            ):
                assert await connection.scalar(select(1)) == 1
    finally:
        await request_engine.dispose()
        await dispose_advisory_claim_engines()


async def test_direct_rag_compatibility_run_settles_cancel_while_model_runs(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    client_message_id = uuid.uuid4()
    inside_model = asyncio.Event()
    release_model = asyncio.Event()

    async def chat(*_args, **_kwargs):
        inside_model.set()
        await release_model.wait()
        return _fake_chat_response()

    fake_service = MagicMock()
    fake_service.chat = AsyncMock(side_effect=chat)
    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        request_task = asyncio.create_task(
            client.post(
                "/api/v1/ai/chat/evidence",
                headers=auth_headers,
                json={
                    "message": "Do not leave this compatibility Run cancelling",
                    "conversation_id": str(conversation_id),
                    "client_message_id": str(client_message_id),
                },
            )
        )
        await asyncio.wait_for(inside_model.wait(), timeout=5)

        engine, factory = await _db_session()
        try:
            async with factory() as session:
                run = (
                    await session.execute(
                        select(AgentRunModel).where(
                            AgentRunModel.conversation_id
                            == _scoped_conversation_id(conversation_id)
                        )
                    )
                ).scalar_one()
                run_id = run.id
                revision = run.status_revision
        finally:
            await engine.dispose()

        cancel = await client.post(
            f"/api/v1/agent-runs/{run_id}/cancel",
            headers=auth_headers,
            json={"expected_revision": revision},
        )
        release_model.set()
        completed = await asyncio.wait_for(request_task, timeout=5)

    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["terminal_code"] == "direct_rag_cancelled"
    assert completed.status_code == 409, completed.text
    assert completed.json()["detail"]["code"] == "direct_rag_run_not_active"


async def test_cancelled_http_request_persists_sanitized_failed_terminal(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    inside_model = asyncio.Event()
    never_release = asyncio.Event()

    async def chat(*_args, **_kwargs):
        inside_model.set()
        await never_release.wait()
        return _fake_chat_response()

    fake_service = MagicMock()
    fake_service.chat = AsyncMock(side_effect=chat)
    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        request_task = asyncio.create_task(
            client.post(
                "/api/v1/ai/chat/evidence",
                headers=auth_headers,
                json={
                    "message": "Cancel the transport while the model is running",
                    "conversation_id": str(conversation_id),
                    "client_message_id": str(uuid.uuid4()),
                },
            )
        )
        await asyncio.wait_for(inside_model.wait(), timeout=5)
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

    engine, factory = await _db_session()
    try:
        async with factory() as session:
            run = (
                await session.execute(
                    select(AgentRunModel).where(
                        AgentRunModel.conversation_id
                        == _scoped_conversation_id(conversation_id)
                    )
                )
            ).scalar_one()
            assert run.status == "failed"
            assert run.terminal_code == "direct_rag_request_cancelled"
            assert run.terminal_reason == (
                "Legacy Direct RAG execution failed; diagnostics omitted"
            )
    finally:
        await engine.dispose()


async def test_completion_and_next_run_start_follow_guard_first_lock_order(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch,
) -> None:
    conversation_id = uuid.uuid4()
    inside_model = asyncio.Event()
    release_model = asyncio.Event()
    completion_has_run_lock = asyncio.Event()
    release_completion = asyncio.Event()
    successor_has_guard = asyncio.Event()
    original_acquire = ConversationExecutionGuard.acquire
    original_append_event = RunCoordinator.append_event

    async def controlled_acquire(self, session, **kwargs):
        await original_acquire(self, session, **kwargs)
        task = asyncio.current_task()
        assert task is not None
        if task.get_name() == "successor-start":
            successor_has_guard.set()

    async def controlled_append_event(self, **kwargs):
        result = await original_append_event(self, **kwargs)
        task = asyncio.current_task()
        if task is not None and task.get_name() == "direct-rag-completion":
            completion_has_run_lock.set()
            await release_completion.wait()
        return result

    monkeypatch.setattr(ConversationExecutionGuard, "acquire", controlled_acquire)
    monkeypatch.setattr(RunCoordinator, "append_event", controlled_append_event)

    async def chat(*_args, **_kwargs):
        inside_model.set()
        await release_model.wait()
        return _fake_chat_response()

    fake_service = MagicMock()
    fake_service.chat = AsyncMock(side_effect=chat)
    engine, factory = await _db_session()
    try:
        with patch(
            "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
            new=fake_service,
        ):
            first_request = asyncio.create_task(
                client.post(
                    "/api/v1/ai/chat/evidence",
                    headers=auth_headers,
                    json={
                        "message": "First guarded completion",
                        "conversation_id": str(conversation_id),
                        "client_message_id": str(uuid.uuid4()),
                    },
                ),
                name="direct-rag-completion",
            )
            await asyncio.wait_for(inside_model.wait(), timeout=5)

            async with factory() as session, session.begin():
                identity = await ExecutionIdentityService(
                    session
                ).bootstrap_direct_rag(
                    tenant_id=DEFAULT_TENANT_ID,
                    actor_id=DEFAULT_ADMIN_ID,
                )
                budget = RunBudgetSnapshot(
                    max_steps=2,
                    max_wall_seconds=300,
                    max_tokens=100_000,
                    max_cost_micros=2_000_000,
                    max_tool_calls=1,
                    max_retries=0,
                )
                config = RunConfigSnapshot(
                    agent_definition_version_id=identity.agent_definition_version.id,
                    runtime_profile_id=identity.runtime_profile.id,
                    model_profile_key=None,
                    autonomy_level=0,
                    policy_version="compat.direct_rag.v1",
                    tool_keys=(),
                    budget=budget,
                )
                launch = TurnLaunchSpecV1(
                    agent_definition_version_id=identity.agent_definition_version.id,
                    runtime_profile_id=identity.runtime_profile.id,
                    runtime_capability_snapshot=(
                        identity.capability_snapshot.model_dump(mode="json")
                    ),
                    run_config_snapshot=config.model_dump(mode="json"),
                    budget_snapshot=budget.model_dump(mode="json"),
                )
                receipt = await ConversationExecutionCoordinator(session).submit_turn(
                    tenant_id=DEFAULT_TENANT_ID,
                    actor_id=DEFAULT_ADMIN_ID,
                    conversation_id=_scoped_conversation_id(conversation_id),
                    command=TurnCommand(
                        client_message_id=uuid.uuid4(),
                        parts=(
                            MessagePartInput(
                                type=MessagePartType.TEXT,
                                text="Queued successor",
                            ),
                        ),
                        agent_definition_version_id=(
                            identity.agent_definition_version.id
                        ),
                    ),
                    launch=launch,
                )
            queued = await AgentBridgeDispatcher(
                factory, worker_id="d1-lock-order"
            ).dispatch_turn(event_id=receipt.event_id)
            assert queued is not None

            release_model.set()
            await asyncio.wait_for(completion_has_run_lock.wait(), timeout=5)

            async def start_successor():
                async with factory() as session, session.begin():
                    return await ConversationExecutionCoordinator(session).start_run(
                        tenant_id=DEFAULT_TENANT_ID,
                        run_id=queued.id,
                        expected_revision=queued.status_revision,
                    )

            start_task = asyncio.create_task(
                start_successor(), name="successor-start"
            )
            await asyncio.sleep(0.1)
            assert not start_task.done()
            assert not successor_has_guard.is_set()
            release_completion.set()
            with pytest.raises(RunConflictError, match="projection is unresolved"):
                await asyncio.wait_for(start_task, timeout=5)
            assert successor_has_guard.is_set()
            first_response = await asyncio.wait_for(first_request, timeout=5)

            async with factory() as session, session.begin():
                started, _ = await ConversationExecutionCoordinator(session).start_run(
                    tenant_id=DEFAULT_TENANT_ID,
                    run_id=queued.id,
                    expected_revision=queued.status_revision,
                )

        assert first_response.status_code == 200, first_response.text
        assert started.status.value == "starting"
    finally:
        release_model.set()
        release_completion.set()
        await engine.dispose()


async def test_oversized_answer_returns_stable_failure_and_fails_projection(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    conversation_id = uuid.uuid4()
    oversized_reply = "x" * (64 * 1024 + 1)
    response_value = _fake_chat_response()
    response_value.reply = oversized_reply
    fake_service = MagicMock()
    fake_service.chat = AsyncMock(return_value=response_value)

    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        response = await client.post(
            "/api/v1/ai/chat/evidence",
            headers=auth_headers,
            json={
                "message": "Return an oversized answer",
                "conversation_id": str(conversation_id),
                "client_message_id": str(uuid.uuid4()),
            },
        )

    assert response.status_code == 502
    body = response.json()["detail"]
    assert body["code"] == "direct_rag_output_too_large"
    assert oversized_reply not in response.text

    engine, factory = await _db_session()
    try:
        async with factory() as session:
            run = await session.get(AgentRunModel, uuid.UUID(body["run_id"]))
            assert run is not None
            assert run.status == "failed"
            assert run.terminal_code == "direct_rag_output_too_large"
            assistant_count = await session.scalar(
                select(func.count())
                .select_from(MessageModel)
                .where(
                    MessageModel.conversation_id
                    == _scoped_conversation_id(conversation_id),
                    MessageModel.message_kind == "assistant_output",
                )
            )
            assert assistant_count == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "body",
    [
        {"message": "missing client id", "conversation_id": str(uuid.uuid4())},
        {"message": "missing conversation id", "client_message_id": str(uuid.uuid4())},
        {"message": ""},
        {"message": "contains\x00nul"},
        {"message": "汉" * 21846},
    ],
)
async def test_evidence_chat_requires_complete_optional_idempotency_pair(
    client: AsyncClient,
    auth_headers: dict,
    body: dict,
) -> None:
    response = await client.post(
        "/api/v1/ai/chat/evidence", headers=auth_headers, json=body
    )
    assert response.status_code == 422
