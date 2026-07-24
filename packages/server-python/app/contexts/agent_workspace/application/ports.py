from __future__ import annotations

import uuid
from typing import Protocol


class ResourceReferenceAccessPort(Protocol):
    """Authorize opaque Resource references without importing Resource internals."""

    async def can_reference_resources(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_ids: tuple[uuid.UUID, ...],
    ) -> bool: ...
