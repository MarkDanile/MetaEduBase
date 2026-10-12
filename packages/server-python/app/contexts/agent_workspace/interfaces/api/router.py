from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_control_plane import (
    ConversationExecutionCoordinator,
    ConversationHasNonTerminalRunError,
    ConversationHasPendingTurnError,
    ExecutionPortUnavailableError,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.cursor import InvalidCursorError
from app.contexts.agent_workspace.application.dto import (
    ConversationView,
    MessagePartInput,
    TurnCommand,
)
from app.contexts.agent_workspace.application.v1_launch_policy import (
    V1CompatibilityLaunchPolicy,
)
from app.contexts.agent_workspace.domain import (
    AgentDefinitionNotFoundError,
    AgentWorkspaceError,
    CapabilityDeniedError,
    ContentClassification,
    ConversationIdConflictError,
    ConversationNotFoundError,
    ConversationPurgedError,
    ConversationPurgeInProgressError,
    ConversationRecoveryExpiredError,
    ConversationRestoreNotAllowedError,
    ConversationState,
    DeletedConversationListingError,
    IdempotencyConflictError,
    InvalidConversationStateError,
    LateBodyWriteRejectedError,
    LaunchPolicyInternalError,
    Message,
    MessagePart,
    MessagePartType,
    ResourceReferenceForbiddenError,
    RevisionConflictError,
    TitleSourceConflictError,
)
from app.contexts.agent_workspace.interfaces.api.submit_turn_rate_limit import (
    submit_turn_rate_limiter,
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


# ---------------------------------------------------------------------------
# WS-S2 phase-A 公共 submit turn 契约（phase-A §1/§3/§4/§7，PR #642 冻结）
# ---------------------------------------------------------------------------


class SubmitTurnPartRequest(BaseModel):
    """客户端可提交的单个消息片段（对齐内部 ``MessagePartInput``）。"""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, max_length=50)
    text: str | None = Field(default=None, max_length=200_000)
    format: str | None = Field(default=None, max_length=100)
    resource_id: uuid.UUID | None = None
    media_type: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=400)
    classification: str = Field(default="internal", max_length=50)


class SubmitTurnRequest(BaseModel):
    """phase-A §3：仅这四个字段可由客户端提供。

    ``model_config`` 用 ``extra="forbid"``：phase-A §4 的 server-selected 字段
    （``tenant_id`` / ``actor_id`` / ``runtime_profile_id`` / ``runtime_binding_id``
    / ``runtime_capability_snapshot`` / ``run_config_snapshot`` / ``context_snapshot_*``
    / ``budget_snapshot`` / ``parent_run_id`` / message seq / run_queue_seq）与任何
    未知顶层字段都由 schema 层直接拒绝为 ``422 validation_error``。
    """

    model_config = ConfigDict(extra="forbid")

    client_message_id: uuid.UUID
    parts: list[SubmitTurnPartRequest] = Field(..., min_length=1, max_length=100)
    agent_definition_version_id: uuid.UUID
    client_options: dict[str, Any] = Field(default_factory=dict)


class SubmitTurnResponse(BaseModel):
    """phase-A §7：receipt 的公共字段。不暴露 outbox event_id、digest 或任何
    server-selected launch 字段。"""

    message_id: uuid.UUID
    message_seq: int
    run_id: uuid.UUID
    run_queue_seq: int
    dispatch_state: str
    idempotent_replay: bool
    correlation_id: uuid.UUID
    created_at: datetime


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
    if isinstance(exc, ConversationHasPendingTurnError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_has_pending_turn", str(exc)),
        ) from exc
    if isinstance(exc, ConversationHasNonTerminalRunError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_has_non_terminal_run", str(exc)),
        ) from exc
    if isinstance(exc, ExecutionPortUnavailableError):
        raise HTTPException(
            status_code=503,
            detail=_error_detail("execution_unavailable", str(exc)),
        ) from exc
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
    if isinstance(exc, ConversationRecoveryExpiredError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_recovery_expired", str(exc)),
        ) from exc
    if isinstance(exc, ConversationPurgeInProgressError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_purge_in_progress", str(exc)),
        ) from exc
    if isinstance(exc, ConversationPurgedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_purged", str(exc)),
        ) from exc
    if isinstance(exc, ConversationRestoreNotAllowedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_restore_not_allowed", str(exc)),
        ) from exc
    if isinstance(exc, LateBodyWriteRejectedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("late_body_write_rejected", str(exc)),
        ) from exc
    if isinstance(exc, DeletedConversationListingError):
        # deleted/purged fail-closed：公开 list/search 不接受 deleted 状态。
        # 410 Gone 表达「该视图永久不可用」，不泄露任何 deleted 会话存在性/内容。
        raise HTTPException(
            status_code=410,
            detail=_error_detail("deleted_conversation_listing", str(exc)),
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
        await ConversationExecutionCoordinator(session).restore_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=_expected_revision(if_match),
        )
        view = await _service(session).get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _raise_workspace_error(exc)
    return _conversation_dto(view)


@router.delete("/{conversation_id}", response_model=ConversationDTO, status_code=202)
async def delete_conversation(
    conversation_id: uuid.UUID,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tenant_id, actor_id = _identity(current_user)
    try:
        await ConversationExecutionCoordinator(session).delete_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=_expected_revision(if_match),
        )
        view = await _service(session).get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            include_deleted=True,
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


def _submit_turn_part_input(part: SubmitTurnPartRequest) -> MessagePartInput:
    return MessagePartInput(
        type=MessagePartType(part.type),
        text=part.text,
        format=part.format,
        resource_id=part.resource_id,
        media_type=part.media_type,
        display_name=part.display_name,
        classification=ContentClassification(part.classification),
    )


