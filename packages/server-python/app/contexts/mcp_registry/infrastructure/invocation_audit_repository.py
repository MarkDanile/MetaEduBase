"""Invocation audit repository for REQ-044 Task 3.

Writes and queries ``metaedu.mcp_invocation_audit``. Every query is
forced through ``tenant_id`` — audit rows are as strictly isolated as
the server registrations themselves (spec §4.2, AC-7).

Only sha256 *digests* of params / response are ever stored here; the
raw payloads never reach this repository by contract of
:class:`MCPInvocationService` (the sole writer).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.infrastructure.mcp_server_models import (
    MCPInvocationAuditModel,
)


class InvocationAuditRepository:
    """Async repository over ``metaedu.mcp_invocation_audit``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        server_code: str,
        tool_name: str,
        caller_type: str,
        caller_user_id: uuid.UUID | None,
        params_digest: str | None,
        response_digest: str | None,
        ok: bool,
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
    ) -> MCPInvocationAuditModel:
        """Insert one audit row (flush only — caller owns the commit)."""
        row = MCPInvocationAuditModel(
            tenant_id=tenant_id,
            server_id=server_id,
            server_code=server_code,
            tool_name=tool_name,
            caller_type=caller_type,
            caller_user_id=caller_user_id,
            params_digest=params_digest,
            response_digest=response_digest,
            ok=ok,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_server(
        self,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MCPInvocationAuditModel], int]:
        """Paginated audit rows for one server, tenant-forced.

        Returns ``(rows, total)`` newest-first so the management UI can
        page a deterministic, isolation-safe view (spec §4.5 last row).
        """
        base = select(MCPInvocationAuditModel).where(
            MCPInvocationAuditModel.tenant_id == tenant_id,
            MCPInvocationAuditModel.server_id == server_id,
        )
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self._session.execute(
            base.order_by(MCPInvocationAuditModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)
