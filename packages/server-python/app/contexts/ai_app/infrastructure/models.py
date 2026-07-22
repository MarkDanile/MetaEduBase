from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

from app.contexts.ai_app.domain.enums import AiAppEntryType, AiAppStatus, AiAppVisibility

Base = declarative_base()


class AiApplicationModel(Base):
    __tablename__ = "ai_applications"
    __table_args__ = {"schema": "metaedu"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    icon = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default=AiAppStatus.DRAFT.value)
    visibility = Column(String(20), nullable=False, default=AiAppVisibility.INTERNAL.value)
    entry_type = Column(String(20), nullable=False, default=AiAppEntryType.INTERNAL_ROUTE.value)
    route_path = Column(String(200), nullable=True)
    external_url = Column(String(500), nullable=True)
    config_schema = Column(JSONB, nullable=True)
    required_capabilities = Column(JSONB, nullable=True)
    owner = Column(String(200), nullable=True)
    version = Column(String(20), nullable=False, default="1.0.0")
    sort_order = Column(Integer, nullable=False, default=0)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)
    # BUG-018 AC-3: 平台应用跨租户可见，仅 super_admin 可写。
    is_platform = Column(Boolean, nullable=False, default=False)
    share_token = Column(String(100), nullable=True, unique=True)
    api_token = Column(String(100), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
