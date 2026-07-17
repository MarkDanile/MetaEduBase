"""RBAC service: field-level visibility + cross-tenant grant check + audit log.

REQ-052 Task 3: thin orchestration layer on top of
:class:`PermissionsRepository` enforcing three policies:

1. **Field visibility** (strict-default MASKED) — if the role has no row in
   ``metaedu.role_permissions`` for the entity, every column is treated as
   sensitive and masked. Only columns explicitly mapped to ``visible`` are
   returned raw; ``hidden`` removes the column from response entirely.

2. **Cross-tenant grant** — same-tenant calls short-circuit to True. A
   cross-tenant call requires a still-valid grant row in
   ``metaedu.tenant_access_grants``.

3. **Audit log** — ``log_query`` validates ``business_purpose`` is
   either a non-empty string or ``None``. None means the user opted out
   of typing intent context (BUG-015); the audit row records the column
   as NULL.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.permissions import Role, Visibility
from app.contexts.structured_data.infrastructure.permissions_repository import (
    PermissionsRepository,
)


class RBACService:
    """Authorization decisions for the structured_data query path."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PermissionsRepository(session)

    # ------------------------------------------------------------ visibility

    async def get_field_visibility(
        self,
        tenant_id: uuid.UUID,
        role: Role,
        entity_type: str,
        column_name: str,
    ) -> Visibility:
        """Resolve the :class:`Visibility` for one column under one role.

        Strict-default policy (per REQ-052 §12): if no rule row exists, or
        the row exists but does not mention ``column_name``, return
        :attr:`Visibility.MASKED`. This means a misconfigured schema
        silently protects data instead of leaking it — defence-in-depth on
        top of the column-level ``sensitive`` flag in
        :class:`SemanticModel`.
        """
        rules = await self._repo.get_role_visibility_rules(
            tenant_id, role.value, entity_type
        )
        if not rules:
            return Visibility.MASKED
        if column_name not in rules:
            return Visibility.MASKED
        try:
            return Visibility(rules[column_name])
        except ValueError:
            # Unknown / typo'd value in DB — fall back to strict default.
            return Visibility.MASKED

    # ------------------------------------------------------------ tenant access

    async def check_tenant_access(
        self,
        tenant_id: uuid.UUID,
        grantee_tenant_id: uuid.UUID,
        entity_type: str,
    ) -> bool:
        """Return True iff the grantee tenant may read this entity_type.

        Same-tenant lookups short-circuit to True. Cross-tenant reads
        require an active row in ``metaedu.tenant_access_grants``.
        """
        if tenant_id == grantee_tenant_id:
            return True
        return await self._repo.check_tenant_grant(
            tenant_id, grantee_tenant_id, entity_type
        )

    # ------------------------------------------------------------ audit log

    async def log_query(self, **kwargs) -> None:
        """Persist a row to ``metaedu.query_audit_log`` after enforcing the
        ``business_purpose`` invariant.

        ``business_purpose`` may be a non-empty / non-whitespace string,
        or ``None``. Empty strings / whitespace-only strings are
        rejected with ``ValueError`` before any DB round-trip is
        attempted, so callers see a clear, actionable error instead of
        an integrity error from the driver. ``None`` (BUG-015 — user
        opted out of typing intent context) is forwarded to the DB
        unchanged so the audit row carries ``business_purpose=NULL``.
        """
        business_purpose = kwargs.get("business_purpose")
        if business_purpose is not None and (
            not isinstance(business_purpose, str) or not business_purpose.strip()
        ):
            raise ValueError(
                "business_purpose must be a non-empty string or None for "
                "query_audit_log (REQ-052 §12 / BUG-015)."
            )
        await self._repo.log_query(**kwargs)
