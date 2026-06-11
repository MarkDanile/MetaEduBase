import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.database import Base


class KnowledgeNodeModel(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        Index("ix_kn_tenant_domain", "tenant_id", "domain"),
        Index("ix_kn_tenant_parent", "tenant_id", "parent_id"),
        Index("ix_kn_tenant_level", "tenant_id", "level"),
        Index("ix_kn_path", "path"),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.tenants.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.knowledge_nodes.id")
    )
    path: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    embedding_id: Mapped[str | None] = mapped_column(String(100))
    embedding: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str | None] = mapped_column(Text)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # REQ-010 Slice 5: resolution status of source linkage.
    # 'chunk_resolved' = LLM extraction pinned the entity to a specific chunk.
    # 'file_only' = only source_file_id could be determined; chunk undecided.
    # NULL = legacy node, resolution status unknown (backfill candidates).
    node_source_resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    tenant = relationship("TenantModel", lazy="selectin")
    children = relationship(
        "KnowledgeNodeModel",
        lazy="selectin",
        backref="parent_node",
        remote_side="KnowledgeNodeModel.id",
    )


class KnowledgeEdgeModel(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        Index("ix_ke_source", "source_id"),
        Index("ix_ke_target", "target_id"),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.tenants.id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.knowledge_nodes.id"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.knowledge_nodes.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

    tenant = relationship("TenantModel", lazy="selectin")
    source = relationship("KnowledgeNodeModel", foreign_keys=[source_id], lazy="selectin")
    target = relationship("KnowledgeNodeModel", foreign_keys=[target_id], lazy="selectin")
