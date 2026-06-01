from sqlalchemy import Column, DateTime, String, Text
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
