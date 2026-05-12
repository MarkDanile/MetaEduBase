from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from app.shared.domain.entity import AggregateRoot


class KnowledgeDomain(StrEnum):
    ELECTRONICS_INFO = "electronics_info"
    SMART_MANUFACTURING = "smart_manufacturing"
    FINANCE_COMMERCE = "finance_commerce"
    MEDICAL_HEALTH = "medical_health"
    EDUCATION_SPORTS = "education_sports"
    CIVIL_ENGINEERING = "civil_engineering"
    TRANSPORTATION = "transportation"
    AGRICULTURE = "agriculture"
    ART_DESIGN = "art_design"
    PUBLIC_SERVICE = "public_service"


class KnowledgeLevel(StrEnum):
    PROFESSIONAL = "professional"
    COURSE = "course"
    CHAPTER = "chapter"
    KNOWLEDGE_POINT = "knowledge_point"
    SKILL_POINT = "skill_point"
    OPERATION_STEP = "operation_step"


class KnowledgeNode(AggregateRoot):
    tenant_id: uuid.UUID
    title: str
    description: str | None = None
    domain: KnowledgeDomain
    level: KnowledgeLevel
    parent_id: uuid.UUID | None = None
    path: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    embedding_id: str | None = None
