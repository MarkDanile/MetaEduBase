"""Skill registry ORM for REQ-045 (metaedu.skills / skill_execution_audit).

Maps the two tables introduced in alembic migration 022. ``skills`` holds
per-tenant skill registrations — each skill is a declarative SOP template
(YAML body in ``sop_template``, never containing secrets) with semantic
versioning (``(tenant_id, code, version)`` unique), a role whitelist
(``allowed_roles``), and an ``enabled`` flag defaulting to false so a
freshly registered skill must be explicitly enabled. ``is_active`` is the
soft-delete marker that keeps audit FK references intact.

``skill_execution_audit`` records every execution attempt with sha256
digests of the subject / per-step results / synthesized report instead of
raw content — facts and report bodies never land in the audit table.

The models mirror the column layout defined in the migration exactly.
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


class SkillModel(Base):
    """ORM row over ``metaedu.skills``."""

    __tablename__ = "skills"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sop_template: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allowed_roles: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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


class SkillExecutionAuditModel(Base):
    """ORM row over ``metaedu.skill_execution_audit``."""

    __tablename__ = "skill_execution_audit"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.skills.id"),
        nullable=False,
    )
    skill_code: Mapped[str] = mapped_column(String(50), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(20), nullable=False)
    caller_type: Mapped[str] = mapped_column(String(30), nullable=False)
    caller_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    subject_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    steps_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
