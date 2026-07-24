from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Annotated, NoReturn, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.agent_run_access import build_run_query_service
from app.contexts.agent_execution.application.dto import EventReplayBatch
from app.contexts.agent_execution.domain import (
    AgentExecutionError,
    AgentRun,
    EventCursorAheadError,
    EventGapDetectedError,
    EventHistoryExpiredError,
    InvalidRunTransitionError,
    RunConflictError,
    RunEvent,
    RunNotFoundError,
    RunRevisionConflictError,
)
from app.contexts.identity.interfaces.api.dependencies import (
    get_current_user,
    get_stream_current_user,
)
from app.shared.infrastructure.database import get_session, get_session_factory
from app.shared.schemas.canonical_json import canonical_digest, canonical_json_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-runs"])

_POLL_INTERVAL_SECONDS = 1.0
_HEARTBEAT_INTERVAL_SECONDS = 15.0
_MAX_EVENT_SEQ = 2**63 - 1


class _DisconnectProbe(Protocol):
    async def is_disconnected(self) -> bool: ...


class CancelRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class RunDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    conversation_id: uuid.UUID
    queue_seq: int
    root_input_message_id: uuid.UUID
    parent_run_id: uuid.UUID | None
    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_binding_id: uuid.UUID | None
    status: str
    status_revision: int
    first_available_event_seq: int
    last_event_seq: int
    event_log_complete: bool
    queued_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    terminal_code: str | None
    terminal_reason: str | None
    terminal_result_digest: str | None
    terminal_output_digest: str | None
    terminal_output_size: int | None
    terminal_output_media_type: str | None
    terminal_output_classification: str | None
    terminal_message_id: uuid.UUID | None
    output_publish_state: str
    usage: dict[str, int]
    pending_input_request_count: int
    pending_approval_count: int
    created_at: datetime
    updated_at: datetime


def _identity(current_user: dict) -> tuple[uuid.UUID, uuid.UUID]:
    return (
        uuid.UUID(str(current_user["tenant_id"])),
        uuid.UUID(str(current_user["id"])),
    )


def _run_dto(run: AgentRun) -> RunDTO:
    return RunDTO(
        id=run.id,
        conversation_id=run.conversation_id,
        queue_seq=run.queue_seq,
        root_input_message_id=run.root_input_message_id,
        parent_run_id=run.parent_run_id,
        agent_definition_version_id=run.agent_definition_version_id,
        runtime_profile_id=run.runtime_profile_id,
        runtime_binding_id=run.runtime_binding_id,
        status=run.status.value,
        status_revision=run.status_revision,
        first_available_event_seq=run.first_available_event_seq,
        last_event_seq=run.last_event_seq,
        event_log_complete=run.event_log_complete,
        queued_at=run.queued_at,
        started_at=run.started_at,
        ended_at=run.ended_at,
        terminal_code=run.terminal_code,
        terminal_reason=run.terminal_reason,
        terminal_result_digest=run.terminal_result_digest,
        terminal_output_digest=run.terminal_output_digest,
        terminal_output_size=run.terminal_output_size,
        terminal_output_media_type=run.terminal_output_media_type,
        terminal_output_classification=(
            run.terminal_output_classification.value
            if run.terminal_output_classification is not None
            else None
        ),
        terminal_message_id=run.terminal_message_id,
        output_publish_state=run.output_publish_state.value,
        usage=run.usage_summary.model_dump(mode="json"),
        pending_input_request_count=0,
        pending_approval_count=0,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _error_detail(code: str, message: str, **context: object) -> dict[str, object]:
    return {"code": code, "message": message, **context}


def _raise_execution_error(exc: Exception) -> NoReturn:
    if isinstance(exc, RunNotFoundError):
        raise HTTPException(
            status_code=404,
            detail=_error_detail("not_found", str(exc)),
        ) from exc
    if isinstance(exc, EventHistoryExpiredError):
        raise HTTPException(
            status_code=410,
            detail=_error_detail(
                "event_history_expired",
                str(exc),
                first_available_event_seq=exc.first_available_event_seq,
                run_status=exc.run_status,
                event_log_complete=exc.event_log_complete,
            ),
        ) from exc
    if isinstance(exc, EventCursorAheadError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "event_cursor_ahead",
                str(exc),
                after_seq=exc.after_seq,
                last_event_seq=exc.last_event_seq,
            ),
        ) from exc
    if isinstance(exc, EventGapDetectedError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail(
                "event_gap_detected",
                str(exc),
                expected_seq=exc.expected_seq,
                received_seq=exc.received_seq,
            ),
        ) from exc
    if isinstance(exc, RunRevisionConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("revision_conflict", str(exc)),
        ) from exc
    if isinstance(exc, InvalidRunTransitionError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("invalid_state_transition", str(exc)),
        ) from exc
    if isinstance(exc, RunConflictError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("run_conflict", str(exc)),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=422,
            detail=_error_detail("validation_error", str(exc)),
        ) from exc
    if isinstance(exc, AgentExecutionError):
        raise HTTPException(
            status_code=409,
            detail=_error_detail("execution_conflict", str(exc)),
        ) from exc
    raise exc


