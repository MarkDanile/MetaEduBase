"""MCP registry service: 注册 / 更新 / 启停 / 删除编排 + 管理 RBAC.

REQ-044 Task 2: sits between :mod:`mcp_registry_router` and
:class:`MCPServerRepository`. Mirrors the :class:`CatalogService` pattern:

1. **RBAC** — only ``admin`` / ``data_admin`` / ``super_admin`` may create,
   update, enable, disable or delete MCP server registrations. All roles
   may read (list / get).
2. **Code uniqueness** — ``(tenant_id, code)`` is unique in the DB, but
   the service surfaces a typed :class:`MCPServerCodeConflictError`
   *before* the INSERT so the router can return 409.
3. **Validation** — ``code`` / ``transport`` / ``credential_ref`` format
   errors raise plain :class:`ValueError`, which the router maps to 422.
   ``credential_ref`` is validated as an env-key *name* via
   :class:`CredentialRef`; the environment is **not** probed at
   registration time (spec §4.3 — avoid environment coupling).
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.domain.mcp_server import (
    CredentialRef,
    MCPServer,
)
from app.contexts.mcp_registry.infrastructure.mcp_server_repository import (
    MCPServerRepository,
)

# Roles that may register / modify / enable / disable / delete MCP servers.
# Same admin set as CATALOG_ADMIN_ROLES (REQ-054) — ``super_admin`` is the
# seeded dev admin's role and must be allowed for bootstrapping.
MCP_REGISTRY_ADMIN_ROLES = {"admin", "data_admin", "super_admin"}

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TRANSPORTS = {"streamable_http", "sse"}

# Fields a PATCH may touch. ``code`` / ``tenant_id`` / ``created_by`` are
# immutable after registration; ``enabled`` flips only via enable/disable.
_UPDATABLE_FIELDS = {
    "name",
    "description",
    "transport",
    "server_url",
    "credential_ref",
    "allowed_roles",
    "timeout_ms",
}


class MCPRegistryPermissionError(PermissionError):
    """用户无权管理 MCP server 注册。"""


class MCPServerCodeConflictError(ValueError):
    """同 tenant 内 MCP server code 已存在。"""


class MCPServerNotFoundError(LookupError):
    """MCP server 不存在（或已软删 / 不属于本 tenant）。"""


class MCPRegistryService:
    """CRUD + enable/disable orchestration and RBAC for :class:`MCPServer`."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = MCPServerRepository(session)

    def _check_admin(self, role: str) -> None:
        if role not in MCP_REGISTRY_ADMIN_ROLES:
            raise MCPRegistryPermissionError(
                f"角色 '{role}' 无权管理 MCP server"
                f"（仅 {sorted(MCP_REGISTRY_ADMIN_ROLES)} 可操作）"
            )

    @staticmethod
    def _validate_code(code: str) -> None:
        if not _CODE_PATTERN.match(code):
            raise ValueError(
                "code 必须匹配 ^[a-z][a-z0-9_]*$（小写字母开头，如 qcc）"
            )

    @staticmethod
    def _validate_transport(transport: str) -> None:
        if transport not in TRANSPORTS:
            raise ValueError(f"transport 必须是 {sorted(TRANSPORTS)} 之一")

    @staticmethod
    def _validate_credential_ref(credential_ref: str | None) -> None:
        # 只校验引用名格式，不探测 env 是否存在（spec §4.3）。格式非法时
        # CredentialRef.__post_init__ 抛 ValueError -> router 映射 422。
        if credential_ref is not None:
            CredentialRef(credential_ref)

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        server_url: str,
        created_by: uuid.UUID,
        description: str | None = None,
        transport: str = "streamable_http",
        credential_ref: str | None = None,
        allowed_roles: list[str] | None = None,
        timeout_ms: int = 30000,
        role: str = "employee",
    ) -> MCPServer:
        self._check_admin(role)
        self._validate_code(code)
        self._validate_transport(transport)
        self._validate_credential_ref(credential_ref)
        # code 唯一性校验 — 提前于 INSERT，让 router 能返回 409
        existing = await self._repo.get_by_code(tenant_id, code)
        if existing:
            raise MCPServerCodeConflictError(f"MCP server code '{code}' 已存在")
        server = MCPServer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code=code,
            name=name,
            description=description,
            transport=transport,
            server_url=server_url,
            credential_ref=credential_ref,
            allowed_roles=list(allowed_roles or []),
            enabled=False,  # 注册后默认停用，必须显式 enable（spec §4.2）
            timeout_ms=timeout_ms,
            created_by=created_by,
        )
        return await self._repo.create(server)

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[MCPServer]:
        return await self._repo.list_by_tenant(tenant_id)

    async def get_by_id(
        self, tenant_id: uuid.UUID, server_id: uuid.UUID
    ) -> MCPServer:
        server = await self._repo.get_by_id(tenant_id, server_id)
        if not server:
            raise MCPServerNotFoundError("MCP server 不存在")
        return server

    async def update(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        role: str = "employee",
        **kwargs: object,
    ) -> MCPServer:
        self._check_admin(role)
        updates = {k: v for k, v in kwargs.items() if k in _UPDATABLE_FIELDS}
        transport = updates.get("transport")
        if transport is not None:
            self._validate_transport(str(transport))
        credential_ref = updates.get("credential_ref")
        if credential_ref is not None:
            self._validate_credential_ref(str(credential_ref))
        server = await self._repo.update(tenant_id, server_id, **updates)
        if not server:
            raise MCPServerNotFoundError("MCP server 不存在")
        return server

    async def set_enabled(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        enabled: bool,
        role: str = "employee",
    ) -> MCPServer:
        self._check_admin(role)
        server = await self._repo.set_enabled(tenant_id, server_id, enabled)
        if not server:
            raise MCPServerNotFoundError("MCP server 不存在")
        return server

    async def delete(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        role: str = "employee",
    ) -> None:
        """Soft delete only — a server with audit rows is never hard-deleted."""
        self._check_admin(role)
        ok = await self._repo.soft_delete(tenant_id, server_id)
        if not ok:
            raise MCPServerNotFoundError("MCP server 不存在")
