"""MCP transport client for REQ-044 Task 3.

Implements the MCP client over **streamable HTTP** (the current MCP
spec transport) with plain httpx — a deliberate fallback decision:
the official ``mcp`` Python SDK is not installed in this environment
and adding it did not pass dependency review, so this module
implements the minimal JSON-RPC 2.0 + SSE parsing subset we need
(``initialize`` handshake → ``notifications/initialized`` →
``tools/call`` / ``tools/list``). The choice is recorded in the Task 3
commit message.

Transport behaviour (spec §4.4):

- ``streamable_http`` (default): single-endpoint POST of JSON-RPC 2.0
  envelopes. The response may be ``application/json`` *or* an SSE
  stream (``text/event-stream``) — both are parsed. A per-call session
  is opened (``initialize`` → capture ``Mcp-Session-Id`` →
  ``notifications/initialized``) so session-aware servers work, and
  discarded afterwards (stateless per call).
- ``sse`` (legacy enum, kept for config compatibility): NOT
  implemented in V1 — calls fail with ``error_code=transport_error``
  and a clear message. Old dual-endpoint servers must be fronted by a
  streamable-HTTP gateway.

Auth: ``Authorization: Bearer <resolved credential>``; the header name
is configurable via the constructor (default ``Authorization``). The
credential value is **never** logged, never put into error messages,
and never persisted.

Timeout: ``asyncio.wait_for`` hard timeout of ``server.timeout_ms``
per call; timeouts normalize to ``error_code="timeout"``.

Error normalization (spec §4.2 error codes):
``timeout`` | ``transport_error`` (network / non-2xx / handshake
failure / unsupported transport) | ``tool_error`` (JSON-RPC error
object, or a ``tools/call`` result with ``isError: true``).

Assembly boundary: only
:class:`~app.contexts.mcp_registry.application.mcp_invocation_service.MCPInvocationService`
constructs :class:`MCPClient`; business code never does.
"""
from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.contexts.mcp_registry.domain.mcp_server import MCPServer

# Normalized error codes (spec §4.2).
ERROR_TIMEOUT = "timeout"
ERROR_TRANSPORT = "transport_error"
ERROR_TOOL = "tool_error"


class MCPClientError(Exception):
    """Typed transport failure raised by :meth:`MCPClient.list_tools`.

    ``call_tool`` normalizes failures into :class:`MCPCallResult`
    instead of raising; ``list_tools`` (used by the enable connectivity
    probe) must return ``list[dict]`` on success, so it raises this
    typed error on failure. ``error_code`` is one of the normalized
    codes above. The message never contains the credential value or raw
    request / response bodies.
    """

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class MCPCallResult:
    """Normalized outcome of a ``tools/call`` invocation."""

    ok: bool
    result: dict | None = None
    error_code: str | None = None
    error_message: str | None = None


def _extract_sse_messages(body: str) -> list[dict]:
    """Parse an SSE stream body into JSON-RPC message dicts.

    Each ``data:`` line carries one JSON-RPC message; multi-line data
    fields are concatenated per the SSE spec. Non-JSON lines are
    skipped defensively.
    """
    messages: list[dict] = []
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
        elif line.strip() == "" and data_lines:
            payload = "\n".join(data_lines)
            data_lines = []
            try:
                messages.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    if data_lines:
        with contextlib.suppress(json.JSONDecodeError):
            messages.append(json.loads("\n".join(data_lines)))
    return messages


