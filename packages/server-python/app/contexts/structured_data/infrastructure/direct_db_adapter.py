"""DirectDBAdapter — V1 interface skeleton (REQ-054 Task 4).

Upgraded from the REQ-052 placeholder to a V1 read-only adapter that
connects to an external PostgreSQL via ``asyncpg`` and runs a simple
``SELECT * FROM <table> LIMIT N``.

Configuration (``data_source_config``):
    connection_string: str  # read-only PG connection string
    table_name: str         # the table to SELECT from

Security measures (V1):
- ``table_name`` is whitelisted via regex ``^[a-zA-Z_][a-zA-Z0-9_]*$``
  before interpolation into SQL — prevents SQL injection. Invalid names
  raise :class:`ValueError`.
- ``limit`` is clamped to 1000 (spec §5.5 soft cap).
- Only ``SELECT`` is issued; no DML/DDL. ``connection_string`` is
  expected to be a read-only role — enforced at the PG grant level, not
  here.

What V1 does **not** do yet:
- JSONB predicate filtering (``company_name = 'ACME'``). Lands in V2.
- Column whitelisting / projection (currently ``SELECT *``). Lands in V2
  with SqlGuard integration.
- ``tenant_id`` injection (the external PG is not multi-tenant in V1;
  RBAC + tenant scoping is the orchestrator's responsibility).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)

# Whitelist for table_name — only letters, digits, and underscores,
# starting with a letter or underscore. This prevents SQL injection
# since table_name is interpolated into the SQL string (asyncpg's
# parameterized queries don't support table identifiers as $N params).
_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Spec §5.5 soft cap — limit is clamped to this value to prevent
# unbounded result sets from the external database.
_MAX_LIMIT = 1000

# Default limit when query_plan doesn't specify one.
_DEFAULT_LIMIT = 100


class DirectDBAdapter(DataSourceAdapter):
    """V1: connect to external PostgreSQL and run read-only SELECT."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        config: dict | None = None,
    ) -> None:
        self._session = session
        self._config = config or {}

    def get_data_source_type(self) -> str:
        return "direct_db"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Execute a read-only SELECT against the external PG.

        Returns an empty list if ``connection_string`` or ``table_name``
        is missing from the config (defensive — the orchestrator should
        have called :meth:`validate_query` first).

        Raises :class:`ValueError` if ``table_name`` fails the regex
        whitelist check (SQL injection prevention).
        """
        conn_str = self._config.get("connection_string")
        table = self._config.get("table_name")
        if not conn_str or not table:
            return []

        # SQL injection prevention: validate table_name before interpolation.
        # asyncpg's $N parameters cannot be used for table identifiers,
        # so we must interpolate the table name directly — hence the
        # strict whitelist.
        if not _TABLE_NAME_PATTERN.match(table):
            raise ValueError(
                f"table_name '{table}' contains invalid characters; "
                f"only letters, digits, and underscores are allowed "
                f"(pattern: ^[a-zA-Z_][a-zA-Z0-9_]*$)."
            )

        # Clamp limit to the spec §5.5 soft cap.
        limit = min(int(query_plan.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)

        conn = await asyncpg.connect(conn_str)
        try:
            # Only SELECT is issued; table_name is whitelisted above;
            # limit is parameterized via $1.
            rows = await conn.fetch(
                f"SELECT * FROM {table} LIMIT $1", limit
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Check that ``connection_string`` and ``table_name`` are configured."""
        errors: list[str] = []
        if not self._config.get("connection_string"):
            errors.append("direct_db 缺少 connection_string 配置")
        if not self._config.get("table_name"):
            errors.append("direct_db 缺少 table_name 配置")
        return errors
