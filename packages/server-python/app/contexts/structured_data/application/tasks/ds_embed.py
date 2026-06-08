"""`ds_embed` Celery task — structured_data pipeline step 2 of 4 (row embeddings)."""

from __future__ import annotations

import logging
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


@shared_task(name="ds_embed")
def ds_embed(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(
            session, tenant_id, dataset_id=dataset_id, task_type="ds_embed"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Get all rows
            result = await session.execute(
                text(
                    "SELECT id, data FROM metaedu.dataset_rows "
                    "WHERE dataset_id = :did AND tenant_id = :tid ORDER BY row_index"
                ),
                {"did": dataset_id, "tid": tenant_id},
            )
            rows = result.mappings().all()

            # Use same embedding approach as document tasks: MiniMax first, SiliconFlow fallback
            mm_key = settings.minimax_api_key
            sf_key = settings.siliconflow_api_key
            if not mm_key and not sf_key:
                raise RuntimeError(
                    "No embedding API key configured "
                    "(MINIMAX_API_KEY or SILICONFLOW_API_KEY required)"
                )

            import httpx

            async def embed_one(client: httpx.AsyncClient, text_in: str) -> list[float] | None:
                if mm_key:
                    try:
                        resp = await client.post(
                            f"{settings.minimax_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {mm_key}"},
                            json={"model": settings.minimax_embedding_model, "input": [text_in]},
                        )
                        resp.raise_for_status()
                        return resp.json()["data"][0]["embedding"]
                    except Exception as e:
                        logger.warning(f"MiniMax embed failed: {e}")
                if sf_key:
                    try:
                        resp = await client.post(
                            f"{settings.siliconflow_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {sf_key}"},
                            json={
                                "model": settings.siliconflow_embedding_model,
                                "input": [text_in],
                            },
                        )
                        resp.raise_for_status()
                        return resp.json()["data"][0]["embedding"]
                    except Exception as e:
                        logger.warning(f"SiliconFlow embed failed: {e}")
                return None

            success_count = 0
            async with httpx.AsyncClient(timeout=60.0) as client:
                for i, row in enumerate(rows):
                    text_parts = [str(v) for v in row["data"].values()]
                    embed_text = " ".join(text_parts)[:8192]
                    embedding = await embed_one(client, embed_text)
                    if not embedding:
                        continue
                    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

                    # Insert chunk first (without embedding), then update embedding
                    chunk_id = uuid.uuid4()
                    now = datetime.now(UTC).replace(tzinfo=None)
                    await session.execute(
                        text(
                            "INSERT INTO metaedu.document_chunks "
                            "(id, tenant_id, file_id, chunk_index, content, created_at) "
                            "VALUES (:id, :tid, :fid, :idx, :content, :now)"
                        ),
                        {
                            "id": chunk_id,
                            "tid": tenant_id,
                            "fid": dataset_id,
                            "idx": i,
                            "content": embed_text,
                            "now": now,
                        },
                    )
                    await session.execute(
                        text("UPDATE metaedu.document_chunks SET embedding = :vec WHERE id = :cid"),
                        {"vec": vec_str, "cid": chunk_id},
                    )
                    success_count += 1
                    progress = int((i + 1) / len(rows) * 100) if rows else 100
                    await _update_task_status(session, task_id, "running", progress)
                    await session.commit()

            if rows and success_count == 0:
                raise RuntimeError(f"All embeddings failed (0 of {len(rows)} rows succeeded)")

            # Update kg_status
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'pending', "
                    "updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            from .ds_extract_kg import ds_extract_kg

            ds_extract_kg.delay(dataset_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()  # Commit failure status before re-raising
            raise

    asyncio.run(_run_in_session(_do))
