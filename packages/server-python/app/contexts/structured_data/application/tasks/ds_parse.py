"""`ds_parse` Celery task — structured_data pipeline step 1 of 4 (xlsx → rows)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

logger = logging.getLogger(__name__)


@shared_task(name="ds_parse")
def ds_parse(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        # Get dataset record
        result = await session.execute(
            text("SELECT * FROM metaedu.datasets WHERE id = :did AND tenant_id = :tid"),
            {"did": dataset_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            raise ValueError(f"Dataset {dataset_id} not found")

        task_id = await _create_task(
            session, tenant_id, dataset_id=dataset_id, task_type="ds_parse"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            source_file = row["source_file"]
            file_path = os.path.join(settings.upload_dir, source_file)

            if source_file and source_file.endswith((".xlsx", ".xls")):
                from app.shared.parsing.xlsx_parser import extract_xlsx_rows

                parsed = extract_xlsx_rows(file_path)
            else:
                raise ValueError(f"Unsupported file type: {source_file}")

            # Bulk insert rows
            now = datetime.now(UTC).replace(tzinfo=None)
            for i, row_data in enumerate(parsed.rows):
                row_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO metaedu.dataset_rows "
                        "(id, tenant_id, dataset_id, row_index, data, created_at) "
                        "VALUES (:id, :tid, :did, :idx, CAST(:data AS jsonb), :now)"
                    ),
                    {
                        "id": row_id,
                        "tid": tenant_id,
                        "did": dataset_id,
                        "idx": i,
                        "data": json.dumps(row_data),
                        "now": now,
                    },
                )

            # Update column metadata
            await session.execute(
                text(
                    "UPDATE metaedu.datasets "
                    "SET column_names = CAST(:cnames AS jsonb), "
                    "    column_types = CAST(:ctypes AS jsonb), "
                    "    row_count = :rcount, status = 'processed', "
                    "    updated_at = :now "
                    "WHERE id = :did"
                ),
                {
                    "cnames": json.dumps(parsed.column_names),
                    "ctypes": json.dumps(parsed.column_types),
                    "rcount": len(parsed.rows),
                    "now": now,
                    "did": dataset_id,
                },
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain directly to KG extraction
            from .ds_extract_kg import ds_extract_kg

            ds_extract_kg.delay(dataset_id_str, tenant_id_str)

            # TD-063 fix: return len(parsed.rows) so caller knows
            # how many rows were parsed.
            return len(parsed.rows)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET status = 'failed', updated_at = :now "
                    "WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )
            await session.commit()  # Commit failure status before re-raising
            raise

    # TD-063 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))
