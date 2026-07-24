from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.cursor import InvalidCursorError
from app.contexts.agent_workspace.application.dto import ConversationView
from app.contexts.agent_workspace.domain import (
    AgentWorkspaceError,
    ConversationIdConflictError,
    ConversationNotFoundError,
    ConversationPurgedError,
    ConversationState,
    IdempotencyConflictError,
    InvalidConversationStateError,
    Message,
    MessagePart,
    ResourceReferenceForbiddenError,
    RevisionConflictError,
    TitleSourceConflictError,
)
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session

router = APIRouter(
    prefix="/api/v1/agent-workspace/conversations",
    tags=["agent-workspace"],
)


class ConversationCreateRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=400)


class ConversationRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=400)


class ConversationDTO(BaseModel):
    id: uuid.UUID
    title: str | None
    title_source: str
    state: str
    parent_conversation_id: uuid.UUID | None
    forked_from_message_id: uuid.UUID | None
    last_activity_at: datetime
    pinned_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationDTO]
    next_cursor: str | None


class MessagePartDTO(BaseModel):
    id: uuid.UUID
    part_seq: int
    type: str
    text: str | None
    format: str | None
    resource_id: uuid.UUID | None
    media_type: str | None
    display_name: str | None
    classification: str


class MessageDTO(BaseModel):
    id: uuid.UUID
    seq: int
    kind: str
    author_type: str
    author_id: uuid.UUID | None
    requested_run_id: uuid.UUID | None
    requested_run_queue_seq: int | None
    dispatch_state: str | None
    origin_run_id: uuid.UUID | None
    output_ordinal: int | None
    reply_to_message_id: uuid.UUID | None
    content_state: str
    created_at: datetime
    parts: list[MessagePartDTO]


class MessageListResponse(BaseModel):
    items: list[MessageDTO]
    has_more: bool


def _service(session: AsyncSession) -> AgentWorkspaceService:
    return AgentWorkspaceService(session)


def _identity(current_user: dict) -> tuple[uuid.UUID, uuid.UUID]:
    return (
        uuid.UUID(str(current_user["tenant_id"])),
        uuid.UUID(str(current_user["id"])),
    )


def _conversation_dto(view: ConversationView) -> ConversationDTO:
    item = view.conversation
    return ConversationDTO(
        id=item.id,
        title=item.title,
        title_source=item.title_source.value,
        state=item.state.value,
        parent_conversation_id=item.parent_conversation_id,
        forked_from_message_id=item.forked_from_message_id,
        last_activity_at=item.last_activity_at,
        pinned_at=view.pinned_at,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _part_dto(part: MessagePart) -> MessagePartDTO:
    return MessagePartDTO(
        id=part.id,
        part_seq=part.part_seq,
        type=part.part_type.value,
        text=part.text_content,
        format=part.content_format,
        resource_id=part.resource_id,
        media_type=part.media_type,
        display_name=part.display_name,
        classification=part.classification.value,
    )


def _message_dto(message: Message) -> MessageDTO:
    return MessageDTO(
        id=message.id,
        seq=message.seq,
        kind=message.message_kind.value,
        author_type=message.author_type.value,
        author_id=message.author_id,
        requested_run_id=message.requested_run_id,
        requested_run_queue_seq=message.requested_run_queue_seq,
        dispatch_state=(
            message.turn_dispatch_state.value if message.turn_dispatch_state else None
        ),
        origin_run_id=message.origin_run_id,
        output_ordinal=message.output_ordinal,
        reply_to_message_id=message.reply_to_message_id,
        content_state=message.content_state.value,
        created_at=message.created_at,
        parts=[_part_dto(part) for part in message.parts],
    )


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _raise_workspace_error(exc: Exception) -> NoReturn:
    if isinstance(exc, ConversationNotFoundError):
        raise HTTPException(
            status_code=404, detail=_error_detail("not_found", str(exc))
        ) from exc
    if isinstance(exc, RevisionConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("revision_conflict", str(exc)),
        ) from exc
    if isinstance(exc, ResourceReferenceForbiddenError):
        raise HTTPException(
            status_code=403,
            detail=_error_detail("resource_reference_forbidden", str(exc)),
        ) from exc
    if isinstance(exc, IdempotencyConflictError | ConversationIdConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("idempotency_conflict", str(exc)),
        ) from exc
    if isinstance(exc, ConversationPurgedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_purged", str(exc)),
        ) from exc
    if isinstance(exc, TitleSourceConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("title_source_conflict", str(exc)),
        ) from exc
    if isinstance(exc, InvalidConversationStateError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("invalid_state_transition", str(exc)),
        ) from exc
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=400,
            detail=_error_detail("invalid_cursor", str(exc)),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", str(exc)),
        ) from exc
    if isinstance(exc, AgentWorkspaceError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("workspace_conflict", str(exc)),
        ) from exc
    raise exc


def _expected_revision(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=_error_detail("revision_required", "If-Match is required"),
        )
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    value = value.strip('"')
    try:
        revision = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_error_detail("invalid_revision", "If-Match must be an integer"),
        ) from exc
    if revision < 1:
        raise HTTPException(
            status_code=400,
            detail=_error_detail("invalid_revision", "If-Match must be positive"),
        )
    return revision


@router.post("", response_model=ConversationDTO, status_code=201)
async def create_conversation(
    request: ConversationCreateRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view, created = await _service(session).create_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=request.conversation_id,
            title=request.title,
        )
        await session.commit()
    except Exception as exc:
        _raise_workspace_error(exc)
    response.status_code = 201 if created else 200
    return _conversation_dto(view)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    state_filter: Annotated[ConversationState, Query(alias="state")] = (
        ConversationState.ACTIVE
    ),
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        page = await _service(session).list_conversations(
            tenant_id=tenant_id,
            actor_id=actor_id,
            state=state_filter,
            query=q,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _raise_workspace_error(exc)
    return ConversationListResponse(
        items=[_conversation_dto(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{conversation_id}", response_model=ConversationDTO)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.patch("/{conversation_id}", response_model=ConversationDTO)
async def rename_conversation(
    conversation_id: uuid.UUID,
    request: ConversationRenameRequest,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).rename_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            title=request.title,
            expected_revision=_expected_revision(if_match),
        )
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.put("/{conversation_id}/pin", response_model=ConversationDTO)
async def pin_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).set_pinned(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            pinned=True,
        )
        await session.commit()
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.delete("/{conversation_id}/pin", response_model=ConversationDTO)
async def unpin_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).set_pinned(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            pinned=False,
        )
        await session.commit()
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.post("/{conversation_id}/archive", response_model=ConversationDTO)
async def archive_conversation(
    conversation_id: uuid.UUID,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).archive_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=_expected_revision(if_match),
        )
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.post("/{conversation_id}/restore", response_model=ConversationDTO)
async def restore_conversation(
    conversation_id: uuid.UUID,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        view = await _service(session).restore_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=_expected_revision(if_match),
        )
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: uuid.UUID,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        page = await _service(session).list_messages(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            before_seq=before_seq,
            after_seq=after_seq,
            limit=limit,
        )
    except Exception as exc:
        _raise_workspace_error(exc)
    return MessageListResponse(
        items=[_message_dto(item) for item in page.items],
        has_more=page.has_more,
    )
