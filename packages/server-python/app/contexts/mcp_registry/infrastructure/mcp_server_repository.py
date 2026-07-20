"""MCP server repository: CRUD + tenant 隔离.

REQ-044 Task 2: every query is scoped by ``tenant_id`` so that one tenant
cannot read or mutate another tenant's MCP server registrations. Soft
delete (``is_active = False``) is the only delete path — audit rows in
``mcp_invocation_audit`` hold an FK to ``mcp_servers.id``, so a registered
server is never hard-deleted.

The repository persists only configuration. ``credential_ref`` is the
*name* of an environment variable (see :class:`CredentialRef`); the
secret value is never stored here.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.domain.mcp_server import MCPServer
from app.contexts.mcp_registry.infrastructure.mcp_server_models import (
    MCPServerModel,
)


class MCPServerRepository:
    """Async CRUD repository over ``metaedu.mcp_servers``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, server: MCPServer) -> MCPServer:
        row = MCPServerModel(
            id=server.id,
            tenant_id=server.tenant_id,
            code=server.code,
            name=server.name,
            description=server.description,
            transport=server.transport,
            server_url=server.server_url,
            credential_ref=server.credential_ref,
            allowed_roles=server.allowed_roles,
            enabled=server.enabled,
            timeout_ms=server.timeout_ms,
            is_active=server.is_active,
            created_by=server.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(
        self, tenant_id: uuid.UUID, server_id: uuid.UUID
    ) -> MCPServer | None:
        stmt = select(MCPServerModel).where(
            MCPServerModel.id == server_id,
            MCPServerModel.tenant_id == tenant_id,
            MCPServerModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_code(
        self, tenant_id: uuid.UUID, code: str
    ) -> MCPServer | None:
        stmt = select(MCPServerModel).where(
            MCPServerModel.tenant_id == tenant_id,
            MCPServerModel.code == code,
            MCPServerModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[MCPServer]:
        stmt = (
            select(MCPServerModel)
            .where(
                MCPServerModel.tenant_id == tenant_id,
                MCPServerModel.is_active == True,  # noqa: E712
            )
            .order_by(MCPServerModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def update(
        self,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        **kwargs: object,
    ) -> MCPServer | None:
        stmt = select(MCPServerModel).where(
            MCPServerModel.id == server_id,
            MCPServerModel.tenant_id == tenant_id,
            MCPServerModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        for key, val in kwargs.items():
            if val is not None and hasattr(row, key):
                setattr(row, key, val)
        await self._session.flush()
        return self._to_domain(row)

    async def set_enabled(
        self, tenant_id: uuid.UUID, server_id: uuid.UUID, enabled: bool
    ) -> MCPServer | None:
        stmt = select(MCPServerModel).where(
            MCPServerModel.id == server_id,
            MCPServerModel.tenant_id == tenant_id,
            MCPServerModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.enabled = enabled
        await self._session.flush()
        return self._to_domain(row)

    async def soft_delete(
        self, tenant_id: uuid.UUID, server_id: uuid.UUID
    ) -> bool:
        """Soft delete only — never row-delete.

        ``mcp_invocation_audit.server_id`` FK references this row, so hard
        delete would break audit traceability (spec §4.5: 有审计行的
        server 不硬删 — V1 统一软删）.
        """
        stmt = select(MCPServerModel).where(
            MCPServerModel.id == server_id,
            MCPServerModel.tenant_id == tenant_id,
            MCPServerModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_active = False
        await self._session.flush()
        return True

    def _to_domain(self, row: MCPServerModel) -> MCPServer:
        return MCPServer(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            description=row.description,
            transport=row.transport,
            server_url=row.server_url,
            credential_ref=row.credential_ref,
            allowed_roles=list(row.allowed_roles or []),
            enabled=row.enabled,
            timeout_ms=row.timeout_ms,
            is_active=row.is_active,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
