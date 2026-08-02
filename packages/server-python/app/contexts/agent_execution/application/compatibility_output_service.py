from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contexts.agent_execution.domain import RunConflictError
from app.contexts.agent_execution.infrastructure.compatibility_output_repository import (
    CompatibilityOutputRepository,
)
from app.contexts.agent_execution.infrastructure.models import CompatibilityOutputModel
from app.contexts.agent_workspace.application.ports import TerminalOutput
from app.shared.schemas.canonical_json import canonical_digest, canonical_json_bytes

MAX_COMPATIBILITY_OUTPUT_BYTES = 64 * 1024
MAX_COMPATIBILITY_ENVELOPE_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class CompatibilityOutputSnapshot:
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    output_ref: str
    output_digest: str
    response_digest: str
    reply: str
    response_envelope: dict


class CompatibilityOutputService:
    def __init__(self, session: AsyncSession):
        self._repository = CompatibilityOutputRepository(session)

    async def stage(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
        reply: str,
        response_envelope: dict,
    ) -> CompatibilityOutputSnapshot:
        # S3-C round-4 P3: delegate to stage_with_created, discard created.
        snapshot, _created = await self.stage_with_created(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            output_ref=output_ref,
            reply=reply,
            response_envelope=response_envelope,
        )
        return snapshot

    async def stage_with_created(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
        reply: str,
        response_envelope: dict,
    ) -> tuple[CompatibilityOutputSnapshot, bool]:
        """S3-C round-3 P2-1：stage 直接返回 ``(snapshot, created)``，不二次探测。

        ``created=True`` 表示本次调用真实新建（非幂等 replay 命中 existing）。
        fenced port 据此决定是否推进 checkpoint。
        """
        output = reply.encode("utf-8")
        if len(output) > MAX_COMPATIBILITY_OUTPUT_BYTES:
            raise ValueError("compatibility output exceeds 65536 UTF-8 bytes")
        envelope_size = len(canonical_json_bytes(response_envelope))
        if envelope_size > MAX_COMPATIBILITY_ENVELOPE_BYTES:
            raise ValueError("compatibility response envelope exceeds 262144 bytes")
        snapshot = CompatibilityOutputSnapshot(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            output_ref=output_ref,
            output_digest=hashlib.sha256(output).hexdigest(),
            response_digest=canonical_digest(response_envelope),
            reply=reply,
            response_envelope=response_envelope,
        )
        existing = await self._repository.get_by_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if existing is not None:
            self._validate_existing(existing, snapshot)
            return self._to_snapshot(existing), False
        await self._repository.add(
            CompatibilityOutputModel(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                run_id=run_id,
                output_ref=output_ref,
                output_digest=snapshot.output_digest,
                response_digest=snapshot.response_digest,
                reply_text=reply,
                response_envelope=response_envelope,
                media_type="text/markdown",
                classification="internal",
                created_at=datetime.now(UTC),
            )
        )
        return snapshot, True

    async def require_by_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> CompatibilityOutputSnapshot:
        row = await self._repository.get_by_run(tenant_id=tenant_id, run_id=run_id)
        if row is None:
            raise RunConflictError("compatibility terminal output is missing")
        return self._to_snapshot(row)

    async def require_by_ref(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
    ) -> CompatibilityOutputSnapshot:
        row = await self._repository.get_by_ref(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            output_ref=output_ref,
        )
        if row is None:
            raise RunConflictError("compatibility terminal output is unavailable")
        return self._to_snapshot(row)

    @staticmethod
    def _validate_existing(
        row: CompatibilityOutputModel, snapshot: CompatibilityOutputSnapshot
    ) -> None:
        if (
            row.conversation_id != snapshot.conversation_id
            or row.output_ref != snapshot.output_ref
            or row.output_digest != snapshot.output_digest
            or row.response_digest != snapshot.response_digest
        ):
            raise RunConflictError("compatibility output replay conflicts")

    @staticmethod
    def _to_snapshot(row: CompatibilityOutputModel) -> CompatibilityOutputSnapshot:
        # 该快照只用于已完成的 terminal output 读取/重放，对应
        # ``payload_state='present'``（正文非空）。redacted tombstone 是 R1 purge
        # 后的状态，不会出现在此路径；在此断言边界，不让 Optional 泄漏到快照。
        if row.reply_text is None or row.response_envelope is None:
            raise RunConflictError(
                "compatibility output body is erased; snapshot unavailable"
            )
        return CompatibilityOutputSnapshot(
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            run_id=row.run_id,
            output_ref=row.output_ref,
            output_digest=row.output_digest,
            response_digest=row.response_digest,
            reply=row.reply_text,
            response_envelope=row.response_envelope,
        )


class CompatibilityOutputReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def read_terminal_output(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
    ) -> TerminalOutput:
        async with self._session_factory() as session:
            snapshot = await CompatibilityOutputService(session).require_by_ref(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                run_id=run_id,
                output_ref=output_ref,
            )
        return TerminalOutput(
            content=snapshot.reply.encode("utf-8"), media_type="text/markdown"
        )
