"""MCP server domain entity for REQ-044.

An MCP server registration is a tenant-scoped configuration row that tells
the platform how to reach an external MCP server (transport, URL, timeout)
and who may invoke it (``allowed_roles``). This dataclass is the
pure-Python domain representation — persistence is handled by
:class:`MCPServerModel` (ORM) and the repository (Task 2).

``CredentialRef`` is the secret boundary: the database only ever stores
the *name* of an environment variable; the value is resolved from
``os.environ`` at invocation time and is never logged, printed, or
persisted.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

_ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class CredentialUnavailableError(Exception):
    """Raised when a credential reference cannot be resolved from the environment."""


@dataclass(frozen=True)
class CredentialRef:
    """Value object referencing a secret by environment variable name.

    Only the env key name is stored (e.g. ``QCC_MCP_TOKEN``); ``resolve()``
    reads the value from the process environment at call time and raises
    :class:`CredentialUnavailableError` when it is missing — fail-closed.
    The resolved value is never logged or printed.
    """

    env_key: str

    def __post_init__(self) -> None:
        if not _ENV_KEY_PATTERN.match(self.env_key):
            raise ValueError(
                "credential_ref must be an env key name matching "
                "^[A-Z][A-Z0-9_]*$ (e.g. QCC_MCP_TOKEN)"
            )

    def resolve(self) -> str:
        """Return the secret value from the environment, or fail closed."""
        value = os.environ.get(self.env_key)
        if not value:
            raise CredentialUnavailableError(
                f"credential env key {self.env_key!r} is not set"
            )
        return value


@dataclass
class MCPServer:
    """Domain entity for a tenant-scoped MCP server registration."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    server_url: str
    description: str | None = None
    transport: str = "streamable_http"
    credential_ref: str | None = None
    allowed_roles: list[str] = field(default_factory=list)
    enabled: bool = False
    timeout_ms: int = 30000
    is_active: bool = True
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def allows_role(self, role: str) -> bool:
        """白名单校验：role 是否被允许调用该 server（空列表 = 仅 super_admin）。"""
        return role == "super_admin" or role in self.allowed_roles
