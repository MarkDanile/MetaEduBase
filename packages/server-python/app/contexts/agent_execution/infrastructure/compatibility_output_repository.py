from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.infrastructure.models import CompatibilityOutputModel


class CompatibilityOutputRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, row: CompatibilityOutputModel) -> None:
        self._session.add(row)
        await self._session.flush()

    async def get_by_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> CompatibilityOutputModel | None:
        return (
            await self._session.execute(
                select(CompatibilityOutputModel).where(
                    CompatibilityOutputModel.tenant_id == tenant_id,
                    CompatibilityOutputModel.run_id == run_id,
                )
            )
        ).scalar_one_or_none()

    async def get_by_ref(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        output_ref: str,
    ) -> CompatibilityOutputModel | None:
        return (
            await self._session.execute(
                select(CompatibilityOutputModel).where(
                    CompatibilityOutputModel.tenant_id == tenant_id,
                    CompatibilityOutputModel.conversation_id == conversation_id,
                    CompatibilityOutputModel.run_id == run_id,
                    CompatibilityOutputModel.output_ref == output_ref,
                )
            )
        ).scalar_one_or_none()
