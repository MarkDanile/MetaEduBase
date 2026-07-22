import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.database import Base


class TenantModel(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    school_name: Mapped[str] = mapped_column(String(300), nullable=False)
    isolation: Mapped[str] = mapped_column(String(20), default="shared")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_tenant_username", "tenant_id", "username", unique=True),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.tenants.id"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="teacher")
    domain: Mapped[str | None] = mapped_column(String(100))
    clearance_level: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    tenant = relationship("TenantModel", lazy="selectin")


class TenantScopedConfigModel(Base):
    """REQ-058: tenant 级配置（Internal MCP / DD Catalog / Skill binding）。"""

    __tablename__ = "tenant_scoped_config"
    __table_args__ = (
        Index(
            "ix_tenant_scoped_config_tenant_id",
            "tenant_id",
        ),
        {"schema": "metaedu"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.tenants.id"),
        primary_key=True,
    )
    config_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    config_value: Mapped[dict] = mapped_column(
        JSONB(),
        nullable=False,
    )  # type: ignore[assignment]  # JSONB 存任意 JSON（dict/list/标量）
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
