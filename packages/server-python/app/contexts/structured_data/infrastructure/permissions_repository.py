"""Permissions repository: role_permissions + tenant_access_grants + query_audit_log.

REQ-052 Task 3: backs :class:`RBACService` with read access for
``role_permissions`` (visibility_rules) and ``tenant_access_grants`` (cross-
tenant grant checks), and write access for ``query_audit_log`` (audit per
query).

The repository is a thin async-SQLAlchemy wrapper — all authorization and
business rules live in :class:`RBACService`. This separation matches the
brief and lets the repo stay trivially mockable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.infrastructure.semantic_models_models import (
    QueryAuditLogModel,
    RolePermissionModel,
    TenantAccessGrantModel,
)


def _utcnow_naive() -> datetime:
    """Naive UTC ``datetime`` matching project convention.

    The DB stores naive UTC; passing tz-aware values would not match the
    index range, so we always compare and store naive UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class PermissionsRepository:
    """Async repository for the three RBAC tables in the ``metaedu`` schema."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ reads

    async def get_role_visibility_rules(
        self, tenant_id: uuid.UUID, role: str, entity_type: str
    ) -> dict | None:
        """Return the JSONB ``visibility_rules`` for one (tenant, role, entity) row.

        Returns ``None`` when no row exists — caller decides what strict
        default to apply. We don't fall back here so the policy stays in the
        service layer.
        """
        stmt = select(RolePermissionModel).where(
            RolePermissionModel.tenant_id == tenant_id,
            RolePermissionModel.role == role,
            RolePermissionModel.entity_type == entity_type,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.visibility_rules if row else None

    async def check_tenant_grant(
        self, tenant_id: uuid.UUID, grantee_tenant_id: uuid.UUID, entity_type: str
    ) -> bool:
        """Return True iff at least one (tenant, grantee, entity) grant row
        exists and is not expired (``expires_at`` is ``NULL`` or in the
        future).

        Multiple grants may exist (different admins, different scopes); we
        take any active one as sufficient.
        """
        stmt = select(TenantAccessGrantModel).where(
            TenantAccessGrantModel.tenant_id == tenant_id,
            TenantAccessGrantModel.grantee_tenant_id == grantee_tenant_id,
            TenantAccessGrantModel.entity_type == entity_type,
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        now = _utcnow_naive()
        return any(
            (r.expires_at is None or r.expires_at > now) for r in rows
        )

    # ----------------------------------------------------------------- writes

    async def log_query(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str,
        business_purpose: str | None,
        question: str,
        query_plan: dict,
        data_source_type: str,
        data_source_ref: str | None,
        result_count: int,
        duration_ms: int | None,
        ip: str | None,
        user_agent: str | None,
        catalog_id: uuid.UUID | None = None,
    ) -> None:
        """Append a row to ``metaedu.query_audit_log``.

        BUG-015: ``business_purpose`` is now optional. The DB schema
        (alembic migration 020) flipped the column to NULL-able so a user
        who opts out of typing intent context writes an audit row with
        ``business_purpose=NULL``. The identity / question / query_plan /
        result_count / IP / user-agent / catalog_id columns still pin
        the request to the actor and dataset, so spec §12 (国资审计)
        remains satisfied even when intent text is absent.

        ``catalog_id`` is REQ-054's audit-completeness tag: every audit row
        records which database the question was asked against. It is
        optional at the signature level because pre-REQ-054 callers
        (legacy tests) don't supply it; in production every
        :class:`QueryService.ask` call passes the resolved
        ``semantic_model.catalog_id`` so the audit log fully satisfies
        spec §12 (国资审计 / database-attribution completeness).
        """
        log = QueryAuditLogModel(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            catalog_id=catalog_id,
            business_purpose=business_purpose,
            question=question,
            query_plan=query_plan,
            data_source_type=data_source_type,
            data_source_ref=data_source_ref,
            result_count=result_count,
            duration_ms=duration_ms,
            ip=ip,
            user_agent=user_agent,
        )
        self._session.add(log)
        await self._session.flush()
