"""Abstract data source adapter interface (REQ-052).

Every data source the semantic layer can reach — uploaded dataset
(``imported_dataset``), read-only ``direct_db``, or external ``mcp`` —
must implement this ABC. The repository and downstream query planner
are written against the ABC only; they have no knowledge of which
concrete adapter they end up talking to.

Three methods form the contract:

- :meth:`get_data_source_type` — discriminator string matching
  :class:`DataSourceType` values, so callers can pick the right adapter.
- :meth:`query` — execute a normalized query plan and return result rows
  as plain ``dict``s. **Every implementation must inject the
  ``tenant_id`` predicate** to enforce isolation.
- :meth:`validate_query` — return a list of error messages; empty list
  means the plan is acceptable.
"""

from __future__ import annotations

import abc
import uuid
from typing import Any


class CapabilityUnavailableError(Exception):
    """Raised when an adapter's capability is not yet implemented.

    Distinct from returning ``[]`` (which would masquerade as "query
    succeeded, no data"). The MCP V1 adapter raises this from
    :meth:`DataSourceAdapter.query` because no real MCP server is wired
    up yet - returning an empty list would let the orchestrator build a
    "0 results" summary for a request that never actually ran, hiding the
    capability gap from the user and the audit trail.

    The router / orchestrator maps this to a 501 Not Implemented (or a
    400 with a clear capability message) so the caller knows the path is
    intentionally unavailable rather than silently empty.
    """


class DataSourceAdapter(abc.ABC):
    """统一数据源适配器接口。语义层不绑死数据源类型。"""

    @abc.abstractmethod
    def get_data_source_type(self) -> str:
        """Return one of ``"imported_dataset"`` / ``"direct_db"`` / ``"mcp"``."""
        ...

    @abc.abstractmethod
    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Execute the query and return unified ``result_rows``.

        Implementations MUST apply ``tenant_id ==`` as a hard filter
        regardless of what ``query_plan`` contains — that's the security
        boundary against cross-tenant data leakage.
        """
        ...

    @abc.abstractmethod
    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Return a list of human-readable error messages.

        Empty list means the plan is acceptable. This is the place future
        slices will plug in SqlGuard / RBAC / PII rules.
        """
        ...
