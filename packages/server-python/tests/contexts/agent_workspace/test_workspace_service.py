from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from app.contexts.agent_workspace.application.command_digest import (
    turn_request_digest,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.cursor import InvalidCursorError
from app.contexts.agent_workspace.application.dto import (
    MessagePartInput,
    TurnCommand,
)
from app.contexts.agent_workspace.domain import (
    ConversationNotFoundError,
    ConversationState,
    IdempotencyConflictError,
    MessageContentState,
    MessagePartType,
    ResourceReferenceForbiddenError,
    RevisionConflictError,
    TitleSourceConflictError,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ConversationUserStateModel,
    MessageModel,
)

pytestmark = pytest.mark.asyncio

TENANT_A = uuid.UUID("10000000-0000-0000-0000-000000000001")
TENANT_B = uuid.UUID("20000000-0000-0000-0000-000000000001")
OWNER_A = uuid.UUID("10000000-0000-0000-0000-000000000002")
OWNER_B = uuid.UUID("10000000-0000-0000-0000-000000000003")
AGENT_VERSION = uuid.UUID("10000000-0000-0000-0000-000000000004")


async def _create(service: AgentWorkspaceService, *, title: str | None = None):
    view, created = await service.create_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        title=title,
    )
    assert created
    return view


def _command(
    client_message_id: uuid.UUID,
    text: str,
    *,
    agent_version: uuid.UUID = AGENT_VERSION,
    options: dict | None = None,
) -> TurnCommand:
    return TurnCommand(
        client_message_id=client_message_id,
        parts=(
            MessagePartInput(
                type=MessagePartType.TEXT,
                text=text,
                format="plain_text",
            ),
        ),
        agent_definition_version_id=agent_version,
        client_options=options or {},
    )


async def test_create_is_idempotent_for_client_conversation_id(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    conversation_id = uuid.uuid4()
    first, first_created = await service.create_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=conversation_id,
        title="Initial",
    )
    second, second_created = await service.create_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=conversation_id,
        title="Initial",
    )
    assert first_created is True
    assert second_created is False
    assert second.conversation.id == first.conversation.id
    assert second.conversation.title == "Initial"
    with pytest.raises(IdempotencyConflictError):
        await service.create_conversation(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=conversation_id,
            title="Different create command",
        )


async def test_tenant_and_owner_are_both_required_for_reads(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(service)
    for tenant_id, actor_id in ((TENANT_B, OWNER_A), (TENANT_A, OWNER_B)):
        with pytest.raises(ConversationNotFoundError):
            await service.get_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=view.conversation.id,
            )


async def test_user_title_and_auto_title_use_revision_cas(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(service)
    auto = await service.apply_auto_title(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        title="Auto title",
        expected_revision=1,
    )
    assert auto.title == "Auto title"
    assert auto.title_source.value == "auto"
    renamed = await service.rename_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        title="\x00  User\n title  ",
        expected_revision=2,
    )
    assert renamed.conversation.title == "User title"
    assert renamed.conversation.title_source.value == "user"
    with pytest.raises(RevisionConflictError):
        await service.rename_conversation(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            title="stale",
            expected_revision=2,
        )
    with pytest.raises(TitleSourceConflictError):
        await service.apply_auto_title(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            title="must not overwrite",
            expected_revision=3,
        )


async def test_pin_is_user_state_and_does_not_mutate_conversation_revision(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(service)
    pinned = await service.set_pinned(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        pinned=True,
    )
    assert pinned.pinned_at is not None
    assert pinned.conversation.revision == 1
    state = (
        await db_session.execute(
            select(ConversationUserStateModel).where(
                ConversationUserStateModel.conversation_id == view.conversation.id
            )
        )
    ).scalar_one()
    assert state.user_id == OWNER_A
    unpinned = await service.set_pinned(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        pinned=False,
    )
    assert unpinned.pinned_at is None
    assert unpinned.conversation.revision == 1


async def test_archive_restore_and_deleted_rows_are_hidden(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(service)
    archived = await service.archive_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        expected_revision=1,
    )
    assert archived.conversation.state is ConversationState.ARCHIVED
    restored = await service.restore_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        expected_revision=2,
    )
    assert restored.conversation.state is ConversationState.ACTIVE

    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == view.conversation.id)
        .values(state="deleted", revision=4)
    )
    await db_session.flush()
    with pytest.raises(ConversationNotFoundError):
        await service.get_conversation(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
        )
    deleted = await service.get_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        include_deleted=True,
    )
    assert deleted.conversation.state is ConversationState.DELETED
    restored_deleted = await service.restore_conversation(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        expected_revision=4,
    )
    assert restored_deleted.conversation.state is ConversationState.ACTIVE


