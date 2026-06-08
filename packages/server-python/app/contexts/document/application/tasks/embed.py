"""`embed_chunks` Celery task — pipeline step 3 of 6 (DashScope bge-m3)."""

from __future__ import annotations

import logging
import uuid

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

from .pipeline_guard import _check_pipeline_stale

logger = logging.getLogger(__name__)


@shared_task(name="embed_chunks")
def embed_chunks(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="embed")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("embed_chunks %s: stale pipeline, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            result = await session.execute(
                text(
                    "SELECT id, content FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid AND embedding IS NULL "
                    "ORDER BY chunk_index"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            chunks = result.mappings().all()
            total = len(chunks)

            import httpx

            if not chunks:
                await _update_task_status(session, task_id, "success", 100)
                from .index import index_tsvector

                index_tsvector.delay(file_id_str, tenant_id_str, pipeline_version)
                return

            # Batch embedding — SiliconFlow supports batch input
            texts = [chunk["content"][:8192] for chunk in chunks]

            async def batch_embed_siliconflow(texts: list[str]) -> list[list[float]] | None:
                if not settings.siliconflow_api_key:
                    return None
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{settings.siliconflow_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                            json={"model": settings.siliconflow_embedding_model, "input": texts},
                        )
                        resp.raise_for_status()
                        return [item["embedding"] for item in resp.json()["data"]]
                except Exception as e:
                    logger.warning(f"SiliconFlow batch embedding failed: {e}")
                    return None

            async def batch_embed_minimax(texts: list[str]) -> list[list[float]] | None:
                if not settings.minimax_api_key:
                    return None
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            f"{settings.minimax_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {settings.minimax_api_key}"},
                            json={"model": settings.minimax_embedding_model, "input": texts},
                        )
                        resp.raise_for_status()
                        return [item["embedding"] for item in resp.json()["data"]]
                except Exception as e:
                    logger.warning(f"MiniMax batch embedding failed: {e}")
                    return None

            # Try MiniMax batch first, fallback to SiliconFlow batch
            embeddings = await batch_embed_minimax(texts)
            if not embeddings:
                embeddings = await batch_embed_siliconflow(texts)

            if not embeddings:
                logger.error(
                    "All embedding providers failed for all %d chunks (file=%s)",
                    total, file_id,
                )
                await _update_task_status(
                    session,
                    task_id,
                    "failed",
                    0,
                    "Embedding API failed: MiniMax and SiliconFlow both returned no results",
                )
                await session.commit()
                return

            # Batch update all chunks
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await session.execute(
                    text("UPDATE metaedu.document_chunks SET embedding = :vec WHERE id = :cid"),
                    {"vec": vec_str, "cid": chunk["id"]},
                )

            await _update_task_status(session, task_id, "running", 90)
            await session.commit()

            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task
            from .index import index_tsvector

            index_tsvector.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))
