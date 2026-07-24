from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.dto import EventReplayWindow
from app.contexts.agent_execution.domain import AgentRun, EventGapDetectedError
from app.contexts.agent_execution.infrastructure.execution_mappers import (
    to_event,
    to_run,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
)


class AgentExecutionQueryRepository:
    """Tenant-scoped Run/Event replay reads. It never commits its session."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_run(
        self, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun | None:
        row = (
            await self._session.execute(
                select(AgentRunModel).where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.id == run_id,
                )
            )
        ).scalar_one_or_none()
        return to_run(row) if row is not None else None

    async def read_event_replay_window(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        after_seq: int,
        limit: int,
        validate_full_range: bool,
    ) -> EventReplayWindow | None:
        run_row = (
            await self._session.execute(
                select(AgentRunModel)
                .where(
                    AgentRunModel.tenant_id == tenant_id,
                    AgentRunModel.id == run_id,
                )
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if run_row is None:
            return None
        if after_seq > run_row.last_event_seq:
            return EventReplayWindow(run=to_run(run_row), events=())
        lower_bound = max(after_seq + 1, run_row.first_available_event_seq)
        if validate_full_range and lower_bound <= run_row.last_event_seq:
            gap = await self._find_event_gap(
                tenant_id=tenant_id,
                run_id=run_id,
                lower_bound=lower_bound,
                upper_bound=run_row.last_event_seq,
            )
            if gap is not None:
                raise EventGapDetectedError(
                    expected_seq=gap[0],
                    received_seq=gap[1],
                )
        rows = (
            await self._session.execute(
                select(RunEventModel)
                .where(
                    RunEventModel.tenant_id == tenant_id,
                    RunEventModel.run_id == run_id,
                    RunEventModel.seq >= lower_bound,
                    RunEventModel.seq <= run_row.last_event_seq,
                )
                .order_by(RunEventModel.seq)
                .limit(limit)
            )
        ).scalars()
        return EventReplayWindow(
            run=to_run(run_row),
            events=tuple(to_event(row) for row in rows),
        )

    async def _find_event_gap(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        lower_bound: int,
        upper_bound: int,
    ) -> tuple[int, int | None] | None:
        count, minimum, maximum = (
            await self._session.execute(
                select(
                    func.count(RunEventModel.seq),
                    func.min(RunEventModel.seq),
                    func.max(RunEventModel.seq),
                ).where(
                    RunEventModel.tenant_id == tenant_id,
                    RunEventModel.run_id == run_id,
                    RunEventModel.seq >= lower_bound,
                    RunEventModel.seq <= upper_bound,
                )
            )
        ).one()
        expected_count = upper_bound - lower_bound + 1
        if count == expected_count and minimum == lower_bound and maximum == upper_bound:
            return None
        if minimum is None:
            return lower_bound, None
        if minimum != lower_bound:
            return lower_bound, minimum
        ordered = (
            select(
                RunEventModel.seq.label("seq"),
                func.lag(RunEventModel.seq)
                .over(order_by=RunEventModel.seq)
                .label("previous_seq"),
            )
            .where(
                RunEventModel.tenant_id == tenant_id,
                RunEventModel.run_id == run_id,
                RunEventModel.seq >= lower_bound,
                RunEventModel.seq <= upper_bound,
            )
            .subquery()
        )
        internal_gap = (
            await self._session.execute(
                select(ordered.c.previous_seq, ordered.c.seq)
                .where(
                    ordered.c.previous_seq.is_not(None),
                    ordered.c.seq != ordered.c.previous_seq + 1,
                )
                .order_by(ordered.c.seq)
                .limit(1)
            )
        ).one_or_none()
        if internal_gap is not None:
            return internal_gap.previous_seq + 1, internal_gap.seq
        assert maximum is not None
        return maximum + 1, None
