"""`ChunkRetriever` Protocol 契约测试。

REQ-010 Slice 2 — 参照 `RecallChannel` Protocol 风格（见 TD-030 收口），用
`set(sig.parameters)` 与 Protocol 严格对齐；不依赖下划线前缀做兼容。
"""

from __future__ import annotations

import inspect

import pytest

from app.contexts.knowledge.application.retrievers import ChunkRetriever
from app.contexts.knowledge.application.retrievers_fake import FakeChunkRetriever


@pytest.mark.parametrize("impl", [FakeChunkRetriever])
def test_chunk_retriever_implements_protocol(impl: object) -> None:
    """FakeChunkRetriever must satisfy the ChunkRetriever Protocol at runtime."""
    assert isinstance(impl, ChunkRetriever)


def test_chunk_retriever_protocol_signature() -> None:
    """Protocol signature must match the contract documented in the spec.

    Required parameters (positional + keyword-only):
      query, ner_result, tenant_id, session, *, top_k=5, file_filter=None
    """
    proto_params = set(inspect.signature(ChunkRetriever.retrieve).parameters)
    fake_params = set(inspect.signature(FakeChunkRetriever.retrieve).parameters)
    assert fake_params == proto_params, (
        f"FakeChunkRetriever.retrieve params {fake_params} "
        f"differ from Protocol {proto_params}"
    )


def test_fake_chunk_retriever_returns_preset_evidence() -> None:
    """FakeChunkRetriever should return its preset return_value (capped by top_k)."""
    import asyncio
    import uuid

    from app.contexts.knowledge.domain.evidence import EvidenceItem
    from app.shared.domain.ner_pipeline import NERResult

    async def _run() -> None:
        fake = FakeChunkRetriever()
        items = [
            EvidenceItem(
                evidence_id="",
                source_type="chunk",
                file_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
                title=f"chunk-{i}",
                content="x",
            )
            for i in range(3)
        ]
        fake.return_value = items

        result = await fake.retrieve(
            query="hi",
            ner_result=NERResult(),
            tenant_id="tenant-1",
            session=None,  # type: ignore[arg-type]
            top_k=2,
        )
        assert len(result) == 2
        assert result[0].title == "chunk-0"
        assert fake.calls[0]["top_k"] == 2

    asyncio.run(_run())


def test_fake_chunk_retriever_records_file_filter() -> None:
    """FakeChunkRetriever must capture the optional file_filter argument."""
    import asyncio

    from app.shared.domain.ner_pipeline import NERResult

    async def _run() -> None:
        fake = FakeChunkRetriever()
        await fake.retrieve(
            query="q",
            ner_result=NERResult(),
            tenant_id="t",
            session=None,  # type: ignore[arg-type]
            top_k=5,
            file_filter=["file-a", "file-b"],
        )
        assert fake.calls[0]["file_filter"] == ["file-a", "file-b"]

    asyncio.run(_run())