async def test_turn_digest_idempotency_covers_agent_and_options(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(service)
    client_message_id = uuid.uuid4()
    command = _command(
        client_message_id,
        "Select a site",
        options={"response_language": "zh-CN"},
    )
    first = await service.reserve_user_turn(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        command=command,
    )
    replay = await service.reserve_user_turn(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        command=command,
    )
    assert replay.idempotent_replay is True
    assert replay.message.id == first.message.id
    assert replay.message.requested_run_id == first.message.requested_run_id
    assert replay.message.requested_run_queue_seq == first.message.requested_run_queue_seq

    with pytest.raises(IdempotencyConflictError):
        await service.reserve_user_turn(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            command=_command(
                client_message_id,
                "Select a site",
                options={"response_language": "en-US"},
            ),
        )
    with pytest.raises(IdempotencyConflictError):
        await service.reserve_user_turn(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            command=_command(
                client_message_id,
                "Select a site",
                agent_version=uuid.uuid4(),
            ),
        )


async def test_turn_digest_is_order_stable_and_rejects_untyped_floats():
    parts = (
        MessagePartInput(type=MessagePartType.TEXT, text="stable", format="plain_text"),
    )
    common = {
        "tenant_id": TENANT_A,
        "actor_id": OWNER_A,
        "conversation_id": uuid.uuid4(),
        "client_message_id": uuid.uuid4(),
        "parts": parts,
        "agent_definition_version_id": AGENT_VERSION,
    }
    first = turn_request_digest(
        **common,
        client_options={"z": [1, True], "a": {"nested": "value"}},
    )
    second = turn_request_digest(
        **common,
        client_options={"a": {"nested": "value"}, "z": [1, True]},
    )
    assert first == second
    with pytest.raises(ValueError, match="floating-point"):
        turn_request_digest(**common, client_options={"temperature": 0.2})


async def test_resource_references_fail_closed_without_tenant_actor_authorizer(
    db_session,
):
    resource_id = uuid.uuid4()
    base_service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view = await _create(base_service)
    command = TurnCommand(
        client_message_id=uuid.uuid4(),
        parts=(
            MessagePartInput(
                type=MessagePartType.RESOURCE_REF,
                resource_id=resource_id,
            ),
        ),
        agent_definition_version_id=AGENT_VERSION,
    )
    with pytest.raises(ResourceReferenceForbiddenError, match="authorization adapter"):
        await base_service.reserve_user_turn(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            command=command,
        )

    class ResourceAccess:
        def __init__(self, allowed: bool):
            self.allowed = allowed
            self.observed = None

        async def can_reference_resources(self, **kwargs):
            self.observed = kwargs
            return self.allowed

    denied_access = ResourceAccess(False)
    denied_service = AgentWorkspaceService(
        db_session,
        cursor_secret="test-secret",
        resource_access=denied_access,
    )
    with pytest.raises(ResourceReferenceForbiddenError, match="not accessible"):
        await denied_service.reserve_user_turn(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=view.conversation.id,
            command=command,
        )
    assert denied_access.observed == {
        "tenant_id": TENANT_A,
        "actor_id": OWNER_A,
        "resource_ids": (resource_id,),
    }

    allowed_access = ResourceAccess(True)
    allowed_service = AgentWorkspaceService(
        db_session,
        cursor_secret="test-secret",
        resource_access=allowed_access,
    )
    reserved = await allowed_service.reserve_user_turn(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=view.conversation.id,
        command=command,
    )
    assert reserved.message.parts[0].resource_id == resource_id


async def test_history_before_after_and_visible_search(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    target = await _create(service, title="Park planning")
    other = await _create(service, title="Other thread")
    for index, text in enumerate(("alpha", "needle company", "omega"), start=1):
        await service.reserve_user_turn(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            conversation_id=target.conversation.id,
            command=_command(uuid.uuid4(), text),
        )
        assert index > 0
    page = await service.list_messages(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=target.conversation.id,
        before_seq=4,
        limit=2,
    )
    assert [message.seq for message in page.items] == [2, 3]
    assert page.has_more is True
    forward = await service.list_messages(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=target.conversation.id,
        after_seq=1,
        limit=10,
    )
    assert [message.seq for message in forward.items] == [2, 3]

    search = await service.list_conversations(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        query="NEEDLE",
    )
    assert [item.conversation.id for item in search.items] == [target.conversation.id]
    needle_message = (
        await db_session.execute(
            select(MessageModel).where(
                MessageModel.conversation_id == target.conversation.id,
                MessageModel.seq == 2,
            )
        )
    ).scalar_one()
    needle_message.content_state = MessageContentState.REDACTED.value
    await db_session.flush()
    hidden = await service.list_conversations(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        query="needle",
    )
    assert not hidden.items
    title_search = await service.list_conversations(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        query="planning",
    )
    assert [item.conversation.id for item in title_search.items] == [
        target.conversation.id
    ]
    assert other.conversation.id != target.conversation.id


async def test_keyset_cursor_binds_filters_and_excludes_new_rows(db_session):
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    originals = [await _create(service, title=f"Original {index}") for index in range(4)]
    await service.set_pinned(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        conversation_id=originals[0].conversation.id,
        pinned=True,
    )
    first = await service.list_conversations(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        limit=2,
    )
    assert first.next_cursor
    assert first.items[0].conversation.id == originals[0].conversation.id
    created_later = await _create(service, title="Created after issued-at")
    second = await service.list_conversations(
        tenant_id=TENANT_A,
        actor_id=OWNER_A,
        cursor=first.next_cursor,
        limit=2,
    )
    observed = {item.conversation.id for item in (*first.items, *second.items)}
    assert observed == {item.conversation.id for item in originals}
    assert created_later.conversation.id not in observed
    with pytest.raises(InvalidCursorError):
        await service.list_conversations(
            tenant_id=TENANT_A,
            actor_id=OWNER_A,
            query="different",
            cursor=first.next_cursor,
            limit=2,
        )
