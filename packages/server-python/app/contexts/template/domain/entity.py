from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

FieldType = Literal["text", "textarea", "number", "object", "table", "array"]

@dataclass
class TableColumn:
    key: str
    label: str
    type: Literal["text", "textarea", "number"]
    width: str | None = None

@dataclass
class Field:
    key: str
    label: str
    type: FieldType
    description: str | None = None
    children: list[Field] = field(default_factory=list)
    columns: list[TableColumn] = field(default_factory=list)
    items: list[Field] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Field:
        return cls(
            key=d["key"],
            label=d["label"],
            type=d["type"],
            description=d.get("description"),
            children=[Field.from_dict(c) for c in d.get("children", [])],
            columns=[TableColumn(**c) for c in d.get("columns", [])],
            items=[Field.from_dict(i) for i in d.get("items", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"key": self.key, "label": self.label, "type": self.type}
        if self.description:
            result["description"] = self.description
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.columns:
            result["columns"] = [c.__dict__ for c in self.columns]
        if self.items:
            result["items"] = [i.to_dict() for i in self.items]
        return result

@dataclass
class Template:
    id: UUID
    tenant_id: UUID
    name: str
    doc_types: list[str]
    fields: list[Field]
    ai_prompt: str | None = None
    ai_context: str | None = None
    source_file_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_db_row(cls, row: Any) -> Template:
        raw_fields = row.fields if isinstance(row.fields, list) else []
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            doc_types=list(row.doc_types or []),
            fields=[Field.from_dict(f) for f in raw_fields],
            ai_prompt=row.ai_prompt,
            ai_context=getattr(row, 'ai_context', None),
            source_file_id=row.source_file_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
