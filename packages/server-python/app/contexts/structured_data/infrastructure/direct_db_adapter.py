"""DirectDBAdapter — V1 placeholder (REQ-052).

This adapter is intentionally a no-op stub. The plan schedules direct-database
support (read-only SELECT against a whitelisted schema) for stage 2; until
then every entry point raises :class:`NotImplementedError` so the rest of the
pipeline can rely on the class existing and conforming to the
:class:`DataSourceAdapter` ABC.

Callers must switch to :class:`ImportedDatasetAdapter` for the V1 release.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)


class DirectDBAdapter(DataSourceAdapter):
    """V1 placeholder — raise NotImplementedError from every entry point."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "DirectDBAdapter 是 V1 计划，阶段 2 实现。当前用 ImportedDatasetAdapter。"
        )

    def get_data_source_type(self) -> str:
        return "direct_db"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        raise NotImplementedError("DirectDBAdapter 是 V1 计划")

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        raise NotImplementedError("DirectDBAdapter 是 V1 计划")
