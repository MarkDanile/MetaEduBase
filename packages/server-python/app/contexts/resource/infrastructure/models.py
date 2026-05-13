import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.database import Base


class ResourceModel(Base):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_res_tenant_type", "tenant_id", "resource_type"),
        Index("ix_res_tenant_domain", "tenant_id", "domain"),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("metaedu.tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="raw")
    domain: Mapped[str | None] = mapped_column(String(50))
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    knowledge_point_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer)
    file_type: Mapped[str | None] = mapped_column(String(50))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("metaedu.users.id"), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

    tenant = relationship("TenantModel", lazy="selectin")
    uploader = relationship("UserModel", lazy="selectin")
