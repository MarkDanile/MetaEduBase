from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class TemplateVersion:
    id: UUID
    template_id: UUID
    tenant_id: UUID
    version_number: int
    name: str
    doc_types: list[str]
    fields: list[dict[str, Any]]
    ai_prompt: str | None
    ai_context: str | None
    schema_version: int
    snapshot_at: datetime
