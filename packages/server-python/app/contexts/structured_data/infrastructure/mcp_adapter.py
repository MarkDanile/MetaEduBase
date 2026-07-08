"""MCPAdapter — V1 interface skeleton (REQ-054 Task 4).

Upgraded from the REQ-052 placeholder to a V1 interface skeleton. V1
does **not** connect to a real MCP (Model Context Protocol) server —
``query`` returns an empty list and ``validate_query`` checks config
completeness. V2 will wire up the QCC MCP server.

Configuration (``data_source_config``):
    server_url: str     # MCP server URL
    tool_name: str      # the tool to invoke on the MCP server
"""

from __future__ import annotations

import uuid
from typing import Any

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)


class MCPAdapter(DataSourceAdapter):
    """V1: MCP service mapping interface skeleton (no real server)."""

    def __init__(
        self,
        session: Any = None,
        config: dict | None = None,
    ) -> None:
        self._config = config or {}

    def get_data_source_type(self) -> str:
        return "mcp"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """V1: return an empty list — no real MCP server is connected.

        V2 will connect to the QCC MCP server via ``server_url`` and
        invoke ``tool_name`` with the query plan.
        """
        return []

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Check that ``server_url`` and ``tool_name`` are configured."""
        errors: list[str] = []
        if not self._config.get("server_url"):
            errors.append("mcp 缺少 server_url 配置")
        if not self._config.get("tool_name"):
            errors.append("mcp 缺少 tool_name 配置")
        return errors