def _resolve_after_seq(after_seq: int | None, last_event_id: str | None) -> int:
    header_cursor: int | None = None
    if last_event_id is not None:
        value = last_event_id.strip()
        if (
            not value
            or len(value) > 19
            or not value.isascii()
            or not value.isdecimal()
            or int(value) > _MAX_EVENT_SEQ
        ):
            raise HTTPException(
                status_code=400,
                detail=_error_detail(
                    "invalid_event_cursor",
                    "Last-Event-ID must be a non-negative integer",
                ),
            )
        header_cursor = int(value)
    if after_seq is not None and header_cursor is not None and after_seq != header_cursor:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "event_cursor_conflict",
                "after_seq and Last-Event-ID must match",
            ),
        )
    return after_seq if after_seq is not None else (header_cursor or 0)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _event_delivery(
    event: RunEvent,
    *,
    batch: EventReplayBatch,
) -> tuple[str, dict[str, object]]:
    if event.visibility in batch.access.visible_event_scopes:
        event_name = event.event_type.value
        data: dict[str, object] = {
            "schema_version": 1,
            "run_id": str(event.run_id),
            "seq": event.seq,
            "event_type": event.event_type.value,
            "occurred_at": _rfc3339(event.occurred_at),
            "payload_state": event.content.payload_state.value,
            "payload": (
                event.content.payload_inline.model_dump(mode="json")
                if event.content.payload_inline is not None
                else None
            ),
        }
    else:
        event_name = "event.redacted"
        data = {
            "schema_version": 1,
            "run_id": str(event.run_id),
            "seq": event.seq,
            "reason": "not_authorized",
        }
    data["delivery_digest"] = canonical_digest(
        {
            "audience": batch.access.audience_key,
            "delivery": data,
            "event_id": str(event.id),
            "source_payload_digest": event.content.payload_digest,
        }
    )
    return event_name, data


def _sse_frame(event: RunEvent, *, batch: EventReplayBatch) -> bytes:
    event_name, data = _event_delivery(event, batch=batch)
    return (
        f"id: {event.seq}\nevent: {event_name}\ndata: ".encode()
        + canonical_json_bytes(data)
        + b"\n\n"
    )


async def _read_event_batch(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    run_id: uuid.UUID,
    after_seq: int,
    validate_full_range: bool = False,
) -> EventReplayBatch:
    async with session_factory() as session:
        return await build_run_query_service(session).read_event_batch(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
            after_seq=after_seq,
            validate_full_range=validate_full_range,
        )


