"""`GraphRetriever` Protocol 契约测试。"""

from __future__ import annotations

import inspect

import pytest

from app.contexts.knowledge.application.retrievers import GraphRetriever
from app.contexts.knowledge.application.retrievers_fake import FakeGraphRetriever


@pytest.mark.parametrize("impl", [FakeGraphRetriever])
def test_graph_retriever_implements_protocol(impl: object) -> None:
    assert isinstance(impl, GraphRetriever)


def test_graph_retriever_protocol_signature() -> None:
    proto_params = set(inspect.signature(GraphRetriever.retrieve).parameters)
    fake_params = set(inspect.signature(FakeGraphRetriever.retrieve).parameters)
    assert fake_params == proto_params, (
        f"FakeGraphRetriever.retrieve params {fake_params} "
        f"differ from Protocol {proto_params}"
    )


def test_fake_graph_retriever_returns_preset_evidence() -> None:
    import asyncio
    import uuid

    from app.contexts.knowledge.domain.evidence import EvidenceItem
    from app.shared.domain.ner_pipeline import NERResult

    async def _run() -> None:
        fake = FakeGraphRetriever()
        items = [
            EvidenceItem(
                evidence_id="",
                source_type="knowledge_node",
                file_id=uuid.uuid4(),
                node_id=uuid.uuid4(),
                title=f"node-{i}",
                content="desc",
            )
            for i in range(2)
        ]
        fake.return_value = items

        result = await fake.retrieve(
            query="hi",
            ner_result=NERResult(),
            tenant_id="t",
            session=None,  # type: ignore[arg-type]
            top_k=5,
        )
        assert len(result) == 2
        assert fake.calls[0]["top_k"] == 5

    asyncio.run(_run())
