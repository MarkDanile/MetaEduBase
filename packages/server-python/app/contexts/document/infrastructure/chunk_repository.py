"""Document chunk repository — raw SQL implementation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_file(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT id, tenant_id, file_id, chunk_index, content, section_title, "
                "section_path, "
                "char_start, char_end, created_at, "
                "CASE WHEN embedding IS NOT NULL THEN true ELSE false END AS has_embedding "
                "FROM metaedu.document_chunks "
                "WHERE file_id = :fid AND tenant_id = :tid "
                "ORDER BY chunk_index"
            ),
            {"fid": file_id, "tid": tenant_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_chunks_by_file_and_indices(
        self,
        file_id: uuid.UUID,
        indices: list[int],
        tenant_id: uuid.UUID,
    ) -> dict[int, dict]:
        """Fetch specific chunk_index values for one file.

        Returns a dict mapping chunk_index -> row dict.
        Empty list or no matches → empty dict (not an error).
        """
        if not indices:
            return {}
        result = await self._session.execute(
            text(
                "SELECT id, tenant_id, file_id, chunk_index, content, section_title, "
                "section_path, char_start, char_end, created_at, "
                "CASE WHEN embedding IS NOT NULL THEN true ELSE false END AS has_embedding "
                "FROM metaedu.document_chunks "
                "WHERE file_id = :fid AND tenant_id = :tid AND chunk_index = ANY(:indices) "
                "ORDER BY chunk_index"
            ),
            {"fid": file_id, "tid": tenant_id, "indices": indices},
        )
        return {row["chunk_index"]: dict(row) for row in result.mappings().all()}

    async def get_chunk_by_id(self, chunk_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        """Fetch a single chunk row by its primary key id. Returns None if not found."""
        result = await self._session.execute(
            text(
                "SELECT id, tenant_id, file_id, chunk_index, content, section_title, "
                "section_path, char_start, char_end, created_at, "
                "CASE WHEN embedding IS NOT NULL THEN true ELSE false END AS has_embedding "
                "FROM metaedu.document_chunks "
                "WHERE id = :cid AND tenant_id = :tid "
                "LIMIT 1"
            ),
            {"cid": chunk_id, "tid": tenant_id},
        )
        rows = result.mappings().all()
        return dict(rows[0]) if rows else None

    async def bulk_insert(
        self, tenant_id: uuid.UUID, file_id: uuid.UUID, chunks: list[dict]
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        for chunk in chunks:
            chunk_id = uuid.uuid4()
            await self._session.execute(
                text(
                    "INSERT INTO metaedu.document_chunks "
                    "(id, tenant_id, file_id, chunk_index, content, section_title, "
                    "section_path, char_start, char_end, created_at) "
                    "VALUES (:id, :tid, :fid, :idx, :content, :stitle, "
                    ":spath, :cstart, :cend, :now)"
                ),
                {
                    "id": chunk_id,
                    "tid": tenant_id,
                    "fid": file_id,
                    "idx": chunk["index"],
                    "content": chunk["content"],
                    "stitle": chunk.get("section_title"),
                    "spath": chunk.get("section_path"),
                    "cstart": chunk.get("char_start"),
                    "cend": chunk.get("char_end"),
                    "now": now,
                },
            )

    async def update_embedding(self, chunk_id: uuid.UUID, embedding: list[float]) -> None:
        await self._session.execute(
            text("UPDATE metaedu.document_chunks SET embedding = :vec::vector WHERE id = :cid"),
            {"vec": json.dumps(embedding), "cid": chunk_id},
        )

    async def update_tsvector(self, chunk_id: uuid.UUID) -> None:
        await self._session.execute(
            text(
                "UPDATE metaedu.document_chunks "
                "SET content_tsvector = to_tsvector('chinese_zh', content) "
                "WHERE id = :cid"
            ),
            {"cid": chunk_id},
        )

    async def delete_by_file(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        """Delete all chunks for a file. Returns the number of rows deleted.

        BUG-004: returning the rowcount lets the caller (e.g.
        cleanup_file_derivatives) verify the cascade actually ran.
        Previously this returned None — silently swallowed delete
        failures, leaving orphan rows in the DB.
        """
        result = await self._session.execute(
            text("DELETE FROM metaedu.document_chunks WHERE file_id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
        return result.rowcount or 0