async def _stream_event_frames(
    *,
    request: _DisconnectProbe,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    run_id: uuid.UUID,
    initial_batch: EventReplayBatch,
    token_expires_at: float,
    poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    heartbeat_interval_seconds: float = _HEARTBEAT_INTERVAL_SECONDS,
    epoch_seconds: Callable[[], float] = time.time,
) -> AsyncIterator[bytes]:
    batch = initial_batch
    cursor = initial_batch.after_seq
    loop = asyncio.get_running_loop()
    last_heartbeat = loop.time()
    while True:
        if epoch_seconds() >= token_expires_at:
            return
        for event in batch.events:
            if epoch_seconds() >= token_expires_at:
                return
            cursor = event.seq
            yield _sse_frame(event, batch=batch)
        if batch.run.is_terminal and cursor >= batch.run.last_event_seq:
            return
        if await request.is_disconnected():
            return
        if cursor >= batch.run.last_event_seq:
            await asyncio.sleep(poll_interval_seconds)
        if await request.is_disconnected():
            return
        try:
            batch = await _read_event_batch(
                session_factory=session_factory,
                tenant_id=tenant_id,
                actor_id=actor_id,
                run_id=run_id,
                after_seq=cursor,
            )
        except RunNotFoundError:
            return
        except AgentExecutionError:
            logger.exception("Agent Run SSE closed after a durable replay error")
            return
        if not batch.events and loop.time() - last_heartbeat >= heartbeat_interval_seconds:
            last_heartbeat = loop.time()
            yield b": heartbeat\n\n"


@router.get("/{run_id}", response_model=RunDTO)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
) -> RunDTO:
    tenant_id, actor_id = _identity(current_user)
    try:
        run = await build_run_query_service(session).get_run(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
        )
    except Exception as exc:
        _raise_execution_error(exc)
    return _run_dto(run)


@router.post("/{run_id}/cancel", response_model=RunDTO)
async def cancel_run(
    run_id: uuid.UUID,
    command: CancelRunRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
) -> RunDTO:
    tenant_id, actor_id = _identity(current_user)
    try:
        run = await build_run_query_service(session).request_cancel(
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
            expected_revision=command.expected_revision,
        )
        await session.commit()
    except Exception as exc:
        _raise_execution_error(exc)
    return _run_dto(run)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    after_seq: Annotated[int | None, Query(ge=0, le=_MAX_EVENT_SEQ)] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    current_user: dict = Depends(get_stream_current_user),  # noqa: B008
    session_factory: async_sessionmaker[AsyncSession] = Depends(  # noqa: B008
        get_session_factory
    ),
) -> StreamingResponse:
    if any(key != "after_seq" for key in request.query_params):
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "url_token_forbidden",
                "credentials are not accepted in the event stream URL",
            ),
        )
    if len(request.headers.getlist("last-event-id")) > 1:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "event_cursor_conflict",
                "Last-Event-ID must be supplied at most once",
            ),
        )
    if len(request.query_params.getlist("after_seq")) > 1:
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                "event_cursor_conflict",
                "after_seq must be supplied at most once",
            ),
        )
    cursor = _resolve_after_seq(after_seq, last_event_id)
    tenant_id, actor_id = _identity(current_user)
    token_expires_at = current_user.get("_token_expires_at")
    if not isinstance(token_expires_at, int | float):
        raise HTTPException(
            status_code=401,
            detail=_error_detail(
                "invalid_token_expiry",
                "the event stream requires a token expiry",
            ),
        )
    try:
        initial_batch = await _read_event_batch(
            session_factory=session_factory,
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
            after_seq=cursor,
            validate_full_range=True,
        )
    except Exception as exc:
        _raise_execution_error(exc)
    return StreamingResponse(
        _stream_event_frames(
            request=request,
            session_factory=session_factory,
            tenant_id=tenant_id,
            actor_id=actor_id,
            run_id=run_id,
            initial_batch=initial_batch,
            token_expires_at=float(token_expires_at),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