def _raise_submit_turn_error(exc: Exception) -> NoReturn:
    """phase-A §10 错误表到 HTTP 的映射（submit-turn 专属命名空间）。

    与既有 ``_raise_workspace_error`` 分开是刻意的：phase-A §6 冻结 submit-turn
    的 ``409`` 命名空间只含 ``idempotency_conflict`` 与 ``conversation_not_active``，
    而会话元数据端点仍沿用 ``invalid_state_transition``。共用一张映射表会改动
    既有端点的对外错误码，属破坏性契约变更，故不合并。
    """
    if isinstance(exc, AgentDefinitionNotFoundError):
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", str(exc)),
        ) from exc
    if isinstance(exc, CapabilityDeniedError):
        raise HTTPException(
            status_code=403,
            detail=_error_detail("capability_denied", str(exc)),
        ) from exc
    if isinstance(exc, ResourceReferenceForbiddenError):
        raise HTTPException(
            status_code=403,
            detail=_error_detail("resource_access_denied", str(exc)),
        ) from exc
    if isinstance(exc, LaunchPolicyInternalError):
        raise HTTPException(
            status_code=500,
            detail=_error_detail("internal_error", str(exc)),
        ) from exc
    if isinstance(exc, IdempotencyConflictError | ConversationIdConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("idempotency_conflict", str(exc)),
        ) from exc
    if isinstance(exc, InvalidConversationStateError):
        # archived 会话：phase-A §2 要求 conversation_not_active（先 restore 再提交）。
        # deleted 会话在 repository 层以 include_deleted=False 取行，已落到 404 分支。
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_not_active", str(exc)),
        ) from exc
    if isinstance(exc, ConversationNotFoundError):
        # 不存在 / 非 owner / 已删除三者统一 404，反枚举（phase-A §10）。
        raise HTTPException(
            status_code=404,
            detail=_error_detail("conversation_not_found", str(exc)),
        ) from exc
    if isinstance(exc, LateBodyWriteRejectedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("late_body_write_rejected", str(exc)),
        ) from exc
    if isinstance(exc, ConversationHasPendingTurnError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_has_pending_turn", str(exc)),
        ) from exc
    if isinstance(exc, ConversationHasNonTerminalRunError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("conversation_has_non_terminal_run", str(exc)),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", str(exc)),
        ) from exc
    # phase-A §10 最终兜底：未列举异常必须仍返回稳定 code `internal_error`，
    # 否则客户端按 detail.code 分流时该路径拿不到 code。用 `from exc` 保留
    # 异常链，服务端日志仍可拿到原始异常用于诊断。
    raise HTTPException(
        status_code=500,
        detail=_error_detail("internal_error", "unexpected submit-turn failure"),
    ) from exc


@router.post(
    "/{conversation_id}/turns",
    response_model=SubmitTurnResponse,
    status_code=201,
)
async def submit_turn(
    conversation_id: uuid.UUID,
    response: Response,
    payload: dict[str, Any] = Body(..., embed=False),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """WS-S2 phase-A 公共提交端点。

    phase-A §6：submit-turn **不接受** ``If-Match`` / expected revision；无关的
    Conversation revision 变化（auto title、rename 等）不得让正常发送失败。

    本函数只做 phase-A §1 冻结的 router 职责：认证上下文、DTO 解析、调用
    application/composition 层、异常到错误码映射、响应映射。launch 构造、
    capability gate 与 durable 写入都在下层。
    """
    tenant_id, actor_id = _identity(current_user)

    # phase-A §10：per-actor / per-tenant 提交限流，带 Retry-After。
    decision = submit_turn_rate_limiter.acquire(tenant_id=tenant_id, actor_id=actor_id)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=_error_detail(
                "rate_limited", "submit rate limit exceeded for this actor"
            ),
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    # 严格 schema：未知顶层字段与 server-selected 字段一律 422（fail-closed）。
    try:
        request_model = SubmitTurnRequest.model_validate(payload)
        parts = tuple(_submit_turn_part_input(part) for part in request_model.parts)
        command = TurnCommand(
            client_message_id=request_model.client_message_id,
            parts=parts,
            agent_definition_version_id=request_model.agent_definition_version_id,
            client_options=request_model.client_options,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", _validation_message(exc)),
        ) from exc

    try:
        launch = await V1CompatibilityLaunchPolicy(session).build_launch(
            tenant_id=tenant_id,
            agent_definition_version_id=request_model.agent_definition_version_id,
        )
        receipt = await ConversationExecutionCoordinator(session).submit_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=command,
            launch=launch,
        )
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await session.rollback()
        _raise_submit_turn_error(exc)

    message = receipt.reserved.message
    assert message.requested_run_id is not None
    assert message.requested_run_queue_seq is not None
    # phase-A §1：首次接受 201；幂等重放 200 + idempotent_replay=true。
    if receipt.reserved.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return SubmitTurnResponse(
        message_id=message.id,
        message_seq=message.seq,
        run_id=message.requested_run_id,
        run_queue_seq=message.requested_run_queue_seq,
        dispatch_state=receipt.dispatch_state.value,
        idempotent_replay=receipt.reserved.idempotent_replay,
        correlation_id=receipt.correlation_id,
        created_at=message.created_at,
    )


def _validation_message(exc: Exception) -> str:
    """把 pydantic 校验错误压成稳定可读的 message（客户端只依赖 code）。"""
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()))
            parts.append(f"{location}: {error.get('msg', 'invalid')}" if location
                         else str(error.get("msg", "invalid")))
        return "; ".join(parts) or "request validation failed"
    return str(exc)
