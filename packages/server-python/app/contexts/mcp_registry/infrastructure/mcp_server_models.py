"""MCP registry ORM for REQ-044 (metaedu.mcp_servers / mcp_invocation_audit).

Maps the two tables introduced in alembic migration 021. ``mcp_servers``
holds per-tenant MCP server registrations; ``credential_ref`` stores only
the *environment variable name* of the credential — the secret value is
never persisted. ``mcp_invocation_audit`` records every invocation attempt
with sha256 digests instead of raw params / response payloads.

The models mirror the column layout defined in the migration exactly —
``allowed_roles`` is a JSONB role whitelist, ``enabled`` defaults to false
so a freshly registered server must be explicitly enabled, and
``is_active`` is the soft-delete marker that keeps audit FK references
intact.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    """Naive UTC datetime matching the project convention."""
    return datetime.now(UTC).replace(tzinfo=None)


class MCPServerModel(Base):
    """ORM row over ``metaedu.mcp_servers``."""

    __tablename__ = "mcp_servers"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport: Mapped[str] = mapped_column(
        String(20), nullable=False, default="streamable_http"
    )
    server_url: Mapped[str] = mapped_column(String(500), nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    allowed_roles: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30000
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class MCPInvocationAuditModel(Base):
    """ORM row over ``metaedu.mcp_invocation_audit``."""

    __tablename__ = "mcp_invocation_audit"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.mcp_servers.id"),
        nullable=False,
    )
    server_code: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    caller_type: Mapped[str] = mapped_column(String(30), nullable=False)
    caller_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    params_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
