"""MCPAdapter — real MCP invocation via the REQ-044 registry.

Rewired in REQ-044 Task 3: the adapter no longer raises
``CapabilityUnavailableError`` (the REQ-054/REQ-057 V1 placeholder).
``data_source_config`` now names a *registered* MCP server plus tool:

    server_code: str    # code of a row in metaedu.mcp_servers (this tenant)
    tool_name: str      # the tool to invoke on that server

``query`` delegates to
:class:`~app.contexts.mcp_registry.application.mcp_invocation_service.MCPInvocationService`,
which resolves the server for the tenant, enforces enabled / role /
credential gates, calls the MCP transport, and writes the
``mcp_invocation_audit`` row. Unregistered / disabled / forbidden /
transport failures propagate as typed
:class:`MCPInvocationError` / :class:`MCPInvocationServerNotFoundError` —
explicit failures, never an empty-list success and never a
capability-placeholder masquerade.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationService,
)
from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)


class MCPAdapter(DataSourceAdapter):
    """MCP data source adapter: delegates to ``MCPInvocationService``."""

    def __init__(
        self,
        session: Any = None,
        config: dict | None = None,
        invocation_service: MCPInvocationService | None = None,
    ) -> None:
        self._config = config or {}
        # Assembly boundary preserved: the adapter receives the service;
        # only MCPInvocationService constructs the MCPClient.
        self._invocation_service = invocation_service or (
            MCPInvocationService(session) if session is not None else None
        )

    def get_data_source_type(self) -> str:
        return "mcp"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Invoke the configured MCP tool and normalize rows.

        Explicit-failure contract: config gaps raise ``ValueError``;
        registry / permission / transport failures propagate as
        :class:`MCPInvocationError` (audited by the invocation service)
        or :class:`MCPInvocationServerNotFoundError` (unregistered). Nothing
        here swallows a failure into ``[]``.
        """
        if self._invocation_service is None:
            raise ValueError(
                "MCPAdapter 需要 MCPInvocationService（经 session 装配或显式注入）"
            )
        server_code = self._config.get("server_code")
        tool_name = self._config.get("tool_name")
        if not server_code or not tool_name:
            raise ValueError(
                "mcp 数据源配置不完整：需要 server_code 与 tool_name"
            )
        result = await self._invocation_service.invoke(
            tenant_id=tenant_id,
            server_code=str(server_code),
            tool_name=str(tool_name),
            params=query_plan,
            caller=InvocationCaller(
                caller_type="adapter:structured_data",
                role=user_role,
                user_id=None,
            ),
        )
        return self._rows_from_result(result)

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Check that ``server_code`` and ``tool_name`` are configured."""
        errors: list[str] = []
        if not self._config.get("server_code"):
            errors.append("mcp 缺少 server_code 配置")
        if not self._config.get("tool_name"):
            errors.append("mcp 缺少 tool_name 配置")
        return errors

    @staticmethod
    def _rows_from_result(result: Any) -> list[dict]:
        """Normalize a ``tools/call`` result into ``list[dict]`` rows.

        Prefers MCP ``structuredContent``; falls back to JSON-encoded
        ``content`` text items; last resort wraps the raw result dict.

        A non-dict result (e.g. a bare list from a non-spec server) or an
        empty result yields ``[]`` - never a phantom ``[{}]`` row that
        would inflate ``result_count`` downstream.
        """
        # Entry guard: defend against non-spec result shapes (a bare list
        # would AttributeError on ``.get``) and empty results (which must
        # not become a phantom single-row ``[{}]``).
        if not isinstance(result, dict) or not result:
            return []
        structured = result.get("structuredContent")
        if isinstance(structured, list):
            return [r for r in structured if isinstance(r, dict)]
        if isinstance(structured, dict):
            rows = structured.get("rows")
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
            return [structured]
        content = result.get("content")
        if isinstance(content, list):
            texts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            parsed: list[dict] = []
            for text_item in texts:
                if not text_item:
                    continue
                try:
                    payload = json.loads(text_item)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(payload, list):
                    parsed.extend(r for r in payload if isinstance(r, dict))
                elif isinstance(payload, dict):
                    parsed.append(payload)
            return parsed
        return [result]
