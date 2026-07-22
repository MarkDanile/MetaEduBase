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
# BUG-019 AC-1: 非 MCP secret 命名空间（JWT / DB / LLM provider keys 等）显式拒绝，
# 即便其格式匹配 _ENV_KEY_PATTERN。命名空间宽松：含 ``MCP_`` 或 ``_MCP_`` 即可
# （兼容既有 QCC_MCP_TOKEN / INTERNAL_MCP_TOKEN 等约定）。
_MCP_NAMESPACE_PATTERN = re.compile(r"(^|_)(MCP)_", re.IGNORECASE)
_BEARER_PREFIX = "Bearer "

# BUG-019 AC-1: 显式黑名单 —— 这些前缀/字串的 env 绝不能作为 MCP credential，
# 防止高权账号读到 LLM / 数据库 / JWT 密钥并发往外部 MCP。
DENIED_KEY_FRAGMENTS = (
    "JWT_SECRET",
    "JWT_KEY",
    "DATABASE_URL",
    "DB_URL",
    "DB_PASSWORD",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_KEY",
    "SILICONFLOW_API_KEY",
    "SILICONFLOW_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_KEY",
    "OPENAI_API_KEY",
    "OPENAI_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_KEY",
    "LLM_API_KEY",
    "QCC_CLIENT_SECRET",  # QCC 真正的 secret vs QCC_MCP_TOKEN（绑定 token）
    "PRIVATE_KEY",
    "ROOT_PASSWORD",
    "ADMIN_PASSWORD",
    "POSTGRES_PASSWORD",
)


def _is_denied_env_key(env_key: str) -> bool:
    upper = env_key.upper()
    if any(fragment in upper for fragment in DENIED_KEY_FRAGMENTS):
        return True
    # 通配：*SECRET* / *PASSWORD* / *PRIVATE_KEY*（避免漏网）
    return "SECRET" in upper or "PASSWORD" in upper or "PRIVATE_KEY" in upper


class CredentialUnavailableError(Exception):
    """Raised when a credential reference cannot be resolved from the environment."""


@dataclass(frozen=True)
class AuthCredential:
    """Opaque resolved credential — a fully-composed Authorization header value.

    The raw secret is composed into ``header_value`` exactly once (at
    construction) and only ever read via :attr:`header_value` when building an
    httpx request. ``__repr__`` / ``__str__`` are redacted, so the secret can
    never surface in a log line, an error message, or a failure traceback's
    frame-locals printout — the call-chain frames hold this opaque object, not
    a plain ``str`` containing the secret.
    """

    _header_value: str

    @property
    def header_value(self) -> str:
        """The composed ``Authorization`` header value (e.g. ``Bearer <x>``)."""
        return self._header_value

    @property
    def raw(self) -> str:
        """The bare secret (no scheme), for the audit error-message scrubber.

        ``MCPInvocationService._sanitize`` needs the bare value to detect it
        inside error strings. That function is pure (a single ``str.replace``)
        and never raises, so the transient ``str`` it receives cannot leak.
        """
        return self._header_value.removeprefix(_BEARER_PREFIX)

    def __repr__(self) -> str:  # redact: never expose the secret
        return "<AuthCredential redacted>"

    def __str__(self) -> str:  # redact: never expose the secret
        return "<AuthCredential redacted>"


@dataclass(frozen=True)
class CredentialRef:
    """Value object referencing a secret by environment variable name.

    Only the env key name is stored (e.g. ``QCC_MCP_TOKEN``); ``resolve()``
    reads the value from the process environment at call time and raises
    :class:`CredentialUnavailableError` when it is missing — fail-closed.
    The resolved value is returned as an opaque :class:`AuthCredential` and is
    never logged or printed.
    """

    env_key: str

    def __post_init__(self) -> None:
        if not _ENV_KEY_PATTERN.match(self.env_key):
            raise ValueError(
                "credential_ref must be an env key name matching "
                "^[A-Z][A-Z0-9_]*$ (e.g. QCC_MCP_TOKEN)"
            )
        # BUG-019 AC-1: 强制 MCP namespace + 拒绝高敏感命名（JWT/DB/LLM key 等）。
        if not _MCP_NAMESPACE_PATTERN.search(self.env_key):
            raise ValueError(
                f"credential_ref {self.env_key!r} 不在 MCP 命名空间内"
                "（env key 名必须包含 MCP_ 或 _MCP_，如 QCC_MCP_TOKEN）"
            )
        if _is_denied_env_key(self.env_key):
            raise ValueError(
                f"credential_ref {self.env_key!r} 命中黑名单"
                "（JWT/DB/LLM/private/password 等非 MCP secret 不可用）"
            )

    def resolve(self) -> AuthCredential:
        """Resolve the secret from the environment into an opaque AuthCredential.

        Reads ``os.environ[env_key]`` at call time. A redundant ``Bearer ``
        scheme prefix in the env value is stripped (the client adds the scheme
        itself), so a value of either ``<token>`` or ``Bearer <token>`` works.
        Fail-closed: raises :class:`CredentialUnavailableError` when the key is
        unset or empty. The raw secret is never returned as a plain ``str``.
        """
        value = os.environ.get(self.env_key)
        if not value:
            raise CredentialUnavailableError(
                f"credential env key {self.env_key!r} is not set"
            )
        raw = value.removeprefix(_BEARER_PREFIX)
        return AuthCredential(f"{_BEARER_PREFIX}{raw}")


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
