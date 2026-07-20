"""MCP registry CRUD API for REQ-044 (Task 2).

Endpoints (spec §4.5, first 7 rows):
- ``POST   /api/v1/mcp-servers``             — register (admin/data_admin/super_admin)
- ``GET    /api/v1/mcp-servers``             — list (any authenticated user, own tenant)
- ``GET    /api/v1/mcp-servers/{id}``        — detail (any authenticated user, own tenant)
- ``PATCH  /api/v1/mcp-servers/{id}``        — update config / allowed_roles (admin roles)
- ``POST   /api/v1/mcp-servers/{id}/enable`` — enable (admin roles)
- ``POST   /api/v1/mcp-servers/{id}/disable``— disable (admin roles)
- ``DELETE /api/v1/mcp-servers/{id}``        — soft delete (admin roles)

The router is intentionally light: auth + payload parsing + typed-error
mapping (403 / 404 / 409 / 422). The response DTO contains **no secret** —
by design only the env-key *name* (``credential_ref``) is ever stored or
returned; the value lives only in the process environment.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryPermissionError,
    MCPRegistryService,
    MCPServerCodeConflictError,
    MCPServerNotFoundError,
)
from app.contexts.mcp_registry.domain.mcp_server import MCPServer
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/mcp-servers", tags=["mcp-registry"])

_TRANSPORT_PATTERN = r"^(streamable_http|sse)$"


class MCPServerCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=200)
    server_url: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    transport: str = Field(default="streamable_http", pattern=_TRANSPORT_PATTERN)
    # env key 名（如 QCC_MCP_TOKEN）— 只存引用名，格式在 service 层校验
    credential_ref: str | None = Field(default=None, max_length=200)
    allowed_roles: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=30000, gt=0)


class MCPServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    transport: str | None = Field(default=None, pattern=_TRANSPORT_PATTERN)
    server_url: str | None = Field(default=None, min_length=1, max_length=500)
    credential_ref: str | None = Field(default=None, max_length=200)
    allowed_roles: list[str] | None = None
    timeout_ms: int | None = Field(default=None, gt=0)


class MCPServerDTO(BaseModel):
    """Public representation — contains no secret, only the env-key name."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    description: str | None
    transport: str
    server_url: str
    credential_ref: str | None
    allowed_roles: list[str]
    enabled: bool
    timeout_ms: int
    created_by: uuid.UUID | None
    created_at: str
    updated_at: str


def _to_dto(server: MCPServer) -> MCPServerDTO:
    return MCPServerDTO(
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
        created_by=server.created_by,
        created_at=server.created_at.isoformat() if server.created_at else "",
        updated_at=server.updated_at.isoformat() if server.updated_at else "",
    )


def _service(session: AsyncSession) -> MCPRegistryService:
    return MCPRegistryService(session)


@router.post("", response_model=MCPServerDTO, status_code=201)
async def create_mcp_server(
    req: MCPServerCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        server = await service.create(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            code=req.code,
            name=req.name,
            server_url=req.server_url,
            description=req.description,
            transport=req.transport,
            credential_ref=req.credential_ref,
            allowed_roles=req.allowed_roles,
            timeout_ms=req.timeout_ms,
            created_by=uuid.UUID(str(current_user["id"])),
            role=str(current_user.get("role", "employee")),
        )
    except MCPRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MCPServerCodeConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await session.commit()
    return _to_dto(server)


@router.get("", response_model=list[MCPServerDTO])
async def list_mcp_servers(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    servers = await service.list_by_tenant(
        uuid.UUID(str(current_user["tenant_id"]))
    )
    return [_to_dto(s) for s in servers]


@router.get("/{server_id}", response_model=MCPServerDTO)
async def get_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        server = await service.get_by_id(
            uuid.UUID(str(current_user["tenant_id"])),
            uuid.UUID(server_id),
        )
    except MCPServerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_dto(server)


@router.patch("/{server_id}", response_model=MCPServerDTO)
async def update_mcp_server(
    server_id: str,
    req: MCPServerUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        server = await service.update(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            server_id=uuid.UUID(server_id),
            role=str(current_user.get("role", "employee")),
            **req.model_dump(exclude_unset=True),
        )
    except MCPRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MCPServerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await session.commit()
    return _to_dto(server)


async def _set_enabled(
    server_id: str,
    enabled: bool,
    session: AsyncSession,
    current_user: dict,
) -> MCPServer:
    service = _service(session)
    try:
        server = await service.set_enabled(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            server_id=uuid.UUID(server_id),
            enabled=enabled,
            role=str(current_user.get("role", "employee")),
        )
    except MCPRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MCPServerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session.commit()
    return server


@router.post("/{server_id}/enable", response_model=MCPServerDTO)
async def enable_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    # TODO(Task 3): 可选 list_tools 连通校验（spec §4.5：失败不阻塞启用，
    # 仅返回警告）。Task 2 只翻转 enabled 标志。
    server = await _set_enabled(server_id, True, session, current_user)
    return _to_dto(server)


@router.post("/{server_id}/disable", response_model=MCPServerDTO)
async def disable_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    server = await _set_enabled(server_id, False, session, current_user)
    return _to_dto(server)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = _service(session)
    try:
        await service.delete(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            server_id=uuid.UUID(server_id),
            role=str(current_user.get("role", "employee")),
        )
    except MCPRegistryPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MCPServerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session.commit()
