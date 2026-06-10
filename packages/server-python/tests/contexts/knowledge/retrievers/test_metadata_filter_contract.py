"""`MetadataFilter` Protocol 契约测试。"""

from __future__ import annotations

import inspect

import pytest

from app.contexts.knowledge.application.retrievers import MetadataFilter
from app.contexts.knowledge.application.retrievers_fake import FakeMetadataFilter


@pytest.mark.parametrize("impl", [FakeMetadataFilter])
def test_metadata_filter_implements_protocol(impl: object) -> None:
    assert isinstance(impl, MetadataFilter)


def test_metadata_filter_protocol_signature() -> None:
    proto_params = set(inspect.signature(MetadataFilter.filter).parameters)
    fake_params = set(inspect.signature(FakeMetadataFilter.filter).parameters)
    assert fake_params == proto_params, (
        f"FakeMetadataFilter.filter params {fake_params} "
        f"differ from Protocol {proto_params}"
    )


def test_fake_metadata_filter_passes_through_candidates() -> None:
    import asyncio
    import uuid

    from app.contexts.knowledge.domain.evidence import EvidenceItem
    from app.shared.domain.ner_pipeline import NERResult

    async def _run() -> None:
        fake = FakeMetadataFilter()
        items = [
            EvidenceItem(
                evidence_id="",
                source_type="chunk",
                file_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
                title=f"c-{i}",
                content="x",
            )
            for i in range(4)
        ]
        result = await fake.filter(
            ner_result=NERResult(),
            tenant_id="t",
            session=None,  # type: ignore[arg-type]
            candidates=items,
        )
        assert len(result) == 4
        assert fake.calls[0]["candidate_count"] == 4

    asyncio.run(_run())
