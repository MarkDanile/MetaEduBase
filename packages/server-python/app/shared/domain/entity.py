from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Entity(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class AggregateRoot(Entity):
    _domain_events: list = []

    def add_domain_event(self, event) -> None:
        self._domain_events.append(event)

    def clear_domain_events(self) -> list:
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