class MCPClient:
    """Minimal MCP client (streamable HTTP) over httpx.

    ``transport`` is injectable purely for tests (``httpx.MockTransport``);
    production wiring leaves it ``None``.
    """

    def __init__(
        self,
        *,
        auth_header: str = "Authorization",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth_header = auth_header
        self._transport = transport
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        server: MCPServer,
        credential: str | None,
        tool_name: str,
        params: dict,
    ) -> MCPCallResult:
        """Invoke ``tool_name`` and normalize the outcome.

        Never raises for transport / tool failures — they come back as
        ``MCPCallResult(ok=False, error_code=...)`` so the invocation
        service can write a uniform audit row.
        """
        try:
            # Per spec §4.4, ``server.timeout_ms`` is the "单次调用超时" budget
            # for one logical call_tool - which in streamable_http includes the
            # initialize handshake + notifications/initialized + tools/call
            # (you cannot call tools/call without first initializing). The
            # wait_for therefore covers the whole _with_session; for V1's
            # single-tool QCC calls the handshake is one cheap round-trip and
            # leaves the bulk of the budget for tools/call.
            result = await asyncio.wait_for(
                self._with_session(
                    server,
                    credential,
                    lambda client, sid: self._rpc(
                        client,
                        server,
                        credential,
                        sid,
                        "tools/call",
                        {"name": tool_name, "arguments": params},
                    ),
                ),
                timeout=server.timeout_ms / 1000,
            )
        except (TimeoutError, httpx.TimeoutException):
            return MCPCallResult(
                ok=False,
                error_code=ERROR_TIMEOUT,
                error_message=f"MCP call timed out after {server.timeout_ms}ms",
            )
        except MCPClientError as e:
            return MCPCallResult(
                ok=False, error_code=e.error_code, error_message=str(e)
            )
        except httpx.HTTPError as e:
            # httpx messages contain the URL but never headers, so the
            # credential cannot leak here.
            return MCPCallResult(
                ok=False,
                error_code=ERROR_TRANSPORT,
                error_message=f"transport failure: {type(e).__name__}: {e}",
            )
        # Tool-level failure: JSON-RPC result flagged isError.
        if result.get("isError"):
            return MCPCallResult(
                ok=False,
                error_code=ERROR_TOOL,
                error_message=self._tool_error_message(result),
            )
        return MCPCallResult(ok=True, result=result)

    async def list_tools(
        self, server: MCPServer, credential: str | None
    ) -> list[dict]:
        """Return the server's tool list (enable connectivity probe).

        Raises :class:`MCPClientError` on any failure — the caller
        (enable endpoint) turns that into a non-blocking warning.
        """
        try:
            result = await asyncio.wait_for(
                self._with_session(
                    server,
                    credential,
                    lambda client, sid: self._rpc(
                        client, server, credential, sid, "tools/list", {}
                    ),
                ),
                timeout=server.timeout_ms / 1000,
            )
        except (TimeoutError, httpx.TimeoutException) as e:
            raise MCPClientError(
                ERROR_TIMEOUT,
                f"list_tools timed out after {server.timeout_ms}ms",
            ) from e
        except MCPClientError:
            raise
        except httpx.HTTPError as e:
            raise MCPClientError(
                ERROR_TRANSPORT,
                f"transport failure: {type(e).__name__}: {e}",
            ) from e
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise MCPClientError(
                ERROR_TRANSPORT, "tools/list response missing 'tools' list"
            )
        return tools

    # ------------------------------------------------------------------
    # internal — session + JSON-RPC plumbing
    # ------------------------------------------------------------------

    async def _with_session(self, server, credential, fn):
        """Open an MCP session (initialize handshake), run ``fn``, discard.

        The legacy ``sse`` transport is a kept enum only — fail with a
        clear, actionable error instead of silently misbehaving.
        """
        if server.transport == "sse":
            raise MCPClientError(
                ERROR_TRANSPORT,
                "legacy 'sse' (dual-endpoint) transport is not implemented "
                "in V1 — register the server with transport=streamable_http",
            )
        if server.transport != "streamable_http":
            raise MCPClientError(
                ERROR_TRANSPORT,
                f"unsupported transport {server.transport!r}",
            )
        async with httpx.AsyncClient(
            transport=self._transport, timeout=None
        ) as client:
            init_result, session_id = await self._rpc_with_headers(
                client,
                server,
                credential,
                None,
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "metaedu-mcp-client", "version": "1.0"},
                },
            )
            if not isinstance(init_result, dict):
                raise MCPClientError(
                    ERROR_TRANSPORT, "initialize handshake returned no result"
                )
            # Fire-and-forget initialized notification (spec-required);
            # failures here must not block the actual call.
            await self._notify(
                client, server, credential, session_id, "notifications/initialized"
            )
            return await fn(client, session_id)

    def _headers(
        self, credential: str | None, session_id: str | None
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        # The credential is injected here and ONLY here — never logged,
        # never included in error messages.
        if credential:
            headers[self._auth_header] = f"Bearer {credential}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        return headers

    async def _rpc(self, client, server, credential, session_id, method, params):
        result, _ = await self._rpc_with_headers(
            client, server, credential, session_id, method, params
        )
        return result

    async def _rpc_with_headers(
        self, client, server, credential, session_id, method, params
    ) -> tuple[Any, str | None]:
        """POST one JSON-RPC request; return (result, mcp-session-id)."""
        request_id = next(self._ids)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        response = await client.post(
            server.server_url,
            json=payload,
            headers=self._headers(credential, session_id),
        )
        new_session_id = response.headers.get("mcp-session-id", session_id)
        if response.status_code >= 400:
            raise MCPClientError(
                ERROR_TRANSPORT,
                f"MCP server returned HTTP {response.status_code} for {method}",
            )
        message = self._decode_response(response, request_id, method)
        error = message.get("error")
        if error is not None:
            detail = error.get("message", "unknown JSON-RPC error")
            raise MCPClientError(
                ERROR_TOOL, f"{method} failed: {detail}"
            )
        return message.get("result"), new_session_id

    def _decode_response(
        self, response: httpx.Response, request_id: int, method: str
    ) -> dict:
        """Decode an ``application/json`` or ``text/event-stream`` body."""
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for message in _extract_sse_messages(response.text):
                if message.get("id") == request_id:
                    return message
            raise MCPClientError(
                ERROR_TRANSPORT,
                f"SSE stream for {method} contained no response for "
                f"request id {request_id}",
            )
        try:
            message = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise MCPClientError(
                ERROR_TRANSPORT,
                f"unparseable response for {method} "
                f"(content-type {content_type or 'unknown'})",
            ) from e
        if not isinstance(message, dict):
            raise MCPClientError(
                ERROR_TRANSPORT, f"non-object JSON-RPC response for {method}"
            )
        return message

    async def _notify(
        self, client, server, credential, session_id, method: str
    ) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        # Best-effort per MCP spec; the subsequent real call will surface
        # any genuine connectivity problem.
        with contextlib.suppress(httpx.HTTPError):
            await client.post(
                server.server_url,
                json={"jsonrpc": "2.0", "method": method},
                headers=self._headers(credential, session_id),
            )

    @staticmethod
    def _tool_error_message(result: dict) -> str:
        """Extract a short message from a ``tools/call`` isError result.

        Only the tool's own text content is surfaced (never the request
        params); the invocation service truncates to 500 chars.
        """
        content = result.get("content")
        if isinstance(content, list):
            texts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            joined = "; ".join(t for t in texts if t)
            if joined:
                return f"tool reported error: {joined}"
        return "tool reported error (isError=true)"
