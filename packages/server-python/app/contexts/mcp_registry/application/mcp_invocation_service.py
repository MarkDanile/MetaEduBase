"""MCP invocation service for REQ-044 Task 3 (spec §4.6).

The single orchestration entry point for calling an MCP tool:

    resolve server (tenant, code)
      -> check enabled                (else audit ok=False error_code=disabled)
      -> check caller role            (else audit ok=False error_code=forbidden)
      -> resolve CredentialRef        (else audit ok=False error_code=credential_unavailable)
      -> MCPClient.call_tool          (timeout / transport_error / tool_error)
      -> write audit row (digests, ok, duration_ms, caller, tenant_id)

An unregistered server is the ONLY failure branch with no audit row —
there is no ``server_id`` to associate, so it raises
:class:`MCPInvocationServerNotFoundError` before any audit write.

Digest convention (spec §4.2): ``sha256(canonical_json)`` where
canonical JSON uses sorted keys and compact separators. Raw params /
response bodies are NEVER persisted; ``error_message`` is truncated to
500 chars and scrubbed of the resolved credential value.

Assembly boundary: this is the ONLY place an :class:`MCPClient` is
constructed (business code receives the service, never the client).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.domain.mcp_server import (
    AuthCredential,
    CredentialRef,
    CredentialUnavailableError,
    MCPServer,
)
from app.contexts.mcp_registry.infrastructure.invocation_audit_repository import (
    InvocationAuditRepository,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import (
    MCPClient,
    MCPClientError,
)
from app.contexts.mcp_registry.infrastructure.mcp_server_repository import (
    MCPServerRepository,
)

_ERROR_MESSAGE_MAX = 500


def canonical_digest(obj: Any) -> str:
    """sha256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MCPInvocationError(Exception):
    """Typed invocation failure — always paired with an audit row.

    ``error_code`` is one of ``disabled`` / ``forbidden`` /
    ``credential_unavailable`` / ``timeout`` / ``transport_error`` /
    ``tool_error`` (``not_registered`` only via the NotFound subclass,
    which is NOT audited — see spec §4.6).
    """

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class MCPInvocationServerNotFoundError(MCPInvocationError, LookupError):
    """Server code not registered for this tenant — no audit row written."""

    def __init__(self, server_code: str) -> None:
        super().__init__(
            "not_registered", f"MCP server '{server_code}' 未注册"
        )


@dataclass(frozen=True)
class InvocationCaller:
    """Who triggered the invocation (audit attribution)."""

    caller_type: str  # "http_api" / "adapter:structured_data" / "service"
    role: str
    user_id: uuid.UUID | None = None


class MCPInvocationService:
    """Invocation orchestration + audit for registered MCP servers."""

    def __init__(
        self, session: AsyncSession, client: MCPClient | None = None
    ) -> None:
        self._session = session
        self._servers = MCPServerRepository(session)
        self._audit = InvocationAuditRepository(session)
        # Assembly boundary: MCPClient is constructed here and only here.
        self._client = client or MCPClient()

    async def invoke(
        self,
        *,
        tenant_id: uuid.UUID,
        server_code: str,
        tool_name: str,
        params: dict | None,
        caller: InvocationCaller,
    ) -> dict:
        """Invoke ``tool_name`` on the registered server; return its result.

        Raises :class:`MCPInvocationServerNotFoundError` (unregistered, no
        audit) or :class:`MCPInvocationError` (audited failure).
        """
        started = time.monotonic()
        server = await self._servers.get_by_code(tenant_id, server_code)
        if server is None or not server.is_active:
            raise MCPInvocationServerNotFoundError(server_code)

        # params_digest is computed up front so even pre-call failures
        # carry it; it is None only when no params were supplied at all
        # (spec §4.2 nullable note).
        params_digest = canonical_digest(params) if params is not None else None

        def _duration() -> int:
            return int((time.monotonic() - started) * 1000)

        async def _fail(error_code: str, message: str) -> MCPInvocationError:
            await self._audit.write(
                tenant_id=tenant_id,
                server_id=server.id,
                server_code=server.code,
                tool_name=tool_name,
                caller_type=caller.caller_type,
                caller_user_id=caller.user_id,
                params_digest=params_digest,
                response_digest=None,
                ok=False,
                error_code=error_code,
                error_message=message[:_ERROR_MESSAGE_MAX],
                duration_ms=_duration(),
            )
            return MCPInvocationError(error_code, message)

        # ---- enabled gate ----
        if not server.enabled:
            raise await _fail(
                "disabled", f"MCP server '{server.code}' 已停用"
            )

        # ---- role gate (empty allowed_roles = super_admin only) ----
        if not server.allows_role(caller.role):
            raise await _fail(
                "forbidden",
                f"角色 '{caller.role}' 无权调用 MCP server '{server.code}'",
            )

        # ---- credential resolution (fail-closed, no call made) ----
        # resolve() returns an opaque AuthCredential (redacted repr) — the
        # raw secret is never bound as a plain str local here, so a traceback
        # cannot print it.
        credential: AuthCredential | None = None
        if server.credential_ref:
            try:
                credential = CredentialRef(server.credential_ref).resolve()
            except CredentialUnavailableError as e:
                raise await _fail("credential_unavailable", str(e)) from e

        # ---- transport call ----
        result = await self._client.call_tool(server, credential, tool_name, params or {})
        if not result.ok:
            message = self._sanitize(
                result.error_message or "MCP call failed",
                credential.raw if credential is not None else None,
            )
            raise await _fail(result.error_code or "transport_error", message)

        await self._audit.write(
            tenant_id=tenant_id,
            server_id=server.id,
            server_code=server.code,
            tool_name=tool_name,
            caller_type=caller.caller_type,
            caller_user_id=caller.user_id,
            params_digest=params_digest,
            response_digest=canonical_digest(result.result),
            ok=True,
            error_code=None,
            error_message=None,
            duration_ms=_duration(),
        )
        return result.result or {}

    async def probe_connectivity(self, server: MCPServer) -> str | None:
        """Non-blocking ``list_tools`` probe for the enable endpoint.

        Returns ``None`` on success, otherwise a warning string. Never
        raises, never writes audit (this is a connectivity check, not a
        business invocation), and the warning never contains the
        credential value.
        """
        credential: AuthCredential | None = None
        if server.credential_ref:
            try:
                credential = CredentialRef(server.credential_ref).resolve()
            except CredentialUnavailableError as e:
                return f"连通校验未执行：{e}"
        try:
            await self._client.list_tools(server, credential)
        except MCPClientError as e:
            message = self._sanitize(
                str(e), credential.raw if credential is not None else None
            )
            return f"list_tools 连通校验失败 ({e.error_code})：{message}"
        return None

    @staticmethod
    def _sanitize(message: str, credential: str | None) -> str:
        """Guarantee the resolved secret never appears in stored text.

        Pure, non-raising (a single ``str.replace``): the bare secret it
        receives is transient and cannot leak into a traceback.
        """
        if credential:
            message = message.replace(credential, "***")
        return message
