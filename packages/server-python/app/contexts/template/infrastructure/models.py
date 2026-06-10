from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class TemplateModel(Base):
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(100), nullable=False)
    doc_types = Column(ARRAY(String(50)), nullable=False)
    fields = Column(JSONB(), nullable=False)
    ai_prompt = Column(Text, nullable=True)
    ai_context = Column(Text, nullable=True)
    source_file_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    # REQ-002-4: schema evolution + deprecation
    schema_version = Column(Integer, nullable=False, default=1, server_default="1")
    is_deprecated = Column(Boolean, nullable=False, default=False, server_default="false")
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_reason = Column(Text, nullable=True)


class TemplateVersionModel(Base):
    __tablename__ = "template_versions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    template_id = Column(UUID(as_uuid=True), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    version_number = Column(Integer, nullable=False, server_default="1")
    name = Column(String(100), nullable=False)
    doc_types = Column(ARRAY(String(50)), nullable=False)
    fields = Column(JSONB(), nullable=False)
    ai_prompt = Column(Text, nullable=True)
    ai_context = Column(Text, nullable=True)
    schema_version = Column(Integer, nullable=False, server_default="1")
    snapshot_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
