"""MCPAdapter — V1 placeholder (REQ-052).

Mirror of :class:`DirectDBAdapter`: this adapter is intentionally a no-op
stub until stage 2, when the MCP (Model Context Protocol) client lands and
external tools / data sources become reachable through the same
:class:`DataSourceAdapter` contract.

Every entry point raises :class:`NotImplementedError`. Callers must use
:class:`ImportedDatasetAdapter` for V1.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)


class MCPAdapter(DataSourceAdapter):
    """V1 placeholder — raise NotImplementedError from every entry point."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "MCPAdapter 是 V1 计划，阶段 2 实现。当前用 ImportedDatasetAdapter。"
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
        raise NotImplementedError("MCPAdapter 是 V1 计划")

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        raise NotImplementedError("MCPAdapter 是 V1 计划")
