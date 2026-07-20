"""Test MCPClient transport (REQ-044 Task 3, spec §4.4).

Pure unit tests over httpx ``MockTransport`` - no real network. Covers
the streamable-HTTP JSON-RPC 2.0 path (``initialize`` ->
``notifications/initialized`` -> ``tools/call`` / ``tools/list``),
both ``application/json`` and ``text/event-stream`` (SSE) responses,
and the normalized error codes (``timeout`` / ``transport_error`` /
``tool_error``).

The legacy ``sse`` transport enum must fail with a clear
``transport_error`` (not implemented in V1).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.contexts.mcp_registry.domain.mcp_server import MCPServer
from app.contexts.mcp_registry.infrastructure.mcp_client import (
    ERROR_TIMEOUT,
    ERROR_TOOL,
    ERROR_TRANSPORT,
    MCPClient,
    MCPClientError,
)

pytestmark = pytest.mark.asyncio


def _server(
    *,
    transport: str = "streamable_http",
    server_url: str = "https://mcp.example.com/rpc",
    credential_ref: str | None = None,
    timeout_ms: int = 30000,
) -> MCPServer:
    """Build a minimal MCPServer domain entity for transport tests."""
    base = MCPServer(
        id=None,
        tenant_id=None,
        code="qcc",
        name="企查查",
        transport=transport,
        server_url=server_url,
        credential_ref=credential_ref,
        allowed_roles=["admin"],
        enabled=True,
        timeout_ms=timeout_ms,
        is_active=True,
        created_by=None,
    )
    return base


def _jsonrpc(result, req_id):
    """Build a JSON-RPC 2.0 success response payload."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _mock(handler, client: MCPClient | None = None) -> MCPClient:
    """Wire an httpx MockTransport into an MCPClient."""
    transport = httpx.MockTransport(handler)
    return client or MCPClient(transport=transport)


def _seq_handler(responses_by_method: dict[str, list]):
    """Return a MockTransport handler that serves initialize -> notify -> call.

    ``responses_by_method`` maps method -> list of result payloads (popped
    FIFO). ``notifications/initialized`` is a fire-and-forget 202. The
    handler tracks JSON-RPC ids so each response echoes the request id.
    """
    pending = {k: list(v) for k, v in responses_by_method.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method not in pending or not pending[method]:
            return httpx.Response(500, text="no queued response")
        result = pending[method].pop(0)
        return httpx.Response(
            200, json=_jsonrpc(result, req_id),
            headers={"content-type": "application/json"},
        )

    return handler


# ── call_tool success ──────────────────────────────────────────────


async def test_call_tool_success_json_response():
    """tools/call over application/json returns ok=True with the result."""
    handler = _seq_handler({
        "initialize": [{"protocolVersion": "2025-03-26", "capabilities": {}}],
        "tools/call": [{"structuredContent": [{"company": "ACME"}]}],
    })
    client = _mock(handler)
    result = await client.call_tool(
        _server(), credential="tok", tool_name="search", params={"q": "ACME"}
    )
    assert result.ok is True
    assert result.result == {"structuredContent": [{"company": "ACME"}]}
    assert result.error_code is None


async def test_call_tool_success_sse_response():
    """tools/call answered via SSE stream is parsed into the result."""
    init_result = {"protocolVersion": "2025-03-26", "capabilities": {}}
    call_result = {"content": [{"type": "text", "text": '[{"x": 1}]'}]}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return httpx.Response(202)
        result = {"initialize": init_result, "tools/call": call_result}[method]
        body = f"event: message\ndata: {json.dumps(_jsonrpc(result, req_id))}\n\n"
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    client = _mock(handler)
    result = await client.call_tool(
        _server(), credential="tok", tool_name="search", params={}
    )
    assert result.ok is True
    assert result.result == call_result


async def test_call_tool_no_credential_when_server_has_none():
    """A server with credential_ref=None calls without an Authorization header."""
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        payload = json.loads(request.content)
        if payload.get("method") == "notifications/initialized":
            return httpx.Response(202)
        req_id = payload.get("id")
        method = payload.get("method")
        result = {"initialize": {"protocolVersion": "2025-03-26"}, "tools/call": {}}[method]
        return httpx.Response(200, json=_jsonrpc(result, req_id))

    client = _mock(handler)
    await client.call_tool(_server(credential_ref=None), credential=None,
                           tool_name="t", params={})
    assert "authorization" not in seen_headers


# ── error normalization ────────────────────────────────────────────


async def test_call_tool_timeout_normalizes_to_timeout_code():
    """A transport-level timeout -> ok=False error_code=timeout (never raises).

    httpx.MockTransport handlers are synchronous, so we raise
    ``httpx.ReadTimeout`` (a ``httpx.TimeoutException`` subclass) to
    exercise the timeout branch of the client's error normalization.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = _mock(handler)
    result = await client.call_tool(
        _server(timeout_ms=50), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TIMEOUT


async def test_call_tool_http_error_normalizes_to_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _mock(handler)
    result = await client.call_tool(
        _server(), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TRANSPORT


async def test_call_tool_jsonrpc_error_normalizes_to_tool_error():
    def err_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            return httpx.Response(200, json=_jsonrpc({"protocolVersion": "2025-03-26"}, req_id))
        # tools/call returns a JSON-RPC error object.
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32602, "message": "invalid params"},
        })

    client = _mock(err_handler)
    result = await client.call_tool(
        _server(), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TOOL
    assert "invalid params" in result.error_message


async def test_call_tool_iserror_result_normalizes_to_tool_error():
    """A tools/call result with isError=true is a tool-level failure."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return httpx.Response(202)
        result = {
            "initialize": {"protocolVersion": "2025-03-26"},
            "tools/call": {
                "isError": True,
                "content": [{"type": "text", "text": "company not found"}],
            },
        }[method]
        return httpx.Response(200, json=_jsonrpc(result, req_id))

    client = _mock(handler)
    result = await client.call_tool(
        _server(), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TOOL
    assert "company not found" in result.error_message


# ── legacy sse transport ───────────────────────────────────────────


async def test_legacy_sse_transport_not_implemented():
    """sse enum -> transport_error (V1 not implemented)."""
    client = MCPClient()
    result = await client.call_tool(
        _server(transport="sse"), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TRANSPORT
    assert "sse" in result.error_message


async def test_unsupported_transport_rejected():
    client = MCPClient()
    result = await client.call_tool(
        _server(transport="websocket"), credential="tok", tool_name="t", params={}
    )
    assert result.ok is False
    assert result.error_code == ERROR_TRANSPORT


# ── list_tools (enable probe) ──────────────────────────────────────


async def test_list_tools_returns_tools_on_success():
    handler = _seq_handler({
        "initialize": [{"protocolVersion": "2025-03-26"}],
        "tools/list": [{"tools": [{"name": "search"}, {"name": "detail"}]}],
    })
    client = _mock(handler)
    tools = await client.list_tools(_server(), credential="tok")
    assert [t["name"] for t in tools] == ["search", "detail"]


async def test_list_tools_raises_typed_error_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = _mock(handler)
    with pytest.raises(MCPClientError) as exc:
        await client.list_tools(_server(), credential="tok")
    assert exc.value.error_code == ERROR_TRANSPORT
